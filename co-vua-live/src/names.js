'use strict';
/*
 * ĐỌC ĐÚNG TÊN NGƯỜI CHƠI
 * Tên TikTok thường có emoji, chữ kiểu lạ (𝓣𝓾𝓪𝓷), dấu gạch dưới, dãy số dài...
 * File này làm sạch tên để giọng đọc phát âm được.
 *
 * Muốn ép cách đọc cho 1 người: mở data/cach-doc-ten.json, thêm dòng dạng
 *   "id-tiktok-hoac-ten": "cách đọc bằng chữ"
 * Ví dụ:  "vnpsolar": "vê en pê sô la"   (lưu file là có hiệu lực ngay, không cần tắt game)
 */
const fs = require('fs');

function cleanForSpeech(raw) {
  let s = String(raw == null ? '' : raw).normalize('NFKC'); // chữ kiểu lạ -> chữ thường
  s = s.replace(/[​-‏‪-‮⁠﻿︎️]/g, ' ');
  s = s.replace(/[\p{Extended_Pictographic}\p{Emoji_Presentation}]/gu, ' '); // emoji
  s = s.replace(/[\p{So}\p{Sk}\p{Sm}\p{Sc}\p{Cf}\p{Cc}\p{Cs}]/gu, ' '); // ký hiệu lạ
  s = s.replace(/^@+/, '');
  s = s.replace(/[_\-.·•|~*#^<>\\/[\](){}"'`´:;!?+=,&%$]+/g, ' ');
  s = s.replace(/(\p{Ll})(\p{Lu})/gu, '$1 $2'); // tuanKiet -> tuan Kiet
  s = s.replace(/(\p{L})(\d)/gu, '$1 $2').replace(/(\d)(\p{L})/gu, '$1 $2'); // tách chữ-số
  s = s.replace(/(\p{L})\1{2,}/gu, '$1$1'); // "hayyyyy" -> "hayy"
  s = s.replace(/\s+/g, ' ').trim();
  if (!/\p{L}/u.test(s)) return ''; // chỉ toàn emoji/số -> không đọc được
  const words = s.split(' ').slice(0, 4).join(' ').slice(0, 30).trim();
  return words.replace(/\d{3,}/g, (d) => d.split('').join(' ')); // 2003 -> 2 0 0 3
}

class Namer {
  constructor(file) {
    this.file = file;
    this.map = {};
    this.mtime = 0;
  }

  refresh() {
    try {
      const st = fs.statSync(this.file);
      if (st.mtimeMs === this.mtime) return;
      this.mtime = st.mtimeMs;
      const raw = JSON.parse(fs.readFileSync(this.file, 'utf8'));
      this.map = {};
      for (const [k, v] of Object.entries(raw)) {
        if (!k.startsWith('_') && typeof v === 'string' && v.trim()) {
          this.map[k.trim().toLowerCase()] = v.trim();
        }
      }
    } catch (e) {
      this.map = {};
      this.mtime = 0;
    }
  }

  /** Đọc 1 đoạn chữ bất kỳ (ví dụ tên quà): ưu tiên cách đọc đã đặt trong cach-doc-ten.json */
  sayText(raw, fallback = '') {
    this.refresh();
    const key = String(raw || '').trim().toLowerCase();
    if (key && this.map[key]) return this.map[key];
    return cleanForSpeech(raw) || fallback;
  }

  /** Tên để ĐỌC thành tiếng. fallback dùng khi tên không đọc được. */
  say(user, fallback = 'người chơi') {
    this.refresh();
    if (!user) return fallback;
    const keys = [user.uniqueId, user.id, user.name]
      .filter(Boolean)
      .map((s) => String(s).trim().toLowerCase());
    for (const k of keys) if (this.map[k]) return this.map[k];
    return cleanForSpeech(user.name) || cleanForSpeech(user.uniqueId) || fallback;
  }
}

module.exports = { Namer, cleanForSpeech };
