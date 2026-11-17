# TTube

Bản build cá nhân (tên cũ: MyTube; thư mục, package ID `com.personal.mytube` và tag `mytube-v*` giữ nguyên để cập nhật liền mạch) của ứng dụng Android **YTXTube** (trình xem YouTube / YouTube Music không quảng cáo, Shorts, lời bài hát, tải video, PiP, Android TV).

Dựa trên mã nguồn [Koustubh12345/YTXTube](https://github.com/Koustubh12345/YTXTube) — giấy phép **GPL-3.0** (xem `LICENSE`).

## Khác biệt so với bản gốc

| | YTXTube gốc | TTube |
|---|---|---|
| Tên app | YTXTube | TTube |
| Màn hình mở app | không có | 2 giây: logo T, chữ TTube, tên **Tiền**, thanh load đỏ (`Splash.kt`) |
| Biểu tượng | nút play đỏ | chữ **T** trắng + nút play vàng trên nền đỏ (`docs/mytube-icon.svg`) |
| Package ID | `com.tensei.ytxtube` | `com.personal.mytube` (cài song song được với bản gốc) |
| Khóa ký APK | khóa của tác giả | khóa riêng `app/mytube.keystore` |
| Kiểm tra cập nhật | release của tác giả | release `mytube-v*` trong repo này |
| Mục "Developer" trong Cài đặt | Telegram của tác giả | ghi công tác giả, mở repo gốc |

## Tải APK

Mỗi lần có thay đổi trong thư mục `mytube/`, GitHub Actions (workflow **TTube - Build APK**) tự build và đăng một release có tag `mytube-v2.2.0.<số build>` (đánh dấu *pre-release*, không chiếm vị trí "Latest" của các release khác).

Vào tab **Releases** của repo → chọn release `TTube …` → tải file `TTube-….apk` về điện thoại và cài đặt (cho phép "Cài ứng dụng không rõ nguồn gốc"). Yêu cầu Android 7.0+.

## Cập nhật

Mỗi lần mở app, TTube tự kiểm tra release mới. Nếu có bản mới hơn, app hiện hộp thoại **"Có bản cập nhật mới"** kèm nội dung thay đổi và 3 lựa chọn:

- **Cập nhật**: tải APK về và cài đè, dữ liệu vẫn giữ nguyên.
- **Để sau**: tiếp tục dùng bản cũ, lần mở app sau sẽ nhắc lại.
- **Bỏ qua bản này**: không nhắc lại bản đó nữa, chỉ nhắc khi có bản mới hơn.

Muốn cập nhật thủ công thì vào **Cài đặt → bấm vào dòng Phiên bản**. Cách này vẫn hiện cả bản đã bỏ qua.

## Tự build trên máy

Cần JDK 21 và Android SDK:

```bash
cd mytube
./gradlew :app:assembleRelease
# APK: app/build/outputs/apk/release/app-release.apk
```

## Đổi tên app

- `app/src/main/res/values/strings.xml` → `app_name`
- `app/src/main/java/com/tensei/ytxtube/Screens.kt` → tiêu đề màn hình chính (`title = "TTube"`)

## Ghi chú

Repo này công khai nên khóa ký và mật khẩu mặc định cũng công khai. Nếu muốn an toàn hơn, tạo khóa mới và đặt mật khẩu qua GitHub Secrets `KEYSTORE_PASSWORD`, `KEY_ALIAS`, `KEY_PASSWORD` (cần thêm chúng vào bước build trong workflow).
