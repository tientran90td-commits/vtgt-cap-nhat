'use strict';
/*
 * ĐƯỜNG DỰ PHÒNG: zrok (mã nguồn mở, bản chạy sẵn tại zrok.io). Chỉ dùng khi bạn đã dán "mã zrok" và Cloudflare đang lỗi.
 * Cách làm: tải zrok2 từ GitHub (openziti/zrok) -> `zrok2 enable <mã>` (một lần) -> `zrok2 share public --headless <cổng>`
 * rồi đọc địa chỉ https://....share.zrok.io từ kết quả in ra. Giao diện giống Tunnel (tunnel.js) để remote.js dùng chung.
 * Lưu ý bảo mật: zrok chạy ngay trên máy này nên phải đi qua cổng chắn (tunnel-guard.js), không cho người lạ trông như "chính máy này".
 * Mã zrok lưu ở data/zrok.json (đừng gửi file này cho ai).
 */
const fs = require('fs');
const path = require('path');
const crypto = require('crypto');
const cp = require('child_process');
const { EventEmitter } = require('events');
const { Readable } = require('stream');
const { pipeline } = require('stream/promises');
const { listenGuard } = require('./tunnel-guard');

const URL_RE = /https:\/\/[a-z0-9-]+\.shares?\.zrok\.io/i;
const ANSI = /\x1b\[[0-9;?]*[ -/]*[@-~]/g;
const RELEASES = 'https://api.github.com/repos/openziti/zrok/releases/latest';
const sha = (s) => crypto.createHash('sha256').update(String(s)).digest('hex').slice(0, 16);

function pickAsset(assets, platform = process.platform, arch = process.arch) {
  const os = platform === 'win32' ? 'windows' : platform === 'darwin' ? 'darwin' : 'linux';
  const ar = arch === 'arm64' ? '(arm64|aarch64)' : '(amd64|x86_64|x64)';
  const re = new RegExp(`${os}.*${ar}|${ar}.*${os}`, 'i');
  return (assets || []).find((a) => /\.tar\.gz$/i.test(a.name) && re.test(a.name)) || null;
}

class Zrok extends EventEmitter {
  constructor(dataDir) {
    super();
    this.dir = dataDir;
    this.binDir = path.join(dataDir, 'bin');
    this.proc = null;
    this.guard = null;
    this.want = false;
    this.port = 0;
    this.url = '';
    this.state = 'off'; // off | downloading | starting | online | error
    this.error = '';
    this.progress = 0;
    this.backoff = 5000;
    this.timer = null;
    this.tail = [];
    this.launching = false;
  }

  file() {
    return path.join(this.dir, 'zrok.json');
  }
  read() {
    try {
      return JSON.parse(fs.readFileSync(this.file(), 'utf8'));
    } catch (e) {
      return {};
    }
  }
  write(o) {
    fs.mkdirSync(this.dir, { recursive: true });
    fs.writeFileSync(this.file(), JSON.stringify(o), { mode: 0o600 });
  }
  hasToken() {
    return !!this.read().token;
  }
  setToken(t) {
    t = String(t || '').trim();
    if (t && !/^[A-Za-z0-9]{6,40}$/.test(t)) throw new Error('Mã zrok không đúng dạng (chỉ gồm chữ và số, khoảng 12 ký tự). Chép đúng mã ở bước "Enable" trên trang zrok.');
    this.write(t ? { token: t } : {}); // đổi mã => phải enable lại
    return !!t;
  }

  set(state, extra = {}) {
    this.state = state;
    Object.assign(this, { error: '' }, extra);
    this.emit('status', this.info());
  }
  info() {
    return { state: this.state, url: this.url, error: this.error, progress: this.progress };
  }

  binName() {
    return process.platform === 'win32' ? 'zrok2.exe' : 'zrok2';
  }
  findBin(dir) {
    const want = new Set(['zrok2', 'zrok2.exe', 'zrok', 'zrok.exe']);
    const walk = (d, depth) => {
      let ents = [];
      try {
        ents = fs.readdirSync(d, { withFileTypes: true });
      } catch (e) {
        return '';
      }
      for (const e of ents) if (e.isFile() && want.has(e.name.toLowerCase())) return path.join(d, e.name);
      if (depth < 3) for (const e of ents) if (e.isDirectory()) {
        const r = walk(path.join(d, e.name), depth + 1);
        if (r) return r;
      }
      return '';
    };
    return walk(dir, 0);
  }

  async ensureBinary() {
    if (process.env.CARO_ZROK_BIN) return process.env.CARO_ZROK_BIN; // dùng khi thử nghiệm
    const have = this.findBin(path.join(this.binDir, 'zrok'));
    if (have) return have;
    this.progress = 0;
    this.set('downloading');
    const r = await fetch(RELEASES, { headers: { 'User-Agent': 'caro-live', Accept: 'application/vnd.github+json' }, signal: AbortSignal.timeout(30000) });
    if (!r.ok) throw new Error('không hỏi được GitHub bản zrok mới nhất (mã ' + r.status + ')');
    const rel = await r.json();
    const asset = pickAsset(rel.assets);
    if (!asset) throw new Error('không thấy bản zrok cho máy này trong ' + (rel.tag_name || 'GitHub') + ': ' + (rel.assets || []).map((a) => a.name).slice(0, 8).join(', '));
    const outDir = path.join(this.binDir, 'zrok');
    fs.rmSync(outDir, { recursive: true, force: true });
    fs.mkdirSync(outDir, { recursive: true });
    const tgz = path.join(this.binDir, 'zrok-download.tar.gz');
    const d = await fetch(asset.browser_download_url, { redirect: 'follow', signal: AbortSignal.timeout(10 * 60 * 1000) });
    if (!d.ok || !d.body) throw new Error('không tải được zrok (mã ' + d.status + ')');
    const total = Number(d.headers.get('content-length')) || asset.size || 0;
    let got = 0;
    const src = Readable.fromWeb(d.body);
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
    await pipeline(src, fs.createWriteStream(tgz));
    await new Promise((resolve, reject) => cp.execFile('tar', ['-xzf', tgz, '-C', outDir], { windowsHide: true, timeout: 120000 }, (e, so, se) => (e ? reject(new Error('không giải nén được zrok: ' + String(se || e.message).slice(0, 100))) : resolve())));
    fs.rmSync(tgz, { force: true });
    const bin = this.findBin(outDir);
    if (!bin) throw new Error('giải nén xong nhưng không thấy ' + this.binName());
    if (process.platform !== 'win32') fs.chmodSync(bin, 0o755);
    return bin;
  }

  run(bin, args, ms) {
    return new Promise((resolve) => {
      let out = '';
      const p = cp.spawn(bin, args, { windowsHide: true });
      const add = (c) => (out += c.toString());
      p.stdout.on('data', add);
      p.stderr.on('data', add);
      const t = setTimeout(() => p.kill(), ms);
      p.on('error', (e) => {
        clearTimeout(t);
        resolve({ code: -1, out: e.message });
      });
      p.on('exit', (code) => {
        clearTimeout(t);
        resolve({ code, out: out.replace(ANSI, '') });
      });
    });
  }

  async ensureEnabled(bin) {
    const st = this.read();
    if (!st.token) throw new Error('chưa có mã zrok');
    if (st.enabledFor === sha(st.token)) return;
    this.set('starting');
    const r = await this.run(bin, ['enable', st.token], 90000);
    const ok = r.code === 0 || /already|exists/i.test(r.out);
    if (!ok) {
      const line = r.out.split('\n').map((l) => l.trim()).filter(Boolean).pop() || '';
      throw new Error('zrok enable lỗi' + (line ? ': ' + line.slice(0, 120) : ' (mã ' + r.code + ')'));
    }
    this.write({ ...st, enabledFor: sha(st.token) });
    this.emit('log', 'zrok: đã bật môi trường zrok trên máy này.');
  }

  start(port) {
    this.want = true;
    this.port = port;
    if (this.proc || this.timer || this.launching) return;
    this.launch();
  }

  async launch() {
    this.timer = null;
    if (!this.want || this.proc || this.launching || !this.hasToken()) return;
    this.launching = true;
    try {
      const bin = await this.ensureBinary();
      if (!this.want) return void (this.launching = false);
      await this.ensureEnabled(bin);
      if (!this.want) return void (this.launching = false);
      this.url = '';
      this.tail = [];
      this.set('starting');
      this.guard = await listenGuard(this.port);
      const p = cp.spawn(bin, ['share', 'public', '--headless', `http://127.0.0.1:${this.guard.port}`], { windowsHide: true });
      this.proc = p;
      this.launching = false;
      const take = (chunk) => {
        for (const raw of chunk.toString().replace(ANSI, '').split(/\r?\n/)) {
          const l = raw.trim();
          if (!l) continue;
          this.tail.push(l);
          if (this.tail.length > 8) this.tail.shift();
          const m = !this.url && l.match(URL_RE);
          if (m) {
            this.url = m[0];
            this.backoff = 5000;
            this.emit('log', 'zrok: đã có địa chỉ ' + this.url);
            this.set('online', { url: this.url });
          }
        }
      };
      p.stdout.on('data', take);
      p.stderr.on('data', take);
      const giveUp = setTimeout(() => {
        if (this.proc === p && !this.url) {
          this.tail.push('quá 60 giây vẫn chưa có địa chỉ');
          try {
            p.kill();
          } catch (e) {
            /* đã tắt */
          }
        }
      }, 60000);
      p.on('error', (e) => {
        clearTimeout(giveUp);
        this.cleanup();
        this.fail(e.message);
      });
      p.on('exit', (code) => {
        clearTimeout(giveUp);
        this.cleanup();
        if (!this.want) return this.set('off');
        const why = [...this.tail].reverse().find((l) => /error|fail|denied|unauthor|not enabled|invalid|limit|quota|refused|timeout/i.test(l)) || this.tail[this.tail.length - 1] || '';
        if (/not enabled|unauthor|invalid token|environment/i.test(why)) this.write({ token: this.read().token }); // bắt enable lại ở lần sau
        this.emit('log', `zrok dừng (mã ${code})${why ? ': ' + why.slice(0, 160) : ''}`);
        this.fail(`zrok dừng (mã ${code})${why ? ': ' + why.slice(0, 90) : ''}`);
      });
    } catch (e) {
      this.launching = false;
      this.cleanup();
      this.fail(e.message);
    }
  }

  cleanup() {
    this.proc = null;
    this.url = '';
    if (this.guard) {
      try {
        this.guard.server.close();
      } catch (e) {
        /* đã đóng */
      }
      this.guard = null;
    }
  }

  fail(msg) {
    if (!this.want) return;
    this.set('error', { error: String(msg).slice(0, 160), url: '' });
    clearTimeout(this.timer);
    this.timer = setTimeout(() => this.launch(), this.backoff);
    this.backoff = Math.min(this.backoff * 2, 120000);
  }

  /** true = tiến trình zrok còn chạy và đã có địa chỉ; null = chưa biết (không làm gì). */
  async ready() {
    return this.proc && this.url ? true : null;
  }

  restart(why) {
    if (!this.want || !this.proc) return;
    this.emit('log', 'zrok: dựng lại' + (why ? ' (' + why + ')' : ''));
    try {
      this.proc.kill();
    } catch (e) {
      /* đã tắt */
    }
  }

  stop() {
    this.want = false;
    clearTimeout(this.timer);
    this.timer = null;
    if (this.proc) {
      try {
        this.proc.kill();
      } catch (e) {
        /* đã tắt */
      }
    }
    this.cleanup();
    this.set('off');
  }
}

module.exports = { Zrok, URL_RE, pickAsset };
