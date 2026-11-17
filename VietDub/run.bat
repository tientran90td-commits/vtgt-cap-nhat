@echo off
cd /d "%~dp0"
set "TEMP=%~dp0data\tmp"
set "TMP=%~dp0data\tmp"
if not exist "%TEMP%" mkdir "%TEMP%"
if not exist .venv\Scripts\pythonw.exe (
  echo Chua cai dat - dang chay install.bat ...
  call install.bat
)
start "" .venv\Scripts\pythonw.exe main.py
