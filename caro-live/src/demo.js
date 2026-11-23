'use strict';
/*
 * CHẾ ĐỘ THỬ (DEMO): tạo khán giả ảo bình luận, thả tim, tặng quà và 2 người chơi tự đánh cờ,
 * để bạn xem game chạy mà không cần bật LIVE. Chạy bằng file CHAY-THU-DEMO.bat
 */

const FAKE = [
  ['minhanh_98', 'Minh Anh 🌸'],
  ['tuan.kiet', 'Tuấn Kiệt'],
  ['hoaibao2003', 'Hoài Bảo'],
  ['ngocdiep_', '𝓝𝓰𝓸𝓬 𝓓𝓲𝓮̣̂𝓹'],
  ['bichtram', 'Bích Trâm'],
  ['quangvinh77', 'Quang Vinh'],
  ['thuyvy', 'Thúy Vy ✨'],
  ['duyphong', 'Duy Phong'],
  ['lanhuong', 'Lan Hương'],
  ['khanhlinh_', 'Khánh Linh'],
  ['trungkien', 'Trung Kiên'],
  ['phuongthao', 'Phương Thảo'],
];
const CHAT = ['hay quá', 'cố lên', 'j9 đi', 'đánh k6 đi', 'xem vui ghê', 'chặn nó đi', 'ai thắng vậy', '🔥🔥', 'haha', 'đỉnh quá'];
const GIFTS = [
  ['Hoa hồng', 1],
  ['Hoa hồng', 1],
  ['Cà phê', 5],
  ['Trái tim', 10],
  ['Sư tử', 29],
];

const pick = (a) => a[Math.floor(Math.random() * a.length)];

/** Chấm điểm đơn giản để 2 người chơi ảo biết tấn công / chặn. */
function chooseMove(game, mark) {
  const opp = mark === 'X' ? 'O' : 'X';
  const dirs = [[1, 0], [0, 1], [1, 1], [1, -1]];
  const run = (x, y, who, dx, dy) => {
    let n = 0;
    for (let i = 1; i < 5; i++) {
      if (game.get(x + dx * i, y + dy * i) === who) n++;
      else break;
    }
    for (let i = 1; i < 5; i++) {
      if (game.get(x - dx * i, y - dy * i) === who) n++;
      else break;
    }
    return n;
  };
  const W = [1, 10, 100, 1000, 100000];
  let best = null;
  let bestScore = -1;
  for (let y = 0; y < game.size; y++) {
    for (let x = 0; x < game.size; x++) {
      if (!game.isEmpty(x, y)) continue;
      let near = game.moves.length === 0 ? 1 : 0;
      for (let dy = -2; dy <= 2 && !near; dy++) for (let dx = -2; dx <= 2; dx++) if (game.get(x + dx, y + dy)) near = 1;
      if (!near) continue;
      let s = Math.random() * 3;
      for (const [dx, dy] of dirs) {
        s += W[Math.min(run(x, y, mark, dx, dy), 4)];
        s += W[Math.min(run(x, y, opp, dx, dy), 4)] * 0.9;
      }
      s -= (Math.abs(x - 7) + Math.abs(y - 7)) * 0.2;
      if (s > bestScore) {
        bestScore = s;
        best = { x, y };
      }
    }
  }
  return best || game.nearbyEmptyCell();
}

function formatMove(x, y) {
  const L = String.fromCharCode(65 + x);
  const forms = [`${L}${y + 1}`, `${L.toLowerCase()}${y + 1}`, `${L.toLowerCase()} ${y + 1}`, `${y + 1}${L.toLowerCase()}`, `đánh ${L.toLowerCase()}${y + 1} nhé`];
  return pick(forms);
}

function startDemo(hub, cfg, log = console.log, opts = {}) {
  const users = FAKE.map(([id, name]) => ({ id: 'demo:' + id, uniqueId: id, name, avatar: '/demo-avatar?n=' + encodeURIComponent(name) }));
  if (opts.status) hub.setConnection('demo', 'CHẾ ĐỘ THỬ (khán giả ảo)');
  log('Đang chạy CHẾ ĐỘ THỬ: khán giả ảo sẽ tự bình luận và chơi.');
  const timers = [];
  let giftSeq = 0;

  // khán giả nhộn nhịp
  timers.push(
    setInterval(() => {
      const u = pick(users);
      const r = Math.random();
      if (r < 0.55) hub.onComment(u, pick(CHAT));
      else if (r < 0.9) hub.onLike(u, 1 + Math.floor(Math.random() * 10));
      else if (r < 0.97) {
        const [name, diamonds] = pick(GIFTS);
        hub.onGift(u, { name, diamonds, count: 1, key: `demo-gift-${++giftSeq}` });
      } else if (r < 0.985) hub.onFollow(u);
      else hub.onShare(u);
    }, 450)
  );

  // người được chọn tự thả tim xác nhận (thỉnh thoảng "vắng mặt" để thấy cảnh mời người khác thay)
  const liked = new Set();
  timers.push(
    setInterval(() => {
      const m = hub.match;
      if (m.phase !== 'confirm' || !m.confirm) return;
      for (const sl of m.confirm.slots) {
        const key = `${m.phaseStartedAt}:${sl.user.id}`;
        if (sl.done || liked.has(key)) continue;
        liked.add(key);
        if (liked.size > 200) liked.clear();
        if (Math.random() < 0.12) continue;
        timers.push(
          setTimeout(() => {
            if (m.phase === 'confirm') hub.onLike(sl.user, 5);
          }, 1500 + Math.random() * 5000)
        );
      }
    }, 300)
  );

  // người chơi tự đánh khi đến lượt
  let scheduled = '';
  timers.push(
    setInterval(() => {
      const m = hub.match;
      if (m.phase !== 'playing') {
        scheduled = '';
        return;
      }
      const key = `${m.gameNo}:${m.game.moves.length}`;
      if (scheduled === key) return;
      scheduled = key;
      const mark = m.turn;
      const p = m.players[mark];
      const t = setTimeout(() => {
        if (m.phase !== 'playing' || m.turn !== mark || key !== `${m.gameNo}:${m.game.moves.length}`) return;
        const cell = chooseMove(m.game, mark);
        if (!cell) return;
        // thỉnh thoảng gõ sai trước khi gõ đúng, để thấy game nhận diện bình luận
        if (Math.random() < 0.15) hub.onComment(p, pick(['để mình nghĩ đã', 'j99', 'hmm']));
        hub.onComment(p, formatMove(cell.x, cell.y));
      }, 1500 + Math.random() * 4500);
      timers.push(t);
    }, 300)
  );

  return {
    stop() {
      for (const t of timers) {
        clearInterval(t);
        clearTimeout(t);
      }
      timers.length = 0;
    },
  };
}

module.exports = { startDemo, chooseMove };
