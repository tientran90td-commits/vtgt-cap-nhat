@echo off
chcp 65001 >nul
setlocal EnableExtensions
title Don dep moi truong cu - Recap Studio
echo ============================================================
echo   DON DEP MOI TRUONG CU (Movie Recap AI 1.x, cache, model)
echo   Moi muc deu HOI TRUOC khi xoa. Video da xuat KHONG bi xoa.
echo   Hay TAT app Movie Recap AI / Recap Studio truoc khi chay.
echo ============================================================
echo.

echo [1] Du lieu app cu Movie Recap AI: cai dat, model VSR, Whisper, ffmpeg, du an
echo     %APPDATA%\MovieRecapAI
call :ask && call :del "%APPDATA%\MovieRecapAI"

echo.
echo [2] Thu muc cai app cu Movie Recap AI (co .venv rat nang)
set "OLD="
set /p "OLD=    Keo tha thu muc MovieRecapAI vao day roi Enter (bo trong = bo qua): "
if defined OLD (
  set "OLD=%OLD:"=%"
)
if defined OLD (
  if exist "%OLD%\main.py" if exist "%OLD%\recap" (
    call :ask && call :del "%OLD%"
  ) else (
    echo     Thu muc nay khong phai Movie Recap AI - bo qua cho an toan.
  )
)

echo.
echo [3] File tam cua cac du an Recap Studio (giong doc, doan da dung) - lam lai se tu tao
echo     %APPDATA%\RecapStudio\projects
call :ask && call :del "%APPDATA%\RecapStudio\projects"

echo.
echo [4] Model Whisper / giong AI da tai (Hugging Face) - lan sau dung app se tai lai
echo     %USERPROFILE%\.cache\huggingface
call :ask && call :del "%USERPROFILE%\.cache\huggingface"

echo.
echo [5] Bo nho tam cai thu vien Python (pip cache)
echo     %LOCALAPPDATA%\pip\cache
call :ask && call :del "%LOCALAPPDATA%\pip\cache"

echo.
echo [6] Moi truong Python cua Recap Studio (.venv) - xoa de cai lai sach bang install.bat
echo     %~dp0.venv
call :ask && call :del "%~dp0.venv"

echo.
echo [7] Model AI cua Ollama (moi model vai GB). Recap Studio dung: qwen2.5:7b
where ollama >nul 2>nul
if errorlevel 1 (
  echo     Khong thay Ollama - bo qua.
  goto done
)
ollama list
:ollama_loop
set "M="
set /p "M=    Go ten model muon xoa (vd llama3.1:8b), bo trong = xong: "
if not defined M goto done
ollama rm "%M%"
goto ollama_loop

:done
echo.
echo ============================================================
echo  Xong. Neu da xoa .venv: chay lai install.bat roi run.bat.
echo  Go han Ollama: Settings ^> Apps ^> Ollama ^> Uninstall.
echo ============================================================
pause
exit /b 0

:ask
choice /c YN /n /m "    Xoa muc nay? [Y = co / N = khong] "
if errorlevel 2 exit /b 1
exit /b 0

:del
if exist "%~1" (
  rd /s /q "%~1" 2>nul
  if exist "%~1" (echo     Chua xoa het - co file dang mo, tat app roi chay lai.) else (echo     Da xoa.)
) else (
  echo     Khong co - bo qua.
)
exit /b 0
