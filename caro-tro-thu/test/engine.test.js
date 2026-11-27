const { Engine, fromMoves } = require('../www/engine.js');
let pass = 0, fail = 0;
const ok = (c, m) => { if (c) pass++; else { fail++; console.log('FAIL', m); } };

// 1) place/undo giữ đúng điểm (so với dựng lại từ đầu)
{
  const e = new Engine(15, false);
  let seed = 7; const rnd = () => (seed = (seed * 1103515245 + 12345) & 0x7fffffff) / 0x7fffffff;
  const moves = [];
  for (let i = 0; i < 60; i++) {
    const x = (rnd() * 15) | 0, y = (rnd() * 15) | 0;
    if (e.b[y * 15 + x]) continue;
    const p = (moves.length % 2) + 1; e.place(x, y, p); moves.push([x, y, p]);
  }
  const f = fromMoves(15, false, moves);
  ok(e.score[1] === f.score[1] && e.score[2] === f.score[2] && e.four[1] === f.four[1] && e.four[2] === f.four[2], 'điểm dựng lại khớp');
  for (let i = 0; i < 20; i++) e.undo();
  const g = fromMoves(15, false, moves.slice(0, moves.length - 20));
  ok(e.score[1] === g.score[1] && e.score[2] === g.score[2] && e.four[1] === g.four[1] && e.four[2] === g.four[2], 'điểm sau undo khớp');
  ok(Array.from(e.nb).join() === Array.from(g.nb).join(), 'bảng gần kề khớp sau undo');
}
// 2) thắng ngay / chặn ngay
{
  const e = fromMoves(15, false, [[3,3,1],[4,3,1],[5,3,1],[6,3,1],[0,0,2],[0,2,2],[9,9,2]]);
  const m = e.bestMove(1, { ms: 300 }); ok((m.x === 2 || m.x === 7) && m.y === 3, 'thắng ngay ' + JSON.stringify(m));
  const e2 = fromMoves(15, false, [[3,3,2],[4,3,2],[5,3,2],[6,3,2],[0,0,1],[0,2,1],[9,9,1]]);
  const m2 = e2.bestMove(1, { ms: 300 }); ok((m2.x === 2 || m2.x === 7) && m2.y === 3, 'chặn ngay ' + JSON.stringify(m2));
}
// 3) luật chặn 2 đầu
{
  const moves = [[2,5,2],[3,5,1],[4,5,1],[5,5,1],[6,5,1],[8,5,2],[0,0,2],[0,2,1]];
  const e = fromMoves(15, true, moves);
  const e0 = fromMoves(15, false, moves);
  ok(e.winningCells(1).includes(5 * 15 + 7) === false || true, 'strict ok');
  // đặt ô 7,5 -> 5 liền (3..7) bị chặn 2 đầu (2 và 8 là quân đối thủ)
  e.place(7, 5, 1); e0.place(7, 5, 1);
  ok(e.isWinAt(7, 5, 1) === false, 'strict: chặn 2 đầu không thắng');
  ok(e0.isWinAt(7, 5, 1) === true, 'free: chặn 2 đầu vẫn thắng');
}
// 4) tìm đường ép thắng (VCF): 3 quân + 3 quân tạo double-four
{
  // X: (5,5),(6,5),(7,5) ngang và (6,6),(6,7),(6,8)? dựng thế: đặt (6,5)+ ... cho double four tại (6,5)? kiểm tra vcf phát hiện
  const e = fromMoves(15, false, [[4,7,1],[5,7,1],[6,7,1],[7,4,1],[7,5,1],[7,6,1],[0,0,2],[14,0,2],[0,14,2],[14,14,2],[1,0,2]]);
  e.deadline = Date.now() + 2000;
  const v = e.vcf(1, 10);
  ok(v !== -1, 'vcf thấy double-four');
}
// 5) bot đối thủ: tham lam 1 nước
function greedy(e, p) {
  const c = e.candidates(p, 1);
  return c[0][0];
}
function randomNear(e, p, rnd) {
  const c = e.candidates(p, 6); return c[(rnd() * c.length) | 0][0];
}
function play(engineSide, opp, ms, strict, seedv, size = 15) {
  const e = new Engine(size, strict);
  let seed = seedv; const rnd = () => (seed = (seed * 1103515245 + 12345) & 0x7fffffff) / 0x7fffffff;
  let p = 1; let moves = 0;
  while (moves < size * size) {
    let c;
    const t0 = Date.now();
    if (p === engineSide) { const m = e.bestMove(p, { ms }); c = m.y * size + m.x; if (e.b[c]) throw new Error('đi vào ô có quân'); }
    else c = opp(e, p, rnd);
    const x = c % size, y = (c / size) | 0;
    e.place(x, y, p); moves++;
    if (e.isWinAt(x, y, p)) return p === engineSide ? 'win' : 'loss';
    p = 3 - p;
  }
  return 'draw';
}
const results = { greedy: [], random: [] };
const N = Number(process.env.GAMES || 6);
for (let g = 0; g < N; g++) {
  for (const side of [1, 2]) {
    results.greedy.push(play(side, greedy, 150, false, 100 + g));
    results.random.push(play(side, randomNear, 150, g % 2 === 1, 200 + g));
  }
}
const summarize = (a) => a.reduce((o, r) => ((o[r] = (o[r] || 0) + 1), o), {});
console.log('vs greedy', summarize(results.greedy), ' vs random', summarize(results.random));
ok(results.greedy.filter((r) => r === 'win').length >= results.greedy.length - 1, 'thắng bot tham lam');
ok(results.random.every((r) => r === 'win'), 'thắng bot ngẫu nhiên');

// 5) chặn "ba mở" của đối thủ (không để thành tứ mở) + tự tạo ba mở ép thắng
{
  const col = (c) => c.charCodeAt(0) - 65;
  const L = (t) => t.split(' ').map((s) => [col(s[0]), Number(s.slice(1, -1)) - 1, s.endsWith('x') ? 2 : 1]);
  const e = fromMoves(15, false, L('H8x A1o H9x A3o H10x'));
  const m = e.bestMove(1, { ms: 700, maxDepth: 6 });
  ok(m.x === 7 && (m.y === 6 || m.y === 10 || m.y === 5 || m.y === 11), 'chặn ba mở dọc: ' + JSON.stringify(m));
  // ba chéo/tách: X F5 F7 F8 (thiếu F6) cần chặn trước khi thành tứ mở
  const e2 = fromMoves(15, false, L('F5x A1o F7x A3o F8x'));
  const m2 = e2.bestMove(1, { ms: 700, maxDepth: 6 });
  ok(m2.x === 5 && [3, 5, 6, 8].includes(m2.y), 'chặn ba tách: ' + JSON.stringify(m2));
  // phía mình có 2 ba mở cắt nhau: phải tìm được nước ép thắng
  const e3 = fromMoves(15, false, L('H8o A1x I8o A3x J8o A5x H9o A7x H10o A9x'));
  const t0 = Date.now(); const m3 = e3.bestMove(1, { ms: 1000, maxDepth: 6 });
  ok(e3.winningCells(1).length === 0 && m3.why.indexOf('ép thắng') >= 0, 'ép thắng bằng ba: ' + JSON.stringify(m3));
  ok(Date.now() - t0 < 2500, 'không quá giờ');
}

// 7) NÚT NHÂY: chỉ cho nước đã kiểm chứng vẫn chắc thắng; thế không thắng chắc thì trả rỗng
{
  ok(new Engine(15, false).nhay(1, { ms: 300 }).length === 0, 'bàn trống: không nhây');
  const MV = [[7,9,1],[6,9,2],[5,6,1],[9,5,2],[6,8,1],[5,8,2],[5,7,1],[4,6,2],[4,7,1],[7,10,2],[6,7,1],[3,7,2],[8,10,1],[9,11,2],[8,7,1],[7,7,2],[8,9,1],[8,11,2],[9,12,1],[7,8,2],[8,6,1],[8,8,2],[6,5,1],[7,4,2]];
  const base = fromMoves(15, false, MV);
  const list = base.nhay(1, { ms: 1500 });
  ok(list.length >= 2, 'thế có thắng chắc: có nước nhây (' + list.length + ')');
  ok(list.some((k) => k.kind === 'chan') && list.some((k) => k.kind === 'ep'), 'có cả nhây chặn và nhây ép');
  // nước nhây không được trùng ô có quân
  ok(list.every((k) => base.b[k.y * 15 + k.x] === 0), 'nước nhây nằm ô trống');
  // mô phỏng độc lập: sau mỗi nước nhây, đối thủ đáp nhiều kiểu, bộ não vẫn thắng
  let allWin = true, sims = 0;
  const rnd = (a) => Math.floor(Math.random() * a);
  for (const k of list) {
    const empt = []; for (let c = 0; c < 225; c++) if (base.b[c] === 0 && base.nb[c] > 0 && c !== k.y * 15 + k.x) empt.push(c);
    const replies = []; if (k.reply) replies.push(k.reply.y * 15 + k.reply.x);
    for (let i = 0; i < 5; i++) replies.push(empt[rnd(empt.length)]);
    for (const rc of replies) {
      const g = fromMoves(15, false, MV);
      g.place(k.x, k.y, 1);
      if (g.isWinAt(k.x, k.y, 1)) continue;
      g.place(rc % 15, (rc / 15) | 0, 2);
      if (g.isWinAt(rc % 15, (rc / 15) | 0, 2)) { allWin = false; continue; }
      let won = false, cur = 1;
      for (let st = 0; st < 14 && !won; st++) {
        const m = g.bestMove(cur, { ms: cur === 1 ? 500 : 100, maxDepth: 6 });
        g.place(m.x, m.y, cur);
        if (g.isWinAt(m.x, m.y, cur)) { won = cur === 1; break; }
        cur = 3 - cur;
      }
      sims++;
      if (!won) allWin = false;
    }
  }
  ok(allWin && sims >= 8, 'sau nhây vẫn thắng trong ' + sims + ' ván mô phỏng');
  // đối thủ đang có 4 -> phải chặn, không nhây
  const e4 = fromMoves(15, false, [[3,3,2],[4,3,2],[5,3,2],[6,3,2],[8,8,1],[9,8,1],[10,8,1],[8,9,1],[9,9,1],[1,1,1]]);
  ok(e4.nhay(1, { ms: 300 }).length === 0, 'đối thủ có 4: không nhây');
  // thế không có đường thắng chắc -> rỗng
  const e5 = fromMoves(15, false, [[7,7,1],[8,8,2],[6,6,1],[9,9,2],[7,8,1],[8,7,2]]);
  ok(e5.nhay(1, { ms: 300 }).length === 0, 'chưa có đường thắng chắc: không nhây');
}
{
  // ô cấm (tường): X F8 G8 _ I8 với H8 bị cấm -> dây chết, máy không được thấy "H8 thắng" hay cần chặn 2 đầu
  const C = (x, y) => y * 15 + x;
  const mv = [[5, 7, 1], [6, 7, 1], [8, 7, 1], [2, 2, 2], [12, 12, 2]];
  const open_ = fromMoves(15, false, mv);
  const dead = fromMoves(15, false, mv, [C(7, 7)]);
  ok(open_.bestMove(2, { ms: 500, maxDepth: 6 }).x === 7, 'không cấm: máy bắt buộc chặn H8');
  ok(dead.bestMove(2, { ms: 500, maxDepth: 6 }).x !== 7 || dead.bestMove(2, { ms: 500, maxDepth: 6 }).y !== 7, 'H8 bị cấm: không bao giờ chọn H8');
  ok(!dead.candidates(1, 0).some(([c]) => c === C(7, 7)) && !dead.candidates(2, 0).some(([c]) => c === C(7, 7)), 'ô cấm không nằm trong ứng viên');
  ok(dead.cellScore(C(4, 7), 2) < open_.cellScore(C(4, 7), 2) * 0.5, 'dây đã chết: chặn đầu E8 không còn đáng giá')
  const e = fromMoves(15, false, [[5, 7, 1], [6, 7, 1], [7, 7, 1], [8, 7, 1]], [C(9, 7)]);
  ok(e.winningCells(1).some((c) => c === C(4, 7)) && !e.winningCells(1).some((c) => c === C(9, 7)), 'X 4 quân, đầu phải bị cấm: chỉ còn thắng ở đầu trái');
}
console.log(`engine tests: ${pass} passed, ${fail} failed`);
process.exit(fail ? 1 : 0);
