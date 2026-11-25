'use strict';
const $ = (id) => document.getElementById(id);
let eng = { state: 'off' };
let rem = null;
let busy = false;
let lastErr = '';

function setPill() {
  const p = $('pill');
  const map = { off: ['off', 'Đang tắt'], starting: ['wait', 'Đang khởi động…'], on: ['on', 'Đang chạy'], crashed: ['bad', 'Bị lỗi, đã dừng'] };
  const [cls, txt] = map[eng.state] || map.off;
  p.className = 'pill ' + cls;
  p.textContent = txt;
  const run = eng.state === 'on' || eng.state === 'starting';
  $('btnStart').disabled = run;
  $('btnStop').disabled = !run;
  $('mode').disabled = run;
  $('tiktok').disabled = run;
  const ready = eng.state === 'on';
  for (const id of ['liveP', 'liveL', 'panel']) $(id).disabled = !ready;
  $('rOn').disabled = !ready || busy;
  $('rOff').disabled = !ready || !(rem && rem.enabled);
  $('idRow').style.display = $('mode').value === 'tiktok' ? '' : 'none';
}

function setRemote() {
  const el = $('rStat');
  if (lastErr) {
    el.innerHTML = `<span style="color:#ff9a9a">${esc(lastErr)}</span>`;
    return setPill();
  }
  if (!rem) {
    el.innerHTML = '<span class="muted">Chạy game xong mới bật kết nối được.</span>';
    return setPill();
  }
  if (!rem.enabled) {
    el.innerHTML = '<span class="muted">Chưa bật. Nhập tài khoản + mật khẩu rồi bấm "Bật kết nối".</span>';
    return setPill();
  }
  const T = { downloading: `Đang tải thành phần kết nối lần đầu (${rem.progress || 0}%)…`, starting: 'Đang mở đường truyền Internet…', online: 'Đường truyền đã mở', error: 'Đường truyền lỗi, đang thử lại…', off: 'Đã tắt' };
  let h = `Tài khoản: <b>${esc(rem.account)}</b><br>${T[rem.tunnel] || rem.tunnel}`;
  if (rem.tunnel === 'online') h += rem.published ? '<br>✅ Điện thoại đã có thể nối vào (nhập đúng tài khoản + mật khẩu).' : '<br>Đang báo địa chỉ cho điện thoại…';
  if (rem.phones) h += `<br>📱 Đang có <b>${rem.phones}</b> điện thoại kết nối`;
  if (rem.error) h += `<br><span style="color:#ff9a9a">${esc(rem.error)}</span>`;
  el.innerHTML = h;
  setPill();
}

function esc(s) {
  return String(s == null ? '' : s).replace(/[&<>"]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' })[c]);
}

function addLog(l) {
  const box = $('log');
  const stick = box.scrollTop + box.clientHeight >= box.scrollHeight - 20;
  box.textContent += l + '\n';
  if (box.textContent.length > 40000) box.textContent = box.textContent.slice(-30000);
  if (stick) box.scrollTop = box.scrollHeight;
}

function msg(t, ok) {
  const m = $('msg');
  m.textContent = t || '';
  m.className = 'msg' + (ok ? ' ok' : '');
}

$('mode').addEventListener('change', setPill);
$('btnStart').addEventListener('click', async () => {
  msg('');
  const r = await caro.start({ mode: $('mode').value, tiktok: $('tiktok').value });
  if (!r.ok) msg(r.error);
});
$('btnOld').addEventListener('click', async () => {
  const r = await caro.importOld();
  if (r.ok) msg('Đã lấy: ' + r.done.join(' + ') + '. Bấm "Bắt đầu" để dùng.', true);
  else if (r.error) msg(r.error);
});
$('btnStop').addEventListener('click', () => caro.stop());
$('liveP').addEventListener('click', () => caro.openLive('portrait'));
$('liveL').addEventListener('click', () => caro.openLive('landscape'));
$('panel').addEventListener('click', () => caro.openPanel());
$('folder').addEventListener('click', () => caro.openFolder());
$('rOn').addEventListener('click', async () => {
  busy = true;
  lastErr = '';
  setPill();
  const r = await caro.remoteConfig({ account: $('acc').value, password: $('pw').value, enabled: true });
  busy = false;
  if (!r.ok) lastErr = r.error || 'Không bật được';
  else {
    $('pw').value = '';
    rem = r;
  }
  setRemote();
});
$('rOff').addEventListener('click', async () => {
  lastErr = '';
  const r = await caro.remoteConfig({ enabled: false });
  if (r && r.ok) rem = r;
  setRemote();
});

caro.on('log', addLog);
caro.on('engine', (s) => {
  eng = s;
  if (s.state === 'off') rem = null;
  setRemote();
});
caro.on('remote', (r) => {
  rem = r;
  setRemote();
});

(async () => {
  const s = await caro.state();
  eng = s.engine;
  rem = s.remote;
  $('ver').textContent = 'bản ' + s.version;
  $('mode').value = (s.ui && s.ui.mode) || (s.engine.tiktok ? 'tiktok' : 'demo');
  $('tiktok').value = s.engine.tiktok || '';
  $('edgeNote').textContent = s.edge ? 'Màn hình LIVE mở bằng Microsoft Edge để có giọng đọc tiếng Việt tự nhiên.' : 'Không thấy Microsoft Edge nên màn hình LIVE mở bằng cửa sổ của app (có thể không có giọng đọc tiếng Việt tự nhiên).';
  for (const l of s.logs) addLog(l);
  setRemote();
})();
