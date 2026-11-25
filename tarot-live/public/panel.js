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
  if (confirm('Xóa toàn bộ điểm tương tác?')) cmd('clear');
};
$('btnPause').onclick = () => cmd('set', { values: { paused: !(S && S.settings.paused) } });
$('btnDraw').onclick = () => {
  cmd('draw', { name: $('drName').value, topic: $('drTopic').value, dob: $('drDob').value, question: $('drQuestion').value });
  $('drName').value = '';
  $('drDob').value = '';
  $('drQuestion').value = '';
};
$('btnTest1').onclick = () => cmd('testDraw', { spread: 1 });
$('btnTest3').onclick = () => cmd('testDraw', { spread: 3 });
$('btnTest5').onclick = () => cmd('testDraw', { spread: 5 });
$('btnVoice').onclick = () => {
  voice.unlock();
  voice.test('mc', 'Xin chào cả nhà, mình là MC Tarot. Hít một hơi thật sâu, và cùng xem lá bài hôm nay muốn nhắn nhủ điều gì nhé.');
};
$('btnAnnounce').onclick = () => {
  saveForm();
  setTimeout(() => cmd('announce'), 400);
};

// ------------------------------------------------------------ cài đặt (tự lưu)
const FIELDS = ['title', 'subtitle', 'minScore', 'reverseChance', 'readSpeed', 'autoDraw', 'autoIdleSeconds', 'giftPriority', 'voiceOn', 'voiceVolume', 'voiceRate', 'voicePitch', 'announceText', 'announceEvery', 'askInfo', 'collectSeconds', 'aiProvider', 'aiModel', 'aiTimeout'];

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

// danh sách giọng tiếng Việt của trình duyệt đang mở bảng điều khiển
let voiceSig = '';
function syncVoiceList(chosen) {
  const sel = $('voiceName');
  const names = voice.viVoices().map((v) => v.name);
  const sig = names.join('|') + '#' + chosen;
  if (sig === voiceSig || document.activeElement === sel) return;
  voiceSig = sig;
  sel.innerHTML = '<option value="">Tự chọn giọng nữ tiếng Việt hay nhất</option>' + names.map((n) => `<option value="${esc(n)}">${esc(n)}</option>`).join('');
  sel.value = names.includes(chosen) ? chosen : '';
}
$('voiceName').addEventListener('change', () => cmd('set', { values: { voiceName: $('voiceName').value } }));

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
  ph.textContent = s.current ? (s.current.pending ? '🤖 Xáo bài / chờ AI' : '🎴 Đang bói') : s.collect ? '📝 Chờ thông tin' : s.preparing ? '🤖 AI đang viết' : s.settings.paused ? '⏸ Tạm ngưng' : '⏳ Đang chờ người tương tác';
  $('btnPause').textContent = s.settings.paused ? '▶ Mở lại nhận lượt mới' : '⏸ Tạm ngưng nhận lượt mới';
  voice.setSettings({ mcVoice: s.settings.voiceName, mcRate: Number(s.settings.voiceRate), mcPitch: Number(s.settings.voicePitch) });
  syncVoiceList(s.settings.voiceName);
  $('voiceInfo').textContent = voice.describe();
  const ki = $('aiKeyInfo');
  if (s.ai.provider === 'off') ki.textContent = 'AI đang tắt: game đọc bằng lời viết sẵn.';
  else if (!s.ai.hasKey) ki.textContent = '⚠️ Chưa thấy file ai-api-key.txt cạnh file CHAY-GAME.bat nên game vẫn đọc bằng lời viết sẵn.';
  else ki.textContent = '✅ Đã thấy khóa AI. Nếu AI lỗi hoặc quá chậm, game tự đọc bằng lời viết sẵn.';

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
    ? s.queue.map((q, i) => `<li><span>${i + 1}.</span><span class="nm">${esc(q.name)}</span><span class="hint">${q.score} điểm${q.seen ? ' • đã xem: ' + esc(q.seen) : ''}</span>${q.vip ? '<span class="vip">★ đủ điểm</span>' : ''}<button data-bump="${esc(q.id)}">Chọn ngay</button><button data-rm="${esc(q.id)}">Loại</button></li>`).join('')
    : '<li class="hint">Chưa có ai tương tác.</li>');
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
