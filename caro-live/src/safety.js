/*
 * AN TOÀN NỘI DUNG KHI LIVE TIKTOK (module riêng, không đụng tới phần chơi game).
 *  - sanitizeName: tên người xem (nickname TikTok) hiện lên màn hình và được MC đọc to -> bỏ link, che từ thô tục,
 *    quảng cáo nhà cái / cờ bạc / lừa đảo / nội dung người lớn / ma túy (TikTok: chủ phòng chịu trách nhiệm cả chữ hiện và tiếng đọc).
 *  - sanitizeChat: nội dung bình luận hiện trong bảng điều khiển / dòng tin -> che nếu vi phạm.
 *  - checkAnnouncement: thông báo của chủ phòng không được dẫn người xem ra ngoài TikTok (link, Zalo, Facebook, số điện thoại...),
 *    không kêu gọi tặng quà, không có từ thô tục / cờ bạc.
 *  - checkLine: kiểm tra 1 câu thoại MC do chủ phòng tự sửa (data/thoai.json): cùng bộ luật như thông báo.
 */

const L = '\\p{L}';
// từ thô tục / nhạy cảm: chỉ khớp khi đứng riêng thành 1 từ (tránh bắt nhầm như "đụng", "admin")
const BAD_WORDS = new RegExp(
  `(?<![${L}\\d])(` +
    [
      'địt', 'đụ', 'đéo', 'cặc', 'lồn', 'buồi', 'cứt', 'đĩ', 'mẹ mày', 'con chó', 'thằng chó', 'óc chó', 'chó đẻ', 'đồ chó', 'súc vật', 'khốn nạn',
      'đm+', 'dmm+', 'dcm', 'dkm', 'vcl', 'vkl', 'clgt', 'đcm', 'đkm', 'cmm', 'cmn', 'ditme', 'ditmemay', 'dit me', 'dit con me', 'du ma', 'du me', 'con cac', 'concac', 'cai lon', 'cailon', 'đ\\.m', 'đ\\s?m\\s?m', 'd\\.m\\.?',
      'fuck\\w*', 'shit\\w*', 'bitch\\w*', 'porn\\w*', 'sex', 'xxx', 'nigg\\w*', 'pussy', 'cunt', 'whore', 'slut', 'faggot', 'retard\\w*', 'rape\\w*',
      'nazi', 'hitler', 'isis', 'kkk',
    ].join('|') +
    `)(?![${L}\\d])`,
  'iu'
);
// quảng cáo cờ bạc / cá độ / nhà cái (so khớp trên chữ đã bỏ dấu)
const GAMBLING = /(?<![a-z0-9])(nha ?cai|ca ?cuoc|ca ?do|danh ?de|lo ?de|tai ?xiu|no ?hu|xoc ?dia|ban ?ca|bau ?cua ?an ?tien|game ?bai ?doi ?thuong|doi ?thuong|casino|sbobet|[a-z]*\d{2,3}bet|bet\d{2,3}|w88|fb88|m88|v9bet|kubet|hitclub|go88|sunwin|rikvip|b52club|jun88|789club|789bet|vn88|12bet|bong88|slot ?game|nohu|xosoo?|soi ?cau)(?![a-z0-9])/;
// lừa đảo / kiếm tiền / dẫn ra ngoài (trong TÊN và bình luận)
const SCAM = /(?<![a-z0-9])(kiem ?tien|viec ?lam ?online|cong ?tac ?vien|nhiem ?vu ?online|dau ?tu|forex|crypto|tien ?ao|vay ?tien|rut ?tien|nap ?tien|hoa ?hong ?cao|zalo|telegram|tele ?:|inbox|ib ?minh|lien ?he)(?![a-z0-9])/;
// nội dung người lớn / chất cấm trong tên
const ADULT = /(?<![a-z0-9])(phim ?sex|gai ?goi|nude|lo ?hang|show ?hang|sex|18\+|ma ?tuy|thuoc ?lac|can ?sa|heroin|cocaine|bay ?lac)(?![a-z0-9])/;

const LINK = /https?:\/\/|www\.|\b[a-z0-9-]+\.(com|vn|net|org|me|ly|io|xyz|club|top|info|tv|app)\b|t\.me\/|bit\.ly/i;
const SOCIAL = /\b(zalo|facebook|fb\.com|telegram|messenger|whatsapp|viber|instagram|shopee|lazada|youtube|inbox|ib mình|liên hệ|link bio|mua hàng|đặt hàng|nhận quà|kiếm tiền|việc làm|đầu tư|nạp tiền|cá cược|nhà cái|casino|sàn|crypto|tiền ảo)\b/i;
const PHONE = /(?:\+?84|0)[\s.\-]?\d(?:[\s.\-]?\d){8,9}/;

// Câu KÊU GỌI / ĐỔI CHÁC bằng quà tặng (TikTok coi là "gift baiting" / điều kiện hoá nội dung bằng quà).
// Câu CẢM ƠN ("đã tặng {qua}") không bị bắt.
const GIFT_ASK = new RegExp(
  [
    '(hãy|xin|mời|nhớ|nhanh tay|cứ|mau|đi|nào)\\s+(tặng|gửi|thả|ban|nạp)\\s+(quà|lễ vật|gift|hoa hồng|rose|galaxy|lion|universe)',
    '(tặng|gửi|thả|ban)\\s+(quà|lễ vật|gift)\\s+(đi|nào|nhé|nha|để|cho tại hạ|giúp|giùm|mới|thì)',
    'để\\s+(được\\s+)?(lên đài|lên bàn|được chọn|có suất|giành suất|chơi|thắng)[^.!?\\n]{0,40}(tặng|quà|gift|lễ vật)',
    '(tặng|quà|gift|lễ vật)[^.!?\\n]{0,40}để\\s+(được\\s+)?(lên đài|lên bàn|được chọn|có suất|giành suất|chơi|thắng|chắc chắn)',
    'ủng hộ\\s+(tại hạ|mình|kênh|live|admin|streamer)',
    '\\bdonate\\b',
    'xin\\s+(quà|gift|lễ vật)',
    'quà\\s+(mới|thì)\\s+(được|có)',
  ].join('|'),
  'iu'
);

function norm(s) {
  return String(s || '').normalize('NFC').replace(/[\u0000-\u001f\u007f​-‏‪-‮⁦-⁩]/g, '').replace(/\s+/g, ' ').trim();
}

/** Bỏ dấu tiếng Việt, về chữ thường (để bắt "n.h.à c.á.i", "nha cai", "NHÀ CÁI"...). */
function fold(s) {
  return norm(s)
    .toLowerCase()
    .normalize('NFD')
    .replace(/[̀-ͯ]/g, '')
    .replace(/đ/g, 'd');
}

/** Gộp các ký tự tách rời kiểu "n h a c a i" / "n.h.a.c.a.i" để bắt tên cố tình viết rời. */
function squash(s) {
  return fold(s).replace(/[^a-z0-9+]/g, '');
}
const SQUASH_STEMS = /(nhacai|cacuoc|taixiu|nohu|xocdia|casino|sbobet|kubet|hitclub|sunwin|rikvip|bong88|jun88|789bet|789club|kiemtien|congtacvien|phimsex|gaigoi|thuoclac|matuy)/;

function gamblingOrScam(s) {
  const f = fold(s);
  return GAMBLING.test(f) || SCAM.test(f) || ADULT.test(f) || SQUASH_STEMS.test(squash(s));
}

function flagged(s) {
  return BAD_WORDS.test(s) || LINK.test(s) || PHONE.test(s.replace(/[\s.\-]/g, '')) || gamblingOrScam(s);
}

/** Tên hiển thị an toàn. id dùng để đặt tên thay thế khác nhau cho từng người. */
function sanitizeName(name, id = '') {
  const s = norm(name).slice(0, 30);
  if (s && !flagged(s)) return s;
  const tail = String(id || name || '0').replace(/\D/g, '').slice(-3) || String(Math.abs(hash(String(id || name || '0'))) % 1000);
  return 'Khán giả ' + tail.padStart(3, '0');
}

/** Bình luận hiện trong dòng tin / bảng điều khiển: vi phạm thì che. */
function sanitizeChat(text) {
  const s = norm(text).slice(0, 70);
  return flagged(s) ? '…' : s;
}

function hash(s) {
  let h = 0;
  for (let i = 0; i < s.length; i++) h = (h * 31 + s.charCodeAt(i)) | 0;
  return h;
}

/** Kiểm tra thông báo của chủ phòng. Trả về { ok:true } hoặc { ok:false, msg }. */
function checkAnnouncement(text) {
  const s = norm(text);
  if (LINK.test(s) || PHONE.test(s.replace(/[\s.\-]/g, '')) || SOCIAL.test(s)) {
    return { ok: false, msg: 'Thông báo không được kèm link, số điện thoại, Zalo/Facebook, mời mua hàng, kiếm tiền, đầu tư… (TikTok không cho LIVE dẫn người xem ra ngoài). Hãy sửa lại.' };
  }
  if (GIFT_ASK.test(s)) {
    return { ok: false, msg: 'Thông báo không được kêu gọi / đổi chác bằng quà tặng (kiểu "tặng quà để được chơi"). TikTok coi đó là gift baiting. Hãy sửa lại.' };
  }
  if (gamblingOrScam(s)) return { ok: false, msg: 'Thông báo có nội dung cờ bạc / kiếm tiền / người lớn, TikTok không cho phép. Hãy sửa lại.' };
  if (BAD_WORDS.test(s)) return { ok: false, msg: 'Thông báo có từ thô tục, hãy sửa lại cho phù hợp với tiêu chuẩn LIVE.' };
  return { ok: true };
}

/** Kiểm tra 1 câu thoại MC. Trả về null nếu ổn, hoặc lý do (chữ) nếu vi phạm. */
function checkLine(text) {
  const s = norm(text);
  if (!s) return null;
  if (LINK.test(s) || PHONE.test(s.replace(/[\s.\-]/g, '')) || SOCIAL.test(s)) return 'có link / số điện thoại / dẫn người xem ra ngoài TikTok';
  if (GIFT_ASK.test(s)) return 'kêu gọi hoặc đổi chác bằng quà tặng (gift baiting)';
  if (gamblingOrScam(s)) return 'có nội dung cờ bạc / kiếm tiền / người lớn';
  if (BAD_WORDS.test(s)) return 'có từ thô tục';
  return null;
}

module.exports = { sanitizeName, sanitizeChat, checkAnnouncement, checkLine, norm };
