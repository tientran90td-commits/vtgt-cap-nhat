'use strict';
/*
 * CÀI ĐẶT GAME CỜ VUA LIVE
 * Mở file này bằng Notepad nếu muốn đổi số. Chỉ đổi số/chữ phía sau dấu ":" rồi lưu lại.
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

const fast = !!process.env.CARO_FAST; // chỉ dùng khi kiểm tra tự động

module.exports = {
  // ===== KẾT NỐI TIKTOK =====
  tiktokUsername: readTextFile('ten-tiktok.txt').replace(/^@/, ''),
  signApiKey: readTextFile('euler-api-key.txt'), // không bắt buộc (xem HUONG-DAN.txt)
  tikfinityUrl: 'ws://127.0.0.1:21213/', // dùng khi chạy với --tikfinity (nhận sự kiện từ TikFinity Desktop)

  // ===== MÁY CHỦ =====
  host: '127.0.0.1',
  port: Number(process.env.CARO_PORT) || 3000,
  testApi: true, // cho phép tự gõ thử bình luận bằng trình duyệt (xem HUONG-DAN.txt)

  // ===== LUẬT CỜ =====
  boardSize: 8, // cờ vua 8 x 8 (cột a-h, hàng 1-8)
  themeAuto: true, // mỗi ván đổi màu bàn cờ, màu phòng, tóc/áo 2 nhân vật (chống nhàm chán)
  showCellLabels: true, // ghi ký hiệu (a1, e4...) mờ mờ trong từng ô để người xem biết gõ gì

  // ===== CHỌN NGƯỜI CHƠI =====
  hostCanPlay: false, // chủ phòng có được vào bàn chơi không
  minPointsToPlay: 1, // cần ít nhất bấy nhiêu điểm tương tác mới được chọn
  winnerStays: true, // người thắng ở lại đấu tiếp với người tương tác cao nhất
  maxWinStreak: 3, // thắng liên tiếp bấy nhiêu ván thì phải nhường chỗ

  // ===== THỜI GIAN (giây) =====
  lobbySeconds: fast ? 4 : 25, // thời gian "đua tương tác" trước khi chọn người chơi (lần đầu / sau khi bấm Ván mới)
  autoNextGame: true, // true = hết ván tự sang ván kế tiếp, vòng chờ chọn người chơi được rút ngắn (nextLobbySeconds)
  nextLobbySeconds: fast ? 4 : 10, // thời gian chờ chọn người chơi cho các ván sau (khán giả đã tích điểm trong lúc xem)
  coinSeconds: fast ? 2 : 7, // thời gian tung đồng xu
  turnSeconds: fast ? 6 : 60, // thời gian suy nghĩ cho mỗi nước đi
  extraTimeSeconds: 30, // người chơi gõ "!them" hoặc "thêm giờ" để xin thêm bấy nhiêu giây (cho lượt đang đến)
  extraTimesPerGame: 1, // mỗi người được xin thêm giờ tối đa bấy nhiêu lần trong 1 ván (0 = tắt)
  resultSeconds: fast ? 3 : 14, // thời gian hiện kết quả trước khi sang ván mới
  maxTimeouts: 2, // hết giờ liên tiếp bấy nhiêu lần thì xử thua

  // ===== GIỌNG ĐỌC (đổi ở bảng điều khiển cũng được) =====
  voice: {
    on: true, // bật giọng đọc điều phối viên + trọng tài
    volume: 1, // 0 - 1
    talk: fast ? 'lively' : 'normal', // mức độ nói: 'quiet' = gần như im lặng | 'normal' = chưa vào trận thì chào/giải thích/cảm ơn, trong trận im lặng | 'lively' = thêm đọc từng nước đi
    readMoves: true, // đọc từng nước đi ("An đánh ca 6, đến lượt Bình") - chỉ khi mức nói là 'normal' hoặc 'lively'
    mcVoice: '', // tên giọng điều phối viên (để trống = tự chọn)
    refVoice: '', // tên giọng trọng tài (để trống = tự chọn)
    bigGiftDiamonds: 100, // quà từ bấy nhiêu kim cương trở lên được cảm ơn bằng câu "quà lớn"
    thanksDelayMs: 2500, // chờ chút để gộp quà liên tiếp (combo) rồi mới cảm ơn
    mcRate: null, // tốc độ đọc điều phối viên (0.6 - 1.5), null = tự động
    mcPitch: null, // cao độ điều phối viên (0.5 - 1.8), null = tự động
    refRate: null,
    refPitch: null,
  },

  // ===== ÂM THANH HIỆU ỨNG (tiếng đặt quân, 4 quân liền, thắng...) =====
  sfx: { on: true, volume: 0.7 },

  // ===== NHẠC NỀN (tự tạo nhạc nhẹ; hoặc bỏ file mp3 của bạn vào thư mục public\music) =====
  music: { on: true, volume: 0.3 },

  // ===== XÁC NHẬN BẰNG THẢ TIM =====
  // Sau khi chọn được người chơi, họ phải THẢ TIM trong bấy nhiêu giây để xác nhận sẽ chơi.
  // Ai không thả tim sẽ mất suất (bị trừ hết điểm) và người kế tiếp được mời thay. 0 = tắt.
  confirmSeconds: fast ? 0 : 20,

  // ===== BIỂN BÁO NHỎ Ở GÓC MÀN HÌNH =====
  // Ghi sẵn các điều cần thiết (gõ tọa độ, nếu bình luận bị ẩn thì thêm @, xin thêm giờ...). Không đọc thành tiếng.
  showSign: true,
  // Đến lượt mà người chơi chưa bình luận gì sau bấy nhiêu giây -> biển báo nhấp nháy để gây chú ý (0 = tắt).
  idleHintSeconds: fast ? 0 : 12,

  // ===== TIẾNG TÍCH TẮC ĐỒNG HỒ =====
  clockSeconds: 15, // người chơi còn bấy nhiêu giây thì bắt đầu kêu tích tắc (0 = tắt)

  // ===== NHẮC FOLLOW / CHIA SẺ =====
  reminderSeconds: process.env.CARO_FAST ? 0 : 150, // cứ bấy nhiêu giây nhắc 1 lần (0 = tắt)

  // ===== ĐIỂM TƯƠNG TÁC (dùng để chọn người chơi) =====
  points: {
    // Thứ tự điểm: QUÀ > FOLLOW > CHIA SẺ > THẢ TIM. Quà càng đắt càng nhiều điểm (nhưng tăng chậm dần để người thả tim chay vẫn có cơ hội).
    comment: 1, // mỗi bình luận
    commentCooldownSeconds: 3, // chống spam: bình luận cách nhau ít nhất bấy nhiêu giây mới tính điểm
    like: 1, // mỗi lượt thả tim
    likeMaxPerEvent: 15, // tối đa mỗi lần bấm tim liên tục
    likeCapPerRound: 120, // tối đa bấy nhiêu điểm từ thả tim trong 1 vòng (0 = không giới hạn)
    share: 60, // chia sẻ LIVE (tính 1 lần mỗi vòng)
    follow: 100, // follow (tính 1 lần mỗi vòng)
    // Điểm của 1 món quà = giftBase + giftPerDiamond x (kim cương của món)^giftPower
    // Ví dụ với số mặc định: Hoa hồng (1💎) ~175 điểm, quà 30💎 ~340, quà 100💎 ~540, quà 1000💎 ~1700. Tặng x món thì nhân x.
    giftBase: 150,
    giftPerDiamond: 25,
    giftPower: 0.6,
    giftCapPerRound: 4000, // tối đa bấy nhiêu điểm từ quà trong 1 vòng (0 = không giới hạn)
  },
};
