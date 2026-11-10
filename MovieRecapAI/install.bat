@echo off
chcp 65001 >nul
title Movie Recap AI - Cai dat
cd /d "%~dp0"
echo ============================================
echo   MOVIE RECAP AI - CAI DAT LAN DAU
echo ============================================
where python >nul 2>nul
if errorlevel 1 (
  echo [!] Chua co Python. Tai Python 3.10 - 3.12 tai https://www.python.org/downloads/
  echo     Nho tick "Add python.exe to PATH" khi cai.
  pause
  exit /b 1
)
if not exist .venv (
  echo [1/4] Tao moi truong ao .venv ...
  python -m venv .venv
)
call .venv\Scripts\activate.bat
echo [2/4] Cai thu vien chinh ...
python -m pip install --upgrade pip
pip install -r requirements.txt
if errorlevel 1 (
  echo [!] Cai thu vien loi. Kiem tra mang roi chay lai install.bat
  pause
  exit /b 1
)
echo [3/4] Cai giong doc offline Piper (tuy chon) ...
pip install "piper-tts>=1.2" || echo     (bo qua Piper)
echo      Cai VieNeu-TTS - giong Viet AI phat am chuan (tuy chon) ...
pip install "vieneu>=3.8" || echo     (bo qua VieNeu-TTS)
echo [4/4] Kiem tra FFmpeg ...
where ffmpeg >nul 2>nul
if errorlevel 1 (
  echo     Chua co FFmpeg tren may - thu cai bang winget ...
  winget install -e --id Gyan.FFmpeg --accept-source-agreements --accept-package-agreements || echo     Khong cai duoc qua winget. App se dung FFmpeg du phong cua imageio-ffmpeg.
)
echo.
echo XONG! Chay run.bat de mo ung dung.
echo (Muon nhan ban giong XTTS: .venv\Scripts\pip install coqui-tts)
pause
