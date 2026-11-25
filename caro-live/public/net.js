/*
 * KẾT NỐI REALTIME với server (WebSocket). Dùng chung cho trang LIVE và bảng điều khiển.
 */
/** Mã kết nối (nếu trang được mở từ app Caro Trợ Thủ qua WiFi) để gắn vào các yêu cầu HTTP. */
export function codeQuery() {
  let code = new URLSearchParams(location.search).get('code') || '';
  try {
    if (!code) code = sessionStorage.getItem('caroCode') || '';
  } catch (e) {
    /* bỏ qua */
  }
  return code ? '?code=' + encodeURIComponent(code) : '';
}

/** Báo cho app Caro Trợ Thủ (khung chứa bảng điều khiển) biết bảng đã nối được game chưa. */
function tellParent(ok) {
  try {
    if (window.parent && window.parent !== window) window.parent.postMessage({ caroPanel: 'ws', ok: !!ok }, '*');
  } catch (e) {
    /* bỏ qua */
  }
}

export function connect(onState, onStatus) {
  let ws = null;
  const api = {
    connected: false,
    send(msg) {
      if (ws && ws.readyState === 1) ws.send(JSON.stringify(msg));
    },
    command(cmd, extra = {}) {
      api.send({ type: 'cmd', cmd, ...extra });
    },
  };

  function open() {
    const proto = location.protocol === 'https:' ? 'wss' : 'ws';
    // app Caro Trợ Thủ mở bảng điều khiển qua WiFi kèm ?code=... -> nhớ mã để nối WebSocket
    let code = new URLSearchParams(location.search).get('code') || '';
    try {
      if (code) sessionStorage.setItem('caroCode', code);
      else code = sessionStorage.getItem('caroCode') || '';
    } catch (e) {
      /* bỏ qua */
    }
    ws = new WebSocket(`${proto}://${location.host}/${code ? '?code=' + encodeURIComponent(code) : ''}`);
    ws.onopen = () => {
      api.connected = true;
      tellParent(true);
      if (onStatus) onStatus(true);
    };
    ws.onmessage = (e) => {
      try {
        onState(JSON.parse(e.data));
      } catch (err) {
        /* bỏ qua gói lỗi */
      }
    };
    ws.onclose = () => {
      api.connected = false;
      tellParent(false);
      if (onStatus) onStatus(false);
      setTimeout(open, 1500);
    };
    ws.onerror = () => {
      try {
        ws.close();
      } catch (e) {
        /* bỏ qua */
      }
    };
  }
  open();
  return api;
}
