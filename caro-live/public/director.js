/*
 * ĐẠO DIỄN: biến dữ liệu từ server thành "màn trình diễn":
 *  - nước đi mới -> xếp hàng chờ -> nhân vật nghĩ tối thiểu ~1.3s -> đưa tay đặt quân -> mới hiện trên bàn cờ 2D
 *  - đến lượt ai thì người đó "suy nghĩ" và CAMERA QUAY VỀ NGƯỜI ĐÓ
 *  - kết thúc: người thắng nhảy mừng, người thua gục xuống, camera quay về người thắng
 * Bàn cờ 2D, giọng đọc, bảng kết quả đều đọc từ `view` để khớp với cử động.
 */

const MIN_THINK = 1.3; // giây

export class Director {
  constructor(scene) {
    this.scene = scene;
    this.state = null;
    this.offset = 0;
    this.gameNo = -1;
    this.queue = [];
    this.queued = 0;
    this.current = null;
    this.shown = [];
    this.resultReady = false;
    this.effPhase = 'lobby';
    this.onReset = null;
    this.onPlaced = null; // gọi khi 1 quân vừa chạm bàn (dùng cho âm thanh/hiệu ứng)
    this.seatInit = false;
    this.occKeys = null; // ai đang ngồi mỗi ghế (để biết khi nào đổi người)
    this.occPhase = '';
    this.holdPrev = { X: false, O: false };
    this.lastSpot = 0;
    this.pendingSpot = null;
    this.spotUntil = 0;
    this.lockPose = null; // chỉ dùng khi kiểm tra góc quay
    this.view = { moves: [], forbidden: [], banned: [], last: null, winLine: null, resultReady: false, effPhase: 'lobby', busy: false };
  }

  onState(s, offset) {
    this.state = s;
    this.offset = offset;
    if (s.gameNo !== this.gameNo || s.moves.length < this.queued) {
      this.resetBoard(s);
    } else {
      for (let i = this.queued; i < s.moves.length; i++) this.queue.push(s.moves[i]);
      this.queued = s.moves.length;
    }
    this.detectSwap();
    this.syncNames();
    // khán giả (ngoài trận) vừa tặng quà -> xếp hàng chờ để zoom camera vào họ
    const gs = s.giftSpot;
    if (gs && gs.id !== this.lastSpot) {
      this.lastSpot = gs.id;
      if (this.seatInit) this.pendingSpot = gs; // lần đầu mở trang thì bỏ qua quà cũ
    }
    this.syncSeats(!this.seatInit);
    this.seatInit = true;
  }

  /** Ai đang có mặt ở bàn: đang có ván/xác nhận/xem kết quả thì cả 2 ngồi; ở sảnh chờ thì chỉ ngồi người đã được chọn. */
  syncSeats(instant) {
    const s = this.state;
    const sc = this.scene;
    if (!sc.seat) return;
    const lobbyPick = s.phase === 'lobby' && s.lobby && s.lobby.preview ? s.lobby.preview : [];
    sc.seat('X', s.phase !== 'lobby' || !!lobbyPick[0], instant);
    sc.seat('O', s.phase !== 'lobby' || !!lobbyPick[1], instant);
    if (sc.setCrowd) sc.setCrowd(s.crowd || [], instant);
  }

  resetBoard(s) {
    const sc = this.scene;
    sc.clearPieces();
    this.queue = [];
    this.current = null;
    this.shown = [];
    this.resultReady = false;
    this.gameNo = s.gameNo;
    for (const m of s.moves) {
      sc.addPieceInstant(m);
      this.shown.push(m);
    }
    this.queued = s.moves.length;
    if (s.phase === 'finished' && s.result) {
      this.resultReady = true;
      if (s.result.line) sc.showWinLine(s.result.line);
    }
    for (const c of Object.values(sc.chars)) {
      c.placing = null;
      c.setHeld(false);
    }
    if (this.onReset) this.onReset();
  }

  /** Người đang đứng tên ở mỗi ghế (cùng cách chọn với bảng tên). */
  occupants() {
    const s = this.state;
    if (s.phase === 'lobby' || (s.phase === 'confirm' && s.confirm)) {
      const pv = s.phase === 'lobby' ? s.lobby.preview : s.confirm.slots;
      return [pv[0] || null, pv[1] || null];
    }
    if (s.phase === 'coin' && s.coin && !s.players.X) return [s.coin.heads, s.coin.tails];
    return [s.players.X || null, s.players.O || null];
  }

  /** Đổi người giữa các trận (người thua rời đi, người mới vào...): báo cho 2 ghế diễn cảnh đứng dậy đi ra rồi người mới đi vào.
   *  Bỏ qua lúc tung đồng xu: ở đó chỉ là chia lại bên X/O của cùng 2 người, không ai đổi chỗ. */
  detectSwap() {
    const sc = this.scene;
    const occ = this.occupants();
    const keys = occ.map((p) => (p ? String(p.id || p.name || '') : ''));
    const phase = this.state.phase;
    const prev = this.occKeys;
    const coinInvolved = phase === 'coin' || this.occPhase === 'coin';
    if (prev && this.seatInit && !coinInvolved && sc.replaceSeat) {
      ['X', 'O'].forEach((mark, i) => {
        if (prev[i] && keys[i] && prev[i] !== keys[i]) sc.replaceSeat(mark);
      });
    }
    this.occKeys = keys;
    this.occPhase = phase;
  }

  syncNames() {
    const s = this.state;
    const sc = this.scene;
    const { X, O } = sc.chars;
    // ghế đang đổi người: giữ bảng tên cũ cho đến khi người mới bước vào
    const hold = { X: !!(sc.seatHolding && sc.seatHolding('X')), O: !!(sc.seatHolding && sc.seatHolding('O')) };
    this.holdPrev = hold;
    const set = (mark, ch, name, neutral, avatar) => {
      if (!hold[mark]) ch.setTag(name, neutral, avatar);
    };
    if (s.phase === 'lobby' || (s.phase === 'confirm' && s.confirm)) {
      const pv = s.phase === 'lobby' ? s.lobby.preview : s.confirm.slots;
      set('X', X, pv[0] ? pv[0].name : 'Chờ đạo hữu…', true, pv[0] ? pv[0].avatar : '');
      set('O', O, pv[1] ? pv[1].name : 'Chờ đạo hữu…', true, pv[1] ? pv[1].avatar : '');
    } else if (s.phase === 'coin' && s.coin && !s.players.X) {
      // đang tung đồng xu, chưa chia X/O: chỉ hiện tên 2 người (trung tính), chưa nói ai cầm quân nào
      set('X', X, s.coin.heads.name, true, s.coin.heads.avatar || '');
      set('O', O, s.coin.tails.name, true, s.coin.tails.avatar || '');
    } else {
      set('X', X, s.players.X ? s.players.X.name : '…', false, s.players.X ? s.players.X.avatar : '');
      set('O', O, s.players.O ? s.players.O.name : '…', false, s.players.O ? s.players.O.avatar : '');
    }
  }

  nowServer() {
    return Date.now() + this.offset;
  }

  update(dt, time) {
    const s = this.state;
    const sc = this.scene;
    const urgency = { X: 0, O: 0 };
    if (!s) {
      sc.update(dt, time, { urgency });
      return;
    }
    const chars = sc.chars;
    // người mới vừa bước vào ghế đã đổi người -> cập nhật bảng tên ngay (không chờ lần cập nhật trạng thái kế tiếp)
    if ((this.holdPrev.X && !sc.seatHolding('X')) || (this.holdPrev.O && !sc.seatHolding('O'))) this.syncNames();

    // 1) bắt đầu nước đi tiếp theo trong hàng chờ
    if (!this.current && this.queue.length) {
      const mv = this.queue[0];
      const ch = chars[mv.m];
      const thinking = ch.mode === 'think' && !ch.placing;
      if (!thinking || ch.modeT >= MIN_THINK) {
        this.queue.shift();
        this.current = mv;
        ch.setMode('idle');
        ch.place(sc.cellToWorld(mv.x, mv.y), {
          onTouch: () => {
            sc.dropPiece(mv);
            this.shown.push(mv);
            if (this.onPlaced) this.onPlaced(mv, this.shown);
          },
          onDone: () => {
            this.current = null;
          },
        });
      }
    }

    // 2) chọn cử động + góc quay theo giai đoạn
    const busy = !!this.current || this.queue.length > 0;
    let eff = s.phase;
    if (s.phase === 'finished' && busy) eff = 'playing';
    this.effPhase = eff;

    if (eff === 'lobby' || eff === 'confirm') {
      chars.X.setMode('idle');
      chars.O.setMode('idle');
      // sảnh chờ: lùi camera cho thấy cả phòng (ghế trống + khán giả); lúc chọn người xác nhận thì quay về bàn
      sc.setPose(eff === 'lobby' && !(sc.seats && (sc.seats.X.desired || sc.seats.O.desired)) ? 'room' : 'wide');
    } else if (eff === 'coin') {
      chars.X.setMode('cheer');
      chars.O.setMode('cheer');
      sc.setPose('table');
    } else if (eff === 'playing') {
      if (this.current) {
        sc.setPose('place' + this.current.m);
        chars[this.current.m === 'X' ? 'O' : 'X'].setMode('idle');
      } else if (!busy) {
        const t = s.turn;
        const o = t === 'X' ? 'O' : 'X';
        chars[t].setMode('think');
        chars[o].setMode('idle');
        sc.setPose('focus' + t);
        const left = s.turnEndsAt - this.nowServer();
        urgency[t] = left < 10000 ? Math.min(1, Math.max(0, 1 - left / 10000)) : 0;
      }
    } else if (eff === 'finished') {
      const r = s.result;
      if (r && r.winner) {
        const w = r.winner;
        chars[w].setMode('win');
        chars[w === 'X' ? 'O' : 'X'].setMode('lose');
        sc.setPose('win' + w);
      } else {
        chars.X.setMode('shrug');
        chars.O.setMode('shrug');
        sc.setPose('wide');
      }
      if (!this.resultReady) {
        this.resultReady = true;
        if (r && r.line) sc.showWinLine(r.line);
      }
    }

    if (this.pendingSpot && time >= this.spotUntil) {
      const gs = this.pendingSpot;
      this.pendingSpot = null;
      const label = '🎁 ' + gs.gift + (gs.count > 1 ? ' x' + gs.count : '');
      if (sc.spotlight && sc.spotlight(gs.userId, label)) this.spotUntil = time + 4.2;
    }
    if (time < this.spotUntil) sc.setPose('gift');
    sc.crowdCheer = eff === 'finished' && !!(s.result && s.result.winner);
    if (this.lockPose) sc.setPose(this.lockPose);
    sc.update(dt, time, { urgency });

    const v = this.view;
    v.moves = this.shown;
    v.last = this.shown.length ? this.shown[this.shown.length - 1] : null;
    v.winLine = this.resultReady && s.result && s.result.line ? s.result.line : null;
    v.resultReady = this.resultReady;
    v.forbidden = eff === 'playing' && !busy && s.forbidden ? s.forbidden : [];
    v.banned = (eff === 'playing' || eff === 'finished') && s.banned ? s.banned : [];
    v.effPhase = eff;
    v.busy = busy;
  }

  /** Những câu giọng đọc đã tới lúc được phép đọc (đúng lúc quân chạm bàn / kết quả hiện ra). */
  dueCues(spoken) {
    const s = this.state;
    if (!s) return [];
    const now = this.nowServer();
    const out = [];
    for (const c of s.cues) {
      if (spoken.has(c.id)) continue;
      if (now < c.at) continue;
      if (c.gate) {
        if (c.gate.k === 'move' && this.shown.length < c.gate.n) continue;
        if (c.gate.k === 'result' && !this.resultReady) continue;
      }
      out.push(c);
    }
    return out;
  }
}
