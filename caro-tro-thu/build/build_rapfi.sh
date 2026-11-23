#!/usr/bin/env bash
# Dựng engine Rapfi (https://github.com/dhbloo/rapfi, GPL-3) thành WebAssembly và kiểm tra bằng Node.
# Chạy từ thư mục gốc của kho. Kết quả (nếu kiểm tra đạt) nằm ở caro-tro-thu/app/src/main/assets/rapfi/
set -euo pipefail
ROOT="$(pwd)"
OUT="$ROOT/caro-tro-thu/app/src/main/assets/rapfi"
WORK="$(mktemp -d)"
echo "== tải mã nguồn Rapfi và bộ trọng số =="
git clone --depth 1 https://github.com/dhbloo/rapfi.git "$WORK/rapfi"
rm -rf "$WORK/rapfi/Networks"
git clone --depth 1 https://github.com/dhbloo/rapfi-networks.git "$WORK/rapfi/Networks"
cd "$WORK/rapfi/Networks"

echo "== chuẩn bị cấu hình (chỉ luật tự do 5 quân, toạ độ x,y chuẩn) =="
python3 - <<'PY'
import re
t = open('config-example/gomocalc-mix9svq.toml', encoding='utf8').read()
t = re.sub(r'coord_conversion_mode\s*=\s*"[^"]*"', 'coord_conversion_mode = "none"', t)
t, n1 = re.subn(r'\[\[model\.evaluator\.weights\]\]\s*\nweight_file = "mix9svqstandard[^\n]*\n', '', t)
t, n2 = re.subn(r'\[\[model\.evaluator\.weights\]\]\s*\nweight_file_black[^\n]*\nweight_file_white[^\n]*\n', '', t)
assert n1 == 1 and n2 == 1 and 'mix9svqfreestyle_bsmix.bin.lz4' in t, (n1, n2)
open('app-config.toml', 'w', encoding='utf8').write(t)
open('wasm_preloads.txt', 'w', encoding='utf8').write(
    'app-config.toml@config.toml\nclassical@/\nmix9svq/mix9svqfreestyle_bsmix.bin.lz4@/mix9svqfreestyle_bsmix.bin.lz4')
PY
grep -n "coord_conversion_mode\|weight_file" app-config.toml

echo "== biên dịch WebAssembly =="
cd "$WORK/rapfi/Rapfi"
mkdir -p build/wasm && cd build/wasm
emcmake cmake ../.. -DCMAKE_BUILD_TYPE=Release -DNO_COMMAND_MODULES=ON -DNO_MULTI_THREADING=ON -DUSE_WASM_SIMD=ON
emmake cmake --build . -j"$(nproc)"
ls -la

JS="$(ls rapfi-single*.js | head -1)"
BASE="${JS%.js}"
echo "== kiểm tra bằng Node: $JS =="
cp "$ROOT/caro-tro-thu/build/smoke_rapfi.js" ./smoke_rapfi.js
node smoke_rapfi.js "./$JS"

echo "== đạt: chép vào assets =="
mkdir -p "$OUT"
cp "$BASE.js" "$OUT/rapfi-single.js"
cp "$BASE.wasm" "$OUT/rapfi-single.wasm"
cp "$BASE.data" "$OUT/rapfi-single.data"
cp "$WORK/rapfi/Copying.txt" "$OUT/Copying.txt"
cp "$WORK/rapfi/AUTHORS" "$OUT/AUTHORS"
echo "Rapfi: https://github.com/dhbloo/rapfi (GPL-3). Trọng số: https://github.com/dhbloo/rapfi-networks (CC0)." > "$OUT/NGUON.txt"
ls -la "$OUT"
