'use strict';
/*
 * MÁY CHỦ: mở trang http://localhost:3000 (bàn cờ + cảnh 3D) và đẩy dữ liệu realtime cho trang đó.
 * Chạy:  node src/server.js          (kết nối TikTok LIVE thật)
 *        node src/server.js --demo   (chế độ thử, khán giả ảo)
 */
const http = require('http');
const fs = require('fs');
const path = require('path');
const { WebSocketServer } = require('ws');
const applink = require('./applink');
const config = require('../config');
const { Hub } = require('./hub');
const { startDemo } = require('./demo');
const updater = require('./updater');

const PUBLIC = path.join(__dirname, '..', 'public');
const MIME = {
  '.html': 'text/html; charset=utf-8',
  '.js': 'text/javascript; charset=utf-8',
  '.mjs': 'text/javascript; charset=utf-8',
  '.css': 'text/css; charset=utf-8',
  '.json': 'application/json; charset=utf-8',
  '.png': 'image/png',
  '.jpg': 'image/jpeg',
  '.svg': 'image/svg+xml',
  '.ico': 'image/x-icon',
  '.mp4': 'video/mp4',
  '.webm': 'video/webm',
};

const log = (...a) => console.log(new Date().toLocaleTimeString('vi-VN'), ...a);

const wantDemo = process.argv.includes('--demo');
const useTikFinity = process.argv.includes('--tikfinity');
const demo = wantDemo || (!useTikFinity && !config.tiktokUsername);
config.demo = demo;

const hub = new Hub(config);


// ---------- ảnh đại diện + nhạc nền ----------
const AVATAR_HOST = /(^|\.)(tiktokcdn|tiktokcdn-us|tiktokv|byteoversea|ibytedtos|muscdn|tiktok|bytecdn)\.(com|us|net|cn)$/i;
const avatarCache = new Map(); // url -> { type, buf }

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
  const svg = `<svg xmlns="http://www.w3.org/2000/svg" width="128" height="128"><defs><linearGradient id="g" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="hsl(${h},80%,62%)"/><stop offset="1" stop-color="hsl(${(h + 50) % 360},75%,45%)"/></linearGradient></defs><rect width="128" height="128" fill="url(#g)"/><text x="64" y="86" font-size="70" font-family="Arial,sans-serif" font-weight="700" text-anchor="middle" fill="#fff">${letter}</text></svg>`;
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

// ---------- thẻ "Kết nối app Caro Trợ Thủ" (chỉ cho trang trên chính máy này) ----------
function serveAppLink(req, res, url) {
  const send = (code, obj) => {
    res.writeHead(code, { 'Content-Type': 'application/json; charset=utf-8', 'Cache-Control': 'no-store' });
    res.end(JSON.stringify(obj));
  };
  if (!applink.isLoopback(req.socket.remoteAddress)) return send(403, { ok: false });
  if (url.pathname === '/app-link' && req.method === 'GET') return send(200, { ok: true, ...applink.info(config.port), listening: config.host });
  if (url.pathname === '/app-link/wifi' && req.method === 'POST') {
    applink.setWifi(url.searchParams.get('on') === '1');
    return send(200, { ok: true, ...applink.info(config.port), listening: config.host, restart: true });
  }
  if (url.pathname === '/app-link/newcode' && req.method === 'POST') {
    applink.newCode();
    return send(200, { ok: true, ...applink.info(config.port), listening: config.host });
  }
  return send(404, { ok: false });
}

// ---------- HTTP ----------
const server = http.createServer((req, res) => {
  const url = new URL(req.url, 'http://localhost');

  // --- ảnh đại diện TikTok (đi qua máy chủ để trình duyệt vẽ được lên hình 3D) ---
  if (url.pathname === '/avatar') return serveAvatar(url.searchParams.get('u'), res);
  if (url.pathname === '/demo-avatar') return serveDemoAvatar(url.searchParams.get('n'), res);
  if (url.pathname.startsWith('/app-link')) return serveAppLink(req, res, url);
  if (url.pathname === '/music-list') return serveMusicList(res);
  if (url.pathname.startsWith('/update/') && updater.handle(req, res, url, { log })) return;
  if (url.pathname === '/viewers') {
    // chỉ trả cho trang chạy trên chính máy này
    // (hoặc từ app Caro Trợ Thủ qua WiFi/Tailscale, có đúng mã kết nối)
    const host = String(req.headers.host || '').replace(/:\d+$/, '');
    const localHost = ['localhost', '127.0.0.1', '[::1]'].includes(host);
    if (!localHost && !applink.allowHttpRemote(req, url)) {
      res.writeHead(403);
      return res.end('Forbidden');
    }
    res.writeHead(200, { 'Content-Type': 'application/json; charset=utf-8', 'Cache-Control': 'no-store' });
    return res.end(JSON.stringify(hub.viewers()));
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
  if (/^\.(mp4|webm)$/i.test(path.extname(file))) {
    // video: phát theo từng đoạn (Range) để trình duyệt / OBS tua và phát mượt
    fs.stat(file, (err, st) => {
      if (err || !st.isFile()) {
        res.writeHead(404);
        return res.end('Not found');
      }
      const m = /^bytes=(\d*)-(\d*)$/.exec(req.headers.range || '');
      let start = 0;
      let end = st.size - 1;
      if (m && (m[1] || m[2])) {
        if (m[1]) start = Number(m[1]);
        if (m[2]) end = m[1] ? Math.min(Number(m[2]), st.size - 1) : st.size - 1;
        if (!m[1]) start = Math.max(0, st.size - Number(m[2]));
      }
      if (start > end || start >= st.size) {
        res.writeHead(416, { 'Content-Range': 'bytes */' + st.size });
        return res.end();
      }
      const partial = !!m;
      res.writeHead(partial ? 206 : 200, {
        'Content-Type': 'video/mp4',
        'Accept-Ranges': 'bytes',
        'Content-Length': end - start + 1,
        ...(partial ? { 'Content-Range': `bytes ${start}-${end}/${st.size}` } : {}),
      });
      fs.createReadStream(file, { start, end }).pipe(res);
    });
    return;
  }
  fs.readFile(file, (err, buf) => {
    if (err) {
      res.writeHead(404);
      return res.end('Not found');
    }
    res.writeHead(200, {
      'Content-Type': MIME[path.extname(file).toLowerCase()] || 'application/octet-stream',
      'Cache-Control': 'no-store',
    });
    res.end(buf);
  });
});

// ---------- WebSocket: đẩy trạng thái cho trang web ----------
// Chỉ nhận kết nối từ trang trên chính máy này, hoặc app Caro Trợ Thủ (máy khác phải có mã kết nối - xem src/applink.js)
const wss = new WebSocketServer({ server, verifyClient: (info) => applink.allowWs(info) });
let lastJson = '';
let lastSent = 0;

function broadcast(force = false) {
  const now = Date.now();
  const state = hub.getState(now);
  const { serverNow, ...rest } = state;
  const json = JSON.stringify(rest);
  const changed = json !== lastJson;
  if (!changed && !force && now - lastSent < 1500) return; // nhịp tim để đồng bộ đồng hồ
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
        hub.command(msg);
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
  if (e.code === 'EADDRINUSE') {
    console.log(`\nCổng ${config.port} đang được dùng. Có thể game đang chạy ở cửa sổ khác - hãy đóng nó rồi chạy lại.\n`);
  } else {
    console.log('Lỗi máy chủ:', e.message);
  }
  process.exit(1);
});

server.listen(config.port, config.host, () => {
  console.log('');
  console.log('==============================================');
  console.log('  CARO LIVE v1.0 đã sẵn sàng!');
  console.log(`  Mở trang:  http://localhost:${config.port}`);
  console.log('  (Giữ cửa sổ đen này mở trong lúc LIVE)');
  console.log('==============================================');
  console.log('');
  if (demo) {
    if (!wantDemo) log('Chưa có ID TikTok (file ten-tiktok.txt) nên chạy CHẾ ĐỘ THỬ.');
    hub.demo = startDemo(hub, config, log, { status: true });
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
