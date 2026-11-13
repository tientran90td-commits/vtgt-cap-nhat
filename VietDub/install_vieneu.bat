@echo off
chcp 65001 >nul
title VietDub Studio - Cai giong VieNeu
cd /d "%~dp0"
if not exist .venv\Scripts\activate.bat (
  echo Chua cai app - chay install.bat truoc.
  pause
  exit /b 1
)
echo Giong VieNeu (Ngoc Huyen, Hai Dang...) chay tren may, can them khoang 3 GB trong.
set "TEMP=%~dp0.tmp"
set "TMP=%~dp0.tmp"
if not exist "%TEMP%" mkdir "%TEMP%"
set PIP_NO_CACHE_DIR=1
call .venv\Scripts\activate.bat
pip install vieneu
if errorlevel 1 (echo [!] Cai VieNeu loi - thuong do thieu cho trong o dia.) else (echo XONG! Mo app, chon giong VieNeu.)
rd /s /q "%~dp0.tmp" 2>nul
pause
