/*
 * BÀN CỜ VUA 2D NHÌN TỪ TRÊN XUỐNG (nửa trên màn hình).
 * Cũng cung cấp hàm vẽ nền bàn cờ dùng chung cho bàn cờ 3D (scene3d.js).
 * Quy ước: x = cột (a=0), y = hàng (hàng 1 = 0). Hàng 8 nằm trên cùng, quân trắng ở dưới.
 * Trong mỗi ô có ghi mờ ký hiệu (a1, e4...) để người xem biết gõ gì.
 */
import { FILES, sqXY, xySq, colorOf, boardFromMoves, kingSquare } from './chessmodel.js';
import { drawPiece } from './chesspiece2d.js';

export const COLORS = { X: '#ffd166', O: '#6aa8ff', gold: '#ffd54a' };
// Bảng màu bàn cờ hiện tại (theme.js đổi qua setBoardPalette mỗi ván)
const PAL = { light: '#ecd7ae', dark: '#a8794f', frame: ['#7a4a22', '#5a3414'], label: '#f6e2bd' };
export function setBoardPalette(p) {
  if (!p) return;
  PAL.light = p.light;
  PAL.dark = p.dark;
  PAL.frame = p.frame.slice();
  PAL.label = p.label;
}
// độ sáng 0..1 của màu '#rrggbb' (để chọn chữ sáng hoặc tối cho dễ đọc)
function lum(hex) {
  const n = parseInt(hex.slice(1), 16);
  return (0.299 * ((n >> 16) & 255) + 0.587 * ((n >> 8) & 255) + 0.114 * (n & 255)) / 255;
}

export function layout(px, size = 8) {
  const label = px * 0.055;
  const pad = px * 0.012;
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

/** Ký hiệu mờ ở góc trên-trái của từng ô (a1, e4...). Vẽ SAU quân cờ để không bị che. */
export function paintCellLabels(ctx, L) {
  const size = L.size;
  ctx.font = `800 ${Math.round(L.cell * 0.23)}px system-ui, Arial, sans-serif`;
  ctx.textAlign = 'left';
  ctx.textBaseline = 'top';
  for (let y = 0; y < size; y++) {
    for (let x = 0; x < size; x++) {
      const dark = (x + y) % 2 === 0;
      const bg = dark ? PAL.dark : PAL.light;
      ctx.fillStyle = lum(bg) < 0.62 ? 'rgba(255,248,235,0.8)' : 'rgba(40,24,10,0.68)';
      ctx.fillText(FILES[x] + (y + 1), L.gx0 + x * L.cell + L.cell * 0.07, L.gy0 + (size - 1 - y) * L.cell + L.cell * 0.04);
    }
  }
}

/** Nền bàn cờ: khung gỗ + 64 ô sáng/tối + nhãn a-h, 1-8 (+ ký hiệu mờ trong từng ô nếu cellLabels). Chưa có quân. */
export function paintBoardBase(ctx, px, size = 8, cellLabels = false) {
  const L = layout(px, size);
  paintWood(ctx, px, px, 11, PAL.frame[0], PAL.frame[1]);
  const gw = L.cell * size;
  for (let y = 0; y < size; y++) {
    for (let x = 0; x < size; x++) {
      const dark = (x + y) % 2 === 0; // a1 là ô tối
      ctx.fillStyle = dark ? PAL.dark : PAL.light;
      ctx.fillRect(L.gx0 + x * L.cell, L.gy0 + (size - 1 - y) * L.cell, L.cell + 0.5, L.cell + 0.5);
    }
  }
  ctx.strokeStyle = 'rgba(30,14,4,0.85)';
  ctx.lineWidth = Math.max(2, px / 300);
  ctx.strokeRect(L.gx0, L.gy0, gw, gw);

  if (cellLabels) paintCellLabels(ctx, L);

  ctx.fillStyle = PAL.label;
  ctx.font = `800 ${Math.round(L.cell * 0.46)}px system-ui, Arial, sans-serif`;
  ctx.textAlign = 'center';
  ctx.textBaseline = 'middle';
  for (let x = 0; x < size; x++) {
    ctx.fillText(FILES[x], L.gx0 + (x + 0.5) * L.cell, L.gy0 + gw + L.label * 0.52);
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

export class BoardView {
  constructor(canvas, size = 8) {
    this.canvas = canvas;
    this.ctx = canvas.getContext('2d');
    this.size = size;
    this.px = 0;
    this.base = null;
    this.L = null;
    this.labels = null;
    this.cache = { n: -1, board: null, key: '' };
    this.popKey = '';
    this.popT = 0;
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
    this.base = null;
  }

  /** Gọi sau setBoardPalette: vẽ lại nền bàn cờ ở khung hình kế tiếp. */
  setTheme() {
    this.base = null;
  }

  repaintBase(labels) {
    this.labels = labels;
    this.base = document.createElement('canvas');
    this.base.width = this.px;
    this.base.height = this.px;
    this.L = paintBoardBase(this.base.getContext('2d'), this.px, this.size, false);
    this.top = null;
    if (labels) {
      this.top = document.createElement('canvas');
      this.top.width = this.px;
      this.top.height = this.px;
      paintCellLabels(this.top.getContext('2d'), this.L);
    }
  }

  boardOf(moves) {
    const key = moves.length + ':' + (moves.length ? moves[moves.length - 1].n + moves[moves.length - 1].to : '');
    if (this.cache.key !== key) this.cache = { key, board: boardFromMoves(moves) };
    return this.cache.board;
  }

  /**
   * view = { moves (đã đồng bộ với cử động nhân vật), last, labels, select:{from,targets}|null }
   * t = thời gian (giây)
   */
  draw(view, t = 0) {
    if (!this.px) return;
    const labels = view.labels !== false;
    if (!this.base || this.labels !== labels) this.repaintBase(labels);
    const ctx = this.ctx;
    const L = this.L;
    ctx.drawImage(this.base, 0, 0);
    const board = this.boardOf(view.moves);
    const sqRect = (sq) => {
      const { x, y } = sqXY(sq);
      const { cx, cy } = cellCenter(L, x, y);
      return { cx, cy, x0: cx - L.cell / 2, y0: cy - L.cell / 2 };
    };

    // nước đi gần nhất: tô 2 ô
    const last = view.last;
    if (last) {
      const a = 0.32 + 0.14 * Math.sin(t * 4);
      ctx.fillStyle = `rgba(255,213,74,${a})`;
      for (const sq of [last.from, last.to]) {
        const r = sqRect(sq);
        ctx.fillRect(r.x0, r.y0, L.cell, L.cell);
      }
    }
    // quân đang được chọn
    if (view.select && view.select.from) {
      const r = sqRect(view.select.from);
      ctx.fillStyle = 'rgba(80,170,255,0.45)';
      ctx.fillRect(r.x0, r.y0, L.cell, L.cell);
      ctx.strokeStyle = 'rgba(120,200,255,0.95)';
      ctx.lineWidth = L.cell * 0.05;
      ctx.strokeRect(r.x0 + 1, r.y0 + 1, L.cell - 2, L.cell - 2);
    }
    // vua đang bị chiếu / bị chiếu hết
    if (last && (last.check || last.mate)) {
      const k = kingSquare(board, colorOf(last.m) === 'w' ? 'b' : 'w');
      if (k) {
        const r = sqRect(k);
        const g = ctx.createRadialGradient(r.cx, r.cy, L.cell * 0.05, r.cx, r.cy, L.cell * 0.62);
        const a = 0.55 + 0.3 * Math.sin(t * 7);
        g.addColorStop(0, `rgba(255,40,40,${a})`);
        g.addColorStop(1, 'rgba(255,40,40,0)');
        ctx.fillStyle = `rgba(255,50,50,${0.28 + 0.12 * Math.sin(t * 7)})`;
        ctx.fillRect(r.x0, r.y0, L.cell, L.cell);
        ctx.fillStyle = g;
        ctx.fillRect(r.x0 - L.cell * 0.15, r.y0 - L.cell * 0.15, L.cell * 1.3, L.cell * 1.3);
      }
    }
    // quân cờ
    const popKey = last ? last.n + last.to : '';
    if (popKey !== this.popKey) {
      this.popKey = popKey;
      this.popT = t;
    }
    const pop = Math.max(0, 1 - (t - this.popT) / 0.3);
    for (const [sq, p] of board) {
      const { x, y } = sqXY(sq);
      const c = cellCenter(L, x, y);
      const isLast = last && sq === last.to;
      const s = L.cell * 0.92 * (isLast ? 1 + 0.22 * pop * pop : 1);
      drawPiece(ctx, p.t, p.c, c.cx, c.cy + L.cell * 0.02, s);
    }
    if (this.top) ctx.drawImage(this.top, 0, 0);
    // ô đi được của quân đang chọn: chấm tròn (ô có quân đối phương: vòng tròn)
    if (view.select && view.select.targets) {
      for (const sq of view.select.targets) {
        const r = sqRect(sq);
        const pulse = 0.75 + 0.25 * Math.sin(t * 6);
        if (board.has(sq)) {
          ctx.strokeStyle = `rgba(255,90,90,${pulse})`;
          ctx.lineWidth = L.cell * 0.09;
          ctx.beginPath();
          ctx.arc(r.cx, r.cy, L.cell * 0.42, 0, Math.PI * 2);
          ctx.stroke();
        } else {
          ctx.fillStyle = `rgba(60,170,255,${0.55 * pulse + 0.3})`;
          ctx.beginPath();
          ctx.arc(r.cx, r.cy, L.cell * 0.15, 0, Math.PI * 2);
          ctx.fill();
        }
      }
    }
  }
}
