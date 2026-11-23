# Thành phần bên thứ ba

- **Rapfi** — engine caro/gomoku (vô địch Gomocup 2024). Mã nguồn: https://github.com/dhbloo/rapfi — giấy phép GPL-3.
  APK được dựng tự động bởi GitHub Actions (file `.github/workflows/caro-tro-thu-apk.yml`): workflow tải đúng mã nguồn Rapfi ở trên,
  biên dịch ra WebAssembly bằng Emscripten và đóng vào app. Toàn bộ mã nguồn dùng để dựng nằm ở kho Rapfi và kho này.
- **Rapfi networks** — trọng số mạng NNUE, giấy phép CC0: https://github.com/dhbloo/rapfi-networks
