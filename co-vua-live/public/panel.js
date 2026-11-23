/*
 * BẢNG ĐIỀU KHIỂN (trang chủ http://localhost:3000)
 * Chỉ điều khiển game qua WebSocket - không chứa luật chơi. Màn hình phát nằm ở live.html.
 */
import { connect } from './net.js';
import { Voice } from './voice.js';
import { Sfx } from './sfx.js';
import { avatarSrc } from './avatar.js';

const $ = (id) => document.getElementById(id);
const esc = (s) => String(s).replace(/[&<>"]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
const origin = location.origin;
const URL_PORTRAIT = `${origin}/live.html?layout=portrait`;
const URL_LAND = `${origin}/live.html?layout=landscape`;

let S = null;
const voice = new Voice();
const sfx = new Sfx();
let lastNotice = 0;

const net = connect(
  (s) => {
    S = s;
    render(s);
  },
  (ok) => {
    const c = $('chipWs');
    c.textContent = ok ? '● Game đang chạy' : '● Mất kết nối game';
    c.className = 'chip ' + (ok ? 'on' : 'off');
  }
);
const cmd = (c, extra) => net.command(c, extra);

// ------------------------------------------------------------ mở màn hình live
function openLive(url, name) {
  const w = window.open(url, name);
  $('popupWarn').classList.toggle('hidden', !!w);
  if (w) {
    try {
      w.focus();
    } catch (e) {
      /* bỏ qua */
    }
  }
}
$('btnPortrait').onclick = () => openLive(URL_PORTRAIT, 'covua-live-portrait');
$('btnLandscape').onclick = () => openLive(URL_LAND, 'covua-live-landscape');
async function copy(text, btn) {
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
$('btnStart').onclick = () => cmd('startNow');
$('btnSkip').onclick = () => cmd('skipTurn');
$('btnConfirm').onclick = () => cmd('skipConfirm');
$('btnAddTime').onclick = () => cmd('addTime', { seconds: 15 });
$('btnForfeitX').onclick = () => confirm('Xử thua người chơi TRẮNG ?') && cmd('forfeit', { mark: 'X' });
$('btnForfeitO').onclick = () => confirm('Xử thua người chơi ĐEN ?') && cmd('forfeit', { mark: 'O' });
$('btnReset').onclick = () => confirm('Bắt đầu lại từ đầu (xoá ván đang chơi)?') && cmd('reset');
$('demoToggle').onchange = (e) => cmd('demo', { on: e.target.checked });

// ------------------------------------------------------------ gõ thử
function who() {
  const v = $('tWho').value;
  if (v === 'host') return { user: 'host', name: 'Chủ phòng' };
  if (v === 'X' || v === 'O') {
    const p = S && S.players && S.players[v];
    if (p) return { user: p.id, name: p.name };
    toast('Chưa có người chơi ' + (v === 'X' ? 'trắng' : 'đen') + ' — đang chờ chọn người.', 'warn');
    return null;
  }
  return { user: 'khach-thu', name: 'Khán giả thử' };
}
function sendText() {
  const w = who();
  const text = $('tText').value.trim();
  if (!w || !text) return;
  cmd('test', { kind: 'comment', text, ...w });
  $('tText').value = '';
}
$('tSend').onclick = sendText;
$('tText').onkeydown = (e) => e.key === 'Enter' && sendText();
$('tLike').onclick = () => {
  const w = who();
  if (w) cmd('test', { kind: 'like', count: 15, ...w });
};
document.querySelectorAll('.tGift').forEach((b) => {
  b.onclick = () => {
    const w = who();
    if (w) cmd('test', { kind: 'gift', gift: b.dataset.g, diamonds: Number(b.dataset.d), ...w });
  };
});

// ------------------------------------------------------------ cài đặt ván
const NUM_KEYS = ['lobbySeconds', 'nextLobbySeconds', 'coinSeconds', 'turnSeconds', 'extraTimeSeconds', 'extraTimesPerGame', 'resultSeconds', 'maxTimeouts', 'maxWinStreak', 'minPointsToPlay'];
let savedTimer = null;
function flashSaved() {
  $('saved').textContent = '✓ đã lưu';
  clearTimeout(savedTimer);
  savedTimer = setTimeout(() => ($('saved').textContent = ''), 1800);
}
document.querySelectorAll('#setForm [data-k]').forEach((el) => {
  el.onchange = () => {
    const k = el.dataset.k;
    const v = el.type === 'checkbox' ? el.checked : el.tagName === 'SELECT' ? el.value : Number(el.value);
    cmd('settings', { patch: { [k]: v } });
    flashSaved();
  };
});
function fillSettings(st) {
  if (!st) return;
  document.querySelectorAll('#setForm [data-k]').forEach((el) => {
    if (document.activeElement === el) return;
    const v = st[el.dataset.k];
    if (el.type === 'checkbox') el.checked = !!v;
    else if (String(el.value) !== String(v)) el.value = v;
  });
}

// ------------------------------------------------------------ giọng đọc
const vPatch = (p) => {
  cmd('settings', { patch: { voice: p } });
  flashSaved();
};
$('vOn').onchange = (e) => vPatch({ on: e.target.checked });
$('vMoves').onchange = (e) => vPatch({ readMoves: e.target.checked });
$('vTalk').onchange = (e) => vPatch({ talk: e.target.value });
$('vVol').onchange = (e) => vPatch({ volume: Number(e.target.value) });
$('vBig').onchange = (e) => vPatch({ bigGiftDiamonds: Number(e.target.value) });
$('vMc').onchange = (e) => vPatch({ mcVoice: e.target.value });
$('vRef').onchange = (e) => vPatch({ refVoice: e.target.value });
$('vTestMc').onclick = () => testSay('mc', 'Xin chào các bạn, mình là điều phối viên của Cờ vua LIVE. Chúc cả nhà chơi vui!');
$('vTestRef').onclick = () => testSay('ref', 'Tôi là trọng tài. Ván cờ bắt đầu, mời hai người chơi.');
function testSay(role, text) {
  voice.unlock();
  voice.setSettings({ ...(S && S.settings ? S.settings.voice : {}), on: true });
  voice.test(role, text);
}
// ---- âm thanh hiệu ứng
const sPatch = (p) => {
  cmd('settings', { patch: { sfx: p } });
  flashSaved();
};
$('sOn').onchange = (e) => sPatch({ on: e.target.checked });
$('sVol').onchange = (e) => sPatch({ volume: Number(e.target.value) });
const mPatch = (p) => {
  cmd('settings', { patch: { music: p } });
  flashSaved();
};
$('mOn').onchange = (e) => mPatch({ on: e.target.checked });
$('mVol').onchange = (e) => mPatch({ volume: Number(e.target.value) });
document.querySelectorAll('.sfxTest').forEach((b) => {
  b.onclick = () => {
    sfx.unlock();
    sfx.setOptions({ on: true, volume: S && S.settings && S.settings.sfx ? S.settings.sfx.volume : 0.7 });
    setTimeout(() => (b.dataset.s === 'place' ? sfx.place('X') : sfx[b.dataset.s]()), 60);
  };
});

// ---- chỉnh tốc độ / cao độ giọng
for (const id of ['mcRate', 'mcPitch', 'refRate', 'refPitch']) {
  const el = $(id);
  el.oninput = () => ($(id + 'V').textContent = el.value);
  el.onchange = () => vPatch({ [id]: Number(el.value) });
}
document.querySelectorAll('.preset').forEach((b) => {
  b.onclick = () => {
    const r = b.dataset.r;
    vPatch({ [r + 'Rate']: Number(b.dataset.rate), [r + 'Pitch']: Number(b.dataset.pitch) });
    setTimeout(() => (r === 'mc' ? $('vTestMc') : $('vTestRef')).click(), 350);
  };
});
$('vAuto').onclick = () => vPatch({ mcRate: null, mcPitch: null, refRate: null, refPitch: null });

let voiceSig = '';
function fillVoice(st) {
  if (!st) return;
  const v = st.voice;
  voice.setSettings(v);
  const list = voice.viVoices();
  const sig = list.map((x) => x.name).join('|') + '#' + v.mcVoice + '#' + v.refVoice;
  if (sig !== voiceSig && document.activeElement !== $('vMc') && document.activeElement !== $('vRef')) {
    voiceSig = sig;
    const opts = (cur) =>
      '<option value="">Tự chọn</option>' +
      list.map((x) => `<option value="${esc(x.name)}"${x.name === cur ? ' selected' : ''}>${esc(x.name)}</option>`).join('');
    $('vMc').innerHTML = opts(v.mcVoice);
    $('vRef').innerHTML = opts(v.refVoice);
  }
  if (document.activeElement !== $('vVol')) $('vVol').value = v.volume;
  if (document.activeElement !== $('vBig')) $('vBig').value = v.bigGiftDiamonds;
  $('vOn').checked = !!v.on;
  $('vMoves').checked = !!v.readMoves;
  if (document.activeElement !== $('vTalk')) $('vTalk').value = v.talk || 'normal';
  const sl = (id, val, def) => {
    if (document.activeElement === $(id)) return;
    $(id).value = typeof val === 'number' ? val : def;
    $(id + 'V').textContent = typeof val === 'number' ? val : 'tự động';
  };
  sl('mcRate', v.mcRate, 1.05);
  sl('mcPitch', v.mcPitch, 1.05);
  sl('refRate', v.refRate, 1.0);
  sl('refPitch', v.refPitch, 0.95);
  $('vNote').textContent = voice.describe();
}
window.speechSynthesis && window.speechSynthesis.addEventListener('voiceschanged', () => {
  voiceSig = '';
  if (S) fillVoice(S.settings);
});

// ------------------------------------------------------------ sửa thoại
const scriptEls = new Map(); // key -> {root, ta, en, state}
const sendTimers = new Map();

function buildScript(items) {
  const host = $('scriptList');
  host.innerHTML = '';
  scriptEls.clear();
  let group = null;
  for (const it of items) {
    if (it.group !== group) {
      group = it.group;
      const g = document.createElement('div');
      g.className = 'sg';
      g.textContent = group;
      host.appendChild(g);
    }
    const root = document.createElement('div');
    root.className = 'sc';
    root.innerHTML = `
      <div class="hd"><span class="lb">${esc(it.label)}</span><span class="role ${it.role}">${it.role === 'mc' ? '🎤 Điều phối' : '⚖️ Trọng tài'}</span></div>
      <textarea rows="2"></textarea>
      <div class="vars"></div>
      <div class="ft">
        <button data-a="test">▶ Thử đọc</button>
        <button data-a="def">↩ Về mặc định</button>
        <label><input type="checkbox" data-a="en"> Dùng câu này</label>
      </div>`;
    const ta = root.querySelector('textarea');
    ta.value = it.text;
    ta.rows = Math.min(6, Math.max(2, it.text.split('\n').length + 0));
    const vars = root.querySelector('.vars');
    for (const v of it.vars || []) {
      const b = document.createElement('button');
      b.textContent = '{' + v + '}';
      b.title = (S && S.scriptVars && S.scriptVars[v]) || '';
      b.onclick = () => {
        const a = ta.selectionStart ?? ta.value.length;
        const z = ta.selectionEnd ?? a;
        ta.value = ta.value.slice(0, a) + '{' + v + '}' + ta.value.slice(z);
        ta.focus();
        ta.selectionStart = ta.selectionEnd = a + v.length + 2;
        queueSend(it.key);
      };
      vars.appendChild(b);
    }
    const en = root.querySelector('[data-a=en]');
    en.checked = it.enabled;
    ta.oninput = () => queueSend(it.key);
    en.onchange = () => queueSend(it.key, 0);
    root.querySelector('[data-a=def]').onclick = () => {
      cmd('scriptReset', { key: it.key });
      toast('Đã trả về thoại mặc định');
    };
    root.querySelector('[data-a=test]').onclick = () => {
      const lines = ta.value.split('\n').map((x) => x.trim()).filter(Boolean);
      if (!lines.length) return;
      const sample = (S && S.scriptSample) || {};
      const line = lines[Math.floor(Math.random() * lines.length)].replace(/\{(\w+)\}/g, (m, k) => (sample[k] !== undefined ? sample[k] : m));
      testSay(it.role, line);
    };
    host.appendChild(root);
    scriptEls.set(it.key, { root, ta, en, it });
  }
}
function queueSend(key, delay = 500) {
  const e = scriptEls.get(key);
  if (!e) return;
  clearTimeout(sendTimers.get(key));
  sendTimers.set(
    key,
    setTimeout(() => {
      cmd('script', { key, text: e.ta.value, enabled: e.en.checked });
      flashSaved();
    }, delay)
  );
}
let scriptSig = '';
function fillScript(items) {
  if (!items) return;
  const sig = items.map((i) => i.key).join(',');
  if (sig !== scriptSig) {
    scriptSig = sig;
    buildScript(items);
    return;
  }
  for (const it of items) {
    const e = scriptEls.get(it.key);
    if (!e) continue;
    if (document.activeElement !== e.ta && !sendTimers.get(it.key) && e.ta.value !== it.text) e.ta.value = it.text;
    if (document.activeElement !== e.en) e.en.checked = it.enabled;
    e.root.classList.toggle('edited', it.edited);
    e.root.classList.toggle('off', !it.enabled);
  }
}
$('scriptAll').onclick = () => {
  if (!confirm('Khôi phục TẤT CẢ câu thoại về bản gốc?')) return;
  cmd('scriptReset', { key: '*' });
  scriptSig = '';
  toast('Đã khôi phục thoại gốc');
};

// ------------------------------------------------------------ hiển thị chung
const PHASE = { lobby: 'Chọn người chơi', confirm: 'Chờ thả tim xác nhận', coin: 'Tung đồng xu', playing: 'Đang đấu', finished: 'Kết quả ván' };
function render(s) {
  const tt = $('chipTt');
  const c = s.connection || {};
  if (s.demo) {
    tt.textContent = '🧪 Chế độ DEMO';
    tt.className = 'chip wait';
  } else {
    tt.textContent = c.text || 'TikTok…';
    tt.className = 'chip ' + (c.status === 'connected' ? 'on' : c.status === 'error' ? 'err' : 'wait');
  }
  $('chipPhase').textContent = PHASE[s.phase] || s.phase;
  $('demoToggle').checked = !!s.demo;

  const X = s.players && s.players.X;
  const O = s.players && s.players.O;
  let line = '';
  if (X || O) line += `⚪ ${X ? esc(X.name) : '…'}  vs  ⚫ ${O ? esc(O.name) : '…'}`;
  if (s.champion) line += ` • Người giữ bàn: ${esc(s.champion.name)} (thắng ${s.champion.streak})`;
  $('status').innerHTML = line || 'Chưa có người chơi.';

  const top = $('topList');
  top.innerHTML = s.top && s.top.length
    ? s.top.map((u) => `<li><b>${esc(u.name)}</b>${u.suspect ? ' <span title="Nghi auto-click thả tim">⚠</span>' : ''} <span class="pt">${u.points} điểm${u.diamonds ? ' • ' + u.diamonds + '💎' : ''}</span></li>`).join('')
    : '<li class="pt">Chưa ai tương tác.</li>';

  const label = { moved: 'đã đi', ignored: 'bỏ qua', seen: 'chưa tới lượt' };
  const chat = $('chatList');
  const rows = (s.recent || []).slice().reverse();
  chat.innerHTML = rows.length
    ? rows
        .map(
          (r) =>
            `<li><b>${esc(r.name)}:</b> <span>${esc(r.text)}</span>${r.move ? `<span class="tag ${r.status || ''}">${esc(r.move)}${r.status ? ' • ' + (label[r.status] || '') : ''}</span>` : ''}</li>`
        )
        .join('')
    : '<li class="pt">Chưa có bình luận.</li>';

  $('tHint').textContent = s.testApi ? '' : 'Chức năng gõ thử đang tắt trong config.js.';
  fillSettings(s.settings);
  fillVoice(s.settings);
  if (s.settings && s.settings.sfx) {
    $('sOn').checked = !!s.settings.sfx.on;
    if (document.activeElement !== $('sVol')) $('sVol').value = s.settings.sfx.volume;
  }
  if (s.settings && s.settings.music) {
    $('mOn').checked = !!s.settings.music.on;
    if (document.activeElement !== $('mVol')) $('mVol').value = s.settings.music.volume;
  }
  fillScript(s.script);

  if (s.notice && s.notice.id !== lastNotice) {
    if (lastNotice) toast(s.notice.text, s.notice.kind === 'warn' ? 'warn' : '');
    lastNotice = s.notice.id;
  }
}

let toastTimer = null;
function toast(text, kind = '') {
  const t = $('toast');
  t.textContent = text;
  t.className = 'toast ' + kind;
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => t.classList.add('hidden'), 3200);
}

// ------------------------------------------------------------ chọn 2 người xem cho đấu với nhau
const picked = []; // id của tối đa 2 người được chọn
let viewers = [];
let viewersSig = '';
function renderViewers() {
  const q = $('vwSearch').value.trim().toLowerCase();
  const list = viewers.filter((u) => !q || u.name.toLowerCase().includes(q) || String(u.uniqueId || '').toLowerCase().includes(q));
  $('vwCount').textContent = viewers.length ? `(${viewers.length} người)` : '';
  const box = $('vwList');
  const keep = box.scrollTop;
  box.innerHTML = list.length
    ? list
        .map((u) => {
          const i = picked.indexOf(u.id);
          const tag = u.host ? '<span class="tg">chủ phòng</span>' : u.mark ? '<span class="tg">đang chơi</span>' : '';
          const av = u.avatar ? `<img src="${esc(avatarSrc(u.avatar))}" alt="" loading="lazy">` : '<img alt="">';
          return `<li class="${i >= 0 ? 'sel' : ''}" data-id="${esc(u.id)}"><span class="no">${i >= 0 ? i + 1 : ''}</span>${av}<span class="nm"><b>${esc(u.name)}</b></span>${tag}<span class="pt">${u.points} điểm</span></li>`;
        })
        .join('')
    : `<li class="pt">${viewers.length ? 'Không tìm thấy.' : 'Chưa ai bình luận / thả tim / tặng quà. Người xem hiện ra ở đây khi họ tương tác.'}</li>`;
  box.scrollTop = keep;
  const nameOf = (id) => {
    const u = viewers.find((v) => v.id === id);
    return u ? esc(u.name) : '(đã rời)';
  };
  $('vwPick').innerHTML = picked.length ? 'Đã chọn: ' + picked.map(nameOf).join('  vs  ') + (picked.length < 2 ? '  vs  …' : '') : 'Chưa chọn ai.';
}
$('vwList').onclick = (e) => {
  const li = e.target.closest('li[data-id]');
  if (!li) return;
  const id = li.dataset.id;
  const i = picked.indexOf(id);
  if (i >= 0) picked.splice(i, 1);
  else {
    picked.push(id);
    if (picked.length > 2) picked.shift();
  }
  renderViewers();
};
$('vwSearch').oninput = renderViewers;
$('vwClear').onclick = () => {
  picked.length = 0;
  renderViewers();
};
$('vwGo').onclick = () => {
  if (picked.length !== 2) return toast('Hãy chọn đủ 2 người trước.', 'warn');
  const busy = !!S && (S.phase === 'playing' || S.phase === 'coin');
  if (busy && !confirm('Đang có ván. Dừng ván này và cho 2 người đã chọn đấu?')) return;
  cmd('pick', { ids: picked.slice(), force: true, confirmLike: $('vwLike').checked });
  picked.length = 0;
  renderViewers();
};
async function pollViewers() {
  try {
    const r = await fetch('/viewers', { cache: 'no-store' });
    if (r.ok) {
      const data = await r.json();
      const sig = JSON.stringify(data);
      if (sig !== viewersSig) {
        viewersSig = sig;
        viewers = data;
        renderViewers();
      }
    }
  } catch (e) {
    /* mất kết nối: thử lại lần sau */
  }
}
pollViewers();
setInterval(pollViewers, 3000);
