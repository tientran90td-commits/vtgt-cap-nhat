/*
 * PHÁT HIỆN "4 QUÂN LIỀN" sau mỗi nước đi (chỉ để làm hiệu ứng, không ảnh hưởng luật).
 * moves: [{x,y,m}], last: nước vừa đi. Trả về null hoặc { open: true|false } - open = cả 2 đầu còn trống (khó chặn).
 */
export function fourInRow(moves, size, last) {
  const grid = new Map();
  for (const mv of moves) grid.set(mv.x + ',' + mv.y, mv.m);
  const at = (x, y) => (x < 0 || y < 0 || x >= size || y >= size ? 'edge' : grid.get(x + ',' + y) || '');
  let best = null;
  for (const [dx, dy] of [[1, 0], [0, 1], [1, 1], [1, -1]]) {
    let n = 1;
    let x = last.x + dx;
    let y = last.y + dy;
    while (at(x, y) === last.m) { n++; x += dx; y += dy; }
    const e1 = at(x, y);
    x = last.x - dx;
    y = last.y - dy;
    while (at(x, y) === last.m) { n++; x -= dx; y -= dy; }
    const e2 = at(x, y);
    if (n === 4) {
      const free = (e1 === '' ? 1 : 0) + (e2 === '' ? 1 : 0);
      if (free > 0 && (!best || free > best.free)) best = { free, open: free === 2 };
    }
  }
  return best ? { open: best.open } : null;
}
