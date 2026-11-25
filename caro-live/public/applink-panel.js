/*
 * THẺ "KẾT NỐI APP CARO TRỢ THỦ" trên bảng điều khiển. Chỉ gọi /app-link của máy chủ (src/applink.js).
 */
const $ = (id) => document.getElementById(id);
let cur = null;

function show(r) {
  cur = r;
  const on = r.wifi;
  $('linkWifi').textContent = on ? '📴 Tắt kết nối qua WiFi' : '📶 Bật kết nối qua WiFi';
  $('linkCode').classList.toggle('hidden', !on);
  const lines = [];
  lines.push('• Cùng điện thoại (Termux): trong app nhập địa chỉ <b>' + r.local + '</b>, không cần mã.');
  if (on) {
    const ad = r.addresses && r.addresses.length ? r.addresses.map((a) => '<b>' + a + '</b>' + (/^100\./.test(a) ? ' (Tailscale — dùng được cả khi khác WiFi)' : '')).join(' hoặc ') : '(không thấy địa chỉ WiFi — kiểm tra máy đã vào WiFi chưa)';
    lines.push('• Điện thoại khác cùng WiFi: nhập địa chỉ ' + ad + ' và mã kết nối <b>' + r.code + '</b>.');
    lines.push('• Khác WiFi / đang dùng 4G: cài Tailscale (miễn phí) trên cả máy này và điện thoại, đăng nhập cùng 1 tài khoản, rồi nhập địa chỉ 100.x.x.x của máy này vào app.');
    if (r.listening === '127.0.0.1') lines.push('<span class="warn">⚠ Vừa bật xong — hãy ĐÓNG game rồi mở lại (CHAY-GAME.bat) để có hiệu lực.</span>');
  } else {
    lines.push('• Điện thoại khác: bấm "Bật kết nối qua WiFi", rồi đóng và mở lại game. Chỉ bật khi ở mạng WiFi nhà mình.');
  }
  $('linkInfo').innerHTML = lines.join('<br>');
}

async function load() {
  try {
    show(await (await fetch('/app-link', { cache: 'no-store' })).json());
  } catch (e) {
    $('linkInfo').textContent = 'Không đọc được thông tin kết nối.';
  }
}

$('linkWifi').onclick = async () => {
  const on = !(cur && cur.wifi);
  if (on && !confirm('Mở cổng cho điện thoại trong cùng WiFi nối vào game (có mã 6 số bảo vệ). Chỉ bật khi dùng WiFi nhà mình. Tiếp tục?')) return;
  try {
    show(await (await fetch('/app-link/wifi?on=' + (on ? 1 : 0), { method: 'POST' })).json());
  } catch (e) {
    $('linkInfo').textContent = 'Lỗi, thử lại.';
  }
};
$('linkCode').onclick = async () => {
  if (!confirm('Đổi mã kết nối? Các app đang nối bằng mã cũ sẽ phải nhập mã mới.')) return;
  try {
    show(await (await fetch('/app-link/newcode', { method: 'POST' })).json());
  } catch (e) {
    /* bỏ qua */
  }
};
load();
