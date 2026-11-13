# 🌐 VietDub Studio

Dịch video tiếng nước ngoài (Trung, Anh, Hàn, Nhật, Thái...) sang **tiếng Việt chuẩn, tự nhiên**. Ra video có
**thuyết minh / lồng tiếng Việt** và **phụ đề Việt**, đã **xóa phụ đề gốc**.

## Làm được gì

| Bước | Cách làm |
|---|---|
| ⬇ Lấy video | Kéo thả file, hoặc **dán link** YouTube / TikTok / Douyin / Bilibili / Facebook (yt-dlp) |
| 🎧 Lời gốc | Phụ đề có sẵn (file .srt, phụ đề trong MKV, phụ đề tải kèm link) → Whisper bằng card đồ họa / CPU → Groq (online, rất nhanh). Tự lọc câu "ảo" Whisper hay bịa (字幕由..., Thanks for watching...) |
| 🌐 Dịch | AI đọc lướt cả video để lập **bảng tên riêng** (tên Trung → Hán-Việt: 林动 → Lâm Động) và **xưng hô** giữa các nhân vật, rồi dịch từng lô câu theo văn phong bạn chọn. Câu nào bị sót thì app tự dịch lại. Câu nào dài quá thời gian nói thì AI tự rút gọn |
| 🎙️ Thuyết minh | Giọng Edge (Hoài My, Nam Minh: miễn phí), Piper (trên máy), VieNeu (cài thêm), OpenAI, ElevenLabs, Gemini. Mỗi câu đặt đúng lúc nhân vật nói. Câu dài thì đọc nhanh hơn chút (tối đa 1.35 lần), không bao giờ đọc chồng câu |
| 🎵 Tiếng gốc | **AI tách nhạc nền** (model UVR MDX-Net): bỏ hẳn giọng gốc, giữ nhạc nền và tiếng động, nghe như phim lồng tiếng thật. Có card đồ họa thì chạy bằng card (DirectML). Hoặc giữ tiếng gốc nhỏ, tự giảm thêm lúc đang đọc |
| 🧽 Phụ đề gốc | **Xóa thông minh**: tự dò dải phụ đề, dò **lúc nào có chữ** và **chữ rộng tới đâu**, rồi chỉ xóa đúng chỗ đó, đúng lúc đó. Hình được nội suy từ vùng xung quanh nên không để lại dải mờ hay dải đen |
| 💬 Phụ đề Việt | In lên hình, kèm luôn phụ đề bật/tắt được trong file MP4 |
| 🎬 Xuất | Giữ khung gốc hoặc 16:9 / 9:16 / 1:1. Không cần vẽ gì lên hình thì **chép thẳng hình gốc**, xuất trong vài giây |
| 📤 Đăng | Ảnh bìa có tiêu đề tiếng Việt, tiêu đề / mô tả / hashtag tiếng Việt |

**Chạy cả trên máy lẫn qua mạng** (ô chế độ ở góc trên): ⚡ Tự động · 🔒 Chỉ trên máy · 🌐 Ưu tiên online. Mỗi bước
tự chọn cách đang dùng được; lỗi hay mất mạng thì tự chuyển cách kia.

**🔄 Cập nhật trực tiếp**: bấm nút *Cập nhật* (app cũng tự báo khi có bản mới). Cài đặt, dự án và model được giữ
nguyên. Có nút *Quay lại bản trước* trong ⚙️ Cài đặt.

## Cài đặt (Windows)

1. Cài **Python 3.12** từ <https://www.python.org/downloads/>. Nhớ tick ✅ *Add python.exe to PATH*.
2. Giải nén vào ổ còn **ít nhất 3 GB trống**, ví dụ `D:\VietDub`.
3. Bấm đúp **`install.bat`**. Script tự kiểm tra chỗ trống; pip để file tạm trên cùng ổ với app và không lưu cache,
   nên không làm đầy ổ C.
4. **AI dịch**: cách hay nhất và miễn phí là lấy key **Gemini** tại <https://aistudio.google.com/apikey>, rồi dán vào
   ⚙️ Cài đặt. Muốn dịch không cần mạng thì chọn **Y** khi `install.bat` hỏi cài Ollama (~5 GB, cần 8 GB RAM).
5. Bấm đúp **`run.bat`**.

Giọng **VieNeu** (Ngọc Huyền, Hải Đăng...) nặng ~3 GB nên cài riêng bằng **`install_vieneu.bat`** khi cần.

## Cách dùng

1. Kéo thả video hoặc dán link → *Tải*.
2. Chọn **mẫu nhanh**: *Thuyết minh + Vietsub*, *Chỉ Vietsub*, *TikTok dọc* hoặc *Nhanh nhất*.
3. Phim cổ trang thì chọn văn phong *Cổ trang*. Biết tên nhân vật thì ghi vào ô *Tên riêng*, ví dụ `林动 = Lâm Động`.
4. Bấm **⚡ VIỆT HÓA → XUẤT VIDEO**.
5. Muốn sửa câu dịch: sửa thẳng ở cột *Tiếng Việt* → **👁 Xem thử 20 giây** → **🎬 Xuất lại từ bảng dịch**.
   Giọng đã đọc được dùng lại, chỉ câu đã sửa mới đọc lại.

Dòng lệnh: `python main.py video.mp4` hoặc `python main.py https://... --output sub`.

## Ổ đầy (No space left on device)

- Dọn Thùng rác, chạy *Disk Cleanup* cho ổ C.
- Xóa cache pip cũ: `%LOCALAPPDATA%\pip\cache`.
- Dự án cũ (giọng đã đọc, file tạm) nằm ở `%APPDATA%\VietDub\projects`, xóa thoải mái.

## Cấu trúc

```
VietDub/
├── main.py                # giao diện / dòng lệnh
├── vietdub/
│   ├── translate.py       # dịch: bảng tên riêng & xưng hô, dịch theo lô, dịch lại câu sót, rút gọn câu dài
│   ├── dub.py             # ghép thuyết minh khớp thời gian
│   ├── separate.py        # AI tách nhạc nền khỏi giọng (UVR MDX-Net qua onnxruntime)
│   ├── hardsub.py         # dò phụ đề gốc: vị trí, lúc xuất hiện, bề rộng
│   ├── render.py          # xuất video 1 lượt: xóa phụ đề gốc, phụ đề Việt, trộn tiếng
│   ├── transcript.py      # lời gốc: phụ đề / Whisper
│   ├── voices.py          # giọng đọc
│   ├── hybrid.py          # chế độ máy ⇄ mạng
│   ├── ai.py              # AI: Ollama, Gemini, Claude, OpenAI, Groq, DeepSeek, OpenRouter
│   ├── download.py        # tải video từ link
│   ├── publish.py         # ảnh bìa, tiêu đề, hashtag
│   ├── updater.py         # cập nhật trực tiếp
│   └── project.py         # quy trình & lưu dự án
├── ui/                    # giao diện PySide6
└── tests/test_core.py     # kiểm thử toàn bộ quy trình (không cần mạng)
```

## Bản quyền

Chỉ dịch và đăng lại video bạn có quyền sử dụng: video của bạn, được chủ kênh cho phép, hoặc giấy phép cho phép.
Giữ ghi công kênh gốc trong phần mô tả. Đăng lại video của người khác khi chưa được phép có thể bị nền tảng gỡ hoặc
khóa kênh.

## Mã nguồn mở tích hợp

| Dự án | Dùng để |
|---|---|
| [FFmpeg](https://ffmpeg.org) | Xử lý hình & tiếng, xóa phụ đề gốc (bộ lọc delogo), in phụ đề, trộn tiếng |
| [yt-dlp](https://github.com/yt-dlp/yt-dlp) | Tải video từ hơn 1000 trang |
| [faster-whisper](https://github.com/SYSTRAN/faster-whisper), [whisper.cpp](https://github.com/ggml-org/whisper.cpp) | Nghe lời gốc (CPU / card đồ họa Vulkan) |
| [UVR MDX-Net](https://github.com/Anjok07/ultimatevocalremovergui), [python-audio-separator](https://github.com/nomadkaraoke/python-audio-separator) | Model & thuật toán tách nhạc nền (viết lại gọn bằng numpy + [onnxruntime](https://onnxruntime.ai)) |
| [Ollama](https://ollama.com) + Qwen2.5 | AI dịch chạy trên máy |
| [edge-tts](https://github.com/rany2/edge-tts), [Piper](https://github.com/rhasspy/piper), [VieNeu-TTS](https://github.com/pnnbao97/VieNeu-TTS) | Giọng thuyết minh |
| [PySide6](https://doc.qt.io/qtforpython-6/), [Pillow](https://python-pillow.org) | Giao diện, ảnh bìa |
