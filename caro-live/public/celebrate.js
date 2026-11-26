/*
 * ĂN MỪNG KHI CÓ NGƯỜI THẮNG (module riêng).
 * Khi 1 người thắng ván: phát NGAY tiếng nhạc của video, đợi đủ giây "showAt" của video đó rồi mới hiện hình thế chỗ 2 nhân vật 3D.
 * Hết video: ẩn video, 2 nhân vật quay lại như cũ, game tiếp tục các bước như cũ.
 * MỖI TRẬN BỐC NGẪU NHIÊN 1 VIDEO trong danh sách VIDEOS bên dưới (video được nạp sẵn từ cuối trận trước nên bật là chạy ngay).
 * Muốn thêm video: bỏ 2 file <tên>.mp4 (H.264 + AAC) và <tên>.webm vào public/media rồi thêm 1 dòng vào VIDEOS.
 * Muốn đổi giây hiện hình của từng video: sửa số showAt ở dòng của video đó.
 */
const VIDEOS = [
  { file: 'celebrate', showAt: 4 }, // video làm lúc trước
  { file: 'celebrate2', showAt: 3 }, // video 1 (mới): hiện hình lúc giây thứ 3
  { file: 'celebrate3', showAt: 6 }, // video 2 (mới): hiện hình lúc giây thứ 6
]; // showAt: giây (tính theo thời gian của video): có tiếng trước, tới giây này mới hiện hình

export class Celebrate {
  constructor(video, wrap, threeCanvas) {
    this.v = video;
    this.wrap = wrap;
    this.three = threeCanvas;
    this.running = false;
    this.shown = false;
    this.cur = VIDEOS[0];
    this.v.preload = 'auto';
    this.v.playsInline = true;
    this.v.addEventListener('ended', () => this.stop());
    // lỗi nguồn: chỉ dừng khi cả mp4 lẫn webm đều không phát được (lỗi của thẻ <source> cuối cùng)
    this.v.addEventListener('error', () => this.stop());
    this.v.addEventListener('timeupdate', () => this.tick()); // không phụ thuộc vòng vẽ khung hình (tab nền / OBS bị giảm tốc)
    setInterval(() => this.tick(), 250);
    window.addEventListener('resize', () => this.layout());
    this.choose(); // bốc video cho trận đầu tiên
  }

  /** Bốc ngẫu nhiên 1 video cho trận tới và nạp sẵn. Chỉ gọi khi video đang không chạy. */
  choose() {
    const e = VIDEOS[Math.floor(Math.random() * VIDEOS.length)];
    this.cur = e;
    const v = this.v;
    while (v.firstChild) v.removeChild(v.firstChild);
    let last = null;
    for (const [ext, type] of [['mp4', 'video/mp4'], ['webm', 'video/webm']]) {
      last = document.createElement('source');
      last.src = 'media/' + e.file + '.' + ext;
      last.type = type;
      v.appendChild(last);
    }
    if (last) last.addEventListener('error', () => this.stop());
    try { v.load(); } catch (err) {}
  }

  active() {
    return this.running;
  }

  start() {
    this.halt();
    const v = this.v;
    this.running = true;
    this.shown = false;
    this.startedAt = Date.now();
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

  /** Dừng và trả hình về như cũ (không đổi video). */
  halt() {
    this.running = false;
    this.shown = false;
    const v = this.v;
    try { v.pause(); } catch (e) {}
    v.classList.remove('show');
    if (this.three) this.three.style.visibility = '';
  }

  /** Hết trận ăn mừng: dừng, rồi bốc sẵn video cho trận sau. */
  stop() {
    const was = this.running;
    this.halt();
    if (was) this.choose();
  }

  layout() {
    const w = this.wrap.clientWidth, h = this.wrap.clientHeight;
    const size = Math.floor(Math.min(w, h) * 0.97);
    this.v.style.width = size + 'px';
    this.v.style.height = size + 'px';
  }

  /** Gọi mỗi khung hình. */
  tick() {
    // video bị trình duyệt giữ lại (chưa phát được) sau 1,5 giây -> thử lại không tiếng
    if (this.running && !this.shown && this.v.paused && Date.now() - (this.startedAt || 0) > 1500 && !this.v.ended) {
      this.startedAt = Date.now();
      this.v.muted = true;
      const q = this.v.play();
      if (q && q.catch) q.catch(() => {});
    }
    if (this.running && (this.v.ended || (isFinite(this.v.duration) && this.v.currentTime >= this.v.duration - 0.04))) { this.stop(); return; } // hết video -> về như cũ
    if (!this.running || this.shown) return;
    if (this.v.currentTime >= this.cur.showAt && !this.v.paused) {
      this.shown = true;
      this.layout();
      this.v.classList.add('show');
      if (this.three) this.three.style.visibility = 'hidden'; // 2 nhân vật nhường chỗ cho video
    }
  }
}
