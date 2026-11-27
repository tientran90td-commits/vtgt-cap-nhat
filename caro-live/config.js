'use strict';
/*
 * CÀI ĐẶT GAME CARO LIVE
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
  host: readTextFile('data/app-wifi.txt') === '1' ? '0.0.0.0' : '127.0.0.1', // 0.0.0.0 = cho app Trợ Thủ nối qua WiFi (bật ở bảng điều khiển)
  port: Number(process.env.CARO_PORT) || 3000,
  testApi: true, // cho phép tự gõ thử bình luận bằng trình duyệt (xem HUONG-DAN.txt)

  // ===== LUẬT CỜ =====
  boardSize: 15, // bàn 15 x 15 (cột A-O, hàng 1-15)
  winLength: 5, // 5 quân liên tiếp là thắng
  blockBothEnds: false, // false = đủ 5 quân liên tiếp là thắng, kể cả bị chặn 2 đầu | true = bị chặn cả 2 đầu thì KHÔNG tính thắng
  oBan: false, // true = LUẬT "O CẤM 1 Ô": sau nước đầu của X, O gõ 1 ô để cấm (X không được đi vào đó đến hết ván), rồi O mới đi quân
  forbidX: false, // true = LUẬT CẤM cho quân đi trước (X): không được đánh vào ô tạo 3-3, 4-4 hoặc hàng dài hơn 5 (xem src/forbidden.js)

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
  turnSeconds: fast ? 6 : 45, // thời gian suy nghĩ cho mỗi nước đi
  extraTimeSeconds: 20, // người chơi gõ "!them" hoặc "thêm giờ" để xin thêm bấy nhiêu giây (cho lượt đang đến)
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
  // ===== LOGO TÊN KÊNH trên màn hình LIVE (đổi trong bảng điều khiển, không cần sửa file) =====
  logoOn: true,
  logoName: 'Trần Quỳnh Chi',
  logoSub: 'live chính',
  logoFont: 'default', // kiểu chữ: default | arial | segoe | tahoma | trebuchet | verdana | georgia | times | palatino | impact | comic | courier
  logoSize: 100, // cỡ chữ logo, % (100 = mặc định)
  logoColor: 'gold', // màu chữ: 'gold' (vàng kim) hoặc mã màu #rrggbb
  logoBold: true,
  logoItalic: false,
  logoFrame: true, // khung nền mờ + viền quanh logo
  showCellLabels: true, // ghi tọa độ (A1, H8, O15...) mờ trong từng ô vuông để người xem biết gõ gì
  themeAuto: true, // mỗi ván đổi màu bàn cờ, màu phòng, tóc/áo 2 nhân vật
  crowdMax: 10, // số khán giả (tên + ảnh đại diện) hiện thành nhân vật đứng quanh phòng, 0 = tắt
  boardSkin: 'auto', // kiểu bàn cờ: 'auto' = mỗi ván 1 kiểu | 'wood' = bàn gỗ | rong-vang, thanh-long, bach-ho, chu-tuoc, huyen-vu, cong-nghe, neon-tim, thien-ha, vu-tru (vũ trụ, có sao băng)
  // CẢNH GIỚI (rank): số ván thắng cần để lên từng bậc: Phàm Nhân->Luyện Khí->Trúc Cơ->Kết Đan->Nguyên Anh->Hóa Thần
  rankWins: [2, 4, 6, 8, 12],
  rankLossPenalty: 'tier', // thua = ĐỘ KIẾP THẤT BẠI: 'tier' = mất hết điểm của cảnh giới đang đứng (Kết Đan 4 điểm -> Kết Đan 0 điểm, giữ cảnh giới) | 'all' = mất sạch về Phàm Nhân | số (vd 1 = trừ 1 điểm) | 0 = thua không mất điểm
  rankPromoBonus: 0, // (tùy chọn) vừa lên cảnh giới mới được tặng sẵn bấy nhiêu điểm để thua ngay 1 ván không bị tụt liền. Mặc định 0: thắng +1, thua -1 đúng như nhau
  rankBoardRows: 4, // số người hiện trên bảng rank
  celebrateOn: true, // có người thắng -> phát video ăn mừng (mỗi trận bốc ngẫu nhiên 1 trong các video ở public/media, xem public/celebrate.js): có tiếng ngay, vài giây sau mới hiện hình thế chỗ 2 nhân vật
  celebrateMinSeconds: Number(process.env.CARO_CELEB_MIN) || (fast ? 0 : 33), // màn hình kết quả giữ ít nhất bấy nhiêu giây để video chạy hết (video dài nhất 15 giây + vài giây quân cuối còn đang đặt xuống + thời gian MC đọc lời chúc mừng SAU video)
  ledOn: true, // đèn LED chạy ở đường kẻ bàn cờ
  // Đến lượt mà người chơi chưa bình luận gì sau bấy nhiêu giây -> biển báo nhấp nháy để gây chú ý (0 = tắt).
  idleHintSeconds: fast ? 0 : 12,

  // ===== TIẾNG TÍCH TẮC ĐỒNG HỒ =====
  clockSeconds: 15, // người chơi còn bấy nhiêu giây thì bắt đầu kêu tích tắc (0 = tắt)

  // ===== NHẮC FOLLOW / CHIA SẺ =====
  reminderSeconds: process.env.CARO_FAST ? 0 : 150, // cứ bấy nhiêu giây nhắc 1 lần (0 = tắt)

  // ===== ĐIỂM TƯƠNG TÁC (dùng để chọn người chơi) =====
  points: {
    // Thứ tự điểm: QUÀ > FOLLOW > CHIA SẺ > THẢ TIM. Quà càng đắt càng nhiều điểm (tăng chậm dần theo giá trị quà). Mặc định KHÔNG giới hạn điểm (các số cap = 0).
    comment: 1, // mỗi bình luận
    commentCooldownSeconds: 3, // chống spam: bình luận cách nhau ít nhất bấy nhiêu giây mới tính điểm
    like: 1, // mỗi lượt thả tim
    likeMaxPerEvent: 0, // tối đa mỗi lần bấm tim liên tục (0 = không giới hạn)
    likeCapPerRound: 0, // tối đa bấy nhiêu điểm từ thả tim trong 1 vòng (0 = không giới hạn)
    share: 60, // chia sẻ LIVE (tính 1 lần mỗi vòng)
    follow: 100, // follow (tính 1 lần mỗi vòng)
    // Điểm của 1 món quà = giftBase + giftPerDiamond x (kim cương của món)^giftPower
    // Ví dụ với số mặc định: Hoa hồng (1💎) ~175 điểm, quà 30💎 ~340, quà 100💎 ~540, quà 1000💎 ~1700. Tặng x món thì nhân x.
    giftBase: 150,
    giftPerDiamond: 25,
    giftPower: 0.6,
    giftCapPerRound: 0, // tối đa bấy nhiêu điểm từ quà trong 1 vòng (0 = không giới hạn)
  },

};
