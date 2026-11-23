@echo off
chcp 65001 >nul
cd /d "%~dp0"
title Co Vua LIVE - Cai moi truong
echo ================================================
echo    CO VUA LIVE - TU DONG TAI VA CAI MOI TRUONG
echo ================================================
echo  (can Internet; cai Node.js + thu vien cua game)
echo.

rem ---- Buoc 1: Node.js (can ban 20 tro len, co kem npm) ----
if exist "%ProgramFiles%\nodejs\npm.cmd" set "PATH=%ProgramFiles%\nodejs;%PATH%"
where node >nul 2>nul
if errorlevel 1 goto installnode
where npm >nul 2>nul
if errorlevel 1 goto installnode
node -e "process.exit(Number(process.versions.node.split('.')[0])>=20?0:1)" >nul 2>nul
if errorlevel 1 goto installnode
echo [1/2] Node.js va npm da co san. Bo qua.
goto step2

:installnode
echo [1/2] Dang tai va cai Node.js (khoang 1-3 phut). Neu Windows hoi quyen, bam Yes.
where winget >nul 2>nul
if errorlevel 1 goto direct
winget install -e --id OpenJS.NodeJS.LTS --silent --accept-package-agreements --accept-source-agreements
if exist "%ProgramFiles%\nodejs\npm.cmd" set "PATH=%ProgramFiles%\nodejs;%PATH%"
node -e "process.exit(Number(process.versions.node.split('.')[0])>=20?0:1)" >nul 2>nul
if errorlevel 1 goto direct
where npm >nul 2>nul
if not errorlevel 1 goto recheck

:direct
echo Dang tai bo cai Node.js truc tiep tu nodejs.org ...
powershell -NoProfile -ExecutionPolicy Bypass -Command "$ErrorActionPreference='Stop'; [Net.ServicePointManager]::SecurityProtocol=[Net.SecurityProtocolType]::Tls12; $j=Invoke-RestMethod 'https://nodejs.org/dist/index.json'; $v=($j | Where-Object { $_.lts } | Select-Object -First 1).version; $f='node-'+$v+'-x64.msi'; $out=Join-Path $env:TEMP $f; Invoke-WebRequest -UseBasicParsing ('https://nodejs.org/dist/'+$v+'/'+$f) -OutFile $out; Start-Process msiexec.exe -ArgumentList ('/i '+[char]34+$out+[char]34+' /passive /norestart') -Wait"
if exist "%ProgramFiles%\nodejs\npm.cmd" set "PATH=%ProgramFiles%\nodejs;%PATH%"

:recheck
where node >nul 2>nul
if errorlevel 1 goto nodefail
where npm >nul 2>nul
if errorlevel 1 goto nodefail
node -e "process.exit(Number(process.versions.node.split('.')[0])>=20?0:1)" >nul 2>nul
if errorlevel 1 goto nodefail
echo Da cai xong Node.js.

rem ---- Buoc 2: thu vien cua game ----
:step2
echo [2/2] Dang tai thu vien cua game (khoang 1-2 phut)...
call npm install --no-audit --no-fund
if errorlevel 1 goto npmfail

echo.
echo ================================================
echo  XONG! Da tai het moi truong ve may.
echo  Bay gio hay bam dup CHAY-THU-DEMO.bat de thu.
echo ================================================
if /i "%~1"=="tudong" exit /b 0
pause
exit /b 0

:nodefail
echo.
echo Khong tu cai duoc Node.js. Hay mo https://nodejs.org , tai ban LTS, cai xong roi chay lai file nay.
start "" https://nodejs.org/en/download
if /i "%~1"=="tudong" exit /b 1
pause
exit /b 1

:npmfail
echo.
echo Tai thu vien that bai. Kiem tra mang Internet roi chay lai file nay.
if /i "%~1"=="tudong" exit /b 1
pause
exit /b 1
