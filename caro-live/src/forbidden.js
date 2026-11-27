'use strict';
/*
 * LUẬT CẤM (kiểu renju) CHO QUÂN ĐI TRƯỚC - tách riêng, chỉ đọc bàn cờ, không đổi luật thắng/thua.
 * Chỉ áp dụng cho bàn thắng 5 quân. Quân bị cấm KHÔNG được đánh vào các ô làm ra:
 *   - "33": hai hàng 3 mở cùng lúc
 *   - "44": hai hàng 4 cùng lúc
 *   - "6" : hàng dài từ 6 quân trở lên
 * Ngoại lệ: nước đánh làm đủ ĐÚNG 5 quân (thắng) thì luôn được phép, dù có tạo 3-3 hay 4-4.
 * Một "hàng 3 mở" chỉ tính khi nước biến nó thành 4 mở lại hợp lệ (không phạm luật cấm chính nó).
 */

const DIRS = [[1, 0], [0, 1], [1, 1], [1, -1]];

const REASONS = {
  33: 'tạo 2 hàng 3 mở cùng lúc (3-3)',
  44: 'tạo 2 hàng 4 cùng lúc (4-4)',
  6: 'tạo hàng dài hơn 5 quân',
};

function at(game, x, y, dx, dy, t) {
  return game.get(x + dx * t, y + dy * t);
}

/** Số quân liên tiếp cùng màu đi qua (x,y) theo hướng (dx,dy), kèm ô ngay sau 2 đầu. */
function run(game, x, y, dx, dy, mark) {
  let a = 0;
  while (at(game, x, y, dx, dy, a + 1) === mark) a++;
  let b = 0;
  while (at(game, x, y, dx, dy, -(b + 1)) === mark) b++;
  return { n: a + b + 1, hi: a, lo: b, end1: at(game, x, y, dx, dy, a + 1), end2: at(game, x, y, dx, dy, -(b + 1)) };
}

/** Các ô trống (t từ -4..4) mà đánh vào đó thì thành ĐÚNG 5 quân đi qua (x,y). Trả về mảng t. */
function completions(game, x, y, dx, dy, mark) {
  const out = [];
  for (let t = -4; t <= 4; t++) {
    if (!t || at(game, x, y, dx, dy, t) !== '') continue;
    const cx = x + dx * t;
    const cy = y + dy * t;
    game.cells[cy][cx] = mark;
    const r = run(game, cx, cy, dx, dy, mark);
    game.cells[cy][cx] = '';
    // dãy 5 mới phải chứa (x,y): (x,y) cách c đúng -t ô, nằm trong [−lo, +hi]
    if (r.n === 5 && -t <= r.hi && -t >= -r.lo) out.push(t);
  }
  return out;
}

function countFours(game, x, y, dx, dy, mark) {
  const ts = completions(game, x, y, dx, dy, mark);
  let n = ts.length;
  // hàng 4 mở (_XXXX_) có 2 ô thắng nhưng chỉ là MỘT hàng 4
  for (const a of ts) {
    if (ts.includes(a + 5)) {
      let solid = true;
      for (let k = 1; k <= 4; k++) if (at(game, x, y, dx, dy, a + k) !== mark) solid = false;
      if (solid) n--;
    }
  }
  return n;
}

/** Hàng 3 mở thật: có ô để đánh thành 4 mở (cả 2 đầu trống, không dẫn tới hàng dài) và nước đó không bị cấm. */
function isOpenThree(game, x, y, dx, dy, mark, depth) {
  for (let t = -4; t <= 4; t++) {
    if (!t || at(game, x, y, dx, dy, t) !== '') continue;
    const cx = x + dx * t;
    const cy = y + dy * t;
    game.cells[cy][cx] = mark;
    const r = run(game, cx, cy, dx, dy, mark);
    game.cells[cy][cx] = '';
    if (r.n !== 4 || -t > r.hi || -t < -r.lo) continue;
    if (r.end1 !== '' || r.end2 !== '') continue;
    // 2 ô thắng ở 2 đầu phải cho ĐÚNG 5 (ô kế bên ngoài không được là quân cùng màu)
    const p1 = at(game, cx, cy, dx, dy, r.hi + 2);
    const p2 = at(game, cx, cy, dx, dy, -(r.lo + 2));
    if (p1 === mark || p2 === mark) continue;
    if (depth < 2 && reasonCode(game, cx, cy, mark, depth + 1)) continue; // chỉ đánh thành 4 mở bằng nước bị cấm thì chưa là 3 thật
    return true;
  }
  return false;
}

/** Mã lý do cấm: '6' | '44' | '33' | null. */
function reasonCode(game, x, y, mark, depth = 0) {
  if (!game.isEmpty(x, y)) return null;
  game.cells[y][x] = mark;
  try {
    const opp = mark === 'X' ? 'O' : 'X';
    let over = false;
    for (const [dx, dy] of DIRS) {
      const r = run(game, x, y, dx, dy, mark);
      if (r.n === 5) {
        const blocked = game.blockBothEnds && r.end1 === opp && r.end2 === opp;
        if (!blocked) return null; // đủ đúng 5 = thắng, luôn được phép
      }
      if (r.n >= 6) over = true;
    }
    if (over) return '6';
    let fours = 0;
    let threes = 0;
    for (const [dx, dy] of DIRS) {
      const f = countFours(game, x, y, dx, dy, mark);
      fours += f;
      if (!f && isOpenThree(game, x, y, dx, dy, mark, depth)) threes++;
    }
    if (fours >= 2) return '44';
    if (threes >= 2) return '33';
    return null;
  } finally {
    game.cells[y][x] = '';
  }
}

/** Ô (x,y) có bị cấm với quân `mark` không? Chỉ quân đi trước ('X') bị cấm. Trả về chuỗi lý do hoặc null. */
function forbiddenReason(game, x, y, mark) {
  if (mark !== 'X' || game.winLength !== 5) return null;
  const code = reasonCode(game, x, y, mark);
  return code ? REASONS[code] : null;
}

/** Danh sách ô cấm (chỉ xét ô trống trong vòng 2 ô quanh các quân đã đánh) để hiện lên bàn. */
function forbiddenCells(game, mark) {
  if (mark !== 'X' || game.winLength !== 5 || !game.moves.length) return [];
  const out = [];
  for (let y = 0; y < game.size; y++) {
    for (let x = 0; x < game.size; x++) {
      if (game.cells[y][x] !== '') continue;
      let near = false;
      for (let dy = -2; dy <= 2 && !near; dy++) for (let dx = -2; dx <= 2; dx++) if (game.get(x + dx, y + dy)) { near = true; break; }
      if (!near) continue;
      const c = reasonCode(game, x, y, mark);
      if (c) out.push({ x, y, r: c });
    }
  }
  return out;
}

module.exports = { forbiddenReason, forbiddenCells, REASONS };
