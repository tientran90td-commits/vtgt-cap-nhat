/*
 * THẺ "THÔNG BÁO CHO NGƯỜI XEM" trên bảng điều khiển (module riêng).
 * Gửi lệnh announce / announceClear tới máy chủ; nhớ 4 thông báo gần nhất để bấm gửi lại nhanh.
 */
import { connect } from './net.js';
const $ = (id) => document.getElementById(id);
const net = connect((s) => {
  const box = $('annRepeatState');
  const r = s && s.announceRepeat;
  box.classList.toggle('hidden', !r);
  if (r) box.textContent = '🔁 Đang lặp lại mỗi ' + (r.every >= 60 ? (r.every % 60 ? r.every + ' giây' : r.every / 60 + ' phút') : r.every + ' giây') + ' — bấm "Tắt" để dừng.';
}, null);
const KEY = 'caro.announce.recent';

function recent() {
  try { return JSON.parse(localStorage.getItem(KEY) || '[]').slice(0, 4); } catch (e) { return []; }
}
function remember(t) {
  const list = [t, ...recent().filter((x) => x !== t)].slice(0, 4);
  try { localStorage.setItem(KEY, JSON.stringify(list)); } catch (e) { /* bỏ qua */ }
  drawRecent();
}
function drawRecent() {
  const box = $('annRecent');
  box.replaceChildren();
  for (const t of recent()) {
    const b = document.createElement('button');
    b.type = 'button';
    b.textContent = t.length > 28 ? t.slice(0, 28) + '…' : t;
    b.title = t;
    b.onclick = () => { $('annText').value = t; $('annText').focus(); };
    box.appendChild(b);
  }
}

$('annSend').onclick = () => {
  const text = $('annText').value.trim();
  if (!text) { $('annText').focus(); return; }
  let every = Number($('annEvery').value) || 0;
  if (every < 0) every = Number($('annEveryCustom').value) || 0;
  net.command('announce', { text, seconds: Number($('annSecs').value) || 0, every, speakRepeat: $('annSpeakRepeat').checked });
  remember(text);
};
$('annEvery').onchange = () => { $('annEveryCustom').style.display = Number($('annEvery').value) < 0 ? '' : 'none'; };
$('annClear').onclick = () => net.command('announceClear');
$('annText').addEventListener('keydown', (e) => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); $('annSend').click(); } });
drawRecent();
