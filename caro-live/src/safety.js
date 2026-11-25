/*
 * AN TOÀN NỘI DUNG KHI LIVE TIKTOK (module riêng, không đụng tới phần chơi game).
 *  - sanitizeName: tên người xem (nickname TikTok) hiện lên màn hình và được MC đọc to -> bỏ link, che từ thô tục.
 *  - checkAnnouncement: thông báo của chủ phòng không được dẫn người xem ra ngoài TikTok (link, Zalo, Facebook, số điện thoại...)
 *    hay chứa từ thô tục (TikTok không cho LIVE có mục đích chính là đưa người xem đi nơi khác).
 */

const L = '\\p{L}';
// từ thô tục / nhạy cảm: chỉ khớp khi đứng riêng thành 1 từ (tránh bắt nhầm như "đụng", "admin")
const BAD_WORDS = new RegExp(
  `(?<![${L}\\d])(` +
    [
      'địt', 'đụ', 'đéo', 'cặc', 'lồn', 'buồi', 'cứt', 'đĩ', 'mẹ mày', 'con chó', 'thằng chó', 'óc chó',
      'đm+', 'dmm+', 'dcm', 'dkm', 'vcl', 'vkl', 'clgt', 'đcm', 'đkm', 'ditme', 'ditmemay',
      'fuck\\w*', 'shit\\w*', 'bitch\\w*', 'porn\\w*', 'sex', 'xxx', 'nigg\\w*', 'pussy',
    ].join('|') +
    `)(?![${L}\\d])`,
  'iu'
);
const LINK = /https?:\/\/|www\.|\b[a-z0-9-]+\.(com|vn|net|org|me|ly|io|xyz|club|top|info|tv|app)\b|t\.me\/|bit\.ly/i;
const SOCIAL = /\b(zalo|facebook|fb\.com|telegram|messenger|whatsapp|viber|instagram|shopee|lazada|youtube|inbox|ib mình|liên hệ|link bio|mua hàng|đặt hàng|nhận quà|kiếm tiền|việc làm|đầu tư|nạp tiền|cá cược|nhà cái|casino|sàn|crypto|tiền ảo)\b/i;
const PHONE = /(?:\+?84|0)[\s.\-]?\d(?:[\s.\-]?\d){8,9}/;

function norm(s) {
  return String(s || '').normalize('NFC').replace(/[\u0000-\u001f\u007f​-‏‪-‮⁦-⁩]/g, '').replace(/\s+/g, ' ').trim();
}

function flagged(s) {
  return BAD_WORDS.test(s) || LINK.test(s) || PHONE.test(s.replace(/[\s.\-]/g, ''));
}

/** Tên hiển thị an toàn. id dùng để đặt tên thay thế khác nhau cho từng người. */
function sanitizeName(name, id = '') {
  const s = norm(name).slice(0, 30);
  if (s && !flagged(s)) return s;
  const tail = String(id || name || '0').replace(/\D/g, '').slice(-3) || String(Math.abs(hash(String(id || name || '0'))) % 1000);
  return 'Khán giả ' + tail.padStart(3, '0');
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
  if (BAD_WORDS.test(s)) return { ok: false, msg: 'Thông báo có từ thô tục, hãy sửa lại cho phù hợp với tiêu chuẩn LIVE.' };
  return { ok: true };
}

module.exports = { sanitizeName, checkAnnouncement, norm };
