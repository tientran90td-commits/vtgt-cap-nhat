'use strict';
/*
 * CỔNG CHẮN trước đường hầm dự phòng (zrok).
 * Vì sao cần: game coi mọi yêu cầu đến từ chính máy này (127.0.0.1) và KHÔNG mang dấu "qua Internet" là yêu cầu tin cậy
 * (được phép bấm Cập nhật, đổi cài đặt...). Chương trình zrok chạy ngay trên máy này nên mọi người lạ vào qua zrok
 * cũng sẽ trông như đến từ 127.0.0.1. Cổng chắn này gắn dấu "x-forwarded-for" vào MỌI yêu cầu rồi mới chuyển cho game,
 * nên game luôn đòi mã vào cửa của tài khoản (xem applink.js) - giống hệt khi đi qua Cloudflare.
 */
const http = require('http');
const net = require('net');

const MARK = { 'x-forwarded-for': 'tunnel-guard' };

function createGuard(targetPort) {
  const srv = http.createServer((req, res) => {
    const up = http.request({ host: '127.0.0.1', port: targetPort, method: req.method, path: req.url, headers: { ...req.headers, ...MARK } }, (r) => {
      res.writeHead(r.statusCode, r.headers);
      r.pipe(res);
    });
    up.on('error', () => {
      if (!res.headersSent) res.writeHead(502);
      res.end();
    });
    req.pipe(up);
  });
  srv.on('upgrade', (req, sock, head) => {
    const up = net.connect(targetPort, '127.0.0.1', () => {
      const h = { ...req.headers, ...MARK };
      const lines = [`${req.method} ${req.url} HTTP/1.1`];
      for (const [k, v] of Object.entries(h)) lines.push(`${k}: ${Array.isArray(v) ? v.join(', ') : v}`);
      up.write(lines.join('\r\n') + '\r\n\r\n');
      if (head && head.length) up.write(head);
      sock.pipe(up);
      up.pipe(sock);
    });
    up.on('error', () => sock.destroy());
    sock.on('error', () => up.destroy());
    sock.on('close', () => up.destroy());
    up.on('close', () => sock.destroy());
  });
  srv.on('clientError', (e, sock) => sock.destroy());
  return srv;
}

/** Mở cổng chắn ở một cổng ngẫu nhiên chỉ trên 127.0.0.1. Trả về { server, port }. */
function listenGuard(targetPort) {
  return new Promise((resolve, reject) => {
    const server = createGuard(targetPort);
    server.once('error', reject);
    server.listen(0, '127.0.0.1', () => resolve({ server, port: server.address().port }));
  });
}

module.exports = { createGuard, listenGuard };
