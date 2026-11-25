/* CHUYỂN TAB: Nối game / Điều khiển (bảng điều khiển game ngay trong app) / Tự nhập. */
(function () {
  const $ = (id) => document.getElementById(id);
  let loadedUrl = '';
  function show(id) {
    for (const v of document.querySelectorAll('.view')) v.classList.toggle('on', v.id === id);
    for (const b of document.querySelectorAll('#tabs button')) b.classList.toggle('on', b.dataset.tab === id);
    if (id === 'viewPanel') {
      const url = window.LinkApp ? LinkApp.panelUrl() : '';
      $('viewPanel').classList.toggle('has', !!url);
      if (url && url !== loadedUrl) { loadedUrl = url; $('pnFrame').src = url; }
    }
    // bàn cờ vẽ theo kích thước khung; khung ẩn thì đo = 0 nên phải vẽ lại khi hiện
    setTimeout(() => { window.dispatchEvent(new Event('resize')); if (window.LinkApp) LinkApp.relayout(); }, 30);
  }
  for (const b of document.querySelectorAll('#tabs button')) b.addEventListener('click', () => show(b.dataset.tab));
})();
