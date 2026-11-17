@echo off
chcp 65001 >nul
title Recap Studio - Cai dat
cd /d "%~dp0"
echo ==================================================
echo   RECAP STUDIO - CAI DAT LAN DAU (chay tren may)
echo ==================================================
where python >nul 2>nul
if errorlevel 1 (
  echo [!] Chua co Python. Tai Python 3.12 tai https://www.python.org/downloads/
  echo     Nho tick "Add python.exe to PATH" khi cai, roi chay lai install.bat
  start https://www.python.org/downloads/
  pause
  exit /b 1
)
if not exist .venv (
  echo [1/4] Tao moi truong .venv ...
  python -m venv .venv
)
call .venv\Scripts\activate.bat
echo [2/4] Cai thu vien (Whisper, giong VieNeu, giao dien...) - lan dau mat vai phut ...
python -m pip install --upgrade pip
pip install -r requirements.txt
if errorlevel 1 (
  echo [!] Cai thu vien loi. Kiem tra mang roi chay lai install.bat
  pause
  exit /b 1
)
echo [3/4] Cai Ollama - AI viet kich ban chay tren may ...
set "OLLAMA=%LOCALAPPDATA%\Programs\Ollama\ollama.exe"
where ollama >nul 2>nul && set "OLLAMA=ollama"
if not exist "%OLLAMA%" if not "%OLLAMA%"=="ollama" (
  winget install -e --id Ollama.Ollama --accept-source-agreements --accept-package-agreements
)
if exist "%LOCALAPPDATA%\Programs\Ollama\ollama app.exe" start "" "%LOCALAPPDATA%\Programs\Ollama\ollama app.exe"
timeout /t 5 >nul
echo [4/4] Tai model AI qwen2.5:7b (~4.7 GB, mot lan) ...
"%OLLAMA%" pull qwen2.5:7b || echo     Chua tai duoc - mo app, vao Cai dat bam "Tai model AI".
echo.
echo XONG! Bam run.bat de mo Recap Studio.
pause
