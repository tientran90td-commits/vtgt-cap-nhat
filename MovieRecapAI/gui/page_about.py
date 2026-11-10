"""Trang giới thiệu: các dự án mã nguồn mở được tích hợp + hướng dẫn nhanh."""
from __future__ import annotations

from PySide6.QtWidgets import QTextBrowser

from recap import APP_NAME, APP_VERSION

from .widgets import Page

OSS = [
    ("FFmpeg", "https://github.com/FFmpeg/FFmpeg", "LGPL/GPL", "Cắt ghép, mã hóa video, trộn âm thanh, chèn phụ đề"),
    ("faster-whisper", "https://github.com/SYSTRAN/faster-whisper", "MIT", "Nhận dạng lời thoại offline (Whisper)"),
    ("OpenAI Whisper", "https://github.com/openai/whisper", "MIT", "Model nhận dạng giọng nói gốc"),
    ("CTranslate2", "https://github.com/OpenNMT/CTranslate2", "MIT", "Chạy Whisper nhanh trên CPU/GPU"),
    ("PySceneDetect", "https://github.com/Breakthrough/PySceneDetect", "BSD-3", "Dò chuyển cảnh"),
    ("OpenCV", "https://github.com/opencv/opencv", "Apache-2.0", "Đọc khung hình cho dò cảnh"),
    ("yt-dlp", "https://github.com/yt-dlp/yt-dlp", "Unlicense", "Tải phim từ YouTube, Facebook, TikTok... + phụ đề"),
    ("edge-tts", "https://github.com/rany2/edge-tts", "LGPL-3.0", "400+ giọng Microsoft Edge miễn phí"),
    ("gTTS", "https://github.com/pndurette/gTTS", "MIT", "Giọng Google Translate miễn phí"),
    ("Piper", "https://github.com/rhasspy/piper", "MIT/GPL", "Giọng đọc neural offline"),
    ("piper-voices", "https://huggingface.co/rhasspy/piper-voices", "nhiều license", "Kho giọng Piper"),
    ("Coqui TTS / XTTS-v2", "https://github.com/idiap/coqui-ai-TTS", "MPL-2.0 (model: CPML)",
     "Nhân bản giọng nói offline"),
    ("viXTTS", "https://huggingface.co/capleaf/viXTTS", "CPML", "XTTS tinh chỉnh cho tiếng Việt"),
    ("pyttsx3", "https://github.com/nateshmbhat/pyttsx3", "MPL-2.0", "Giọng có sẵn của Windows/macOS/Linux"),
    ("libass", "https://github.com/libass/libass", "ISC", "Vẽ phụ đề đẹp vào video"),
    ("Qt / PySide6", "https://code.qt.io/cgit/pyside/pyside-setup.git", "LGPL-3.0", "Giao diện người dùng"),
    ("Anthropic Python SDK", "https://github.com/anthropics/anthropic-sdk-python", "MIT", "Kết nối Claude"),
    ("Requests", "https://github.com/psf/requests", "Apache-2.0", "Kết nối các API AI"),
    ("imageio-ffmpeg", "https://github.com/imageio/imageio-ffmpeg", "BSD-2", "FFmpeg dự phòng đóng gói sẵn"),
    ("Ollama", "https://github.com/ollama/ollama", "MIT", "Chạy LLM offline (Llama, Qwen, Gemma...)"),
]


class AboutPage(Page):
    def __init__(self, app):
        super().__init__(app, f"ℹ️  {APP_NAME} {APP_VERSION}", "Hướng dẫn nhanh và danh sách mã nguồn mở được tích hợp.")
        tb = QTextBrowser()
        tb.setOpenExternalLinks(True)
        rows = "".join(f"<tr><td><a href='{u}'>{n}</a></td><td>{lic}</td><td>{d}</td></tr>" for n, u, lic, d in OSS)
        tb.setHtml(f"""
<h3>🚀 Cách dùng nhanh (miễn phí hoàn toàn)</h3>
<ol>
<li>Vào <b>🔑 API & Cài đặt</b>, dán <b>Gemini API key</b> (miễn phí tại aistudio.google.com/apikey).</li>
<li>Vào <b>🎬 Video nguồn</b>, kéo thả phim (hoặc dán link YouTube).</li>
<li>Bấm <b>⚡ TỰ ĐỘNG LÀM TẤT CẢ</b>. App sẽ: nhận dạng thoại (Whisper) → dò cảnh → AI viết kịch bản →
    lồng tiếng (Edge TTS giọng Hoài My) → dựng video có phụ đề.</li>
<li>Muốn chỉnh: sửa lời thuyết minh/mốc thời gian trong bảng ở <b>📝 Kịch bản</b>, đổi giọng ở <b>🎙️ Giọng đọc</b>,
    rồi bấm <b>🚀 XUẤT VIDEO</b> (chỉ dựng lại đoạn đã sửa).</li>
</ol>
<h3>💡 Mẹo</h3>
<ul>
<li>Phim có phụ đề .srt: chọn <i>Dùng file phụ đề có sẵn</i> - nhanh và chính xác hơn nhận dạng.</li>
<li>Máy có card NVIDIA: chọn model Whisper <i>large-v3</i> và bộ mã hóa <i>NVENC</i> để nhanh hơn nhiều lần.</li>
<li>Kiểu <i>Cắt highlight giữ thoại gốc</i> không cần giọng đọc; để trống lời thuyết minh 1 dòng để giữ câu thoại đắt giá.</li>
<li>Video TikTok: bấm mẫu <i>📱 TikTok / Reels / Shorts</i> ở bước 4.</li>
</ul>
<h3>⚖️ Lưu ý bản quyền</h3>
<p>Chỉ sử dụng với phim bạn có quyền sử dụng (phim của bạn, phim được cấp phép, nội dung public domain) hoặc trong
phạm vi sử dụng hợp lý theo luật bản quyền nơi bạn sinh sống. Người dùng tự chịu trách nhiệm về nội dung đăng tải.</p>
<h3>🧩 Mã nguồn mở được tích hợp</h3>
<table cellpadding='5' border='0'><tr><th align='left'>Dự án</th><th align='left'>Giấy phép</th>
<th align='left'>Dùng để</th></tr>{rows}</table>
<p>Dịch vụ AI qua API: Google Gemini, Anthropic Claude, OpenAI, Groq, DeepSeek, OpenRouter, xAI, Mistral, Qwen,
ElevenLabs, Google Cloud TTS, Azure Speech, FPT.AI.</p>
""")
        self.root.addWidget(tb, 1)
