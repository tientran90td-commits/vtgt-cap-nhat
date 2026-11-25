/*
 * MÀN HÌNH LIVE TAROT: nhận trạng thái từ máy chủ, vẽ lá bài (lật có ảnh), lời đọc và hàng chờ.
 * Buổi bói đang chạy là 1 danh sách "bước" (xáo bài, từng lá, tổng kết, kết); trang này chạy theo giờ của máy chủ.
 */
import { connect } from './net.js';
import { Voice } from './voice.js';
import { Sfx } from './sfx.js';

const $ = (id) => document.getElementById(id);
const q = new URLSearchParams(location.search);
const muted = q.get('mute') === '1';
if (q.get('bg') === 'none') document.body.classList.add('nobg');
let layoutPref = q.get('layout') || '';

const voice = new Voice();
voice.forceMute = muted;
const sfx = new Sfx();
sfx.on = !muted;

// ---------------------------------------------------------------- khung hình
function fitStage() {
  const W = window.innerWidth;
  const H = window.innerHeight;
  const lay = layoutPref === 'portrait' || layoutPref === 'landscape' ? layoutPref : W / H > 1.2 ? 'landscape' : 'portrait';
  const ratio = lay === 'portrait' ? 9 / 16 : 16 / 9;
  let sw = W;
  let sh = W / ratio;
  if (sh > H) {
    sh = H;
    sw = H * ratio;
  }
  const st = $('stage');
  st.dataset.layout = lay;
  st.style.width = sw + 'px';
  st.style.height = sh + 'px';
  document.documentElement.style.fontSize = (lay === 'portrait' ? sh / 71.1 : sh / 40) + 'px';
}
window.addEventListener('resize', fitStage);
fitStage();

// ---------------------------------------------------------------- trạng thái
let S = null;
let offset = 0;
let builtFor = null; // id buổi bói đã dựng lá bài ('idle' nếu đang chờ)
let lastStep = -1;
let lastCue = null;
let lastAnnounce = 0;

const avatarUrl = (a) => (!a ? '' : /^https?:/i.test(a) ? '/avatar?u=' + encodeURIComponent(a) : a);

function slot(cardId, pos, rev) {
  const el = document.createElement('div');
  el.className = 'slot' + (rev ? ' rev' : '');
  el.innerHTML = `<div class="pos"></div><div class="inner"><div class="back"><img src="/cards/back.jpg" alt=""></div><div class="face"><img ${cardId ? `src="/cards/${cardId}.jpg"` : ''} alt=""></div></div>`;
  el.querySelector('.pos').textContent = pos || '';
  return el;
}

function buildCards(cur) {
  const box = $('cards');
  box.innerHTML = '';
  box.className = '';
  if (!cur) {
    box.classList.add('idle', 'three');
    for (let i = 0; i < 3; i++) box.appendChild(slot('', '', false));
    return;
  }
  if (cur.cards.length === 3) box.classList.add('three');
  if (cur.cards.length === 5) box.classList.add('five');
  for (const c of cur.cards) box.appendChild(slot(c.id, c.pos, c.rev));
}

function fitText() {
  const t = $('ctext');
  t.style.fontSize = '';
  let size = parseFloat(getComputedStyle(t).fontSize);
  const min = size * 0.62;
  while (t.scrollHeight > t.clientHeight + 1 && size > min) {
    size -= size * 0.04;
    t.style.fontSize = size + 'px';
  }
}

function setPanel(name, small, kw, text) {
  const r = $('reading');
  $('cname').innerHTML = '';
  $('cname').textContent = name;
  if (small) {
    const s = document.createElement('small');
    s.textContent = small;
    $('cname').appendChild(s);
  }
  $('ckw').textContent = kw ? 'Từ khóa: ' + kw : '';
  $('ctext').textContent = text || '';
  r.classList.remove('swap');
  void r.offsetWidth;
  r.classList.add('swap');
  fitText();
}

function stepIndex(cur, el) {
  let k = 0;
  for (let i = 0; i < cur.steps.length; i++) if (cur.steps[i].at <= el) k = i;
  return k;
}

function render() {
  if (!S) return;
  const now = Date.now() + offset;
  const cur = S.current;
  const stage = $('stage');
  stage.classList.toggle('reading', !!cur);

  const key = cur ? cur.id : 'idle';
  if (builtFor !== key) {
    builtFor = key;
    lastStep = -1;
    buildCards(cur);
    if (cur) voice.stop();
  }
  const box = $('cards');
  const slots = [...box.children];

  const cb = $('collectBox');
  const col = !cur && S.collect;
  const prep = !cur && S.preparing;
  cb.classList.toggle('hidden', !col);
  stage.classList.toggle('collecting', !!col);
  if (col) {
    $('cbName').textContent = S.collect.name;
    $('cbSec').textContent = Math.max(0, Math.ceil((S.collect.until - now) / 1000));
  }
  if (!cur && (col || prep)) {
    $('who').style.visibility = 'hidden';
    box.classList.toggle('shuffle', !!prep);
    const k = col ? 'collect' + S.collect.name : 'prep' + S.preparing.name;
    if (lastStep !== k) {
      lastStep = k;
      if (col) setPanel('Chờ thông tin của bạn…', '', '', `${S.collect.name} ơi, hãy bình luận họ tên, ngày tháng năm sinh và chuyện bạn muốn xem.`);
      else {
        sfx.shuffle();
        setPanel('Đang xáo bài…', '', '', `${S.preparing.name}, mình đang chuẩn bị lời đọc cho bạn…`);
      }
    }
    return;
  }

  if (!cur) {
    box.classList.remove('shuffle');
    $('who').style.visibility = 'hidden';
    if (lastStep !== -2) {
      lastStep = -2;
      const h = S.history[0];
      const last = h ? `Vừa rồi: ${h.name} rút ${h.cards.join(', ')}` : 'Mỗi lượt có lời đọc riêng cho bạn.';
      setPanel('Mời bạn rút bài ✨', '', '', `Bình luận !bai để vào hàng chờ. ${last}`);
    }
    return;
  }

  $('who').style.visibility = 'visible';
  $('whoName').textContent = cur.user.name;
  $('whoTopic').textContent = cur.topicLabel;
  const img = $('whoImg');
  const av = cur.auto ? '' : avatarUrl(cur.user.avatar);
  if (av) {
    if (img.getAttribute('src') !== av) img.src = av;
    img.style.display = '';
  } else img.style.display = 'none';

  const el = now - cur.startedAt;
  const si = stepIndex(cur, el);
  const st = cur.steps[si];
  if (si === lastStep) return;
  lastStep = si;

  if (voice.settings.on || true) voice.push({ role: 'mc', text: st.say, prio: 3 });
  box.classList.toggle('shuffle', st.kind === 'shuffle');
  if (st.kind === 'shuffle') {
    sfx.shuffle();
    slots.forEach((s) => s.classList.remove('flipped', 'dim', 'active', 'show'));
    setPanel('Đang xáo bài…', '', '', st.say);
  } else if (st.kind === 'reveal') {
    slots.forEach((s) => {
      s.classList.add('flipped', 'show');
      s.classList.remove('dim', 'active');
    });
    sfx.flip();
    setPanel('Lật bài!', '', '', cur.cards.map((c) => c.vi + (c.rev ? ' (ngược)' : '')).join(' • '));
  } else if (st.kind === 'card') {
    const c = cur.cards[st.idx];
    slots.forEach((s, i) => {
      s.classList.toggle('flipped', cur.flipAll || i <= st.idx);
      s.classList.toggle('show', cur.flipAll || i <= st.idx);
      s.classList.toggle('active', i === st.idx);
      s.classList.toggle('dim', i !== st.idx && cur.cards.length > 1);
    });
    sfx.flip();
    setPanel(`${cur.cards.length > 1 ? c.pos + ' • ' : ''}${c.vi}`, c.rev ? '(lá ngược)' : '', c.kw, c.text);
  } else if (st.kind === 'sum') {
    slots.forEach((s) => {
      s.classList.add('flipped', 'show');
      s.classList.remove('dim', 'active');
    });
    const sumText = st.say.replace(/^Tổng kết:\s*/, '');
    setPanel('Tổng kết', '', '', sumText.charAt(0).toUpperCase() + sumText.slice(1));
  } else {
    slots.forEach((s) => {
      s.classList.add('flipped', 'show');
      s.classList.remove('dim', 'active');
    });
    sfx.done();
    setPanel('Cảm ơn bạn 🌙', '', '', st.say);
  }
}

function renderSide() {
  if (!S) return;
  const set = S.settings;
  $('demoRibbon').classList.toggle('hidden', !S.demo);
  $('title').textContent = '🔮 ' + (set.title || 'Tarot LIVE');
  $('hint').textContent = set.subtitle || '';
  document.title = (set.title || 'Tarot LIVE') + ' - màn hình phát';
  const ql = $('queueList');
  ql.innerHTML = '';
  if (!S.queue.length) {
    const s = document.createElement('span');
    s.className = 'qmore';
    s.textContent = 'chưa có ai — gõ !bai để vào hàng chờ';
    ql.appendChild(s);
  } else {
    for (const it of S.queue.slice(0, 4)) {
      const c = document.createElement('span');
      c.className = 'qchip' + (it.vip ? ' vip' : '');
      c.textContent = `${it.name} · ${it.spread} lá`;
      ql.appendChild(c);
    }
    if (S.queueTotal > 4) {
      const m = document.createElement('span');
      m.className = 'qmore';
      m.textContent = `+${S.queueTotal - 4}`;
      ql.appendChild(m);
    }
  }
  $('ticker').textContent = S.feed.slice(-2).map((f) => f.text).join('   ');
  const a = S.announce;
  const ann = $('announce');
  if (a) {
    ann.textContent = a.text;
    ann.classList.remove('hidden');
  } else ann.classList.add('hidden');
  if (a && a.id !== lastAnnounce) lastAnnounce = a.id;

  // giọng đọc: cài đặt + câu cảm ơn / mời gọi từ máy chủ
  voice.setSettings({ on: set.voiceOn, volume: set.voiceVolume, mcRate: 0.98, mcPitch: 1.0 });
  const maxId = S.cues.length ? S.cues[S.cues.length - 1].id : 0;
  if (lastCue === null) lastCue = maxId; // lần đầu nối: không đọc lại câu cũ
  for (const c of S.cues) if (c.id > lastCue) voice.push({ role: 'mc', text: c.text, prio: c.prio || 2 });
  lastCue = Math.max(lastCue, maxId);
}

connect(
  (st) => {
    S = st;
    offset = st.serverNow - Date.now();
    renderSide();
    render();
  },
  () => {}
);
setInterval(render, 120);
setInterval(() => $('unlock').classList.toggle('hidden', !(voice.needsGesture && !muted)), 1000);

function unlockAll() {
  voice.unlock();
  sfx.unlock();
}
window.addEventListener('pointerdown', unlockAll);
$('unlock').addEventListener('click', unlockAll);
window.addEventListener('keydown', (e) => {
  unlockAll();
  const k = e.key.toLowerCase();
  if (k === 'f') document.fullscreenElement ? document.exitFullscreen() : document.documentElement.requestFullscreen().catch(() => {});
  else if (k === 'p') { layoutPref = 'portrait'; fitStage(); }
  else if (k === 'l') { layoutPref = 'landscape'; fitStage(); }
  else if (k === 'm') {
    voice.forceMute = !voice.forceMute;
    sfx.on = !voice.forceMute;
    if (voice.forceMute) voice.stop();
  }
});
