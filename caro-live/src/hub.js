'use strict';
const { Reminder } = require('./reminder');
/*
 * TRẠM ĐIỀU PHỐI: nhận sự kiện (bình luận, tim, quà, chia sẻ, follow) từ TikTok hoặc chế độ demo,
 * rồi chuyển đến đúng nơi: tính điểm tương tác + diễn biến trận đấu.
 * Cũng nhận lệnh từ bảng điều khiển (ván mới, bắt đầu ngay, đổi cài đặt...).
 */
const path = require('path');
const { Interaction } = require('./interaction');
const { Stats } = require('./stats');
const { Match } = require('./match');
const { Namer } = require('./names');
const { Commentator } = require('./commentator');
const { Settings } = require('./settings');
const { Script, SAMPLE, VAR_HELP } = require('./script');
const { parseMove } = require('./commands');
const { labelOf } = require('./game');

class Hub {
  constructor(cfg) {
    this.cfg = cfg;
    const dataDir = path.join(__dirname, '..', 'data');
    this.settings = new Settings(cfg, path.join(dataDir, 'cai-dat.json'));
    this.interaction = new Interaction(cfg.points);
    this.stats = new Stats(path.join(dataDir, 'thanh-tich.json'));
    this.namer = new Namer(path.join(dataDir, 'cach-doc-ten.json'));
    this.script = new Script(path.join(dataDir, 'thoai.json'));
    this.commentator = new Commentator(cfg, this.namer, this.script);
    this.commentator.phaseOf = () => (this.match ? this.match.phase : 'lobby');
    this.match = new Match(cfg, this.interaction, this.stats, this.commentator);
    this.match.settingsView = () => this.settings.snapshot();
    this.match.onPromo = (kind, text, now) => {
      this.promo = { id: now, kind, text, until: now + 11000 };
    };
    this.match.applySettings();
    this.chatLog = [];
    this.chatSeq = 0;
    this.notice = null; // thông báo cho bảng điều khiển
    this.reminder = new Reminder(cfg);
    this.promo = null; // khung nhắc follow/chia sẻ đang hiện trên màn hình live
    this.giftCues = new Map();
    this.demo = null; // bộ điều khiển chế độ thử (demo.js)
  }

  onComment(user, text, now = Date.now()) {
    const m = this.match;
    const before = m.game.moves.length;
    const phaseBefore = m.phase;
    this.interaction.addComment(user, now);
    this.commentator.greet(user, now);
    m.onComment(user, text, now);

    const parsed = parseMove(text, this.cfg.boardSize);
    const mark = m.markOf(user.id);
    const moved = m.game.moves.length > before;
    let label = parsed.ok ? parsed.label : null;
    if (!label && moved) {
      const lm = m.game.moves[m.game.moves.length - 1]; // nước đi ghép từ 2 bình luận ("j" rồi "9")
      label = labelOf(lm.x, lm.y);
    }
    let status = null;
    if (label) {
      status = moved ? 'moved' : mark && phaseBefore === 'playing' ? 'ignored' : 'seen';
    }
    this.chatLog.push({
      id: ++this.chatSeq,
      name: user.name,
      text: String(text).slice(0, 70),
      move: label,
      mark,
      status,
    });
    if (this.chatLog.length > 14) this.chatLog.shift();
  }

  onLike(user, count, now = Date.now()) {
    this.interaction.addLike(user, count);
    this.match.onLike(user, now); // pha xác nhận: người được chọn thả tim -> ghi nhận
  }

  onGift(user, gift, now = Date.now()) {
    const pts = this.interaction.addGift(user, Number(gift.diamonds) || 0, Number(gift.count) || 1);
    if (gift.announce !== false) {
      const n = Number(gift.count) || 1;
      const pt = pts ? ` (+${pts} điểm)` : '';
      this.match.feed(`🎁 Đạo hữu ${user.name} ban tặng ${gift.name}${n > 1 ? ' x' + n : ''}${pt}`, 'gift');
      const cue = this.commentator.giftThanks(user, gift, now);
      if (cue && gift.key) {
        if (this.giftCues.size > 60) this.giftCues.clear();
        this.giftCues.set(gift.key, cue);
      }
    }
  }

  /** Quà liên tiếp (combo): chỉ cộng thêm điểm, không đăng thêm dòng thông báo. */
  onGiftPoints(user, unitDiamonds, delta, key, totalCount) {
    this.interaction.addGift(user, unitDiamonds, delta);
    if (key && this.giftCues.has(key)) this.commentator.updateGiftThanks(this.giftCues.get(key), totalCount);
  }

  onShare(user, now = Date.now()) {
    const p = this.interaction.addShare(user);
    if (p) {
      this.match.feed(`🔁 Đạo hữu ${user.name} chia sẻ LIVE (+${p} điểm)`, 'gift');
      this.commentator.shareThanks(user, now);
    }
  }

  onFollow(user, now = Date.now()) {
    const p = this.interaction.addFollow(user);
    if (p) {
      this.match.feed(`➕ Đạo hữu ${user.name} đã follow (+${p} điểm)`, 'gift');
      this.commentator.followThanks(user, now);
    }
  }

  setConnection(status, text) {
    this.match.connection = { status, text };
  }

  /** Lệnh từ bảng điều khiển. Trả về { ok, msg }. */
  command(msg, now = Date.now()) {
    const m = this.match;
    const done = (r) => {
      if (r && r.ok === false) this.notice = { id: Date.now(), text: r.msg || 'Không thực hiện được', kind: 'warn' };
      return r || { ok: true };
    };
    switch (msg && msg.cmd) {
      case 'reset':
        m.hardReset(now);
        return done({ ok: true });
      case 'startNow':
        return done(m.startNow(now));
      case 'skipTurn':
        return done(m.skipTurn(now));
      case 'addTime':
        return done(m.extendTurn(msg.seconds, now));
      case 'skipConfirm':
        return done(m.skipConfirm(now));
      case 'pick':
        return done(m.pickPlayers(msg.ids, { force: !!msg.force, confirmLike: !!msg.confirmLike }, now));
      case 'forfeit':
        return done(m.forfeitPlayer(msg.mark === 'O' ? 'O' : 'X', now));
      case 'settings': {
        const changed = this.settings.apply(msg.patch);
        m.applySettings();
        return done({ ok: true, changed });
      }
      case 'script': {
        const ok = this.script.set(String(msg.key), { text: msg.text, enabled: msg.enabled });
        return done(ok ? { ok: true } : { ok: false, msg: 'Không tìm thấy câu thoại này.' });
      }
      case 'scriptReset':
        if (msg.key === '*') this.script.resetAll();
        else this.script.reset(String(msg.key));
        return done({ ok: true });
      case 'demo': {
        if (msg.on && !this.demo) {
          m.hardReset(now);
          this.demo = require('./demo').startDemo(this, this.cfg);
          this.cfg.demo = true;
          this.notice = { id: Date.now(), text: 'Đã bật chế độ thử (khán giả ảo).', kind: 'info' };
        } else if (!msg.on && this.demo) {
          this.demo.stop();
          this.demo = null;
          this.cfg.demo = false;
          m.hardReset(now);
          this.interaction.purge('demo:');
          this.notice = { id: Date.now(), text: 'Đã tắt chế độ thử.', kind: 'info' };
        }
        return done({ ok: true });
      }
      case 'test': {
        if (!this.cfg.testApi) return done({ ok: false, msg: 'Chức năng gõ thử đang tắt.' });
        const id = String(msg.user || 'tester').toLowerCase().slice(0, 30) || 'tester';
        const nm = String(msg.name || id).slice(0, 30);
        const user = { id, uniqueId: id, name: nm, avatar: '/demo-avatar?n=' + encodeURIComponent(nm) };
        if (msg.kind === 'gift') {
          this.onGift(user, { name: String(msg.gift || 'Quà thử'), diamonds: Number(msg.diamonds) || 1, count: 1 });
        } else if (msg.kind === 'like') {
          this.onLike(user, Number(msg.count) || 15);
        } else {
          this.onComment(user, String(msg.text || ''));
        }
        return done({ ok: true });
      }
      default:
        return done({ ok: false, msg: 'Lệnh không hợp lệ' });
    }
  }

  /** Danh sách tất cả người đã tương tác (cho bảng điều khiển chọn người solo). */
  viewers() {
    const m = this.match;
    return [...this.interaction.users.values()]
      .sort((a, b) => b.points - a.points || b.diamonds - a.diamonds || a.order - b.order)
      .slice(0, 500)
      .map((u) => ({
        id: u.id,
        name: u.name,
        uniqueId: u.uniqueId,
        avatar: u.avatar,
        points: u.points,
        diamonds: u.diamonds,
        mark: m.markOf(u.id),
        host: m.isHost(u),
      }));
  }

  tick(now = Date.now()) {
    this.match.tick(now);
    this.commentator.flushDeferred(now);
    const kind = this.reminder.tick(now, this.match.phase);
    if (kind) {
      const cue = this.match.voice.remind(kind, now);
      if (cue) this.promo = { id: now, kind, text: cue.text, until: now + 11000 };
    }
  }

  getState(now = Date.now()) {
    const s = this.match.getState(now);
    s.recent = this.chatLog;
    s.notice = this.notice;
    s.promo = this.promo && now < this.promo.until ? this.promo : null;
    s.demo = !!this.demo;
    s.script = this.script.list();
    s.scriptSample = SAMPLE;
    s.scriptVars = VAR_HELP;
    s.testApi = !!this.cfg.testApi;
    return s;
  }
}

module.exports = { Hub };
