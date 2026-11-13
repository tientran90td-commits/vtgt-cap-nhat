@echo off
chcp 65001 >nul
setlocal EnableExtensions
title VietDub Studio - Cai dat (moi thu nam o o chua app)
cd /d "%~dp0"
set "APP=%~dp0"
set "DATA=%~dp0data"
set "TOOLS=%~dp0tools"
echo ==================================================
echo   VIETDUB STUDIO - CAI DAT
echo   Python, thu vien, model, file tam: TAT CA nam trong
echo   %APP%
echo   Khong ghi gi vao o C.
echo ==================================================
if /i "%~d0"=="%SystemDrive%" (
  echo [!] Thu muc app dang o o %~d0 - la o he thong.
  echo     O C day thi hay chep ca thu muc VietDub sang o D roi chay install.bat o do.
  choice /c YN /n /m "    Van cai o day? [Y/N] "
  if errorlevel 2 exit /b 1
)
for /f %%F in ('powershell -NoProfile -Command "[math]::Floor((New-Object IO.DriveInfo '%~d0').AvailableFreeSpace/1GB)"') do set FREEGB=%%F
echo O %~d0 con trong: %FREEGB% GB
if defined FREEGB if %FREEGB% LSS 5 (
  echo [!] Can it nhat 5 GB trong tren o %~d0. Hay don bot roi chay lai.
  pause
  exit /b 1
)
if not exist "%DATA%\tmp" mkdir "%DATA%\tmp"
if not exist "%TOOLS%" mkdir "%TOOLS%"
rem --- moi file tam, bo nho dem, model deu nam o o nay
set "TEMP=%DATA%\tmp"
set "TMP=%DATA%\tmp"
set "UV_CACHE_DIR=%DATA%\cache\uv"
set "UV_PYTHON_INSTALL_DIR=%TOOLS%\python"
set "UV_PYTHON_PREFERENCE=only-managed"
set "UV_LINK_MODE=copy"
set "PIP_NO_CACHE_DIR=1"
set "HF_HOME=%DATA%\huggingface"

echo.
echo [1/4] Tai uv - trinh cai Python sieu nhanh (~20 MB) ...
if not exist "%TOOLS%\uv.exe" (
  curl -L --fail -o "%DATA%\tmp\uv.zip" https://github.com/astral-sh/uv/releases/latest/download/uv-x86_64-pc-windows-msvc.zip
  powershell -NoProfile -Command "Expand-Archive -Force '%DATA%\tmp\uv.zip' '%TOOLS%'"
  del "%DATA%\tmp\uv.zip" 2>nul
)
if not exist "%TOOLS%\uv.exe" goto no_uv

echo [2/4] Cai Python 3.12 vao %TOOLS%\python (khong can Python o o C) ...
if not exist .venv\Scripts\python.exe (
  "%TOOLS%\uv.exe" venv --seed --python 3.12 .venv
  if errorlevel 1 goto fail
)
echo [3/4] Cai thu vien (Whisper, giong Ngoc Huyen, OCR, giao dien...) - lan dau mat vai phut ...
"%TOOLS%\uv.exe" pip install --python .venv\Scripts\python.exe -r requirements.txt
if errorlevel 1 goto fail
rem --- chay model AI bang card do hoa (AMD/NVIDIA/Intel) qua DirectML
.venv\Scripts\python.exe -c "import onnxruntime as o,sys; sys.exit(0 if 'DmlExecutionProvider' in o.get_available_providers() else 1)" 2>nul || "%TOOLS%\uv.exe" pip install --python .venv\Scripts\python.exe --no-deps --reinstall onnxruntime-directml
goto ai

:no_uv
echo [!] Khong tai duoc uv - dung Python co san tren may.
where python >nul 2>nul
if errorlevel 1 (
  echo [!] Chua co Python. Kiem tra mang roi chay lai install.bat.
  pause
  exit /b 1
)
if not exist .venv python -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt
if errorlevel 1 goto fail

:ai
echo.
echo [4/4] AI DICH:
echo   - Cach nhanh, hay nhat, MIEN PHI: lay key Gemini tai https://aistudio.google.com/apikey
echo     roi dan vao app (Cai dat). Khong can cai them gi.
echo   - Hoac AI chay tren may (khong can mang): Ollama + model qwen2.5:7b (~6 GB, can 8 GB RAM),
echo     cai vao %TOOLS%\ollama, model de o %DATA%\ollama-models.
choice /c YN /n /m "   Cai AI tren may (Ollama)? [Y/N] "
if errorlevel 2 goto done
set "OLLAMA_MODELS=%DATA%\ollama-models"
setx OLLAMA_MODELS "%DATA%\ollama-models" >nul
if not exist "%TOOLS%\ollama\ollama.exe" (
  curl -L --fail -o "%DATA%\tmp\OllamaSetup.exe" https://ollama.com/download/OllamaSetup.exe
  "%DATA%\tmp\OllamaSetup.exe" /DIR="%TOOLS%\ollama" /VERYSILENT /SUPPRESSMSGBOXES /NORESTART
  del "%DATA%\tmp\OllamaSetup.exe" 2>nul
)
if not exist "%TOOLS%\ollama\ollama.exe" (
  echo [!] Chua cai duoc Ollama - co the dung key Gemini thay the.
  goto done
)
taskkill /im "ollama app.exe" /f >nul 2>nul
taskkill /im ollama.exe /f >nul 2>nul
start "" /b "%TOOLS%\ollama\ollama.exe" serve
timeout /t 6 >nul
"%TOOLS%\ollama\ollama.exe" pull qwen2.5:7b || echo     Chua tai duoc - mo app, vao Cai dat bam "Tai model AI".
goto done

:fail
echo [!] Cai dat loi. Neu bao "No space left on device": don o %~d0 roi chay lai.
rd /s /q "%DATA%\tmp" 2>nul
pause
exit /b 1

:done
rd /s /q "%DATA%\tmp" 2>nul
mkdir "%DATA%\tmp" 2>nul
echo.
echo XONG! Bam run.bat de mo VietDub Studio.
pause
