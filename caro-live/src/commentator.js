'use strict';
/*
 * SOẠN CÂU NÓI cho ĐIỀU PHỐI VIÊN (mc) và TRỌNG TÀI (ref).
 * Nội dung câu nằm trong script.js (sửa ở bảng điều khiển). File này quyết định KHI NÀO nói gì.
 * Giọng đọc thật nằm ở public/voice.js (chạy trong trình duyệt).
 *
 * Mỗi câu (cue) có:
 *  - role: 'mc' | 'ref'
 *  - at: thời điểm (giờ server) được phép đọc
 *  - gate: null | {k:'move', n} = đọc khi quân thứ n chạm bàn | {k:'result'} = đọc sau khi nước cuối đánh xong
 *  - prio: 1 = có thể bỏ nếu đang bận, 2 = bình thường, 3 = quan trọng (kết quả)
 */

// Cách đọc tên cột bằng chữ cái tiếng Việt
const LETTER_SOUND = {
  A: 'a', B: 'bê', C: 'xê', D: 'đê', E: 'e', F: 'ép', G: 'gờ', H: 'hát', I: 'i', J: 'di',
  K: 'ca', L: 'lờ', M: 'mờ', N: 'nờ', O: 'o',
};
const NUM_WORD = { 3: 'ba', 4: 'bốn', 5: 'năm', 6: 'sáu' };

function spellCell(x, y) {
  const letter = String.fromCharCode(65 + x);
  return `${LETTER_SOUND[letter] || letter} ${y + 1}`;
}

// MỨC ĐỘ NÓI (cài ở bảng điều khiển). Chia 2 hoàn cảnh:
//   - CHƯA VÀO TRẬN (chờ người chơi, xác nhận tim, tung xu, hết ván): nói thoải mái - chào người mới,
//     giải thích cách chơi, cảm ơn quà / follow / chia sẻ (mức Vừa trở lên).
//   - ĐANG TRONG TRẬN: nói ÍT NHẤT CÓ THỂ - chỉ đọc kết quả thắng/thua/hòa. Quà tặng trong trận được dồn lại cảm ơn sau trận.
//   quiet (0)  = chưa vào trận cũng gần như im lặng (chỉ kết quả đồng xu, thắng/thua, quà lớn)
//   normal (1) = chưa vào trận: chào, giải thích, cảm ơn; trong trận: im lặng
//   lively (2) = thêm đọc từng nước đi, cảnh báo giờ trong trận
// Các câu không được đọc vẫn hiện chữ trên màn hình (khung thông báo / biển báo).
const LEVEL = { quiet: 0, normal: 1, lively: 2 };
const QUIET_KEYS = new Set(['coinResult', 'winGame', 'winForfeit', 'draw', 'giftBig']);
const MATCH_ONLY_KEYS = new Set(['move', 'moveEnd', 'occupied', 'warn10', 'timeoutAuto', 'extraTime']);
const minLevel = (key, inMatch) => (QUIET_KEYS.has(key) ? 0 : inMatch || MATCH_ONLY_KEYS.has(key) ? 2 : 1);

class Commentator {
  constructor(cfg, namer, script) {
    this.cfg = cfg;
    this.namer = namer;
    this.script = script;
    this.cues = [];
    this.seq = 0;
    this.thanksLog = [];
    this.deferred = []; // quà tặng trong trận: cảm ơn sau trận
    this.seen = new Set(); // người đã được chào
    this.phaseOf = () => 'lobby'; // hub gắn vào: trả về pha hiện tại của trận
  }

  push(role, text, o = {}) {
    const cue = {
      id: ++this.seq,
      role,
      text,
      prio: o.prio || 2,
      at: o.at || Date.now(),
      gate: o.gate || null,
    };
    this.cues.push(cue);
    if (this.cues.length > 20) this.cues.shift();
    return cue;
  }

  /** Dựng câu từ kịch bản rồi đưa vào hàng đợi. */
  /** Đang trong trận (đang đánh cờ) thì nói ít nhất có thể. */
  inMatch() {
    return this.phaseOf() === 'playing';
  }

  level() {
    const t = this.cfg.voice && this.cfg.voice.talk;
    return t in LEVEL ? LEVEL[t] : 0;
  }

  say(key, vars, o = {}) {
    const it = this.script.item(key);
    if (!it) return null;
    if (minLevel(key, this.inMatch()) > this.level() && !(o.force)) return null; // mức nói thấp: bỏ các câu không quan trọng
    const text = this.script.render(key, vars, o.n);
    if (!text) return null;
    const cue = this.push(it.role, text, o);
    cue.re = { key, vars, n: o.n == null ? null : o.n };
    return cue;
  }

  nm(user, fallback) {
    return this.namer.say(user, fallback);
  }

  // ----- điều phối viên -----
  lobbyStart(first, now, secs) {
    this.say(first ? 'welcome' : 'lobbyStart', { giay: secs || this.cfg.lobbySeconds }, { at: now });
  }

  lobbyWarning(preview, now) {
    if (!preview.length) {
      this.say('lobbyEmpty', {}, { at: now });
      return;
    }
    const names = preview.map((u) => this.nm(u, 'vô danh'));
    this.say('lobbyWarn', { ten: names.join(' và '), ten1: names[0], ten2: names[1] || '' }, { at: now });
  }

  picked(champion, chosen, now) {
    if (champion) {
      this.say(
        'pickedChamp',
        { ten1: this.nm(champion, 'chủ đài'), ten2: this.nm(chosen[0], 'tân khách') },
        { at: now }
      );
    } else {
      this.say(
        'pickedPair',
        { ten1: this.nm(chosen[0], 'số một'), ten2: this.nm(chosen[1], 'số hai') },
        { at: now }
      );
    }
  }

  hostReset(now) {
    this.say('hostReset', {}, { at: now });
  }

  // ----- trọng tài -----
  coinToss(now) {
    this.say('coinToss', {}, { at: now + 1200 });
  }

  /** Đọc kết quả đúng lúc đồng xu đã dừng và đã chia X/O (match.revealCoin). */
  coinResult(xUser, oUser, now) {
    this.say('coinResult', { ten1: this.nm(xUser, 'quân X'), ten2: this.nm(oUser, 'quân O') }, { at: now, prio: 3 });
  }

  start(xUser, now) {
    this.say('startGame', { ten: this.nm(xUser, 'quân X') }, { at: now });
  }

  move(user, mark, x, y, nextUser, n, now) {
    if (this.cfg.voice && this.cfg.voice.readMoves === false) return;
    if (this.level() < 2) return;
    const vars = {
      ten: this.nm(user, `người chơi ${mark}`),
      oco: spellCell(x, y),
      tiep: nextUser ? this.nm(nextUser, `người chơi ${mark === 'X' ? 'O' : 'X'}`) : '',
    };
    this.say(nextUser ? 'move' : 'moveEnd', vars, { at: now, gate: { k: 'move', n }, prio: 1, n });
  }

  occupied(user, x, y, now) {
    this.say('occupied', { ten: this.nm(user, 'vô danh'), oco: spellCell(x, y) }, { at: now, prio: 1 });
  }

  timeoutAuto(user, x, y, n, now) {
    this.say('timeoutAuto', { ten: this.nm(user, 'vô danh'), oco: spellCell(x, y) }, { at: now, gate: { k: 'move', n } });
  }

  warn10(user, now) {
    this.say('warn10', { ten: this.nm(user, 'vô danh') }, { at: now, prio: 1 });
  }

  win(winner, loser, info, now) {
    const w = this.nm(winner, 'vô danh');
    const l = this.nm(loser, 'vô danh');
    const gate = { k: 'result' };
    if (info.type === 'forfeit') {
      this.say('winForfeit', { ten: w, thua: l, lydo: info.why }, { at: now, gate, prio: 3 });
    } else {
      this.say('winGame', { ten: w, thua: l, so: NUM_WORD[this.cfg.winLength] || this.cfg.winLength }, { at: now, gate, prio: 3 });
    }
    this.say('congrats', { ten: w }, { at: now, gate });
    if (info.streak >= 2) this.say('streak', { ten: w, so: info.streak }, { at: now, gate });
    if (info.steppedDown) this.say('stepDown', { ten: w }, { at: now, gate });
    if (info.type !== 'forfeit' && !info.rankDown) this.say('loseComfort', { thua: l }, { at: now, gate });
  }

  rankUp(name, tierName, now) {
    this.say('rankUp', { ten: this.nm({ name }, 'vô danh'), canhgioi: tierName }, { at: now, gate: { k: 'result' }, prio: 2 });
  }

  rankDown(name, tierName, now, lost) {
    this.say('rankDown', { ten: this.nm({ name }, 'vô danh'), canhgioi: tierName, diem: lost || 0 }, { at: now, gate: { k: 'result' }, prio: 2 });
  }

  draw(now) {
    this.say('draw', {}, { at: now, gate: { k: 'result' }, prio: 3 });
  }

  // ----- cảm ơn -----
  /** Có bao nhiêu câu cảm ơn vừa được tạo trong 7 giây qua (chống đọc dồn dập). */
  recentThanks(now) {
    this.thanksLog = this.thanksLog.filter((t) => now - t < 7000);
    return this.thanksLog.length;
  }

  /** Cảm ơn thưa thớt để đỡ ồn. Mức ít: chỉ quà LỚN, cách nhau 30 giây. Mức vừa: cảm ơn hết nhưng cách nhau 12 giây (quà lớn không bị chặn). Mức nhiều: cảm ơn hết. */
  thanksGap(big, now) {
    const lv = this.level();
    if (lv >= 2) return true;
    if (lv === 1) {
      if (!big && this.lastThanksAt != null && now - this.lastThanksAt < 12000) return false;
      this.lastThanksAt = now;
      return true;
    }
    if (!big) return false;
    if (this.lastThanksAt != null && now - this.lastThanksAt < 30000) return false;
    this.lastThanksAt = now;
    return true;
  }

  /** Chào người mới (lần bình luận đầu tiên). Chỉ khi chưa vào trận; cách nhau ít nhất 15 giây. */
  greet(user, now) {
    if (!user || this.seen.has(user.id)) return null;
    if (this.seen.size > 5000) this.seen.clear();
    this.seen.add(user.id);
    if (this.inMatch() || this.level() < 1) return null;
    if (this.lastGreetAt != null && now - this.lastGreetAt < 15000) return null;
    this.lastGreetAt = now;
    return this.say('greet', { ten: this.nm(user, 'mới đến') }, { at: now + 800, prio: 1 });
  }

  /** Giải thích cách chơi lúc chờ. */
  howTo(now, delayMs) {
    return this.say('howTo', {}, { at: now + (delayMs || 9000), prio: 1 });
  }

  /** Cảm ơn dồn lại sau trận (quà tặng trong lúc đang đánh). */
  flushDeferred(now) {
    if (!this.deferred.length || this.inMatch()) return;
    const list = this.deferred.splice(0);
    list.sort((p, q) => q.total - p.total);
    for (const d of list.slice(0, 2)) {
      this.say(d.big ? 'giftBig' : 'giftThanks', d.vars, { at: now + 2500, prio: d.big ? 3 : 2, force: true });
    }
  }

  giftThanks(user, gift, now) {
    const total = (Number(gift.diamonds) || 0) * (Number(gift.count) || 1);
    const big = total >= ((this.cfg.voice && this.cfg.voice.bigGiftDiamonds) || 100);
    if (!big && this.recentThanks(now) >= 3) return null; // quá nhiều quà nhỏ cùng lúc: bỏ bớt
    const delay = (this.cfg.voice && this.cfg.voice.thanksDelayMs) || 2500;
    const vars = {
      ten: this.nm(user, 'vô danh'),
      qua: this.namer.sayText(gift.name, 'món quà'),
      so: gift.count || 1,
    };
    if (this.inMatch() && this.level() < 2) {
      // đang trong trận: không nói, dồn lại cảm ơn sau trận
      if ((big || this.level() >= 1) && this.deferred.length < 6) this.deferred.push({ big, total, vars });
      return null;
    }
    if (!this.thanksGap(big, now)) return null;
    const cue = this.say(big ? 'giftBig' : 'giftThanks', vars, { at: now + delay, prio: big ? 3 : 2 });
    if (cue) this.thanksLog.push(now);
    return cue;
  }

  /** Quà combo tăng số lượng: sửa lại câu cảm ơn nếu chưa tới lúc đọc. */
  updateGiftThanks(cue, count) {
    if (!cue || !cue.re || Date.now() >= cue.at) return;
    const vars = { ...cue.re.vars, so: count };
    const text = this.script.render(cue.re.key, vars, cue.re.n == null ? 0 : cue.re.n);
    if (text) {
      cue.text = text;
      cue.re.vars = vars;
    }
  }

  followThanks(user, now) {
    if (this.recentThanks(now) >= 3 || !this.thanksGap(false, now)) return;
    const cue = this.say('followThanks', { ten: this.nm(user, 'vô danh') }, { at: now + 1500 });
    if (cue) this.thanksLog.push(now);
  }

  /** Nhắc định kỳ. Luôn trả về câu để hiện lên màn hình; có đọc thành tiếng hay không tùy mức nói. */
  remind(kind, now) {
    const pts = this.cfg.points || {};
    const key = kind === 'share' ? 'remindShare' : 'remindFollow';
    const vars = { diem: kind === 'share' ? pts.share : pts.follow };
    const cue = this.say(key, vars, { at: now });
    if (cue) return cue;
    const text = this.script.render(key, vars);
    return text ? { text } : null;
  }

  extraTime(user, giay, now) {
    this.say('extraTime', { ten: this.nm(user, 'vô danh'), giay }, { at: now, prio: 1 });
  }

  // ----- xác nhận thả tim -----
  confirmAsk(users, giay, now) {
    const names = users.map((u) => this.nm(u, 'vô danh'));
    if (names.length >= 2) this.say('confirmAsk', { ten1: names[0], ten2: names[1], giay }, { at: now });
    else if (names.length === 1) this.say('confirmAskOne', { ten: names[0], giay }, { at: now });
  }

  confirmOk(user, now) {
    this.say('confirmOk', { ten: this.nm(user, 'vô danh') }, { at: now, prio: 1 });
  }

  confirmWarn(users, giay, now) {
    const names = users.map((u) => this.nm(u, 'bạn')).join(' và ');
    this.say('confirmWarn', { ten: names, giay }, { at: now, prio: 1 });
  }

  confirmFail(user, replacement, now) {
    if (replacement) this.say('confirmFail', { ten: this.nm(user, 'vô danh'), ten2: this.nm(replacement, 'vô danh') }, { at: now });
    else this.say('confirmFailNone', { ten: this.nm(user, 'vô danh') }, { at: now });
  }

  shareThanks(user, now) {
    if (this.recentThanks(now) >= 3 || !this.thanksGap(false, now)) return;
    const cue = this.say('shareThanks', { ten: this.nm(user, 'vô danh') }, { at: now + 1500 });
    if (cue) this.thanksLog.push(now);
  }
}

module.exports = { Commentator, spellCell };
