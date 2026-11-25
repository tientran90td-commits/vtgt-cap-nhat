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
const { checkAnnouncement } = require('./safety');

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

  /** Tim đến nhưng TikTok không cho biết ai thả: đếm lại, cứ 1 phút báo 1 lần trong dòng tin để chủ phòng biết. */
  onLikeIgnored() {
    this.likeIgnored = (this.likeIgnored || 0) + 1;
  }

  onLike(user, count, now = Date.now()) {
    this.interaction.addLike(user, count, now);
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
      this.match.feed(`🔁 Đạo hữu ${user.name} đã chia sẻ LIVE, cảm ơn!`, 'gift');
      this.commentator.shareThanks(user, now);
    }
  }

  onFollow(user, now = Date.now()) {
    const p = this.interaction.addFollow(user);
    if (p) {
      this.match.feed(`➕ Đạo hữu ${user.name} đã follow, chào mừng!`, 'gift');
      this.commentator.followThanks(user, now);
    }
  }

  /** Thông báo của chủ phòng: hiện bảng nhỏ trên màn hình live + MC đọc lên. */
  announce(text, seconds, now = Date.now()) {
    const t = String(text || '').replace(/\s+/g, ' ').trim().slice(0, 220);
    if (!t) return { ok: false, msg: 'Chưa gõ nội dung thông báo.' };
    const chk = checkAnnouncement(t); // không cho dẫn người xem ra ngoài TikTok / từ thô tục
    if (!chk.ok) return chk;
    let secs = Number(seconds);
    if (!(secs > 0)) secs = Math.min(30, Math.max(8, 5 + t.length * 0.1)); // tự tính theo độ dài chữ
    secs = Math.min(120, Math.max(3, secs));
    this.announcement = { id: now, text: t, until: now + secs * 1000 };
    const cue = this.match.voice.push('mc', 'Thông báo từ chủ phòng. ' + t, { at: now, prio: 3 });
    if (cue) cue.noCaption = true;
    return { ok: true };
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
      case 'announce':
        return done(this.announce(msg.text, msg.seconds, now));
      case 'announceClear':
        this.announcement = null;
        return done({ ok: true });
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

  /** Khán giả đang xem (không phải người chơi) để vẽ nhân vật đứng quanh phòng: tên + ảnh đại diện. */
  crowd(now = Date.now()) {
    const max = Number.isFinite(this.cfg.crowdMax) ? this.cfg.crowdMax : 10;
    if (max <= 0) return [];
    const m = this.match;
    return [...this.interaction.users.values()]
      .filter((u) => u.seenAt && now - u.seenAt < 15 * 60000 && !m.markOf(u.id))
      .sort((a, b) => b.seenAt - a.seenAt)
      .slice(0, max)
      .map((u) => ({ id: u.id, name: u.name, avatar: u.avatar || '' }));
  }

  tick(now = Date.now()) {
    this.match.tick(now);
    if (this.likeIgnored && now - (this.likeIgnoredAt || 0) > 60000) {
      this.match.feed(`ℹ ${this.likeIgnored} lượt tim trong 1 phút qua không rõ người thả (TikTok không gửi tên) nên không tính điểm được`, 'info');
      this.likeIgnored = 0;
      this.likeIgnoredAt = now;
    }
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
    s.demo = !!this.cfg.demo; // đang chạy chế độ thử (khán giả ảo)
    s.crowd = this.crowd(now);
    s.notice = this.notice;
    s.announce = this.announcement && now < this.announcement.until ? { id: this.announcement.id, text: this.announcement.text, until: this.announcement.until } : null;
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
