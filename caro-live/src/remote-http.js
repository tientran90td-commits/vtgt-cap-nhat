'use strict';
/*
 * Cổng điều khiển "xem từ xa" cho bảng điều khiển / app PC (CHỈ nhận từ chính máy này, không nhận qua đường hầm).
 *   GET  /remote           trạng thái
 *   POST /remote/config    { account, password, enabled }
 *   POST /remote/zrok      { token }  (mã zrok cho đường dự phòng; rỗng = xóa)
 */
const applink = require('./applink');

let remote = null;
const attach = (r) => {
  remote = r;
};

function body(req) {
  return new Promise((resolve) => {
    let s = '';
    req.on('data', (c) => {
      s += c;
      if (s.length > 4000) req.destroy();
    });
    req.on('end', () => {
      try {
        resolve(JSON.parse(s || '{}'));
      } catch (e) {
        resolve({});
      }
    });
    req.on('error', () => resolve({}));
  });
}

/** Trả true nếu đã xử lý. */
function handle(req, res, url) {
  const send = (code, obj) => {
    res.writeHead(code, { 'Content-Type': 'application/json; charset=utf-8', 'Cache-Control': 'no-store' });
    res.end(JSON.stringify(obj));
  };
  if (!applink.isLocalRequest(req)) return send(403, { ok: false }), true;
  if (!remote) return send(503, { ok: false, error: 'Chưa sẵn sàng' }), true;
  if (url.pathname === '/remote' && req.method === 'GET') return send(200, { ok: true, ...remote.status() }), true;
  if (url.pathname === '/remote/config' && req.method === 'POST') {
    body(req).then(async (b) => {
      try {
        if (b.zrokToken !== undefined && !b.account && b.enabled === undefined) return send(200, { ok: true, ...remote.setZrokToken(String(b.zrokToken || '')) }); // chỉ lưu/xóa mã zrok
        const st = await remote.configure(String(b.account || ''), String(b.password || ''), b.enabled !== false);
        send(200, { ok: true, ...st });
      } catch (e) {
        send(200, { ok: false, error: e.message });
      }
    });
    return true;
  }
  if (url.pathname === '/remote/zrok' && req.method === 'POST') {
    body(req).then((b) => {
      try {
        send(200, { ok: true, ...remote.setZrokToken(String(b.token || '')) });
      } catch (e) {
        send(200, { ok: false, error: e.message });
      }
    });
    return true;
  }
  return send(404, { ok: false }), true;
}

module.exports = { handle, attach };
