'use strict';
/*
 * CÀI ĐẶT CÓ THỂ ĐỔI Ở BẢNG ĐIỀU KHIỂN, lưu vào data/cai-dat.json (giữ nguyên khi cập nhật phần mềm).
 */
const fs = require('fs');
const path = require('path');
const { checkAnnouncement, norm } = require('./safety');

const NUMBERS = {
  reverseChance: [0, 100],
  userCooldown: [0, 900],
  maxQueue: [1, 60],
  autoIdleSeconds: [10, 300],
  announceEvery: [0, 30],
  voiceVolume: [0, 1],
  collectSeconds: [15, 180],
  aiTimeout: [3, 25],
};
const BOOLS = ['allowThree', 'allowFive', 'autoDraw', 'giftPriority', 'voiceOn', 'paused', 'askInfo'];
const SPEEDS = ['slow', 'normal', 'fast'];

class Settings {
  constructor(cfg, file) {
    this.file = file;
    this.v = { ...cfg.defaults };
    try {
      const saved = JSON.parse(fs.readFileSync(file, 'utf8'));
      this.apply(saved, true);
    } catch (e) {
      /* chưa có file */
    }
  }

  /** Áp dụng thay đổi sau khi kiểm tra. Trả về { ok, msg }. */
  apply(patch, silent = false) {
    if (!patch || typeof patch !== 'object') return { ok: false, msg: 'Dữ liệu không hợp lệ' };
    for (const [k, [lo, hi]] of Object.entries(NUMBERS)) {
      if (patch[k] == null || patch[k] === '') continue;
      const n = Number(patch[k]);
      if (Number.isFinite(n)) this.v[k] = Math.min(hi, Math.max(lo, k === 'voiceVolume' ? n : Math.round(n)));
    }
    for (const k of BOOLS) if (patch[k] != null) this.v[k] = !!patch[k];
    if (patch.defaultSpread != null) this.v.defaultSpread = [3, 5].includes(Number(patch.defaultSpread)) ? Number(patch.defaultSpread) : 1;
    if (SPEEDS.includes(patch.readSpeed)) this.v.readSpeed = patch.readSpeed;
    if (['off', 'claude', 'gemini'].includes(patch.aiProvider)) this.v.aiProvider = patch.aiProvider;
    if (typeof patch.aiModel === 'string') this.v.aiModel = patch.aiModel.replace(/[^\w.\-]/g, '').slice(0, 60);
    for (const k of ['title', 'subtitle']) {
      if (typeof patch[k] === 'string') {
        const s = norm(patch[k]).slice(0, 40);
        const c = checkAnnouncement(s);
        if (!c.ok) return this.fail(c.msg, silent);
        this.v[k] = s;
      }
    }
    if (typeof patch.announceText === 'string') {
      const s = norm(patch.announceText).slice(0, 140);
      if (s) {
        const c = checkAnnouncement(s);
        if (!c.ok) return this.fail(c.msg, silent);
      }
      this.v.announceText = s;
    }
    if (!silent) this.save();
    return { ok: true };
  }

  /** Có ô bị từ chối: vẫn lưu các ô hợp lệ đã áp dụng, rồi báo lỗi. */
  fail(msg, silent) {
    if (!silent) this.save();
    return { ok: false, msg };
  }

  save() {
    try {
      fs.mkdirSync(path.dirname(this.file), { recursive: true });
      fs.writeFileSync(this.file, JSON.stringify(this.v, null, 2));
    } catch (e) {
      /* không ghi được thì thôi */
    }
  }

  snapshot() {
    return { ...this.v };
  }
}

module.exports = { Settings, NUMBERS, BOOLS };
