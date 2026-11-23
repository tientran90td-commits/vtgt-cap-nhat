"use strict";
/*
 * NHẮC FOLLOW / CHIA SẺ định kỳ (hiện chữ trên màn hình + điều phối viên đọc).
 * Chỉ quyết định "khi nào nhắc, nhắc gì" - nội dung câu nằm ở script.js (sửa được ở bảng điều khiển).
 */
class Reminder {
  constructor(cfg) {
    this.cfg = cfg;
    this.last = Date.now();
    this.next = 'follow';
  }

  /** Trả về 'follow' | 'share' khi đến giờ nhắc, ngược lại null. */
  tick(now, phase) {
    const every = Number(this.cfg.reminderSeconds) * 1000;
    if (!(every > 0)) {
      this.last = now; // đang tắt: tính lại mốc để khi bật lại không nhắc liền
      return null;
    }
    if (phase !== 'lobby' && phase !== 'playing') return null;
    if (now - this.last < every) return null;
    this.last = now;
    const k = this.next;
    this.next = k === 'follow' ? 'share' : 'follow';
    return k;
  }
}

module.exports = { Reminder };
