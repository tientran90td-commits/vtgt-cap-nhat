#!/data/data/com.termux/files/usr/bin/bash
# Chay Co Vua LIVE tren Termux (Android). Dung:  bash chay-termux.sh        (that)
#                                              bash chay-termux.sh --demo (thu)
cd "$(dirname "$0")" || exit 1
if ! command -v node >/dev/null 2>&1; then
  echo "Dang cai Node.js..."
  pkg update -y && pkg install -y nodejs || { echo "Cai Node.js that bai"; exit 1; }
fi
if [ ! -d node_modules ]; then
  echo "Lan dau chay: cai thu vien..."
  npm install --no-audit --no-fund || { echo "Cai thu vien that bai"; exit 1; }
fi
if [ "$1" != "--demo" ] && [ "$1" != "--tikfinity" ] && [ ! -f ten-tiktok.txt ]; then
  printf "Nhap ID TikTok (khong co @): "
  read -r id
  printf "%s" "$id" > ten-tiktok.txt
fi
echo
echo "Mo Chrome tren dien thoai, vao:  http://localhost:3000"
echo "(giu Termux chay nen; muon tat thi bam Ctrl + C)"
termux-wake-lock 2>/dev/null
while true; do
  node src/server.js "$@"
  code=$?
  if [ "$code" -eq 3 ]; then echo "Vua cap nhat xong, dang mo lai game..."; sleep 2; continue; fi
  exit "$code"
done
