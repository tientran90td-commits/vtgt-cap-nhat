/* CHUYỂN TAB: Nối game / Điều khiển (bảng điều khiển game ngay trong app) / Tự nhập. */
(function () {
  const $ = (id) => document.getElementById(id);
  let loadedUrl = '';
  const NONE_WAIT = 'Đang nối vào máy tính… Bảng điều khiển sẽ hiện ngay khi nối được. Nếu lâu quá, vào tab "Nối game" xem lý do.';
  const NONE_NO = 'Chưa nối game. Vào tab "Nối game" nhập tài khoản + mật khẩu (hoặc địa chỉ) trước, bảng điều khiển sẽ hiện ở đây.';

  // Chỉ mở bảng điều khiển khi ĐANG nối được game; mất kết nối thì gỡ khung đi (tránh hiện trang lỗi của Cloudflare do địa chỉ cũ đã chết)
  function syncPanel() {
    const url = window.LinkApp ? LinkApp.panelUrl() : '';
    $('viewPanel').classList.toggle('has', !!url);
    if (url) {
      if (url !== loadedUrl) { loadedUrl = url; $('pnWarn').classList.add('hidden'); $('pnFrame').src = url; }
    } else {
      if (loadedUrl) { loadedUrl = ''; $('pnFrame').src = 'about:blank'; }
      $('pnNone').textContent = window.LinkApp && LinkApp.hasTarget() ? NONE_WAIT : NONE_NO;
    }
  }

  function show(id) {
    for (const v of document.querySelectorAll('.view')) v.classList.toggle('on', v.id === id);
    for (const b of document.querySelectorAll('#tabs button')) b.classList.toggle('on', b.dataset.tab === id);
    if (id === 'viewPanel') syncPanel();
    // bàn cờ vẽ theo kích thước khung; khung ẩn thì đo = 0 nên phải vẽ lại khi hiện
    setTimeout(() => { window.dispatchEvent(new Event('resize')); if (window.LinkApp) LinkApp.relayout(); }, 30);
  }

  // bảng điều khiển (trong khung) báo đã nối được game chưa; chưa nối thì hiện cảnh báo + nút tải lại
  window.addEventListener('message', (e) => {
    const d = e.data;
    if (d && d.caroPanel === 'ws') $('pnWarn').classList.toggle('hidden', !!d.ok);
  });
  $('pnReload').addEventListener('click', () => {
    const u = window.LinkApp ? LinkApp.panelUrl() : '';
    if (u) { $('pnWarn').classList.add('hidden'); $('pnFrame').src = u + (u.includes('?') ? '&' : '?') + 't=' + Date.now(); }
  });
  window.addEventListener('caro-link-state', syncPanel);
  for (const b of document.querySelectorAll('#tabs button')) b.addEventListener('click', () => show(b.dataset.tab));
})();
