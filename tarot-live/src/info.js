'use strict';
/*
 * THÔNG TIN NGƯỜI ĐƯỢC CHỌN: họ tên, ngày tháng năm sinh, chuyện muốn xem (người xem tự bình luận).
 * - parseInfo: tách từ bình luận. Ví dụ "Lan, 12/05/1995, tình duyên"  |  "Tên Minh sinh ngày 3 tháng 8 năm 1990 muốn xem công việc"
 * - zodiacOf / lifePath: cung hoàng đạo và số chủ đạo tính từ ngày sinh (tính toán đơn giản, mang tính giải trí).
 * Ngày sinh chỉ giữ trong bộ nhớ trong lúc bói (không lưu file, không hiện nguyên ngày trên màn hình).
 */
const { norm, checkAnnouncement, sanitizeName } = require('./safety');
const { fold, detectTopic } = require('./parse');

const LABEL = /^(ho va ten|ho ten|ten|toi la|minh la|em la|con la|name)\s*[:\-]?\s*/;

function validDate(d, m, y) {
  const now = new Date().getFullYear();
  if (!(y >= 1920 && y <= now) || !(m >= 1 && m <= 12) || !(d >= 1 && d <= 31)) return false;
  const t = new Date(Date.UTC(y, m - 1, d));
  return t.getUTCFullYear() === y && t.getUTCMonth() === m - 1 && t.getUTCDate() === d;
}

/** Tìm ngày sinh trong 1 đoạn chữ. Trả về { d, m, y, match } hoặc null. */
function findDate(text) {
  const t = String(text || '');
  const a = /(?<!\d)(\d{1,2})\s*[\/\-.]\s*(\d{1,2})\s*[\/\-.]\s*(\d{4})(?!\d)/.exec(t);
  const b = /(?<!\d)(\d{1,2})\s*(?:thang|tháng|th)\s*(\d{1,2})\s*(?:nam|năm|n)?\s*(\d{4})(?!\d)/i.exec(t.normalize('NFC'));
  for (const m of [a, b]) {
    if (!m) continue;
    const d = Number(m[1]);
    const mo = Number(m[2]);
    const y = Number(m[3]);
    if (validDate(d, mo, y)) return { d, m: mo, y, match: m[0] };
  }
  return null;
}

/**
 * Tách 1 bình luận. fallbackName: tên TikTok của người đó (dùng khi họ không ghi tên).
 * Trả về { name, dob, question, topic, sensitive } (trường nào không có thì null / '').
 */
function parseInfo(text, fallbackName = '') {
  let s = norm(text).slice(0, 220);
  const dob = findDate(s);
  if (dob) {
    const at = s.indexOf(dob.match);
    const before = s.slice(0, at).replace(/\s*(sinh\s*ngày|ngày\s*sinh|sinh\s*nhật|\bsn\b|\bsinh\b|\bngày\b)\s*[:\-]?\s*$/i, '');
    s = before + ' , ' + s.slice(at + dob.match.length);
  }
  const parts = s.split(/[,;|\n]+|\s+-\s+/).map((x) => x.trim()).filter(Boolean);
  let name = '';
  const rest = [];
  for (const p of parts) {
    const f = fold(p);
    const labelled = LABEL.test(f);
    const cleaned = labelled ? p.slice(p.length - f.replace(LABEL, '').length).trim() : p;
    const looksName = cleaned.length >= 2 && cleaned.length <= 32 && cleaned.split(/\s+/).length <= 5 && !/[?!]/.test(cleaned) && !/\d/.test(cleaned) && !detectTopic(cleaned).found;
    if (!name && (labelled || (looksName && !rest.length))) {
      name = cleaned.replace(/^(ten|họ tên|họ và tên|tôi là|mình là|em là|con là)\s*[:\-]?\s*/i, '').trim();
    } else rest.push(p);
  }
  let question = norm(rest.join(', ').replace(/[<>{}\[\]]/g, ' ').replace(/\d{1,2}\s*[\/\-.]\s*\d{1,2}\s*[\/\-.]\s*\d{4}/g, ' ')).replace(/^[\s,;.\-]+|[\s,;\-]+$/g, '').slice(0, 100);
  if (question && !checkAnnouncement(question).ok) question = ''; // có link / số điện thoại / từ thô tục -> bỏ
  const t = detectTopic(question);
  return {
    name: name ? sanitizeName(name, fallbackName) : '',
    dob: dob ? { d: dob.d, m: dob.m, y: dob.y } : null,
    question,
    topic: t.topic,
    sensitive: t.sensitive,
  };
}

/** Gộp nhiều lần bình luận của cùng 1 người. */
function mergeInfo(a, b) {
  return {
    name: a.name || b.name,
    dob: a.dob || b.dob,
    question: [a.question, b.question].filter(Boolean).join('. ').slice(0, 100),
    topic: a.topic !== 'general' ? a.topic : b.topic,
    sensitive: a.sensitive || b.sensitive,
  };
}

// ---------------------------------------------------------------- cung hoàng đạo
const ZODIAC = [
  // [tên, tháng bắt đầu, ngày bắt đầu, tính cách (gợi mở)]
  ['Ma Kết', 12, 22, 'kiên trì và có trách nhiệm'],
  ['Bảo Bình', 1, 20, 'độc lập và nhiều ý tưởng'],
  ['Song Ngư', 2, 19, 'nhạy cảm và giàu trí tưởng tượng'],
  ['Bạch Dương', 3, 21, 'nhiệt huyết và dám nghĩ dám làm'],
  ['Kim Ngưu', 4, 20, 'điềm đạm và yêu sự ổn định'],
  ['Song Tử', 5, 21, 'nhanh nhẹn và thích khám phá'],
  ['Cự Giải', 6, 21, 'dịu dàng và giàu tình cảm'],
  ['Sư Tử', 7, 23, 'tự tin và hào phóng'],
  ['Xử Nữ', 8, 23, 'tỉ mỉ và chu đáo'],
  ['Thiên Bình', 9, 23, 'hài hòa và yêu sự công bằng'],
  ['Bọ Cạp', 10, 23, 'sâu sắc và quyết liệt'],
  ['Nhân Mã', 11, 22, 'lạc quan và yêu tự do'],
];

function zodiacOf(dob) {
  if (!dob) return null;
  let cur = ZODIAC[0];
  for (const z of ZODIAC) if (dob.m > z[1] || (dob.m === z[1] && dob.d >= z[2])) cur = z;
  return { name: cur[0], trait: cur[3] };
}

// ---------------------------------------------------------------- số chủ đạo (thần số học)
const LIFE = {
  1: 'tiên phong, tự lập, thích dẫn đầu',
  2: 'hòa nhã, biết lắng nghe, giỏi kết nối',
  3: 'sáng tạo, vui vẻ, biết truyền cảm hứng',
  4: 'chắc chắn, thực tế, làm việc có nền nếp',
  5: 'ưa tự do, linh hoạt, thích trải nghiệm mới',
  6: 'quan tâm, có trách nhiệm, yêu gia đình',
  7: 'thích suy ngẫm, tìm hiểu, sống nội tâm',
  8: 'có tham vọng, quyết đoán, khả năng tổ chức',
  9: 'nhân hậu, rộng lượng, nghĩ cho cộng đồng',
  11: 'nhạy bén, giàu trực giác và cảm hứng',
  22: 'tầm nhìn lớn, biến ý tưởng thành việc thật',
};

function lifePath(dob) {
  if (!dob) return null;
  const sum = (n) => String(n).split('').reduce((a, c) => a + Number(c), 0);
  let n = sum(dob.d) + sum(dob.m) + sum(dob.y);
  while (n > 9 && n !== 11 && n !== 22) n = sum(n);
  return { n, trait: LIFE[n] };
}

/** Thông tin đã xử lý, an toàn để hiện lên màn hình (không có nguyên ngày sinh). */
function profile(info) {
  if (!info) return null;
  const z = zodiacOf(info.dob);
  const lp = lifePath(info.dob);
  return {
    name: info.name || '',
    zodiac: z ? z.name : '',
    zodiacTrait: z ? z.trait : '',
    lifeNo: lp ? lp.n : 0,
    lifeTrait: lp ? lp.trait : '',
    question: info.question || '',
  };
}

module.exports = { parseInfo, mergeInfo, findDate, zodiacOf, lifePath, profile };
