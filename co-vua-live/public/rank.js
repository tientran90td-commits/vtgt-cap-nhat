/*
 * CẢNH GIỚI (RANK) - phần giao diện (module riêng):
 *  - frameFor(tier): đặt khung avatar theo cấp (đẹp dần từ Phàm Nhân tới Hóa Thần, giao diện ở rank.css)
 *  - renderRankBoard(state, setAvatar): vẽ bảng xếp hạng rank dưới bảng tu vi
 * Dữ liệu cấp bậc do server tính (src/rank.js) và gửi kèm state: players[X|O].rank, rankBoard[].
 */
export const TIER_NAMES = ['Phàm Nhân', 'Luyện Khí', 'Trúc Cơ', 'Kết Đan', 'Nguyên Anh', 'Hóa Thần'];

/** Đặt cấp cho phần tử khung `.fr` (class t0..t5). */
export function setFrame(frEl, tier) {
  if (!frEl) return;
  const t = Math.max(0, Math.min(5, Number(tier) || 0));
  const cls = 't' + t;
  if (frEl.dataset.tier === cls) return;
  frEl.dataset.tier = cls;
  frEl.classList.remove('t0', 't1', 't2', 't3', 't4', 't5');
  frEl.classList.add(cls);
}

let boardKey = '';
export function renderRankBoard(s, avatarSrc) {
  const list = s.rankBoard || [];
  const key = JSON.stringify(list.map((e) => [e.id, e.name, e.avatar, e.wins, e.rank.tier, e.rank.into]));
  if (key === boardKey) return;
  boardKey = key;
  const ol = document.getElementById('rankBoardList');
  if (!ol) return;
  ol.replaceChildren();
  if (!list.length) {
    const li = document.createElement('li');
    li.className = 'hint';
    li.textContent = 'Thắng ván cờ để nhập đạo, lên cảnh giới!';
    ol.appendChild(li);
    return;
  }
  for (const e of list) {
    const r = e.rank;
    const li = document.createElement('li');
    const fr = document.createElement('div');
    fr.className = 'fr';
    setFrame(fr, r.tier);
    const av = document.createElement('div');
    av.className = 'av';
    const img = document.createElement('img');
    img.alt = '';
    const sp = document.createElement('span');
    sp.textContent = [...String(e.name || '?').trim()][0] || '?';
    av.append(img, sp);
    if (e.avatar) {
      img.referrerPolicy = 'no-referrer';
      img.src = avatarSrc(e.avatar);
      img.onerror = () => (img.style.display = 'none');
    } else {
      img.style.display = 'none';
    }
    fr.appendChild(av);

    const info = document.createElement('div');
    info.className = 'rb-info';
    const nm = document.createElement('span');
    nm.className = 'rb-name';
    nm.textContent = e.name;
    const tier = document.createElement('span');
    tier.className = 'rb-tier tc' + r.tier;
    tier.textContent = r.name;
    const prog = document.createElement('span');
    prog.className = 'rb-prog';
    if (r.max) {
      prog.textContent = `Đỉnh cao • thắng ${e.wins} trận`;
    } else {
      prog.textContent = `Thắng ${r.into}/${r.need} → ${TIER_NAMES[r.tier + 1]}`;
    }
    info.append(nm, tier, prog);
    if (!r.max) {
      const bar = document.createElement('div');
      bar.className = 'rb-bar';
      const i = document.createElement('i');
      i.style.width = Math.min(100, (r.into / r.need) * 100).toFixed(0) + '%';
      bar.appendChild(i);
      info.appendChild(bar);
    }
    li.append(fr, info);
    ol.appendChild(li);
  }
}
