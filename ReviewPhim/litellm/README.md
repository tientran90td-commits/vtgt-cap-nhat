# LiteLLM cho ReviewPhim AI - đỡ lỗi quá tải khi gửi AI

[LiteLLM](https://www.litellm.ai/) (mã nguồn mở, MIT) là trạm trung chuyển chạy trên máy tính / máy chủ: app gửi yêu cầu
tới LiteLLM, LiteLLM gửi tiếp cho Gemini / DeepSeek / Groq... và:

- **xoay vòng nhiều key** (5 key Gemini miễn phí = gấp 5 lượt),
- **tự thử lại** khi AI báo quá tải (429 / 503), **tạm bỏ** key / AI đang lỗi,
- **tự chuyển AI dự phòng** khi AI chính lỗi hết,
- dùng thêm AI khác: Claude, Mistral, AI chạy ở nhà bằng Ollama...

Không làm AI hết quá tải: nếu mọi AI cùng lỗi thì app vẫn chuyển sang 🖐 làm tay như cũ.

> Không có máy tính bật sẵn? App cũng tự xoay nhiều key: ở Cài đặt nhập nhiều key cho 1 AI, cách nhau dấu phẩy.

## Chạy trên máy tính Windows

1. Cài Python 3.10+ ([python.org](https://www.python.org/downloads/), tích *Add python.exe to PATH*).
2. Tải thư mục này về, mở `config.yaml` bằng Notepad, thay `KEY_GEMINI_1`, `KEY_DEEPSEEK`... bằng key của bạn,
   đổi `master_key`.
3. Bấm đúp `chay_litellm.bat` (lần đầu tự cài). Cửa sổ hiện địa chỉ IP máy tính.
4. Trên điện thoại (cùng wifi): ReviewPhim AI → ⚙️ Cài đặt → **🖥 Máy chủ AI riêng**:
   - Địa chỉ: `192.168.x.x:4000` (IP máy tính hiện trong cửa sổ)
   - Key: `master_key` trong `config.yaml`
   - Model viết / dịch: `chinh` · Model nhìn ảnh: `nhin-anh`
   - Bấm **🔌 Kiểm tra kết nối**.

Windows hỏi tường lửa thì cho phép mạng riêng (Private). Máy tính phải bật khi app làm video.

## Linux / máy chủ thuê

```bash
pip install "litellm[proxy]"
litellm --config config.yaml --host 0.0.0.0 --port 4000
```

Chạy trên máy chủ có địa chỉ công khai thì dùng được cả khi điện thoại không ở nhà - nhớ đặt `master_key` khó đoán.

## AI chạy ở nhà, miễn phí (Ollama)

Cài [Ollama](https://ollama.com), chạy `ollama pull qwen2.5:14b` (viết / dịch) và `ollama pull gemma3:12b` (nhìn ảnh), rồi:
- bỏ dấu `#` ở mục Ollama trong `config.yaml` để LiteLLM dùng làm dự phòng, hoặc
- trỏ thẳng app tới Ollama: địa chỉ `192.168.x.x:11434`, model `qwen2.5:14b`, model nhìn ảnh `gemma3:12b`
  (đặt biến môi trường `OLLAMA_HOST=0.0.0.0` để điện thoại kết nối được).

AI chạy ở nhà viết / dịch kém DeepSeek / Gemini một bậc và chậm hơn trên máy không có card đồ họa mạnh.
