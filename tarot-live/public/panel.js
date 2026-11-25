/*
 * BẢNG ĐIỀU KHIỂN (trang chủ http://localhost:3002)
 * Chỉ điều khiển game qua WebSocket - không chứa luật. Màn hình phát nằm ở live.html.
 */
import { connect } from './net.js';
import { Voice } from './voice.js';

const $ = (id) => document.getElementById(id);
const esc = (s) => String(s).replace(/[&<>"]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
const origin = location.origin;
const URL_PORTRAIT = `${origin}/live.html?layout=portrait`;
const URL_LAND = `${origin}/live.html?layout=landscape`;
const TOPIC = { general: 'Tổng quát', love: 'Tình duyên', work: 'Công việc - học tập' };

let S = null;
let formFilled = false;
const voice = new Voice();

const net = connect(
  (s) => {
    S = s;
    render(s);
  },
  (ok) => {
    const c = $('chipWs');
    c.textContent = ok ? '● Game đang chạy' : '● Mất kết nối game';
    c.className = 'chip ' + (ok ? 'on' : 'off');
  },
  (msg) => toast(msg, true)
);
const cmd = (c, extra) => net.command(c, extra);

function toast(text, warn = false) {
  const t = document.createElement('div');
  t.className = 'toast' + (warn ? ' warn' : '');
  t.textContent = text;
  document.body.appendChild(t);
  setTimeout(() => t.remove(), 3500);
}

// ------------------------------------------------------------ màn hình live
function openLive(url, name) {
  const w = window.open(url, name);
  $('popupWarn').classList.toggle('hidden', !!w);
}
$('btnPortrait').onclick = () => openLive(URL_PORTRAIT, 'tarot-live-portrait');
$('btnLandscape').onclick = () => openLive(URL_LAND, 'tarot-live-landscape');
async function copy(text) {
  try {
    await navigator.clipboard.writeText(text);
    toast('Đã chép: ' + text);
  } catch (e) {
    window.prompt('Chép link này:', text);
  }
}
$('copyPortrait').onclick = () => copy(URL_PORTRAIT);
$('copyLandscape').onclick = () => copy(URL_LAND);
$('previewFrame').src = '/live.html?layout=portrait&mute=1';

// ------------------------------------------------------------ nút điều khiển
$('btnSkip').onclick = () => cmd('skip');
$('btnClear').onclick = () => {
  if (confirm('Xóa toàn bộ hàng chờ?')) cmd('clear');
};
$('btnPause').onclick = () => cmd('set', { values: { paused: !(S && S.settings.paused) } });
$('btnDraw').onclick = () => {
  cmd('draw', { name: $('drName').value, spread: $('drSpread').value, topic: $('drTopic').value });
  $('drName').value = '';
};
$('btnTest1').onclick = () => cmd('testDraw', { spread: 1 });
$('btnTest3').onclick = () => cmd('testDraw', { spread: 3 });
$('btnTest5').onclick = () => cmd('testDraw', { spread: 5 });
$('btnVoice').onclick = () => {
  voice.unlock();
  voice.test('mc', 'Xin chào cả nhà, mình là MC Tarot. Hôm nay chúng ta cùng rút bài nhé.');
};
$('btnAnnounce').onclick = () => {
  saveForm();
  setTimeout(() => cmd('announce'), 400);
};

// ------------------------------------------------------------ cài đặt (tự lưu)
const FIELDS = ['title', 'subtitle', 'defaultSpread', 'flipAll', 'allowThree', 'allowFive', 'reverseChance', 'userCooldown', 'maxQueue', 'readSpeed', 'autoDraw', 'autoIdleSeconds', 'giftPriority', 'voiceOn', 'voiceVolume', 'announceText', 'announceEvery'];

function fillForm(set) {
  for (const k of FIELDS) {
    const el = $(k);
    if (!el) continue;
    if (el.type === 'checkbox') el.checked = !!set[k];
    else el.value = set[k];
  }
}

let saveTimer = null;
function saveForm() {
  const v = {};
  for (const k of FIELDS) {
    const el = $(k);
    v[k] = el.type === 'checkbox' ? el.checked : el.value;
  }
  cmd('set', { values: v });
  const s = $('saved');
  s.classList.add('on');
  clearTimeout(saveTimer);
  saveTimer = setTimeout(() => s.classList.remove('on'), 1800);
}
for (const k of FIELDS) {
  const el = $(k);
  el.addEventListener('change', saveForm);
}

// ------------------------------------------------------------ vẽ
let lastHtml = {};
function setHtml(id, html) {
  if (lastHtml[id] === html) return;
  lastHtml[id] = html;
  $(id).innerHTML = html;
}

function render(s) {
  if (!formFilled) {
    fillForm(s.settings);
    formFilled = true;
  }
  const tt = $('chipTt');
  tt.textContent = 'TikTok: ' + (s.connection.text || '…');
  tt.className = 'chip ' + (s.connection.status === 'connected' || s.connection.status === 'demo' ? 'on' : s.connection.status === 'error' ? 'err' : 'wait');
  const ph = $('chipPhase');
  ph.textContent = s.current ? '🎴 Đang bói' : s.settings.paused ? '⏸ Tạm ngưng' : '⏳ Đang chờ';
  $('btnPause').textContent = s.settings.paused ? '▶ Mở lại nhận lượt mới' : '⏸ Tạm ngưng nhận lượt mới';
  $('voiceInfo').textContent = voice.describe();

  const c = s.current;
  if (!c) setHtml('cur', 'Chưa có lượt nào đang chạy. Khi có người xin bài, lượt sẽ tự bắt đầu.');
  else {
    const el = Math.max(0, Math.round(((Date.now() + (s.serverNow - Date.now())) - c.startedAt) / 1000));
    setHtml('cur',
      `<div><span class="nm">${esc(c.user.name)}</span> • ${esc(c.topicLabel)} • ${c.cards.length} lá${c.auto ? ' (tự rút)' : ''}</div>` +
      `<div class="cardsmini">${c.cards.map((x) => `<img class="${x.rev ? 'rev' : ''}" src="/cards/${x.id}.jpg" title="${esc(x.vi)}">`).join('')}</div>` +
      `<div class="hint tiny">${c.cards.map((x) => esc(x.vi) + (x.rev ? ' (ngược)' : '')).join(' • ')}</div>`);
  }

  $('qCount').textContent = s.queueTotal ? `(${s.queueTotal} người)` : '';
  setHtml('queue', s.queue.length
    ? s.queue.map((q, i) => `<li><span>${i + 1}.</span><span class="nm">${esc(q.name)}</span><span class="hint">${q.spread} lá • ${esc(TOPIC[q.topic] || '')}</span>${q.vip ? '<span class="vip">★ ưu tiên</span>' : ''}<button data-bump="${q.id}">Ưu tiên</button><button data-rm="${q.id}">Xóa</button></li>`).join('')
    : '<li class="hint">Hàng chờ trống.</li>');
  setHtml('hist', s.history.length
    ? s.history.map((h) => `<li><b>${esc(h.name)}</b> <span class="hint">${esc(h.topic)}${h.auto ? ' • tự rút' : ''}:</span> ${h.cards.map(esc).join(', ')}</li>`).join('')
    : '<li class="hint">Chưa có lượt nào.</li>');
  setHtml('feed', s.feed.slice().reverse().map((f) => `<li>${esc(f.text)}</li>`).join('') || '<li class="hint">Chưa có.</li>');
}

$('queue').addEventListener('click', (e) => {
  const b = e.target.closest('button');
  if (!b) return;
  if (b.dataset.bump) cmd('bump', { id: b.dataset.bump });
  if (b.dataset.rm) cmd('remove', { id: b.dataset.rm });
});
