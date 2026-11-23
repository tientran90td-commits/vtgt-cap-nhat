/*
 * GIAO DIỆN ĐỔI THEO TỪNG VÁN: màu bàn cờ, màu phòng 3D và dáng (màu tóc, áo) 2 nhân vật.
 * File này chỉ chứa DANH SÁCH MÀU và hàm áp dụng. Muốn thêm kiểu mới: thêm 1 mục vào THEMES / BOYS / GIRLS.
 * Cách chọn: ván số n dùng kiểu (n*3) % 8 cho bàn + phòng, (n*5) % 8 cho nhân vật nam, (n*7) % 8 cho nhân vật nữ
 * (cộng thêm 1 số lệch ngẫu nhiên mỗi lần mở trang) nên 2 ván liền nhau luôn khác nhau.
 * Quân X (đỏ) và O (xanh) giữ nguyên màu để luôn dễ nhìn.
 */
import { setBoardPalette } from './board.js';

export const THEMES = [
  {
    name: 'Gỗ cổ điển',
    board: { wood: ['#cf955a', '#a8692f'], label: '#2a1608' },
    room: { bg: 0x101626, wall: 0x1b2238, rug: 0x6b2230, ring: 0xd9a441, seat: 0x7a1f2e, table: ['#8a5a34', '#6b4122'], frame3d: 0x4a2a12 },
  },
  {
    name: 'Xanh lá',
    board: { wood: ['#e6cf8a', '#bfa05a'], label: '#3a2a08' },
    room: { bg: 0x0f1f18, wall: 0x17302a, rug: 0x1f4d3a, ring: 0xe3c26b, seat: 0x2f5d46, table: ['#7a6a44', '#5c4e30'], frame3d: 0x3a4a2a },
  },
  {
    name: 'Đại dương',
    board: { wood: ['#a8d5c2', '#6fae96'], label: '#10372c' },
    room: { bg: 0x0b1a2c, wall: 0x12304d, rug: 0x1d4f7a, ring: 0xbfe3ff, seat: 0x2a6aa0, table: ['#7a8fa0', '#5a6f80'], frame3d: 0x2a3f55 },
  },
  {
    name: 'Hồng đào',
    board: { wood: ['#b5cfe6', '#7fa3c7'], label: '#10253a' },
    room: { bg: 0x2a1420, wall: 0x4a2335, rug: 0x8a3a5a, ring: 0xffd1dc, seat: 0xb04a6a, table: ['#b88a7a', '#8f6658'], frame3d: 0x6a3347 },
  },
  {
    name: 'Tím mộng mơ',
    board: { wood: ['#f1c9d3', '#d79aae'], label: '#4a1a2a' },
    room: { bg: 0x15102a, wall: 0x2a2150, rug: 0x4b3a8a, ring: 0xd9c2ff, seat: 0x6a4ab0, table: ['#8a78a8', '#6a5a88'], frame3d: 0x3a2e60 },
  },
  {
    name: 'Đá xám',
    board: { wood: ['#d4c6ea', '#a58fcc'], label: '#2a1a4a' },
    room: { bg: 0x15171c, wall: 0x262a33, rug: 0x444b5a, ring: 0xd8dde6, seat: 0x596073, table: ['#8e949e', '#6e747e'], frame3d: 0x3a3f48 },
  },
  {
    name: 'Ngọc lam',
    board: { wood: ['#d5d8de', '#9aa1ad'], label: '#1c2230' },
    room: { bg: 0x0a1d1d, wall: 0x123a3a, rug: 0x1c5f5c, ring: 0xf0d98a, seat: 0x2f8a85, table: ['#7a9a8a', '#5a7a6a'], frame3d: 0x24504c },
  },
  {
    name: 'Đỏ rượu vang',
    board: { wood: ['#f3d9a8', '#d9a15c'], label: '#3a2208' },
    room: { bg: 0x1f0f12, wall: 0x3a1a20, rug: 0x7a2a34, ring: 0xe8b86a, seat: 0x9a3a44, table: ['#9a6a54', '#7a4a38'], frame3d: 0x5a2a2a },
  },
];

// hair = màu tóc, hairLight = màu bóng tóc, cloth = áo, accent = khăn / nơ / điểm nhấn
export const BOYS = [
  { hair: 0x14161f, hairLight: 0x6a78b8, cloth: 0xeef2f8, accent: 0x35c6a0 },
  { hair: 0xdfe6f0, hairLight: 0xffffff, cloth: 0x9fc5e8, accent: 0xffd166 },
  { hair: 0x1a1224, hairLight: 0x8a6ad0, cloth: 0x6e5ab0, accent: 0xf2d675 },
  { hair: 0x2a2f3a, hairLight: 0x8fa0c8, cloth: 0x2f6f6a, accent: 0xe8f0ff },
  { hair: 0x3a1e14, hairLight: 0xb98a5a, cloth: 0xe8d9b0, accent: 0xb03a2e },
  { hair: 0x0e1a2e, hairLight: 0x5a90d8, cloth: 0xc8d6ea, accent: 0x4ad1c8 },
  { hair: 0xc9ced8, hairLight: 0xffffff, cloth: 0x30364a, accent: 0xffd23f },
  { hair: 0x2a1a3a, hairLight: 0xa88be0, cloth: 0xf4e9ff, accent: 0x9a7ae0 },
];
export const GIRLS = [
  { hair: 0x1b1b2c, hairLight: 0x8a8fc8, cloth: 0xf6f8fc, accent: 0x6fc3ff },
  { hair: 0xe0709a, hairLight: 0xffb3cf, cloth: 0xffeef3, accent: 0xb066ff },
  { hair: 0xe8c45a, hairLight: 0xfff0a8, cloth: 0xbfe0f5, accent: 0xff7fa8 },
  { hair: 0xcfdcf0, hairLight: 0xffffff, cloth: 0xe3ecfa, accent: 0xffb3b3 },
  { hair: 0x4a2a1a, hairLight: 0xb9835a, cloth: 0xffd9c9, accent: 0xffe08a },
  { hair: 0x2fa58a, hairLight: 0xa8f0da, cloth: 0xe6faf3, accent: 0xf28cb1 },
  { hair: 0x6a3fa0, hairLight: 0xc2a0f0, cloth: 0xe3d3f7, accent: 0x4ad1c8 },
  { hair: 0xd2691e, hairLight: 0xffb36b, cloth: 0xfff3e0, accent: 0x7fb0ff },
];

const SHIFT = Math.floor(Math.random() * 8); // lệch ngẫu nhiên mỗi lần mở trang
const mod = (n) => ((n % 8) + 8) % 8;

/** Chọn kiểu cho ván số gameNo. forced = số 0..7 để ép 1 kiểu (vd ?theme=3 trên địa chỉ trang). */
export function themeForGame(gameNo, forced = null) {
  if (forced !== null && forced >= 0) {
    const i = mod(forced);
    return { index: i, name: THEMES[i].name, ...THEMES[i], X: BOYS[i], O: GIRLS[i] };
  }
  const n = Number(gameNo) || 0;
  const i = mod(n * 3 + SHIFT);
  return { index: i, name: THEMES[i].name, ...THEMES[i], X: BOYS[mod(n * 5 + SHIFT * 3)], O: GIRLS[mod(n * 7 + SHIFT * 5)] };
}

/** Kiểu cố định (không đổi): Gỗ cổ điển + 2 nhân vật gốc. */
export function classicTheme() {
  return { index: 0, name: THEMES[0].name, ...THEMES[0], X: BOYS[0], O: GIRLS[0] };
}

/** Áp dụng lên bàn cờ 2D (boardView) và cảnh 3D (scene). */
export function applyTheme(theme, boardView, scene) {
  setBoardPalette({ ...theme.board, skin: theme.skin || null });
  if (boardView && boardView.setTheme) boardView.setTheme();
  if (scene && scene.setTheme) scene.setTheme(theme);
}
