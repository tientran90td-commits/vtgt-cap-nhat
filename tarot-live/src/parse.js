'use strict';
/*
 * ĐỌC BÌNH LUẬN XIN BÓI BÀI. Ví dụ:  "!bai"  "!bai 3"  "bói bài tình yêu"  "xem tarot công việc 3 lá"  "rút bài"
 * Trả về { spread: 1|3|5|0, topic: 'general'|'love'|'work', sensitive: bool } hoặc null nếu không phải lời xin bài.
 * spread = 0 nghĩa là khán giả không nói rõ (dùng số lá mặc định ở cài đặt).
 */
function fold(s) {
  return String(s || '')
    .toLowerCase()
    .normalize('NFD')
    .replace(/[̀-ͯ]/g, '')
    .replace(/đ/g, 'd')
    .replace(/[^a-z0-9!\s]/g, ' ')
    .replace(/\s+/g, ' ')
    .trim();
}

const TRIGGER = /(^|\s)(!bai|!tarot|!boi|!rut|!xem)(\s|$)|\b(rut bai|boc bai|xem bai|boi bai|boi tarot|xem tarot|rut tarot|boc tarot|tarot)\b/;
const LOVE = /\b(tinh yeu|tinh duyen|tinh cam|crush|nguoi yeu|nguoi thuong|hen ho|ny|duyen)\b/;
const WORK = /\b(cong viec|su nghiep|viec lam|thang tien|hoc tap|thi cu|hoc hanh|cong danh|dinh huong)\b/;
const FIVE = /\b(5 la|nam la|5)\b/;
const THREE = /\b(3 la|ba la|3|ba|qua khu|tuong lai)\b/;
const ONE = /\b(1 la|mot la|1|mot)\b/;
// chủ đề không xem (sức khỏe, tiền bạc, sinh tử, pháp lý, cờ bạc...) -> vẫn rút bài nhưng chỉ đọc thông điệp chung
const SENSITIVE = /\b(benh|ung thu|suc khoe|chet|tu vong|mang thai|co bau|ly hon|toa an|tien bac|trung so|so de|lo de|xo so|ca do|chung khoan|dau tu|vay no)\b/;

function parseRequest(text) {
  const f = fold(text);
  if (!f || f.length > 80) return null;
  if (!TRIGGER.test(f)) return null;
  const topic = LOVE.test(f) ? 'love' : WORK.test(f) ? 'work' : 'general';
  const spread = FIVE.test(f) ? 5 : THREE.test(f) ? 3 : ONE.test(f) ? 1 : 0;
  return { spread, topic, sensitive: SENSITIVE.test(f) };
}

/** Đoán chủ đề từ 1 câu (dùng cho "chuyện muốn xem"). found = có nhắc tới chủ đề cụ thể. */
function detectTopic(text) {
  const f = fold(text);
  const topic = LOVE.test(f) ? 'love' : WORK.test(f) ? 'work' : 'general';
  return { topic, sensitive: SENSITIVE.test(f), found: topic !== 'general' || SENSITIVE.test(f) };
}

module.exports = { parseRequest, fold, detectTopic };
