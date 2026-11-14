#!/data/data/com.termux/files/usr/bin/bash
# Cài Phim Việt Studio cho Termux (Android). Chạy trong Termux:
#   curl -fsSL https://raw.githubusercontent.com/tientran90td-commits/vtgt-cap-nhat/claude/movie-summary-app-0q90dq/Termux/install.sh | bash
# Sau đó gõ:  phimviet   (Chrome tự mở giao diện)
set -e
REPO="tientran90td-commits/vtgt-cap-nhat"
BRANCH="claude/movie-summary-app-0q90dq"
APP="$HOME/phimviet"
TMPD="${TMPDIR:-$PREFIX/tmp}/phimviet-install"

say() { printf '\n\033[1;35m== %s\033[0m\n' "$1"; }

say "Phim Việt Studio - cài cho Termux"
if [ ! -d "$HOME/storage/shared" ]; then
  echo "Cho phép Termux đọc bộ nhớ máy (để chọn video & lưu video vào Thư viện ảnh)..."
  termux-setup-storage || true
  sleep 3
fi

say "1/4 Cập nhật gói Termux"
pkg update -y || true
yes | pkg upgrade -y -o Dpkg::Options::="--force-confnew" || true

say "2/4 Cài công cụ: Python, ffmpeg, numpy, Tesseract (đọc chữ trên hình)"
pkg install -y python python-pip ffmpeg python-numpy python-pillow tesseract curl unzip
# tách giọng gốc giữ nhạc nền (không bắt buộc - máy nào không có gói thì bỏ qua)
pkg install -y python-onnxruntime >/dev/null 2>&1 && echo "Đã có onnxruntime (tách nhạc nền)" || echo "Bỏ qua tách nhạc nền (không có onnxruntime cho máy này)"

say "3/4 Cài thư viện Python: giọng đọc Edge, tải video yt-dlp"
# bản thuần Python, khỏi phải biên dịch trên điện thoại
export AIOHTTP_NO_EXTENSIONS=1 YARL_NO_EXTENSIONS=1 MULTIDICT_NO_EXTENSIONS=1 FROZENLIST_NO_EXTENSIONS=1 PROPCACHE_NO_EXTENSIONS=1
pip install -U --no-cache-dir requests edge-tts yt-dlp gTTS

say "4/4 Tải Phim Việt Studio"
rm -rf "$TMPD" && mkdir -p "$TMPD" "$APP"
curl -fL "https://codeload.github.com/$REPO/zip/refs/heads/$BRANCH" -o "$TMPD/app.zip"
unzip -q "$TMPD/app.zip" -d "$TMPD"
SRC="$(find "$TMPD" -mindepth 1 -maxdepth 1 -type d | head -1)"
rm -rf "$APP/Termux" "$APP/VietDub.new"
cp -r "$SRC/Termux" "$APP/Termux"
mkdir -p "$APP/VietDub.new"
cp -r "$SRC/VietDub/vietdub" "$APP/VietDub.new/vietdub"
rm -rf "$APP/VietDub" && mv "$APP/VietDub.new" "$APP/VietDub"
rm -rf "$TMPD"

cat > "$PREFIX/bin/phimviet" <<EOS
#!/data/data/com.termux/files/usr/bin/bash
# giữ máy không ngủ khi đang làm video (tắt màn hình vẫn chạy)
termux-wake-lock 2>/dev/null || true
cd "$APP/Termux" && exec python server.py "\$@"
EOS
chmod +x "$PREFIX/bin/phimviet"
# nút tắt ngoài màn hình chính (cần app Termux:Widget)
mkdir -p "$HOME/.shortcuts" && cp "$PREFIX/bin/phimviet" "$HOME/.shortcuts/PhimViet" && chmod +x "$HOME/.shortcuts/PhimViet"

say "Xong! Gõ:  phimviet"
echo "Chrome sẽ mở giao diện ở http://127.0.0.1:8765 - giữ Termux chạy trong lúc làm video."
