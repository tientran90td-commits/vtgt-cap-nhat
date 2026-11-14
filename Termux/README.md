# Phim Việt Studio - bản Termux (Android)

Làm **video review / tóm tắt phim** và **dịch phim nước ngoài sang tiếng Việt** (thuyết minh + Vietsub) ngay trên điện thoại, giao diện là trang web mở trong Chrome.

## Cài (1 lần)

1. Cài **Termux** từ F-Droid hoặc GitHub (bản trên Google Play đã cũ).
2. Mở Termux, dán lệnh:
   ```
   curl -fsSL https://raw.githubusercontent.com/tientran90td-commits/vtgt-cap-nhat/claude/movie-summary-app-0q90dq/Termux/install.sh | bash
   ```
   Bấm **Cho phép** khi Android hỏi quyền bộ nhớ. Cài mất khoảng 5-10 phút.
3. Mỗi lần dùng: mở Termux, gõ `phimviet` → Chrome tự mở giao diện.

## Dùng

| Bước | |
|---|---|
| Video | **Chọn trong máy** (Download, Movies, DCIM, Zalo, Telegram), **Tải lên**, hoặc dán link TikTok / YouTube / Douyin / Bilibili |
| Làm gì | 🎬 **Review / tóm tắt** thành video 1-15 phút · 🌐 **Dịch nguyên video** (thuyết minh + Vietsub / chỉ Vietsub / chỉ thuyết minh) |
| Lời gốc | 🔤 **Đọc phụ đề cứng trên hình** (Tesseract, không cần mạng: bấm 🔍 Tự tìm khung, 🔤 Đọc thử) · 🎧 **Nghe lời thoại** bằng Groq Whisper (miễn phí, cần key) |
| AI | Có key (DeepSeek, Gemini, OpenRouter, Groq, OpenAI) thì tự gọi API. **Không có key**: app soạn sẵn yêu cầu → bấm Chép → Mở DeepSeek → dán → chép câu trả lời → Dán → Dùng |
| Giọng | Microsoft Edge (Hoài My, Nam Minh), miễn phí |
| Kịch bản | Tab ✏️ Kịch bản: sửa tên nhân vật / câu dịch → Lưu & xuất lại |
| Kết quả | Lưu ở **Movies/PhimViet** (hiện trong Thư viện ảnh), xem ngay trong trang |

Nút **🔄 Cập nhật** ở góc trên lấy bản mới nhất (giữ nguyên dữ liệu và video).

## Mã nguồn mở dùng

ffmpeg (x264, libass, chip mã hóa của máy qua MediaCodec) · Tesseract OCR (Apache-2.0) + tessdata_fast · yt-dlp (Unlicense) · edge-tts (LGPL-3.0) · numpy · onnxruntime (MIT, tách nhạc nền UVR MDX-Net nếu máy có) · lõi VietDub (thư mục `../VietDub`).

Máy chủ chỉ nghe ở `127.0.0.1` và chỉ nhận lệnh từ chính trang của app.

## Thử trên máy tính

```
python tests/test_termux.py
```
Chạy máy chủ thật với video phụ đề tiếng Trung: review + dịch (giả lập dán DeepSeek), kiểm tra video ra, giao diện điện thoại (Chromium, ảnh ở `tests/screens/`).
