'use strict';
/*
 * XEM TỪ XA BẰNG TÀI KHOẢN: nhập tài khoản + mật khẩu ở app PC và app điện thoại, điện thoại tự tìm và nối vào game.
 *  1) Từ tài khoản + mật khẩu tính ra: mã vào cửa (token), tên hòm thư (topic), khóa mã hóa (xem account-core.js).
 *  2) Mở đường hầm Internet (tunnel.js) -> có địa chỉ https tạm.
 *  3) Mã hóa địa chỉ đó rồi gửi vào hòm thư (rendezvous.js). Điện thoại lấy, giải mã, nối vào kèm mã vào cửa.
 *  4) Người lạ biết địa chỉ đường hầm vẫn KHÔNG vào được: applink.js chỉ cho qua khi có đúng mã vào cửa.
 * Mật khẩu KHÔNG được lưu trên máy; chỉ lưu 3 giá trị dẫn xuất ở data/remote-keys.json (đừng gửi file này cho ai).
 */
const fs = require('fs');
const path = require('path');
const { EventEmitter } = require('events');
const A = require('./account-core');
const applink = require('./applink');
const rendezvous = require('./rendezvous');
const { Tunnel } = require('./tunnel');
const { Zrok } = require('./zrok');

const REPUBLISH_MS = 5 * 60 * 1000; // gửi lại địa chỉ định kỳ (ntfy giữ tin ~12 giờ) để điện thoại luôn tìm được bản mới
const HEALTH_EVERY_MS = 20 * 1000; // cứ 20 giây tự gọi thử chính đường hầm từ bên ngoài
const HEALTH_GRACE_MS = 40 * 1000; // vừa mở xong cần vài chục giây để mạng Cloudflare nhận địa chỉ mới
const HEALTH_FAILS = 3; // cloudflared báo MẤT kết nối liên tiếp bấy nhiêu lần (~1 phút) thì dựng lại đường hầm
const FALLBACK_AFTER_MS = 60 * 1000; // Cloudflare chưa lên được sau bấy lâu mà đã có mã zrok -> bật đường dự phòng zrok
const DELAY_AFTER_URL_MS = 4000; // địa chỉ mới cần vài giây để mạng Cloudflare nhận

class Remote extends EventEmitter {
  constructor({ dataDir, port, log }) {
    super();
    this.dir = dataDir;
    this.port = port;
    this.log = log || (() => {});
    this.tunnel = new Tunnel(dataDir);
    this.zrok = new Zrok(dataDir);
    this.cfBadSince = 0;
    this.cfg = { enabled: false, account: '', server: rendezvous.DEFAULT_SERVER };
    this.keys = null; // { token, topic, keyB64 }
    this.key = null;
    this.published = 0;
    this.pubError = '';
    this.phones = () => 0;
    this.timers = [];
    this.lastUrl = '';
    this.tunnel.on('status', (s) => this.onTunnel(s));
    this.tunnel.on('log', (m) => this.log(m));
    this.zrok.on('status', (s) => this.onTunnel(s));
    this.zrok.on('log', (m) => this.log(m));
    // true = còn kết nối, false = cloudflared báo mất hết kết nối, null = không biết (không làm gì). Có thể thay khi kiểm tra tự động.
    this.probe = () => this.tunnel.ready();
    this.healthFails = 0;
    this.onlineAt = 0;
    this.load();
  }

  file(n) {
    return path.join(this.dir, n);
  }

  load() {
    try {
      Object.assign(this.cfg, JSON.parse(fs.readFileSync(this.file('remote.json'), 'utf8')));
    } catch (e) {
      /* chưa cài */
    }
    try {
      this.keys = JSON.parse(fs.readFileSync(this.file('remote-keys.json'), 'utf8'));
    } catch (e) {
      this.keys = null;
    }
  }

  save() {
    fs.mkdirSync(this.dir, { recursive: true });
    fs.writeFileSync(this.file('remote.json'), JSON.stringify(this.cfg));
    if (this.keys) fs.writeFileSync(this.file('remote-keys.json'), JSON.stringify(this.keys));
  }

  /** Gọi khi game khởi động: nếu đã bật từ trước thì tự mở lại. */
  async autostart() {
    if (this.cfg.enabled && this.keys) await this.enable();
  }

  async configure(account, password, enabled = true) {
    if (!enabled) return this.disable();
    const d = await A.derive(account, password); // ném lỗi nếu quá ngắn
    this.keys = { token: d.token, topic: d.topic, keyB64: d.keyB64 };
    this.cfg.account = A.normAccount(account);
    this.cfg.enabled = true;
    this.save();
    this.tunnel.stop();
    this.zrok.stop();
    this.lastUrl = '';
    return this.enable();
  }

  async enable() {
    this.key = await A.keyFrom(this.keys.keyB64);
    applink.setRemoteToken(this.keys.token);
    this.cfg.enabled = true;
    this.pubError = '';
    this.tunnel.start(this.port);
    this.timers.push(setInterval(() => this.publish().catch(() => {}), REPUBLISH_MS));
    this.timers.push(setInterval(() => this.health().catch(() => {}), HEALTH_EVERY_MS));
    this.cfBadSince = Date.now();
    this.timers.push(setInterval(() => this.fallback(), HEALTH_EVERY_MS));
    this.emit('status', this.status());
    return this.status();
  }

  disable() {
    // báo cho điện thoại biết là đã TẮT (để khỏi cố nối vào địa chỉ cũ đã chết)
    if (this.key && this.keys && this.cfg.enabled) {
      A.seal(this.key, { v: 1, t: Date.now(), off: true }).then((text) => rendezvous.publish(this.cfg.server, this.keys.topic, text)).catch(() => {});
    }
    this.cfg.enabled = false;
    this.save();
    applink.setRemoteToken('');
    for (const t of this.timers) clearInterval(t);
    this.timers = [];
    this.tunnel.stop();
    this.zrok.stop();
    this.published = 0;
    return this.status();
  }

  /** Gọi thử đường hầm từ bên ngoài: nếu "đứng" (tiến trình còn nhưng không ai vào được) thì dựng lại. */
  async health(now = Date.now()) {
    const t = this.tunnel;
    if (!this.cfg.enabled || t.state !== 'online' || !t.url || now - this.onlineAt < HEALTH_GRACE_MS) return;
    let ok = null;
    try {
      ok = await this.probe(t.url);
    } catch (e) {
      ok = null;
    }
    if (t.url === '' || t.state !== 'online') return; // trong lúc chờ đã đổi trạng thái
    if (ok === null) return; // không hỏi được thì không kết luận (tránh dựng lại oan một đường truyền đang tốt)
    if (ok) {
      this.healthFails = 0;
      return;
    }
    this.healthFails++;
    if (this.healthFails >= HEALTH_FAILS) {
      this.healthFails = 0;
      t.restart('cloudflared báo mất kết nối tới Cloudflare');
    }
  }

  /** Địa chỉ đang dùng được: ưu tiên Cloudflare, nếu không có thì zrok (dự phòng). */
  cur() {
    const t = this.tunnel;
    if (t.state === 'online' && t.url) return { src: 'cloudflare', url: t.url };
    const z = this.zrok;
    if (z.state === 'online' && z.url) return { src: 'zrok', url: z.url };
    return null;
  }

  /** Cloudflare mãi không lên mà đã có mã zrok -> bật zrok; Cloudflare lên rồi -> tắt zrok cho đỡ tốn. */
  fallback(now = Date.now()) {
    if (!this.cfg.enabled) return;
    if (this.tunnel.state === 'online') {
      this.cfBadSince = 0;
      if (this.zrok.want) {
        setTimeout(() => {
          if (this.tunnel.state === 'online') this.zrok.stop();
        }, 15000);
      }
      return;
    }
    if (!this.cfBadSince) this.cfBadSince = now;
    if (now - this.cfBadSince >= FALLBACK_AFTER_MS && this.zrok.hasToken() && !this.zrok.want) {
      this.log('Cloudflare chưa lên được, chuyển sang đường dự phòng zrok…');
      this.zrok.start(this.port);
    }
  }

  setZrokToken(token) {
    const has = this.zrok.setToken(token);
    if (!has) this.zrok.stop();
    this.emit('status', this.status());
    return this.status();
  }

  onTunnel() {
    const c = this.cur();
    if (c && c.url !== this.lastUrl) {
      this.lastUrl = c.url;
      this.onlineAt = Date.now();
      this.healthFails = 0;
      setTimeout(() => this.publish().catch(() => {}), DELAY_AFTER_URL_MS);
    }
    this.emit('status', this.status());
  }

  async publish() {
    const c = this.cur();
    if (!this.cfg.enabled || !this.key || !c) return;
    try {
      const text = await A.seal(this.key, { v: 1, t: Date.now(), url: c.url });
      await rendezvous.publish(this.cfg.server, this.keys.topic, text);
      this.published = Date.now();
      this.pubError = '';
      this.log('Đã báo địa chỉ cho điện thoại (đã mã hóa).');
    } catch (e) {
      this.pubError = e.message;
      this.log('Chưa báo được cho điện thoại:', e.message);
      setTimeout(() => this.publish().catch(() => {}), 30000);
    }
    this.emit('status', this.status());
  }

  status() {
    const t = this.tunnel.info();
    const z = this.zrok.info();
    const c = this.cur();
    let tunnel = t.state;
    let url = t.url;
    let error = t.error;
    let progress = t.progress;
    let via = 'cloudflare';
    if (c && c.src === 'zrok') {
      tunnel = 'online';
      url = c.url;
      error = '';
      via = 'zrok';
    } else if (this.zrok.want && t.state !== 'online') {
      // đang chạy đường dự phòng: nói rõ cả hai bên
      if (z.state !== 'off') tunnel = z.state;
      progress = z.state === 'downloading' ? z.progress : progress;
      error = [t.error && 'Cloudflare: ' + t.error, z.error && 'zrok: ' + z.error].filter(Boolean).join(' | ');
    }
    return {
      enabled: !!this.cfg.enabled,
      account: this.cfg.account,
      hasKeys: !!this.keys,
      tunnel,
      via,
      zrokSet: this.zrok.hasToken(),
      url,
      progress,
      error: error || this.pubError,
      published: this.published,
      phones: this.phones(),
      server: this.cfg.server,
    };
  }
}

module.exports = { Remote };
