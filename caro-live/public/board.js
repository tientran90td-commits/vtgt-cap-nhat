/*
 * BÀN CỜ 2D NHÌN TỪ TRÊN XUỐNG (nửa trên màn hình, giống ảnh mẫu).
 * Cũng cung cấp hàm vẽ nền bàn cờ dùng chung cho bàn cờ 3D (scene3d.js).
 * Quy ước: x = cột (A=0), y = hàng (hàng 1 = 0). Hàng 15 nằm trên cùng.
 */

import { paintSkinBase, drawLed } from './board-skins.js';

export const COLORS = { X: '#ff4d4f', O: '#2f9bff', gold: '#ffd54a' };

export function layout(px, size) {
  const label = px * 0.06;
  const pad = px * 0.015;
  const cell = (px - label - pad * 2) / size;
  return { px, size, cell, gx0: label + pad, gy0: pad, label, pad };
}

function rng(seed) {
  return function () {
    seed |= 0;
    seed = (seed + 0x6d2b79f5) | 0;
    let t = Math.imul(seed ^ (seed >>> 15), 1 | seed);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

// Bảng màu bàn cờ hiện tại (theme.js đổi qua setBoardPalette mỗi ván)
const PAL = { wood: ['#cf955a', '#a8692f'], label: '#2a1608', skin: null };
export function setBoardPalette(p) {
  if (!p) return;
  PAL.wood = p.wood.slice();
  PAL.label = p.label;
  PAL.skin = p.skin || null; // kiểu bàn cờ hoa văn + LED (board-skins.js); null = bàn gỗ
}
/** Kiểu bàn cờ đang dùng (null = bàn gỗ). Cảnh 3D dùng để vẽ đèn LED lên mặt bàn. */
export function currentSkin() {
  return PAL.skin;
}
export { drawLed };

export function paintWood(ctx, w, h, seed = 7, light = '#cf955a', dark = '#a8692f') {
  const g = ctx.createLinearGradient(0, 0, w, h);
  g.addColorStop(0, light);
  g.addColorStop(1, dark);
  ctx.fillStyle = g;
  ctx.fillRect(0, 0, w, h);
  const r = rng(seed);
  ctx.lineCap = 'round';
  for (let i = 0; i < 150; i++) {
    const y0 = r() * h;
    const amp = 2 + r() * 10;
    const len = w * (0.4 + r() * 0.7);
    const x0 = r() * w - len * 0.2;
    ctx.strokeStyle = r() > 0.5 ? `rgba(70,35,10,${0.05 + r() * 0.1})` : `rgba(255,220,170,${0.04 + r() * 0.08})`;
    ctx.lineWidth = 0.5 + r() * 2.2;
    ctx.beginPath();
    ctx.moveTo(x0, y0);
    const k = r() * 6;
    for (let x = 0; x <= len; x += 14) ctx.lineTo(x0 + x, y0 + Math.sin(x / 60 + k) * amp);
    ctx.stroke();
  }
}

/** Nền bàn cờ: gỗ + lưới + nhãn cột A-O, hàng 1-15 (chưa có quân). */
export function paintBoardBase(ctx, px, size) {
  const L = layout(px, size);
  if (PAL.skin) {
    paintSkinBase(ctx, px, size, L, PAL.skin);
    return L;
  }
  paintWood(ctx, px, px, 11, PAL.wood[0], PAL.wood[1]);
  const gw = L.cell * size;
  // khung lưới hơi sáng hơn
  ctx.fillStyle = 'rgba(255,230,190,0.10)';
  ctx.fillRect(L.gx0, L.gy0, gw, gw);
  ctx.strokeStyle = 'rgba(40,20,5,0.75)';
  ctx.lineWidth = Math.max(1, px / 700);
  ctx.beginPath();
  for (let i = 0; i <= size; i++) {
    const a = L.gx0 + i * L.cell;
    ctx.moveTo(a, L.gy0);
    ctx.lineTo(a, L.gy0 + gw);
    const b = L.gy0 + i * L.cell;
    ctx.moveTo(L.gx0, b);
    ctx.lineTo(L.gx0 + gw, b);
  }
  ctx.stroke();
  ctx.lineWidth = Math.max(2, px / 300);
  ctx.strokeRect(L.gx0, L.gy0, gw, gw);

  ctx.fillStyle = PAL.label;
  ctx.font = `800 ${Math.round(L.cell * 0.55)}px system-ui, Arial, sans-serif`;
  ctx.textAlign = 'center';
  ctx.textBaseline = 'middle';
  for (let x = 0; x < size; x++) {
    ctx.fillText(String.fromCharCode(65 + x), L.gx0 + (x + 0.5) * L.cell, L.gy0 + gw + L.label * 0.55);
  }
  ctx.textAlign = 'right';
  for (let y = 0; y < size; y++) {
    ctx.fillText(String(y + 1), L.gx0 - L.pad - 2, L.gy0 + (size - 1 - y + 0.5) * L.cell + 1);
  }
  return L;
}

export function cellCenter(L, x, y) {
  return { cx: L.gx0 + (x + 0.5) * L.cell, cy: L.gy0 + (L.size - 1 - y + 0.5) * L.cell };
}

function strokeMark(ctx, mark, cx, cy, r) {
  ctx.beginPath();
  if (mark === 'X') {
    const d = r * 0.78;
    ctx.moveTo(cx - d, cy - d);
    ctx.lineTo(cx + d, cy + d);
    ctx.moveTo(cx + d, cy - d);
    ctx.lineTo(cx - d, cy + d);
  } else {
    ctx.arc(cx, cy, r * 0.78, 0, Math.PI * 2);
  }
  ctx.stroke();
}

function drawMark(ctx, mark, cx, cy, r) {
  ctx.save();
  ctx.lineCap = 'round';
  ctx.shadowColor = 'rgba(0,0,0,0.35)';
  ctx.shadowBlur = r * 0.35;
  ctx.shadowOffsetY = r * 0.12;
  ctx.lineWidth = r * 0.34;
  if (PAL.skin) {
    // viền sáng mỏng quanh quân để nổi trên mọi nền hoa văn
    ctx.shadowColor = 'transparent';
    ctx.strokeStyle = 'rgba(255,255,255,0.92)';
    ctx.lineWidth = r * 0.34 + r * 0.2;
    strokeMark(ctx, mark, cx, cy, r);
    ctx.shadowColor = 'rgba(0,0,0,0.35)';
    ctx.lineWidth = r * 0.34;
  }
  if (mark === 'X') {
    ctx.strokeStyle = COLORS.X;
    const d = r * 0.78;
    ctx.beginPath();
    ctx.moveTo(cx - d, cy - d);
    ctx.lineTo(cx + d, cy + d);
    ctx.moveTo(cx + d, cy - d);
    ctx.lineTo(cx - d, cy + d);
    ctx.stroke();
  } else {
    ctx.strokeStyle = COLORS.O;
    ctx.beginPath();
    ctx.arc(cx, cy, r * 0.78, 0, Math.PI * 2);
    ctx.stroke();
  }
  ctx.restore();
}

export class BoardView {
  constructor(canvas, size = 15) {
    this.canvas = canvas;
    this.ctx = canvas.getContext('2d');
    this.size = size;
    this.px = 0;
    this.base = null;
    this.L = null;
    this.ledOn = true; // đèn LED sáng ở đường kẻ + vệt sáng ánh gương (chỉ có khi dùng kiểu bàn cờ hoa văn)
  }

  resize(cssPx) {
    const dpr = Math.min(window.devicePixelRatio || 1, 2);
    const px = Math.max(64, Math.round(cssPx * dpr));
    if (px === this.px) return;
    this.px = px;
    this.canvas.width = px;
    this.canvas.height = px;
    this.canvas.style.width = cssPx + 'px';
    this.canvas.style.height = cssPx + 'px';
    this.base = document.createElement('canvas');
    this.base.width = px;
    this.base.height = px;
    this.L = paintBoardBase(this.base.getContext('2d'), px, this.size);
  }

  /** Gọi sau setBoardPalette: vẽ lại nền bàn cờ theo màu mới. */
  setTheme() {
    if (!this.base) return;
    this.L = paintBoardBase(this.base.getContext('2d'), this.px, this.size);
  }

  /** view = { moves, last, winLine } (đã đồng bộ với cử động nhân vật) */
  draw(view, t = 0) {
    if (!this.base) return;
    const ctx = this.ctx;
    const L = this.L;
    ctx.drawImage(this.base, 0, 0);
    if (PAL.skin && this.ledOn) drawLed(ctx, L, PAL.skin, t);

    // ô nước đi gần nhất
    if (view.last) {
      const { cx, cy } = cellCenter(L, view.last.x, view.last.y);
      const a = 0.35 + 0.25 * Math.sin(t * 5);
      ctx.fillStyle = `rgba(255,213,74,${a})`;
      ctx.fillRect(cx - L.cell / 2, cy - L.cell / 2, L.cell, L.cell);
    }
    if (view.winLine) {
      ctx.fillStyle = 'rgba(255,213,74,0.45)';
      for (const c of view.winLine) {
        const p = cellCenter(L, c.x, c.y);
        ctx.fillRect(p.cx - L.cell / 2, p.cy - L.cell / 2, L.cell, L.cell);
      }
    }
    for (const m of view.moves) {
      const p = cellCenter(L, m.x, m.y);
      drawMark(ctx, m.m, p.cx, p.cy, L.cell * 0.4);
    }
    if (view.winLine && view.winLine.length > 1) {
      const a = cellCenter(L, view.winLine[0].x, view.winLine[0].y);
      const b = cellCenter(L, view.winLine[view.winLine.length - 1].x, view.winLine[view.winLine.length - 1].y);
      ctx.save();
      ctx.strokeStyle = `rgba(255,236,150,${0.75 + 0.25 * Math.sin(t * 8)})`;
      ctx.shadowColor = '#ffcf33';
      ctx.shadowBlur = L.cell * 0.6;
      ctx.lineWidth = L.cell * 0.16;
      ctx.lineCap = 'round';
      ctx.beginPath();
      ctx.moveTo(a.cx, a.cy);
      ctx.lineTo(b.cx, b.cy);
      ctx.stroke();
      ctx.restore();
    }
  }
}
