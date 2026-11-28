'use strict';
/*
 * DIỄN BIẾN TRẬN ĐẤU (máy trạng thái):
 *   lobby (đua tương tác)  ->  confirm (2 người được chọn THẢ TIM xác nhận)  ->  coin (tung đồng xu)
 *   ->  playing (đánh cờ)  ->  finished (kết quả)  ->  lobby ...
 * Người chơi đánh cờ bằng cách bình luận tọa độ, ví dụ: j9, k6.
 */
const crypto = require('crypto');
const { forbiddenReason, forbiddenCells } = require('./forbidden');
const { Game, labelOf } = require('./game');
const { parseMove, parsePartial, parseCommand } = require('./commands');
const { rankInfo } = require('./rank');

const other = (m) => (m === 'X' ? 'O' : 'X');
const brief = (u) => ({
  id: u.id,
  uniqueId: u.uniqueId || '',
  name: u.name || u.uniqueId || 'Ẩn danh',
  avatar: u.avatar || '',
});

// Tung đồng xu: đồng xu bay/quay (chưa ai biết kết quả) -> hết COIN_DRAW_MS mới BỐC NGẪU NHIÊN mặt ngửa/sấp
// -> đồng xu rơi và dừng trong COIN_LAND_MS -> lúc đó mới công bố ai X (đi trước), ai O. Khớp với public/coin.js.
const COIN_DRAW_MS = 2600;
const COIN_LAND_MS = 1500;

class Match {
  constructor(cfg, interaction, stats, commentator) {
    this.cfg = cfg;
    this.interaction = interaction;
    this.stats = stats;
    this.voice = commentator;
    this.game = new Game(cfg.boardSize, cfg.winLength, cfg.blockBothEnds);

    this.connection = { status: 'starting', text: '' };
    this.feedList = [];
    this.feedSeq = 0;
    this.softNotes = new Map();

    this.gameNo = 0;
    this.champion = null; // { ...player, streak }
    this.entering = {}; // chuỗi thắng của từng người LÚC VÀO ván hiện tại: { id: số ván } (ghép tay có thể tự đặt)
    this.excludeNext = new Set();
    this.booked = null; // cặp đã HẸN TRƯỚC cho ván kế tiếp: { ids:[a,b], confirmLike }
    this.firstLobby = true;
    this.confirm = null; // { slots:[{user,done}], round, warned } trong pha xác nhận thả tim
    this.confirmFailed = new Set();
    this.lastCommentAt = { X: 0, O: 0 };
    this.extraUsed = { X: 0, O: 0 }; // số lần đã xin thêm giờ trong ván
    this.partial = { X: null, O: null }; // nửa tọa độ vừa gõ ("j" rồi "9" ở bình luận sau)
    this.hinted = false;
    this.signPulseUntil = 0;
    this.onPromo = null; // (dự phòng) hub gắn vào: hiện khung nhắc trên màn hình live

    this.enterLobby(Date.now());
  }

  // ---------- tiện ích ----------
  isHost(user) {
    if (!user || !user.uniqueId) return false;
    const u = user.uniqueId.toLowerCase();
    return (!!this.cfg.tiktokUsername && u === this.cfg.tiktokUsername.toLowerCase()) ||
      (!!this.cfg.demo && u === 'host');
  }

  feed(text, kind = 'info', mark = null) {
    this.feedList.push({ id: ++this.feedSeq, kind, text, mark });
    if (this.feedList.length > 10) this.feedList.shift();
  }

  softNote(key, text, ms, kind = 'warn') {
    const now = Date.now();
    if ((this.softNotes.get(key) || 0) + ms > now) return false;
    this.softNotes.set(key, now);
    if (this.softNotes.size > 500) this.softNotes.clear();
    this.feed(text, kind);
    return true;
  }

  markOf(userId) {
    if (this.players.X && this.players.X.id === userId) return 'X';
    if (this.players.O && this.players.O.id === userId) return 'O';
    return null;
  }

  rulesText() {
    const c = this.cfg;
    return `${c.winLength} quân liên tiếp${c.blockBothEnds ? ', không bị chặn 2 đầu' : ''}${c.forbidX && c.winLength === 5 ? ', X bị cấm 3-3 / 4-4 / hàng dài' : ''}${c.oBan ? ', O cấm 1 ô sau nước thứ ' + (Number(c.oBanAfter) || 2) + ' của X (cả hai bên không được đi)' : ''}`;
  }

  // ---------- chọn người chơi ----------
  eligible(u) {
    return !(this.isHost(u) && !this.cfg.hostCanPlay) && !(this.champion && u.id === this.champion.id);
  }

  /** Cặp chủ phòng đã hẹn trước (nếu cả 2 vẫn còn trong danh sách người xem). */
  bookedList() {
    if (!this.booked) return null;
    const list = this.booked.ids.map((id) => this.interaction.users.get(id)).filter(Boolean);
    return list.length === 2 ? list : null;
  }

  /** Hẹn trước: hết ván hiện tại, ván kế tiếp sẽ là 2 người này (không cần đủ điểm, không tính chuỗi thắng). */
  bookNext(ids, opt = {}, now = Date.now()) {
    const uniq = [...new Set(Array.isArray(ids) ? ids.map(String) : [])];
    const list = uniq.map((id) => this.interaction.users.get(id)).filter(Boolean);
    if (uniq.length !== 2 || list.length !== 2) return { ok: false, msg: 'Cần chọn đúng 2 người (người này phải đã tương tác trong live).' };
    const streaks = this.cleanStreaks(uniq, opt.streaks);
    this.booked = { ids: uniq, confirmLike: !!opt.confirmLike, streaks };
    this.feed(`📌 Đã hẹn trước: đạo hữu ${list[0].name} và ${list[1].name} sẽ đấu ván kế tiếp${this.streakNote(list, streaks)}`, 'info');
    return { ok: true };
  }

  /** Làm sạch số ván thắng liên tiếp do chủ phòng nhập: chỉ giữ người trong cặp, số nguyên 0-50. Bỏ trống = tự động. */
  cleanStreaks(ids, raw) {
    const out = {};
    if (!raw || typeof raw !== 'object') return out;
    for (const id of ids) {
      const v = raw[id];
      if (v === undefined || v === null || v === '') continue;
      const n = Math.floor(Number(v));
      if (Number.isFinite(n)) out[id] = Math.max(0, Math.min(50, n));
    }
    return out;
  }

  /** Chuỗi thắng lúc vào ván: số chủ phòng đặt; không đặt thì GIỮ NGUYÊN chuỗi hiện có (người đang giữ bàn). */
  makeEntering(list, preset) {
    const out = {};
    for (const u of list) {
      const n = preset && preset[u.id] !== undefined ? preset[u.id] : this.champion && this.champion.id === u.id ? this.champion.streak : 0;
      if (n > 0) out[u.id] = n;
    }
    return out;
  }

  streakNote(list, preset) {
    const ent = this.makeEntering(list, preset);
    const parts = list.filter((u) => ent[u.id] > 0).map((u) => `${u.name} đang thắng ${ent[u.id]} ván liên tiếp`);
    return parts.length ? ` (${parts.join('; ')})` : '';
  }

  cancelBooked() {
    if (!this.booked) return { ok: true };
    this.booked = null;
    this.feed('📌 Chủ phòng đã huỷ lịch hẹn trước', 'info');
    return { ok: true };
  }

  chooseCandidates() {
    const bl = this.bookedList();
    if (bl) return { need: 2, list: bl, ok: true, booked: true };
    const need = this.champion ? 1 : 2;
    const min = this.cfg.minPointsToPlay;
    const base = (u) => this.eligible(u);
    let list = this.interaction
      .top(20, { min, filter: (u) => base(u) && !this.excludeNext.has(u.id) })
      .slice(0, need);
    if (list.length < need) {
      const ids = new Set(list.map((u) => u.id));
      const more = this.interaction
        .top(20, { min, filter: (u) => base(u) && !ids.has(u.id) })
        .slice(0, need - list.length);
      list = list.concat(more);
    }
    return { need, list, ok: list.length >= need };
  }

  // ---------- chuyển pha ----------
  enterLobby(now, next = false) {
    // next = vừa hết ván: tự sang ván kế tiếp với vòng chờ ngắn hơn
    const farm = !!this.cfg.farmOn; // chế độ "cày điểm": vòng chờ = khoảng cày điểm, xóa bảng điểm cũ, bắt đầu tính điểm lại từ 0
    const secs = farm ? Math.max(10, Number(this.cfg.farmSeconds) || 35) : next && this.cfg.autoNextGame !== false ? this.cfg.nextLobbySeconds : this.cfg.lobbySeconds;
    this.lobbySecs = secs;
    this.farmRound = farm;
    if (farm) this.interaction.resetPoints();
    this.interaction.frozen = false;
    this.phase = 'lobby';
    this.players = { X: null, O: null };
    this.game.reset();
    this.ban = { cell: null, picking: false }; // luật "O cấm 1 ô" (src: tryBan)
    this.result = null;
    this.coin = null;
    this.coinPlayers = null;
    this.coinSeats = null;
    this.waiting = false;
    this.confirm = null;
    this.confirmFailed = new Set();
    this.lobbyWarned = false;
    this.phaseStartedAt = now;
    this.phaseEndsAt = now + secs * 1000;
    this.turn = 'X';
    this.turnStartedAt = now;
    this.turnEndsAt = now;
    if (farm) {
      this.feed(`⏱ BẮT ĐẦU CÀY ĐIỂM! ${secs} giây: bình luận, thả tim, chia sẻ để lên bảng, người dẫn đầu sẽ lên đài`, 'info');
      this.voice.farmStart(this.firstLobby, now, secs);
    } else this.voice.lobbyStart(this.firstLobby, now, secs);
    if (secs >= 18) this.voice.howTo(now, 10000);
    this.firstLobby = false;
  }

  /** Chọn xong người chơi: nếu bật xác nhận thì sang pha "thả tim", không thì tung đồng xu luôn. */
  beginSelection(c, now) {
    if (this.cfg.farmOn) this.interaction.frozen = true; // hết khoảng cày điểm: ngưng tính điểm cho tới sau trận
    let confirmLike = this.cfg.confirmSeconds > 0;
    if (c.booked) {
      // tới lượt cặp đã hẹn: bỏ chuỗi thắng cũ, dùng lịch hẹn một lần
      confirmLike = !!(this.booked && this.booked.confirmLike) && this.cfg.confirmSeconds > 0;
      c.entering = this.makeEntering(c.list, this.booked && this.booked.streaks); // tính TRƯỚC khi bỏ người giữ bàn cũ
      this.champion = null;
      this.excludeNext.clear();
      this.booked = null;
      this.feed(`📌 Tới lượt cặp đã hẹn trước: ${c.list[0].name} gặp ${c.list[1].name}`, 'info');
    }
    if (confirmLike) this.startConfirm(c, now);
    else this.startCoin(c, now);
  }

  startConfirm(c, now) {
    const secs = this.cfg.confirmSeconds;
    this.phase = 'confirm';
    this.waiting = false;
    this.phaseStartedAt = now;
    this.phaseEndsAt = now + secs * 1000;
    this.confirm = {
      slots: c.list.map((u) => ({ user: u, done: this.isHost(u) })), // chủ phòng không cần thả tim
      round: 1,
      warned: false,
      entering: c.entering || null,
    };
    const pending = this.confirm.slots.filter((x) => !x.done).map((x) => x.user);
    const names = c.list.map((u) => u.name).join(' và ');
    this.feed(`❤ ${names}: mời đạo hữu THẢ TIM để xác nhận lên đài (${secs}s)`, 'info');
    this.voice.confirmAsk(pending, secs, now);
    this.checkConfirmed(now);
  }

  /** Người được chọn thả tim -> ghi nhận. */
  onLike(user, now = Date.now()) {
    if (this.phase !== 'confirm' || !this.confirm) return;
    const slot = this.confirm.slots.find((x) => x.user.id === user.id || (user.rawId && x.user.rawId && x.user.rawId === user.rawId));
    if (!slot || slot.done) return;
    slot.done = true;
    this.feed(`❤ Đạo hữu ${slot.user.name} đã thả tim, sẵn sàng!`, 'gift');
    if (this.confirm.slots.every((x) => x.done)) this.checkConfirmed(now);
    else this.voice.confirmOk(slot.user, now);
  }

  checkConfirmed(now) {
    if (this.phase !== 'confirm' || !this.confirm) return;
    if (!this.confirm.slots.every((x) => x.done)) return;
    const list = this.confirm.slots.map((x) => x.user);
    const entering = this.confirm.entering || undefined;
    this.confirm = null;
    this.startCoin({ list, entering }, now);
  }

  /** Hết giờ xác nhận: người chưa thả tim mất suất, mời người kế tiếp thay. */
  confirmTimeout(now) {
    const cf = this.confirm;
    const failed = cf.slots.filter((x) => !x.done);
    for (const f of failed) {
      this.confirmFailed.add(f.user.id);
      this.interaction.zero(f.user.id); // phải tương tác lại từ đầu mới được chọn
    }
    const used = new Set(cf.slots.map((x) => x.user.id));
    const min = this.cfg.minPointsToPlay;
    for (const f of failed) {
      const rep = this.interaction.top(20, {
        min,
        filter: (u) => this.eligible(u) && !this.confirmFailed.has(u.id) && !used.has(u.id),
      })[0];
      if (!rep) {
        this.feed(`⏰ Đạo hữu ${f.user.name} không thả tim, không còn ai thế chỗ. Chọn lại người lên đài!`, 'warn');
        this.voice.confirmFail(f.user, null, now);
        this.confirm = null;
        this.enterLobby(now);
        return;
      }
      used.add(rep.id);
      const old = f.user;
      f.user = rep;
      f.done = this.isHost(rep);
      this.feed(`⏰ Đạo hữu ${old.name} không thả tim. Mời đạo hữu ${rep.name} thế chỗ, xin thả tim!`, 'warn');
      this.voice.confirmFail(old, rep, now);
    }
    cf.round += 1;
    cf.warned = false;
    this.phaseStartedAt = now;
    this.phaseEndsAt = now + this.cfg.confirmSeconds * 1000;
    this.checkConfirmed(now);
  }

  /** Chủ phòng bấm "Bỏ qua xác nhận". */
  skipConfirm(now = Date.now()) {
    if (this.phase !== 'confirm' || !this.confirm) return { ok: false, msg: 'Chỉ bấm được khi đang chờ xác nhận thả tim.' };
    for (const x of this.confirm.slots) x.done = true;
    this.checkConfirmed(now);
    return { ok: true };
  }

  startCoin(c, now) {
    const chosen = c.list;
    let p1;
    let p2;
    if (c.entering) {
      // ghép tay / hẹn trước: đủ 2 người, chuỗi thắng do chủ phòng đặt (hoặc giữ nguyên của người đang giữ bàn)
      p1 = chosen[0];
      p2 = chosen[1];
      this.entering = { ...c.entering };
    } else if (this.champion) {
      p1 = this.champion;
      p2 = chosen[0];
      this.entering = { [this.champion.id]: this.champion.streak };
    } else {
      p1 = chosen[0];
      p2 = chosen[1];
      this.entering = {};
    }
    this.voice.picked(this.champion, chosen, now);

    this.gameNo += 1;
    this.game.reset();
    this.result = null;
    // CHƯA chia X/O: kết quả đồng xu được bốc ngẫu nhiên ở drawCoin() sau khi đồng xu đã bay một lúc
    this.players = { X: null, O: null };
    this.coinPlayers = [p1, p2];
    this.coinSeats = null;
    const drawMs = Math.max(1200, Math.min(COIN_DRAW_MS, this.cfg.coinSeconds * 1000 - COIN_LAND_MS - 700));
    this.coin = {
      face: null, // 'heads' | 'tails' - có sau drawMs
      first: null, // { mark: 'X', name } - có sau revealMs
      revealed: false,
      heads: brief(p1),
      tails: brief(p2),
      drawMs,
      revealMs: drawMs + COIN_LAND_MS,
    };
    if (c.entering) {
      // hiện "chuỗi thắng" trên màn hình cho người đang có chuỗi cao nhất
      const best = [p1, p2].sort((a, b) => (this.entering[b.id] || 0) - (this.entering[a.id] || 0))[0];
      const n = this.entering[best.id] || 0;
      this.champion = n > 0 ? { ...brief(best), streak: n } : null;
      const note = this.streakNote([p1, p2], this.entering);
      if (note && this.cfg.winnerStays) this.feed(`🔥 Chuỗi thắng giữ nguyên${note}`, 'info');
    }
    this.interaction.resetPoints();
    this.excludeNext.clear();
    this.stats.recordGame(p1);
    this.stats.recordGame(p2);

    this.phase = 'coin';
    this.phaseStartedAt = now;
    this.phaseEndsAt = now + this.cfg.coinSeconds * 1000;
    this.voice.coinToss(now);
  }

  /** Bốc ngẫu nhiên mặt đồng xu (ngửa = người thứ nhất đi trước, sấp = người thứ hai). Chỉ gọi khi đồng xu đã bay xong phần quay. */
  drawCoin() {
    const c = this.coin;
    if (!c || c.face !== null || !this.coinPlayers) return;
    const [p1, p2] = this.coinPlayers;
    const heads = crypto.randomInt(2) === 0;
    c.face = heads ? 'heads' : 'tails';
    this.coinSeats = heads ? [p1, p2] : [p2, p1];
  }

  /** Đồng xu đã dừng hẳn: bây giờ mới chia X/O và công bố. */
  revealCoin(now) {
    const c = this.coin;
    if (!c || c.revealed || c.face === null || !this.coinSeats) return;
    const [xp, op] = this.coinSeats;
    this.players = { X: brief(xp), O: brief(op) };
    c.first = { mark: 'X', name: this.players.X.name };
    c.revealed = true;
    this.feed(`🪙 Tung đồng xu: đạo hữu ${this.players.X.name} đi trước (X đỏ)`, 'info');
    this.voice.coinResult(this.players.X, this.players.O, now);
  }

  /** Bốc + công bố ngay (hết giờ pha tung xu, hoặc kiểm thử). */
  settleCoin(now = Date.now()) {
    this.drawCoin();
    this.revealCoin(now);
  }

  /** Đã ngồi vào bàn (hoặc đang tung đồng xu giành quyền đi trước) - dùng để không vẽ họ lẫn vào khán giả. */
  seated(userId) {
    return this.markOf(userId) || (this.coinPlayers && this.coinPlayers.some((u) => u.id === userId) && this.phase === 'coin' ? 'X' : null);
  }

  startPlaying(now) {
    this.phase = 'playing';
    this.phaseStartedAt = now;
    this.timeouts = { X: 0, O: 0 };
    this.extraUsed = { X: 0, O: 0 };
    this.ban = { cell: null, picking: false };
    this.beginTurn('X', now);
    this.feed(`▶ Khai cục! Gõ tọa độ như j9, k6 để xuất chiêu`, 'info');
    this.voice.start(this.players.X, now);
  }

  beginTurn(mark, now) {
    this.turn = mark;
    this.turnStartedAt = now;
    this.turnEndsAt = now + this.cfg.turnSeconds * 1000;
    this.warned = false;
    this.hinted = false;
    this.partial = { X: null, O: null };
  }

  /** Người đang đến lượt xin thêm giờ ("!them", "thêm giờ"). */
  requestExtra(mark, now) {
    const secs = Number(this.cfg.extraTimeSeconds) || 0;
    const max = Number(this.cfg.extraTimesPerGame) || 0;
    if (!(max > 0) || !(secs > 0)) return;
    const player = this.players[mark];
    if (mark !== this.turn) {
      this.softNote(`turn:${player.id}`, `${player.name}: chưa tới lượt của bạn`, 7000);
      return;
    }
    if (this.extraUsed[mark] >= max) {
      this.softNote(`extra:${player.id}`, `${player.name}: bạn đã dùng hết lượt xin thêm giờ`, 8000);
      return;
    }
    this.extraUsed[mark] += 1;
    this.addTime(secs, now);
    this.feed(`⏳ Đạo hữu ${player.name} xin thêm ${secs} giây`, 'info', mark);
    this.voice.extraTime(player, secs, now);
  }

  /** Cộng thêm giờ cho lượt hiện tại (người chơi xin hoặc chủ phòng bấm nút). */
  addTime(secs, now) {
    this.turnEndsAt += secs * 1000;
    if (this.turnEndsAt - now > 10000) this.warned = false; // cho phép cảnh báo "còn 10 giây" lần nữa
  }

  extendTurn(secs, now = Date.now()) {
    if (this.phase !== 'playing') return { ok: false, msg: 'Chưa trong ván đấu.' };
    const n = Math.max(1, Math.min(120, Math.round(Number(secs) || 15)));
    this.addTime(n, now);
    this.feed(`⏳ Chủ phòng ban thêm ${n} giây cho đạo hữu ${this.players[this.turn].name}`, 'info', this.turn);
    return { ok: true };
  }

  /** Khán giả gõ !diem: báo hạng + điểm của họ trong bảng top tương tác (hiện chữ, không đọc thành tiếng). */
  showRank(user) {
    const list = this.interaction.top(100000, { min: 1, filter: (u) => this.cfg.hostCanPlay || !this.isHost(u) });
    const i = list.findIndex((u) => u.id === user.id);
    const name = user.name || user.uniqueId || 'Bạn';
    let text;
    if (i < 0) {
      text = `📊 ${name}: bạn chưa có điểm. Bình luận hoặc thả tim để cùng tham gia!`;
    } else {
      const need = this.chooseCandidates().need;
      const me = list[i];
      text = `📊 ${name}: hạng ${i + 1}/${list.length} • ${me.points} điểm`;
      if (i >= need && list[need - 1]) text += ` • cần hơn ${list[need - 1].points - me.points} điểm nữa để vào top ${need}`;
      else text += ` • đang trong top ${need} được chọn đấu!`;
    }
    this.softNote(`rank:${user.id}`, text, 12000, 'info');
  }

  // ---------- nhận bình luận ----------
  onComment(user, text, now = Date.now()) {
    const cmd = parseCommand(text);
    if (cmd === 'reset' && this.isHost(user)) {
      this.hardReset(now);
      return;
    }
    if (cmd === 'rank') {
      this.showRank(user);
      return;
    }
    if (this.phase !== 'playing') return;
    const mark = this.markOf(user.id);
    if (!mark) return; // khán giả: chỉ được tính điểm tương tác
    this.lastCommentAt[mark] = now; // người chơi vẫn đang tương tác (bình luận hiện được)

    if (cmd === 'surrender') {
      this.finishForfeit(mark, 'đã chủ động nhận thua', now);
      return;
    }
    if (cmd === 'extend') {
      this.requestExtra(mark, now);
      return;
    }

    const mv = parseMove(text, this.cfg.boardSize);
    if (!mv.ok) {
      if (mv.reason === 'many') {
        this.softNote(`many:${user.id}`, `${this.players[mark].name}: chỉ gõ 1 tọa độ thôi nhé`, 6000);
      } else if (mv.reason === 'range') {
        this.softNote(`range:${user.id}`, `${this.players[mark].name}: tọa độ ngoài bàn cờ (A-O, 1-15)`, 6000);
      } else if (mark === this.turn) {
        this.onPartial(mark, text, now);
      }
      return;
    }
    this.partial[mark] = null;
    if (mark !== this.turn) {
      this.softNote(`turn:${user.id}`, `${this.players[mark].name}: chưa tới lượt của bạn`, 7000);
      return;
    }
    this.tryMove(mark, mv.x, mv.y, now);
  }

  /** Chỉ gõ nửa tọa độ: nhớ lại ~12 giây, nửa còn lại gõ sau thì ghép thành nước đi. */
  onPartial(mark, text, now) {
    const part = parsePartial(text, this.cfg.boardSize);
    if (!part) return;
    const prev = this.partial[mark];
    if (prev && prev.kind !== part.kind && now - prev.at <= 12000) {
      this.partial[mark] = null;
      const x = part.kind === 'letter' ? part.x : prev.x;
      const y = part.kind === 'row' ? part.y : prev.y;
      this.tryMove(mark, x, y, now);
      return;
    }
    this.partial[mark] = { ...part, at: now };
    const p = this.players[mark];
    this.softNote(`part:${p.id}`, `${p.name}: gõ cả cột và hàng trong 1 bình luận nhé, ví dụ j9 (đã nhận "${part.label}")`, 9000);
  }

  tryMove(mark, x, y, now) {
    const player = this.players[mark];
    if (this.ban.picking) {
      this.tryBan(mark, x, y, now);
      return;
    }
    if (!this.game.isEmpty(x, y)) {
      const label = labelOf(x, y);
      if (this.softNote(`occ:${player.id}`, `${label} đã có quân, ${player.name} chọn ô khác`, 4000)) {
        this.voice.occupied(player, x, y, now);
      }
      return;
    }
    if (this.ban.cell && this.ban.cell.x === x && this.ban.cell.y === y) {
      if (this.softNote(`ban:${player.id}`, `🚫 ${labelOf(x, y)} là ô bị CẤM (cả hai bên không được đi), ${player.name} chọn ô khác`, 6000, 'warn')) {
        this.voice.banHit(player, x, y, now);
      }
      return;
    }
    if (this.cfg.forbidX) {
      const why = forbiddenReason(this.game, x, y, mark);
      if (why) {
        const label = labelOf(x, y);
        if (this.softNote(`forbid:${player.id}`, `⛔ ${label} là ô CẤM với quân đi trước (${why}), ${player.name} chọn ô khác`, 6000, 'warn')) {
          this.voice.forbidden(player, x, y, why, now);
        }
        return;
      }
    }
    const r = this.game.place(x, y, mark);
    this.timeouts[mark] = 0;
    this.feed(`${player.name} xuất chiêu ${labelOf(x, y)}`, 'move', mark);
    this.afterMove(mark, x, y, r, now);
  }

  afterMove(mark, x, y, r, now) {
    const n = this.game.moves.length;
    const next = other(mark);
    if (r.win) {
      this.voice.move(this.players[mark], mark, x, y, null, n, now);
      this.finishWin(mark, r.line, now);
    } else if (r.draw) {
      this.voice.move(this.players[mark], mark, x, y, null, n, now);
      this.finishDraw(now);
    } else if (this.banDue(mark)) {
      // luật "O cấm 1 ô": sau nước thứ oBanAfter của X (mặc định 2), O phải chọn 1 ô cấm (gõ tọa độ) rồi mới được đi quân
      this.voice.move(this.players[mark], mark, x, y, null, n, now);
      this.startBan(now);
    } else {
      this.voice.move(this.players[mark], mark, x, y, this.players[next], n, now);
      this.beginTurn(next, now);
    }
  }

  /** Vừa xong nước của `mark`: có tới lúc O cấm ô chưa? (dùng cho cả nước thường lẫn nước thiên đạo đánh thay khi hết giờ) */
  banDue(mark) {
    return !!(this.cfg.oBan && mark === 'X' && !this.ban.cell && !this.ban.picking && this.game.moves.filter((m) => m.mark === 'X').length >= (Number(this.cfg.oBanAfter) || 2));
  }

  startBan(now) {
    this.ban.picking = true;
    this.beginTurn('O', now);
    this.feed(`🚫 ${this.players.O.name} hãy CẤM 1 ô: gõ tọa độ ô muốn cấm (cả hai bên không được đi vào ô đó đến hết ván)`, 'warn', 'O');
    this.voice.banAsk(this.players.O, now);
  }

  /** O chọn ô cấm (bước 1). Xong thì O gõ tọa độ lần nữa để đi quân (bước 2). */
  tryBan(mark, x, y, now) {
    const player = this.players[mark];
    if (!this.game.isEmpty(x, y)) {
      if (this.softNote(`occ:${player.id}`, `${labelOf(x, y)} đã có quân, ${player.name} chọn ô trống để cấm`, 4000)) {
        this.voice.occupied(player, x, y, now);
      }
      return;
    }
    this.setBan(x, y, now);
  }

  setBan(x, y, now) {
    this.ban = { cell: { x, y }, picking: false };
    const o = this.players.O;
    const xp = this.players.X;
    this.feed(`🚫 ${o.name} đã CẤM ô ${labelOf(x, y)}: cả hai bên không được đi vào đó đến hết ván. Mời ${o.name} đi quân!`, 'warn', 'O');
    this.voice.banSet(o, xp, x, y, now);
    this.beginTurn('O', now);
  }

  onTurnTimeout(now) {
    const mark = this.turn;
    const player = this.players[mark];
    this.timeouts[mark] += 1;
    if (this.timeouts[mark] >= this.cfg.maxTimeouts) {
      this.finishForfeit(mark, 'hết thời gian quá nhiều lần nên bị xử thua', now);
      return;
    }
    if (this.ban.picking) {
      // O hết giờ mà chưa chọn ô cấm: thiên đạo chọn thay 1 ô gần quân
      const bc = this.game.nearbyEmptyCell();
      if (!bc) {
        this.finishDraw(now);
        return;
      }
      this.feed(`⏰ ${player.name} hết giờ! Thiên đạo cấm thay ô ${labelOf(bc.x, bc.y)} (${this.timeouts[mark]}/${this.cfg.maxTimeouts})`, 'warn', mark);
      this.setBan(bc.x, bc.y, now);
      return;
    }
    const isBanned = (c) => this.ban.cell && this.ban.cell.x === c.x && this.ban.cell.y === c.y;
    let cell = this.game.nearbyEmptyCell();
    for (let i = 0; i < 80 && cell && (isBanned(cell) || (this.cfg.forbidX && forbiddenReason(this.game, cell.x, cell.y, mark))); i++) cell = this.game.nearbyEmptyCell();
    if (!cell) {
      this.finishDraw(now);
      return;
    }
    const r = this.game.place(cell.x, cell.y, mark);
    this.feed(
      `⏰ ${player.name} hết giờ! Thiên đạo đánh thay ${labelOf(cell.x, cell.y)} (${this.timeouts[mark]}/${this.cfg.maxTimeouts})`,
      'warn',
      mark
    );
    this.voice.timeoutAuto(player, cell.x, cell.y, this.game.moves.length, now);
    if (r.win) this.finishWin(mark, r.line, now);
    else if (r.draw) this.finishDraw(now);
    else if (this.banDue(mark)) this.startBan(now); // X bị đánh thay đúng nước thứ 2: vẫn tới lượt O cấm ô
    else this.beginTurn(other(mark), now);
  }

  // ---------- lệnh từ bảng điều khiển ----------
  applySettings() {
    this.game.blockBothEnds = !!this.cfg.blockBothEnds;
  }

  /** Bắt đầu ván ngay, không đợi hết giờ "đua tương tác". */
  /**
   * Chủ phòng tự chọn 2 người xem cho đấu với nhau (từ bảng điều khiển).
   * opt.force: cho phép dừng ván đang chơi; opt.confirmLike: bắt 2 người thả tim xác nhận như bình thường.
   */
  pickPlayers(ids, opt = {}, now = Date.now()) {
    const uniq = [...new Set(Array.isArray(ids) ? ids.map(String) : [])];
    const list = uniq.map((id) => this.interaction.users.get(id)).filter(Boolean);
    if (uniq.length !== 2 || list.length !== 2) return { ok: false, msg: 'Cần chọn đúng 2 người (người này phải đã tương tác trong live).' };
    if ((this.phase === 'playing' || this.phase === 'coin') && !opt.force) return { ok: false, msg: 'Đang có ván. Hãy xác nhận dừng ván trước khi chọn người mới.' };
    const entering = this.makeEntering(list, this.cleanStreaks(uniq, opt.streaks)); // tính trước khi bỏ người giữ bàn cũ
    this.champion = null;
    this.excludeNext.clear();
    this.enterLobby(now);
    this.feed(`🎯 Chủ phòng chỉ định đạo hữu ${list[0].name} và ${list[1].name} tỷ thí${this.streakNote(list, entering)}`, 'info');
    if (opt.confirmLike && this.cfg.confirmSeconds > 0) this.startConfirm({ list, entering }, now);
    else this.startCoin({ list, entering }, now);
    return { ok: true };
  }

  startNow(now = Date.now()) {
    if (this.phase === 'finished') {
      this.enterLobby(now);
    }
    if (this.phase !== 'lobby') return { ok: false, msg: 'Chỉ bấm được khi đang chờ chọn người chơi.' };
    const c = this.chooseCandidates();
    if (!c.ok) return { ok: false, msg: `Chưa đủ người (cần ${c.need} người có điểm tương tác).` };
    this.beginSelection(c, now);
    return { ok: true };
  }

  /** Đánh thay cho người đang đến lượt (không tính lỗi hết giờ). */
  skipTurn(now = Date.now()) {
    if (this.phase !== 'playing') return { ok: false, msg: 'Chưa trong ván đấu.' };
    this.timeouts[this.turn] = Math.max(0, this.timeouts[this.turn] - 1);
    this.onTurnTimeout(now);
    this.timeouts.X = Math.max(0, this.timeouts.X);
    this.timeouts.O = Math.max(0, this.timeouts.O);
    return { ok: true };
  }

  forfeitPlayer(mark, now = Date.now()) {
    if (this.phase !== 'playing' || !this.players[mark]) return { ok: false, msg: 'Chưa trong ván đấu.' };
    this.finishForfeit(mark, 'bị chủ phòng xử thua', now);
    return { ok: true };
  }

  // ---------- kết thúc ván ----------
  finishCommon(now) {
    this.phase = 'finished';
    this.phaseStartedAt = now;
    let secs = this.cfg.resultSeconds;
    // có video ăn mừng: giữ màn hình kết quả đủ lâu để video chạy hết rồi mới sang bước kế
    if (this.cfg.celebrateVideo && this.result && this.result.winner) secs = Math.max(secs, this.cfg.celebrateMinSeconds || 0);
    // có bảng "đột phá": cộng thêm thời gian để hiện sau video ăn mừng (~8 giây)
    const ru = this.result && this.result.rankUp ? 1 : 0;
    const rd = this.result && this.result.rankDown ? 1 : 0;
    if (ru || rd) {
      if (this.cfg.celebrateVideo) secs += ru * 7 + rd * 6;
      else secs = Math.max(secs, ru * 9 + rd * 8);
    }
    this.phaseEndsAt = now + secs * 1000;
  }

  settleWinner(winMark, now, result) {
    const winner = this.players[winMark];
    const loser = this.players[other(winMark)];
    const steps = this.cfg.rankWins;
    const before = this.rankOf(winner);
    const beforeL = this.rankOf(loser);
    this.stats.recordWin(winner);
    // thắng: +1 điểm đạo hạnh; vừa lên cảnh giới mới thì tặng thêm điểm bảo hộ
    let pw = before.pts + 1;
    if (rankInfo(pw, steps).tier > before.tier) pw += Math.max(0, Math.floor(Number(this.cfg.rankPromoBonus) || 0));
    this.stats.setRp(winner, pw);
    const after = this.rankOf(winner);
    if (after.tier > before.tier) {
      result.rankUp = { name: winner.name, avatar: winner.avatar || '', tier: after.tier, tierName: after.name, fromTier: before.tier, fromName: before.name };
      this.rankUpInfo = result.rankUp;
    }
    // thua = "độ kiếp thất bại": mặc định mất HẾT điểm của cảnh giới đang đứng (giữ cảnh giới, về 0 điểm).
    // rankLossPenalty: 'tier' | 'all' (mất sạch về Phàm Nhân) | số điểm cố định | 0 (không mất)
    const cfgPen = this.cfg.rankLossPenalty;
    const mode = cfgPen === 'all' || cfgPen === Infinity ? 'all' : cfgPen === 'tier' ? 'tier' : 'num';
    const pen = mode === 'all' ? Infinity : mode === 'tier' ? beforeL.into : Math.max(0, Math.floor(Number(cfgPen) || 0));
    if (pen > 0 && loser && beforeL.pts > 0) {
      this.stats.setRp(loser, Math.max(0, beforeL.pts - pen));
      const afterL = this.rankOf(loser);
      result.rankDown = {
        name: loser.name, avatar: loser.avatar || '',
        tier: afterL.tier, tierName: afterL.name, fromTier: beforeL.tier, fromName: beforeL.name,
        lost: beforeL.pts - afterL.pts, fromPts: beforeL.into, toPts: afterL.into, all: mode === 'all',
      };
      this.rankDownInfo = result.rankDown;
    }
    let streak = 1;
    let steppedDown = false;
    if (this.cfg.winnerStays) {
      streak = (this.entering[winner.id] || 0) + 1; // chuỗi lúc vào ván (kể cả do chủ phòng đặt) + ván vừa thắng
      if (this.cfg.maxWinStreak > 0 && streak >= this.cfg.maxWinStreak) {
        steppedDown = true;
        this.champion = null;
        this.excludeNext = new Set([winner.id, loser.id]);
        result.note = `${winner.name} thắng ${streak} ván liên tiếp, nhường chỗ cho người khác!`;
      } else {
        this.champion = { ...winner, streak };
        this.excludeNext = new Set([loser.id]);
        if (streak >= 2) result.note = `Chuỗi thắng: ${streak} ván`;
      }
    } else {
      this.champion = null;
      this.excludeNext = new Set([winner.id, loser.id]);
    }
    result.streak = streak;
    return { winner, loser, streak, steppedDown };
  }

  rankOf(u) {
    return rankInfo(u && this.stats.rpOf ? this.stats.rpOf(u.id) : 0, this.cfg.rankWins);
  }

  rankBoard() {
    if (!this.stats.ranked) return [];
    if (!this._rb || this._rb.rev !== this.stats.rev || this._rb.n !== this.cfg.rankBoardRows) {
      const n = Math.max(1, Math.min(8, Number(this.cfg.rankBoardRows) || 4));
      this._rb = { rev: this.stats.rev, n: this.cfg.rankBoardRows, list: this.stats.ranked(n).map((e) => ({ ...e, rank: rankInfo(e.rp, this.cfg.rankWins) })) };
    }
    return this._rb.list;
  }

  finishWin(mark, line, now) {
    this.result = { type: 'win', winner: mark, text: `🏆 Đạo hữu ${this.players[mark].name} đại thắng!`, note: '', line };
    const s = this.settleWinner(mark, now, this.result);
    this.feed(this.result.text, 'win', mark);
    this.voice.win(s.winner, s.loser, { type: 'win', streak: s.streak, steppedDown: s.steppedDown, rankDown: !!this.result.rankDown }, now);
    this.announceRankUp(now);
    this.finishCommon(now);
  }

  finishForfeit(loserMark, why, now) {
    const winMark = other(loserMark);
    this.result = {
      type: 'forfeit',
      winner: winMark,
      text: `🏆 Đạo hữu ${this.players[winMark].name} đắc thắng! (${this.players[loserMark].name} ${why})`,
      note: '',
      line: null,
    };
    const s = this.settleWinner(winMark, now, this.result);
    this.feed(this.result.text, 'win', winMark);
    this.voice.win(
      s.winner,
      s.loser,
      { type: 'forfeit', why, streak: s.streak, steppedDown: s.steppedDown },
      now
    );
    this.announceRankUp(now);
    this.finishCommon(now);
  }

  /** Người thắng vừa lên cảnh giới mới: ghi vào dòng tin + MC chúc mừng đột phá. */
  announceRankUp(now) {
    const r = this.rankUpInfo;
    this.rankUpInfo = null;
    if (r) {
      this.feed(`⚡ Đạo hữu ${r.name} đột phá lên ${r.tierName}!`, 'win');
      if (this.voice.rankUp) this.voice.rankUp(r.name, r.tierName, now);
    }
    const d = this.rankDownInfo;
    this.rankDownInfo = null;
    if (d) {
      this.feed(`🌧️ Đạo hữu ${d.name} độ kiếp thất bại, mất ${d.lost} điểm đạo hạnh${d.tier < d.fromTier ? ', rớt xuống ' + d.tierName : ''}!`, 'info');
      if (this.voice.rankDown) this.voice.rankDown(d.name, d.tierName, now, d.lost);
    }
  }

  finishDraw(now) {
    this.result = { type: 'draw', winner: null, text: '🤝 Hòa cục! Bàn cờ đã kín quân', note: '', line: null };
    this.champion = null;
    this.excludeNext = new Set([this.players.X.id, this.players.O.id]);
    this.feed(this.result.text, 'win');
    this.voice.draw(now);
    this.finishCommon(now);
  }

  hardReset(now) {
    this.champion = null;
    this.entering = {};
    this.excludeNext.clear();
    this.gameNo += 1;
    this.feed('♻ Chủ phòng đã khai mở lại trận pháp', 'info');
    this.voice.hostReset(now);
    this.enterLobby(now);
  }

  // ---------- nhịp thời gian ----------
  tick(now = Date.now()) {
    this.interaction.frozen = !!this.cfg.farmOn && this.phase !== 'lobby'; // chế độ cày điểm: chỉ tính điểm trong vòng chờ sau trận
    switch (this.phase) {
      case 'lobby': {
        const left = this.phaseEndsAt - now;
        if (!this.lobbyWarned && left <= 10000 && this.lobbySecs >= 15) {
          this.lobbyWarned = true;
          this.voice.lobbyWarning(this.chooseCandidates().list, now);
        }
        if (left <= 0) {
          const c = this.chooseCandidates();
          if (c.ok) this.beginSelection(c, now);
          else this.waiting = true;
        }
        break;
      }
      case 'confirm': {
        if (!this.confirm) break;
        const left = this.phaseEndsAt - now;
        if (!this.confirm.warned && left > 0 && left <= 8000 && this.cfg.confirmSeconds >= 12) {
          this.confirm.warned = true;
          const pending = this.confirm.slots.filter((x) => !x.done).map((x) => x.user);
          if (pending.length) this.voice.confirmWarn(pending, Math.ceil(left / 1000), now);
        }
        if (left <= 0) this.confirmTimeout(now);
        break;
      }
      case 'coin': {
        const c = this.coin;
        if (c && c.revealed === false) {
          // (revealed === undefined là ván cũ lưu từ bản trước: đã chia X/O sẵn, không cần làm gì)
          if (c.face === null && now >= this.phaseStartedAt + c.drawMs) this.drawCoin();
          if (c.face !== null && now >= this.phaseStartedAt + c.revealMs) this.revealCoin(now);
        }
        if (now >= this.phaseEndsAt) {
          if (c && c.revealed === false) this.settleCoin(now);
          this.startPlaying(now);
        }
        break;
      }
      case 'playing':
        if (!this.warned && this.cfg.turnSeconds >= 15 && this.turnEndsAt - now <= 10000) {
          this.warned = true;
          this.voice.warn10(this.players[this.turn], now);
        }
        this.idleCheck(now);
        if (now >= this.turnEndsAt) this.onTurnTimeout(now);
        break;
      case 'finished':
        if (now >= this.phaseEndsAt) this.enterLobby(now, true);
        break;
      default:
    }
  }

  /** Người đang đến lượt im lặng quá lâu -> nhắc (có thể bình luận của họ bị TikTok ẩn: thêm @ phía trước). */
  idleCheck(now) {
    const wait = Number(this.cfg.idleHintSeconds) * 1000;
    if (!(wait > 0) || this.hinted || this.warned) return;
    if (now - this.turnStartedAt < wait || this.turnEndsAt - now <= 4000) return;
    if ((this.lastCommentAt[this.turn] || 0) >= this.turnStartedAt) return;
    const p = this.players[this.turn];
    if (!p) return;
    this.hinted = true;
    this.signPulseUntil = now + 12000; // biển báo ở góc màn hình nhấp nháy (không nói thành tiếng)
    this.feed(`💬 Đạo hữu ${p.name}: bình luận không hiện? Thêm @ hoặc @@ trước tọa độ (vd @@j9)`, 'warn', this.turn);
  }

  /** Nội dung biển báo nhỏ ở góc màn hình live. */
  signView(now) {
    if (this.cfg.showSign === false) return null;
    if (this.phase === 'confirm') return { lines: ['❤ Thả tim để xác nhận lên đài'], pulse: false };
    if (this.phase !== 'playing') return null;
    const lines = ['⌨ Xuất chiêu bằng tọa độ: j9 · k6 · ca 6', '👻 Bình luận không hiện? Thêm @ hoặc @@ trước (vd @@j9)'];
    if ((Number(this.cfg.extraTimesPerGame) || 0) > 0) lines.push('⏳ Gõ !them để xin thêm thời gian');
    lines.push('📊 Gõ !diem để xem cơ duyên (điểm) của đạo hữu');
    return { lines, pulse: now < (this.signPulseUntil || 0) };
  }

  // ---------- gửi cho giao diện ----------
  confirmView() {
    const slots = [];
    if (this.champion) slots.push({ ...brief(this.champion), champion: true, done: true });
    for (const x of this.confirm.slots) slots.push({ ...brief(x.user), done: x.done });
    return { slots, round: this.confirm.round };
  }

  getState(now = Date.now()) {
    const c = this.chooseCandidates();
    const hostFilter = (u) => this.cfg.hostCanPlay || !this.isHost(u);
    const top = this.interaction.top(8, { min: 1, filter: hostFilter }).map((u) => ({
      id: u.id,
      name: u.name,
      avatar: u.avatar,
      points: u.points,
      diamonds: u.diamonds,
      mark: this.markOf(u.id),
    }));
    const preview = [];
    if (this.champion && !c.booked) preview.push({ ...this.champion, champion: true });
    for (const u of c.list) preview.push(brief(u));

    return {
      serverNow: now,
      phase: this.phase,
      gameNo: this.gameNo,
      size: this.cfg.boardSize,
      rules: this.rulesText(),
      host: this.cfg.tiktokUsername || '',
      phaseStartedAt: this.phaseStartedAt,
      phaseEndsAt: this.phaseEndsAt,
      phaseTotalMs: this.phaseEndsAt - this.phaseStartedAt,
      turn: this.turn,
      turnEndsAt: this.turnEndsAt,
      turnTotalMs: this.cfg.turnSeconds * 1000,
      players: { X: this.players.X && { ...this.players.X, rank: this.rankOf(this.players.X) }, O: this.players.O && { ...this.players.O, rank: this.rankOf(this.players.O) } },
      rankBoard: this.rankBoard(),
      coin: this.coin,
      moves: this.game.moves.map((m) => ({ x: m.x, y: m.y, m: m.mark })),
      forbidden: this.cfg.forbidX && this.phase === 'playing' && this.turn === 'X' ? forbiddenCells(this.game, 'X') : [],
      banned: this.ban.cell ? [this.ban.cell] : [],
      banPicking: !!this.ban.picking,
      result: this.result,
      champion: this.champion ? { name: this.champion.name, streak: this.champion.streak } : null,
      booked: this.bookedList() ? this.bookedList().map((u) => u.name) : null,
      lobby: { need: c.need, waiting: this.waiting, preview },
      farm: this.cfg.farmOn ? { on: true, active: this.phase === 'lobby', secs: this.lobbySecs } : null,
      confirm: this.phase === 'confirm' && this.confirm ? this.confirmView() : null,
      sign: this.signView(now),
      top,
      wins: this.stats.top(3),
      feed: this.feedList,
      cues: this.voice.cues,
      connection: this.connection,
      settings: this.settingsView ? this.settingsView() : null,
    };
  }
}

module.exports = { Match };
