@echo off
cd /d "%~dp0"
powershell -NoProfile -ExecutionPolicy Bypass -Command "Start-Process powershell -Verb RunAs -Wait -ArgumentList '-NoProfile','-ExecutionPolicy','Bypass','-File','%~dp0windows\install-startup.ps1'"
echo.
echo If Windows asked for approval, HomeSynergy is now set to start at logon.
pause
