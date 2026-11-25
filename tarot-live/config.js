'use strict';
/*
 * CÀI ĐẶT GAME TAROT LIVE
 * Mở file này bằng Notepad nếu muốn đổi số. Phần lớn cài đặt có thể đổi ngay ở bảng điều khiển (không cần sửa file).
 * ID TikTok KHÔNG cần sửa ở đây: file CHAY-GAME.bat sẽ hỏi và lưu vào file ten-tiktok.txt.
 */
const fs = require('fs');
const path = require('path');

function readTextFile(name) {
  try {
    return fs.readFileSync(path.join(__dirname, name), 'utf8').replace(/^﻿/, '').trim();
  } catch (e) {
    return '';
  }
}

const fast = !!process.env.TAROT_FAST; // chỉ dùng khi kiểm tra tự động

module.exports = {
  // ===== KẾT NỐI TIKTOK =====
  tiktokUsername: readTextFile('ten-tiktok.txt').replace(/^@/, ''),
  signApiKey: readTextFile('euler-api-key.txt'), // không bắt buộc
  tikfinityUrl: 'ws://127.0.0.1:21213/', // dùng khi chạy với --tikfinity

  // ===== MÁY CHỦ =====
  host: '127.0.0.1',
  port: Number(process.env.TAROT_PORT) || 3002, // khác Caro (3000) để chạy cùng lúc được
  testApi: true, // cho phép tự gõ thử bình luận (xem HUONG-DAN.txt)
  fast,

  // ===== GIÁ TRỊ MẶC ĐỊNH (đổi ở bảng điều khiển cũng được, bảng sẽ lưu vào data/cai-dat.json) =====
  defaults: {
    title: 'Tarot LIVE',
    subtitle: 'Tương tác tốt nhất sẽ được xem 5 lá Tarot',
    defaultSpread: 1, // 1 = rút 1 lá | 3 = rút 3 lá (quá khứ - hiện tại - tương lai) | 5 = rút 5 lá (tình huống - nguyên nhân - trở ngại - lời khuyên - kết quả)
    allowThree: true, // cho khán giả xin "3 lá"
    allowFive: true, // cho khán giả xin "5 lá" (mỗi lượt khoảng 1,5 phút)
    reverseChance: 30, // % lá bị ngược (0 = không có lá ngược)
    userCooldown: fast ? 0 : 90, // giây: 1 người phải chờ bấy nhiêu giây mới được xin lượt nữa (0 = không giới hạn)
    maxQueue: 25, // hàng chờ tối đa
    readSpeed: 'normal', // slow | normal | fast  (tốc độ chuyển lá, theo độ dài lời đọc)
    autoDraw: false, // không ai xin thì tự rút "thông điệp cho cả phòng" để màn hình không đứng yên
    autoIdleSeconds: fast ? 3 : 45,
    giftPriority: false, // người xin lượt mà từng tặng quà được xếp lên trước (tắt mặc định)
    voiceOn: true,
    voiceVolume: 1,
    // 2 giọng: ĐIỀU PHỐI (mời người xem, chia / lật bài, đọc tên lá) và NGƯỜI ĐỌC TAROT (chào, đọc ý nghĩa từng lá, tổng kết, lời chúc)
    voiceName: '', // giọng điều phối; để trống = tự chọn giọng nam tiếng Việt (ví dụ Microsoft NamMinh)
    voiceRate: 1.0, // tốc độ điều phối
    voicePitch: 1.0,
    readerVoice: '', // giọng người đọc Tarot; để trống = tự chọn giọng nữ tiếng Việt (ví dụ Microsoft HoaiMy)
    readerRate: 0.9, // người đọc Tarot: chậm, trầm
    readerPitch: 0.95,
    announceText: '',
    announceEvery: 0, // phút (0 = tắt)
    paused: false, // tạm ngưng nhận lượt mới
    minScore: fast ? 1 : 3, // điểm tương tác tối thiểu để được chọn (bình luận 1 điểm, !bai 3, chia sẻ 8, follow 6, quà 4)
    askInfo: true, // người được chọn phải bình luận họ tên, ngày/tháng/năm sinh, chuyện muốn xem
    collectSeconds: fast ? 4 : 60, // thời gian chờ người đó bình luận
    aiProvider: 'off', // off | claude | gemini (cần file ai-api-key.txt)
    aiModel: '', // để trống = dùng mẫu mặc định
    aiTimeout: 9, // giây chờ AI, quá hạn thì dùng lời đọc viết sẵn
  },
};
