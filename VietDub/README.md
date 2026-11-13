# 🌐 VietDub Studio

Dịch video tiếng nước ngoài (Trung, Anh, Hàn, Nhật, Thái...) sang **tiếng Việt chuẩn, tự nhiên**. Ra video có
**thuyết minh / lồng tiếng Việt** và **phụ đề Việt**, đã **xóa phụ đề gốc**.

## Làm được gì

| Bước | Cách làm |
|---|---|
| ⬇ Lấy video | Kéo thả file, hoặc **dán link** YouTube / TikTok / Douyin / Bilibili / Facebook (yt-dlp) |
| 🔲 Phụ đề cứng | **Kéo khung** đúng dòng chữ in sẵn trên video (hoặc để app tự dò), bấm *Đọc thử* để xem app đọc đúng không, rồi **quét cả video** thành lời gốc có thời gian (OCR RapidOCR / PaddleOCR: Trung giản & phồn thể, Anh, Nhật, Hàn, Thái, Nga, Hindi, Ả Rập, Latin). Khung này cũng dùng để xóa phụ đề gốc đúng chỗ |
| 🎧 Lời gốc | Phụ đề có sẵn (file .srt, phụ đề trong MKV, phụ đề tải kèm link) → Whisper bằng card đồ họa / CPU → Groq (online, rất nhanh). Tự lọc câu "ảo" Whisper hay bịa (字幕由..., Thanks for watching...) |
| 🌐 Dịch | AI đọc lướt cả video để lập **bảng tên riêng** (tên Trung → Hán-Việt: 林动 → Lâm Động) và **xưng hô** giữa các nhân vật, rồi dịch từng lô câu theo văn phong bạn chọn. Câu nào bị sót thì app tự dịch lại. Câu nào dài quá thời gian nói thì AI tự rút gọn |
| 🎙️ Thuyết minh | Giọng **VieNeu Ngọc Huyền** (mặc định, chạy trên máy), Hải Đăng..., Edge Hoài My / Nam Minh (miễn phí, cần mạng), Piper, OpenAI, ElevenLabs, Gemini. Mỗi câu đặt đúng lúc nhân vật nói. Câu dài thì đọc nhanh hơn chút (tối đa 1.35 lần), không bao giờ đọc chồng câu |
| 🎵 Tiếng gốc | **AI tách nhạc nền** (model UVR MDX-Net): bỏ hẳn giọng gốc, giữ nhạc nền và tiếng động, nghe như phim lồng tiếng thật. Có card đồ họa thì chạy bằng card (DirectML). Hoặc giữ tiếng gốc nhỏ, tự giảm thêm lúc đang đọc |
| 🧽 Phụ đề gốc | **Xóa thông minh**: tự dò dải phụ đề, dò **lúc nào có chữ** và **chữ rộng tới đâu**, rồi chỉ xóa đúng chỗ đó, đúng lúc đó. Hình được nội suy từ vùng xung quanh nên không để lại dải mờ hay dải đen |
| 💬 Phụ đề Việt | In lên hình, kèm luôn phụ đề bật/tắt được trong file MP4 |
| ✏️ Chỉnh phụ đề trực tiếp | Video chạy, **phụ đề Việt hiện ngay trên hình**. Gõ sửa chữ là thấy liền; chỉnh thời gian bằng nút *= lúc này* hoặc ±0.1 giây; tách, gộp, thêm, xóa câu; dời tất cả phụ đề; đổi cỡ, màu, vị trí chữ. Phím tắt: Space, Ctrl+S, Alt+[ / Alt+], PageUp / PageDown |
| 🎬 Xuất | Giữ khung gốc hoặc 16:9 / 9:16 / 1:1. Không cần vẽ gì lên hình thì **chép thẳng hình gốc**, xuất trong vài giây |
| 📤 Đăng | Ảnh bìa có tiêu đề tiếng Việt, tiêu đề / mô tả / hashtag tiếng Việt |
| 🎬 Dựng tiếp | **OpenCut tiếng Việt** (trình dựng mã nguồn mở kiểu CapCut) mở ngay trong cửa sổ riêng, dòng thời gian đã có sẵn: video đã xóa phụ đề gốc, giọng thuyết minh, phụ đề Việt (chữ sửa được). Cắt ghép, thêm chữ, nhãn dán, hiệu ứng, mặt nạ, khung hình chính... rồi bấm **Xuất video** |

**Chạy cả trên máy lẫn qua mạng** (ô chế độ ở góc trên): ⚡ Tự động · 🔒 Chỉ trên máy · 🌐 Ưu tiên online. Mỗi bước
tự chọn cách đang dùng được; lỗi hay mất mạng thì tự chuyển cách kia.

**🔄 Cập nhật trực tiếp**: bấm nút *Cập nhật* (app cũng tự báo khi có bản mới). Cài đặt, dự án và model được giữ
nguyên. Có nút *Quay lại bản trước* trong ⚙️ Cài đặt.

## Cài đặt (Windows) - tất cả nằm trên ổ chứa app (vd ổ D), không ghi gì vào ổ C

1. Giải nén vào ổ D, ví dụ `D:\VietDub` (ổ còn **ít nhất 5 GB** trống).
2. Bấm đúp **`install.bat`**. **Không cần cài Python trước**: script tải **uv** rồi tự cài Python 3.12 vào
   `D:\VietDub\tools\python`. Thư viện, file tạm và bộ nhớ đệm đều nằm trong `D:\VietDub`.
   Script tự kiểm tra chỗ trống và cảnh báo nếu thư mục app đang ở ổ C.
3. **AI dịch**: cách hay nhất và miễn phí là lấy key **Gemini** tại <https://aistudio.google.com/apikey>, dán vào
   ⚙️ Cài đặt. Muốn dịch không cần mạng thì chọn **Y** khi được hỏi cài Ollama. Ollama sẽ cài vào
   `D:\VietDub\tools\ollama`, model để ở `D:\VietDub\data\ollama-models`.
4. Bấm đúp **`run.bat`**.

| Thứ | Nằm ở |
|---|---|
| Python, uv, Ollama | `D:\VietDub\tools\` |
| Cài đặt, dự án, model (Whisper, giọng Ngọc Huyền, OCR, tách nhạc), file tạm, OpenCut | `D:\VietDub\data\` |
| Video xuất ra / video tải về | `D:\VietDub\Video xuất\`, `D:\VietDub\Video tải về\` |

Đang dùng bản cũ (dữ liệu ở `%APPDATA%\VietDub` trên ổ C): mở bản 1.3 là app **tự chuyển dữ liệu sang ổ D** và xóa
bản cũ ở ổ C để giải phóng chỗ. Chuyển cả thư mục app sang ổ khác: chạy lại `install.bat` ở chỗ mới.

**📦 Thư viện → ⬇ Tải tất cả** (nút ở góc trên): tải về máy 1 lần giọng **VieNeu Ngọc Huyền** (giọng mặc định),
model đọc chữ cho mọi ngôn ngữ, Whisper, model tách nhạc, giọng Piper. Sau đó làm video không cần mạng.

## Cách dùng

1. Kéo thả video hoặc dán link → *Tải*.
2. Chọn **mẫu nhanh**: *Thuyết minh + Vietsub*, *Chỉ Vietsub*, *TikTok dọc* hoặc *Nhanh nhất*.
3. Phim cổ trang thì chọn văn phong *Cổ trang*. Biết tên nhân vật thì ghi vào ô *Tên riêng*, ví dụ `林动 = Lâm Động`.
4. Bấm **⚡ VIỆT HÓA → XUẤT VIDEO**.
5. Muốn sửa câu dịch: sửa thẳng ở cột *Tiếng Việt* → **👁 Xem thử 20 giây** → **🎬 Xuất lại từ bảng dịch**.
   Giọng đã đọc được dùng lại, chỉ câu đã sửa mới đọc lại.

Dòng lệnh: `python main.py video.mp4` hoặc `python main.py https://... --output sub`.

## 🎬 Dựng tiếp trong OpenCut

Bấm **🎬 Dựng tiếp trong OpenCut** (thanh dưới cùng). VietDub chuẩn bị 3 thứ rồi mở OpenCut trong cửa sổ riêng của
Edge / Chrome:

- video đã xóa phụ đề gốc (nếu chọn tách nhạc thì tiếng nền đã bỏ giọng gốc),
- giọng thuyết minh tiếng Việt (1 rãnh âm thanh riêng, chỉnh âm lượng / cắt được),
- phụ đề Việt dạng chữ trên dòng thời gian (sửa chữ, phông, màu, vị trí được).

### Công cụ thêm trong OpenCut (bản VietDub)

**Tab ✨ VietDub AI** (trên cùng thanh bên trái của OpenCut), chạy trên máy nhờ VietDub:

- 🎙️ **Đọc chữ thành giọng**: giọng Ngọc Huyền / Edge / Piper, thêm vào dòng thời gian tại đầu phát.
- 💬 **Tạo phụ đề tiếng Việt** cho video / âm thanh bất kỳ trong dự án: nghe hoặc đọc phụ đề cứng, dịch, rồi tạo
  chữ sửa được.
- 🎙️ **Thuyết minh tiếng Việt** cho một file: giọng đọc khớp thời gian + phụ đề.
- 🎵 **Tách nhạc nền & giọng nói** thành 2 file âm thanh riêng.
- 🧽 **Xóa phụ đề cứng** thông minh.
- 🌐 **Dịch chữ đang chọn** sang tiếng Việt.
- ⬇ **Tải video từ link** vào dự án.

**13 hiệu ứng mới** (tab Hiệu ứng, kéo thả lên dòng thời gian hoặc lên đoạn video, chỉnh được và đặt khung hình chính):
Bộ lọc màu có sẵn (Ấm áp, Lạnh, Điện ảnh xanh-cam, Hoài cổ, Đen trắng, Sepia, Rực rỡ, Phai màu, Đêm, Kẹo ngọt,
Mùa thu, Mờ lì...), Chỉnh màu (sáng, tương phản, bão hòa, phơi sáng, nhiệt độ, xoay màu, vùng sáng/tối, gamma),
Đen trắng & tông màu, Viền tối, Làm nét, Phát sáng, Nhiễu hạt phim, Lệch màu RGB, Mờ chuyển động, Mờ phóng to,
Khảm điểm ảnh, Lật / gương, Hai tông màu.

Đã sửa 2 lỗi có sẵn của OpenCut classic khiến hiệu ứng đặt trên rãnh hiệu ứng không hiện hoặc làm khung xem trước
bị phóng to; ẩn 2 tab "sắp có" (chuyển cảnh, chỉnh màu) và tab âm thanh online.

OpenCut chạy hoàn toàn trên máy: VietDub tự chạy 1 máy chủ web nhỏ ở `127.0.0.1` (không ra mạng), không cần Node.js
hay đăng nhập. Dự án OpenCut được lưu trong cửa sổ đó, lần sau mở lại vẫn còn. Giữ VietDub mở trong lúc dựng.

OpenCut là phần mềm mã nguồn mở của nhóm OpenCut (giấy phép MIT, xem `opencut/LICENSE-OpenCut.txt`). Bản đi kèm là
bản *classic* đã ngừng phát triển; VietDub dịch giao diện sang tiếng Việt, sửa vài lỗi có sẵn, bỏ phần cần máy chủ
online (đăng nhập, góp ý, thư viện âm thanh Freesound). Dựng lại bản này (cần Bun, Rust + wasm32, wasm-bindgen-cli 0.2.116): xem `opencut/build_opencut_vi.py`.

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
│   ├── ocr.py             # quét phụ đề cứng thành chữ (RapidOCR)
│   ├── components.py      # 📦 tải thư viện & model
│   ├── opencut.py         # máy chủ OpenCut trên máy + cầu nối VietDub
│   ├── oc_tools.py        # công cụ AI cho tab VietDub AI trong OpenCut
│   ├── render.py          # xuất video 1 lượt: xóa phụ đề gốc, phụ đề Việt, trộn tiếng
│   ├── transcript.py      # lời gốc: phụ đề / Whisper
│   ├── voices.py          # giọng đọc
│   ├── hybrid.py          # chế độ máy ⇄ mạng
│   ├── ai.py              # AI: Ollama, Gemini, Claude, OpenAI, Groq, DeepSeek, OpenRouter
│   ├── download.py        # tải video từ link
│   ├── publish.py         # ảnh bìa, tiêu đề, hashtag
│   ├── updater.py         # cập nhật trực tiếp
│   └── project.py         # quy trình & lưu dự án
├── opencut/               # OpenCut tiếng Việt: bản dựng sẵn (zip) + script Việt hóa & dựng lại
│   └── wasm/              # hiệu ứng mới (shader WGSL) + bản vá lõi Rust/WebAssembly
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
| [RapidOCR](https://github.com/RapidAI/RapidOCR) + [PaddleOCR](https://github.com/PaddlePaddle/PaddleOCR) | Đọc phụ đề cứng mọi ngôn ngữ |
| [OpenCut](https://github.com/opencut-app/opencut-classic) (MIT) | Trình dựng video, Việt hóa, chạy kèm |
| [PySide6](https://doc.qt.io/qtforpython-6/), [Pillow](https://python-pillow.org) | Giao diện, ảnh bìa |
