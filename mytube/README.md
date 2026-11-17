# MyTube

Bản build cá nhân của ứng dụng Android **YTXTube** (trình xem YouTube / YouTube Music không quảng cáo, Shorts, lời bài hát, tải video, PiP, Android TV).

Dựa trên mã nguồn [Koustubh12345/YTXTube](https://github.com/Koustubh12345/YTXTube) — giấy phép **GPL-3.0** (xem `LICENSE`).

## Khác biệt so với bản gốc

| | YTXTube gốc | MyTube |
|---|---|---|
| Tên app | YTXTube | MyTube |
| Package ID | `com.tensei.ytxtube` | `com.personal.mytube` (cài song song được với bản gốc) |
| Khóa ký APK | khóa của tác giả | khóa riêng `app/mytube.keystore` |
| Kiểm tra cập nhật | release của tác giả | release `mytube-v*` trong repo này |
| Mục "Developer" trong Cài đặt | Telegram của tác giả | ghi công tác giả, mở repo gốc |

## Tải APK

Mỗi lần có thay đổi trong thư mục `mytube/`, GitHub Actions (workflow **MyTube - Build APK**) tự build và đăng một release có tag `mytube-v2.2.0.<số build>` (đánh dấu *pre-release*, không chiếm vị trí "Latest" của các release khác).

Vào tab **Releases** của repo → chọn release `MyTube …` → tải file `MyTube-….apk` về điện thoại và cài đặt (cho phép "Cài ứng dụng không rõ nguồn gốc"). Yêu cầu Android 7.0+.

Lần sau app tự báo khi có bản build mới hơn (Cài đặt → kiểm tra cập nhật).

## Tự build trên máy

Cần JDK 21 và Android SDK:

```bash
cd mytube
./gradlew :app:assembleRelease
# APK: app/build/outputs/apk/release/app-release.apk
```

## Đổi tên app

- `app/src/main/res/values/strings.xml` → `app_name`
- `app/src/main/java/com/tensei/ytxtube/Screens.kt` → tiêu đề màn hình chính (`title = "MyTube"`)

## Ghi chú

Repo này công khai nên khóa ký và mật khẩu mặc định cũng công khai. Nếu muốn an toàn hơn, tạo khóa mới và đặt mật khẩu qua GitHub Secrets `KEYSTORE_PASSWORD`, `KEY_ALIAS`, `KEY_PASSWORD` (cần thêm chúng vào bước build trong workflow).
