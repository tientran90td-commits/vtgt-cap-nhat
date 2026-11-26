'use strict';
/*
 * ĐỘNG CƠ: chạy game (src/server.js) như một tiến trình con, đọc nhật ký, tự mở lại khi cập nhật (mã 3) hoặc khi lỗi.
 * File này KHÔNG phụ thuộc Electron nên có thể thử riêng bằng Node thường.
 */
const fs = require('fs');
const path = require('path');
const cp = require('child_process');
const { EventEmitter } = require('events');

class Engine extends EventEmitter {
  constructor(root, execPath, electronMode) {
    super();
    this.root = root;
    this.execPath = execPath;
    this.electronMode = !!electronMode; // true: dùng chính Electron làm "node"
    this.proc = null;
    this.want = false;
    this.mode = 'tiktok'; // tiktok | tikfinity | demo
    this.logs = [];
    this.state = 'off'; // off | starting | on | crashed
    this.crashes = 0;
    this.timer = null;
    this.port = 3000;
  }

  log(line) {
    const s = String(line).replace(/\x1b\[[0-9;]*m/g, '').trimEnd();
    if (!s) return;
    this.logs.push(s);
    if (this.logs.length > 300) this.logs.shift();
    this.emit('log', s);
  }

  setState(s) {
    this.state = s;
    this.emit('state', this.info());
  }

  info() {
    return { state: this.state, mode: this.mode, port: this.port, tiktok: this.tiktokId() };
  }

  tiktokId() {
    try {
      return fs.readFileSync(path.join(this.root, 'ten-tiktok.txt'), 'utf8').trim().replace(/^@/, '');
    } catch (e) {
      return '';
    }
  }

  setTiktokId(id) {
    const v = String(id || '').trim().replace(/^@/, '').replace(/[^\w.]/g, '');
    fs.writeFileSync(path.join(this.root, 'ten-tiktok.txt'), v);
    return v;
  }

  start(mode) {
    if (mode) this.mode = mode;
    if (this.proc) return;
    this.want = true;
    this.spawn();
  }

  spawn() {
    const args = [path.join('src', 'server.js')];
    if (this.mode === 'demo') args.push('--demo');
    if (this.mode === 'tikfinity') args.push('--tikfinity');
    const env = { ...process.env };
    if (this.electronMode) env.ELECTRON_RUN_AS_NODE = '1';
    this.setState('starting');
    const p = cp.spawn(this.execPath, args, { cwd: this.root, env, windowsHide: true, stdio: ['ignore', 'pipe', 'pipe'] });
    this.proc = p;
    const feed = (buf) => {
      for (const line of String(buf).split(/\r?\n/)) {
        this.log(line);
        if (this.state === 'starting' && /localhost:\d+|Đang chạy|dang chay/i.test(line)) this.setState('on');
      }
    };
    p.stdout.on('data', feed);
    p.stderr.on('data', feed);
    p.on('error', (e) => this.log('Không chạy được game: ' + e.message));
    p.on('exit', (code) => {
      this.proc = null;
      if (!this.want) return this.setState('off');
      if (code === 3) {
        this.log('Vừa cập nhật xong, đang mở lại game…');
        this.crashes = 0;
        return setTimeout(() => this.want && this.spawn(), 1500);
      }
      this.crashes++;
      if (this.crashes >= 10) {
        this.want = false;
        this.log('Game lỗi liên tục, đã dừng. Xem nhật ký ở trên.');
        return this.setState('crashed');
      }
      this.log(`Game gặp lỗi (mã ${code}), tự mở lại sau 5 giây (lần ${this.crashes}/10).`);
      this.setState('starting');
      this.timer = setTimeout(() => this.want && this.spawn(), 5000);
    });
  }

  /** Người dùng chủ động tắt: xóa dữ liệu "ván đang dở" để lần mở sau bắt đầu mới (khác với cập nhật / game tự mở lại). */
  clearResume() {
    try {
      fs.unlinkSync(path.join(this.root, 'data', 'dang-choi.json'));
    } catch (err) {
      /* không có thì thôi */
    }
  }

  stop() {
    this.want = false;
    clearTimeout(this.timer);
    this.crashes = 0;
    if (this.proc) {
      const p = this.proc;
      p.once('exit', () => this.clearResume()); // đợi game tắt hẳn rồi mới xóa (tránh bị ghi lại)
      try {
        p.kill();
      } catch (e) {
        /* đã tắt */
      }
    } else {
      this.clearResume();
      this.setState('off');
    }
  }

  restart(mode) {
    if (mode) this.mode = mode;
    if (!this.proc) return this.start();
    const p = this.proc;
    p.once('exit', () => setTimeout(() => this.start(), 300));
    this.stop();
    this.want = true;
  }
}

module.exports = { Engine };
