/*
 * NHẠC NỀN.
 *  - Nếu có file nhạc trong thư mục  public/music  (mp3, ogg, wav, m4a): phát ngẫu nhiên các bài đó.
 *  - Nếu không có: tự tạo nhạc nền nhẹ nhàng (đàn pad + gảy nốt) ngay trong trình duyệt - không dính bản quyền.
 *  - Tự hạ nhỏ tiếng khi điều phối viên / trọng tài đang nói.
 */
const mtof = (m) => 440 * Math.pow(2, (m - 69) / 12);
const CHORDS = [
  [48, 55, 59, 64], // Cmaj7
  [45, 52, 55, 60], // Am7
  [41, 48, 52, 57], // Fmaj7
  [43, 50, 55, 59], // G6
];
const SCALE = [0, 2, 4, 7, 9]; // ngũ cung - nốt nào cũng hợp

export class Music {
  constructor() {
    this.opt = { on: true, volume: 0.3 };
    this.forceMute = false;
    this.ducked = false;
    this.ctx = null;
    this.master = null;
    this.mode = null; // 'synth' | 'files'
    this.files = [];
    this.audio = null;
    this.order = [];
    this.timer = null;
    this.cur = 0;
    this.step = 0;
    this.nextT = 0;
    this.started = false;
  }

  setOptions(o) {
    if (o) this.opt = { ...this.opt, ...o };
    this.apply(true);
  }

  duck(b) {
    this.ducked = !!b;
  }

  target() {
    return this.opt.on && !this.forceMute ? Math.min(1, Math.max(0, this.opt.volume)) * (this.ducked ? 0.35 : 1) : 0;
  }

  apply(now) {
    const t = this.target();
    this.cur = now ? t : this.cur + (t - this.cur) * 0.2;
    if (this.master) this.master.gain.value = this.cur * 0.9;
    if (this.audio) this.audio.volume = Math.min(1, this.cur);
  }

  needsGesture() {
    if (!this.opt.on || this.forceMute) return false;
    if (this.mode === 'files') return !!this.audio && this.audio.paused && this.blocked;
    return !this.ctx || this.ctx.state !== 'running';
  }

  /** Gọi khi người dùng bấm chuột/phím (trình duyệt chỉ cho phát tiếng sau thao tác này). */
  unlock() {
    if (!this.started) {
      this.started = true;
      this.start();
    } else {
      this.resume();
    }
  }

  resume() {
    try {
      if (this.ctx && this.ctx.state === 'suspended') this.ctx.resume();
      if (this.audio && this.audio.paused) this.audio.play().then(() => (this.blocked = false)).catch(() => (this.blocked = true));
    } catch (e) {
      /* bỏ qua */
    }
  }

  async start() {
    try {
      const r = await fetch('/music-list', { cache: 'no-store' });
      this.files = r.ok ? await r.json() : [];
    } catch (e) {
      this.files = [];
    }
    if (this.files.length) this.startFiles();
    else this.startSynth();
    if (!this.timer) this.timer = setInterval(() => this.apply(false), 100);
  }

  // ---------------------------------------------------------------- phát file nhạc của bạn
  startFiles() {
    this.mode = 'files';
    this.audio = new Audio();
    this.audio.preload = 'auto';
    this.audio.onended = () => this.nextTrack();
    this.audio.onerror = () => setTimeout(() => this.nextTrack(), 500);
    this.nextTrack();
  }

  nextTrack() {
    if (!this.order.length) this.order = [...this.files].sort(() => Math.random() - 0.5);
    const f = this.order.pop();
    this.audio.src = '/music/' + encodeURIComponent(f);
    this.apply(true);
    this.audio.play().then(() => (this.blocked = false)).catch(() => (this.blocked = true));
  }

  // ---------------------------------------------------------------- tự tạo nhạc nền
  startSynth() {
    const AC = window.AudioContext || window.webkitAudioContext;
    if (!AC) return;
    this.mode = 'synth';
    const c = (this.ctx = new AC());
    this.master = c.createGain();
    this.master.gain.value = 0;
    // vang nhẹ (echo)
    const delay = c.createDelay(1);
    delay.delayTime.value = 0.46;
    const fb = c.createGain();
    fb.gain.value = 0.38;
    const wet = c.createGain();
    wet.gain.value = 0.45;
    delay.connect(fb);
    fb.connect(delay);
    delay.connect(wet);
    this.bus = c.createGain();
    this.bus.connect(this.master);
    this.bus.connect(delay);
    wet.connect(this.master);
    const lp = c.createBiquadFilter();
    lp.type = 'lowpass';
    lp.frequency.value = 2600;
    this.master.connect(lp);
    lp.connect(c.destination);
    if (c.state === 'suspended') c.resume();
    this.beat = 60 / 76;
    this.nextT = c.currentTime + 0.2;
    this.step = 0;
    this.apply(true);
    this.sched = setInterval(() => this.schedule(), 120);
  }

  schedule() {
    const c = this.ctx;
    if (!c || c.state !== 'running') {
      this.nextT = Math.max(this.nextT, c ? c.currentTime + 0.1 : 0);
      return;
    }
    while (this.nextT < c.currentTime + 0.6) {
      this.playStep(this.step, this.nextT);
      this.step++;
      this.nextT += this.beat / 2; // nốt móc đơn
    }
  }

  voice(freq, t, dur, { type = 'sine', gain = 0.1, attack = 0.01, release = 0.3 } = {}) {
    const c = this.ctx;
    const o = c.createOscillator();
    const g = c.createGain();
    o.type = type;
    o.frequency.value = freq;
    g.gain.setValueAtTime(0.0001, t);
    g.gain.linearRampToValueAtTime(gain, t + attack);
    g.gain.setTargetAtTime(0.0001, t + dur, release);
    o.connect(g);
    g.connect(this.bus);
    o.start(t);
    o.stop(t + dur + release * 5);
  }

  playStep(step, t) {
    const perChord = 16; // 16 nốt móc đơn = 8 phách mỗi hợp âm
    const chord = CHORDS[Math.floor(step / perChord) % CHORDS.length];
    const s = step % perChord;
    if (s === 0) {
      // đàn pad: ngân dài, êm
      for (const n of chord) {
        this.voice(mtof(n), t, perChord * (this.beat / 2) - 0.2, { type: 'triangle', gain: 0.05, attack: 1.4, release: 0.9 });
      }
      this.voice(mtof(chord[0] - 12), t, 3.4, { type: 'sine', gain: 0.1, attack: 0.05, release: 0.5 }); // bass
    }
    if (s === 8) this.voice(mtof(chord[0] - 12), t, 2.2, { type: 'sine', gain: 0.07, attack: 0.05, release: 0.5 });
    // gảy nốt ngẫu nhiên theo ngũ cung
    if (s % 2 === 0 ? Math.random() < 0.7 : Math.random() < 0.25) {
      const root = chord[0] + 12;
      const deg = SCALE[Math.floor(Math.random() * SCALE.length)] + (Math.random() < 0.35 ? 12 : 0);
      this.voice(mtof(root + deg), t, 0.12, { type: 'sine', gain: 0.07, attack: 0.008, release: 0.45 });
    }
  }
}
