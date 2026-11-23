'use strict';
/*
 * ĐỌC BÌNH LUẬN
 * - parseMove: nhận ra tọa độ nước đi như j9, J9, j 9, 9j, "đi k6 nhé", @j9, @@j9 (có @ ở trước)...
 * - parseCommand: lệnh đặc biệt như !reset (chủ phòng), !dauhang (người chơi)
 */

function stripDiacritics(s) {
  return s.normalize('NFD').replace(/[̀-ͯ]/g, '').replace(/đ/g, 'd');
}

function cleanText(raw, keepAt = true) {
  return String(raw == null ? '' : raw)
    .normalize('NFKC') // chữ/số full-width (ｊ９) -> j9
    .replace(/[​-‏‪-‮⁠﻿]/g, '') // ký tự vô hình
    .toLowerCase()
    .replace(/https?:\/\/\S+/g, ' ') // bỏ link
    // "@j9", "@@j9", "@ k6": dấu @ thêm vào trước tọa độ (để bình luận không bị TikTok ẩn) -> giữ lại tọa độ
    .replace(keepAt ? /@+\s*(?=(?:[a-z]\s*[-.,:]?\s*\d{1,2}|\d{1,2}\s*[-.,:]?\s*[a-z])(?![a-z0-9]))/g : /(?!)/g, ' ')
    .replace(/@[^\s@]+/g, ' ') // bỏ @nhắc tên
    .replace(/\s+/g, ' ')
    .trim();
}

/**
 * Trả về { ok:true, x, y, label } hoặc { ok:false, reason:'none'|'many'|'range' }
 *  - x: cột 0..size-1 (A=0), y: hàng 0..size-1 (hàng 1 = 0)
 * Quy tắc để KHÔNG nhận nhầm:
 *  - Nếu cả bình luận chỉ là tọa độ (có thể kèm biểu tượng/“ạ”): nhận j9, j 9, j-9, 9j.
 *  - Nếu nằm trong câu dài: chỉ nhận dạng liền "j9" (chữ trước, số sau), tách riêng khỏi chữ khác.
 *  - Nếu câu có 2 tọa độ khác nhau -> bỏ qua (tránh đánh nhầm).
 */
function parseMove(raw, size = 15) {
  const r = parseText(cleanText(raw), size);
  // "@i7 j9": nếu hiểu @ là dấu thêm vào mà ra 2 tọa độ, thử coi @xxx là nhắc tên người khác
  if (!r.ok && r.reason === 'many') {
    const r2 = parseText(cleanText(raw, false), size);
    if (r2.ok) return r2;
  }
  // cách viết khác (chỉ thử khi cách thường không ra): "ca 6", "j chín", "hàng 9 cột j", "đánh j 9"...
  if (!r.ok && r.reason === 'none') {
    const sm = smartParse(raw, size);
    if (sm) return sm;
  }
  return r;
}

// ---- NHẬN DIỆN THÔNG MINH: cách gõ khác ngoài "j9" ----
const NUM_WORDS = {
  mot: 1, hai: 2, ba: 3, bon: 4, tu: 4, nam: 5, lam: 5, sau: 6, bay: 7, tam: 8, chin: 9,
  muoi: 10, 'muoi mot': 11, 'muoi mot ': 11, 'muoi hai': 12, 'muoi ba': 13, 'muoi bon': 14, 'muoi lam': 15, 'muoi nam': 15,
};
// cách đọc tên chữ cái kiểu Việt (chỉ nhận khi cả bình luận chỉ có "tên chữ + số")
const LETTER_NAMES = { be: 'b', xe: 'c', de: 'd', ep: 'f', ef: 'f', hat: 'h', di: 'j', ca: 'k', lo: 'l', mo: 'm', no: 'n' };
const NUM_RE = '(\\d{1,2}|muoi (?:mot|hai|ba|bon|lam|nam)|muoi|mot|hai|ba|bon|tu|nam|lam|sau|bay|tam|chin)';

function numberOf(tok) {
  if (/^\d+$/.test(tok)) return parseInt(tok, 10);
  return NUM_WORDS[tok] || 0;
}

function smartParse(raw, size) {
  const t = stripDiacritics(cleanText(raw));
  if (!t) return null;
  const letters = 'abcdefghijklmnopqrstuvwxyz'.slice(0, size);
  let letter = null;
  let row = null;
  let m;

  // a) "hàng 9 cột j" / "cột j dòng 9" / "col j row 9"
  const mc = t.match(/(?:^|\s)(?:cot|col|column)\s*([a-z])(?![a-z])/);
  const mr = t.match(new RegExp('(?:^|\\s)(?:hang|dong|row)\\s*' + NUM_RE + '(?![a-z0-9])'));
  if (mc && mr) {
    letter = mc[1];
    row = numberOf(mr[1]);
  } else if (
    // b) cả bình luận chỉ là "tên chữ + số": "ca 6", "di 9", "j chín", "j/9"
    (m = t.match(new RegExp('^[^a-z0-9]*([a-z]{1,3})\\s*[-.,:/_*]?\\s*' + NUM_RE + '[^a-z0-9]*$')))
  ) {
    const name = m[1];
    if (name.length === 1) letter = name;
    else if (LETTER_NAMES[name]) letter = LETTER_NAMES[name];
    if (letter) row = numberOf(m[2]);
  } else if (
    // c) có động từ + tọa độ cách ra: "đánh j 9 nhé", "đi k 6"
    (m = t.match(new RegExp('(?:^|\\s)(?:danh|di|dat|chon|vao|den|go|move|play|nuoc)\\s+([a-z])\\s*[-.,:]?\\s*(\\d{1,2})(?![a-z0-9])')))
  ) {
    letter = m[1];
    row = numberOf(m[2]);
  }

  if (!letter || !row) return null;
  const x = letters.indexOf(letter);
  if (x < 0) return null; // chữ cái ngoài bàn (p, q...) có thể chỉ là chữ thường, không báo lỗi
  if (row < 1 || row > size) return { ok: false, reason: 'range' };
  return { ok: true, x, y: row - 1, label: letter.toUpperCase() + row };
}

/**
 * Bình luận chỉ có MỘT nửa tọa độ: "j" hoặc "9" (người xem hay gõ tách làm 2 bình luận).
 * Trả về { kind:'letter', x } | { kind:'row', y } | null
 */
function parsePartial(raw, size = 15) {
  const t = cleanText(raw);
  const letters = 'abcdefghijklmnopqrstuvwxyz'.slice(0, size);
  let m = t.match(/^[^a-z0-9]*([a-z])[^a-z0-9]*$/);
  if (m && letters.includes(m[1])) return { kind: 'letter', x: letters.indexOf(m[1]), label: m[1].toUpperCase() };
  m = t.match(/^[^a-z0-9]*(\d{1,2})[^a-z0-9]*$/);
  if (m) {
    const r = parseInt(m[1], 10);
    if (r >= 1 && r <= size) return { kind: 'row', y: r - 1, label: String(r) };
  }
  return null;
}

function parseText(t, size) {
  if (!t) return { ok: false, reason: 'none' };

  const letters = 'abcdefghijklmnopqrstuvwxyz'.slice(0, size);
  const L = `[${letters}]`;
  const found = new Map();
  let outOfRange = false;

  const add = (letter, digits) => {
    const x = letters.indexOf(letter);
    const row = parseInt(digits, 10);
    if (x < 0 || !(row >= 1 && row <= size)) {
      outOfRange = true;
      return;
    }
    found.set(`${x},${row - 1}`, { x, y: row - 1, label: letter.toUpperCase() + row });
  };

  const whole = new RegExp(
    `^[^a-z0-9]*(?:(${L})\\s*[-.,:]?\\s*(\\d{1,2})|(\\d{1,2})\\s*[-.,:]?\\s*(${L}))[^a-z0-9]*$`
  );
  const w = t.match(whole);
  if (w) {
    if (w[1]) add(w[1], w[2]);
    else add(w[4], w[3]);
  } else {
    const tight = new RegExp(`(?<![a-z0-9])(${L})(\\d{1,2})(?![a-z0-9])`, 'g');
    for (const m of t.matchAll(tight)) add(m[1], m[2]);
  }

  if (found.size === 1) return { ok: true, ...[...found.values()][0] };
  if (found.size > 1) return { ok: false, reason: 'many' };
  return { ok: false, reason: outOfRange ? 'range' : 'none' };
}

/** Trả về 'reset' | 'surrender' | 'extend' | null */
function parseCommand(raw) {
  const t = stripDiacritics(cleanText(raw));
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

module.exports = { parseMove, parsePartial, parseCommand, cleanText, stripDiacritics };
