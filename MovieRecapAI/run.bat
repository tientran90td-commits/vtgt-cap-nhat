@echo off
cd /d "%~dp0"
if not exist .venv (
  echo Chua cai dat. Dang chay install.bat ...
  call install.bat
)
start "" .venv\Scripts\pythonw.exe main.py
