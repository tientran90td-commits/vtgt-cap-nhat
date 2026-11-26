'use strict';
/*
 * GIỮ VÁN ĐANG CHƠI KHI CẬP NHẬT / KHỞI ĐỘNG LẠI.
 * Game tự lưu "ảnh chụp" (bàn cờ, ai đang đi, đồng hồ, người chơi, điểm tương tác...) vào data/dang-choi.json:
 *   - ngay lúc game thoát (kể cả khi bấm Cập nhật, game tự thoát mã 3 để mở lại),
 *   - và cứ 3 giây một lần (phòng khi bị tắt đột ngột / treo).
 * Mở lại game: nếu ảnh chụp còn mới thì khôi phục đúng chỗ đang dở. Thời gian lúc game tắt KHÔNG bị tính vào đồng hồ
 * (ví dụ còn 20 giây thì khôi phục vẫn còn 20 giây). Ảnh chụp quá cũ thì bỏ qua và bắt đầu như bình thường.
 * Lưu ý: lần cập nhật đầu tiên LÊN bản có tính năng này vẫn mất ván (vì bản cũ chưa biết lưu); các lần sau thì giữ được.
 */
const fs = require('fs');
const path = require('path');

const VERSION = 1;
const MAX_AGE_EXIT_MS = 10 * 60 * 1000; // lưu lúc thoát bình thường / cập nhật
const MAX_AGE_AUTO_MS = 2 * 60 * 1000; // lưu định kỳ (chỉ dùng khi bị tắt đột ngột)
const MAX_USERS = 3000;
const AUTOSAVE_MS = 3000;

const MATCH_PLAIN = ['entering', 'gameNo', 'champion', 'booked', 'firstLobby', 'confirm', 'lastCommentAt', 'extraUsed', 'partial', 'hinted', 'phase', 'players', 'result', 'coin', 'coinPlayers', 'coinSeats', 'waiting', 'lobbySecs', 'lobbyWarned', 'turn', 'timeouts', 'warned', 'rankUpInfo', 'rankDownInfo', 'signPulseUntil', 'feedList', 'feedSeq'];
const MATCH_TIMES = ['phaseStartedAt', 'phaseEndsAt', 'turnStartedAt', 'turnEndsAt', 'signPulseUntil'];
const MATCH_SETS = ['excludeNext', 'confirmFailed'];

const clone = (v) => (v === undefined ? undefined : JSON.parse(JSON.stringify(v)));

function snapshot(hub, reason, now = Date.now()) {
  const m = hub.match;
  const mt = {};
  for (const k of MATCH_PLAIN) if (m[k] !== undefined) mt[k] = clone(m[k]);
  for (const k of MATCH_TIMES) if (m[k] !== undefined) mt[k] = m[k];
  for (const k of MATCH_SETS) mt[k] = [...(m[k] || [])];
  if (mt.confirm && mt.confirm.slots) mt.confirm.slots = mt.confirm.slots.map((s) => ({ id: s.user.id, user: s.user, done: !!s.done }));
  const users = [...hub.interaction.users.values()].sort((a, b) => (b.seenAt || 0) - (a.seenAt || 0)).slice(0, MAX_USERS);
  return {
    v: VERSION,
    reason,
    savedAt: now,
    match: mt,
    game: { size: m.game.size, cells: clone(m.game.cells), moves: clone(m.game.moves) },
    users: clone(users),
    seq: hub.interaction.seq,
    chatLog: clone(hub.chatLog || []),
    chatSeq: hub.chatSeq || 0,
  };
}

/** Khôi phục. Trả { ok, phase, ... } hoặc { ok:false, why } */
function restore(hub, snap, now = Date.now()) {
  if (!snap || snap.v !== VERSION || !snap.match || !snap.game) return { ok: false, why: 'định dạng lạ' };
  const age = now - snap.savedAt;
  const max = snap.reason === 'exit' ? MAX_AGE_EXIT_MS : MAX_AGE_AUTO_MS;
  if (age < 0 || age > max) return { ok: false, why: 'quá cũ' };
  const m = hub.match;
  if (snap.game.size !== m.game.size) return { ok: false, why: 'đổi cỡ bàn' };
  const d = age; // thời gian game tắt: dồn đồng hồ lên đúng bấy nhiêu để không bị mất giờ

  // người xem + điểm tương tác
  const inter = hub.interaction;
  inter.users.clear();
  for (const u of snap.users || []) {
    if (u.lastCommentAt) u.lastCommentAt += d;
    if (u.seenAt) u.seenAt += d;
    inter.users.set(u.id, u);
  }
  inter.seq = Math.max(inter.seq || 0, snap.seq || 0);

  // trận đấu
  const s = snap.match;
  for (const k of MATCH_PLAIN) if (s[k] !== undefined) m[k] = s[k];
  for (const k of MATCH_TIMES) if (typeof s[k] === 'number') m[k] = s[k] + d;
  if (m.lastCommentAt) for (const k of Object.keys(m.lastCommentAt)) if (m.lastCommentAt[k]) m.lastCommentAt[k] += d;
  for (const k of MATCH_SETS) m[k] = new Set(s[k] || []);
  if (m.confirm && m.confirm.slots) m.confirm.slots = m.confirm.slots.map((x) => ({ user: inter.users.get(x.id) || x.user, done: !!x.done }));
  if (!s.entering && m.champion) m.entering = { [m.champion.id]: m.champion.streak }; // ảnh chụp từ bản cũ chưa có chuỗi thắng lúc vào ván
  m.game.cells = snap.game.cells;
  m.game.moves = snap.game.moves;
  hub.chatLog = snap.chatLog || [];
  hub.chatSeq = snap.chatSeq || 0;
  m.feed('🔄 Game vừa khởi động lại (cập nhật), ván đấu được giữ nguyên!', 'info');
  return { ok: true, phase: m.phase, moves: m.game.moves.length, ageMs: age };
}

function read(file) {
  try {
    return JSON.parse(fs.readFileSync(file, 'utf8'));
  } catch (e) {
    return null;
  }
}

function write(file, obj) {
  const tmp = file + '.tmp';
  fs.mkdirSync(path.dirname(file), { recursive: true });
  fs.writeFileSync(tmp, JSON.stringify(obj));
  fs.renameSync(tmp, file); // ghi vào file tạm rồi đổi tên: không bao giờ để lại file dở dang
}

/** Gắn vào game: khôi phục (nếu có) rồi bật tự lưu. */
function start(hub, file, log = () => {}) {
  const snap = read(file);
  if (snap) {
    try {
      const r = restore(hub, snap);
      if (r.ok) log(`Đã khôi phục ván đang dở (pha "${r.phase}", ${r.moves} nước đi, tắt ${Math.round(r.ageMs / 1000)} giây).`);
      else log('Bỏ qua dữ liệu ván cũ: ' + r.why);
    } catch (e) {
      log('Không khôi phục được ván cũ: ' + e.message);
    }
  }
  let last = '';
  const save = (reason) => {
    try {
      const snapNow = snapshot(hub, reason);
      const sig = JSON.stringify({ ...snapNow, savedAt: 0, reason: '' });
      if (reason === 'auto' && sig === last) return;
      last = sig;
      write(file, snapNow);
    } catch (e) {
      /* lưu lỗi thì thôi, không làm hỏng game */
    }
  };
  const timer = setInterval(() => save('auto'), AUTOSAVE_MS);
  timer.unref();
  process.on('exit', () => save('exit'));
  return { save, file };
}

module.exports = { start, snapshot, restore, VERSION };
