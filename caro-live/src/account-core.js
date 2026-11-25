'use strict';
/*
 * TÀI KHOẢN KẾT NỐI (dùng chung cho app PC và app điện thoại - cùng một đoạn mã chạy ở cả 2 nơi).
 * Từ "tài khoản + mật khẩu" tạo ra 3 thứ (không thể đoán ngược lại mật khẩu):
 *   - token : mã vào cửa. App điện thoại gửi mã này khi nối vào máy tính qua Internet.
 *   - topic : tên "hòm thư" công khai để 2 bên gặp nhau (máy tính để lại địa chỉ, điện thoại đến lấy).
 *   - key   : khóa AES-256 để mã hóa địa chỉ trong hòm thư (người ngoài chỉ thấy chuỗi vô nghĩa).
 * Cần môi trường có WebCrypto (Node >= 20, Electron, Chrome / WebView Android).
 */
(function (root, factory) {
  if (typeof module === 'object' && module.exports) module.exports = factory(globalThis.crypto);
  else root.CaroAccount = factory(root.crypto);
})(typeof self !== 'undefined' ? self : this, function (crypto) {
  const subtle = crypto.subtle;
  const enc = new TextEncoder();
  const dec = new TextDecoder();
  const ITER = 120000;

  const hex = (u8) => Array.from(u8, (b) => b.toString(16).padStart(2, '0')).join('');
  const b64 = (u8) => {
    let s = '';
    for (let i = 0; i < u8.length; i += 0x8000) s += String.fromCharCode.apply(null, u8.subarray(i, i + 0x8000));
    return btoa(s).replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '');
  };
  const unb64 = (s) => {
    const t = String(s).replace(/-/g, '+').replace(/_/g, '/');
    const bin = atob(t + '='.repeat((4 - (t.length % 4)) % 4));
    const u8 = new Uint8Array(bin.length);
    for (let i = 0; i < bin.length; i++) u8[i] = bin.charCodeAt(i);
    return u8;
  };

  /** Tên tài khoản không phân biệt hoa thường / dấu cách thừa. */
  function normAccount(a) {
    return String(a || '').normalize('NFC').trim().toLowerCase().replace(/\s+/g, ' ');
  }

  /** Kiểm tra tài khoản + mật khẩu có đủ dài không. Trả về chuỗi lỗi hoặc ''. */
  function check(account, password) {
    if (normAccount(account).length < 3) return 'Tên tài khoản cần ít nhất 3 ký tự.';
    if (String(password || '').length < 6) return 'Mật khẩu cần ít nhất 6 ký tự.';
    return '';
  }

  async function derive(account, password) {
    const bad = check(account, password);
    if (bad) throw new Error(bad);
    const base = await subtle.importKey('raw', enc.encode(String(password)), 'PBKDF2', false, ['deriveBits']);
    const bits = await subtle.deriveBits(
      { name: 'PBKDF2', hash: 'SHA-256', iterations: ITER, salt: enc.encode('caro-live/v1/' + normAccount(account)) },
      base,
      96 * 8,
    );
    const u8 = new Uint8Array(bits);
    const keyBytes = u8.slice(64, 96);
    const key = await keyFrom(b64(keyBytes));
    return { token: hex(u8.slice(0, 24)), topic: 'cl-' + hex(u8.slice(32, 48)), key, keyB64: b64(keyBytes) };
  }

  /** Dựng lại khóa mã hóa từ chuỗi đã lưu (để máy tính không phải giữ mật khẩu). */
  function keyFrom(keyB64) {
    return subtle.importKey('raw', unb64(keyB64), 'AES-GCM', false, ['encrypt', 'decrypt']);
  }

  /** Mã hóa 1 đối tượng JSON thành chuỗi gọn (an toàn để gửi qua HTTP). */
  async function seal(key, obj) {
    const iv = crypto.getRandomValues(new Uint8Array(12));
    const ct = new Uint8Array(await subtle.encrypt({ name: 'AES-GCM', iv }, key, enc.encode(JSON.stringify(obj))));
    const out = new Uint8Array(12 + ct.length);
    out.set(iv, 0);
    out.set(ct, 12);
    return b64(out);
  }

  /** Giải mã; sai khóa / bị sửa đổi thì trả về null. */
  async function open(key, text) {
    try {
      const u8 = unb64(text);
      const pt = await subtle.decrypt({ name: 'AES-GCM', iv: u8.slice(0, 12) }, key, u8.slice(12));
      return JSON.parse(dec.decode(pt));
    } catch (e) {
      return null;
    }
  }

  return { derive, keyFrom, seal, open, check, normAccount, hex, b64, unb64 };
});
