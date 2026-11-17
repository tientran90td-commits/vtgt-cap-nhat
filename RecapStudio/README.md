# 🎬 Recap Studio 2.0

Biến phim dài thành **video tóm tắt ngắn có thuyết minh** (kiểu review phim TikTok / YouTube).

**Bản 2.0 "lai":** mỗi bước tự chọn **chạy trên máy** hay **qua mạng**, cái nào có sẵn và nhanh thì dùng;
lỗi, hết lượt hay mất mạng thì **tự chuyển sang cách kia**. Không có mạng vẫn làm phim được.

## Chế độ chạy (chọn ở góc trên)

| Chế độ | Khi nào dùng |
|---|---|
| ⚡ **Tự động** (mặc định) | Có key + mạng thì dùng AI online (nhanh, viết dài tốt). Không có thì dùng AI trên máy. Online lỗi thì chuyển sang máy, máy lỗi thì chuyển sang online |
| 🔒 **Chỉ trên máy** | Không dùng mạng: Whisper + Ollama + VieNeu |
| 🌐 **Ưu tiên online** | Dùng AI và giọng online trước, máy là dự phòng |

Đèn trạng thái cạnh ô chế độ cho biết **Mạng / AI trên máy / AI online** có dùng được không. Rê chuột vào để xem
thứ tự AI app sẽ dùng.

## Mỗi bước làm gì

| Bước | Trên máy (offline) | Qua mạng (khi có) |
|---|---|---|
| ⬇ Lấy phim | Kéo thả file | **Dán link** YouTube / TikTok / Facebook... (yt-dlp), tự tải kèm phụ đề nếu có |
| 🎧 Lời thoại | Phụ đề có sẵn (.srt, nhúng MKV) → Whisper card đồ họa (whisper.cpp Vulkan, chạy được RX 5700 XT) → Whisper CPU | Groq / OpenAI Whisper (rất nhanh) |
| ✍️ Kịch bản | Ollama (Qwen2.5 7B), tự mở Ollama, tự tải model | Gemini, Claude, ChatGPT, Groq, OpenRouter, DeepSeek |
| 🎙️ Giọng | VieNeu (Ngọc Huyền, Hải Đăng...), Piper, giọng Windows | Edge (miễn phí), OpenAI, ElevenLabs, Gemini |
| 🎬 Dựng | FFmpeg, nhiều đoạn cùng lúc, mã hóa bằng GPU (AMD/NVIDIA/Intel) | |
| 📤 Đăng | Ảnh bìa tự động + tiêu đề / mô tả / hashtag | AI viết tiêu đề hay hơn |

App tự kiểm tra độ dài kịch bản: AI viết thiếu thì tự yêu cầu viết lại cho đủ thời lượng bạn chọn.

## Mới trong 2.0

- **⚡ Chế độ lai** máy ⇄ mạng, tự chuyển khi lỗi (AI, nhận dạng lời thoại, giọng đọc). Giọng dự phòng đọc lại
  **toàn bộ** để giọng đồng đều.
- **⬇ Tải phim từ link** (yt-dlp).
- **🔍 Tự dò Vietsub in sẵn** trong phim và làm mờ đúng chỗ (kiểu che *Tự dò*). Phim không có phụ đề cứng thì
  không che gì.
- **🎯 Khớp điểm chuyển cảnh**: mỗi đoạn bắt đầu đúng lúc chuyển cảnh, không bị lọt nửa giây của cảnh trước.
  Việc dò chạy nền ngay khi mở phim.
- **📱 Khung dọc bám nhân vật** (OpenCV dò mặt người), lia nhẹ theo nhân vật, không giật.
- **🖼️ Ảnh bìa tự động**: chọn khung hình đẹp nhất (nét, đủ sáng, có mặt người), chữ tiêu đề to có viền.
- **📝 Tiêu đề, mô tả, hashtag**, sao chép một chạm (nút **📤 Đăng video**).
- **👁 Xem trước 1 đoạn** (giọng + phụ đề + khung hình như bản thật) và **trình xem phim** ngay trong app. Bấm vào
  dòng kịch bản thì phim nhảy tới đoạn đó.
- **⚡ Mẫu nhanh**: TikTok 1′, Shorts 3′, YouTube 5′, YouTube 10′.
- **🔄 Cập nhật trực tiếp**: bấm nút *Cập nhật* (hoặc app tự báo khi có bản mới). App tải bản mới, chép đè, giữ nguyên
  cài đặt, dự án và model, rồi khởi động lại. Có nút **Quay lại bản trước** trong ⚙️ Cài đặt.
- Giao diện không đơ: mọi việc kiểm tra mạng, Ollama hay bản mới đều chạy nền.

## Cài đặt (Windows)

1. Cài **Python 3.12** từ <https://www.python.org/downloads/>. Nhớ tick ✅ *Add python.exe to PATH*.
2. Bấm đúp **`install.bat`**. Script tự cài thư viện, **Ollama** (AI trên máy) và model AI `qwen2.5:7b` (~4.7 GB).
3. Bấm đúp **`run.bat`** để mở app.

Đang dùng bản 1.x: chỉ cần bấm **🔄 Cập nhật** trong app, hoặc giải nén bản mới đè lên rồi chạy lại `install.bat`.

Muốn nhanh hơn: ⚙️ Cài đặt → dán **API key** (Gemini / Groq có gói miễn phí). Không có key app vẫn chạy trên máy.

## Cách dùng

1. **Kéo thả phim** vào ô ①, hoặc **dán link** rồi bấm *Tải*.
2. Chọn **mẫu nhanh** hoặc tự chỉnh thời lượng, phong cách, giọng, khung hình.
3. Bấm **⚡ LÀM TẤT CẢ → XUẤT VIDEO**. Thanh dưới hiện từng bước và thời gian.
4. Sửa lời trong bảng ③ → **👁 Xem trước đoạn** → **🎬 Xuất video từ kịch bản**. App chỉ dựng lại phần đã đổi.
5. **📤 Đăng video**: lấy ảnh bìa, tiêu đề, hashtag.

Thư mục xuất mặc định chỉ chứa **video thành phẩm**. Dòng lệnh: `python main.py phim.mp4 --minutes 5`.

## Cấu trúc

```
RecapStudio/
├── main.py              # mở giao diện / chạy dòng lệnh
├── recapstudio/
│   ├── hybrid.py        # chế độ lai: kiểm tra mạng / Ollama / key, chuỗi dự phòng máy ⇄ online
│   ├── ai.py            # Ollama + AI online, hủy được, tự chuyển AI khi lỗi
│   ├── transcript.py    # phụ đề, Whisper (card đồ họa / CPU / API)
│   ├── writer.py        # viết kịch bản đúng thời lượng
│   ├── voices.py        # giọng đọc
│   ├── scenes.py        # dò điểm chuyển cảnh
│   ├── hardsub.py       # dò Vietsub in sẵn
│   ├── reframe.py       # khung dọc bám nhân vật
│   ├── render.py        # dựng video song song
│   ├── publish.py       # ảnh bìa, tiêu đề, hashtag
│   ├── download.py      # tải phim từ link (yt-dlp)
│   ├── updater.py       # cập nhật trực tiếp
│   └── project.py       # quy trình & lưu dự án
├── ui/                  # giao diện PySide6
└── tests/test_core.py   # kiểm thử toàn bộ quy trình (không cần mạng)
```

## Mã nguồn mở sử dụng

FFmpeg · yt-dlp · OpenCV · Pillow · faster-whisper · whisper.cpp · Ollama · Qwen2.5 · VieNeu-TTS · Piper · edge-tts ·
gTTS · PySide6.

Chỉ tải và dùng video bạn có quyền sử dụng; hãy tôn trọng bản quyền phim khi đăng.
