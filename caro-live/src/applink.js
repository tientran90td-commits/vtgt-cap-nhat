'use strict';
/*
 * KẾT NỐI APP "CARO TRỢ THỦ" (Android) vào game, qua WiFi hoặc cùng điện thoại (Termux).
 *  - Mặc định game chỉ nhận kết nối từ chính máy này (an toàn khi LIVE ở nơi công cộng).
 *  - Bật "cho phép app kết nối qua WiFi" thì game mở cổng cho cả mạng nhà, và máy khác phải nhập MÃ KẾT NỐI (6 số) mới vào được.
 *  - Trên cùng máy (localhost / Termux) app vào thẳng, không cần mã.
 * Module này chỉ lo kết nối/bảo mật; không đụng vào luật chơi.
 */
const fs = require('fs');
const os = require('os');
const path = require('path');
const crypto = require('crypto');

const DATA = path.join(__dirname, '..', 'data');
const WIFI_FILE = path.join(DATA, 'app-wifi.txt');
const CODE_FILE = path.join(DATA, 'app-code.txt');
const APP_ORIGIN = 'https://appassets.androidplatform.net'; // địa chỉ ảo của app Caro Trợ Thủ (chỉ app mới mang tên này)

function wifiOn() {
  try {
    return fs.readFileSync(WIFI_FILE, 'utf8').trim() === '1';
  } catch (e) {
    return false;
  }
}

function setWifi(on) {
  fs.mkdirSync(DATA, { recursive: true });
  fs.writeFileSync(WIFI_FILE, on ? '1' : '0');
}

/** Mã kết nối 6 số, tạo 1 lần rồi lưu lại. */
function code() {
  try {
    const t = fs.readFileSync(CODE_FILE, 'utf8').trim();
    if (/^\d{6}$/.test(t)) return t;
  } catch (e) {
    /* chưa có */
  }
  return newCode();
}

function newCode() {
  const c = String(crypto.randomInt(100000, 1000000));
  fs.mkdirSync(DATA, { recursive: true });
  fs.writeFileSync(CODE_FILE, c);
  return c;
}

function isLoopback(addr) {
  return /^(::1|127\.|::ffff:127\.)/.test(String(addr || ''));
}

// Truy cập qua đường hầm Internet (cloudflared) cũng đến từ 127.0.0.1, nhưng luôn kèm các dòng tiêu đề này.
// Phải coi là "từ xa": chỉ cho vào khi có mã tài khoản dài (không phải mã 6 số, vì mã 6 số dò được qua Internet).
let remoteToken = '';
function setRemoteToken(t) {
  remoteToken = String(t || '');
}
function viaProxy(req) {
  const h = (req && req.headers) || {};
  return !!(h['cf-connecting-ip'] || h['cf-ray'] || h['cf-visitor'] || h['x-forwarded-for'] || h['x-forwarded-host'] || h.forwarded);
}
/** Yêu cầu đến từ chính máy này (không qua đường hầm)? */
function isLocalRequest(req) {
  return isLoopback(req.socket && req.socket.remoteAddress) && !viaProxy(req);
}
function tokenOk(given) {
  return !!remoteToken && sameCode(given, remoteToken);
}

function sameCode(a, b) {
  const x = Buffer.from(String(a || ''));
  const y = Buffer.from(String(b || ''));
  return x.length === y.length && crypto.timingSafeEqual(x, y);
}

function localOrigin(origin) {
  if (!origin) return true;
  try {
    const h = new URL(origin).hostname;
    return h === 'localhost' || h === '127.0.0.1' || h === '[::1]';
  } catch (e) {
    return false;
  }
}

/**
 * Ai được nối WebSocket vào game?
 *  - Từ chính máy này: trang chạy trên localhost, hoặc app Caro Trợ Thủ.
 *  - Từ máy khác (chỉ khi đã bật WiFi): phải có đúng mã kết nối trong đường dẫn (?code=...).
 */
function allowWs(info) {
  const req = info.req;
  let given = '';
  try {
    given = new URL(req.url, 'http://x').searchParams.get('code') || '';
  } catch (e) {
    /* bỏ qua */
  }
  if (viaProxy(req)) return tokenOk(given); // qua Internet: chỉ cần đúng mã tài khoản
  const loop = isLoopback(req.socket && req.socket.remoteAddress);
  if (loop) return localOrigin(info.origin) || info.origin === APP_ORIGIN;
  if (!wifiOn()) return false;
  return sameCode(given, code());
}

/** Các địa chỉ trong mạng nhà để gõ vào app, ví dụ 192.168.1.5:3000 */
function lanAddresses(port) {
  const out = [];
  for (const list of Object.values(os.networkInterfaces())) {
    for (const i of list || []) {
      if (i.family === 'IPv4' && !i.internal) out.push(`${i.address}:${port}`);
    }
  }
  return out;
}

function info(port) {
  return { wifi: wifiOn(), code: code(), addresses: lanAddresses(port), local: `127.0.0.1:${port}` };
}

/**
 * Cho trang bảng điều khiển (mở trong app Caro Trợ Thủ qua WiFi/Tailscale) lấy danh sách người xem.
 * Từ chính máy này: như cũ. Từ máy khác: phải bật WiFi và gửi đúng mã (?code=...).
 */
function allowHttpRemote(req, url) {
  const given = url.searchParams.get('code') || '';
  if (viaProxy(req)) return tokenOk(given);
  if (isLoopback(req.socket && req.socket.remoteAddress)) return true;
  if (!wifiOn()) return false;
  return sameCode(given, code());
}

module.exports = { allowHttpRemote, wifiOn, setWifi, code, newCode, isLoopback, isLocalRequest, viaProxy, setRemoteToken, allowWs, lanAddresses, info, APP_ORIGIN };
