/*
 * THẺ "CẬP NHẬT PHẦN MỀM" trên bảng điều khiển. Chỉ gọi /update/check và /update/apply của máy chủ (src/updater.js).
 */
const $ = (id) => document.getElementById(id);
const say = (t) => { $('updMsg').textContent = t; };
let hasNew = false;

async function check(quiet) {
  if (!quiet) say('Đang kiểm tra…');
  try {
    const r = await (await fetch('/update/check', { cache: 'no-store' })).json();
    if (!r.ok) { $('updVer').textContent = 'bản ' + (r.current || '?'); if (!quiet) say('Không kiểm tra được (cần có mạng): ' + r.error); return; }
    $('updVer').textContent = 'bản ' + r.current;
    hasNew = r.hasNew;
    $('updGo').classList.toggle('hidden', !r.hasNew);
    if (r.hasNew) say(`Có bản mới: ${r.latest} (bạn đang dùng ${r.current}). ${r.notes ? 'Nội dung: ' + r.notes + '. ' : ''}Bấm "Cập nhật ngay" — game sẽ tự khởi động lại khoảng 10 giây.`);
    else if (!quiet) say(`Bạn đang dùng bản mới nhất (${r.current}).`);
  } catch (e) { if (!quiet) say('Không kết nối được máy chủ game.'); }
}

async function apply() {
  if (!hasNew) return;
  if (!confirm('Game sẽ tự khởi động lại (khoảng 10 giây). Nếu đang LIVE thì màn hình sẽ bị gián đoạn một lúc. Cập nhật bây giờ?')) return;
  $('updGo').classList.add('hidden');
  say('Đang tải và cập nhật…');
  try {
    const r = await (await fetch('/update/apply', { method: 'POST' })).json();
    if (!r.ok) { say('Lỗi: ' + r.error); $('updGo').classList.remove('hidden'); return; }
    if (!r.changed) { say('Không có gì thay đổi.'); return; }
    say(`Đã cập nhật ${r.changed} file lên bản ${r.version}${r.note ? '. ' + r.note : ''}. Đang khởi động lại…`);
    waitBack();
  } catch (e) { say('Mất kết nối khi cập nhật — nếu game vừa tắt, chạy lại CHAY-GAME.bat.'); }
}

function waitBack() {
  let seenDown = false, tries = 0;
  const t = setInterval(async () => {
    tries++;
    try {
      await fetch('/update/check', { cache: 'no-store' });
      if (seenDown || tries > 6) { clearInterval(t); location.reload(); }
    } catch (e) { seenDown = true; }
    if (tries > 60) { clearInterval(t); say('Game chưa tự mở lại. Hãy chạy lại CHAY-GAME.bat (hoặc chay-termux.sh).'); }
  }, 1500);
}

$('updCheck').onclick = () => check(false);
$('updGo').onclick = apply;
setTimeout(() => check(true), 1500);
