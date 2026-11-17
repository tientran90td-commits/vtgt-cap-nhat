@echo off
chcp 65001 >nul
setlocal EnableDelayedExpansion
cd /d "%~dp0"
title Cai AI may nha cho ReviewPhim AI
echo ============================================================
echo  Cai AI chay tren may tinh nay cho app ReviewPhim AI
echo  (Ollama mien phi + LiteLLM). Lam 1 lan, mat 10-30 phut.
echo ============================================================
echo.

rem ---------- 1. Ollama
where ollama >nul 2>&1
if errorlevel 1 (
  if exist "%LOCALAPPDATA%\Programs\Ollama\ollama.exe" (
    set "PATH=%LOCALAPPDATA%\Programs\Ollama;%PATH%"
  ) else (
    echo [1/5] Cai Ollama...
    winget install --id Ollama.Ollama -e --accept-package-agreements --accept-source-agreements
    if errorlevel 1 (
      echo Khong cai tu dong duoc. Mo trang tai Ollama - cai xong chay lai file nay.
      start https://ollama.com/download
      pause
      exit /b 1
    )
    set "PATH=%LOCALAPPDATA%\Programs\Ollama;%PATH%"
  )
) else (
  echo [1/5] Da co Ollama.
)
rem cho dien thoai ket noi thang toi Ollama neu muon (cong 11434)
setx OLLAMA_HOST 0.0.0.0 >nul

rem ---------- 2. Mo hinh AI nhin duoc anh, chon theo RAM
for /f "usebackq" %%r in (`powershell -NoProfile -Command "[math]::Round((Get-CimInstance Win32_ComputerSystem).TotalPhysicalMemory/1GB)"`) do set RAM=%%r
set MODEL=gemma3:4b
if !RAM! GEQ 24 set MODEL=gemma3:12b
echo [2/5] May co !RAM! GB RAM - tai mo hinh !MODEL! (vai GB, lan dau hoi lau)...
start "" /min ollama serve
timeout /t 3 >nul
ollama pull !MODEL!
if errorlevel 1 (
  echo Tai mo hinh loi - kiem tra mang roi chay lai.
  pause
  exit /b 1
)

rem ---------- 3. Key Gemini (khong bat buoc)
echo.
echo [3/5] Key Gemini mien phi (aistudio.google.com/apikey) giup viet / dich hay hon va nhanh hon.
echo       Dan 1 hoac nhieu key cach nhau dau phay, hoac bam Enter de chi dung AI may nha:
set "KEYS="
set /p KEYS=Key Gemini: 
for /f "usebackq" %%m in (`powershell -NoProfile -Command "'sk-rp-' + [guid]::NewGuid().ToString('N').Substring(0,20)"`) do set MASTER=%%m
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0tao_config.ps1" -Model "!MODEL!" -Keys "!KEYS!" -Master "!MASTER!"

rem ---------- 4. LiteLLM (can Python)
where py >nul 2>&1 || where python >nul 2>&1
if errorlevel 1 (
  echo [4/5] Cai Python...
  winget install --id Python.Python.3.12 -e --accept-package-agreements --accept-source-agreements
  set "PATH=%LOCALAPPDATA%\Programs\Python\Python312;%LOCALAPPDATA%\Programs\Python\Python312\Scripts;%PATH%"
)
if not exist ".venv\Scripts\litellm.exe" (
  echo [4/5] Cai LiteLLM...
  py -3 -m venv .venv 2>nul || python -m venv .venv
  ".venv\Scripts\python.exe" -m pip install --upgrade pip
  ".venv\Scripts\python.exe" -m pip install "litellm[proxy]"
) else (
  echo [4/5] Da co LiteLLM.
)

rem ---------- 5. Mo cong 4000 cho dien thoai cung wifi (can quyen Admin, loi thi bo qua)
netsh advfirewall firewall add rule name="ReviewPhim AI 4000" dir=in action=allow protocol=TCP localport=4000 profile=private >nul 2>&1
if errorlevel 1 echo [5/5] Chua mo duoc tuong lua (chay file nay bang "Run as administrator", hoac bam Allow khi Windows hoi).

rem ---------- thong tin ket noi
(
  echo Nhap vao app ReviewPhim AI - Cai dat - May chu AI rieng:
  for /f "tokens=2 delims=:" %%a in ('ipconfig ^| findstr /c:"IPv4"') do echo   Dia chi:%%a:4000
  echo   Key: !MASTER!
  echo   Model viet / dich: chinh
  echo   Model nhin anh: nhin-anh
  echo Moi lan dung: bam dup CHAY_AI_MAY_NHA.bat ^(may tinh phai bat, cung wifi voi dien thoai^).
) > thong_tin_ket_noi.txt
echo.
type thong_tin_ket_noi.txt
echo.
echo Xong! Bam phim bat ky de chay AI may nha ngay.
pause >nul
call "%~dp0CHAY_AI_MAY_NHA.bat"
