/*
 * TRANG LIVE (sạch): ghép bàn cờ 2D + cảnh 3D + người chơi + giọng đọc.
 * Dữ liệu từ server -> director.js (đồng bộ cử động nhân vật) -> vẽ ra màn hình.
 */
import { connect } from './net.js';
import { Scene3D, NullScene } from './scene3d.js';
import { Director } from './director.js';
import { BoardView } from './board.js';
import { themeForGame, classicTheme, applyTheme } from './theme.js';
import { pickSkin } from './board-skins.js';
import { Voice } from './voice.js';
import { Sfx } from './sfx.js';
import { Music } from './music.js';
import { Fx } from './fx.js';
import { Celebrate } from './celebrate.js';
import { fourInRow } from './threat.js';
import { avatarSrc } from './avatar.js';
import { setFrame, renderRankBoard } from './rank.js';
import { Announcer } from './announce.js';
import { RankUp } from './rankup.js';

const $ = (id) => document.getElementById(id);
const params = new URLSearchParams(location.search);
let layoutPref = params.get('layout') || 'auto';
if (params.get('bg') === 'none') document.body.classList.add('nobg');
const forceMuted = params.has('mute');

const stage = $('stage');
const boardView = new BoardView($('board'), 15);
let scene;
try {
  scene = new Scene3D($('three'), 15);
} catch (e) {
  console.warn('Không bật được 3D:', e);
  scene = new NullScene();
  const note = document.createElement('div');
  note.style.cssText = 'position:absolute;inset:0;display:flex;align-items:center;justify-content:center;color:#9fb0d6;text-align:center;padding:1rem';
  note.textContent = 'Máy/trình duyệt này không bật được hình 3D (WebGL).';
  $('sceneWrap').appendChild(note);
}
const director = new Director(scene);
const voice = new Voice({
  onCaption(item) {
    const el = $('caption');
    if (!item) {
      el.classList.add('hidden');
      return;
    }
    if (item.noCaption) { // lời đọc thông báo: đã có bảng thông báo nên không hiện thêm phụ đề
      el.classList.add('hidden');
      return;
    }
    el.className = item.role;
    el.querySelector('b').textContent = item.role === 'ref' ? '⚖ Trọng tài:' : '🎙 Tại hạ (điều phối):';
    el.querySelector('span').textContent = item.text;
  },
});
voice.forceMute = forceMuted;
const sfx = new Sfx();
sfx.forceMute = forceMuted;
const music = new Music();
music.forceMute = forceMuted;
const fx = new Fx($('fx'), $('banner'), $('promo'));
fx.resize();
window.addEventListener('resize', () => fx.resize());

// âm thanh + hiệu ứng khi quân cờ chạm bàn
director.onPlaced = (mv, shown) => {
  sfx.place(mv.m);
  const th = fourInRow(shown, 15, mv);
  if (th) {
    sfx.four();
    fx.showBanner(th.open ? '⚡ 4 QUÂN MỞ 2 ĐẦU!' : '🔥 4 QUÂN LIỀN!', th.open ? 'open' : '');
  }
};

window.__caro = { scene, director, fx, sfx, music }; // dùng khi kiểm tra tự động
const spoken = new Set();
let state = null;
let offset = 0;

// ---------------------------------------------------------------- bố cục
function applyLayout() {
  const W = window.innerWidth;
  const H = window.innerHeight;
  const lay = layoutPref === 'portrait' || layoutPref === 'landscape' ? layoutPref : W / H > 1.2 ? 'landscape' : 'portrait';
  const ratio = lay === 'portrait' ? 9 / 16 : 16 / 9;
  let sw;
  let sh;
  if (W / H > ratio) {
    sh = H;
    sw = H * ratio;
  } else {
    sw = W;
    sh = W / ratio;
  }
  stage.dataset.layout = lay;
  stage.style.width = sw + 'px';
  stage.style.height = sh + 'px';
  document.documentElement.style.fontSize = (lay === 'portrait' ? sh / 71.1 : sh / 40) + 'px';
  requestAnimationFrame(() => {
    boardView.resize($('boardBox').clientWidth);
    scene.resize($('sceneWrap').clientWidth, $('sceneWrap').clientHeight);
  });
}
window.addEventListener('resize', applyLayout);
applyLayout();

// ---------------------------------------------------------------- dữ liệu
connect(
  (s) => {
    const first = !state;
    state = s;
    offset = s.serverNow - Date.now();
    if (first) for (const c of s.cues) spoken.add(c.id); // không đọc lại thoại cũ khi mở trang
    director.onState(s, offset);
    if (s.settings) {
      voice.setSettings(s.settings.voice);
      sfx.setOptions(s.settings.sfx);
      music.setOptions(s.settings.music);
    }
    handleExtras(s, first);
    $('hostName').textContent = s.host ? '@' + s.host : '';
    renderFeed(s);
    renderRank(s);
  },
  null
);

director.onReset = () => {
  fx.clear();
  // sang ván mới: bỏ các câu đang chờ của ván cũ
  if (state) for (const c of state.cues) if (c.gate) spoken.add(c.id);
};

// ---------------------------------------------------------------- hiệu ứng theo dữ liệu từ máy chủ
const rankup = new RankUp($('rankup'), avatarSrc);
rankup.onShow = () => sfx.chime();
window.__rankup = rankup; // để thử nhanh trong F12
window.__st = () => state;
window.__voice = voice;
const announcer = new Announcer($('announce'), $('sceneWrap'));
let promoId = null;
let lastFeedId = 0;
let fxKey = null;
let celebStartedKey = null; // ván nào đã bắt đầu phát video ăn mừng (để giữ thoại chiến thắng lại, đọc sau khi video hết)
function handleExtras(s, first) {
  // thông báo của chủ phòng (bảng nhỏ + lời đọc)
  if (announcer.update(s.announce, first)) sfx.chime();
  // nhắc follow / chia sẻ
  if (s.promo && s.promo.id !== promoId) {
    promoId = s.promo.id;
    if (!first) {
      fx.showPromo(s.promo.text, s.promo.kind);
      sfx.pop();
    }
  }
  // quà / follow / chia sẻ mới -> tiếng chuông
  const top = s.feed.length ? s.feed[s.feed.length - 1].id : 0;
  if (first) lastFeedId = top;
  else {
    let gift = false;
    for (const f of s.feed) if (f.id > lastFeedId && f.kind === 'gift') gift = true;
    lastFeedId = top;
    if (gift) sfx.chime();
  }
}

const celebrate = new Celebrate($('celebVideo'), $('sceneWrap'), $('three'));
window.__celebrate = celebrate; // để thử nhanh trong F12

// kết quả ván: pháo hoa + nhạc (chạy 1 lần cho mỗi ván, đúng lúc màn hình kết quả hiện ra)
function resultEffects(s) {
  const key = s.gameNo + ':' + (s.result ? s.result.type : '');
  if (key === fxKey) return;
  fxKey = key;
  if (!s.result) return;
  const w = s.result.winner && s.players ? s.players[s.result.winner] : null;
  if (w) {
    sfx.win();
    fx.fireworks(6500);
    fx.showBanner('🏆 ' + w.name + ' ĐẠI THẮNG!', 'Bá đạo! Bá khí ngút trời!');
    if (!(s.settings && s.settings.celebrateOn === false)) {
      celebrate.start(); // video ăn mừng (celebrate.js)
      celebStartedKey = fxKey;
    }
    if (s.result.rankUp) { rankup.queue(s.result.rankUp); } // bảng đột phá hiện sau khi video ăn mừng chạy xong
  } else {
    sfx.lose();
  }
}

// ---------------------------------------------------------------- vẽ giao diện
function setText(el, text) {
  if (el.textContent !== text) el.textContent = text;
}

let feedKey = '';
function renderFeed(s) {
  const key = s.feed.length ? s.feed[s.feed.length - 1].id + ':' + s.feed.length : '';
  if (key === feedKey) return;
  feedKey = key;
  const ul = $('feed');
  ul.replaceChildren();
  for (const f of s.feed.slice(-4)) {
    const li = document.createElement('li');
    li.className = `${f.kind}${f.mark ? ' ' + f.mark : ''}`;
    li.textContent = f.text;
    ul.appendChild(li);
  }
}

let rankKey = '';
const MEDALS = ['🥇', '🥈', '🥉'];
function renderRank(s) {
  const need = s.lobby ? s.lobby.need : 2;
  const key = JSON.stringify([s.top.map((u) => [u.id, u.points, u.name, u.mark]), s.phase, need]);
  if (key === rankKey) return;
  rankKey = key;
  setText($('rankNote'), `Top ${need} đấu ván kế • gõ !diem xem hạng`);
  const ol = $('rankList');
  ol.replaceChildren();
  if (!s.top.length) {
    const li = document.createElement('li');
    li.className = 'hint';
    li.textContent = 'Bình luận / thả tim / tặng quà để lên bảng tu vi!';
    ol.appendChild(li);
    return;
  }
  const rows = 6;
  for (let i = 0; i < rows; i++) {
    const u = s.top[i];
    const li = document.createElement('li');
    const no = document.createElement('span');
    no.className = 'no';
    no.textContent = MEDALS[i] || String(i + 1);
    const nm = document.createElement('span');
    nm.className = 'nm';
    li.append(no, nm);
    if (!u) {
      li.className = 'empty';
      nm.textContent = '—';
    } else {
      if (i < need) li.classList.add('pick');
      nm.textContent = u.name;
      if (u.mark) {
        const tg = document.createElement('span');
        tg.className = 'tg';
        tg.textContent = '⚔';
        li.appendChild(tg);
      }
      const pts = document.createElement('span');
      pts.className = 'pts';
      pts.textContent = u.points + (u.diamonds ? ' 💎' : '');
      li.appendChild(pts);
    }
    ol.appendChild(li);
  }
}

function setAvatar(card, person) {
  const img = card.querySelector('img');
  const span = card.querySelector('.av span');
  const url = person && person.avatar ? person.avatar : '';
  if (img.dataset.src !== url) {
    img.dataset.src = url;
    img.style.display = url ? '' : 'none';
    if (url) {
      img.referrerPolicy = 'no-referrer';
      img.src = avatarSrc(url);
      img.onerror = () => (img.style.display = 'none');
    } else {
      img.removeAttribute('src');
    }
  }
  setText(span, person && person.name ? [...person.name.trim()][0] || '?' : '?');
}

function renderPlayers(s, eff, now) {
  const confirming = eff === 'confirm' && !!s.confirm;
  const lobby = eff === 'lobby' || confirming;
  const pv = confirming ? s.confirm.slots : s.lobby.preview;
  const cards = { X: $('pX'), O: $('pO') };
  for (const mark of ['X', 'O']) {
    const card = cards[mark];
    const person = lobby ? (mark === 'X' ? pv[0] : pv[1]) : s.players[mark];
    setAvatar(card, person);
    setFrame(card.querySelector('.fr'), person && person.rank ? person.rank.tier : 0); // khung avatar theo cảnh giới
    setText(card.querySelector('.nm'), person ? person.name : 'Chờ đạo hữu…');
    let sub = '';
    if (confirming) sub = person ? (person.champion ? 'Nhà vô địch • giữ bàn' : person.done ? '❤ Đã thả tim • sẵn sàng!' : 'Hãy THẢ TIM để xác nhận') : '';
    else if (lobby) sub = person ? (person.champion ? `Nhà vô địch • thắng ${s.champion ? s.champion.streak : 1} ván` : 'Đang dẫn đầu tương tác') : 'Hãy tương tác để lên bàn';
    else sub = `Cầm quân ${mark === 'X' ? 'X đỏ' : 'O xanh'}`;
    if (!lobby && s.champion && s.players[mark] && s.champion.name === s.players[mark].name && s.champion.streak >= 1 && eff !== 'finished') sub += ` • chuỗi thắng ${s.champion.streak}`;
    setText(card.querySelector('.sub'), sub);
    setText(card.querySelector('.mk'), lobby ? '?' : mark === 'X' ? '✕' : '○');

    const playing = eff === 'playing' && s.turn === mark;
    card.classList.toggle('active', playing);
    card.classList.toggle('winner', eff === 'finished' && director.resultReady && s.result && s.result.winner === mark);
    let pct = 0;
    let urgent = false;
    if (playing) {
      const left = Math.max(0, s.turnEndsAt - now);
      pct = Math.min(1, left / s.turnTotalMs);
      urgent = left < 8000;
    } else if (confirming && person && !person.done) {
      pct = Math.max(0, Math.min(1, (s.phaseEndsAt - now) / (s.phaseTotalMs || 1)));
      urgent = s.phaseEndsAt - now < 6000;
    }
    card.querySelector('.bar i').style.width = (pct * 100).toFixed(1) + '%';
    card.classList.toggle('urgent', urgent);
  }
}

function renderHint(s, eff, now) {
  const el = $('hint');
  let html = '';
  if (eff === 'lobby') html = `Luật: <b>${s.rules}</b>`;
  else if (eff === 'confirm') html = 'Hai vị đạo hữu hãy <b>thả tim ❤</b> để xác nhận lên đài';
  else if (eff === 'coin') html = 'Trọng tài đang <b>tung đồng xu</b> định tiên cơ…';
  else if (eff === 'playing') {
    const p = s.players[s.turn];
    const name = p ? p.name : '';
    if (director.busy || !p) html = `<b>${escapeHtml(name || '…')}</b> đang bố trận…`;
    else {
      const left = Math.max(0, Math.ceil((s.turnEndsAt - now) / 1000));
      html = `Lượt của đạo hữu <b>${escapeHtml(name)}</b> • còn <b>${left}s</b> • gõ tọa độ như <b>j9</b>, <b>k6</b>`;
    }
  } else if (eff === 'finished' && s.result) html = escapeHtml(s.result.text);
  if (el.dataset.h !== html) {
    el.dataset.h = html;
    el.innerHTML = html;
  }
}

function escapeHtml(t) {
  return String(t).replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
}

let cfKey = '';
function renderConfirm(s, now) {
  const key = JSON.stringify(s.confirm.slots.map((p) => [p.id, p.done, p.champion]));
  if (key !== cfKey) {
    cfKey = key;
    const ul = $('cfList');
    ul.replaceChildren();
    for (const p of s.confirm.slots) {
      const li = document.createElement('li');
      li.className = p.done ? 'done' : 'wait';
      li.textContent = `${p.champion ? '👑' : p.done ? '✅' : '❤'} ${p.name}${p.champion ? ' (giữ bàn)' : p.done ? ' • sẵn sàng' : ' • chờ thả tim'}`;
      ul.appendChild(li);
    }
  }
  const left = Math.max(0, Math.ceil((s.phaseEndsAt - now) / 1000));
  setText($('cfCount'), String(left));
  if (left <= 5 && left > 0 && left !== lastTick) {
    lastTick = left;
    sfx.tick(left === 1);
  }
}

// biển báo nhỏ ở góc: các điều cần thiết (không đọc thành tiếng)
let signKey = '';
function renderSign(s, now) {
  const el = $('sign');
  const sg = s.sign;
  el.classList.toggle('hidden', !sg);
  if (!sg) {
    signKey = '';
    return;
  }
  const key = sg.lines.join('|');
  if (key !== signKey) {
    signKey = key;
    const ul = $('signList');
    ul.replaceChildren();
    for (const l of sg.lines) {
      const li = document.createElement('li');
      li.textContent = l;
      ul.appendChild(li);
    }
  }
  el.classList.toggle('pulse', !!sg.pulse);
}

// tiếng đồng hồ tích tắc khi người chơi sắp hết giờ
let clockSec = -1;
let clockTurn = '';
function clockTick(s, eff, now) {
  const lim = s.settings ? Number(s.settings.clockSeconds) || 0 : 15;
  if (eff !== 'playing' || !lim || director.busy || !s.players || !s.players[s.turn]) {
    clockSec = -1;
    return;
  }
  const left = Math.ceil((s.turnEndsAt - now) / 1000);
  const turnKey = s.gameNo + ':' + s.moves.length + ':' + s.turn;
  if (turnKey !== clockTurn) {
    clockTurn = turnKey;
    clockSec = -1;
  }
  if (left > lim || left < 1) {
    if (left > lim) clockSec = -1;
    return;
  }
  if (left !== clockSec) {
    clockSec = left;
    sfx.clock(left % 2 === 0, left <= 5);
  }
}

let coinKey = null;
let lastTick = -1;
function renderOverlay(s, eff, now) {
  const ov = $('overlay');
  const lobbyEl = $('ovLobby');
  const coinEl = $('ovCoin');
  const cfEl = $('ovConfirm');
  const resEl = $('ovResult');
  let which = '';
  if (eff === 'lobby') which = 'lobby';
  else if (eff === 'confirm') which = 'confirm';
  else if (eff === 'coin') which = 'coin';
  else if (eff === 'finished' && director.resultReady) which = 'result';
  ov.classList.toggle('hidden', !which);
  lobbyEl.classList.toggle('hidden', which !== 'lobby');
  cfEl.classList.toggle('hidden', which !== 'confirm');
  coinEl.classList.toggle('hidden', which !== 'coin');
  resEl.classList.toggle('hidden', which !== 'result');

  if (which === 'lobby') {
    const left = Math.ceil((s.phaseEndsAt - now) / 1000);
    const c = $('ovCount');
    if (s.lobby.waiting || left <= 0) {
      setText(c, 'Chờ thêm người tương tác…');
      c.classList.add('wait');
    } else {
      setText(c, String(left));
      c.classList.remove('wait');
      if (left <= 5 && left !== lastTick) {
        lastTick = left;
        sfx.tick(left === 1);
      }
    }
  } else if (which === 'confirm' && s.confirm) {
    renderConfirm(s, now);
  } else if (which === 'coin' && s.coin) {
    const elapsed = now - s.phaseStartedAt;
    const coin = $('coin');
    if (coinKey !== s.gameNo) {
      coinKey = s.gameNo;
      if (elapsed < 1500) sfx.coin();
      setText($('coinHead'), s.coin.heads.name);
      setText($('coinTail'), s.coin.tails.name);
      const final = 360 * 5 + (s.coin.face === 'tails' ? 180 : 0);
      coin.style.transition = 'none';
      coin.style.transform = 'rotateY(0deg)';
      void coin.offsetWidth;
      if (elapsed > 3300) {
        coin.style.transform = `rotateY(${final}deg)`;
      } else {
        coin.style.transition = 'transform 3s cubic-bezier(0.15, 0.7, 0.2, 1)';
        coin.style.transform = `rotateY(${final}deg)`;
      }
    }
    setText($('coinResult'), elapsed > 3300 ? `${s.coin.first.name} đi trước • quân X đỏ` : '');
  } else if (which === 'result' && s.result) {
    resultEffects(s);
    setText($('resText'), s.result.text);
    setText($('resNote'), s.result.note || '');
    const left = Math.max(0, Math.ceil((s.phaseEndsAt - now) / 1000));
    setText($('resNext'), `Ván mới sau ${left}s`);
  }
}

function processVoice() {
  const due = director.dueCues(spoken);
  const now = director.nowServer();
  // Thoại chiến thắng (chúc mừng, khen, đột phá...) KHÔNG đọc đè lên nhạc video ăn mừng: giữ lại, video hết mới đọc
  const s = state;
  const celebOn = !(s && s.settings && s.settings.celebrateOn === false);
  const playing = celebrate.active(); // video đang chạy: giữ MỌI lời đọc lại (kể cả cảm ơn quà), tránh đọc đè lên nhạc
  const holdResult = celebOn && s && s.result && s.result.winner && celebStartedKey !== s.gameNo + ':' + s.result.type;
  for (const c of due) {
    if (playing || (holdResult && c.gate && c.gate.k === 'result')) continue;
    spoken.add(c.id);
    if (now - c.at > (c.gate && c.gate.k === 'result' ? 60000 : 15000)) continue; // câu đã quá cũ (lời cảm ơn quà bị giữ lâu quá thì bỏ, tránh đọc dồn sau video)
    voice.push(c);
  }
  const need = !forceMuted && ((voice.supported && voice.settings.on && voice.needsGesture) || sfx.needsGesture() || music.needsGesture());
  $('unlock').classList.toggle('hidden', !need);
}

// ---------------------------------------------------------------- giao diện đổi theo ván (theme.js)
// ?theme=0..7 trên địa chỉ trang = ép 1 kiểu. Bảng điều khiển có ô tick 'Mỗi ván đổi màu bàn cờ, phòng, nhân vật'.
const forcedTheme = params.has('theme') && Number.isFinite(Number(params.get('theme'))) ? Number(params.get('theme')) : null;
// ?skin=0..8 (hoặc tên kiểu, hoặc wood) trên địa chỉ trang = ép 1 kiểu bàn cờ hoa văn + đèn LED (xem board-skins.js).
const forcedSkin = params.has('skin') ? params.get('skin') : null;
let themeKey = null;
function themeTick(s) {
  if (!s || s.gameNo === undefined) return;
  const auto = s.settings ? s.settings.themeAuto !== false : true;
  const skinSetting = forcedSkin !== null ? forcedSkin : s.settings && s.settings.boardSkin ? s.settings.boardSkin : 'auto';
  const skin = pickSkin(skinSetting, s.gameNo);
  const key = (forcedTheme !== null ? 'f' + forcedTheme : auto ? 'a' + s.gameNo : 'c') + '|' + (skin ? skin.id : 'wood');
  if (key === themeKey) return;
  themeKey = key;
  const t = forcedTheme !== null ? themeForGame(0, forcedTheme) : auto ? themeForGame(s.gameNo) : classicTheme();
  t.skin = skin;
  applyTheme(t, boardView, scene);
}

// ---------------------------------------------------------------- vòng lặp
let last = performance.now();
function frame(t) {
  const dt = Math.min(0.1, (t - last) / 1000);
  last = t;
  const time = t / 1000;
  director.update(dt, time);
  themeTick(state);
  const ledOn = !(state && state.settings && state.settings.ledOn === false);
  boardView.ledOn = ledOn;
  if (scene.tickLed) scene.tickLed(time, ledOn);
  boardView.draw(director.view, time);
  scene.render();
  if (state) {
    const now = director.nowServer();
    const eff = director.effPhase;
    renderRankBoard(state, avatarSrc);
    renderPlayers(state, eff, now);
    renderHint(state, eff, now);
    renderOverlay(state, eff, now);
    renderSign(state, now);
    clockTick(state, eff, now);
    processVoice();
    music.duck(!!voice.current || celebrate.active());
    celebrate.tick();
    rankup.tick(eff === 'finished' && director.resultReady, celebrate.active());
    if (celebrate.active() && eff !== 'finished') celebrate.stop(); // sang bước khác (ván mới...) thì dừng ăn mừng
  }
  requestAnimationFrame(frame);
}
requestAnimationFrame(frame);

// ---------------------------------------------------------------- bàn phím + mở khóa tiếng
function unlockVoice() {
  voice.unlock();
  sfx.unlock();
  music.unlock();
}
$('unlock').addEventListener('click', unlockVoice);
window.addEventListener('pointerdown', unlockVoice);
window.addEventListener('keydown', (e) => {
  unlockVoice();
  const k = e.key.toLowerCase();
  if (k === 'f') {
    if (document.fullscreenElement) document.exitFullscreen();
    else document.documentElement.requestFullscreen().catch(() => {});
  } else if (k === 'p') {
    layoutPref = 'portrait';
    applyLayout();
  } else if (k === 'l') {
    layoutPref = 'landscape';
    applyLayout();
  } else if (k === 'm') {
    voice.forceMute = !voice.forceMute;
    sfx.forceMute = voice.forceMute;
    music.forceMute = voice.forceMute;
    sfx.setOptions({});
    music.setOptions({});
    if (voice.forceMute) voice.stop();
  }
});
