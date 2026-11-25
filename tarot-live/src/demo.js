'use strict';
/*
 * CHẾ ĐỘ THỬ (DEMO): khán giả ảo bình luận xin bói bài, tặng quà... để bạn xem game chạy mà không cần bật LIVE.
 * Chạy bằng file CHAY-THU-DEMO.bat
 */
const FAKE = [
  ['minhanh_98', 'Minh Anh 🌸'], ['tuan.kiet', 'Tuấn Kiệt'], ['hoaibao2003', 'Hoài Bảo'], ['bichtram', 'Bích Trâm'],
  ['quangvinh77', 'Quang Vinh'], ['thuyvy', 'Thúy Vy ✨'], ['duyphong', 'Duy Phong'], ['lanhuong', 'Lan Hương'],
  ['khanhlinh_', 'Khánh Linh'], ['trungkien', 'Trung Kiên'], ['phuongthao', 'Phương Thảo'], ['ngocmai', 'Ngọc Mai'],
];
const ASK = ['!bai', '!bai', '!bai 3', '!bai 5', 'bói bài tình yêu', 'xem tarot công việc', '!bai 3 lá tình duyên', 'rút bài đi ạ', '!tarot', '!bai học tập', '!bai sức khỏe'];
const CHAT = ['hay quá', 'xin chào cả nhà', 'lá này đúng ghê', 'mình cũng muốn rút', '🔥🔥', 'haha', 'cảm ơn bạn'];
const GIFTS = [['Hoa hồng', 1], ['Cà phê', 5], ['Trái tim', 10]];
const pick = (a) => a[Math.floor(Math.random() * a.length)];
const mk = ([id, name]) => ({ id, uniqueId: id, name, avatar: `/demo-avatar?n=${encodeURIComponent(name)}` });

function startDemo(hub, cfg, log, opts = {}) {
  const timers = [];
  const fast = !!cfg.fast;
  hub.setConnection('demo', 'CHẾ ĐỘ THỬ (khán giả ảo)');
  const loop = (fn, min, max) => {
    const run = () => {
      try {
        fn();
      } catch (e) {
        log('Lỗi demo:', e.message);
      }
      timers.push(setTimeout(run, (min + Math.random() * (max - min)) * (fast ? 0.1 : 1)));
    };
    timers.push(setTimeout(run, 1500));
  };
  loop(() => hub.onComment(mk(pick(FAKE)), pick(ASK)), 7000, 16000);
  loop(() => hub.onComment(mk(pick(FAKE)), pick(CHAT)), 3000, 8000);
  loop(() => {
    const g = pick(GIFTS);
    hub.onGift(mk(pick(FAKE)), { name: g[0], diamonds: g[1], count: 1 });
  }, 25000, 50000);
  return {
    stop() {
      for (const t of timers) clearTimeout(t);
      timers.length = 0;
    },
  };
}

module.exports = { startDemo };
