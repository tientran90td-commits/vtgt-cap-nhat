/*
 * HIỆU ỨNG TRÊN MÀN HÌNH: pháo hoa + hoa giấy khi có người thắng, biểu ngữ "4 QUÂN LIỀN", khung nhắc follow/chia sẻ.
 */
export class Fx {
  constructor(canvas, bannerEl, promoEl) {
    this.cv = canvas;
    this.ctx = canvas.getContext('2d');
    this.banner = bannerEl;
    this.promo = promoEl;
    this.parts = [];
    this.running = false;
    this.bannerTimer = null;
    this.promoTimer = null;
    this.burstTimers = [];
  }

  resize() {
    const r = this.cv.getBoundingClientRect();
    const dpr = Math.min(2, window.devicePixelRatio || 1);
    const w = Math.max(1, Math.round(r.width * dpr));
    const h = Math.max(1, Math.round(r.height * dpr));
    if (this.cv.width !== w || this.cv.height !== h) {
      this.cv.width = w;
      this.cv.height = h;
    }
    this.dpr = dpr;
  }

  // ---- biểu ngữ ngắn (4 quân liền, ...)
  showBanner(text, kind = '') {
    const b = this.banner;
    b.textContent = text;
    b.className = 'show ' + kind;
    clearTimeout(this.bannerTimer);
    this.bannerTimer = setTimeout(() => (b.className = 'hidden'), 2100);
  }

  // ---- khung nhắc follow / chia sẻ
  showPromo(text, kind) {
    const p = this.promo;
    p.querySelector('i').textContent = kind === 'share' ? '🔁' : kind === 'hint' ? '💬' : '➕';
    p.querySelector('span').textContent = text;
    p.className = 'show ' + kind;
    clearTimeout(this.promoTimer);
    this.promoTimer = setTimeout(() => (p.className = 'hidden'), 10000);
  }

  hidePromo() {
    clearTimeout(this.promoTimer);
    this.promo.className = 'hidden';
  }

  // ---- pháo hoa
  fireworks(ms = 6000) {
    this.stopBursts();
    this.resize();
    const n = Math.floor(ms / 520);
    for (let i = 0; i < n; i++) {
      this.burstTimers.push(setTimeout(() => this.burst(), i * 520 + Math.random() * 200));
    }
    for (let i = 0; i < 3; i++) this.burstTimers.push(setTimeout(() => this.confetti(), i * 900));
    this.start();
  }

  stopBursts() {
    for (const t of this.burstTimers) clearTimeout(t);
    this.burstTimers = [];
  }

  clear() {
    this.stopBursts();
    this.parts = [];
    this.ctx.clearRect(0, 0, this.cv.width, this.cv.height);
  }

  burst() {
    const W = this.cv.width;
    const H = this.cv.height;
    const x = W * (0.15 + Math.random() * 0.7);
    const y = H * (0.12 + Math.random() * 0.38);
    const hue = Math.floor(Math.random() * 360);
    const n = 46;
    const sp = (0.28 + Math.random() * 0.22) * Math.min(W, H) * 0.012;
    for (let i = 0; i < n; i++) {
      const a = (i / n) * Math.PI * 2 + Math.random() * 0.1;
      const v = sp * (0.6 + Math.random() * 0.6);
      this.parts.push({ x, y, vx: Math.cos(a) * v, vy: Math.sin(a) * v, life: 1, decay: 0.012 + Math.random() * 0.008, g: 0.05, hue: hue + Math.random() * 40, size: 2.2, kind: 'spark' });
    }
    this.start();
  }

  confetti() {
    const W = this.cv.width;
    for (let i = 0; i < 40; i++) {
      this.parts.push({ x: Math.random() * W, y: -10, vx: (Math.random() - 0.5) * 2, vy: 2 + Math.random() * 3, life: 1, decay: 0.004, g: 0.02, hue: Math.random() * 360, size: 5 + Math.random() * 5, rot: Math.random() * 6, vr: (Math.random() - 0.5) * 0.3, kind: 'paper' });
    }
    this.start();
  }

  start() {
    if (this.running) return;
    this.running = true;
    const loop = () => {
      const c = this.ctx;
      c.clearRect(0, 0, this.cv.width, this.cv.height);
      const k = this.dpr || 1;
      for (const p of this.parts) {
        p.vy += p.g * k * 0.5;
        p.x += p.vx * k * 0.5;
        p.y += p.vy * k * 0.5;
        p.life -= p.decay;
        if (p.kind === 'spark') p.vx *= 0.985;
        c.globalAlpha = Math.max(0, Math.min(1, p.life * 1.4));
        c.fillStyle = `hsl(${p.hue},95%,62%)`;
        if (p.kind === 'paper') {
          p.rot += p.vr;
          c.save();
          c.translate(p.x, p.y);
          c.rotate(p.rot);
          c.fillRect(-p.size / 2, -p.size / 4, p.size * k * 0.7, p.size * k * 0.35);
          c.restore();
        } else {
          c.beginPath();
          c.arc(p.x, p.y, p.size * k * Math.max(0.4, p.life), 0, Math.PI * 2);
          c.fill();
        }
      }
      c.globalAlpha = 1;
      this.parts = this.parts.filter((p) => p.life > 0 && p.y < this.cv.height + 30);
      if (this.parts.length || this.burstTimers.length) requestAnimationFrame(loop);
      else {
        this.running = false;
        c.clearRect(0, 0, this.cv.width, this.cv.height);
      }
    };
    requestAnimationFrame(loop);
  }
}
