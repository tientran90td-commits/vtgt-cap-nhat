@echo off
timeout /t 3 /nobreak >nul
start "" msedge --autoplay-policy=no-user-gesture-required --new-window http://localhost:3000
if errorlevel 1 start "" http://localhost:3000
exit
