# ReviewPhim AI & MangaRecap AI (Android)

App điện thoại làm **video review / tóm tắt phim** và **dịch phim nước ngoài sang tiếng Việt** (thuyết minh + Vietsub), tự làm hết trên máy.

| Bước | Cách làm |
|---|---|
| Video | Chọn trong máy, dán link TikTok / YouTube / Douyin / Bilibili (yt-dlp), hoặc bấm *Chia sẻ → ReviewPhim AI* từ app khác |
| Lời gốc | Nghe lời thoại bằng **Groq Whisper** (miễn phí, cần key) · **đọc phụ đề cứng trên hình** bằng ML Kit (không cần mạng, đọc chữ Trung + Latin) · hoặc file .srt |
| AI | Viết kịch bản review (hook, kể theo trình tự, đúng tên nhân vật) hoặc dịch theo lô 30 câu + rút gọn câu đọc quá nhanh. Dùng API chính thức: DeepSeek, Gemini, OpenRouter (tự chọn DeepSeek miễn phí), Groq, OpenAI. **Không có key**: app soạn sẵn yêu cầu, bạn dán vào DeepSeek web / app DeepSeek rồi dán câu trả lời lại |
| Giọng đọc | Giọng tiếng Việt có sẵn trong máy (Google / Samsung TTS), miễn phí, đọc được offline |
| Dựng | Media3 Transformer (chip mã hóa phần cứng): cắt nối cảnh, che phụ đề gốc, khung dọc 9:16, phụ đề Việt + tiêu đề. Tiếng trộn bằng ffmpeg (tiếng phim nền nhỏ, tự nhỏ thêm khi có giọng đọc) |
| Review | Mỗi đoạn lời kể ghép vài cảnh ngắn bắt đầu đúng điểm cắt cảnh (bỏ cảnh đen), phụ đề karaoke, tiêu đề hook, nhạc nền tự nhỏ khi có giọng đọc; kịch bản hook + 3 hồi (học cơ chế từ movie-narrator, opensource-clipping, MovieShort-AI) |
| Giọng VieNeu + nhân bản giọng | Giọng AI tiếng Việt [VieNeu-TTS v3 Nano](https://github.com/pnnbao97/VieNeu-TTS) chạy ngay trên điện thoại (onnxruntime, offline sau khi tải ~450 MB một lần). Ghi âm 8-15 giây hoặc chọn file để nhân bản giọng (chỉ giọng của bạn / người đã đồng ý). Âm vị tiếng Việt bằng [sea-g2p](https://github.com/pnnbao97/sea-g2p) (Rust, qua JNI) |
| Giọng VoiceStudio | Tùy chọn: gọi [VoiceStudio](https://github.com/debpalash/VoiceStudio) (AGPL) chạy trên máy tính cùng wifi qua API `/v1/audio/speech` - giọng AI / giọng nhân bản; app không chứa code VoiceStudio, mất kết nối thì tự dùng giọng của máy |
| Kết quả | Lưu vào Thư viện ảnh → Movies/ReviewPhim, có nút Xem / Chia sẻ. Tab *Kịch bản* để sửa chữ rồi xuất lại |

## MangaRecap AI (app thứ 2, thư mục `manga/`)

App **tóm tắt truyện tranh (manga / manhwa / manhua) và light novel thành video** kể chuyện.

| Bước | Cách làm |
|---|---|
| Truyện | Ảnh các trang, cả thư mục, file CBZ / ZIP / PDF; light novel: EPUB (lấy cả ảnh minh họa + bìa), TXT (UTF-8 / GB18030) hoặc dán chữ. Trang manhwa dài được tự cắt ở khoảng trắng giữa các khung tranh |
| Đọc truyện | Truyện tranh: ghép 4 trang/ảnh có số trang, AI nhìn ảnh (Gemini / OpenRouter / Groq / OpenAI) tả diễn biến + dịch lời thoại từng trang; không có key thì 🖐 gửi ảnh cho app Gemini. Light novel: AI tóm tắt từng phần thành các ý (🖐 DeepSeek nếu không có key) |
| Kịch bản | Hook + kể theo trình tự, mỗi đoạn neo vào đúng các trang / phần truyện; tên nhân vật đúng (bảng tên riêng, MyAnimeList) |
| Video | Đúng trang tranh của từng đoạn kể: trang dài cuộn từ trên xuống, trang vừa khung phóng to chậm, nền mờ; light novel dùng ảnh minh họa gần nhất / bìa / khung tên truyện. Phụ đề karaoke, tiêu đề hook, nhạc nền, khung 9:16 hoặc 16:9 |
| Giọng | Như ReviewPhim: giọng máy, VieNeu AI trên máy + nhân bản giọng, VoiceStudio |

Học cơ chế từ mã nguồn mở (ý tưởng, code tự viết): [manga-reader](https://github.com/pashpashpash/manga-reader) (MIT - neo lời kể vào đúng trang, chiếu khung tranh theo lời kể), [Kumiko](https://github.com/njean42/kumiko) (AGPL - tách khung theo rãnh trắng, thứ tự phải→trái), [SmartStitch](https://github.com/MechTechnology/SmartStitch) / [StitchTool](https://github.com/Aeonss/StitchTool) (nối ảnh webtoon rồi cắt lại ở khoảng trắng), BooookScore (tóm tắt sách dài theo từng phần có nhớ mạch phần trước).

Code AI, giọng đọc, dựng video, trộn tiếng dùng chung với ReviewPhim ở thư mục `shared/`.

Cài đặt: tải `ReviewPhim.apk` / `MangaRecap.apk` ở mục Releases (tag `reviewphim`) của repo. App có nút **Cập nhật** tự lấy bản mới.

APK được GitHub Actions dựng (`.github/workflows/reviewphim-android.yml`): test trên JVM + test trên máy ảo Android (ffmpeg, dựng hình có phụ đề, trộn tiếng), rồi mới đăng Release.

Mã nguồn mở dùng: [youtubedl-android](https://github.com/yausername/youtubedl-android) (GPL-3.0, gồm yt-dlp + ffmpeg), AndroidX Media3, ML Kit Text Recognition, OkHttp, ONNX Runtime (MIT), VieNeu-TTS và sea-g2p (Apache-2.0, giấy phép trong assets của app).
