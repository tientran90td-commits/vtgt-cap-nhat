/*
 * THÔNG BÁO LÊN CẢNH GIỚI (rank) - bảng lớn giữa màn hình, hiện ~8 giây (module riêng, giao diện ở rankup.css).
 * Chờ video ăn mừng chạy xong rồi mới hiện để không che video. Dữ liệu: result.rankUp = { name, avatar, tier, tierName, fromTier, fromName }.
 */
import { setFrame } from './rank.js';

const SHOW_MS = 8000;
const COLORS = ['#ffd54a', '#ff7ae8', '#5fd8ff', '#6dffb0', '#ffffff', '#ff8a5c'];

export class RankUp {
  constructor(el, avatarSrc) {
    this.el = el;
    this.avatarSrc = avatarSrc;
    this.pending = null;
    this.until = 0;
    this.visible = false;
  }

  /** Xếp hàng 1 thông báo (hiện khi đủ điều kiện, xem tick). */
  queue(ru) {
    this.pending = ru;
  }

  /** Gọi mỗi khung hình. phaseOk = đang ở màn hình kết quả; blocked = video ăn mừng đang chạy. */
  tick(phaseOk, blocked, now = performance.now()) {
    if (this.visible && (!phaseOk || now >= this.until)) this.hide();
    if (!this.visible && this.pending && phaseOk && !blocked) this.show(this.pending, now);
    if (!phaseOk && !this.visible) this.pending = null; // ván đã sang bước khác
  }

  show(ru, now) {
    this.pending = null;
    this.visible = true;
    this.until = now + SHOW_MS;
    const el = this.el;
    el.className = 'ru t' + ru.tier;
    el.querySelector('.ru-name').textContent = ru.name;
    el.querySelector('.ru-from').textContent = ru.fromName || '';
    el.querySelector('.ru-from').className = 'ru-from tc' + (ru.fromTier || 0);
    const to = el.querySelector('.ru-to');
    to.textContent = ru.tierName;
    to.className = 'ru-to tc' + ru.tier;
    setFrame(el.querySelector('.fr'), ru.tier);
    const img = el.querySelector('img');
    const sp = el.querySelector('.av span');
    sp.textContent = [...String(ru.name || '?').trim()][0] || '?';
    if (ru.avatar) {
      img.style.display = '';
      img.referrerPolicy = 'no-referrer';
      img.src = this.avatarSrc(ru.avatar);
      img.onerror = () => (img.style.display = 'none');
    } else {
      img.style.display = 'none';
    }
    // tia sáng + hạt lấp lánh bay ra
    const box = el.querySelector('.ru-sparks');
    box.replaceChildren();
    for (let i = 0; i < 28; i++) {
      const s = document.createElement('i');
      const ang = (i / 28) * Math.PI * 2 + Math.random() * 0.4;
      const dist = 5 + Math.random() * 6;
      s.style.setProperty('--dx', Math.cos(ang) * dist + 'rem');
      s.style.setProperty('--dy', Math.sin(ang) * dist + 'rem');
      s.style.background = COLORS[i % COLORS.length];
      s.style.animationDelay = (Math.random() * 1.6).toFixed(2) + 's';
      s.style.animationDuration = (1.4 + Math.random() * 1.2).toFixed(2) + 's';
      box.appendChild(s);
    }
    void el.offsetWidth;
    el.classList.add('show');
    if (this.onShow) this.onShow(ru);
  }

  hide() {
    this.visible = false;
    this.el.classList.remove('show');
    this.el.classList.add('hidden');
  }
}
