'use strict';
/*
 * LUẬT CỜ VUA (không liên quan TikTok / giao diện). Dùng thư viện chess.js cho luật chuẩn:
 * nhập thành, bắt tốt qua đường, phong cấp, chiếu, chiếu hết, hòa.
 * Quy ước: X = quân TRẮNG (đi trước), O = quân ĐEN.
 */
const { Chess } = require('chess.js');

const PIECE_VN = { p: 'tốt', n: 'mã', b: 'tượng', r: 'xe', q: 'hậu', k: 'vua' };
const VALUE = { p: 1, n: 3, b: 3, r: 5, q: 9, k: 0 };
const ROOK_MOVE = {
  w: { k: ['h1', 'f1'], q: ['a1', 'd1'] },
  b: { k: ['h8', 'f8'], q: ['a8', 'd8'] },
};
const markOfColor = (c) => (c === 'w' ? 'X' : 'O');

class ChessGame {
  constructor() {
    this.reset();
  }

  reset() {
    this.chess = new Chess();
    this.moves = [];
    this.ended = null;
  }

  /** Bên đang đến lượt: 'X' (trắng) hoặc 'O' (đen) */
  get turn() {
    return markOfColor(this.chess.turn());
  }

  /** Nước đi hợp lệ (dạng chi tiết của chess.js) */
  legalMoves() {
    return this.chess.moves({ verbose: true });
  }

  inCheck() {
    return this.chess.isCheck();
  }

  /** Quân của bên đang đi ở ô sq (hoặc null) */
  pieceAt(sq) {
    return this.chess.get(sq) || null;
  }

  /** Đi 1 nước ({from,to,promotion}). Trả về { ok, move, over } */
  play(m) {
    const mark = this.turn;
    const color = this.chess.turn();
    let r;
    try {
      r = this.chess.move({ from: m.from, to: m.to, promotion: m.promotion || undefined });
    } catch (e) {
      return { ok: false };
    }
    const flags = r.flags || '';
    const rec = {
      n: this.moves.length + 1,
      mark,
      from: r.from,
      to: r.to,
      piece: r.piece,
      color,
      san: r.san,
      captured: r.captured || '',
      promo: r.promotion || '',
      ep: flags.includes('e') ? r.to[0] + r.from[1] : '',
      castle: flags.includes('k') ? 'k' : flags.includes('q') ? 'q' : '',
      check: this.chess.isCheck(),
      mate: this.chess.isCheckmate(),
    };
    if (rec.castle) rec.rook = ROOK_MOVE[color][rec.castle];
    this.moves.push(rec);
    return { ok: true, move: rec, over: this.over() };
  }

  /** null nếu ván còn tiếp, hoặc { type:'checkmate'|'draw', reason, text } */
  over() {
    const c = this.chess;
    if (c.isCheckmate()) return { type: 'checkmate', reason: 'checkmate', text: 'chiếu hết' };
    if (c.isStalemate()) return { type: 'draw', reason: 'stalemate', text: 'hết nước đi (hòa pat)' };
    if (c.isInsufficientMaterial()) return { type: 'draw', reason: 'insufficient', text: 'không đủ quân để chiếu hết' };
    if (c.isThreefoldRepetition()) return { type: 'draw', reason: 'repetition', text: 'lặp lại thế cờ 3 lần' };
    if (c.isDrawByFiftyMoves()) return { type: 'draw', reason: 'fifty', text: '50 nước không ăn quân hay đi tốt' };
    if (c.isDraw()) return { type: 'draw', reason: 'draw', text: 'hai bên hòa' };
    return null;
  }

  /** Điểm vật chất (trắng - đen) */
  material() {
    let s = 0;
    for (const row of this.chess.board()) {
      for (const p of row) if (p) s += (p.color === 'w' ? 1 : -1) * VALUE[p.type];
    }
    return s;
  }

  /**
   * Nước đi "tạm ổn" khi người chơi hết giờ / bot demo: nhìn trước 2 nước theo vật chất,
   * ưu tiên chiếu hết, tránh đi mất quân. Chọn ngẫu nhiên giữa các nước tốt ngang nhau.
   */
  suggestMove(rng = Math.random) {
    const legal = this.legalMoves();
    if (!legal.length) return null;
    const me = this.chess.turn();
    const sign = me === 'w' ? 1 : -1;
    let best = -Infinity;
    let pool = [];
    for (const m of legal) {
      this.chess.move({ from: m.from, to: m.to, promotion: m.promotion });
      let score;
      if (this.chess.isCheckmate()) score = 1000;
      else if (this.chess.isDraw()) score = 0;
      else {
        // đối thủ trả lời tốt nhất (làm điểm của mình thấp nhất)
        let worst = Infinity;
        const replies = this.chess.moves({ verbose: true });
        for (const rp of replies) {
          this.chess.move({ from: rp.from, to: rp.to, promotion: rp.promotion });
          const v = this.chess.isCheckmate() ? -1000 : sign * this.material();
          this.chess.undo();
          if (v < worst) worst = v;
        }
        score = worst === Infinity ? 0 : worst;
        if (this.chess.isCheck()) score += 0.2;
        if (m.promotion) score += 0.1;
      }
      this.chess.undo();
      score += rng() * 0.05;
      if (score > best + 0.0001) {
        best = score;
        pool = [m];
      } else if (Math.abs(score - best) <= 0.05) pool.push(m);
    }
    const pick = pool[Math.floor(rng() * pool.length)] || legal[0];
    return { from: pick.from, to: pick.to, promotion: pick.promotion || undefined, san: pick.san, piece: pick.piece };
  }
}

const sqLabel = (sq) => sq;

module.exports = { ChessGame, PIECE_VN, sqLabel, markOfColor };
