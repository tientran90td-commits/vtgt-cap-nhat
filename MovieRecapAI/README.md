# 🎥 Movie Recap AI: tóm tắt phim dài thành video ngắn

Ứng dụng máy tính (Windows/macOS/Linux), giao diện tiếng Việt. App biến một bộ phim 1–3 tiếng thành video
**review/tóm tắt** 1–15 phút: có **giọng thuyết minh AI**, **phụ đề**, **nhạc nền**, xuất khung **ngang (YouTube)**
hoặc **dọc (TikTok/Reels/Shorts)**.

```
Phim dài ──► 🔍 Nhận diện phim ──► ① Nhận dạng lời thoại ──► ② Dò cảnh ──► ③ AI viết kịch bản + chọn cảnh
        (Whisper / phụ đề có sẵn)      (PySceneDetect)       (Gemini, Claude, GPT, Groq, Ollama…)
                                                                        │
     Video ngắn ◄── ⑤ Dựng video (FFmpeg) ◄── ④ Lồng tiếng (12 công cụ, phát âm chuẩn)
     + phụ đề .srt     cắt cảnh, ghép giọng, phụ đề, nhạc nền, logo, khung 16:9 / 9:16 / 1:1
```

## ✨ Tính năng

| Nhóm | Chi tiết |
|---|---|
| **Nguồn phim** | Kéo thả file (MP4, MKV, AVI, MOV, WEBM…) hoặc dán link YouTube/Facebook/TikTok/Bilibili… (yt-dlp, tự tải kèm phụ đề) |
| **Nhận dạng thoại** | Whisper offline (faster-whisper, CPU/GPU), Groq Whisper API, OpenAI Whisper API, file phụ đề .srt/.vtt/.ass, phụ đề nhúng trong MKV/MP4 |
| **AI viết kịch bản** | Google Gemini, Anthropic Claude, OpenAI, Groq, DeepSeek, OpenRouter, xAI Grok, Mistral, Qwen, **Ollama/LM Studio (offline)**, mọi API dạng OpenAI-compatible, hoặc chế độ **không dùng AI** |
| **Kiểu video** | Thuyết minh AI · Cắt highlight giữ thoại gốc · Kết hợp (thuyết minh + câu thoại đắt giá) |
| **Phong cách** | Review TikTok kịch tính, tóm tắt nghiêm túc, hài hước, cảm xúc, kinh dị, phân tích ý nghĩa, thiếu nhi + yêu cầu riêng |
| **Giọng đọc** | ⭐ VieNeu-TTS (giọng Việt AI offline), Edge TTS (400+ giọng miễn phí, có Hoài My/Nam Minh), gTTS, OpenAI TTS (có chỉnh cảm xúc), ElevenLabs, Gemini TTS (30 giọng), Google Cloud TTS, Azure (500+ giọng, nhiều phong cách), FPT.AI (giọng Việt Bắc/Trung/Nam), **Piper offline**, giọng Windows (SAPI), **XTTS-v2 / viXTTS nhân bản giọng** |
| **Tinh chỉnh giọng** | Tốc độ, cao độ (nửa cung), âm lượng, cảm xúc/phong cách, nghe thử ngay |
| **🎭 Cách đọc** | Tự nhiên, hài hước, hoạt ngôn, nghiêm túc/tin tức, kịch tính, kinh dị, buồn, sôi nổi, ấm áp, gay gắt, thiếu nhi hoặc tự mô tả · AI gán cách đọc **riêng cho từng đoạn** theo cảm xúc cảnh (sửa được trong bảng kịch bản) · OpenAI/Gemini/Azure/ElevenLabs đọc theo cảm xúc thật, các công cụ khác được chỉnh nhịp & cao độ cho hợp |
| **🔍 Nhận diện phim** | AI nhận ra phim từ tên file + 7 khung hình + lời thoại (tên phim, năm, nhân vật, nội dung) · đối chiếu **TMDB** (tùy chọn) để lấy tên nhân vật chuẩn · gợi ý tên riêng cho Whisper nghe đúng · **AI xem hình ảnh** các cảnh để chọn clip chính xác · bạn sửa/bổ sung được |
| **⚡ Mở là dùng ngay** | Màn hình khởi động · mở app là tự chạy nền: cài phần còn thiếu, tải model nhận dạng thoại, nạp sẵn model giọng đọc vào RAM, chọn model AI mới nhất, dò GPU (AMD AMF / NVIDIA / Intel) - không khóa giao diện, tiến độ hiện ở góc dưới · bật/tắt ở mục Cài đặt |
| **🧩 Tự cài đặt** | Tự kiểm tra & tải những gì còn thiếu: thư viện, FFmpeg bản đầy đủ, model Whisper, model VieNeu, giọng Piper tiếng Việt · nút **🩺 Chẩn đoán giọng đọc** & **🔔 Thử loa** · file log để gửi khi gặp lỗi |
| **🗣️ Phát âm chuẩn** | ⭐ **VieNeu-TTS**: AI giọng Việt offline, 25 giọng 3 miền, nhân bản giọng từ mẫu 3–8 giây · tự đọc đúng số, số thập phân, %, tiền tệ, ngày tháng, giờ, khoảng, tỷ số, đơn vị, số La Mã, chữ viết tắt · **từ điển phát âm** do bạn định nghĩa · **AI soát phát âm** (viết lại câu cho dễ đọc, phiên âm tên nước ngoài) · phụ đề vẫn giữ chữ gốc |
| **Biên tập** | Bảng kịch bản sửa trực tiếp: lời thuyết minh, mốc thời gian, thêm/xóa/đổi thứ tự, xem trước cảnh, nghe thử từng đoạn, lưu/mở kịch bản JSON |
| **Dựng video** | 16:9 / 9:16 / 1:1 / 4:5, nền mờ hoặc cắt cúp, 720p–4K, phụ đề tùy chỉnh (font, màu, viền, vị trí), tiêu đề mở đầu, logo, nhạc nền, giảm tiếng phim khi thuyết minh, GPU NVENC/QuickSync/AMF |
| **Tốc độ** | Lưu tạm mọi bước: sửa 1 đoạn rồi xuất lại thì chỉ dựng lại đoạn đó |

## 🚀 Cài đặt (Windows)

1. Cài **Python 3.10–3.12** từ <https://www.python.org/downloads/>. Khi cài nhớ tick ✅ *Add python.exe to PATH*.
2. Tải thư mục `MovieRecapAI` về máy, bấm đúp **`install.bat`**. Script tự tạo môi trường, cài thư viện, Piper và FFmpeg (qua winget).
3. Bấm đúp **`run.bat`** để mở app. Lần đầu mở, app sẽ hỏi để **tự tải những thứ còn thiếu** (hoặc vào mục **🧩 Thành phần & sửa lỗi**, bấm *Cài tất cả còn thiếu*).
4. Không nghe được giọng đọc: vào **🧩 Thành phần & sửa lỗi**, bấm **🔔 Thử loa** rồi **🩺 Chẩn đoán giọng đọc**. App tự sửa những lỗi thường gặp. File log nằm ở `%APPDATA%\MovieRecapAI\logs\app.log`.

> Linux/macOS: `./run.sh` (cần `ffmpeg` có sẵn: `sudo apt install ffmpeg` / `brew install ffmpeg`).
>
> Muốn đóng gói thành file `.exe` gửi người khác: chạy `build_exe.bat`, kết quả nằm ở `dist\MovieRecapAI\`.

## 💻 Gợi ý theo cấu hình máy

| Máy | Nhận dạng thoại | Giọng đọc | Xuất video |
|---|---|---|---|
| **Card AMD (vd RX 5700 XT) / Intel, CPU 12 luồng (vd i5-12400F), RAM 16GB** | Whisper *Tự chọn* (large-v3-turbo chạy CPU, phim 2 tiếng mất khoảng 40-70 phút) hoặc **Groq Whisper API** (miễn phí, vài phút) | VieNeu-TTS v3turbo (CPU) hoặc Edge TTS | Bộ mã hóa *Tự động* → **AMD AMF** |
| Card NVIDIA | Whisper large-v3-turbo trên GPU (rất nhanh) | VieNeu-TTS / XTTS dùng GPU | NVENC |
| Máy yếu / laptop cũ | Groq Whisper API hoặc model `small` | Edge TTS hoặc VieNeu v3nano | CPU |

Card AMD không dùng được CUDA, nên Whisper và VieNeu sẽ chạy bằng CPU (vẫn ổn với CPU 12 luồng). XTTS và Ollama không nên dùng trên card AMD.

## 🔑 Nhập API (mục *API & Cài đặt* trong app)

Không cần nhập hết, chỉ cần dịch vụ bạn dùng. Bấm **Kiểm tra** cạnh mỗi ô để thử kết nối.

| Dịch vụ | Dùng cho | Lấy key | Ghi chú |
|---|---|---|---|
| **Google Gemini** ⭐ | Viết kịch bản, Gemini TTS | <https://aistudio.google.com/apikey> | **Có gói miễn phí**, ngữ cảnh 1 triệu token, rất hợp phim dài |
| Anthropic Claude | Viết kịch bản | <https://console.anthropic.com/settings/keys> | Mặc định `claude-opus-5-5`, viết tự nhiên |
| OpenAI | Kịch bản, OpenAI TTS, Whisper API | <https://platform.openai.com/api-keys> | Đổi Base URL được (Azure OpenAI, proxy…) |
| Groq | Kịch bản (Llama, Qwen…), **Groq Whisper** | <https://console.groq.com/keys> | Miễn phí có giới hạn, rất nhanh |
| DeepSeek / OpenRouter / xAI / Mistral / Qwen | Viết kịch bản | xem nút *Lấy key* trong app | |
| Ollama / LM Studio | Viết kịch bản **offline** | <https://ollama.com> | Không cần key, ví dụ `ollama pull qwen2.5:14b` |
| ElevenLabs | Giọng siêu thật, giọng nhân bản | <https://elevenlabs.io/app/settings/api-keys> | |
| Google Cloud TTS | Giọng WaveNet/Neural2/Chirp | <https://console.cloud.google.com/apis/credentials> | Bật *Cloud Text-to-Speech API* |
| TMDB (tùy chọn) | Nhận diện phim, tên nhân vật chuẩn | <https://www.themoviedb.org/settings/api> | Miễn phí |
| Azure Speech | 500+ giọng, có cảm xúc | Azure Portal → Speech service | Nhập cả **vùng** (vd `southeastasia`) |
| FPT.AI | Giọng Việt 3 miền | <https://console.fpt.ai> | |

Key chỉ lưu trên máy bạn: `%APPDATA%\MovieRecapAI\settings.json` (Windows).

**Không muốn dùng API key?** Chọn nhà cung cấp **🌐 Dùng bản WEB** ở Bước 2. App copy sẵn câu lệnh và mở trang ChatGPT / Gemini / **Google AI Studio** / Claude / DeepSeek / Grok / Copilot, bạn dán vào rồi dán câu trả lời ngược lại vào app (thường 1 lần cho mỗi video, phim rất dài thì vài lần). App không tự đăng nhập hay điều khiển trang web vì làm vậy vi phạm điều khoản của các dịch vụ và dễ bị khóa tài khoản. Nên dùng **Google AI Studio**: miễn phí và đọc được lời thoại cả bộ phim trong 1 lần.

**AI báo lỗi 429 / hết tiền?** App phân biệt: *hết tiền/hết lượt trong ngày* (báo rõ cách khắc phục, không thử lại vô ích), *quá tải tạm thời* (đợi đúng thời gian nhà cung cấp yêu cầu), *yêu cầu quá dài* (tự chia nhỏ lời thoại). Nếu bạn đã nhập key của nhiều AI, app **tự chuyển sang AI khác** khi AI đang dùng hết tiền hoặc quá tải. Lưu ý: gói ChatGPT Plus **không** bao gồm API, API OpenAI phải nạp tiền riêng.

**Bộ miễn phí 100%:** Whisper offline + Gemini (free) + Edge TTS. Hoặc **offline hoàn toàn:** Whisper + Ollama + Piper.

## 🎬 Cách dùng

1. **Video nguồn**: kéo thả phim hoặc dán link, rồi bấm **Tải về**.
2. Bấm **⚡ TỰ ĐỘNG LÀM TẤT CẢ** để app chạy hết các bước và xuất video. Muốn tự tay chỉnh thì làm lần lượt:
3. **Kịch bản AI**: ① *Nhận dạng thoại* → ② *AI viết kịch bản*. Sau đó sửa trong bảng (để trống lời thuyết minh nghĩa là giữ âm thanh gốc của cảnh đó). Nhấp đúp mốc thời gian để xem cảnh.
4. **Giọng đọc**: lọc theo ngôn ngữ và giới tính, chọn giọng, chỉnh tốc độ/cao độ, bấm *Nghe thử*.
5. **Xuất video**: chọn mẫu *TikTok* hoặc *YouTube*, phụ đề, nhạc nền, logo, rồi bấm **🚀 XUẤT VIDEO**.
   App xuất kèm file `.srt` (phụ đề) và `.txt` (kịch bản + mô tả để đăng).

### Chạy dòng lệnh (không giao diện)

```bash
python main.py --cli "phim.mkv" --minutes 8 --provider gemini --voice vi-VN-NamMinhNeural --aspect 9:16
python main.py --cli "https://www.youtube.com/watch?v=..." --subtitle phim.srt -o recap.mp4
```

## 💡 Mẹo

- Phim có sẵn phụ đề `.srt` cùng tên thì app tự nhận ra. Dùng phụ đề nhanh và chuẩn hơn nhận dạng giọng nói.
- Máy có GPU NVIDIA: Whisper `large-v3` cho độ chính xác cao nhất, bộ mã hóa `NVENC` cho tốc độ xuất nhanh (bấm *Kiểm tra GPU*).
- Phim rất dài mà dùng model ngữ cảnh nhỏ (Groq, Ollama): app tự tóm tắt từng phần trước rồi mới viết kịch bản.
- **Phát âm chuẩn nhất cho tiếng Việt:** chọn engine *⭐ VieNeu-TTS* (đã cài sẵn qua `install.bat`, lần đầu tự tải model), bật *Phát âm chuẩn*, bấm *🔎 Xem cách đọc* để xem câu sẽ được đọc ra sao. Tên riêng hay bị đọc sai thì thêm vào *📖 Từ điển phát âm* (vd `Thanos → Tha-nốt`). Nếu muốn kỹ hơn, bật *AI soát phát âm*.
- **Tất cả giọng Piper offline:** engine *Piper* → *🔌 Kho giọng Piper*: tải **tất cả giọng chính thức** (hơn 100 giọng, khoảng chục GB) hoặc *Tất cả giọng tiếng Việt*; tải giọng cộng đồng từ **bất kỳ repo HuggingFace** nào; **nhập file** `.onnx` + `.onnx.json`; **đặt tên** cho giọng (vd "Ngọc Huyền - nữ hoạt ngôn"). Cách đọc (hoạt ngôn, nghiêm túc...) chỉnh cả độ biểu cảm của Piper.
- **⭐ Giọng gợi ý:** chọn nhanh ở đầu trang Giọng đọc, vd *Ngọc Huyền · nữ hoạt ngôn* (VieNeu, offline).
- Giọng Piper tiếng Việt: vào *Giọng đọc* → engine *Piper* → *Tải thêm giọng Piper* → lọc `vi_`.
- Nhân bản giọng tiếng Việt: `pip install coqui-tts`, tải model **viXTTS** (<https://huggingface.co/capleaf/viXTTS>), rồi chọn engine *XTTS*, giọng *Nhân bản*, file mẫu và thư mục model.

## 🧩 Mã nguồn mở được tích hợp

| Dự án | Giấy phép | Vai trò |
|---|---|---|
| [FFmpeg](https://github.com/FFmpeg/FFmpeg) + [libass](https://github.com/libass/libass) | LGPL/GPL, ISC | Cắt ghép, mã hóa, trộn âm thanh, vẽ phụ đề |
| [faster-whisper](https://github.com/SYSTRAN/faster-whisper) / [OpenAI Whisper](https://github.com/openai/whisper) / [CTranslate2](https://github.com/OpenNMT/CTranslate2) | MIT | Nhận dạng lời thoại offline |
| [PySceneDetect](https://github.com/Breakthrough/PySceneDetect) + [OpenCV](https://github.com/opencv/opencv) | BSD-3, Apache-2.0 | Dò chuyển cảnh |
| [yt-dlp](https://github.com/yt-dlp/yt-dlp) | Unlicense | Tải phim + phụ đề từ link |
| [VieNeu-TTS](https://github.com/pnnbao97/VieNeu-TTS) | Apache-2.0 | AI giọng Việt phát âm chuẩn, nhân bản giọng |
| [num2words](https://github.com/savoirfairelinux/num2words) | LGPL-2.1 | Đọc số thành chữ cho ngôn ngữ khác |
| [edge-tts](https://github.com/rany2/edge-tts) | LGPL-3.0 | 400+ giọng Microsoft miễn phí |
| [gTTS](https://github.com/pndurette/gTTS) | MIT | Giọng Google Translate |
| [Piper](https://github.com/rhasspy/piper) + [piper-voices](https://huggingface.co/rhasspy/piper-voices) | MIT/GPL | Giọng neural offline |
| [Coqui TTS (XTTS-v2)](https://github.com/idiap/coqui-ai-TTS) / [viXTTS](https://huggingface.co/capleaf/viXTTS) | MPL-2.0 / CPML | Nhân bản giọng nói |
| [pyttsx3](https://github.com/nateshmbhat/pyttsx3) | MPL-2.0 | Giọng có sẵn của hệ điều hành |
| [PySide6 (Qt)](https://wiki.qt.io/Qt_for_Python) | LGPL-3.0 | Giao diện |
| [anthropic-sdk-python](https://github.com/anthropics/anthropic-sdk-python), [requests](https://github.com/psf/requests) | MIT, Apache-2.0 | Kết nối AI |
| [imageio-ffmpeg](https://github.com/imageio/imageio-ffmpeg) | BSD-2 | FFmpeg dự phòng |
| [Ollama](https://github.com/ollama/ollama) | MIT | Chạy LLM offline |

## 🗂️ Cấu trúc mã nguồn

```
MovieRecapAI/
├── main.py                 # khởi động GUI / CLI
├── recap/                  # lõi xử lý (không phụ thuộc giao diện)
│   ├── config.py           # cấu hình + API key
│   ├── ffmpeg_utils.py     # tìm/chạy FFmpeg, đọc thông tin media
│   ├── transcribe.py       # nhận dạng lời thoại
│   ├── scenes.py           # dò chuyển cảnh
│   ├── llm.py              # kết nối các AI
│   ├── script_writer.py    # prompt + xử lý kịch bản
│   ├── tts.py              # 12 công cụ giọng đọc
│   ├── textnorm.py         # phát âm chuẩn: đọc số/ngày/đơn vị, từ điển, AI soát phát âm
│   ├── film_id.py          # nhận diện phim, TMDB, AI xem hình ảnh cảnh phim
│   ├── components.py       # tự kiểm tra & cài thư viện, FFmpeg, model
│   ├── subtitles.py        # đọc/ghi SRT, ASS
│   ├── editor.py           # dựng video
│   └── pipeline.py         # quản lý dự án, chuỗi xử lý, tải video
├── gui/                    # giao diện PySide6
└── tests/test_pipeline.py  # kiểm thử end-to-end offline
```

Chạy kiểm thử: `python tests/test_pipeline.py`, `python tests/test_textnorm.py`, `python tests/test_features.py`, `python tests/test_piper.py`. Bài kiểm thử tạo phim giả lập, giả lập AI và giọng đọc, rồi dựng ra video 16:9, 9:16 và highlight.

## ⚖️ Lưu ý bản quyền

Chỉ dùng app với phim bạn có quyền sử dụng: phim của bạn, phim được cấp phép, nội dung public domain, hoặc trong
phạm vi *sử dụng hợp lý* theo luật nơi bạn sinh sống. Bạn tự chịu trách nhiệm về nội dung mình đăng tải và về việc tuân
thủ điều khoản của từng dịch vụ AI.
