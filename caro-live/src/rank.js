'use strict';
/*
 * CẢNH GIỚI (RANK) - module riêng, chỉ tính toán, không lưu gì.
 * 6 cảnh giới: Phàm Nhân -> Luyện Khí -> Trúc Cơ -> Kết Đan -> Nguyên Anh -> Hóa Thần.
 * Rank tính theo TỔNG SỐ VÁN THẮNG của người chơi (đã lưu trong data/thanh-tich.json nên thoát ra vào lại vẫn còn).
 * Số ván thắng cần để lên từng cảnh giới sửa ở config.js (rankWins).
 */
const NAMES = ['Phàm Nhân', 'Luyện Khí', 'Trúc Cơ', 'Kết Đan', 'Nguyên Anh', 'Hóa Thần'];
const DEFAULT_STEPS = [3, 5, 7, 10, 15];

function cleanSteps(steps) {
  const out = [];
  for (let i = 0; i < NAMES.length - 1; i++) {
    const n = Math.floor(Number(steps && steps[i]));
    out.push(n >= 1 ? n : DEFAULT_STEPS[i]);
  }
  return out;
}

/** wins = tổng số ván thắng. Trả về { tier, name, into, need, max, wins }: đang ở cảnh giới tier, đã thắng `into`/`need` trận để lên cảnh giới kế. */
function rankInfo(wins, steps) {
  const st = cleanSteps(steps);
  let left = Math.max(0, Math.floor(Number(wins) || 0));
  let tier = 0;
  while (tier < st.length && left >= st[tier]) {
    left -= st[tier];
    tier++;
  }
  const max = tier >= st.length;
  return { tier, name: NAMES[tier], into: left, need: max ? 0 : st[tier], max, wins: Math.max(0, Math.floor(Number(wins) || 0)) };
}

module.exports = { NAMES, DEFAULT_STEPS, rankInfo };
