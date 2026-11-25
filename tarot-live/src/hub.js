'use strict';
/*
 * TRẠM ĐIỀU PHỐI TAROT: nhận bình luận / quà từ TikTok (hoặc chế độ thử), xếp hàng chờ,
 * lần lượt rút bài và phát "buổi bói" cho màn hình live. Cũng nhận lệnh từ bảng điều khiển.
 */
const path = require('path');
const { Settings } = require('./settings');
const { draw } = require('./deck');
const { build, introText, TOPIC_LABEL, POS } = require('./reading');
const ai = require('./ai');
const { parseInfo, mergeInfo, findDate, ageOf, profile } = require('./info');
const { parseRequest } = require('./parse');
const { checkAnnouncement } = require('./safety');

const GAP_MS = 2500; // nghỉ giữa 2 lượt

class Hub {
  constructor(cfg) {
    this.cfg = cfg;
    this.settings = new Settings(cfg, path.join(__dirname, '..', 'data', 'cai-dat.json'));
    this.connection = { status: 'wait', text: 'Chưa kết nối' };
    this.queue = []; // {id, userId, name, avatar, spread, topic, sensitive, vip, at}
    this.current = null; // buổi bói đang chạy
    this.history = [];
    this.feedLog = [];
    this.cues = []; // câu MC cần đọc (màn hình live đọc theo id mới)
    this.seq = 0;
    this.count = 0;
    this.cooldown = new Map(); // userId -> thời điểm được xin lại
    this.diamonds = new Map(); // userId -> tổng kim cương đã tặng (chỉ để xếp ưu tiên nếu bật)
    this.idleSince = Date.now();
    this.nextAt = 0;
    this.nextInvite = Date.now() + 20000;
    this.lastAnnounce = Date.now();
    this.announceShow = null;
    this.users = new Map(); // người xem đã thấy (để hiện số người tương tác)
    this.phase = null; // giai đoạn trước khi bói: {kind:'collect'|'prepare', ...}
    this.interaction = null; // (tiktok.js hỏi, không dùng ở game này)
  }

  // ---------------------------------------------------------------- tiện ích
  feed(text, kind = 'info') {
    this.feedLog.push({ id: ++this.seq, text, kind });
    if (this.feedLog.length > 10) this.feedLog.shift();
  }

  cue(text, prio = 2) {
    this.cues.push({ id: ++this.seq, text, prio });
    if (this.cues.length > 6) this.cues.shift();
  }

  setConnection(status, text) {
    this.connection = { status, text };
  }

  // ---------------------------------------------------------------- sự kiện TikTok
  onComment(user, text, now = Date.now()) {
    this.users.set(user.id, now);
    const req = parseRequest(text);
    if (!req && this.phase && this.phase.kind === 'collect' && this.phase.item.userId === user.id) return this.onInfo(user, text, now);
    if (!req) return null;
    return this.request(user, req, now);
  }

  /** Khán giả xin 1 lượt bói. Trả về { ok, msg }. */
  request(user, req, now = Date.now()) {
    const s = this.settings.v;
    if (s.paused) return { ok: false, msg: 'Đang tạm ngưng nhận lượt' };
    if (this.current && this.current.userId === user.id) return { ok: false, msg: 'Đang bói cho người này' };
    if (this.queue.some((q) => q.userId === user.id)) return { ok: false, msg: 'Đã có trong hàng chờ' };
    const wait = (this.cooldown.get(user.id) || 0) - now;
    if (wait > 0) {
      this.feed(`⏳ ${user.name}: vui lòng chờ ${Math.ceil(wait / 1000)} giây nữa để xin lượt mới`, 'warn');
      return { ok: false, msg: 'Chưa hết thời gian chờ' };
    }
    if (this.queue.length >= s.maxQueue) {
      this.feed(`📋 Hàng chờ đang đầy, ${user.name} thử lại sau nhé`, 'warn');
      return { ok: false, msg: 'Hàng chờ đầy' };
    }
    let spread = req.spread || s.defaultSpread;
    if (spread === 3 && !s.allowThree) spread = 1;
    if (spread === 5 && !s.allowFive) spread = s.allowThree ? 3 : 1;
    const item = {
      id: ++this.seq,
      userId: user.id,
      name: user.name,
      avatar: user.avatar || '',
      spread,
      topic: req.topic,
      sensitive: !!req.sensitive,
      vip: s.giftPriority && (this.diamonds.get(user.id) || 0) > 0,
      at: now,
    };
    this.queue.push(item);
    this.sortQueue();
    this.feed(`🔮 ${user.name} xin bói ${spread} lá`, 'req');
    return { ok: true, id: item.id };
  }

  sortQueue() {
    this.queue.sort((a, b) => (b.vip ? 1 : 0) - (a.vip ? 1 : 0) || a.at - b.at || a.id - b.id);
  }

  onLike() {}
  onLikeIgnored() {}

  onGift(user, gift, now = Date.now()) {
    this.diamonds.set(user.id, (this.diamonds.get(user.id) || 0) + (Number(gift.diamonds) || 0) * (Number(gift.count) || 1));
    if (gift.announce !== false) {
      const n = Number(gift.count) || 1;
      this.feed(`🎁 ${user.name} tặng ${gift.name}${n > 1 ? ' x' + n : ''}`, 'gift');
      this.cue(`Cảm ơn ${user.name} đã tặng ${gift.name}.`, 1);
    }
  }

  onGiftPoints(user, unitDiamonds, delta) {
    this.diamonds.set(user.id, (this.diamonds.get(user.id) || 0) + (Number(unitDiamonds) || 0) * (Number(delta) || 0));
  }

  onShare(user) {
    this.feed(`🔁 ${user.name} đã chia sẻ LIVE, cảm ơn!`, 'gift');
  }

  onFollow(user) {
    this.feed(`➕ ${user.name} đã follow, chào mừng!`, 'gift');
  }

  // ---------------------------------------------------------------- nhận thông tin người được chọn
  /** Người được chọn bình luận họ tên / ngày sinh / chuyện muốn xem. */
  onInfo(user, text, now) {
    const ph = this.phase;
    const got = parseInfo(text, user.name);
    if (!got.dob && !got.name && !got.question) return null;
    ph.info = ph.info ? mergeInfo(ph.info, got) : got;
    const i = ph.info;
    if (!ph.ack) {
      ph.ack = true;
      this.feed(`📝 Đã nhận thông tin của ${user.name}`, 'req');
    }
    // đủ ngày sinh + (tên hoặc chuyện muốn xem) thì chốt sau 3 giây (chờ thêm bình luận bổ sung)
    if (i.dob && (i.name || i.question)) ph.until = Math.min(ph.until, now + (this.cfg.fast ? 300 : 3000));
    return { ok: true };
  }

  /** Bắt đầu 1 lượt: hỏi thông tin (nếu bật) -> nhờ AI viết lời đọc (nếu bật) -> bói. */
  begin(item, now) {
    const s = this.settings.v;
    const manual = !item.userId; // chủ phòng tự rút, hoặc lượt tự động
    if (s.askInfo && !manual && !item.info) {
      this.phase = { kind: 'collect', item, info: null, until: now + s.collectSeconds * 1000, startedAt: now };
      this.cue(`${item.name} ơi, đến lượt bạn rồi. Bạn hãy bình luận họ tên, ngày tháng năm sinh và chuyện muốn xem nhé. Ví dụ: ${item.name}, 20 tháng 8 năm 1998, tình duyên.`, 3);
      return;
    }
    this.prepare(item, item.info || null, now);
  }

  prepare(item, info, now) {
    const s = this.settings.v;
    const prof = info ? profile(info) : null;
    let topic = item.topic !== 'general' ? item.topic : info ? info.topic : 'general';
    const age = info && info.dob ? ageOf(info.dob) : null;
    if (age != null && age < 18 && topic === 'love') topic = 'general'; // người dưới 18: không đọc chủ đề tình duyên
    const sensitive = !!item.sensitive || !!(info && info.sensitive);
    const name = (info && info.name) || item.name;
    const drawn = draw(item.spread, s.reverseChance);
    const job = { item, info, prof, topic, sensitive, name, drawn };
    const useAi = (s.aiProvider === 'claude' || s.aiProvider === 'gemini') && ai.hasKey();
    if (!useAi) return this.start(job, now, null, false);
    // AI đang viết: MC nói lời chào trong lúc chờ
    const intro = introText(name, prof, sensitive);
    this.cue(intro, 3);
    const positions = POS[item.spread][sensitive ? 'general' : topic];
    const req = {
      name,
      dob: info && info.dob ? info.dob : null,
      profile: prof,
      sensitive,
      topicLabel: TOPIC_LABEL[sensitive ? 'general' : topic],
      cards: drawn.map((d, i) => ({ pos: positions[i], vi: d.card.vi, rev: d.rev, kw: d.rev ? d.card.kRev : d.card.kUp })),
    };
    const ph = { kind: 'prepare', job, until: now + (Number(s.aiTimeout) + 3) * 1000, startedAt: now, result: undefined };
    this.phase = ph;
    ai.generate(req, s).then(
      (r) => { ph.result = r; },
      (e) => { ph.result = null; this.feed(`⚠️ AI không dùng được (${String(e.message).slice(0, 60)}), đọc bằng lời viết sẵn`, 'warn'); },
    );
  }

  // ---------------------------------------------------------------- chạy buổi bói
  start(job, now, aiResult, skipIntro) {
    const s = this.settings.v;
    const reading = build(job.drawn, { name: job.name }, {
      topic: job.topic,
      sensitive: job.sensitive,
      speed: s.readSpeed,
      number: this.count,
      fast: this.cfg.fast,
      profile: job.prof,
      ai: aiResult || null,
      skipIntro: !!skipIntro,
    });
    this.count++;
    this.phase = null;
    const item = job.item;
    this.current = {
      id: ++this.seq,
      userId: item.userId || '',
      user: { name: job.name, avatar: item.avatar || '' },
      auto: !!item.auto,
      startedAt: now,
      ...reading,
    };
  }

  /** Chuyển giai đoạn: hết giờ hỏi thông tin -> chuẩn bị; AI xong hoặc quá hạn -> bói. */
  phaseTick(now) {
    const ph = this.phase;
    if (!ph) return;
    if (ph.kind === 'collect') {
      if (now < ph.until) return;
      this.prepare(ph.item, ph.info, now);
    } else if (ph.kind === 'prepare') {
      if (ph.result === undefined && now < ph.until) return;
      this.start(ph.job, now, ph.result || null, true);
    }
  }

  finish(now) {
    const c = this.current;
    if (!c) return;
    const s = this.settings.v;
    this.history.unshift({ name: c.user.name, cards: c.cards.map((x) => x.vi + (x.rev ? ' (ngược)' : '')), topic: c.topicLabel, auto: c.auto });
    if (this.history.length > 8) this.history.pop();
    if (c.userId && s.userCooldown > 0) this.cooldown.set(c.userId, now + s.userCooldown * 1000);
    if (this.cooldown.size > 400) for (const [k, t] of this.cooldown) if (t < now) this.cooldown.delete(k);
    this.current = null;
    this.nextAt = now + GAP_MS;
    this.idleSince = now + GAP_MS;
    this.nextInvite = now + 25000;
  }

  tick(now = Date.now()) {
    const s = this.settings.v;
    if (this.current && now >= this.current.startedAt + this.current.total) this.finish(now);
    if (!this.current && this.phase) this.phaseTick(now);
    if (!this.current && !this.phase && now >= this.nextAt) {
      if (this.queue.length) {
        this.begin(this.queue.shift(), now);
      } else if (s.autoDraw && now - this.idleSince >= s.autoIdleSeconds * 1000) {
        this.begin({ name: 'Cả phòng', spread: 1, topic: 'general', auto: true }, now);
      }
    }
    // nhắc khán giả cách gõ lệnh khi màn hình đang chờ
    if (!this.current && !this.phase && !s.paused && now >= this.nextInvite) {
      this.nextInvite = now + 60000;
      this.cue('Bạn nào muốn rút bài Tarot thì gõ chữ !bai vào bình luận nhé. Gõ !bai 3 để rút ba lá.', 1);
    }
    // thông báo của chủ phòng, lặp lại theo phút
    if (s.announceText && s.announceEvery > 0 && now - this.lastAnnounce >= s.announceEvery * 60000) this.announceNow(now);
    if (this.announceShow && now > this.announceShow.until) this.announceShow = null;
    if (this.cues.length && this.cues[0].id < this.seq - 40) this.cues.shift();
  }

  announceNow(now = Date.now()) {
    const t = this.settings.v.announceText;
    if (!t) return { ok: false, msg: 'Chưa có nội dung thông báo' };
    const c = checkAnnouncement(t);
    if (!c.ok) return { ok: false, msg: c.msg };
    this.lastAnnounce = now;
    this.announceShow = { id: ++this.seq, text: t, until: now + 12000 };
    this.cue(t, 2);
    return { ok: true };
  }

  // ---------------------------------------------------------------- lệnh từ bảng điều khiển
  command(msg, now = Date.now()) {
    switch (msg.cmd) {
      case 'set':
        return this.settings.apply(msg.values || {});
      case 'skip':
        if (this.phase) this.phase = null;
        if (this.current) this.finish(now);
        return { ok: true };
      case 'clear':
        this.queue = [];
        return { ok: true };
      case 'remove':
        this.queue = this.queue.filter((q) => q.id !== Number(msg.id));
        return { ok: true };
      case 'bump': {
        const q = this.queue.find((x) => x.id === Number(msg.id));
        if (q) {
          q.vip = true;
          q.at = 0;
          this.sortQueue();
        }
        return { ok: true };
      }
      case 'draw': {
        // chủ phòng tự rút cho 1 người (đứng đầu hàng chờ)
        const name = String(msg.name || '').trim().slice(0, 30) || 'Bạn';
        const spread = [3, 5].includes(Number(msg.spread)) ? Number(msg.spread) : 1;
        const topic = ['love', 'work'].includes(msg.topic) ? msg.topic : 'general';
        const dob = findDate(String(msg.dob || ''));
        const q = parseInfo(String(msg.question || ''), name);
        const info = dob || q.question ? { name: '', dob: dob ? { d: dob.d, m: dob.m, y: dob.y } : null, question: q.question, topic: q.topic, sensitive: q.sensitive } : null;
        this.queue.unshift({ id: ++this.seq, userId: '', name, avatar: '', spread, topic, sensitive: false, vip: true, at: 0, info });
        return { ok: true };
      }
      case 'announce':
        return this.announceNow(now);
      case 'testDraw':
        this.current = null;
        this.phase = null;
        this.prepare({ name: 'Bạn', spread: [3, 5].includes(Number(msg.spread)) ? Number(msg.spread) : 1, topic: 'general' }, null, now);
        return { ok: true };
      default:
        return { ok: false, msg: 'Lệnh lạ' };
    }
  }

  // ---------------------------------------------------------------- dữ liệu gửi cho trang web
  getState(now = Date.now()) {
    const s = this.settings.snapshot();
    return {
      serverNow: now,
      connection: this.connection,
      demo: !!this.cfg.demo,
      settings: s,
      current: this.current,
      collect: this.phase && this.phase.kind === 'collect' ? { name: this.phase.item.name, avatar: this.phase.item.avatar || '', until: this.phase.until, got: !!this.phase.info } : null,
      preparing: this.phase && this.phase.kind === 'prepare' ? { name: this.phase.job.name, avatar: this.phase.job.item.avatar || '', until: this.phase.until } : null,
      ai: { provider: this.settings.v.aiProvider, hasKey: ai.hasKey() },
      queue: this.queue.slice(0, 20).map((q) => ({ id: q.id, name: q.name, avatar: q.avatar, spread: q.spread, topic: q.topic, vip: q.vip })),
      queueTotal: this.queue.length,
      history: this.history,
      feed: this.feedLog,
      cues: this.cues,
      announce: this.announceShow,
      count: this.count,
      viewers: this.users.size,
    };
  }
}

module.exports = { Hub };
