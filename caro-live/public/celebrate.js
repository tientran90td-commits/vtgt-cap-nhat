/*
 * ĂN MỪNG KHI CÓ NGƯỜI THẮNG (module riêng).
 * Khi 1 người thắng ván: phát NGAY tiếng nhạc của video, đợi đủ SHOW_AT giây rồi mới hiện hình video thế chỗ 2 nhân vật 3D.
 * Hết video: ẩn video, 2 nhân vật quay lại như cũ, game tiếp tục các bước như cũ.
 * Muốn đổi video: thay file public/media/celebrate.mp4 (nên là H.264 + AAC để chạy được trên mọi trình duyệt/OBS).
 * Muốn đổi số giây chờ hiện hình: sửa SHOW_AT ngay bên dưới.
 */
const SHOW_AT = 4; // giây (tính theo thời gian của video): có tiếng trước, tới giây này mới hiện hình

export class Celebrate {
  constructor(video, wrap, threeCanvas) {
    this.v = video;
    this.wrap = wrap;
    this.three = threeCanvas;
    this.running = false;
    this.shown = false;
    this.v.preload = 'auto';
    this.v.playsInline = true;
    this.v.addEventListener('ended', () => this.stop());
    this.v.addEventListener('error', () => this.stop());
    window.addEventListener('resize', () => this.layout());
  }

  active() {
    return this.running;
  }

  start() {
    this.stop();
    const v = this.v;
    this.running = true;
    this.shown = false;
    try { v.currentTime = 0; } catch (e) {}
    v.muted = false;
    v.volume = 0.9;
    const p = v.play();
    if (p && p.catch) {
      p.catch((err) => {
        if (!this.running || (err && err.name === 'AbortError')) return; // bị dừng chủ động, không phải bị chặn tiếng
        // trình duyệt chặn tiếng khi chưa ai bấm vào trang: vẫn phát (không tiếng) để hình hiện đúng lúc
        v.muted = true;
        const q = v.play();
        if (q && q.catch) q.catch(() => this.stop());
      });
    }
  }

  stop() {
    this.running = false;
    this.shown = false;
    const v = this.v;
    try { v.pause(); } catch (e) {}
    v.classList.remove('show');
    if (this.three) this.three.style.visibility = '';
  }

  layout() {
    const w = this.wrap.clientWidth, h = this.wrap.clientHeight;
    const size = Math.floor(Math.min(w, h) * 0.97);
    this.v.style.width = size + 'px';
    this.v.style.height = size + 'px';
  }

  /** Gọi mỗi khung hình. */
  tick() {
    if (this.running && (this.v.ended || (isFinite(this.v.duration) && this.v.currentTime >= this.v.duration - 0.04))) { this.stop(); return; } // hết video -> về như cũ
    if (!this.running || this.shown) return;
    if (this.v.currentTime >= SHOW_AT && !this.v.paused) {
      this.shown = true;
      this.layout();
      this.v.classList.add('show');
      if (this.three) this.three.style.visibility = 'hidden'; // 2 nhân vật nhường chỗ cho video
    }
  }
}
