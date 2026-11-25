/*
 * KẾT NỐI REALTIME với server (WebSocket). Dùng chung cho trang LIVE và bảng điều khiển.
 */
export function connect(onState, onStatus, onNotice) {
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
    ws = new WebSocket(`${proto}://${location.host}/`);
    ws.onopen = () => {
      api.connected = true;
      if (onStatus) onStatus(true);
    };
    ws.onmessage = (e) => {
      try {
        const d = JSON.parse(e.data);
        if (d.notice) {
          if (onNotice) onNotice(d.notice);
          return;
        }
        onState(d);
      } catch (err) {
        /* bỏ qua gói lỗi */
      }
    };
    ws.onclose = () => {
      api.connected = false;
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
