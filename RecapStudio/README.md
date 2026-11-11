# 🎬 Recap Studio

Biến phim dài thành **video tóm tắt ngắn có thuyết minh** (kiểu review phim TikTok / YouTube),
**chạy hoàn toàn trên máy tính của bạn**: không cần API key, không tốn tiền, không lỗi do mạng hay hết lượt.

## Chạy trên máy như thế nào

| Bước | Công cụ (offline, miễn phí, mã nguồn mở) |
|---|---|
| 🎧 Lời thoại | Phụ đề có sẵn (.srt cạnh phim, phụ đề nhúng trong MKV) → **Whisper bằng card đồ họa** (whisper.cpp Vulkan: chạy được cả card AMD như RX 5700 XT) → Whisper CPU (faster-whisper) |
| ✍️ Kịch bản | **Ollama** – AI chạy trên máy (mặc định Qwen2.5 7B, tiếng Việt tốt). App tự kiểm tra độ dài: viết thiếu thì tự yêu cầu viết lại cho đủ thời lượng |
| 🎙️ Giọng đọc | **VieNeu** (giọng Việt AI: Ngọc Huyền, Hải Đăng, Trúc Ly...), **Piper**, giọng có sẵn của Windows |
| 🎬 Dựng video | FFmpeg: 16:9 / 9:16 / 1:1, nền mờ, phụ đề thuyết minh, **che phụ đề gốc** (làm mờ / phóng to / dải đen), nhạc nền, cân bằng âm lượng, **dựng nhiều đoạn cùng lúc**, mã hóa bằng GPU (AMD/NVIDIA/Intel) |

Muốn dùng thêm AI/giọng online (Gemini, Claude, ChatGPT, Groq, ElevenLabs, Edge...): ⚙️ Cài đặt → bỏ tick
**Chỉ dùng trên máy**, rồi nhập API key.

## Cài đặt (Windows)

1. Cài **Python 3.12** từ <https://www.python.org/downloads/> – nhớ tick ✅ *Add python.exe to PATH*.
2. Bấm đúp **`install.bat`**. Script tự cài thư viện, **Ollama** (AI trên máy) và tải model AI `qwen2.5:7b` (~4.7 GB).
3. Bấm đúp **`run.bat`** để mở app.

Lần đầu dùng, app tự tải thêm (một lần, cần mạng): model Whisper, chương trình Whisper card đồ họa, model giọng VieNeu.
Sau đó làm phim không cần mạng.

> Máy yếu / ít RAM: ⚙️ Cài đặt → Model AI chọn **Qwen2.5 3B** rồi bấm *Tải model AI*.

## Cách dùng

1. **Kéo thả phim** vào ô ① (có file phụ đề .srt cùng tên thì app dùng luôn – nhanh và chính xác nhất).
2. Ở ②: chọn **thời lượng** (1′ / 3′ / 5′ / 10′), phong cách, giọng đọc, khung hình.
3. Bấm **⚡ LÀM TẤT CẢ → XUẤT VIDEO**. Thanh dưới cùng hiện từng bước và thời gian.
4. Muốn sửa lời: sửa thẳng trong bảng ③ rồi bấm **🎬 Xuất video từ kịch bản** (chỉ dựng lại phần đã đổi).

Thư mục xuất chỉ chứa **video thành phẩm**. Dòng lệnh: `python main.py phim.mp4 --minutes 5`.

## Cấu trúc

```
RecapStudio/
├── main.py              # mở giao diện / chạy dòng lệnh
├── recapstudio/         # lõi xử lý
│   ├── config.py        # cài đặt (%APPDATA%/RecapStudio)
│   ├── media.py         # FFmpeg, bộ mã hóa GPU
│   ├── transcript.py    # phụ đề, Whisper (card đồ họa / CPU / API)
│   ├── ai.py            # Ollama (offline) + AI online; hủy được, tự chuyển AI khi lỗi
│   ├── writer.py        # viết kịch bản đúng thời lượng
│   ├── voices.py        # giọng đọc (VieNeu, Piper, Windows, Edge, OpenAI, ElevenLabs, Gemini)
│   ├── render.py        # dựng video song song
│   └── project.py       # quy trình & lưu dự án
├── ui/                  # giao diện PySide6
└── tests/test_core.py   # kiểm thử offline toàn bộ quy trình
```

## Mã nguồn mở sử dụng

FFmpeg · faster-whisper · whisper.cpp · Ollama · Qwen2.5 · VieNeu-TTS · Piper · edge-tts · gTTS · PySide6.
Hãy tôn trọng bản quyền phim khi đăng video.
