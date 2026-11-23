/*
 * ÂM THANH HIỆU ỨNG (tạo trực tiếp bằng trình duyệt, không cần file âm thanh):
 * tiếng đặt quân, 4 quân liền, thắng, đếm ngược, tung đồng xu, cảm ơn quà, nhắc nhở.
 */
export class Sfx {
  constructor() {
    this.opt = { on: true, volume: 0.7 };
    this.forceMute = false;
    this.ctx = null;
    this.master = null;
  }

  setOptions(o) {
    if (!o) return;
    this.opt = { ...this.opt, ...o };
    if (this.master) this.master.gain.value = this.level();
  }

  level() {
    return this.opt.on && !this.forceMute ? Math.min(1, Math.max(0, this.opt.volume)) : 0;
  }

  /** Gọi khi người dùng bấm chuột/phím lần đầu (trình duyệt chỉ cho phát tiếng sau thao tác này). */
  unlock() {
    try {
      if (!this.ctx) {
        const AC = window.AudioContext || window.webkitAudioContext;
        if (!AC) return;
        this.ctx = new AC();
        this.master = this.ctx.createGain();
        this.master.gain.value = this.level();
        const comp = this.ctx.createDynamicsCompressor();
        this.master.connect(comp);
        comp.connect(this.ctx.destination);
      }
      if (this.ctx.state === 'suspended') this.ctx.resume();
    } catch (e) {
      /* không có âm thanh */
    }
  }

  needsGesture() {
    return !this.forceMute && this.opt.on && (!this.ctx || this.ctx.state !== 'running');
  }

  ready() {
    return this.ctx && this.ctx.state === 'running' && this.level() > 0;
  }

  // ---- khối dựng âm
  tone(freq, t0, dur, { type = 'sine', gain = 0.3, slide = 0, attack = 0.005 } = {}) {
    const c = this.ctx;
    const o = c.createOscillator();
    const g = c.createGain();
    o.type = type;
    o.frequency.setValueAtTime(freq, t0);
    if (slide) o.frequency.exponentialRampToValueAtTime(Math.max(30, freq + slide), t0 + dur);
    g.gain.setValueAtTime(0.0001, t0);
    g.gain.exponentialRampToValueAtTime(gain, t0 + attack);
    g.gain.exponentialRampToValueAtTime(0.0001, t0 + dur);
    o.connect(g);
    g.connect(this.master);
    o.start(t0);
    o.stop(t0 + dur + 0.05);
  }

  noise(t0, dur, { gain = 0.3, freq = 1800, q = 1 } = {}) {
    const c = this.ctx;
    const len = Math.max(1, Math.floor(c.sampleRate * dur));
    const buf = c.createBuffer(1, len, c.sampleRate);
    const d = buf.getChannelData(0);
    for (let i = 0; i < len; i++) d[i] = (Math.random() * 2 - 1) * (1 - i / len);
    const src = c.createBufferSource();
    src.buffer = buf;
    const f = c.createBiquadFilter();
    f.type = 'bandpass';
    f.frequency.value = freq;
    f.Q.value = q;
    const g = c.createGain();
    g.gain.setValueAtTime(gain, t0);
    g.gain.exponentialRampToValueAtTime(0.0001, t0 + dur);
    src.connect(f);
    f.connect(g);
    g.connect(this.master);
    src.start(t0);
  }

  // ---- các hiệu ứng
  place(mark) {
    if (!this.ready()) return;
    const t = this.ctx.currentTime;
    this.noise(t, 0.05, { gain: 0.5, freq: 2400, q: 1.2 }); // tiếng "cạch" của quân cờ
    this.tone(mark === 'X' ? 190 : 230, t, 0.12, { type: 'triangle', gain: 0.5, slide: -80 }); // tiếng vang gỗ
  }

  four() {
    if (!this.ready()) return;
    const t = this.ctx.currentTime;
    [660, 880, 1175].forEach((f, i) => this.tone(f, t + i * 0.09, 0.25, { type: 'triangle', gain: 0.28 }));
  }

  win() {
    if (!this.ready()) return;
    const t = this.ctx.currentTime;
    const notes = [523, 659, 784, 1047, 784, 1047, 1319];
    notes.forEach((f, i) => this.tone(f, t + i * 0.12, 0.35, { type: 'triangle', gain: 0.3 }));
    this.tone(262, t, 1.1, { type: 'sine', gain: 0.25 });
    for (let i = 0; i < 6; i++) this.noise(t + 0.3 + i * 0.28, 0.25, { gain: 0.18, freq: 3500 + i * 300, q: 0.8 }); // tiếng pháo
  }

  lose() {
    if (!this.ready()) return;
    const t = this.ctx.currentTime;
    [392, 349, 311].forEach((f, i) => this.tone(f, t + i * 0.18, 0.4, { type: 'sine', gain: 0.25 }));
  }

  tick(high) {
    if (!this.ready()) return;
    this.tone(high ? 1320 : 990, this.ctx.currentTime, 0.09, { type: 'square', gain: 0.1 });
  }

  /** Tiếng đồng hồ tích - tắc (luân phiên 2 âm). urgent = những giây cuối: to hơn. */
  clock(tock, urgent) {
    if (!this.ready()) return;
    const t = this.ctx.currentTime;
    const f = tock ? 640 : 880;
    this.tone(f, t, 0.045, { type: 'square', gain: urgent ? 0.16 : 0.1 });
    this.tone(f * 0.5, t, 0.07, { type: 'triangle', gain: urgent ? 0.14 : 0.08 });
  }

  coin() {
    if (!this.ready()) return;
    const t = this.ctx.currentTime;
    for (let i = 0; i < 9; i++) this.tone(2400 + (i % 3) * 300, t + i * 0.28, 0.12, { type: 'sine', gain: 0.1, slide: 600 });
    this.tone(1760, t + 2.9, 0.5, { type: 'triangle', gain: 0.2 });
  }

  chime() {
    if (!this.ready()) return;
    const t = this.ctx.currentTime;
    [988, 1319].forEach((f, i) => this.tone(f, t + i * 0.1, 0.4, { type: 'sine', gain: 0.22 }));
  }

  pop() {
    if (!this.ready()) return;
    this.tone(520, this.ctx.currentTime, 0.14, { type: 'sine', gain: 0.25, slide: 500 });
  }
}
