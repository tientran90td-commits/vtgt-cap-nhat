'use strict';
/*
 * KẾT NỐI TIKTOK LIVE: đọc bình luận, tim, quà, chia sẻ, follow rồi đưa vào hub.js
 * Dùng thư viện tiktok-live-connector. Tự kết nối lại nếu bị rớt mạng hoặc chưa LIVE.
 */

const { sanitizeName } = require('./safety');

function pickUser(u) {
  if (!u) return null;
  const uniqueId = String(u.uniqueId || u.displayId || '').trim();
  const rawId = String(u.userId || u.idStr || u.id || '').trim();
  const id = (uniqueId || rawId).toLowerCase();
  if (!id) return null;
  const avatar =
    u.profilePictureUrl ||
    (u.avatarThumb && u.avatarThumb.urlList && u.avatarThumb.urlList[0]) ||
    (u.avatarMedium && u.avatarMedium.urlList && u.avatarMedium.urlList[0]) ||
    (u.profilePicture && (u.profilePicture.url && u.profilePicture.url[0])) ||
    (u.profilePicture && (u.profilePicture.urls && u.profilePicture.urls[0])) ||
    '';
  return {
    id,
    rawId, // mã số TikTok (có thể khác id chữ): dùng để nối cùng 1 người giữa các loại sự kiện
    uniqueId: uniqueId || id,
    name: sanitizeName(u.nickname || uniqueId || id, rawId || id), // bỏ link / che từ thô tục trong tên hiển thị
    avatar,
  };
}

/** Tạo các hàm xử lý sự kiện (tách riêng để dễ kiểm tra). */
function makeHandlers(hub) {
  const groups = new Map(); // theo dõi chuỗi quà liên tiếp để không cộng trùng
  const alias = new Map(); // mã số TikTok -> id chữ của cùng người (học từ mọi loại sự kiện)

  /**
   * Nhận diện người dùng. Sự kiện tim của TikTok đôi khi chỉ có mã số mà thiếu tên đăng nhập (@id),
   * trong khi bình luận lại có @id -> trước đây bị tính thành 2 người khác nhau (điểm tim không lên, thả tim xác nhận không nhận).
   * Ở đây nối lại: học (mã số -> @id) từ mọi sự kiện, và gộp điểm của "người trùng" đã lỡ tạo ra.
   */
  function who(raw) {
    const u = pickUser(raw);
    if (!u) return null;
    const hasName = !!String((raw && (raw.uniqueId || raw.displayId)) || '').trim();
    if (u.rawId) {
      if (hasName) {
        alias.set(u.rawId, u.id);
        if (u.rawId !== u.id && hub.interaction && hub.interaction.mergeUser) hub.interaction.mergeUser(u.rawId, u.id);
      } else if (alias.has(u.rawId)) {
        u.id = alias.get(u.rawId);
        u.uniqueId = u.id;
      }
    }
    return u;
  }

  function prune(now) {
    if (groups.size < 200) return;
    for (const [k, v] of groups) if (now - v.at > 120000) groups.delete(k);
  }

  return {
    chat(data) {
      const user = who(data && data.user);
      const text = data && (data.comment != null ? data.comment : data.content);
      if (!user || !text) return;
      hub.onComment(user, String(text));
    },

    like(data) {
      const user = who(data && data.user);
      if (!user) {
        if (hub.onLikeIgnored) hub.onLikeIgnored(); // tim không rõ người thả (TikTok không gửi tên)
        return;
      }
      const n = Number(data.likeCount != null ? data.likeCount : data.count) || 1;
      hub.onLike(user, n);
    },

    gift(data) {
      const user = who(data && data.user);
      if (!user) return;
      const g = data.gift || data.giftDetails || {};
      const diamonds = Number(data.diamondCount != null ? data.diamondCount : g.diamondCount) || 1;
      const name = data.giftName || g.giftName || g.name || `quà #${data.giftId || ''}`;
      const repeat = Math.max(1, Number(data.repeatCount != null ? data.repeatCount : data.comboCount) || 1);
      const key = `${user.id}|${data.groupId || data.giftId || name}`;
      const now = Date.now();
      prune(now);
      const prev = groups.get(key);
      if (!prev) {
        groups.set(key, { count: repeat, at: now });
        hub.onGift(user, { name, diamonds, count: repeat, key });
      } else {
        const delta = repeat - prev.count;
        if (delta > 0) {
          prev.count = repeat;
          prev.at = now;
          hub.onGiftPoints(user, diamonds, delta, key, repeat);
        }
      }
      if (data.repeatEnd) groups.delete(key);
    },

    share(data) {
      const user = who(data && data.user);
      if (user) hub.onShare(user);
    },

    follow(data) {
      const user = who(data && data.user);
      if (user) hub.onFollow(user);
    },
  };
}

function explainError(e) {
  const name = (e && (e.name || (e.constructor && e.constructor.name))) || '';
  const msg = (e && e.message) || String(e);
  if (/UserOffline/i.test(name) || /offline|not live|isn't live/i.test(msg)) {
    return 'Tài khoản chưa bật LIVE (hoặc sai ID TikTok). Bật LIVE rồi game sẽ tự kết nối.';
  }
  if (/429|rate/i.test(msg)) return 'Bị giới hạn lượt kết nối, đang thử lại (xem HUONG-DAN.txt mục API key).';
  return `Lỗi kết nối: ${msg}`.slice(0, 160);
}

function startTikTok(cfg, hub, log = console.log) {
  const { TikTokLiveConnection, WebcastEvent, ControlEvent } = require('tiktok-live-connector');
  const handlers = makeHandlers(hub);
  let conn = null;
  let retryTimer = null;
  let stopped = false;
  let connecting = false;

  function scheduleRetry(seconds = 10) {
    if (stopped || retryTimer) return;
    retryTimer = setTimeout(() => {
      retryTimer = null;
      connectOnce();
    }, seconds * 1000);
  }

  function cleanup() {
    if (!conn) return;
    try {
      conn.removeAllListeners();
    } catch (e) {
      /* bỏ qua */
    }
    try {
      conn.disconnect();
    } catch (e) {
      /* bỏ qua */
    }
    conn = null;
  }

  async function connectOnce() {
    if (stopped || connecting) return;
    connecting = true;
    cleanup();
    hub.setConnection('connecting', `Đang kết nối @${cfg.tiktokUsername}…`);
    try {
      conn = new TikTokLiveConnection(
        cfg.tiktokUsername,
        cfg.signApiKey ? { signApiKey: cfg.signApiKey } : {}
      );
      const safe = (fn) => (data) => {
        try {
          fn(data);
        } catch (e) {
          log('Lỗi xử lý sự kiện:', e.message);
        }
      };
      conn.on(WebcastEvent.CHAT, safe(handlers.chat));
      conn.on(WebcastEvent.LIKE, safe(handlers.like));
      conn.on(WebcastEvent.GIFT, safe(handlers.gift));
      conn.on(WebcastEvent.SHARE, safe(handlers.share));
      conn.on(WebcastEvent.FOLLOW, safe(handlers.follow));
      conn.on(ControlEvent.ERROR, (e) => log('Cảnh báo TikTok:', (e && e.message) || e));
      conn.on(ControlEvent.DISCONNECTED, () => {
        hub.setConnection('error', 'Mất kết nối TikTok, đang thử lại…');
        log('Mất kết nối, thử lại sau 8 giây…');
        connecting = false;
        cleanup();
        scheduleRetry(8);
      });
      conn.on(WebcastEvent.STREAM_END, () => {
        hub.setConnection('error', 'Phiên LIVE đã kết thúc.');
        log('Phiên LIVE đã kết thúc.');
      });
      await conn.connect();
      hub.setConnection('connected', `Đã kết nối @${cfg.tiktokUsername}`);
      log(`Đã kết nối LIVE của @${cfg.tiktokUsername}`);
    } catch (e) {
      const text = explainError(e);
      hub.setConnection('error', text);
      log(text);
      cleanup();
      scheduleRetry(10);
    } finally {
      connecting = false;
    }
  }

  connectOnce();
  return {
    stop() {
      stopped = true;
      if (retryTimer) clearTimeout(retryTimer);
      cleanup();
    },
  };
}

module.exports = { startTikTok, makeHandlers, pickUser, explainError };
