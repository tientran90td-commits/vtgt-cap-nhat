/*
 * THÔNG BÁO LÊN CẢNH GIỚI (rank) - bảng lớn giữa màn hình, hiện ~8 giây (module riêng, giao diện ở rankup.css).
 * Chờ video ăn mừng chạy xong rồi mới hiện để không che video. Dữ liệu: result.rankUp = { name, avatar, tier, tierName, fromTier, fromName }.
 */
import { setFrame } from './rank.js';

const SHOW_MS = 8000;
const SHOW_DOWN_MS = 6500;
// lời "tụt hạng" hài hước (chọn ngẫu nhiên)
const DOWN_TITLES = ['💥 ĐỘ KIẾP THẤT BẠI! 💥', '⚡ ĐỘ KIẾP THẤT BẠI! ⚡', '☁️ ĐỘ KIẾP THẤT BẠI! ☁️'];
const DOWN_SUBS = ['Lôi kiếp đánh cho tan tác, tu vi tiêu tan hết!', 'Ngã ở đâu đứng dậy ở đó, đạo hữu cố lên!', 'Thiên lôi quá mạnh, tu lại từ đầu nhé!', 'Thua keo này ta bày keo khác!', 'Đan dược hết date, cần đi mua thêm!'];
const DOWN_COLORS = ['#7a8fb8', '#9aa7c8', '#5a6a94', '#c9d3ee'];
const COLORS = ['#ffd54a', '#ff7ae8', '#5fd8ff', '#6dffb0', '#ffffff', '#ff8a5c'];

export class RankUp {
  constructor(el, avatarSrc) {
    this.el = el;
    this.avatarSrc = avatarSrc;
    this.list = []; // hàng đợi: lên cấp (up) rồi tới tụt cấp (down)
    this.until = 0;
    this.visible = false;
  }

  /** Xếp hàng 1 thông báo (hiện khi đủ điều kiện, xem tick). kind = 'up' | 'down'. */
  queue(ru, kind = 'up') {
    this.list.push({ ...ru, kind });
  }

  /** Gọi mỗi khung hình. phaseOk = đang ở màn hình kết quả; blocked = video ăn mừng đang chạy. */
  tick(phaseOk, blocked, now = performance.now()) {
    if (this.visible && (!phaseOk || now >= this.until)) this.hide();
    if (!this.visible && this.list.length && phaseOk && !blocked) this.show(this.list.shift(), now);
    if (!phaseOk && !this.visible) this.list = []; // ván đã sang bước khác
  }

  show(ru, now) {
    this.visible = true;
    const down = ru.kind === 'down';
    this.until = now + (down ? SHOW_DOWN_MS : SHOW_MS);
    const el = this.el;
    el.className = 'ru t' + ru.tier + (down ? ' down' : '');
    const same = down && ru.fromTier === ru.tier; // cùng cảnh giới: hiện số điểm thay vì tên cảnh giới
    const pick = (a) => a[Math.floor(Math.random() * a.length)];
    el.querySelector('.ru-title').textContent = down ? pick(DOWN_TITLES) : '⚡ ĐỘT PHÁ! ⚡';
    el.querySelector('.ru-sub').textContent = down ? `Mất ${ru.lost || 0} điểm đạo hạnh${same ? ' (' + ru.tierName + ')' : ''}. ` + pick(DOWN_SUBS) : 'Cảnh giới mới, khung avatar thăng cấp';
    el.querySelector('.ru-name').textContent = ru.name;
    el.querySelector('.ru-from').textContent = same ? `${ru.fromPts} điểm` : ru.fromName || '';
    el.querySelector('.ru-from').className = 'ru-from tc' + (ru.fromTier || 0);
    const to = el.querySelector('.ru-to');
    to.textContent = same ? `${ru.toPts || 0} điểm` : ru.tierName;
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
      s.style.setProperty('--dx', Math.cos(ang) * dist * (down ? 0.5 : 1) + 'rem');
      s.style.setProperty('--dy', (down ? 2 + Math.abs(Math.sin(ang)) * dist : Math.sin(ang) * dist) + 'rem'); // tụt hạng: hạt rơi xuống như nước mắt
      s.style.background = (down ? DOWN_COLORS : COLORS)[i % COLORS.length];
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
