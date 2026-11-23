/*
 * MÔ HÌNH BÀN CỜ VUA phía giao diện (không cần thư viện): dựng thế cờ từ danh sách nước đi server gửi.
 * Ô cờ là chuỗi như "e4". Quân: { t:'p|n|b|r|q|k', c:'w'|'b' }.
 */
export const FILES = 'abcdefgh';
export const sqXY = (sq) => ({ x: FILES.indexOf(sq[0]), y: Number(sq[1]) - 1 });
export const xySq = (x, y) => FILES[x] + (y + 1);
export const colorOf = (mark) => (mark === 'X' ? 'w' : 'b');

export function initialBoard() {
  const b = new Map();
  const back = ['r', 'n', 'b', 'q', 'k', 'b', 'n', 'r'];
  for (let i = 0; i < 8; i++) {
    b.set(FILES[i] + '1', { t: back[i], c: 'w' });
    b.set(FILES[i] + '2', { t: 'p', c: 'w' });
    b.set(FILES[i] + '7', { t: 'p', c: 'b' });
    b.set(FILES[i] + '8', { t: back[i], c: 'b' });
  }
  return b;
}

/** Áp 1 nước đi lên bàn (sửa trực tiếp). mv: { m, from, to, p, promo, ep, rook } */
export function applyMove(b, mv) {
  const color = colorOf(mv.m);
  b.delete(mv.from);
  if (mv.ep) b.delete(mv.ep);
  b.set(mv.to, { t: mv.promo || mv.p, c: color });
  if (mv.rook) {
    const r = b.get(mv.rook[0]) || { t: 'r', c: color };
    b.delete(mv.rook[0]);
    b.set(mv.rook[1], r);
  }
  return b;
}

export function boardFromMoves(moves) {
  const b = initialBoard();
  for (const mv of moves) applyMove(b, mv);
  return b;
}

export function kingSquare(b, color) {
  for (const [sq, p] of b) if (p.t === 'k' && p.c === color) return sq;
  return null;
}
