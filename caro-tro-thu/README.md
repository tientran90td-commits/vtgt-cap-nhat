# Caro Trợ Thủ

> **Bản 2.0:** app có 3 tab — **🎮 Nối game** (nối thẳng vào game Caro LIVE đang chạy: hiện bàn cờ, tên + avatar 2 người chơi, bạn chọn "Tôi là…" rồi tới lượt app tự gợi ý), **⚙ Điều khiển** (bảng điều khiển game ngay trong app) và **✍ Tự nhập** (cách cũ bên dưới).
> Địa chỉ nối: cùng điện thoại (Termux) `127.0.0.1:3000`; máy tính cùng WiFi `192.168.x.x:3000` + mã 6 số (bật "Kết nối qua WiFi" ở bảng điều khiển game); khác WiFi dùng [Tailscale](https://tailscale.com) (miễn phí) rồi nhập địa chỉ `100.x.x.x`.
> App cần quyền INTERNET (chỉ để nối vào game của bạn).

App Android (APK) hỗ trợ chơi cờ caro: bạn nhập nước đi của **đối thủ** (chạm vào bàn cờ), app tự tính và tô sáng ô **bạn** nên đánh.

- Chọn **tôi đi trước** hoặc **đối thủ đi trước**, cỡ bàn (10–20), luật thắng (5 quân liền; hoặc "chặn 2 đầu thì không thắng"), mức nghĩ.
- Chạm ô đối thủ vừa đánh → bấm **Xác nhận** (hoặc chạm lại đúng ô đó) → app hiện **👉 Bạn đánh ô J9**.
- **Gợi ý khác**: xem nước đi thay thế. **Tôi đi ô khác**: nếu bạn đi chỗ khác gợi ý. **Lùi**: sửa khi nhập nhầm.
- Chế độ **Tự nhập** chạy hoàn toàn offline. Chế độ **Nối game** chỉ nói chuyện với game của bạn trong mạng nhà (hoặc Tailscale).

## Tải APK
Vào mục **Releases** của kho này, tải `CaroTroThu.apk` (bản mới nhất), cài trên điện thoại Android.
APK được GitHub tự dựng mỗi khi có thay đổi (xem tab **Actions**).

## Cấu trúc
- `app/src/main/assets/index.html` – giao diện + bộ não (đã gộp 1 file).
- `www/` – mã nguồn gốc: `engine.js` (bộ não), `app.js` (tab Tự nhập), `link.js` (tab Nối game), `tabs.js` (chuyển tab), `style.css`.
- `build/build_html.py` – gộp `www/` thành 1 file `index.html`.
- `test/engine.test.js` – kiểm thử bộ não (`node test/engine.test.js`).
- `.github/workflows/build-apk.yml` – tự dựng APK.

Bộ não: chấm điểm theo các cửa sổ 5 ô, alpha-beta tăng dần độ sâu theo thời gian, tìm chuỗi "liên tiếp tạo 4" (VCF) để thấy sớm đường thắng ép buộc và chặn đường thắng ép buộc của đối thủ. Không có chương trình nào thắng chắc 100%, nhưng bản này mạnh hơn người chơi thông thường.

## Nút Nhây
Khi máy tìm được thế thắng chắc (chuỗi tạo 4 liên tiếp), nút "😜 Nhây" sáng lên. Bấm để đổi gợi ý sang một nước trêu đối thủ
(chặn trước điểm mạnh của họ, hoặc ép họ chặn một nước thừa). Mỗi nước nhây đều được máy kiểm chứng: dù đối thủ đáp thế nào
bạn vẫn thắng. Không có nước nào chắc thắng thì nút tắt. Bấm tiếp để xem nước nhây khác, hết danh sách thì quay về gợi ý gốc.


## Bong bóng nổi (bản 2.1)
Bấm 🫧 "Bong bóng" trong tab Trợ thủ. Lần đầu app mở màn hình cài đặt: bật "Hiển thị trên các ứng dụng khác" cho Caro Trợ Thủ.
Khi bạn chuyển sang TikTok, một nút tròn ♟ nổi trên màn hình; tới lượt bạn thì bật ra tin nhắn "👉 Bạn đánh ô G9" (rung nhẹ).
Kéo nút để đổi chỗ, chạm để mở lại app. Mã: BubbleService.java + cầu nối AndroidBubble trong MainActivity.java.

## Gợi ý không bị dừng khi sang TikTok (bản 2.4)
Khi bong bóng đang bật và app ra nền, WebView được chuyển sang một cửa sổ nổi 1x1 điểm ảnh (vô hình) để Android không làm chậm/đóng băng trang
(trước đây gợi ý chỉ chạy được 2-3 lần rồi dừng). Mở lại app thì WebView về chỗ cũ. Xem MainActivity.moveToOverlay / moveBack.

## Luật "O cấm 1 ô" và luật cấm 3-3 / 4-4 (bản 3.1)
- Khi game bật luật **O cấm 1 ô**, tới lượt bạn (bên O) chọn ô cấm, app hiện **🚫 Bạn CẤM ô …** = ô quân X muốn đi nhất; gõ ô đó vào bình luận, rồi gõ tiếp nước đi của bạn.
- Ô bị cấm vẽ tối trên bàn cờ; app không bao giờ gợi ý đi vào ô cấm (cả 2 bên). Khi game bật luật cấm 3-3/4-4 cho X, app cũng né các ô đó khi gợi ý cho X (ô hiện vòng cấm đỏ).

## Ô cấm là "tường" (bản 3.2)
Bộ não coi ô bị O cấm như một bức tường chặn cả hai bên: dây quân nào đi qua ô cấm là dây chết, app không còn gợi ý chặn 2 đầu một dây đã hết đường 5. Rapfi không biết ô cấm, nên khi bàn có ô cấm app vẫn dùng Rapfi nhưng kiểm tra lại từng gợi ý bằng bộ não nội bộ (hiểu ô cấm): loại gợi ý bỏ lỡ nước thắng/chặn thắng, dựa vào dây đã chết, hoặc để đối thủ ép thắng; khi đó dùng nước của bộ não nội bộ.
