'use strict';
/*
 * ĐIỂM TƯƠNG TÁC: bình luận, thả tim, quà tặng, chia sẻ, follow.
 * Người có điểm cao nhất sẽ được chọn lên bàn chơi (xem match.js).
 */


class Interaction {
  constructor(pointsCfg, guardModeFn) {
    // giá trị mặc định (phòng khi config.js cũ thiếu mục mới)
    this.cfg = Object.assign(
      {
        comment: 1, commentCooldownSeconds: 3, like: 1, likeMaxPerEvent: 0, likeCapPerRound: 0,
        share: 60, follow: 100, giftBase: 150, giftPerDiamond: 25, giftPower: 0.6, giftCapPerRound: 0,
      },
      pointsCfg || {}
    );
    this.users = new Map();
    this.seq = 0;
    this.frozen = false; // true = tạm ngưng cộng điểm (chế độ "cày điểm": chỉ tính điểm trong khoảng cày sau mỗi trận)
  }

  touch(user) {
    let u = this.users.get(user.id);
    if (!u) {
      u = {
        id: user.id,
        uniqueId: user.uniqueId || '',
        rawId: user.rawId || '',
        name: user.name || user.uniqueId || 'Ẩn danh',
        avatar: user.avatar || '',
        points: 0,
        diamonds: 0,
        likePts: 0, // điểm đã nhận từ thả tim trong vòng này (để giới hạn)
        likeFrac: 0, // phần lẻ điểm tim (do bị giảm hệ số) để cộng dồn
        giftPts: 0, // điểm đã nhận từ quà trong vòng này (để giới hạn)
        lastCommentAt: 0,
        shared: false,
        followed: false,
        order: this.seq++,
        seenAt: Date.now(),
      };
      this.users.set(u.id, u);
    } else {
      u.seenAt = Date.now();
      if (user.name) u.name = user.name;
      if (user.avatar) u.avatar = user.avatar;
      if (user.uniqueId) u.uniqueId = user.uniqueId;
      if (user.rawId) u.rawId = user.rawId;
    }
    return u;
  }

  /** Gộp "người trùng" (tạo ra do chỉ có mã số) vào người thật: cộng dồn điểm rồi xóa bản trùng. */
  mergeUser(fromId, toId) {
    if (!fromId || fromId === toId) return;
    const g = this.users.get(fromId);
    if (!g) return;
    const t = this.users.get(toId);
    if (t) {
      t.points += g.points;
      t.diamonds += g.diamonds;
      t.likePts += g.likePts;
      t.giftPts += g.giftPts;
      t.likeFrac += g.likeFrac;
      t.shared = t.shared || g.shared;
      t.followed = t.followed || g.followed;
      this.users.delete(fromId);
    } else {
      this.users.delete(fromId);
      g.id = toId;
      g.uniqueId = toId;
      this.users.set(toId, g);
    }
  }

  addComment(user, now = Date.now()) {
    const u = this.touch(user);
    if (this.frozen) return 0;
    if (now - u.lastCommentAt < this.cfg.commentCooldownSeconds * 1000) return 0;
    u.lastCommentAt = now;
    u.points += this.cfg.comment;
    return this.cfg.comment;
  }

  /** Thả tim: ít điểm nhất. Trần (likeMaxPerEvent / likeCapPerRound) mặc định 0 = không giới hạn. */
  addLike(user, count = 1, now = Date.now()) {
    const u = this.touch(user);
    if (this.frozen) return 0;
    let n = Math.max(0, Number(count) || 0);
    if (this.cfg.likeMaxPerEvent > 0) n = Math.min(n, this.cfg.likeMaxPerEvent); // 0 = không giới hạn
    let raw = n * this.cfg.like + u.likeFrac;
    let p = Math.floor(raw);
    u.likeFrac = raw - p;
    if (this.cfg.likeCapPerRound > 0) p = Math.max(0, Math.min(p, this.cfg.likeCapPerRound - u.likePts));
    u.likePts += p;
    u.points += p;
    return p;
  }

  /** Điểm của MỘT món quà: điểm gốc + thêm theo giá trị (tăng chậm dần, để quà siêu đắt không đè hẳn mọi người). */
  giftUnitPoints(unitDiamonds) {
    const d = Math.max(0, Number(unitDiamonds) || 0);
    return this.cfg.giftBase + this.cfg.giftPerDiamond * Math.pow(d, this.cfg.giftPower);
  }

  /** Tặng quà: unitDiamonds = kim cương của 1 món, count = số món. */
  addGift(user, unitDiamonds, count = 1) {
    const u = this.touch(user);
    if (this.frozen) return 0;
    const n = Math.max(1, Number(count) || 1);
    let p = Math.round(this.giftUnitPoints(unitDiamonds) * n);
    if (this.cfg.giftCapPerRound > 0) p = Math.max(0, Math.min(p, this.cfg.giftCapPerRound - u.giftPts));
    u.giftPts += p;
    u.points += p;
    u.diamonds += Math.max(0, Number(unitDiamonds) || 0) * n;
    return p;
  }

  addShare(user) {
    const u = this.touch(user);
    if (this.frozen || u.shared) return 0;
    u.shared = true;
    u.points += this.cfg.share;
    return this.cfg.share;
  }

  addFollow(user) {
    const u = this.touch(user);
    if (this.frozen || u.followed) return 0;
    u.followed = true;
    u.points += this.cfg.follow;
    return this.cfg.follow;
  }

  /** Top người tương tác nhiều nhất. filter(u) -> false để loại. */
  top(n = 5, { min = 1, filter = null } = {}) {
    return [...this.users.values()]
      .filter((u) => u.points >= min && (!filter || filter(u)))
      .sort((a, b) => b.points - a.points || b.diamonds - a.diamonds || a.order - b.order)
      .slice(0, n);
  }

  /** Trừ hết điểm của 1 người (không thả tim xác nhận -> mất suất). */
  zero(id) {
    const u = this.users.get(id);
    if (u) {
      u.points = 0;
      u.likePts = 0;
      u.giftPts = 0;
      u.likeFrac = 0;
    }
  }

  /** Xóa những người có id bắt đầu bằng prefix (dùng để dọn khán giả ảo của chế độ thử). */
  purge(prefix) {
    for (const id of [...this.users.keys()]) if (id.startsWith(prefix)) this.users.delete(id);
  }

  /** Bắt đầu vòng mới: xóa điểm (giữ lại tên + ảnh). */
  resetPoints() {
    for (const u of this.users.values()) {
      u.points = 0;
      u.diamonds = 0;
      u.likePts = 0;
      u.giftPts = 0;
      u.likeFrac = 0;
      u.shared = false;
      u.followed = false;
    }
  }
}

module.exports = { Interaction };
