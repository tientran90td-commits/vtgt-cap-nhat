'use strict';
/*
 * MÁY CHỦ: mở trang http://localhost:3002 (bảng điều khiển) và /live.html (màn hình để phát LIVE), đẩy dữ liệu realtime.
 * Chạy:  node src/server.js            (kết nối TikTok LIVE thật)
 *        node src/server.js --demo     (chế độ thử, khán giả ảo)
 *        node src/server.js --tikfinity (nhận sự kiện từ TikFinity Desktop)
 */
const http = require('http');
const fs = require('fs');
const path = require('path');
const { WebSocketServer } = require('ws');
const config = require('../config');
const { Hub } = require('./hub');
const { startDemo } = require('./demo');
const { parseRequest } = require('./parse');
const updater = require('./updater');

const PUBLIC = path.join(__dirname, '..', 'public');
const MIME = {
  '.html': 'text/html; charset=utf-8',
  '.js': 'text/javascript; charset=utf-8',
  '.css': 'text/css; charset=utf-8',
  '.json': 'application/json; charset=utf-8',
  '.png': 'image/png',
  '.jpg': 'image/jpeg',
  '.svg': 'image/svg+xml',
  '.ico': 'image/x-icon',
  '.mp3': 'audio/mpeg',
};

const log = (...a) => console.log(new Date().toLocaleTimeString('vi-VN'), ...a);
const wantDemo = process.argv.includes('--demo');
const useTikFinity = process.argv.includes('--tikfinity');
const manual = process.argv.includes('--manual'); // chỉ để kiểm tra: không kết nối gì, tự gõ thử qua /test
config.demo = !manual && (wantDemo || (!useTikFinity && !config.tiktokUsername));
const hub = new Hub(config);

const AVATAR_HOST = /(^|\.)(tiktokcdn|tiktokcdn-us|tiktokv|byteoversea|ibytedtos|muscdn|tiktok|bytecdn)\.(com|us|net|cn)$/i;
const avatarCache = new Map();

async function serveAvatar(u, res) {
  try {
    const target = new URL(String(u || ''));
    if (target.protocol !== 'https:' || !AVATAR_HOST.test(target.hostname)) throw new Error('host');
    let hit = avatarCache.get(target.href);
    if (!hit) {
      const r = await fetch(target.href, { headers: { 'User-Agent': 'Mozilla/5.0' }, signal: AbortSignal.timeout(8000) });
      const type = r.headers.get('content-type') || '';
      if (!r.ok || !/^image\//i.test(type)) throw new Error('bad');
      const buf = Buffer.from(await r.arrayBuffer());
      if (buf.length > 3 * 1024 * 1024) throw new Error('big');
      hit = { type, buf };
      if (avatarCache.size > 200) avatarCache.delete(avatarCache.keys().next().value);
      avatarCache.set(target.href, hit);
    }
    res.writeHead(200, { 'Content-Type': hit.type, 'Cache-Control': 'max-age=3600' });
    res.end(hit.buf);
  } catch (e) {
    res.writeHead(404);
    res.end('no avatar');
  }
}

function serveDemoAvatar(name, res) {
  const n = String(name || '?').slice(0, 24);
  let h = 0;
  for (const ch of n) h = (h * 31 + ch.codePointAt(0)) % 360;
  const letter = (n.trim()[0] || '?').toUpperCase().replace(/[<>&"']/g, '?');
  const svg = `<svg xmlns="http://www.w3.org/2000/svg" width="128" height="128"><defs><linearGradient id="g" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="hsl(${h},70%,60%)"/><stop offset="1" stop-color="hsl(${(h + 50) % 360},65%,40%)"/></linearGradient></defs><rect width="128" height="128" fill="url(#g)"/><text x="64" y="86" font-size="70" font-family="Arial,sans-serif" font-weight="700" text-anchor="middle" fill="#fff">${letter}</text></svg>`;
  res.writeHead(200, { 'Content-Type': 'image/svg+xml', 'Cache-Control': 'max-age=3600' });
  res.end(svg);
}

function serveMusicList(res) {
  let files = [];
  try {
    files = fs.readdirSync(path.join(PUBLIC, 'music')).filter((f) => /\.(mp3|ogg|wav|m4a|aac)$/i.test(f));
  } catch (e) {
    /* chưa có thư mục nhạc */
  }
  res.writeHead(200, { 'Content-Type': 'application/json; charset=utf-8', 'Cache-Control': 'no-store' });
  res.end(JSON.stringify(files));
}

const server = http.createServer((req, res) => {
  const url = new URL(req.url, 'http://localhost');
  if (url.pathname === '/avatar') return serveAvatar(url.searchParams.get('u'), res);
  if (url.pathname === '/demo-avatar') return serveDemoAvatar(url.searchParams.get('n'), res);
  if (url.pathname === '/music-list') return serveMusicList(res);
  if (url.pathname.startsWith('/update/') && updater.handle(req, res, url, { log })) return;

  // gõ thử 1 bình luận bằng trình duyệt:  /test?u=An&c=!bai%203   (chỉ từ chính máy này)
  if (url.pathname === '/test' && config.testApi) {
    const ok = ['127.0.0.1', '::1', '::ffff:127.0.0.1'].includes(req.socket.remoteAddress);
    if (!ok) {
      res.writeHead(403);
      return res.end('Forbidden');
    }
    const name = String(url.searchParams.get('u') || 'Khách').slice(0, 30);
    const text = String(url.searchParams.get('c') || '');
    const r = hub.onComment({ id: 'test-' + name.toLowerCase(), uniqueId: name, name, avatar: `/demo-avatar?n=${encodeURIComponent(name)}` }, text);
    res.writeHead(200, { 'Content-Type': 'application/json; charset=utf-8' });
    return res.end(JSON.stringify({ parsed: parseRequest(text), result: r }));
  }

  let rel;
  try {
    rel = decodeURIComponent(url.pathname);
  } catch (e) {
    res.writeHead(400);
    return res.end('Bad request');
  }
  if (rel === '/') rel = '/index.html';
  const file = path.normalize(path.join(PUBLIC, rel));
  if (!file.startsWith(PUBLIC)) {
    res.writeHead(403);
    return res.end('Forbidden');
  }
  fs.readFile(file, (err, buf) => {
    if (err) {
      res.writeHead(404);
      return res.end('Not found');
    }
    const ext = path.extname(file).toLowerCase();
    res.writeHead(200, {
      'Content-Type': MIME[ext] || 'application/octet-stream',
      'Cache-Control': ext === '.jpg' ? 'max-age=86400' : 'no-store',
    });
    res.end(buf);
  });
});

// WebSocket: chỉ nhận kết nối từ trang chạy trên chính máy này
const wss = new WebSocketServer({
  server,
  verifyClient: (info) => {
    const a = (info.req.socket && info.req.socket.remoteAddress) || '';
    const loop = ['127.0.0.1', '::1', '::ffff:127.0.0.1'].includes(a);
    if (!loop) return false;
    if (!info.origin) return true;
    try {
      const h = new URL(info.origin).hostname;
      return h === 'localhost' || h === '127.0.0.1' || h === '[::1]';
    } catch (e) {
      return false;
    }
  },
});
let lastJson = '';
let lastSent = 0;

function broadcast(force = false) {
  const now = Date.now();
  const { serverNow, ...rest } = hub.getState(now);
  const json = JSON.stringify(rest);
  if (json === lastJson && !force && now - lastSent < 1500) return;
  lastJson = json;
  lastSent = now;
  const payload = JSON.stringify({ ...rest, serverNow });
  for (const c of wss.clients) if (c.readyState === 1) c.send(payload);
}

wss.on('connection', (ws) => {
  ws.send(JSON.stringify(hub.getState()));
  ws.on('message', (data) => {
    try {
      const msg = JSON.parse(String(data));
      if (msg && msg.type === 'cmd') {
        const r = hub.command(msg);
        if (r && r.ok === false && r.msg) ws.send(JSON.stringify({ notice: r.msg }));
        broadcast(true);
      }
    } catch (e) {
      /* bỏ qua tin nhắn lạ */
    }
  });
});

setInterval(() => {
  try {
    hub.tick(Date.now());
    broadcast();
  } catch (e) {
    log('Lỗi:', e.stack || e.message);
  }
}, 200);

process.on('unhandledRejection', (e) => log('Cảnh báo:', (e && e.message) || e));
process.on('uncaughtException', (e) => log('Lỗi:', (e && e.stack) || e));

server.on('error', (e) => {
  if (e.code === 'EADDRINUSE') console.log(`\nCổng ${config.port} đang được dùng. Có thể game đang chạy ở cửa sổ khác - hãy đóng nó rồi chạy lại.\n`);
  else console.log('Lỗi máy chủ:', e.message);
  process.exit(1);
});

server.listen(config.port, config.host, () => {
  console.log('');
  console.log('==============================================');
  console.log('  TAROT LIVE v1.0 đã sẵn sàng!');
  console.log(`  Mở trang:  http://localhost:${config.port}`);
  console.log('  (Giữ cửa sổ đen này mở trong lúc LIVE)');
  console.log('==============================================');
  console.log('');
  if (manual) {
    log('CHẾ ĐỘ THỦ CÔNG (--manual): không có khán giả, dùng /test để gõ thử.');
  } else if (config.demo) {
    if (!wantDemo) log('Chưa có ID TikTok (file ten-tiktok.txt) nên chạy CHẾ ĐỘ THỬ.');
    startDemo(hub, config, log);
  } else if (useTikFinity) {
    log('Chế độ TIKFINITY: nhận sự kiện từ TikFinity Desktop (ws://127.0.0.1:21213).');
    require('./tikfinity').startTikFinity(config, hub, log);
  } else {
    log(`Kết nối LIVE của @${config.tiktokUsername} ...`);
    try {
      require('./tiktok').startTikTok(config, hub, log);
    } catch (e) {
      hub.setConnection('error', 'Chưa cài thư viện TikTok. Hãy chạy CHAY-GAME.bat');
      log('Không nạp được thư viện TikTok:', e.message);
    }
  }
});
