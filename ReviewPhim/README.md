# ReviewPhim AI (Android)

App điện thoại làm **video review / tóm tắt phim** và **dịch phim nước ngoài sang tiếng Việt** (thuyết minh + Vietsub), tự làm hết trên máy.

| Bước | Cách làm |
|---|---|
| Video | Chọn trong máy, dán link TikTok / YouTube / Douyin / Bilibili (yt-dlp), hoặc bấm *Chia sẻ → ReviewPhim AI* từ app khác |
| Lời gốc | Nghe lời thoại bằng **Groq Whisper** (miễn phí, cần key) · **đọc phụ đề cứng trên hình** bằng ML Kit (không cần mạng, đọc chữ Trung + Latin) · hoặc file .srt |
| AI | Viết kịch bản review (hook, kể theo trình tự, đúng tên nhân vật) hoặc dịch theo lô 30 câu + rút gọn câu đọc quá nhanh. Dùng API chính thức: DeepSeek, Gemini, OpenRouter (tự chọn DeepSeek miễn phí), Groq, OpenAI. **Không có key**: app soạn sẵn yêu cầu, bạn dán vào DeepSeek web / app DeepSeek rồi dán câu trả lời lại |
| Giọng đọc | Giọng tiếng Việt có sẵn trong máy (Google / Samsung TTS), miễn phí, đọc được offline |
| Dựng | Media3 Transformer (chip mã hóa phần cứng): cắt nối cảnh, che phụ đề gốc, khung dọc 9:16, phụ đề Việt + tiêu đề. Tiếng trộn bằng ffmpeg (tiếng phim nền nhỏ, tự nhỏ thêm khi có giọng đọc) |
| Review | Mỗi đoạn lời kể ghép vài cảnh ngắn bắt đầu đúng điểm cắt cảnh (bỏ cảnh đen), phụ đề karaoke, tiêu đề hook, nhạc nền tự nhỏ khi có giọng đọc; kịch bản hook + 3 hồi (học cơ chế từ movie-narrator, opensource-clipping, MovieShort-AI) |
| Kết quả | Lưu vào Thư viện ảnh → Movies/ReviewPhim, có nút Xem / Chia sẻ. Tab *Kịch bản* để sửa chữ rồi xuất lại |

Cài đặt: tải `ReviewPhim.apk` ở mục Releases (tag `reviewphim`) của repo. App có nút **Cập nhật** tự lấy bản mới.

APK được GitHub Actions dựng (`.github/workflows/reviewphim-android.yml`): test trên JVM + test trên máy ảo Android (ffmpeg, dựng hình có phụ đề, trộn tiếng), rồi mới đăng Release.

Mã nguồn mở dùng: [youtubedl-android](https://github.com/yausername/youtubedl-android) (GPL-3.0, gồm yt-dlp + ffmpeg), AndroidX Media3, ML Kit Text Recognition, OkHttp.
