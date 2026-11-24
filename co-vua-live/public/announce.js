/*
 * THÔNG BÁO CỦA CHỦ PHÒNG (admin) - phần hiển thị trên màn hình live (module riêng).
 * Máy chủ gửi s.announce = { id, text, until } trong lúc thông báo còn hiệu lực; lời đọc đi theo hàng thoại (cues) của MC.
 */
export class Announcer {
  constructor(el, wrap) {
    this.el = el;
    this.wrap = wrap;
    this.id = null;
  }

  /** Gọi mỗi lần có dữ liệu mới. first = lần đầu mở trang (không phát lại thông báo cũ). */
  update(a, first) {
    if (!a) {
      if (this.id !== null) this.hide();
      return;
    }
    if (a.id === this.id) return;
    this.id = a.id;
    if (first) return;
    this.show(a.text);
    return true; // báo cho nơi gọi để phát tiếng "ting"
  }

  show(text) {
    this.el.querySelector('p').textContent = text;
    this.el.classList.remove('hidden');
    this.el.classList.remove('pop');
    void this.el.offsetWidth; // chạy lại hiệu ứng xuất hiện
    this.el.classList.add('pop');
    this.wrap.classList.add('ann');
  }

  hide() {
    this.id = null;
    this.el.classList.add('hidden');
    this.el.classList.remove('pop');
    this.wrap.classList.remove('ann');
  }
}
