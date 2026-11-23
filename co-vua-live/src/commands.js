'use strict';
/*
 * ĐỌC BÌNH LUẬN CỜ VUA
 * parseChessMove(raw, game, sel) nhận nhiều cách gõ:
 *   e2e4 · e2 e4 · e2-e4 · e4 · Nf3 · Nxe5 · exd5 · O-O · e8=Q
 *   mã f3 · xe d1 · tượng c4 · hậu h5 · tốt e4 · mã g1 f3 · nhập thành (ngắn/dài) · e7 e8 hậu
 *   gõ 2 lần: "e2" (chọn quân, hiện các ô đi được) rồi "e4"
 *   @e4, @@e4 (thêm @ để bình luận không bị ẩn)
 * Kết quả:
 *   { ok:true, move:{from,to,promotion} }
 *   { ok:false, reason:'none' }                      không phải nước đi
 *   { ok:false, reason:'illegal', text }             gõ đúng kiểu nhưng không đi được
 *   { ok:false, reason:'ambiguous', options:[...] }  nhiều quân cùng đi được -> hỏi lại
 *   { ok:false, reason:'select', from, targets }     chọn quân, chờ ô đến
 *   { ok:false, reason:'empty', sq }                 ô đó không có quân của bạn đi được
 */

function stripDiacritics(s) {
  return s.normalize('NFD').replace(/[\u0300-\u036f]/g, '').replace(/đ/g, 'd');
}

function cleanText(raw) {
  return String(raw == null ? '' : raw)
    .normalize('NFKC') // ｅ４ -> e4
    .replace(/[\u200b-\u200f\u202a-\u202e\u2060\ufeff]/g, '')
    .toLowerCase()
    .replace(/https?:\/\/\S+/g, ' ')
    .replace(/\s+/g, ' ')
    .trim();
}

const PIECE_WORDS = {
  tot: 'p', pawn: 'p',
  ma: 'n', knight: 'n', horse: 'n',
  tuong: 'b', bishop: 'b',
  xe: 'r', rook: 'r', tower: 'r',
  hau: 'q', queen: 'q',
  vua: 'k', king: 'k',
};
const FILLERS = new Set([
  'di', 'danh', 'nuoc', 'chon', 'quan', 'con', 'cai', 'minh', 'em', 'toi', 'nhe', 'nha', 'a', 'ah', 'oi', 'luon', 'thoi', 'xin',
  'vao', 'o', 'len', 'sang', 'la', 'play', 'move', 'to', 'den', 'phong', 'cap', 'ben', 'cho', 'nao', 'thi', 'nua', 'va',
  'move', 'play', 'ok', 'oke',
]);
const NAMES = { p: 'tốt', n: 'mã', b: 'tượng', r: 'xe', q: 'hậu', k: 'vua' };
const SQ = '[a-h][1-8]';

/** Các cách hiểu 1 từ dạng "gọn" (nf3, exd5, e2e4, e8=q, bc4...) -> danh sách ràng buộc */
function compactToken(tok) {
  const out = [];
  const m1 = tok.match(new RegExp(`^(?:([kqrnb])?)([a-h])?([1-8])?(x|:|-)?(${SQ})(?:=?([qrbn]))?[+#]?$`));
  if (!m1) return out;
  const [, pc, ff, fr, cap, to, promo] = m1;
  const base = { to, promo: promo || '' };
  if (cap === 'x' || cap === ':') base.capture = true;
  if (pc) {
    // chữ đầu là tên quân (n r q k, hoặc b = tượng)
    out.push({ ...base, piece: pc, fromFile: ff || '', fromRank: fr || '' });
    if (pc === 'b') {
      // "bxc4", "b4": b là cột b của tốt -> thử cách hiểu này trước
      const m2 = tok.match(new RegExp(`^([a-h])?([1-8])?(x|:|-)?(${SQ})(?:=?([qrbn]))?[+#]?$`));
      if (m2) out.unshift({ to: m2[4], promo: m2[5] || '', capture: m2[3] === 'x' || m2[3] === ':', fromFile: m2[1] || '', fromRank: m2[2] || '', piece: '' });
    }
  } else {
    out.push({ ...base, piece: '', fromFile: ff || '', fromRank: fr || '' });
  }
  return out;
}

/** Biến danh sách từ thành các "ràng buộc" nước đi có thể hiểu được (theo thứ tự ưu tiên) */
function constraintsOf(tokens) {
  if (!tokens.length) return [];
  const joined = tokens.join(' ');
  // nhập thành
  const castleTok = tokens.find((t) => /^(?:o-o-o|0-0-0|o-o|0-0|oo|ooo|castle|castling|nhapthanh)$/.test(t));
  if (castleTok || /^nhap thanh\b/.test(joined)) {
    let side = 'any';
    if (/^(?:o-o-o|0-0-0|ooo)$/.test(castleTok || '') || /\b(dai|long|hau|q)\b/.test(joined)) side = 'q';
    else if (/^(?:o-o|0-0|oo)$/.test(castleTok || '') || /\b(ngan|short|vua|k)\b/.test(joined)) side = 'k';
    const rest = tokens.filter((t) => t !== castleTok && !/^(nhap|thanh|ngan|dai|short|long|vua|hau|k|q|castle|nhapthanh)$/.test(t));
    return rest.length ? [] : [{ castle: side }];
  }
  let toks = tokens.slice();
  // tên quân tiếng Việt/Anh ở đầu: "ma f3", "ma g1 f3"
  let piece = '';
  if (toks.length > 1 && PIECE_WORDS[toks[0]]) {
    piece = PIECE_WORDS[toks[0]];
    toks = toks.slice(1);
  }
  // phong cấp ở cuối: "e7 e8 hau", "e8 =q"
  let promo = '';
  const last = toks[toks.length - 1];
  if (toks.length > 1 && PIECE_WORDS[last] && PIECE_WORDS[last] !== 'p' && PIECE_WORDS[last] !== 'k') {
    promo = PIECE_WORDS[last];
    toks = toks.slice(0, -1);
  } else if (toks.length > 1 && /^=?[qrbn]$/.test(last) && /^[a-h][1-8]/.test(toks[toks.length - 2] || '')) {
    promo = last.replace('=', '');
    toks = toks.slice(0, -1);
  }
  // bỏ chữ x đứng riêng ("e4 x d5")
  const hadX = toks.includes('x');
  toks = toks.filter((t) => t !== 'x' && t !== '-' && t !== 'x:');
  if (!toks.length) return [];
  const res = [];
  if (toks.length === 1) {
    for (const c of compactToken(toks[0])) res.push({ ...c, piece: piece || c.piece, promo: promo || c.promo, capture: c.capture || hadX });
  } else if (toks.length === 2 && toks.every((t) => new RegExp(`^${SQ}$`).test(t))) {
    res.push({ from: toks[0], to: toks[1], piece, promo, capture: hadX });
  } else if (toks.length === 2 && new RegExp(`^${SQ}$`).test(toks[1])) {
    // "b c4", "n f3", "e x d5" (tên quân/cột rời)
    for (const c of compactToken(toks[0] + toks[1])) res.push({ ...c, piece: piece || c.piece, promo: promo || c.promo, capture: c.capture || hadX });
  }
  return res;
}

function tokenize(text) {
  let t = stripDiacritics(text)
    .replace(/nhap thanh/g, 'nhapthanh')
    .replace(/\b([a-h])\s+([1-8])\b/g, '$1$2') // "e 4" -> e4
    .replace(/[,;!?()"'`~.…]+/g, ' ')
    .replace(/\b\d+\s*\.\s*/g, ' ');
  const toks = t.split(/\s+/).filter(Boolean);
  return toks.filter((x) => !FILLERS.has(x) && !/^\d{1,3}$/.test(x) && !/^[^a-z0-9=\-:]+$/.test(x));
}

function moveMatches(m, c) {
  if (c.castle) return c.castle === 'any' ? !!(m.flags.includes('k') || m.flags.includes('q')) : m.flags.includes(c.castle);
  if (m.flags.includes('k') || m.flags.includes('q')) {
    // nước nhập thành cũng có thể gõ là "vua đi g1"
    if (c.piece && c.piece !== 'k') return false;
  }
  if (c.to && m.to !== c.to) return false;
  if (c.from && m.from !== c.from) return false;
  if (c.piece && m.piece !== c.piece) return false;
  if (c.fromFile && m.from[0] !== c.fromFile) return false;
  if (c.fromRank && m.from[1] !== c.fromRank) return false;
  if (c.capture && !(m.captured || m.flags.includes('e'))) return false;
  if (c.promo ? m.promotion !== c.promo : m.promotion && m.promotion !== 'q') return false;
  return true;
}

function describe(m, all) {
  const same = all.filter((x) => x.piece === m.piece).length > 1;
  const nm = NAMES[m.piece];
  return same ? `${nm} ${m.from} ${m.to}` : `${nm} ${m.to}`;
}

/** Thử hiểu 1 chuỗi (đã làm sạch). Trả kết quả hoặc null nếu không giống nước đi */
function tryText(text, legal, sel, game) {
  const tokens = tokenize(text);
  if (!tokens.length || tokens.length > 8) return null;
  const cs = constraintsOf(tokens);
  if (!cs.length) return null;
  let illegalText = null;
  for (const c of cs) {
    const only = !c.castle && c.to && !c.from && !c.piece && !c.fromFile && !c.fromRank && !c.capture && !c.promo;
    // 1) đang chọn quân dở và gõ ô đến
    if (only && sel && sel.from) {
      const hit = legal.filter((m) => m.from === sel.from && m.to === c.to);
      const pick = hit.find((m) => !m.promotion || m.promotion === 'q');
      if (pick) return { ok: true, move: { from: pick.from, to: pick.to, promotion: pick.promotion || undefined } };
    }
    const ms = legal.filter((m) => moveMatches(m, c));
    if (ms.length === 1) return { ok: true, move: { from: ms[0].from, to: ms[0].to, promotion: ms[0].promotion || undefined } };
    if (ms.length > 1) {
      // vài nước chỉ khác nhau do phong cấp -> đã lọc; còn lại là nhập nhằng thật
      const key = (m) => m.from + m.to;
      const uniq = [...new Map(ms.map((m) => [key(m), m])).values()];
      if (uniq.length === 1) return { ok: true, move: { from: uniq[0].from, to: uniq[0].to, promotion: uniq[0].promotion || undefined } };
      return { ok: false, reason: 'ambiguous', to: c.to, options: uniq.map((m) => ({ from: m.from, to: m.to, piece: m.piece, say: describe(m, uniq) })) };
    }
    // không có nước nào: gõ 1 ô -> chọn quân nếu là quân của mình
    if (only && game) {
      const p = game.pieceAt(c.to);
      const myColor = game.chess.turn();
      if (p && p.color === myColor) {
        const targets = legal.filter((m) => m.from === c.to).map((m) => m.to);
        if (targets.length) return { ok: false, reason: 'select', from: c.to, targets: [...new Set(targets)] };
        return { ok: false, reason: 'stuck', sq: c.to };
      }
      return { ok: false, reason: 'empty', sq: c.to };
    }
    illegalText = illegalText || (c.castle ? 'nhập thành' : (c.from ? c.from + c.to : (c.piece ? NAMES[c.piece] + ' ' : '') + c.to));
  }
  return { ok: false, reason: 'illegal', text: illegalText || tokens.join(' ') };
}

function parseChessMove(raw, game, sel) {
  const base = cleanText(raw);
  if (!base) return { ok: false, reason: 'none' };
  const legal = game.legalMoves();
  // A: bỏ hẳn dấu @ (@@e4 -> e4)   B: coi @abc là nhắc tên người khác
  const variants = [base.replace(/@+/g, ' '), base.replace(/@\S+/g, ' ')];
  let best = null;
  for (const v of variants) {
    const r = tryText(v, legal, sel, game);
    if (!r) continue;
    if (r.ok) return r;
    if (!best || (best.reason === 'illegal' && r.reason !== 'illegal')) best = r;
  }
  if (best) return best;
  // dự phòng: câu ngắn có đúng 1-2 ô cờ ("hay quá e4 nhé")
  const flat = stripDiacritics(base.replace(/@+/g, ' '));
  const squares = [...flat.matchAll(new RegExp(`(?<![a-z0-9])(${SQ})(?![a-z0-9])`, 'g'))].map((m) => m[1]);
  const words = flat.split(/\s+/).filter(Boolean);
  if (words.length <= 5 && squares.length >= 1 && squares.length <= 2) {
    const r = tryText(squares.join(' '), legal, sel, game);
    if (r) return r;
  }
  return { ok: false, reason: 'none' };
}

/** Trả về 'reset' | 'surrender' | 'extend' | null */
function parseCommand(raw) {
  const t = stripDiacritics(cleanText(raw)).replace(/@+/g, ' ').trim();
  // xin thêm giờ: "!them", "!themgio", hoặc viết thường "thêm giờ", "xin thêm giờ ạ"
  if (/^(?:xin |cho |cho minh |cho em )?them (?:gio|thoi gian)(?![a-z])/.test(t)) return 'extend';
  const m = t.match(/^!\s*([a-z]+)(?:\s+([a-z]+))?/);
  if (!m) return null;
  const words = [m[1], m[1] + (m[2] || '')];
  if (words.some((w) => ['reset', 'lammoi', 'newgame'].includes(w))) return 'reset';
  if (words.some((w) => ['dauhang', 'surrender', 'giveup', 'thua'].includes(w))) return 'surrender';
  if (words.some((w) => ['diem', 'top', 'hang', 'rank', 'xephang', 'diemcuatoi'].includes(w))) return 'rank';
  if (words.some((w) => ['them', 'themgio', 'themthoigian', 'extend', 'more'].includes(w))) return 'extend';
  return null;
}

module.exports = { parseChessMove, parseCommand, cleanText, stripDiacritics, PIECE_NAMES: NAMES };
