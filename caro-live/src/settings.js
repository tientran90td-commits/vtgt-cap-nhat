'use strict';
/*
 * CÀI ĐẶT ĐỔI TRỰC TIẾP TỪ BẢNG ĐIỀU KHIỂN (không cần tắt game).
 * Giá trị được lưu vào data/cai-dat.json và nạp lại ở lần chạy sau.
 */
const fs = require('fs');
const path = require('path');

const NUMBERS = {
  lobbySeconds: [5, 300],
  nextLobbySeconds: [3, 300],
  coinSeconds: [4, 20],
  turnSeconds: [8, 180],
  farmSeconds: [10, 120], // chế độ cày điểm: số giây cày sau mỗi trận
  oBanAfter: [1, 3], // luật "O cấm 1 ô": cấm sau nước thứ mấy của X
  extraTimeSeconds: [5, 120],
  extraTimesPerGame: [0, 5],
  resultSeconds: [5, 60],
  maxTimeouts: [1, 5],
  maxWinStreak: [0, 50], // 0 = không giới hạn (người thắng ở lại mãi tới khi thua)
  minPointsToPlay: [0, 100000],
  reminderSeconds: [0, 1800],
  confirmSeconds: [0, 120],
  idleHintSeconds: [0, 120],
  crowdMax: [0, 14],
  clockSeconds: [0, 60],
  logoSize: [50, 250],
};
const BOOLS = ['blockBothEnds', 'forbidX', 'oBan', 'farmOn', 'giftPoints', 'winnerStays', 'hostCanPlay', 'autoNextGame', 'showSign', 'themeAuto', 'ledOn', 'showCellLabels', 'celebrateVideo', 'logoOn', 'logoBold', 'logoItalic', 'logoFrame'];
const LOGO_FONTS = ['default', 'arial', 'segoe', 'tahoma', 'trebuchet', 'verdana', 'georgia', 'times', 'palatino', 'impact', 'comic', 'courier'];
const TEXTS = { logoName: 40, logoSub: 40 }; // chữ tự gõ: tối đa bấy nhiêu ký tự

class Settings {
  constructor(cfg, file) {
    this.cfg = cfg;
    this.file = file;
    this.timer = null;
    if (!process.env.CARO_FAST) this.load();
  }

  load() {
    try {
      const saved = JSON.parse(fs.readFileSync(this.file, 'utf8'));
      this.apply(saved, false);
    } catch (e) {
      /* chưa có file: dùng mặc định */
    }
  }

  /** Kiểm tra + áp dụng. Trả về danh sách mục đã đổi. */
  apply(patch, save = true) {
    const changed = [];
    const c = this.cfg;
    if (!patch || typeof patch !== 'object') return changed;
    for (const [k, [lo, hi]] of Object.entries(NUMBERS)) {
      if (patch[k] === undefined) continue;
      const n = Math.round(Number(patch[k]));
      if (!Number.isFinite(n)) continue;
      const v = Math.min(hi, Math.max(lo, n));
      if (c[k] !== v) {
        c[k] = v;
        changed.push(k);
      }
    }
    if (typeof patch.boardSkin === 'string' && /^(auto|wood|[a-z0-9-]{1,20})$/.test(patch.boardSkin) && c.boardSkin !== patch.boardSkin) {
      c.boardSkin = patch.boardSkin;
      changed.push('boardSkin');
    }
    if (typeof patch.logoFont === 'string' && LOGO_FONTS.includes(patch.logoFont) && c.logoFont !== patch.logoFont) {
      c.logoFont = patch.logoFont;
      changed.push('logoFont');
    }
    if (typeof patch.logoColor === 'string' && (patch.logoColor === 'gold' || /^#[0-9a-fA-F]{6}$/.test(patch.logoColor)) && c.logoColor !== patch.logoColor) {
      c.logoColor = patch.logoColor;
      changed.push('logoColor');
    }
    for (const [k, max] of Object.entries(TEXTS)) {
      if (typeof patch[k] !== 'string') continue;
      const v = patch[k].replace(/[\u0000-\u001f\u007f<>]/g, '').replace(/\s+/g, ' ').trim().slice(0, max);
      if (c[k] !== v) {
        c[k] = v;
        changed.push(k);
      }
    }
    for (const k of BOOLS) {
      if (patch[k] === undefined) continue;
      const v = !!patch[k];
      if (c[k] !== v) {
        c[k] = v;
        changed.push(k);
      }
    }
    if (patch.voice && typeof patch.voice === 'object') {
      const v = c.voice;
      const p = patch.voice;
      if (p.on !== undefined && v.on !== !!p.on) { v.on = !!p.on; changed.push('voice.on'); }
      if (['quiet', 'normal', 'lively'].includes(p.talk) && v.talk !== p.talk) { v.talk = p.talk; changed.push('voice.talk'); }
      if (p.readMoves !== undefined && v.readMoves !== !!p.readMoves) { v.readMoves = !!p.readMoves; changed.push('voice.readMoves'); }
      if (p.volume !== undefined) {
        const n = Math.min(1, Math.max(0, Number(p.volume)));
        if (Number.isFinite(n) && v.volume !== n) { v.volume = n; changed.push('voice.volume'); }
      }
      if (p.bigGiftDiamonds !== undefined) {
        const n = Math.round(Number(p.bigGiftDiamonds));
        if (Number.isFinite(n)) {
          const val = Math.min(1000000, Math.max(1, n));
          if (v.bigGiftDiamonds !== val) { v.bigGiftDiamonds = val; changed.push('voice.bigGiftDiamonds'); }
        }
      }
      for (const [k, lo, hi] of [['mcRate', 0.6, 1.5], ['mcPitch', 0.5, 1.8], ['refRate', 0.6, 1.5], ['refPitch', 0.5, 1.8]]) {
        if (p[k] === undefined) continue;
        let val = null;
        if (p[k] !== null && p[k] !== '') {
          const n = Number(p[k]);
          if (!Number.isFinite(n)) continue;
          val = Math.min(hi, Math.max(lo, Math.round(n * 100) / 100));
        }
        if (v[k] !== val) { v[k] = val; changed.push('voice.' + k); }
      }
      for (const k of ['mcVoice', 'refVoice']) {
        if (typeof p[k] === 'string' && v[k] !== p[k].slice(0, 120)) {
          v[k] = p[k].slice(0, 120);
          changed.push('voice.' + k);
        }
      }
    }
    if (patch.sfx && typeof patch.sfx === 'object') {
      c.sfx = c.sfx || { on: true, volume: 0.7 };
      if (patch.sfx.on !== undefined && c.sfx.on !== !!patch.sfx.on) { c.sfx.on = !!patch.sfx.on; changed.push('sfx.on'); }
      if (patch.sfx.volume !== undefined) {
        const n = Math.min(1, Math.max(0, Number(patch.sfx.volume)));
        if (Number.isFinite(n) && c.sfx.volume !== n) { c.sfx.volume = n; changed.push('sfx.volume'); }
      }
    }
    if (patch.music && typeof patch.music === 'object') {
      c.music = c.music || { on: true, volume: 0.3 };
      if (patch.music.on !== undefined && c.music.on !== !!patch.music.on) { c.music.on = !!patch.music.on; changed.push('music.on'); }
      if (patch.music.volume !== undefined) {
        const n = Math.min(1, Math.max(0, Number(patch.music.volume)));
        if (Number.isFinite(n) && c.music.volume !== n) { c.music.volume = n; changed.push('music.volume'); }
      }
    }
    if (changed.length && save) this.save();
    return changed;
  }

  snapshot() {
    const c = this.cfg;
    const out = { voice: { ...c.voice }, sfx: { ...(c.sfx || { on: true, volume: 0.7 }) }, music: { ...(c.music || { on: true, volume: 0.3 }) } };
    for (const k of Object.keys(NUMBERS)) out[k] = c[k];
    for (const k of BOOLS) out[k] = c[k];
    out.boardSkin = c.boardSkin || 'auto';
    for (const k of Object.keys(TEXTS)) out[k] = c[k] === undefined ? '' : c[k];
    out.logoFont = c.logoFont || 'default';
    out.logoColor = c.logoColor || 'gold';
    return out;
  }

  save() {
    if (this.timer) return;
    this.timer = setTimeout(() => {
      this.timer = null;
      try {
        fs.mkdirSync(path.dirname(this.file), { recursive: true });
        fs.writeFileSync(this.file, JSON.stringify(this.snapshot(), null, 2));
      } catch (e) {
        /* không sao */
      }
    }, 600);
  }
}

module.exports = { Settings, NUMBERS };
