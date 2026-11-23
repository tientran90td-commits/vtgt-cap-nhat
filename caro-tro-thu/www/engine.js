/*
 * BỘ NÃO CARO (gomoku) - chạy được cả trong trình duyệt/WebView và Node.
 * Người chơi 1 và 2. Luật: đủ 5 quân liền là thắng; chế độ strict = "chặn 2 đầu thì không tính thắng".
 * Cách làm: chấm điểm theo các cửa sổ 5 ô (cập nhật từng bước), alpha-beta tăng dần độ sâu theo thời gian,
 * thêm tìm chuỗi "liên tiếp tạo 4" (VCF) để thấy sớm đường thắng ép buộc, và chặn đường thắng ép buộc của đối thủ.
 */
(function (root, factory) {
  if (typeof module === 'object' && module.exports) module.exports = factory();
  else root.CaroEngine = factory();
})(typeof self !== 'undefined' ? self : this, function () {
  const DIRS = [
    [1, 0],
    [0, 1],
    [1, 1],
    [1, -1],
  ];
  const W = [0, 1, 12, 140, 1600, 200000]; // điểm theo số quân trong cửa sổ 5 ô (chỉ 1 phe)
  const WIN = 1e7;

  class Engine {
    /** size: cạnh bàn cờ; strict: true = 5 quân bị chặn cả 2 đầu thì không thắng. */
    constructor(size = 15, strict = false) {
      this.n = size;
      this.strict = !!strict;
      const n = size;
      this.b = new Int8Array(n * n); // 0 trống, 1, 2
      this.nb = new Int16Array(n * n); // số quân nằm trong vòng 2 ô quanh mỗi ô
      this.win = []; // các cửa sổ: mảng 5 chỉ số ô
      this.cellWins = Array.from({ length: n * n }, () => []);
      for (const [dx, dy] of DIRS) {
        for (let y = 0; y < n; y++) {
          for (let x = 0; x < n; x++) {
            const ex = x + 4 * dx;
            const ey = y + 4 * dy;
            if (ex < 0 || ex >= n || ey < 0 || ey >= n) continue;
            const id = this.win.length;
            const cells = [];
            for (let k = 0; k < 5; k++) {
              const c = (y + k * dy) * n + (x + k * dx);
              cells.push(c);
              this.cellWins[c].push(id);
            }
            this.win.push(cells);
          }
        }
      }
      this.cnt = [null, new Int8Array(this.win.length), new Int8Array(this.win.length)];
      this.score = [0, 0, 0];
      this.four = [0, 0, 0]; // số cửa sổ có 4 quân 1 phe + 1 ô trống
      this.stones = 0;
      this.stack = [];
      this.nodes = 0;
      this.deadline = 0;
      this.aborted = false;
    }

    // ---------- đặt / gỡ quân ----------
    place(x, y, p) {
      const n = this.n;
      const c = y * n + x;
      this.b[c] = p;
      const o = 3 - p;
      for (const w of this.cellWins[c]) {
        const cp = this.cnt[p][w];
        const co = this.cnt[o][w];
        // phe p
        if (co === 0) {
          this.score[p] += W[cp + 1] - W[cp];
          if (cp === 4) this.four[p]--;
          if (cp + 1 === 4) this.four[p]++;
        }
        // phe o bị chặn cửa sổ này
        if (cp === 0 && co > 0) {
          this.score[o] -= W[co];
          if (co === 4) this.four[o]--;
        }
        this.cnt[p][w] = cp + 1;
      }
      this.bump(x, y, 1);
      this.stones++;
      this.stack.push(c);
    }

    undo() {
      const n = this.n;
      const c = this.stack.pop();
      const p = this.b[c];
      const o = 3 - p;
      this.b[c] = 0;
      for (const w of this.cellWins[c]) {
        const cp = this.cnt[p][w] - 1;
        const co = this.cnt[o][w];
        this.cnt[p][w] = cp;
        if (co === 0) {
          this.score[p] -= W[cp + 1] - W[cp];
          if (cp + 1 === 4) this.four[p]--;
          if (cp === 4) this.four[p]++;
        }
        if (cp === 0 && co > 0) {
          this.score[o] += W[co];
          if (co === 4) this.four[o]++;
        }
      }
      this.bump(c % n, (c / n) | 0, -1);
      this.stones--;
    }

    bump(x, y, d) {
      const n = this.n;
      for (let yy = Math.max(0, y - 2); yy <= Math.min(n - 1, y + 2); yy++) {
        for (let xx = Math.max(0, x - 2); xx <= Math.min(n - 1, x + 2); xx++) this.nb[yy * n + xx] += d;
      }
    }

    // ---------- thắng / thua ----------
    /** quân p vừa đặt ở (x,y) có tạo thành 5 liền (đúng luật) không */
    isWinAt(x, y, p) {
      const n = this.n;
      for (const [dx, dy] of DIRS) {
        let len = 1;
        let ax = x + dx;
        let ay = y + dy;
        while (ax >= 0 && ax < n && ay >= 0 && ay < n && this.b[ay * n + ax] === p) {
          len++;
          ax += dx;
          ay += dy;
        }
        const endA = ax < 0 || ax >= n || ay < 0 || ay >= n || this.b[ay * n + ax] !== 0; // bị chặn?
        let bx = x - dx;
        let by = y - dy;
        while (bx >= 0 && bx < n && by >= 0 && by < n && this.b[by * n + bx] === p) {
          len++;
          bx -= dx;
          by -= dy;
        }
        const endB = bx < 0 || bx >= n || by < 0 || by >= n || this.b[by * n + bx] !== 0;
        if (len >= 5 && (!this.strict || !(endA && endB))) return true;
      }
      return false;
    }

    /** đường 5 quân thắng (để tô sáng), hoặc null */
    winLineAt(x, y, p) {
      const n = this.n;
      for (const [dx, dy] of DIRS) {
        const cells = [[x, y]];
        let ax = x + dx;
        let ay = y + dy;
        while (ax >= 0 && ax < n && ay >= 0 && ay < n && this.b[ay * n + ax] === p) {
          cells.push([ax, ay]);
          ax += dx;
          ay += dy;
        }
        const endA = ax < 0 || ax >= n || ay < 0 || ay >= n || this.b[ay * n + ax] !== 0;
        let bx = x - dx;
        let by = y - dy;
        while (bx >= 0 && bx < n && by >= 0 && by < n && this.b[by * n + bx] === p) {
          cells.unshift([bx, by]);
          bx -= dx;
          by -= dy;
        }
        const endB = bx < 0 || bx >= n || by < 0 || by >= n || this.b[by * n + bx] !== 0;
        if (cells.length >= 5 && (!this.strict || !(endA && endB))) return cells;
      }
      return null;
    }

    /** các ô mà p đặt vào là thắng ngay */
    winningCells(p) {
      const out = [];
      if (this.four[p] === 0) return out;
      const n = this.n;
      const seen = new Set();
      for (let w = 0; w < this.win.length; w++) {
        if (this.cnt[p][w] !== 4 || this.cnt[3 - p][w] !== 0) continue;
        for (const c of this.win[w]) {
          if (this.b[c] !== 0 || seen.has(c)) continue;
          seen.add(c);
          const x = c % n;
          const y = (c / n) | 0;
          this.b[c] = p; // thử đặt (chỉ để kiểm tra luật chặn 2 đầu)
          const ok = this.isWinAt(x, y, p);
          this.b[c] = 0;
          if (ok) out.push(c);
        }
      }
      return out;
    }

    // ---------- chọn ứng viên ----------
    /** điểm sắp xếp: tấn công + phòng thủ khi p đặt vào ô c */
    cellScore(c, p) {
      const o = 3 - p;
      let a = 0;
      let d = 0;
      for (const w of this.cellWins[c]) {
        const cp = this.cnt[p][w];
        const co = this.cnt[o][w];
        if (co === 0) a += W[cp + 1] - W[cp];
        if (cp === 0) d += W[co + 1] - W[co];
      }
      return a + d * 0.92;
    }

    candidates(p, limit) {
      const n = this.n;
      const list = [];
      if (this.stones === 0) return [[(n >> 1) * n + (n >> 1), 1]];
      for (let c = 0; c < n * n; c++) {
        if (this.b[c] !== 0 || this.nb[c] === 0) continue;
        list.push([c, this.cellScore(c, p)]);
      }
      list.sort((u, v) => v[1] - u[1]);
      return limit ? list.slice(0, limit) : list;
    }

    // ---------- tìm chuỗi liên tiếp tạo 4 (VCF) ----------
    /** p đang tới lượt: có chuỗi tạo 4 liên tiếp dẫn tới thắng không. Trả ô đi đầu tiên hoặc -1. */
    vcf(p, depth) {
      if (depth <= 0) return -1;
      if ((++this.nodes & 255) === 0 && Date.now() > this.deadline) {
        this.aborted = true;
        return -1;
      }
      const o = 3 - p;
      const wins = this.winningCells(p);
      if (wins.length) return wins[0];
      if (this.four[o] > 0) return -1; // đối thủ đang có 4: phải chặn, không còn đi ép được
      const n = this.n;
      // ô tạo ra 4: nằm trong cửa sổ có 3 quân p và không có quân o
      const tried = new Set();
      const moves = [];
      for (let w = 0; w < this.win.length; w++) {
        if (this.cnt[p][w] !== 3 || this.cnt[o][w] !== 0) continue;
        for (const c of this.win[w]) if (this.b[c] === 0 && !tried.has(c)) (tried.add(c), moves.push(c));
      }
      moves.sort((a, b) => this.cellScore(b, p) - this.cellScore(a, p));
      for (const c of moves) {
        const x = c % n;
        const y = (c / n) | 0;
        this.place(x, y, p);
        const comp = this.winningCells(p);
        let res = -1;
        if (comp.length >= 2) res = c; // đối thủ không chặn nổi 2 chỗ
        else if (comp.length === 1) {
          const bc = comp[0];
          this.place(bc % n, (bc / n) | 0, o);
          // nếu việc chặn của đối thủ tạo thành 5 thì không phải chuỗi thắng
          const oWin = this.isWinAt(bc % n, (bc / n) | 0, o);
          if (!oWin && this.vcf(p, depth - 1) !== -1) res = c;
          this.undo();
        }
        this.undo();
        if (res !== -1) return res;
        if (this.aborted) return -1;
      }
      return -1;
    }

    // ---------- alpha-beta ----------
    evalFor(p) {
      return this.score[p] - this.score[3 - p] * 1.05;
    }

    negamax(p, depth, alpha, beta, ply, width) {
      if ((++this.nodes & 255) === 0 && Date.now() > this.deadline) this.aborted = true;
      if (this.aborted) return 0;
      const o = 3 - p;
      if (this.winningCells(p).length) return WIN - ply;
      const oWins = this.winningCells(o);
      if (oWins.length >= 2) return -(WIN - ply - 1);
      if (depth <= 0) return this.evalFor(p);
      let cand;
      if (oWins.length === 1) cand = [[oWins[0], 0]];
      else cand = this.candidates(p, width);
      if (!cand.length) return 0;
      const n = this.n;
      let best = -Infinity;
      for (const [c] of cand) {
        const x = c % n;
        const y = (c / n) | 0;
        this.place(x, y, p);
        const v = -this.negamax(o, depth - 1, -beta, -alpha, ply + 1, width > 6 ? width - 1 : width);
        this.undo();
        if (this.aborted) return 0;
        if (v > best) best = v;
        if (v > alpha) alpha = v;
        if (alpha >= beta) break;
      }
      return best;
    }

    /**
     * Chọn nước đi cho phe p. opts: { ms (thời gian nghĩ), maxDepth }.
     * Trả { x, y, why, depth, nodes, alts:[{x,y}] }.
     */
    bestMove(p, opts = {}) {
      const ms = opts.ms || 1500;
      const maxDepth = opts.maxDepth || 8;
      const n = this.n;
      const o = 3 - p;
      this.deadline = Date.now() + ms;
      this.aborted = false;
      this.nodes = 0;
      const mk = (c, why, extra = {}) => ({ x: c % n, y: (c / n) | 0, why, ...extra });

      if (this.stones === 0) return mk((n >> 1) * n + (n >> 1), 'giữa bàn');
      // 1) thắng ngay
      const myWins = this.winningCells(p);
      if (myWins.length) return mk(myWins[0], 'thắng ngay');
      // 2) chặn đối thủ thắng ngay
      const oppWins = this.winningCells(o);
      if (oppWins.length) return mk(oppWins[0], 'chặn đối thủ thắng');
      // 3) chuỗi ép thắng của mình
      this.deadline = Date.now() + Math.max(200, ms * 0.35);
      const v = this.vcf(p, 14);
      this.aborted = false;
      if (v !== -1) return mk(v, 'ép thắng');
      // 4) alpha-beta tăng dần độ sâu
      this.deadline = Date.now() + ms;
      let root = this.candidates(p, 14);
      // nếu đối thủ có đường ép thắng (VCF) thì ưu tiên các nước phá được nó
      this.deadline = Date.now() + Math.max(200, ms * 0.3);
      const oppForce = this.vcf(o, 12) !== -1;
      this.aborted = false;
      if (oppForce) {
        const safe = [];
        for (const [c, sc] of root) {
          this.place(c % n, (c / n) | 0, p);
          this.deadline = Date.now() + Math.max(120, ms * 0.1);
          const still = this.winningCells(p).length ? false : this.vcf(o, 12) !== -1;
          this.aborted = false;
          this.undo();
          if (!still) safe.push([c, sc + 1e5]);
        }
        if (safe.length) root = safe.concat(root.filter(([c]) => !safe.some(([s]) => s === c)));
      }
      this.deadline = Date.now() + ms;
      this.aborted = false;
      let bestC = root[0][0];
      let depthDone = 0;
      let scores = root.map(([c, sc]) => [c, sc]);
      for (let depth = 2; depth <= maxDepth; depth += 1) {
        let curBest = -1;
        let curScore = -Infinity;
        let alpha = -Infinity;
        const cur = [];
        for (const [c] of scores) {
          this.place(c % n, (c / n) | 0, p);
          const sc = -this.negamax(o, depth - 1, -WIN * 2, -alpha, 1, depth > 4 ? 8 : 10);
          this.undo();
          if (this.aborted) break;
          cur.push([c, sc]);
          if (sc > curScore) {
            curScore = sc;
            curBest = c;
          }
          if (sc > alpha) alpha = sc;
        }
        if (this.aborted) break;
        bestC = curBest;
        depthDone = depth;
        cur.sort((a, b) => b[1] - a[1]);
        scores = cur;
        if (curScore > WIN / 2) break; // đã thấy đường thắng
        if (Date.now() > this.deadline - ms * 0.15) break;
      }
      const alts = scores.slice(0, 4).map(([c]) => ({ x: c % n, y: (c / n) | 0 }));
      return mk(bestC, 'tính nước', { depth: depthDone, nodes: this.nodes, alts });
    }
  }

  /** dựng engine từ danh sách nước đã đi [[x,y,p],...] */
  function fromMoves(size, strict, moves) {
    const e = new Engine(size, strict);
    for (const [x, y, p] of moves) e.place(x, y, p);
    return e;
  }

  return { Engine, fromMoves };
});
