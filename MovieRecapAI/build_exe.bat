@echo off
chcp 65001 >nul
cd /d "%~dp0"
call .venv\Scripts\activate.bat
pip install pyinstaller
pyinstaller --noconfirm --clean --windowed --name MovieRecapAI --icon assets\icon.ico ^
  --add-data "assets;assets" ^
  --collect-all faster_whisper --collect-all ctranslate2 --collect-all scenedetect ^
  --collect-all edge_tts --collect-all gtts --collect-all yt_dlp --collect-all imageio_ffmpeg ^
  --collect-all piper --collect-all vieneu --collect-all num2words --collect-submodules pyttsx3 --hidden-import pyttsx3.drivers.sapi5 ^
  main.py
echo.
echo Ban dong goi nam o: dist\MovieRecapAI\MovieRecapAI.exe
echo Co the chep them ffmpeg.exe + ffprobe.exe vao dist\MovieRecapAI\ffmpeg\ de chay tren may khac.
pause
