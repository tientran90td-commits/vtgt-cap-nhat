'use strict';
/*
 * APP WINDOWS "CARO LIVE": cửa sổ điều khiển (shell.html) + chạy game bên trong + nối điện thoại qua tài khoản.
 * Màn hình LIVE ưu tiên mở bằng Microsoft Edge (có giọng đọc tiếng Việt tự nhiên HoaiMy/NamMinh mà Electron không có).
 */
const { app, BrowserWindow, ipcMain, shell, dialog, Menu } = require('electron');
const fs = require('fs');
const path = require('path');
const cp = require('child_process');
const { Engine } = require('./engine');

const ROOT = path.join(__dirname, '..');
const UI_FILE = path.join(ROOT, 'data', 'app-ui.json');
const engine = new Engine(ROOT, process.execPath, true);
let win = null;
let remoteStatus = null;
let remoteTimer = null;

if (!app.requestSingleInstanceLock()) app.quit();
app.on('second-instance', () => {
  if (win) {
    if (win.isMinimized()) win.restore();
    win.focus();
  }
});

const loadUi = () => {
  try {
    return JSON.parse(fs.readFileSync(UI_FILE, 'utf8'));
  } catch (e) {
    return {};
  }
};
const saveUi = (o) => {
  fs.mkdirSync(path.dirname(UI_FILE), { recursive: true });
  fs.writeFileSync(UI_FILE, JSON.stringify({ ...loadUi(), ...o }));
};

const origin = () => `http://localhost:${engine.port}`;

async function api(pathname, body) {
  const r = await fetch(origin() + pathname, {
    method: body ? 'POST' : 'GET',
    headers: body ? { 'Content-Type': 'application/json' } : {},
    body: body ? JSON.stringify(body) : undefined,
    signal: AbortSignal.timeout(8000),
  });
  return r.json();
}

function send(ch, data) {
  if (win && !win.isDestroyed()) win.webContents.send(ch, data);
}

function fullState() {
  return { engine: engine.info(), logs: engine.logs.slice(-120), remote: remoteStatus, ui: loadUi(), version: readVersion(), edge: !!findEdge() };
}

function readVersion() {
  try {
    return JSON.parse(fs.readFileSync(path.join(ROOT, 'version.json'), 'utf8')).version;
  } catch (e) {
    return 0;
  }
}

function findEdge() {
  if (process.platform !== 'win32') return '';
  const dirs = [process.env['ProgramFiles(x86)'], process.env.ProgramFiles, process.env.LOCALAPPDATA].filter(Boolean);
  for (const d of dirs) {
    const f = path.join(d, 'Microsoft', 'Edge', 'Application', 'msedge.exe');
    if (fs.existsSync(f)) return f;
  }
  return '';
}

function openInApp(url, title, size) {
  const edge = findEdge();
  if (edge) {
    const prof = path.join(ROOT, 'data', 'edge-profile');
    const p = cp.spawn(edge, ['--app=' + url, '--autoplay-policy=no-user-gesture-required', '--user-data-dir=' + prof, '--no-first-run', '--window-size=' + size.join(',')], { detached: true, stdio: 'ignore' });
    p.on('error', () => openElectron(url, title, size));
    p.unref();
    return 'edge';
  }
  openElectron(url, title, size);
  return 'electron';
}

function openElectron(url, title, size) {
  const w = new BrowserWindow({ width: size[0], height: size[1], title, autoHideMenuBar: true, webPreferences: { autoplayPolicy: 'no-user-gesture-required' } });
  w.loadURL(url);
  return w;
}

function startRemotePolling() {
  clearInterval(remoteTimer);
  remoteTimer = setInterval(async () => {
    if (engine.state === 'off') {
      remoteStatus = null;
      return send('remote', null);
    }
    try {
      remoteStatus = await api('/remote');
    } catch (e) {
      remoteStatus = null;
    }
    send('remote', remoteStatus);
  }, 1500);
}

function createWindow() {
  Menu.setApplicationMenu(null);
  win = new BrowserWindow({
    width: 940,
    height: 760,
    minWidth: 760,
    minHeight: 560,
    title: 'Caro LIVE',
    backgroundColor: '#14161f',
    webPreferences: { preload: path.join(__dirname, 'preload.js'), contextIsolation: true, nodeIntegration: false, sandbox: false },
  });
  win.loadFile(path.join(__dirname, 'shell.html'));
  win.on('close', (e) => {
    if (engine.state === 'off' || win.forceClose) return;
    const c = dialog.showMessageBoxSync(win, { type: 'question', buttons: ['Tắt game và thoát', 'Ở lại'], defaultId: 1, cancelId: 1, title: 'Caro LIVE', message: 'Game đang chạy. Thoát app sẽ tắt game và ngắt kết nối điện thoại.' });
    if (c === 1) e.preventDefault();
  });
  win.on('closed', () => {
    win = null;
  });
}

ipcMain.handle('state', () => fullState());
ipcMain.handle('start', (_e, { mode, tiktok }) => {
  if (mode === 'tiktok') {
    const id = engine.setTiktokId(tiktok);
    if (!id) return { ok: false, error: 'Hãy nhập ID TikTok của bạn (không có dấu @).' };
  }
  saveUi({ mode });
  engine.mode = mode;
  engine.start(mode);
  return { ok: true };
});
ipcMain.handle('stop', () => {
  engine.stop();
  return { ok: true };
});
ipcMain.handle('openLive', (_e, layout) => {
  const l = layout === 'landscape' ? 'landscape' : 'portrait';
  const size = l === 'portrait' ? [540, 960] : [1280, 720];
  return { ok: true, by: openInApp(`${origin()}/live.html?layout=${l}`, 'Caro LIVE - màn hình phát', size) };
});
ipcMain.handle('openPanel', () => {
  openElectron(origin() + '/', 'Caro LIVE - bảng điều khiển', [1200, 800]);
  return { ok: true };
});
// Lấy bảng xếp hạng + cài đặt từ thư mục game cũ (chọn thư mục game cũ, hoặc thẳng thư mục "data" của nó).
ipcMain.handle('importOld', async () => {
  if (engine.state !== 'off') return { ok: false, error: 'Hãy bấm "Dừng" game trước rồi mới lấy dữ liệu cũ.' };
  const r = await dialog.showOpenDialog(win, { title: 'Chọn thư mục game Caro LIVE cũ', properties: ['openDirectory'] });
  if (r.canceled || !r.filePaths[0]) return { ok: false, error: '' };
  const pick = r.filePaths[0];
  const src = [path.join(pick, 'data'), pick].find((d) => fs.existsSync(path.join(d, 'thanh-tich.json')));
  if (!src) return { ok: false, error: 'Không thấy file bảng xếp hạng (thanh-tich.json) trong thư mục đó. Hãy chọn đúng thư mục game cũ.' };
  const dst = path.join(ROOT, 'data');
  if (path.resolve(src) === path.resolve(dst)) return { ok: false, error: 'Đây chính là thư mục của app mới rồi.' };
  fs.mkdirSync(dst, { recursive: true });
  const bak = path.join(dst, 'backup-truoc-khi-lay-du-lieu-cu-' + Date.now());
  const done = [];
  for (const f of ['thanh-tich.json', 'cai-dat.json']) {
    const from = path.join(src, f);
    if (!fs.existsSync(from)) continue;
    const to = path.join(dst, f);
    if (fs.existsSync(to)) {
      fs.mkdirSync(bak, { recursive: true });
      fs.copyFileSync(to, path.join(bak, f));
    }
    fs.copyFileSync(from, to);
    done.push(f === 'thanh-tich.json' ? 'bảng xếp hạng' : 'cài đặt');
  }
  return { ok: true, done };
});
ipcMain.handle('openFolder', () => shell.openPath(ROOT));
ipcMain.handle('remoteConfig', async (_e, b) => {
  if (engine.state === 'off') return { ok: false, error: 'Hãy bấm "Bắt đầu" để chạy game trước.' };
  try {
    return await api('/remote/config', b);
  } catch (e) {
    return { ok: false, error: 'Game chưa sẵn sàng, đợi vài giây rồi thử lại.' };
  }
});

engine.on('log', (l) => send('log', l));
engine.on('state', (s) => send('engine', s));

app.whenReady().then(() => {
  createWindow();
  startRemotePolling();
});
app.on('before-quit', () => {
  if (win) win.forceClose = true;
  engine.stop();
});
app.on('window-all-closed', () => app.quit());
