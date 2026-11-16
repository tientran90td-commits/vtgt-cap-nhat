# ReviewPhim AI · MangaRecap AI · LongRecap AI (Android)

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
| Truyện | **Dán link chương**: app tự lấy ảnh trang (truyện tranh) hoặc văn bản chương (truyện chữ), tự đi theo nút "Chương sau" nhiều chương; trang cần JavaScript / đăng nhập thì mở 🌐 trình duyệt trong app rồi bấm Lấy ảnh / Lấy chữ. Hoặc ảnh các trang, cả thư mục, file CBZ / ZIP / PDF; light novel: EPUB (lấy cả ảnh minh họa + bìa), TXT (UTF-8 / GB18030) hoặc dán chữ. Trang manhwa dài được tự cắt ở khoảng trắng giữa các khung tranh |
| Đọc truyện | Truyện tranh: ghép 4 trang/ảnh có số trang, AI nhìn ảnh (Gemini / OpenRouter / Groq / OpenAI) tả diễn biến + dịch lời thoại từng trang; không có key thì 🖐 gửi ảnh cho app Gemini. Light novel: AI tóm tắt từng phần thành các ý (🖐 DeepSeek nếu không có key) |
| Kịch bản | Hook + kể theo trình tự, mỗi đoạn neo vào đúng các trang / phần truyện; tên nhân vật đúng (bảng tên riêng, MyAnimeList) |
| Video | Đúng trang tranh của từng đoạn kể: trang dài cuộn từ trên xuống, trang vừa khung phóng to chậm, nền mờ; light novel dùng ảnh minh họa gần nhất / bìa / khung tên truyện. Phụ đề karaoke, tiêu đề hook, nhạc nền, khung 9:16 hoặc 16:9 |
| Giọng | Như ReviewPhim: giọng máy, VieNeu AI trên máy + nhân bản giọng, VoiceStudio |

Học cơ chế từ mã nguồn mở (ý tưởng, code tự viết): [manga-reader](https://github.com/pashpashpash/manga-reader) (MIT - neo lời kể vào đúng trang / khung, chiếu khung tranh theo lời kể, gửi kèm trang nhân vật làm mẫu → app tự lập bảng nhân vật ảnh + tên), [Kumiko](https://github.com/njean42/kumiko) (AGPL - tách khung theo rãnh trắng, thứ tự phải→trái), [SmartStitch](https://github.com/MechTechnology/SmartStitch) / [StitchTool](https://github.com/Aeonss/StitchTool) (nối ảnh webtoon rồi cắt lại ở khoảng trắng), [Magi](https://github.com/ragavsachdeva/magi) (chỉ cho nghiên cứu - học ý tưởng: bảng nhân vật, gán lời thoại cho người nói, bỏ chữ hiệu ứng), BooookScore (tóm tắt sách dài theo từng phần có nhớ mạch phần trước).

Code AI, giọng đọc, dựng video, trộn tiếng dùng chung với ReviewPhim ở thư mục `shared/`.

## LongRecap AI (app thứ 3, thư mục `longvid/`) - video dài tới 10 tiếng

| Loại | Cách làm |
|---|---|
| 📖 Truyện audio | EPUB (chia chương theo mục lục, ảnh minh họa + bìa), TXT (tự chia theo dòng "Chương ..."), dán chữ, hoặc link chương đầu (lấy liên tiếp tới 1000 chương). **Đọc nguyên văn** (truyện tiếng Việt đọc thẳng không cần AI; truyện nước ngoài AI dịch từng đoạn) hoặc **AI kể lại** rút gọn theo độ dài chọn (30 phút - 10 giờ) |
| 📚 Cả bộ truyện tranh | Nhiều CBZ / ZIP / PDF (mỗi file 1 chương) hoặc link chương; mỗi chương AI đọc tranh + viết lời kể (chia độ dài theo số trang), chiếu từng khung tranh |
| 🎬 Cả bộ phim | Nhiều tập (file / link yt-dlp); mỗi tập nghe lời thoại + xem hình + kịch bản review như ReviewPhim, chia độ dài theo độ dài tập |

Video dài làm theo **từng phần** (chương / tập): mỗi phần dựng xong lưu lại, dừng / tắt app vẫn **làm tiếp** từ phần dở; cuối cùng nối các phần (không mã hóa lại) thành 1 video, hoặc lưu từng phần riêng. AI nhớ nội dung phần trước để nối mạch, tên nhân vật thống nhất. Mức "Tiết kiệm" cho truyện audio ~0.16 GB / giờ (ảnh tĩnh 5 khung/giây). Kèm mục lục chương (dán vào mô tả YouTube) và phụ đề .srt của cả video.

Cài đặt: tải `ReviewPhim.apk` / `MangaRecap.apk` / `LongRecap.apk` ở mục Releases (tag `reviewphim`) của repo. App có nút **Cập nhật** tự lấy bản mới.

APK được GitHub Actions dựng (`.github/workflows/reviewphim-android.yml`): test trên JVM + test trên máy ảo Android (ffmpeg, dựng hình có phụ đề, trộn tiếng), rồi mới đăng Release.

Mã nguồn mở dùng: [youtubedl-android](https://github.com/yausername/youtubedl-android) (GPL-3.0, gồm yt-dlp + ffmpeg), AndroidX Media3, ML Kit Text Recognition, OkHttp, ONNX Runtime (MIT), VieNeu-TTS và sea-g2p (Apache-2.0, giấy phép trong assets của app).
