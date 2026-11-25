'use strict';
/*
 * "HÒM THƯ" ĐỂ MÁY TÍNH VÀ ĐIỆN THOẠI GẶP NHAU. Dùng dịch vụ ntfy.sh (miễn phí, công khai).
 * Máy tính để lại 1 tin ĐÃ MÃ HÓA (chứa địa chỉ đường hầm hiện tại); điện thoại đến lấy tin mới nhất rồi giải mã.
 * Tên hòm thư (topic) được tính từ tài khoản + mật khẩu nên người ngoài không đoán được; nội dung chỉ chủ tài khoản đọc được.
 * Máy chủ có thể đổi trong data/remote.json ("server") nếu bạn tự dựng ntfy riêng.
 */
const DEFAULT_SERVER = 'https://ntfy.sh';

const clean = (s) => String(s || DEFAULT_SERVER).replace(/\/+$/, '');

async function publish(server, topic, text) {
  const r = await fetch(`${clean(server)}/${encodeURIComponent(topic)}`, {
    method: 'POST',
    body: text,
    headers: { 'Content-Type': 'text/plain; charset=utf-8', 'X-Cache': 'yes' },
    signal: AbortSignal.timeout(15000),
  });
  if (!r.ok) throw new Error('hòm thư trả mã ' + r.status);
}

/** Lấy các tin đang lưu trong hòm thư, mới nhất ở cuối. */
async function fetchAll(server, topic) {
  const r = await fetch(`${clean(server)}/${encodeURIComponent(topic)}/json?poll=1&since=all`, { signal: AbortSignal.timeout(15000) });
  if (!r.ok) throw new Error('hòm thư trả mã ' + r.status);
  const out = [];
  for (const line of (await r.text()).split('\n')) {
    if (!line.trim()) continue;
    try {
      const m = JSON.parse(line);
      if (m.event === 'message' && typeof m.message === 'string') out.push({ time: m.time || 0, text: m.message });
    } catch (e) {
      /* bỏ dòng lỗi */
    }
  }
  return out.sort((a, b) => a.time - b.time);
}

module.exports = { publish, fetchAll, DEFAULT_SERVER };
