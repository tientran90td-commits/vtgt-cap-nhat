'use strict';
/*
 * CHỐNG AUTO-CLICK THẢ TIM (module riêng).
 *
 * Ý tưởng: người bấm tay thì bấm thành từng đợt rồi nghỉ; app auto-click thì bấm đều đều không nghỉ.
 * Mỗi người có 2 "bình sức bấm tim":
 *   - bình ngắn (burst): chứa vài chục-vài trăm lượt, hồi nhanh -> đủ cho người bấm tay liên hồi vài chục giây;
 *   - bình dài (long):  chứa nhiều hơn nhưng hồi chậm -> chặn kiểu bấm đều liên tục hàng chục phút.
 * Lượt tim còn "sức" -> tính điểm đủ. Hết sức -> chỉ tính một phần nhỏ (over) chứ không về 0,
 * nên người bấm tay quá hăng cũng không bị mất trắng. Người bấm nghỉ là sức hồi lại ngay.
 * Quá nhiều lượt bị giảm trong 1 phút -> đánh dấu "nghi auto-click" (hiện ⚠ trong bảng điều khiển).
 * Không đụng tới điểm quà / follow / chia sẻ, và 1 lượt tim vẫn đủ để "thả tim xác nhận lên đài".
 */

const PRESETS = {
  off: null,
  loose: { burstCap: 250, burstRate: 6, longCap: 2000, longRate: 5, over: 0.2, flagAt: 500 },
  normal: { burstCap: 120, burstRate: 3.5, longCap: 800, longRate: 3.0, over: 0.1, flagAt: 250 },
  strict: { burstCap: 80, burstRate: 2.5, longCap: 400, longRate: 1.8, over: 0.05, flagAt: 150 },
};

class LikeGuard {
  /** modeFn() trả 'off' | 'loose' | 'normal' | 'strict' (đọc lại mỗi lần để đổi ngay trên bảng điều khiển). */
  constructor(modeFn) {
    this.modeFn = modeFn || (() => 'normal');
    this.st = new Map();
    this.lastSweep = 0;
  }

  /**
   * Một lần nhận n lượt tim của người id.
   * Trả { full, reduced, over, suspect }: full lượt tính đủ điểm, reduced lượt chỉ tính hệ số over.
   */
  take(id, n, now = Date.now()) {
    n = Math.max(0, Math.floor(Number(n) || 0));
    const P = PRESETS[this.modeFn()] || null;
    if (!P || n === 0) return { full: n, reduced: 0, over: 1, suspect: false };
    let s = this.st.get(id);
    if (!s) {
      s = { a: P.burstCap, b: P.longCap, t: now, lim: [], flagged: false };
      this.st.set(id, s);
    }
    const dt = Math.max(0, (now - s.t) / 1000);
    s.t = now;
    s.a = Math.min(P.burstCap, s.a + dt * P.burstRate);
    s.b = Math.min(P.longCap, s.b + dt * P.longRate);
    const full = Math.min(n, Math.floor(s.a), Math.floor(s.b));
    s.a -= full;
    s.b -= full;
    const reduced = n - full;
    if (reduced > 0) s.lim.push([now, reduced]);
    while (s.lim.length && now - s.lim[0][0] > 60000) s.lim.shift();
    let sum = 0;
    for (const e of s.lim) sum += e[1];
    const suspect = sum >= P.flagAt;
    const newly = suspect && !s.flagged;
    if (suspect) s.flagged = true;
    else if (!s.lim.length) s.flagged = false;
    if (now - this.lastSweep > 600000) this.sweep(now);
    return { full, reduced, over: P.over, suspect, newly };
  }

  sweep(now = Date.now()) {
    this.lastSweep = now;
    for (const [id, s] of this.st) if (now - s.t > 900000) this.st.delete(id);
  }
}

module.exports = { LikeGuard, PRESETS };
