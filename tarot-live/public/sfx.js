/* ÂM THANH NHỎ (tạo bằng trình duyệt, không cần file): xáo bài, lật bài, tiếng chuông nhẹ. */
export class Sfx {
  constructor() {
    this.ctx = null;
    this.on = true;
    this.vol = 0.5;
  }
  unlock() {
    try {
      if (!this.ctx) this.ctx = new (window.AudioContext || window.webkitAudioContext)();
      if (this.ctx.state === 'suspended') this.ctx.resume();
    } catch (e) { /* không có âm thanh */ }
  }
  noise(dur, freq, gain = 0.3, t0 = 0) {
    if (!this.ctx || !this.on) return;
    const c = this.ctx;
    const n = Math.floor(c.sampleRate * dur);
    const buf = c.createBuffer(1, n, c.sampleRate);
    const d = buf.getChannelData(0);
    for (let i = 0; i < n; i++) d[i] = (Math.random() * 2 - 1) * (1 - i / n);
    const src = c.createBufferSource();
    src.buffer = buf;
    const f = c.createBiquadFilter();
    f.type = 'bandpass';
    f.frequency.value = freq;
    const g = c.createGain();
    g.gain.value = gain * this.vol;
    src.connect(f).connect(g).connect(c.destination);
    src.start(c.currentTime + t0);
  }
  bell(freq, dur = 1.4, gain = 0.16, t0 = 0) {
    if (!this.ctx || !this.on) return;
    const c = this.ctx;
    const o = c.createOscillator();
    const g = c.createGain();
    o.type = 'sine';
    o.frequency.value = freq;
    const t = c.currentTime + t0;
    g.gain.setValueAtTime(0.0001, t);
    g.gain.exponentialRampToValueAtTime(gain * this.vol, t + 0.02);
    g.gain.exponentialRampToValueAtTime(0.0001, t + dur);
    o.connect(g).connect(c.destination);
    o.start(t);
    o.stop(t + dur + 0.05);
  }
  shuffle() { for (let i = 0; i < 7; i++) this.noise(0.09, 2600 + (i % 3) * 700, 0.25, i * 0.22); }
  flip() { this.noise(0.28, 1800, 0.35); this.bell(880, 1.6, 0.12, 0.25); this.bell(1320, 1.2, 0.07, 0.3); }
  done() { this.bell(660, 1.8, 0.1); this.bell(990, 1.8, 0.08, 0.18); }
}
