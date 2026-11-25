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

const URL_RE = /https:\/\/[a-z0-9-]+\.trycloudflare\.com/i;
const BASE = 'https://github.com/cloudflare/cloudflared/releases/latest/download/';

function assetName() {
  const arch = os.arch();
  if (process.platform === 'win32') return 'cloudflared-windows-amd64.exe';
  if (process.platform === 'linux' && arch === 'x64') return 'cloudflared-linux-amd64';
  if (process.platform === 'linux' && arch === 'arm64') return 'cloudflared-linux-arm64';
  throw new Error('Hệ điều hành này chưa hỗ trợ đường hầm tự động');
}

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
    this.launch();
  }

  async launch() {
    if (!this.want || this.proc) return;
    try {
      const bin = await this.ensureBinary();
      if (!this.want) return;
      this.url = '';
      this.set('starting');
      const p = cp.spawn(bin, ['tunnel', '--no-autoupdate', '--url', `http://127.0.0.1:${this.port}`], { windowsHide: true, stdio: ['ignore', 'pipe', 'pipe'] });
      this.proc = p;
      let ready = false;
      const onData = (buf) => {
        const m = URL_RE.exec(String(buf));
        if (m && !ready) {
          ready = true;
          this.backoff = 3000;
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
        this.fail(`cloudflared dừng (mã ${code})`);
      });
    } catch (e) {
      this.proc = null;
      this.fail(e.message);
    }
  }

  fail(msg) {
    if (!this.want) return;
    this.set('error', { error: String(msg).slice(0, 160), url: '' });
    clearTimeout(this.timer);
    this.timer = setTimeout(() => this.launch(), this.backoff);
    this.backoff = Math.min(this.backoff * 2, 60000);
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
