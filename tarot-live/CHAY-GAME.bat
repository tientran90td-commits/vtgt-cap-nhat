@echo off
chcp 65001 >nul
cd /d "%~dp0"
title Tarot LIVE
echo ================================================
echo    TAROT LIVE v1.0 - tro choi boi bai Tarot cho TikTok LIVE
echo ================================================
echo.

if exist "%ProgramFiles%\nodejs\npm.cmd" set "PATH=%ProgramFiles%\nodejs;%PATH%"
where node >nul 2>nul
if errorlevel 1 goto needenv
where npm >nul 2>nul
if errorlevel 1 goto needenv
goto envok
:needenv
call "%~dp0CAI-MOI-TRUONG.bat" tudong
where node >nul 2>nul
if errorlevel 1 goto nonode
where npm >nul 2>nul
if errorlevel 1 goto nonode
:envok

if exist "ten-tiktok.txt" goto havename
:askname
echo Nhap ID TikTok cua ban (khong co dau @), roi bam Enter.
set "TTNAME="
set /p TTNAME=ID TikTok: 
if "%TTNAME%"=="" goto askname
>"ten-tiktok.txt" <nul set /p ="%TTNAME%"
:havename

if exist "node_modules" goto havemodules
echo Lan dau chay: dang cai thu vien, vui long cho 1-2 phut...
call npm install --no-audit --no-fund
if errorlevel 1 goto npmfail
:havemodules

echo.
echo Dang mo bang dieu khien... (dong cua so den nay de tat game)
start "" /min "%~dp0mo-bang-dieu-khien.bat"
set "RUNS=0"
:run
node src\server.js %1
if errorlevel 3 if not errorlevel 4 goto updated
if errorlevel 1 goto crashed
exit /b

:updated
echo.
echo Vua cap nhat xong, dang mo lai game...
timeout /t 2 /nobreak >nul
set "RUNS=0"
goto run

:crashed
set /a RUNS+=1
if %RUNS% GEQ 10 goto giveup
echo.
echo Game gap loi, tu khoi dong lai sau 5 giay... (lan %RUNS%/10). Muon tat han thi dong cua so nay.
timeout /t 5 /nobreak >nul
goto run

:giveup
echo.
echo Game dung nhieu lan lien tiep. Hay chup man hinh nay gui cho nguoi ho tro.
pause
exit /b

:nonode
echo CHUA CAI NODE.JS. Dang mo trang tai ve, hay chon ban LTS, cai xong roi chay lai file nay.
start "" https://nodejs.org/en/download
pause
exit /b

:npmfail
echo Cai thu vien that bai. Kiem tra mang Internet roi chay lai.
pause
exit /b
