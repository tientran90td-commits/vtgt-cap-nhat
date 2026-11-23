/*
 * ẢNH ĐẠI DIỆN TIKTOK: đổi địa chỉ ảnh sang đường qua máy chủ game (tránh lỗi chặn ảnh),
 * tải 1 lần rồi nhớ lại, báo khi tải xong để vẽ lại biểu tượng.
 */
const cache = new Map(); // src -> { img, ok, waiters }

export function avatarSrc(url) {
  if (!url) return '';
  return url.startsWith('/') ? url : '/avatar?u=' + encodeURIComponent(url);
}

/** Trả về ảnh đã tải xong (hoặc null). Nếu chưa tải thì bắt đầu tải và gọi onReady khi xong. */
export function getAvatar(url, onReady) {
  const src = avatarSrc(url);
  if (!src) return null;
  let e = cache.get(src);
  if (!e) {
    const img = new Image();
    e = { img, ok: false, failed: false, waiters: [] };
    cache.set(src, e);
    img.onload = () => {
      e.ok = true;
      for (const f of e.waiters.splice(0)) f();
    };
    img.onerror = () => {
      e.failed = true;
      e.waiters.length = 0;
    };
    img.src = src;
  }
  if (e.ok) return e.img;
  if (!e.failed && onReady) e.waiters.push(onReady);
  return null;
}
