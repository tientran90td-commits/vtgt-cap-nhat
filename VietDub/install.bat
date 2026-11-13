@echo off
chcp 65001 >nul
title VietDub Studio - Cai dat
cd /d "%~dp0"
echo ==================================================
echo   VIETDUB STUDIO - DICH VIDEO SANG TIENG VIET
echo ==================================================
where python >nul 2>nul
if errorlevel 1 (
  echo [!] Chua co Python. Tai Python 3.12 tai https://www.python.org/downloads/
  echo     Nho tick "Add python.exe to PATH" khi cai, roi chay lai install.bat
  start https://www.python.org/downloads/
  pause
  exit /b 1
)
rem --- kiem tra cho trong: can khoang 3 GB tren o chua app
for /f %%F in ('powershell -NoProfile -Command "[math]::Floor((New-Object IO.DriveInfo %~d0).AvailableFreeSpace/1GB)"') do set FREEGB=%%F
echo O %~d0 con trong: %FREEGB% GB
if defined FREEGB if %FREEGB% LSS 3 (
  echo [!] O %~d0 con it hon 3 GB - hay don bot roi chay lai. Xem README muc "O day".
  pause
  exit /b 1
)
rem --- file tam cua pip de tren cung o voi app, khong luu cache (tranh day o C)
set "TEMP=%~dp0.tmp"
set "TMP=%~dp0.tmp"
if not exist "%TEMP%" mkdir "%TEMP%"
set PIP_NO_CACHE_DIR=1
if not exist .venv (
  echo [1/3] Tao moi truong .venv ...
  python -m venv .venv
)
call .venv\Scripts\activate.bat
echo [2/3] Cai thu vien (Whisper, giong doc, giao dien...) - lan dau mat vai phut ...
python -m pip install --upgrade pip
pip install -r requirements.txt
if errorlevel 1 (
  echo [!] Cai thu vien loi. Neu bao "No space left on device": don o dia roi chay lai.
  rd /s /q "%~dp0.tmp" 2>nul
  pause
  exit /b 1
)
rd /s /q "%~dp0.tmp" 2>nul
echo.
echo [3/3] AI DICH:
echo   - Cach nhanh, hay nhat, MIEN PHI: lay key Gemini tai https://aistudio.google.com/apikey
echo     roi dan vao app (Cai dat). Khong can cai them gi.
echo   - Hoac AI chay tren may (khong can mang): Ollama + model qwen2.5:7b (~5 GB, can 8 GB RAM).
choice /c YN /n /m "   Cai AI tren may (Ollama, ~5 GB)? [Y/N] "
if errorlevel 2 goto done
set "OLLAMA=%LOCALAPPDATA%\Programs\Ollama\ollama.exe"
where ollama >nul 2>nul && set "OLLAMA=ollama"
if not exist "%OLLAMA%" if not "%OLLAMA%"=="ollama" (
  winget install -e --id Ollama.Ollama --accept-source-agreements --accept-package-agreements
)
if exist "%LOCALAPPDATA%\Programs\Ollama\ollama app.exe" start "" "%LOCALAPPDATA%\Programs\Ollama\ollama app.exe"
timeout /t 5 >nul
"%OLLAMA%" pull qwen2.5:7b || echo     Chua tai duoc - mo app, vao Cai dat bam "Tai model AI".
:done
echo.
echo XONG! Bam run.bat de mo VietDub Studio.
pause
