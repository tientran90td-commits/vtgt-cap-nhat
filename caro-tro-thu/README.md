# Caro Trợ Thủ

App Android (APK) hỗ trợ chơi cờ caro: bạn nhập nước đi của **đối thủ** (chạm vào bàn cờ), app tự tính và tô sáng ô **bạn** nên đánh.

- Chọn **tôi đi trước** hoặc **đối thủ đi trước**, cỡ bàn (10–20), luật thắng (5 quân liền; hoặc "chặn 2 đầu thì không thắng"), mức nghĩ.
- Chạm ô đối thủ vừa đánh → bấm **Xác nhận** (hoặc chạm lại đúng ô đó) → app hiện **👉 Bạn đánh ô J9**.
- **Gợi ý khác**: xem nước đi thay thế. **Tôi đi ô khác**: nếu bạn đi chỗ khác gợi ý. **Lùi**: sửa khi nhập nhầm.
- Chạy hoàn toàn offline, không cần mạng, không cần quyền gì.

## Tải APK
Vào mục **Releases** của kho này, mở bản `caro-tro-thu-apk`, tải `CaroTroThu.apk`, cài trên điện thoại Android.
Link trực tiếp: https://github.com/tientran90td-commits/vtgt-cap-nhat/releases/download/caro-tro-thu-apk/CaroTroThu.apk
APK được GitHub tự dựng mỗi khi có thay đổi (xem tab **Actions**).

## Cấu trúc
- `app/src/main/assets/index.html` – giao diện + bộ não (đã gộp 1 file).
- `www/` – mã nguồn gốc: `engine.js` (bộ não), `app.js` (giao diện), `style.css`.
- `build/build_html.py` – gộp `www/` thành 1 file `index.html`.
- `test/engine.test.js` – kiểm thử bộ não (`node test/engine.test.js`).
- `.github/workflows/build-apk.yml` – tự dựng APK.

Bộ não: chấm điểm theo các cửa sổ 5 ô, alpha-beta tăng dần độ sâu theo thời gian, tìm chuỗi "liên tiếp tạo 4" (VCF) để thấy sớm đường thắng ép buộc và chặn đường thắng ép buộc của đối thủ. Không có chương trình nào thắng chắc 100%, nhưng bản này mạnh hơn người chơi thông thường.
