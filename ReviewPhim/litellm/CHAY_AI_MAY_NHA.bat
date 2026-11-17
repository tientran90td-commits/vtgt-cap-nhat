@echo off
chcp 65001 >nul
cd /d "%~dp0"
title AI may nha - ReviewPhim AI (dung tat cua so nay khi dang lam video)
if not exist "config-may-nha.yaml" (
  echo Chua cai - chay CAI_AI_MAY_NHA.bat truoc.
  pause
  exit /b 1
)
set "PATH=%LOCALAPPDATA%\Programs\Ollama;%PATH%"
tasklist /fi "imagename eq ollama.exe" | find /i "ollama.exe" >nul || start "" /min ollama serve
type thong_tin_ket_noi.txt
echo.
".venv\Scripts\litellm.exe" --config config-may-nha.yaml --host 0.0.0.0 --port 4000
pause
