'use strict';
/*
 * CẬP NHẬT TRỰC TIẾP: tool tự tải bản mới nhất từ GitHub và thay file, không cần tải/giải nén lại.
 * - Giữ nguyên: data/ (cài đặt, thống kê), node_modules/, ten-tiktok.txt, euler-api-key.txt.
 * - File bị ghi đè (nếu khác bản cũ) được sao lưu vào data/backup-bản-<số>/ (config.js nếu bạn từng sửa tay sẽ có ở đó).
 * - Cập nhật xong tool tự thoát với mã 3; file CHAY-GAME.bat / chay-termux.sh thấy mã 3 sẽ tự mở lại.
 * Đường dẫn:  GET /update/check   |   POST /update/apply   (chỉ chấp nhận từ chính máy này)
 */
const https = require('https');
const http = require('http');
const fs = require('fs');
const path = require('path');
const zlib = require('zlib');
const cp = require('child_process');

const ROOT = path.join(__dirname, '..');
const PKG = require('../package.json');
const REPO = process.env.TOOL_UPDATE_REPO || 'tientran90td-commits/vtgt-cap-nhat';
const BRANCH = 'main';
const FOLDER = PKG.updateFolder;
const BASE = process.env.TOOL_UPDATE_BASE || ''; // chỉ dùng khi kiểm tra tự động
const KEEP = ['node_modules/', 'data/', 'ten-tiktok.txt', 'euler-api-key.txt', '.git/'];
const TEXT_EXT = new Set(['.js', '.json', '.html', '.css', '.txt', '.bat', '.sh', '.md']);

const versionUrl = () => (BASE ? `${BASE}/version.json` : `https://raw.githubusercontent.com/${REPO}/${BRANCH}/${FOLDER}/version.json`);
const zipUrl = () => (BASE ? `${BASE}/repo.zip` : `https://codeload.github.com/${REPO}/zip/refs/heads/${BRANCH}`);

function get(url, hops = 6) {
  return new Promise((resolve, reject) => {
    const mod = url.startsWith('https:') ? https : http;
    const req = mod.get(url, { headers: { 'User-Agent': 'tool-updater', 'Cache-Control': 'no-cache' } }, (res) => {
      if (res.statusCode >= 300 && res.statusCode < 400 && res.headers.location) {
        res.resume();
        if (hops <= 0) return reject(new Error('chuyển hướng quá nhiều lần'));
        return resolve(get(new URL(res.headers.location, url).toString(), hops - 1));
      }
      if (res.statusCode !== 200) {
        res.resume();
        return reject(new Error('máy chủ trả mã ' + res.statusCode));
      }
      const chunks = [];
      res.on('data', (c) => chunks.push(c));
      res.on('end', () => resolve(Buffer.concat(chunks)));
      res.on('error', reject);
    });
    req.setTimeout(45000, () => req.destroy(new Error('quá thời gian chờ mạng')));
    req.on('error', reject);
  });
}

function localInfo() {
  try {
    const j = JSON.parse(fs.readFileSync(path.join(ROOT, 'version.json'), 'utf8'));
    return { version: Number(j.version) || 0, notes: j.notes || '' };
  } catch (e) {
    return { version: 0, notes: '' };
  }
}

/** Đọc file zip (chỉ cần kiểu nén deflate/stored của GitHub). Trả [{name, data}] */
function unzip(buf) {
  let eocd = -1;
  for (let i = buf.length - 22; i >= Math.max(0, buf.length - 70000); i--) {
    if (buf.readUInt32LE(i) === 0x06054b50) { eocd = i; break; }
  }
  if (eocd < 0) throw new Error('file tải về không phải zip');
  const total = buf.readUInt16LE(eocd + 10);
  let p = buf.readUInt32LE(eocd + 16);
  const out = [];
  for (let n = 0; n < total; n++) {
    if (buf.readUInt32LE(p) !== 0x02014b50) throw new Error('zip hỏng (danh mục)');
    const method = buf.readUInt16LE(p + 10);
    const csize = buf.readUInt32LE(p + 20);
    const nameLen = buf.readUInt16LE(p + 28);
    const extraLen = buf.readUInt16LE(p + 30);
    const commLen = buf.readUInt16LE(p + 32);
    const lho = buf.readUInt32LE(p + 42);
    const name = buf.toString('utf8', p + 46, p + 46 + nameLen);
    p += 46 + nameLen + extraLen + commLen;
    if (name.endsWith('/')) continue;
    if (buf.readUInt32LE(lho) !== 0x04034b50) throw new Error('zip hỏng (đầu file)');
    const start = lho + 30 + buf.readUInt16LE(lho + 26) + buf.readUInt16LE(lho + 28);
    const raw = buf.subarray(start, start + csize);
    let data;
    if (method === 0) data = Buffer.from(raw);
    else if (method === 8) data = zlib.inflateRawSync(raw);
    else throw new Error('zip dùng kiểu nén chưa hỗ trợ (' + method + ')');
    out.push({ name, data });
  }
  return out;
}

async function check() {
  const cur = localInfo();
  const txt = (await get(versionUrl())).toString('utf8');
  const j = JSON.parse(txt);
  const latest = Number(j.version) || 0;
  return { current: cur.version, latest, hasNew: latest > cur.version, notes: j.notes || '' };
}

async function apply(log) {
  const cur = localInfo();
  const entries = unzip(await get(zipUrl()));
  if (!entries.length) throw new Error('gói tải về rỗng');
  const root = entries[0].name.split('/')[0];
  const prefix = `${root}/${FOLDER}/`;
  const picked = entries.filter((e) => e.name.startsWith(prefix)).map((e) => ({ rel: e.name.slice(prefix.length), data: e.data }));
  if (!picked.some((e) => e.rel === 'src/server.js') || !picked.some((e) => e.rel === 'version.json')) {
    throw new Error(`không thấy thư mục "${FOLDER}" đầy đủ trong gói tải về`);
  }
  const newInfo = JSON.parse(picked.find((e) => e.rel === 'version.json').data.toString('utf8'));
  const oldDeps = JSON.stringify(PKG.dependencies || {});
  const backupDir = path.join(ROOT, 'data', `backup-ban-${cur.version}`);
  const changed = [];
  for (const e of picked) {
    if (!e.rel || e.rel.includes('..') || KEEP.some((k) => (k.endsWith('/') ? e.rel.startsWith(k) : e.rel === k))) continue;
    const dest = path.join(ROOT, e.rel);
    if (!path.resolve(dest).startsWith(path.resolve(ROOT) + path.sep)) continue;
    let old = null;
    try { old = fs.readFileSync(dest); } catch (err) { /* file mới */ }
    if (old && old.equals(e.data)) continue;
    if (old && old.length < 300000 && TEXT_EXT.has(path.extname(e.rel).toLowerCase())) {
      const b = path.join(backupDir, e.rel);
      fs.mkdirSync(path.dirname(b), { recursive: true });
      fs.writeFileSync(b, old);
    }
    fs.mkdirSync(path.dirname(dest), { recursive: true });
    fs.writeFileSync(dest, e.data);
    changed.push(e.rel);
  }
  let npmNote = '';
  try {
    const newDeps = JSON.stringify(JSON.parse(fs.readFileSync(path.join(ROOT, 'package.json'), 'utf8')).dependencies || {});
    if (newDeps !== oldDeps) {
      log && log('Thư viện thay đổi, đang chạy npm install…');
      const r = cp.spawnSync(process.platform === 'win32' ? 'npm.cmd' : 'npm', ['install', '--no-audit', '--no-fund'], { cwd: ROOT, shell: process.platform === 'win32', timeout: 300000 });
      if (r.status !== 0) npmNote = 'Không cài được thư viện mới tự động; hãy chạy lại CAI-MOI-TRUONG.bat.';
    }
  } catch (e) { /* bỏ qua */ }
  return { changed: changed.length, files: changed.slice(0, 30), version: Number(newInfo.version) || 0, backup: changed.length ? backupDir : '', note: npmNote };
}

let busy = false;

/** Gắn vào máy chủ HTTP. Trả true nếu đã xử lý yêu cầu. */
function handle(req, res, url, opts = {}) {
  if (!url.pathname.startsWith('/update/')) return false;
  const host = String(req.headers.host || '').replace(/:\d+$/, '');
  const send = (code, obj) => {
    res.writeHead(code, { 'Content-Type': 'application/json; charset=utf-8', 'Cache-Control': 'no-store' });
    res.end(JSON.stringify(obj));
  };
  if (!['localhost', '127.0.0.1', '[::1]'].includes(host)) { send(403, { ok: false, error: 'Forbidden' }); return true; }
  if (url.pathname === '/update/check' && req.method === 'GET') {
    check().then((r) => send(200, { ok: true, ...r })).catch((e) => send(200, { ok: false, current: localInfo().version, error: e.message }));
    return true;
  }
  if (url.pathname === '/update/apply' && req.method === 'POST') {
    if (busy) { send(409, { ok: false, error: 'đang cập nhật' }); return true; }
    busy = true;
    apply(opts.log).then((r) => {
      send(200, { ok: true, ...r });
      if (r.changed > 0) {
        opts.log && opts.log(`Đã cập nhật ${r.changed} file lên bản ${r.version}. Tự khởi động lại…`);
        setTimeout(() => process.exit(3), 800);
      } else busy = false;
    }).catch((e) => { busy = false; send(200, { ok: false, error: e.message }); });
    return true;
  }
  send(404, { ok: false });
  return true;
}

module.exports = { handle, check, apply, unzip, localInfo };
