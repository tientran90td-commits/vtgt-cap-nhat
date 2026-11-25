'use strict';
/*
 * NHẬN SỰ KIỆN TỪ TIKFINITY (ứng dụng TikFinity Desktop chạy trên cùng máy).
 * TikFinity tự kết nối TikTok LIVE rồi phát sự kiện qua WebSocket  ws://localhost:21213/
 * dạng  { "event": "chat" | "gift" | "like" | "follow" | "share" ..., "data": {...} }.
 * Game chỉ cần nghe cổng đó - không cần ID TikTok hay API key.
 */
const WebSocket = require('ws');
const { makeHandlers } = require('./tiktok');

/** Dữ liệu của TikFinity là phẳng (uniqueId, nickname... nằm ngay trong data) -> bọc thành data.user. */
function wrap(d) {
  if (!d || typeof d !== 'object') return {};
  return d.user ? d : { ...d, user: d };
}

/** Chuyển 1 gói TikFinity thành lời gọi handler. Trả về tên sự kiện đã xử lý (hoặc null). */
function dispatch(handlers, msg) {
  if (!msg || typeof msg !== 'object') return null;
  const ev = String(msg.event || '').toLowerCase();
  const data = wrap(msg.data);
  switch (ev) {
    case 'chat':
    case 'comment':
      handlers.chat(data);
      return 'chat';
    case 'like':
      handlers.like(data);
      return 'like';
    case 'gift':
      handlers.gift(data);
      return 'gift';
    case 'follow':
      handlers.follow(data);
      return 'follow';
    case 'share':
      handlers.share(data);
      return 'share';
    case 'social': {
      // kiểu cũ: follow / share nằm trong displayType
      const t = String(data.displayType || data.label || '').toLowerCase();
      if (t.includes('follow')) {
        handlers.follow(data);
        return 'follow';
      }
      if (t.includes('share')) {
        handlers.share(data);
        return 'share';
      }
      return null;
    }
    default:
      return null;
  }
}

function startTikFinity(cfg, hub, log = console.log) {
  const url = cfg.tikfinityUrl || 'ws://127.0.0.1:21213/';
  const handlers = makeHandlers(hub);
  let ws = null;
  let timer = null;
  let stopped = false;
  let warned = false;
  const seen = new Map();
  let total = 0;
  let giftLogged = 0;
  let lastStatus = 0;

  function retry(sec = 3) {
    if (stopped || timer) return;
    timer = setTimeout(() => {
      timer = null;
      open();
    }, sec * 1000);
  }

  function open() {
    if (stopped) return;
    hub.setConnection('connecting', 'Đang nối TikFinity…');
    try {
      ws = new WebSocket(url);
    } catch (e) {
      hub.setConnection('error', 'Địa chỉ TikFinity không hợp lệ.');
      return;
    }
    ws.on('open', () => {
      warned = false;
      hub.setConnection('connected', 'Đã nối TikFinity • chưa nhận sự kiện nào (hãy thử bình luận / thả tim)');
      log('Đã nối TikFinity:', url);
    });
    ws.on('message', (buf) => {
      let msg;
      try {
        msg = JSON.parse(String(buf));
      } catch (e) {
        return;
      }
      let handled = null;
      try {
        handled = dispatch(handlers, msg);
      } catch (e) {
        log('Lỗi xử lý sự kiện TikFinity:', e.message);
      }
      // ghi lại để biết TikFinity có gửi sự kiện thật không (xem cửa sổ đen / ô trạng thái trên bảng điều khiển)
      const name = String((msg && msg.event) || '?');
      total += 1;
      if (!seen.has(name)) log(`TikFinity gửi sự kiện "${name}"${handled ? '' : ' (game không dùng loại này)'}`);
      seen.set(name, (seen.get(name) || 0) + 1);
      if (handled === 'gift' && giftLogged < 3) {
        giftLogged += 1;
        log('Mẫu dữ liệu quà từ TikFinity:', JSON.stringify(msg.data).slice(0, 400));
      }
      const t = Date.now();
      if (t - lastStatus > 1500) {
        lastStatus = t;
        hub.setConnection('connected', `Đã nối TikFinity • đã nhận ${total} sự kiện LIVE`);
      }
    });
    ws.on('close', () => {
      if (stopped) return;
      hub.setConnection('error', 'Chưa nối được TikFinity. Hãy mở TikFinity Desktop và kết nối LIVE.');
      if (!warned) {
        warned = true;
        log('Chưa nối được TikFinity (cổng 21213). Hãy mở TikFinity Desktop, kết nối LIVE rồi game sẽ tự nối.');
      }
      retry(3);
    });
    ws.on('error', () => {
      /* sự kiện 'close' sẽ xử lý và tự thử lại */
    });
  }

  open();
  return {
    stop() {
      stopped = true;
      if (timer) clearTimeout(timer);
      try {
        if (ws) ws.close();
      } catch (e) {
        /* bỏ qua */
      }
    },
  };
}

module.exports = { startTikFinity, dispatch, wrap };
