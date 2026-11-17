@echo off
chcp 65001 >nul
rem Chạy LiteLLM trên máy tính Windows cho app ReviewPhim AI (điện thoại cùng wifi).
rem Lần đầu: cài Python 3.10+ (python.org, tích "Add to PATH"), sửa key trong config.yaml.
cd /d "%~dp0"
if not exist ".venv\Scripts\litellm.exe" (
  echo Cai LiteLLM lan dau...
  py -3 -m venv .venv || python -m venv .venv
  ".venv\Scripts\python.exe" -m pip install --upgrade pip
  ".venv\Scripts\python.exe" -m pip install "litellm[proxy]"
)
echo.
echo Dia chi nhap vao app (Cai dat - May chu AI rieng):
for /f "tokens=2 delims=:" %%a in ('ipconfig ^| findstr /c:"IPv4"') do echo    %%a:4000
echo Model viet / dich: chinh      Model nhin anh: nhin-anh
echo Key: master_key trong config.yaml
echo.
".venv\Scripts\litellm.exe" --config config.yaml --host 0.0.0.0 --port 4000
pause
