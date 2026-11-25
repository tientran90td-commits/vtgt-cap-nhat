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
const CHAT = ['hay quá', 'cố lên', 'e4 đi', 'đi mã f3 đi', 'xem vui ghê', 'chặn lại đi', 'ai thắng vậy', '🔥🔥', 'haha', 'đỉnh quá'];
const GIFTS = [
  ['Hoa hồng', 1],
  ['Hoa hồng', 1],
  ['Cà phê', 5],
  ['Trái tim', 10],
  ['Sư tử', 29],
];

const pick = (a) => a[Math.floor(Math.random() * a.length)];

const PV = { p: 'tốt', n: 'mã', b: 'tượng', r: 'xe', q: 'hậu', k: 'vua' };

/** Chọn nước đi cho người chơi ảo (nhìn trước 2 nước theo vật chất). */
function chooseMove(game) {
  return game.suggestMove();
}

/** Gõ nước đi theo nhiều kiểu khác nhau để thấy game hiểu được. */
function formatMove(mv) {
  const r = Math.random();
  if (mv.san === 'O-O' || mv.san === 'O-O-O') return r < 0.5 ? mv.san : 'nhập thành';
  if (r < 0.3) return mv.from + mv.to + (mv.promotion || '');
  if (r < 0.5) return `${PV[mv.piece]} ${mv.to}`;
  if (r < 0.6) return `@@${mv.from}${mv.to}`;
  return mv.san.replace(/[+#]/g, '');
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
        const mv = chooseMove(m.game);
        if (!mv) return;
        // thỉnh thoảng gõ sai trước khi gõ đúng, để thấy game nhận diện bình luận
        if (Math.random() < 0.15) hub.onComment(p, pick(['để mình nghĩ đã', 'e9', 'hmm']));
        // thỉnh thoảng gõ 2 lần: chọn quân rồi gõ ô đến
        if (Math.random() < 0.25 && !mv.san.startsWith('O-O')) {
          hub.onComment(p, mv.from);
          setTimeout(() => {
            if (m.phase === 'playing' && m.turn === mark && key === `${m.gameNo}:${m.game.moves.length}`) hub.onComment(p, mv.to + (mv.promotion || ''));
          }, 900);
          return;
        }
        hub.onComment(p, formatMove(mv));
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
