'use strict';
/*
 * ĐƯỜNG HẦM INTERNET (Cloudflare "quick tunnel"): cho điện thoại ở WiFi / 4G khác nối vào game trên máy này
 * mà không cần mở cổng router hay cài thêm gì. Dùng chương trình cloudflared (tự tải về lần đầu, ~55 MB).
 * Mỗi lần chạy sẽ có 1 địa chỉ https://xxxx.trycloudflare.com mới; địa chỉ này được gửi MÃ HÓA cho điện thoại (xem remote.js).
 * Lưu ý: Cloudflare ghi rõ quick tunnel không cam kết thời gian hoạt động, nên nếu rớt mạng module tự dựng lại đường hầm.
 */
const fs = require('fs');
const os = require('os');
const path = require('path');
const cp = require('child_process');
const { EventEmitter } = require('events');
const { Readable } = require('stream');
const { pipeline } = require('stream/promises');
const net = require('net');

const URL_RE = /https:\/\/[a-z0-9-]+\.trycloudflare\.com/i;
const BASE = 'https://github.com/cloudflare/cloudflared/releases/latest/download/';

function assetName() {
  const arch = os.arch();
  if (process.platform === 'win32') return 'cloudflared-windows-amd64.exe';
  if (process.platform === 'linux' && arch === 'x64') return 'cloudflared-linux-amd64';
  if (process.platform === 'linux' && arch === 'arm64') return 'cloudflared-linux-arm64';
  throw new Error('Hệ điều hành này chưa hỗ trợ đường hầm tự động');
}

function freePort() {
  return new Promise((resolve, reject) => {
    const srv = net.createServer();
    srv.on('error', reject);
    srv.listen(0, '127.0.0.1', () => {
      const { port } = srv.address();
      srv.close(() => resolve(port));
    });
  });
}

const PROTOCOLS = ['http2', 'auto', 'quic'];

class Tunnel extends EventEmitter {
  constructor(dataDir) {
    super();
    this.binDir = path.join(dataDir, 'bin');
    this.proc = null;
    this.want = false;
    this.url = '';
    this.state = 'off'; // off | downloading | starting | online | error
    this.error = '';
    this.progress = 0;
    this.backoff = 3000;
    this.timer = null;
    this.attempt = 0; // số lần khởi động liên tiếp chưa thành công: mỗi lần đổi giao thức kết nối (http2 -> tự động -> quic)
    this.metricsPort = 0;
    this.tail = [];
    this.limited = 0; // số lần liên tiếp bị Cloudflare từ chối vì tạo quá nhiều đường truyền (lỗi 429)
    this.coolUntil = 0;
  }

  set(state, extra = {}) {
    this.state = state;
    Object.assign(this, { error: '' }, extra);
    this.emit('status', this.info());
  }

  info() {
    return { state: this.state, url: this.url, error: this.error, progress: this.progress };
  }

  binPath() {
    if (process.env.CARO_CLOUDFLARED_BIN) return process.env.CARO_CLOUDFLARED_BIN; // dùng khi thử nghiệm
    return path.join(this.binDir, assetName());
  }

  async ensureBinary() {
    const file = this.binPath();
    if (process.env.CARO_CLOUDFLARED_BIN) return file;
    try {
      if (fs.statSync(file).size > 10 * 1024 * 1024) return file;
    } catch (e) {
      /* chưa có */
    }
    fs.mkdirSync(this.binDir, { recursive: true });
    this.progress = 0;
    this.set('downloading');
    const r = await fetch(BASE + assetName(), { redirect: 'follow', signal: AbortSignal.timeout(10 * 60 * 1000) });
    if (!r.ok || !r.body) throw new Error('không tải được cloudflared (mã ' + r.status + ')');
    const total = Number(r.headers.get('content-length')) || 0;
    let got = 0;
    const tmp = file + '.tmp';
    const src = Readable.fromWeb(r.body);
    src.on('data', (c) => {
      got += c.length;
      if (total) {
        const pct = Math.floor((got / total) * 100);
        if (pct !== this.progress) {
          this.progress = pct;
          this.emit('status', this.info());
        }
      }
    });
    await pipeline(src, fs.createWriteStream(tmp));
    if (fs.statSync(tmp).size < 10 * 1024 * 1024) throw new Error('file cloudflared tải về bị thiếu');
    fs.renameSync(tmp, file);
    if (process.platform !== 'win32') fs.chmodSync(file, 0o755);
    return file;
  }

  start(port) {
    this.want = true;
    this.port = port;
    if (Date.now() < this.coolUntil) return; // đang chờ Cloudflare mở lại: bấm thêm chỉ làm bị chặn lâu hơn
    this.launch();
  }

  async launch() {
    if (!this.want || this.proc) return;
    try {
      const bin = await this.ensureBinary();
      if (!this.want) return;
      this.url = '';
      this.set('starting');
      const proto = PROTOCOLS[this.attempt % PROTOCOLS.length]; // TCP (http2) thường ổn định hơn; nếu hỏng thì thử cách khác
      try {
        this.metricsPort = await freePort();
      } catch (e) {
        this.metricsPort = 0;
      }
      const args = ['tunnel', '--no-autoupdate'];
      if (proto !== 'auto') args.push('--protocol', proto);
      if (this.metricsPort) args.push('--metrics', `127.0.0.1:${this.metricsPort}`);
      args.push('--url', `http://127.0.0.1:${this.port}`);
      this.tail = [];
      const p = cp.spawn(bin, args, { windowsHide: true, stdio: ['ignore', 'pipe', 'pipe'] });
      this.proc = p;
      let ready = false;
      const onData = (buf) => {
        for (const line of String(buf).split(/\r?\n/)) {
          const l = line.replace(/\x1b\[[0-9;]*m/g, '').trim();
          if (l) {
            this.tail.push(l);
            if (this.tail.length > 8) this.tail.shift();
          }
        }
        const m = URL_RE.exec(String(buf));
        if (m && !ready) {
          ready = true;
          this.attempt = 0;
          this.backoff = 3000;
          this.limited = 0;
          this.coolUntil = 0;
          this.url = m[0];
          this.set('online', { url: m[0] });
        }
      };
      p.stdout.on('data', onData);
      p.stderr.on('data', onData);
      p.on('error', (e) => {
        this.proc = null;
        this.fail(e.message);
      });
      p.on('exit', (code) => {
        this.proc = null;
        this.url = '';
        if (!this.want) return this.set('off');
        const why = [...this.tail].reverse().find((l) => /ERR|error|fail|refused|timeout|429|rate/i.test(l)) || this.tail[this.tail.length - 1] || '';
        if (!ready) this.attempt++; // chưa lên được lần nào: lần sau đổi giao thức
        this.emit('log', `cloudflared dừng (mã ${code})${why ? ': ' + why.slice(0, 160) : ''}`);
        this.fail(`cloudflared dừng (mã ${code})${why ? ': ' + why.slice(0, 90) : ''}`);
      });
    } catch (e) {
      this.proc = null;
      this.fail(e.message);
    }
  }

  fail(msg) {
    if (!this.want) return;
    clearTimeout(this.timer);
    if (/\b429\b|too many requests|rate.?limit/i.test(String(msg))) {
      // Cloudflare giới hạn số lần tạo đường truyền miễn phí theo mạng nhà bạn. Thử dồn dập chỉ bị chặn lâu hơn -> chờ hẳn vài phút.
      const mins = [3, 6, 10, 15][Math.min(this.limited, 3)];
      this.limited++;
      this.coolUntil = Date.now() + mins * 60000;
      this.set('error', { error: `Cloudflare đang tạm giới hạn việc tạo đường truyền (lỗi 429: thử quá nhiều lần). Tự thử lại sau ${mins} phút, bạn cứ để yên, đừng bấm lại.`, url: '' });
      this.emit('log', `Cloudflare báo 429 (giới hạn tạo đường truyền). Chờ ${mins} phút rồi tự thử lại.`);
      this.timer = setTimeout(() => this.launch(), mins * 60000);
      return;
    }
    this.limited = 0;
    this.set('error', { error: String(msg).slice(0, 160), url: '' });
    this.timer = setTimeout(() => this.launch(), this.backoff);
    this.backoff = Math.min(this.backoff * 2, 60000);
  }

  /**
   * Hỏi chính cloudflared (cổng nội bộ trên máy này) xem còn kết nối tới Cloudflare không.
   * true = còn; false = KHÔNG còn kết nối nào; null = không hỏi được (không kết luận gì, đừng dựng lại).
   */
  async ready() {
    if (!this.metricsPort || !this.proc) return null;
    try {
      const r = await fetch(`http://127.0.0.1:${this.metricsPort}/ready`, { signal: AbortSignal.timeout(4000) });
      if (r.status === 200) return true;
      if (r.status === 503) return false;
      return null;
    } catch (e) {
      return null;
    }
  }

  /** Ép dựng lại đường hầm (khi phát hiện nó đã "chết" dù tiến trình cloudflared còn chạy). Địa chỉ mới sẽ được báo lại cho điện thoại. */
  restart(why) {
    if (!this.want || !this.proc) return;
    this.emit('log', 'Đường truyền Internet bị đứng' + (why ? ' (' + why + ')' : '') + ', đang dựng lại…');
    this.backoff = 3000;
    try {
      this.proc.kill();
    } catch (e) {
      /* đã tắt */
    }
  }

  stop() {
    this.want = false;
    clearTimeout(this.timer);
    this.url = '';
    if (this.proc) {
      try {
        this.proc.kill();
      } catch (e) {
        /* đã tắt */
      }
      this.proc = null;
    }
    this.set('off');
  }
}

module.exports = { Tunnel, URL_RE };
