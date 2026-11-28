/*
 * CHẾ ĐỘ CÀY ĐIỂM (client): vẽ bảng điểm ở giữa bàn cờ trong khoảng cày điểm sau mỗi trận.
 * Server gửi s.farm = { on, active, secs } và s.top (điểm cày trong khoảng này). Tắt chế độ -> không làm gì.
 */
const MEDALS = ['🥇', '🥈', '🥉'];
let lastKey = '';
let prev = new Map();
let flashUntil = 0;
let lastRound = '';

export function farmOn(s) {
  return !!(s && s.farm && s.farm.on);
}

/** Bật / tắt class của <body> để ẩn bảng cơ duyên bên phải khi đang ở chế độ cày điểm. */
export function farmBody(s) {
  document.body.classList.toggle('farmOn', farmOn(s));
}

export function renderFarm(s, now, $) {
  const need = s.lobby ? s.lobby.need : 2;
  const left = Math.ceil((s.phaseEndsAt - now) / 1000);
  const waiting = s.lobby && s.lobby.waiting;
  const round = s.gameNo + ':' + s.phaseStartedAt;
  if (round !== lastRound) {
    lastRound = round;
    flashUntil = Date.now() + 4500; // 4,5 giây đầu: dòng thông báo "BẮT ĐẦU CÀY ĐIỂM"
    prev = new Map();
    lastKey = '';
  }
  $('farmFlash').classList.toggle('off', Date.now() > flashUntil);
  const c = $('farmCount');
  if (waiting || left <= 0) {
    c.textContent = 'Chờ thêm người tương tác…';
    c.classList.add('wait');
  } else {
    c.textContent = String(left);
    c.classList.remove('wait');
  }
  $('farmFlash').textContent = `⏱ BẮT ĐẦU CÀY ĐIỂM · ${s.farm.secs || ''} GIÂY!`;
  const key = JSON.stringify(s.top.map((u) => [u.id, u.points, u.name]));
  if (key === lastKey) return;
  lastKey = key;
  const ol = $('farmList');
  ol.replaceChildren();
  const rows = 6;
  for (let i = 0; i < rows; i++) {
    const u = s.top[i];
    const li = document.createElement('li');
    const no = document.createElement('span');
    no.className = 'no';
    no.textContent = MEDALS[i] || String(i + 1);
    const nm = document.createElement('span');
    nm.className = 'nm';
    li.append(no, nm);
    if (!u) {
      li.className = 'empty';
      nm.textContent = '—';
    } else {
      if (i < need) li.classList.add('pick');
      nm.textContent = u.name;
      const pts = document.createElement('span');
      pts.className = 'pts';
      pts.textContent = u.points;
      li.appendChild(pts);
      if (prev.has(u.id) && prev.get(u.id) !== u.points) li.classList.add('bump');
    }
    ol.appendChild(li);
  }
  prev = new Map(s.top.map((u) => [u.id, u.points]));
}
