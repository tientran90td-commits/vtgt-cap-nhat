'use strict';
/*
 * TRẠM ĐIỀU PHỐI TAROT (luồng mới):
 *  1) Mọi tương tác (bình luận, thả tim, chia sẻ, follow, quà) cộng điểm cho người xem.
 *  2) Khi màn hình rảnh, game CHỌN NGƯỜI ĐIỂM CAO NHẤT (người chưa xem hết 3 chủ đề) và mời họ bình luận
 *     họ tên + ngày/tháng/năm sinh + chuyện muốn xem.
 *  3) Nhận diện được bình luận đó là gửi AI ngay. Trong lúc chờ AI: xáo bài, chia bài, lật bài, đọc tên 5 lá.
 *  4) AI trả về (hoặc dùng lời viết sẵn nếu AI lỗi / tắt) thì đọc từng lá, tổng kết, lời chúc. Luôn trải 5 lá.
 *  Người đã xem một chủ đề thì không xem lại chủ đề đó; chủ đề khác vẫn được nếu họ lại tương tác tốt (điểm tính lại từ 0 sau mỗi lượt).
 */
const path = require('path');
const { Settings } = require('./settings');
const { draw } = require('./deck');
const { makeCards, showSteps, readSteps, layout, TOPIC_LABEL } = require('./reading');
const { POS } = require('./reading');
const ai = require('./ai');
const { parseRequest } = require('./parse');
const { parseInfo, mergeInfo, findDate, profile } = require('./info');
const { checkAnnouncement } = require('./safety');

const GAP_MS = 2500; // nghỉ giữa 2 lượt
const ACTIVE_MS = 5 * 60 * 1000; // chỉ chọn người vừa tương tác trong 5 phút gần đây
const TOPICS = ['general', 'love', 'work'];
const SCORE = { comment: 1, ask: 3, like: 0.05, share: 8, follow: 6, gift: 4, diamond: 0.2 };

class Hub {
  constructor(cfg) {
    this.cfg = cfg;
    this.settings = new Settings(cfg, path.join(__dirname, '..', 'data', 'cai-dat.json'));
    this.connection = { status: 'wait', text: 'Chưa kết nối' };
    this.eng = new Map(); // userId -> { id, name, avatar, score, lastAt, lastScoreAt, lastText, lastAsk }
    this.done = new Map(); // userId -> Set(chủ đề đã xem trong buổi live này)
    this.banned = new Set(); // người chủ phòng loại khỏi danh sách chọn
    this.forced = []; // lượt chủ phòng tự rút / ưu tiên
    this.current = null; // buổi bói đang chạy
    this.pendingAi = null; // { result, deadline, job }
    this.phase = null; // đang hỏi thông tin: { kind: 'collect', item, info, until }
    this.history = [];
    this.feedLog = [];
    this.cues = [];
    this.seq = 0;
    this.count = 0;
    this.diamonds = new Map();
    this.idleSince = Date.now();
    this.nextAt = 0;
    this.nextInvite = Date.now() + 20000;
    this.lastAnnounce = Date.now();
    this.announceShow = null;
    this.users = new Map();
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

  // ---------------------------------------------------------------- điểm tương tác
  touch(user, now) {
    let e = this.eng.get(user.id);
    if (!e) {
      e = { id: user.id, name: user.name, avatar: user.avatar || '', score: 0, lastAt: now, lastScoreAt: 0, lastText: '', lastAsk: 0 };
      this.eng.set(user.id, e);
      if (this.eng.size > 3000) for (const [k, v] of this.eng) if (now - v.lastAt > 30 * 60 * 1000) this.eng.delete(k);
    }
    e.name = user.name || e.name;
    if (user.avatar) e.avatar = user.avatar;
    e.lastAt = now;
    return e;
  }

  addScore(user, pts, now) {
    if (this.banned.has(user.id)) return;
    this.touch(user, now).score += pts;
  }

  /** Bình luận thường: cộng 1 điểm, chống spam (cách nhau >= 4 giây, không lặp câu trước). */
  scoreComment(user, text, now) {
    const e = this.touch(user, now);
    const t = String(text || '').trim().toLowerCase();
    if (this.banned.has(user.id) || t.length < 2 || t === e.lastText || now - e.lastScoreAt < (this.cfg.fast ? 0 : 4000)) return;
    e.lastText = t;
    e.lastScoreAt = now;
    e.score += SCORE.comment;
  }

  // ---------------------------------------------------------------- sự kiện TikTok
  onComment(user, text, now = Date.now()) {
    this.users.set(user.id, now);
    const req = parseRequest(text);
    const ph = this.phase;
    if (ph && ph.kind === 'collect' && ph.item.userId === user.id && !req) return this.onInfo(user, text, now);
    if (req) {
      const e = this.touch(user, now);
      if (!this.banned.has(user.id) && now - e.lastAsk > (this.cfg.fast ? 0 : 60000)) {
        e.lastAsk = now;
        e.score += SCORE.ask; // gõ !bai = xin được chọn
        this.feed(`🔮 ${user.name} muốn được xem bài`, 'req');
      }
      return { ok: true };
    }
    this.scoreComment(user, text, now);
    return { ok: true };
  }

  onLike(user, n, now = Date.now()) {
    this.addScore(user, Math.min(Number(n) || 1, 30) * SCORE.like, now);
  }

  onLikeIgnored() {}

  onGift(user, gift, now = Date.now()) {
    const n = Number(gift.count) || 1;
    const d = (Number(gift.diamonds) || 0) * n;
    this.diamonds.set(user.id, (this.diamonds.get(user.id) || 0) + d);
    this.addScore(user, SCORE.gift + (this.settings.v.giftPriority ? d * SCORE.diamond : 0), now);
    if (gift.announce !== false) {
      this.feed(`🎁 ${user.name} tặng ${gift.name}${n > 1 ? ' x' + n : ''}`, 'gift');
      this.cue(`Cảm ơn ${user.name} đã tặng ${gift.name}.`, 1);
    }
  }

  onGiftPoints(user, unitDiamonds, delta) {
    this.diamonds.set(user.id, (this.diamonds.get(user.id) || 0) + (Number(unitDiamonds) || 0) * (Number(delta) || 0));
  }

  onShare(user, now = Date.now()) {
    this.addScore(user, SCORE.share, now);
    this.feed(`🔁 ${user.name} đã chia sẻ LIVE, cảm ơn!`, 'gift');
  }

  onFollow(user, now = Date.now()) {
    this.addScore(user, SCORE.follow, now);
    this.feed(`➕ ${user.name} đã follow, chào mừng!`, 'gift');
  }

  // ---------------------------------------------------------------- chọn người
  doneOf(userId) {
    return this.done.get(userId) || new Set();
  }

  /** Danh sách người đủ điều kiện, điểm cao trước. */
  candidates(now = Date.now()) {
    const min = this.settings.v.minScore;
    const cur = this.current && this.current.userId;
    const ph = this.phase && this.phase.item.userId;
    const out = [];
    for (const e of this.eng.values()) {
      if (this.banned.has(e.id) || e.id === cur || e.id === ph) continue;
      if (now - e.lastAt > ACTIVE_MS) continue;
      if (this.doneOf(e.id).size >= TOPICS.length) continue;
      out.push(e);
    }
    out.sort((a, b) => b.score - a.score || a.lastAt - b.lastAt);
    return { all: out, ready: out.filter((e) => e.score >= min) };
  }

  topicOf(info) {
    return info && !info.sensitive && TOPICS.includes(info.topic) ? info.topic : 'general';
  }

  labelsOf(set) {
    return [...set].map((t) => TOPIC_LABEL[t]).join(', ');
  }

  // ---------------------------------------------------------------- hỏi thông tin người được chọn
  begin(item, now) {
    const s = this.settings.v;
    if (s.askInfo && item.userId && !item.info) {
      const e = this.eng.get(item.userId);
      if (e) e.score = 0; // sau lượt này phải tương tác tiếp mới được chọn lại
      this.phase = { kind: 'collect', item, info: null, until: now + s.collectSeconds * 1000, startedAt: now, dupAt: 0 };
      const seen = this.doneOf(item.userId);
      const again = seen.size ? ` Bạn đã xem ${this.labelsOf(seen)} rồi, lần này hãy chọn chủ đề khác nhé.` : '';
      this.cue(`${item.name} là người tương tác tốt nhất lúc này! Mời bạn bình luận họ tên, ngày tháng năm sinh và chuyện muốn xem. Ví dụ: ${item.name}, 20 tháng 8 năm 1998, tình duyên.${again}`, 3);
      this.feed(`⭐ Chọn ${item.name}, đang chờ thông tin`, 'req');
      return;
    }
    this.prepare(item, item.info || null, now);
  }

  /** Người được chọn bình luận họ tên / ngày sinh / chuyện muốn xem. */
  onInfo(user, text, now) {
    const ph = this.phase;
    const got = parseInfo(text, user.name);
    if (!got.dob && !got.name && !got.question) return { ok: false };
    ph.info = ph.info ? mergeInfo(ph.info, got) : got;
    const i = ph.info;
    if (!ph.ack) {
      ph.ack = true;
      this.feed(`📝 Đã nhận thông tin của ${user.name}`, 'req');
    }
    const t = this.topicOf(i);
    if (ph.dupPending && got.topic !== 'general' && !got.sensitive && !this.doneOf(user.id).has(got.topic)) ph.dupPending = false; // đã chọn chủ đề mới
    if (this.doneOf(user.id).has(t)) {
      ph.dupPending = true;
      // chủ đề này đã xem rồi: xin chọn chủ đề khác, cho thêm thời gian
      i.question = '';
      i.topic = 'general';
      i.sensitive = false;
      if (now - ph.dupAt > 8000) {
        ph.dupAt = now;
        this.cue(`${user.name} ơi, chủ đề ${TOPIC_LABEL[t]} bạn đã xem rồi. Hãy chọn chủ đề khác: tình duyên hoặc công việc, học tập nhé.`, 3);
      }
      ph.until = Math.max(ph.until, now + 20000);
      return { ok: false, dup: true };
    }
    const fast = this.cfg.fast;
    if (i.dob && i.name && i.question) ph.until = Math.min(ph.until, now + (fast ? 300 : 500)); // đủ cả 3: gửi AI ngay
    else if (i.dob && (i.name || i.question)) ph.until = Math.min(ph.until, now + (fast ? 300 : 3000)); // chờ thêm bình luận bổ sung
    return { ok: true };
  }

  /** Hết giờ / đủ thông tin: bắt đầu bói, hoặc bỏ qua nếu người đó không gửi gì / chủ đề trùng. */
  endCollect(now) {
    const ph = this.phase;
    this.phase = null;
    const i = ph.info;
    const u = ph.item;
    if (!i || (!i.dob && !i.name && !i.question)) {
      this.feed(`⏭ ${u.name} không gửi thông tin, mời người khác`, 'warn');
      this.cue(`${u.name} chưa gửi thông tin nên mình mời người tiếp theo nhé.`, 2);
      this.nextAt = now + 1500;
      return;
    }
    if (ph.dupPending || this.doneOf(u.userId).has(this.topicOf(i))) {
      this.feed(`⏭ ${u.name} chọn lại chủ đề đã xem, mời người khác`, 'warn');
      this.nextAt = now + 1500;
      return;
    }
    this.prepare(u, i, now);
  }

  // ---------------------------------------------------------------- chạy buổi bói
  /** Rút 5 lá, bắt đầu "xáo - chia - lật - đọc tên" NGAY, đồng thời gửi AI viết lời đọc. */
  prepare(item, info, now) {
    const s = this.settings.v;
    const prof = info ? profile(info) : null;
    const topic = item.topic && item.topic !== 'general' ? item.topic : info ? this.topicOf(info) : 'general';
    const sensitive = !!(info && info.sensitive);
    const name = (info && info.name) || item.name;
    const drawn = draw(5, s.reverseChance);
    const made = makeCards(drawn, { topic, sensitive });
    const show = showSteps(made.cards, { name }, { profile: prof, sensitive, speed: s.readSpeed, rate: s.readerRate, rateMc: s.voiceRate, fast: this.cfg.fast });
    this.current = {
      id: ++this.seq,
      userId: item.userId || '',
      user: { name, avatar: item.avatar || '' },
      auto: !!item.auto,
      startedAt: now,
      cards: made.cards,
      steps: show.steps,
      total: show.total,
      showTotal: show.total,
      pending: true,
      waiting: false,
      ai: false,
      flipAll: true,
      spread: 5,
      topic: made.topic,
      topicLabel: made.topicLabel,
      profile: prof,
    };
    this.count++;
    if (item.userId) {
      if (!this.done.has(item.userId)) this.done.set(item.userId, new Set());
      this.done.get(item.userId).add(made.topic);
    }
    const useAi = (s.aiProvider === 'claude' || s.aiProvider === 'gemini') && ai.hasKey();
    const ap = { result: useAi ? undefined : null, deadline: now + (Number(s.aiTimeout) + 3) * 1000, id: this.current.id };
    this.pendingAi = ap;
    if (!useAi) this.advance(now); // không dùng AI: nối luôn phần đọc bằng lời viết sẵn
    else {
      const req = {
        name,
        dob: info && info.dob ? info.dob : null,
        profile: prof,
        sensitive,
        topicLabel: TOPIC_LABEL[made.topic],
        cards: made.cards.map((c) => ({ pos: c.pos, vi: c.vi, rev: c.rev, kw: c.kw })),
      };
      ai.generate(req, s).then(
        (r) => { ap.result = r; },
        (e) => {
          ap.result = null;
          this.feed(`⚠️ AI không dùng được (${String(e.message).slice(0, 60)}), đọc bằng lời viết sẵn`, 'warn');
        },
      );
    }
  }

  /** Khi đã xong phần xáo - lật - đọc tên: chờ AI (nếu chưa xong), rồi nối phần đọc vào. */
  advance(now) {
    const c = this.current;
    const ap = this.pendingAi;
    if (!c || !c.pending || !ap || ap.id !== c.id) return;
    const s = this.settings.v;
    const el = now - c.startedAt;
    if (ap.result === undefined) {
      if (el >= c.showTotal && !c.waiting) {
        c.waiting = true;
        c.steps.push({ kind: 'wait', role: 'mc', say: 'Mình đang tổng hợp lời đọc cho bạn, chờ mình một chút nhé.', at: c.showTotal, dur: 3000 });
      }
      if (now > ap.deadline) {
        ap.result = null;
        this.feed('⚠️ AI trả lời chậm, đọc bằng lời viết sẵn', 'warn');
      } else return;
    }
    const result = ap.result;
    let base = c.showTotal;
    if (c.waiting) {
      base = Math.max(base + 1000, el + 300);
      const w = c.steps[c.steps.length - 1];
      w.dur = base - w.at;
    }
    if (result) {
      result.cards.forEach((t, i) => { if (c.cards[i]) c.cards[i].text = t; });
      c.ai = true;
    }
    const rd = readSteps(c.cards, { ai: result, speed: s.readSpeed, rate: s.readerRate, rateMc: s.voiceRate, number: this.count - 1, fast: this.cfg.fast });
    layout(rd.steps, base);
    c.steps.push(...rd.steps);
    c.total = base + rd.total;
    c.pending = false;
    this.pendingAi = null;
  }

  finish(now) {
    const c = this.current;
    if (!c) return;
    this.history.unshift({ name: c.user.name, cards: c.cards.map((x) => x.vi + (x.rev ? ' (ngược)' : '')), topic: c.topicLabel, auto: c.auto });
    if (this.history.length > 8) this.history.pop();
    this.current = null;
    this.pendingAi = null;
    this.nextAt = now + GAP_MS;
    this.idleSince = now + GAP_MS;
    this.nextInvite = now + 25000;
  }

  tick(now = Date.now()) {
    const s = this.settings.v;
    if (this.current && this.current.pending) this.advance(now);
    if (this.current && !this.current.pending && now >= this.current.startedAt + this.current.total) this.finish(now);
    if (!this.current && this.phase && now >= this.phase.until) this.endCollect(now);
    if (!this.current && !this.phase && now >= this.nextAt && !s.paused) {
      if (this.forced.length) this.begin(this.forced.shift(), now);
      else {
        const { ready } = this.candidates(now);
        if (ready.length) {
          const e = ready[0];
          this.begin({ userId: e.id, name: e.name, avatar: e.avatar, topic: 'general' }, now);
        } else if (s.autoDraw && now - this.idleSince >= s.autoIdleSeconds * 1000) {
          this.begin({ name: 'Cả phòng', topic: 'general', auto: true }, now);
        }
      }
    }
    // nhắc khán giả khi màn hình đang chờ
    if (!this.current && !this.phase && !s.paused && now >= this.nextInvite) {
      this.nextInvite = now + 60000;
      this.cue('Bạn nào muốn xem Tarot thì cứ bình luận, thả tim, chia sẻ hoặc tặng quà nhé. Mình sẽ chọn người tương tác tốt nhất.', 1);
    }
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
        this.phase = null;
        if (this.current) this.finish(now);
        return { ok: true };
      case 'clear':
        this.eng.clear();
        this.forced = [];
        return { ok: true };
      case 'remove': {
        const id = String(msg.id);
        this.banned.add(id);
        this.eng.delete(id);
        return { ok: true };
      }
      case 'bump': {
        // chủ phòng chọn ngay người này cho lượt kế tiếp
        const e = this.eng.get(String(msg.id));
        if (e && !this.forced.some((f) => f.userId === e.id)) this.forced.unshift({ userId: e.id, name: e.name, avatar: e.avatar, topic: 'general' });
        return { ok: true };
      }
      case 'draw': {
        // chủ phòng tự rút cho 1 người (không cần người đó bình luận)
        const name = String(msg.name || '').trim().slice(0, 30) || 'Bạn';
        const dob = findDate(String(msg.dob || ''));
        const q = parseInfo(String(msg.question || ''), name);
        const info = dob || q.question ? { name: '', dob: dob ? { d: dob.d, m: dob.m, y: dob.y } : null, question: q.question, topic: q.topic, sensitive: q.sensitive } : { name: '', dob: null, question: '', topic: ['love', 'work'].includes(msg.topic) ? msg.topic : 'general', sensitive: false };
        if (['love', 'work'].includes(msg.topic) && info.topic === 'general') info.topic = msg.topic;
        this.forced.unshift({ userId: '', name, avatar: '', topic: info.topic, info });
        return { ok: true };
      }
      case 'announce':
        return this.announceNow(now);
      case 'testDraw':
        this.current = null;
        this.pendingAi = null;
        this.phase = null;
        this.prepare({ name: 'Bạn', topic: 'general', auto: true }, null, now);
        return { ok: true };
      default:
        return { ok: false, msg: 'Lệnh lạ' };
    }
  }

  // ---------------------------------------------------------------- dữ liệu gửi cho trang web
  getState(now = Date.now()) {
    const s = this.settings.snapshot();
    const { all } = this.candidates(now);
    const min = this.settings.v.minScore;
    return {
      serverNow: now,
      connection: this.connection,
      demo: !!this.cfg.demo,
      settings: s,
      current: this.current,
      collect: this.phase ? { name: this.phase.item.name, avatar: this.phase.item.avatar || '', until: this.phase.until, got: !!this.phase.info } : null,
      preparing: null,
      ai: { provider: this.settings.v.aiProvider, hasKey: ai.hasKey() },
      queue: all.slice(0, 6).map((e) => ({ id: e.id, name: e.name, avatar: e.avatar, spread: 5, topic: 'general', vip: e.score >= min, score: Math.round(e.score * 10) / 10, seen: this.labelsOf(this.doneOf(e.id)) })),
      queueTotal: all.length,
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
