'use strict';
/*
 * DIỄN BIẾN TRẬN ĐẤU (máy trạng thái):
 *   lobby (đua tương tác)  ->  confirm (2 người được chọn THẢ TIM xác nhận)  ->  coin (tung đồng xu)
 *   ->  playing (đánh cờ)  ->  finished (kết quả)  ->  lobby ...
 * Người chơi đi cờ vua bằng cách bình luận nước đi, ví dụ: e4, Nf3, mã f3, e2e4. X = quân trắng, O = quân đen.
 */
const crypto = require('crypto');
const { ChessGame, PIECE_VN } = require('./game');
const { parseChessMove, parseCommand } = require('./commands');
const { rankInfo } = require('./rank');

const other = (m) => (m === 'X' ? 'O' : 'X');
const brief = (u) => ({
  id: u.id,
  uniqueId: u.uniqueId || '',
  name: u.name || u.uniqueId || 'Ẩn danh',
  avatar: u.avatar || '',
});

const COIN_FLIP_MS = 3400; // khớp với hiệu ứng đồng xu ở giao diện

class Match {
  constructor(cfg, interaction, stats, commentator) {
    this.cfg = cfg;
    this.interaction = interaction;
    this.stats = stats;
    this.voice = commentator;
    this.game = new ChessGame();

    this.connection = { status: 'starting', text: '' };
    this.feedList = [];
    this.feedSeq = 0;
    this.softNotes = new Map();

    this.gameNo = 0;
    this.champion = null; // { ...player, streak }
    this.excludeNext = new Set();
    this.firstLobby = true;
    this.confirm = null; // { slots:[{user,done}], round, warned } trong pha xác nhận thả tim
    this.confirmFailed = new Set();
    this.lastCommentAt = { X: 0, O: 0 };
    this.extraUsed = { X: 0, O: 0 }; // số lần đã xin thêm giờ trong ván
    this.sel = { X: null, O: null }; // quân đang chọn dở (gõ "e2" rồi "e4")
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
    return 'Cờ vua chuẩn: chiếu hết là thắng';
  }

  // ---------- chọn người chơi ----------
  eligible(u) {
    return !(this.isHost(u) && !this.cfg.hostCanPlay) && !(this.champion && u.id === this.champion.id);
  }

  chooseCandidates() {
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
    const secs = next && this.cfg.autoNextGame !== false ? this.cfg.nextLobbySeconds : this.cfg.lobbySeconds;
    this.lobbySecs = secs;
    this.phase = 'lobby';
    this.players = { X: null, O: null };
    this.game.reset();
    this.result = null;
    this.coin = null;
    this.waiting = false;
    this.confirm = null;
    this.confirmFailed = new Set();
    this.lobbyWarned = false;
    this.phaseStartedAt = now;
    this.phaseEndsAt = now + secs * 1000;
    this.turn = 'X';
    this.turnStartedAt = now;
    this.turnEndsAt = now;
    this.voice.lobbyStart(this.firstLobby, now, secs);
    if (secs >= 18) this.voice.howTo(now, 10000);
    this.firstLobby = false;
  }

  /** Chọn xong người chơi: nếu bật xác nhận thì sang pha "thả tim", không thì tung đồng xu luôn. */
  beginSelection(c, now) {
    if (this.cfg.confirmSeconds > 0) this.startConfirm(c, now);
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
    };
    const pending = this.confirm.slots.filter((x) => !x.done).map((x) => x.user);
    const names = c.list.map((u) => u.name).join(' và ');
    this.feed(`❤ ${names}: hãy THẢ TIM để xác nhận tham gia (${secs}s)`, 'info');
    this.voice.confirmAsk(pending, secs, now);
    this.checkConfirmed(now);
  }

  /** Người được chọn thả tim -> ghi nhận. */
  onLike(user, now = Date.now()) {
    if (this.phase !== 'confirm' || !this.confirm) return;
    const slot = this.confirm.slots.find((x) => x.user.id === user.id || (user.rawId && x.user.rawId && x.user.rawId === user.rawId));
    if (!slot || slot.done) return;
    slot.done = true;
    this.feed(`❤ ${slot.user.name} đã thả tim, sẵn sàng!`, 'gift');
    if (this.confirm.slots.every((x) => x.done)) this.checkConfirmed(now);
    else this.voice.confirmOk(slot.user, now);
  }

  checkConfirmed(now) {
    if (this.phase !== 'confirm' || !this.confirm) return;
    if (!this.confirm.slots.every((x) => x.done)) return;
    const list = this.confirm.slots.map((x) => x.user);
    this.confirm = null;
    this.startCoin({ list }, now);
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
        this.feed(`⏰ ${f.user.name} không thả tim, không còn ai thay thế. Chọn lại người chơi!`, 'warn');
        this.voice.confirmFail(f.user, null, now);
        this.confirm = null;
        this.enterLobby(now);
        return;
      }
      used.add(rep.id);
      const old = f.user;
      f.user = rep;
      f.done = this.isHost(rep);
      this.feed(`⏰ ${old.name} không thả tim. Mời ${rep.name} thay thế, hãy thả tim!`, 'warn');
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
    if (this.champion) {
      p1 = this.champion;
      p2 = chosen[0];
    } else {
      p1 = chosen[0];
      p2 = chosen[1];
    }
    const heads = crypto.randomInt(2) === 0;
    const xp = heads ? p1 : p2;
    const op = heads ? p2 : p1;

    this.voice.picked(this.champion, chosen, now);

    this.gameNo += 1;
    this.game.reset();
    this.result = null;
    this.players = { X: brief(xp), O: brief(op) };
    this.coin = {
      face: heads ? 'heads' : 'tails',
      heads: { name: brief(p1).name },
      tails: { name: brief(p2).name },
      first: { mark: 'X', name: brief(xp).name },
    };
    this.interaction.resetPoints();
    this.excludeNext.clear();
    this.stats.recordGame(p1);
    this.stats.recordGame(p2);

    this.phase = 'coin';
    this.phaseStartedAt = now;
    this.phaseEndsAt = now + this.cfg.coinSeconds * 1000;
    this.feed(`🪙 Tung đồng xu: ${this.players.X.name} cầm quân TRẮNG (đi trước)`, 'info');
    this.voice.coin(this.players.X, this.players.O, now, COIN_FLIP_MS);
  }

  startPlaying(now) {
    this.phase = 'playing';
    this.phaseStartedAt = now;
    this.timeouts = { X: 0, O: 0 };
    this.extraUsed = { X: 0, O: 0 };
    this.beginTurn('X', now);
    this.feed(`▶ Bắt đầu! Gõ nước đi như e4, Nf3, mã f3 hoặc e2e4`, 'info');
    this.voice.start(this.players.X, now);
  }

  beginTurn(mark, now) {
    this.turn = mark;
    this.turnStartedAt = now;
    this.turnEndsAt = now + this.cfg.turnSeconds * 1000;
    this.warned = false;
    this.hinted = false;
    // chọn quân dở được giữ qua lượt kế (20 giây) nếu cùng người; reset ở tryMove
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
    this.feed(`⏳ ${player.name} xin thêm ${secs} giây`, 'info', mark);
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
    this.feed(`⏳ Chủ phòng cộng thêm ${n} giây cho ${this.players[this.turn].name}`, 'info', this.turn);
    return { ok: true };
  }

  /** Khán giả gõ !diem: báo hạng + điểm của họ trong bảng top tương tác (hiện chữ, không đọc thành tiếng). */
  showRank(user) {
    const list = this.interaction.top(100000, { min: 1, filter: (u) => this.cfg.hostCanPlay || !this.isHost(u) });
    const i = list.findIndex((u) => u.id === user.id);
    const name = user.name || user.uniqueId || 'Bạn';
    let text;
    if (i < 0) {
      text = `📊 ${name}: bạn chưa có điểm. Bình luận, thả tim hoặc tặng quà để lên top!`;
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
      this.finishForfeit(mark, 'đã đầu hàng', now);
      return;
    }
    if (cmd === 'extend') {
      this.requestExtra(mark, now);
      return;
    }

    if (mark !== this.turn) {
      // chưa tới lượt: chỉ nhắc khi bình luận trông giống nước đi
      const peek = parseChessMove(text, this.game, null);
      if (peek.reason !== 'none') this.softNote(`turn:${user.id}`, `${this.players[mark].name}: chưa tới lượt của bạn`, 7000);
      return;
    }
    const sel = this.sel[mark] && now - this.sel[mark].at <= 20000 ? this.sel[mark] : null;
    const mv = parseChessMove(text, this.game, sel);
    const name = this.players[mark].name;
    if (mv.ok) {
      this.sel[mark] = null;
      this.tryMove(mark, mv.move, now);
      return;
    }
    switch (mv.reason) {
      case 'select':
        this.sel[mark] = { from: mv.from, targets: mv.targets, at: now };
        this.feed(`${name} chọn ${mv.from}`, 'info', mark);
        break;
      case 'ambiguous':
        this.softNote(`amb:${user.id}`, `${name}: ${mv.to} có ${mv.options.length} quân đi được - gõ \`${mv.options.map((o) => o.say).join('\` hoặc \`')}\``, 9000);
        break;
      case 'illegal':
        this.softNote(`ill:${user.id}`, `${name}: "${mv.text}" không đi được${this.game.inCheck() ? ' (vua đang bị chiếu!)' : ''}`, 6000);
        break;
      case 'empty':
        this.softNote(`emp:${user.id}`, `${name}: không có quân nào của bạn đi được tới ${mv.sq}`, 6000);
        break;
      case 'stuck':
        this.softNote(`stk:${user.id}`, `${name}: quân ở ${mv.sq} chưa đi được, chọn quân khác`, 6000);
        break;
      default:
        break;
    }
  }

  tryMove(mark, move, now) {
    const player = this.players[mark];
    const r = this.game.play(move);
    if (!r.ok) return;
    this.timeouts[mark] = 0;
    this.sel.X = null;
    this.sel.O = null;
    this.feed(`${player.name} đi ${this.moveText(r.move)}`, 'move', mark);
    this.afterMove(mark, r, now);
  }

  /** Mô tả nước đi bằng tiếng Việt: "mã g1 → f3" */
  moveText(m) {
    const verb = m.castle ? (m.castle === 'k' ? 'nhập thành ngắn' : 'nhập thành dài') : `${PIECE_VN[m.piece]} ${m.from} → ${m.to}`;
    const cap = m.captured ? ` (ăn ${PIECE_VN[m.captured]})` : '';
    const promo = m.promo ? ` phong ${PIECE_VN[m.promo]}` : '';
    return `${verb}${cap}${promo}${m.mate ? ' ♚ chiếu hết' : m.check ? ' + chiếu' : ''}`;
  }

  afterMove(mark, r, now) {
    const n = this.game.moves.length;
    const next = other(mark);
    const over = r.over;
    if (over && over.type === 'checkmate') {
      this.voice.move(this.players[mark], mark, r.move, null, n, now);
      this.finishWin(mark, null, now);
    } else if (over) {
      this.voice.move(this.players[mark], mark, r.move, null, n, now);
      this.finishDraw(now, over.text);
    } else {
      this.voice.move(this.players[mark], mark, r.move, this.players[next], n, now);
      if (r.move.check) this.feed(`⚠ Vua ${next === 'X' ? 'trắng' : 'đen'} đang bị chiếu!`, 'warn', next);
      this.beginTurn(next, now);
    }
  }

  onTurnTimeout(now) {
    const mark = this.turn;
    const player = this.players[mark];
    this.timeouts[mark] += 1;
    if (this.timeouts[mark] >= this.cfg.maxTimeouts) {
      this.finishForfeit(mark, 'hết giờ quá nhiều lần và bị xử thua', now);
      return;
    }
    const pick = this.game.suggestMove();
    if (!pick) {
      this.finishDraw(now, 'hết nước đi');
      return;
    }
    const r = this.game.play(pick);
    this.feed(
      `⏰ ${player.name} hết giờ! Tự động đi ${this.moveText(r.move)} (${this.timeouts[mark]}/${this.cfg.maxTimeouts})`,
      'warn',
      mark
    );
    this.voice.timeoutAuto(player, r.move, this.game.moves.length, now);
    this.sel.X = null;
    this.sel.O = null;
    if (r.over && r.over.type === 'checkmate') this.finishWin(mark, null, now);
    else if (r.over) this.finishDraw(now, r.over.text);
    else this.beginTurn(other(mark), now);
  }

  // ---------- lệnh từ bảng điều khiển ----------
  applySettings() {}

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
    this.champion = null;
    this.excludeNext.clear();
    this.enterLobby(now);
    this.feed(`🎯 Chủ phòng chọn ${list[0].name} và ${list[1].name} đấu với nhau`, 'info');
    if (opt.confirmLike && this.cfg.confirmSeconds > 0) this.startConfirm({ list }, now);
    else this.startCoin({ list }, now);
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
    if (this.cfg.celebrateOn && this.result && this.result.winner) secs = Math.max(secs, this.cfg.celebrateMinSeconds || 0);
    // có bảng "đột phá": cộng thêm thời gian để hiện sau video ăn mừng (~8 giây)
    const ru = this.result && this.result.rankUp ? 1 : 0;
    const rd = this.result && this.result.rankDown ? 1 : 0;
    if (ru || rd) {
      if (this.cfg.celebrateOn) secs += ru * 7 + rd * 6;
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
      streak = (this.champion && this.champion.id === winner.id ? this.champion.streak : 0) + 1;
      if (streak >= this.cfg.maxWinStreak) {
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
    this.result = { type: 'win', winner: mark, text: `🏆 ${this.players[mark].name} thắng! (chiếu hết)`, note: '', line };
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
      text: `🏆 ${this.players[winMark].name} thắng! (${this.players[loserMark].name} ${why})`,
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

  finishDraw(now, why = '') {
    this.result = { type: 'draw', winner: null, text: `🤝 Hòa!${why ? ' (' + why + ')' : ''}`, note: '', line: null };
    this.champion = null;
    this.excludeNext = new Set([this.players.X.id, this.players.O.id]);
    this.feed(this.result.text, 'win');
    this.voice.draw(now);
    this.finishCommon(now);
  }

  hardReset(now) {
    this.champion = null;
    this.excludeNext.clear();
    this.gameNo += 1;
    this.feed('♻ Chủ phòng đã làm mới trận đấu', 'info');
    this.voice.hostReset(now);
    this.enterLobby(now);
  }

  // ---------- nhịp thời gian ----------
  tick(now = Date.now()) {
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
      case 'coin':
        if (now >= this.phaseEndsAt) this.startPlaying(now);
        break;
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
    this.feed(`💬 ${p.name}: bình luận không hiện? Thêm @ hoặc @@ trước nước đi (vd @@e4)`, 'warn', this.turn);
  }

  /** Nội dung biển báo nhỏ ở góc màn hình live. */
  signView(now) {
    if (this.cfg.showSign === false) return null;
    if (this.phase === 'confirm') return { lines: ['❤ Thả tim để xác nhận tham gia'], pulse: false };
    if (this.phase !== 'playing') return null;
    const lines = ['⌨ Gõ nước đi: e4 · Nf3 · mã f3 · e2e4', '👻 Bình luận không hiện? Thêm @ hoặc @@ trước (vd @@e4)'];
    if (this.game.inCheck()) lines.unshift('⚠ Vua đang bị chiếu!');
    if ((Number(this.cfg.extraTimesPerGame) || 0) > 0) lines.push('⏳ Gõ !them để xin thêm giờ');
    lines.push('📊 Gõ !diem để xem hạng của bạn');
    return { lines, pulse: now < (this.signPulseUntil || 0) };
  }

  /** Quân đang được chọn của người đến lượt (để tô sáng các ô đi được) */
  selectionView(now) {
    if (this.phase !== 'playing') return null;
    const s = this.sel[this.turn];
    if (!s || now - s.at > 20000) return null;
    return { from: s.from, targets: s.targets, mark: this.turn };
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
    if (this.champion) preview.push({ ...this.champion, champion: true });
    for (const u of c.list) preview.push(brief(u));

    return {
      serverNow: now,
      phase: this.phase,
      gameNo: this.gameNo,
      size: 8,
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
      moves: this.game.moves.map((m) => ({
        n: m.n, m: m.mark, from: m.from, to: m.to, p: m.piece, cap: m.captured, promo: m.promo, ep: m.ep,
        castle: m.castle, rook: m.rook || null, check: m.check, mate: m.mate, san: m.san,
      })),
      select: this.selectionView(now),
      inCheck: this.phase === 'playing' ? this.game.inCheck() : false,
      turnColor: this.game.turn,
      result: this.result,
      champion: this.champion ? { name: this.champion.name, streak: this.champion.streak } : null,
      lobby: { need: c.need, waiting: this.waiting, preview },
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
