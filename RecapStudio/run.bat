@echo off
cd /d "%~dp0"
if not exist .venv\Scripts\pythonw.exe (
  echo Chua cai dat - dang chay install.bat ...
  call install.bat
)
start "" .venv\Scripts\pythonw.exe main.py
