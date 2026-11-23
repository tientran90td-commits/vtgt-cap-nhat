'use strict';
/*
 * LUẬT CỜ CARO (không liên quan TikTok / giao diện)
 * Tọa độ: x = cột (0 = A), y = hàng (0 = hàng 1). Quân: 'X' (đỏ) hoặc 'O' (xanh).
 */

const COLS = 'ABCDEFGHIJKLMNOPQRSTUVWXYZ';

function labelOf(x, y) {
  return COLS[x] + (y + 1);
}

class Game {
  constructor(size = 15, winLength = 5, blockBothEnds = false) {
    this.size = size;
    this.winLength = winLength;
    this.blockBothEnds = blockBothEnds;
    this.reset();
  }

  reset() {
    this.cells = Array.from({ length: this.size }, () => Array(this.size).fill(''));
    this.moves = [];
  }

  inBounds(x, y) {
    return x >= 0 && y >= 0 && x < this.size && y < this.size;
  }

  get(x, y) {
    return this.inBounds(x, y) ? this.cells[y][x] : null;
  }

  isEmpty(x, y) {
    return this.inBounds(x, y) && this.cells[y][x] === '';
  }

  isFull() {
    return this.moves.length >= this.size * this.size;
  }

  /** Đặt quân. Trả về { ok, win, line, draw } */
  place(x, y, mark) {
    if (!this.isEmpty(x, y)) return { ok: false, win: false, line: null, draw: false };
    this.cells[y][x] = mark;
    this.moves.push({ x, y, mark, n: this.moves.length + 1 });
    const line = this.checkWin(x, y, mark);
    return { ok: true, win: !!line, line, draw: !line && this.isFull() };
  }

  checkWin(x, y, mark) {
    const opp = mark === 'X' ? 'O' : 'X';
    const dirs = [
      [1, 0],
      [0, 1],
      [1, 1],
      [1, -1],
    ];
    for (const [dx, dy] of dirs) {
      const line = [{ x, y }];
      let cx = x + dx;
      let cy = y + dy;
      while (this.get(cx, cy) === mark) {
        line.push({ x: cx, y: cy });
        cx += dx;
        cy += dy;
      }
      const end1 = this.get(cx, cy); // ô ngay sau đầu 1 (null nếu ra khỏi bàn)
      cx = x - dx;
      cy = y - dy;
      while (this.get(cx, cy) === mark) {
        line.push({ x: cx, y: cy });
        cx -= dx;
        cy -= dy;
      }
      const end2 = this.get(cx, cy);
      if (line.length >= this.winLength) {
        // Chỉ quân ĐỐI THỦ mới tính là chặn (mép bàn không tính là chặn)
        if (this.blockBothEnds && end1 === opp && end2 === opp) continue;
        line.sort((a, b) => a.x - b.x || a.y - b.y);
        return line;
      }
    }
    return null;
  }

  /** Một ô trống ngẫu nhiên gần các quân đã đánh (dùng khi hết giờ). */
  nearbyEmptyCell(rng = Math.random) {
    if (this.moves.length === 0) {
      const c = Math.floor(this.size / 2);
      return { x: c, y: c };
    }
    const near = [];
    const all = [];
    for (let y = 0; y < this.size; y++) {
      for (let x = 0; x < this.size; x++) {
        if (this.cells[y][x] !== '') continue;
        all.push({ x, y });
        let close = false;
        for (let dy = -1; dy <= 1 && !close; dy++) {
          for (let dx = -1; dx <= 1; dx++) {
            if ((dx || dy) && this.get(x + dx, y + dy)) {
              close = true;
              break;
            }
          }
        }
        if (close) near.push({ x, y });
      }
    }
    const pool = near.length ? near : all;
    return pool[Math.floor(rng() * pool.length)] || null;
  }
}

module.exports = { Game, labelOf, COLS };
