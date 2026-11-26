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

const REPUBLISH_MS = 5 * 60 * 1000; // gửi lại địa chỉ định kỳ (ntfy giữ tin ~12 giờ) để điện thoại luôn tìm được bản mới
const HEALTH_EVERY_MS = 20 * 1000; // cứ 20 giây tự gọi thử chính đường hầm từ bên ngoài
const HEALTH_GRACE_MS = 40 * 1000; // vừa mở xong cần vài chục giây để mạng Cloudflare nhận địa chỉ mới
const HEALTH_FAILS = 2; // thử hỏng liên tiếp bấy nhiêu lần thì dựng lại đường hầm
const DELAY_AFTER_URL_MS = 4000; // địa chỉ mới cần vài giây để mạng Cloudflare nhận

/** Gọi 1 trang tĩnh (không cần mã) qua địa chỉ đường hầm; trả true nếu game trả lời. */
async function defaultProbe(url) {
  const r = await fetch(url + '/version.json', { cache: 'no-store', signal: AbortSignal.timeout(8000), headers: { 'User-Agent': 'caro-health' } });
  return r.ok;
}

class Remote extends EventEmitter {
  constructor({ dataDir, port, log }) {
    super();
    this.dir = dataDir;
    this.port = port;
    this.log = log || (() => {});
    this.tunnel = new Tunnel(dataDir);
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
    this.probe = defaultProbe; // (url) => Promise<boolean>; có thể thay khi kiểm tra tự động
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
    this.emit('status', this.status());
    return this.status();
  }

  disable() {
    this.cfg.enabled = false;
    this.save();
    applink.setRemoteToken('');
    for (const t of this.timers) clearInterval(t);
    this.timers = [];
    this.tunnel.stop();
    this.published = 0;
    return this.status();
  }

  /** Gọi thử đường hầm từ bên ngoài: nếu "đứng" (tiến trình còn nhưng không ai vào được) thì dựng lại. */
  async health(now = Date.now()) {
    const t = this.tunnel;
    if (!this.cfg.enabled || t.state !== 'online' || !t.url || now - this.onlineAt < HEALTH_GRACE_MS) return;
    let ok = false;
    try {
      ok = await this.probe(t.url);
    } catch (e) {
      ok = false;
    }
    if (t.url === '' || t.state !== 'online') return; // trong lúc chờ đã đổi trạng thái
    if (ok) {
      this.healthFails = 0;
      return;
    }
    this.healthFails++;
    if (this.healthFails >= HEALTH_FAILS) {
      this.healthFails = 0;
      t.restart('không ai gọi vào được');
    }
  }

  onTunnel(s) {
    if (s.state === 'online' && s.url && s.url !== this.lastUrl) {
      this.lastUrl = s.url;
      this.onlineAt = Date.now();
      this.healthFails = 0;
      setTimeout(() => this.publish().catch(() => {}), DELAY_AFTER_URL_MS);
    }
    this.emit('status', this.status());
  }

  async publish() {
    if (!this.cfg.enabled || !this.key || !this.tunnel.url) return;
    try {
      const text = await A.seal(this.key, { v: 1, t: Date.now(), url: this.tunnel.url });
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
    return {
      enabled: !!this.cfg.enabled,
      account: this.cfg.account,
      hasKeys: !!this.keys,
      tunnel: t.state,
      url: t.url,
      progress: t.progress,
      error: t.error || this.pubError,
      published: this.published,
      phones: this.phones(),
      server: this.cfg.server,
    };
  }
}

module.exports = { Remote };
