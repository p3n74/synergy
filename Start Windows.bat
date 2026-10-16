@echo off
setlocal
cd /d "%~dp0"
set PYTHONUNBUFFERED=1

if not exist "%USERPROFILE%\.homesynergy\config.json" (
  echo Missing %USERPROFILE%\.homesynergy\config.json
  echo Copy the Mac file ~/.homesynergy/config.json to that folder, then double-click this again.
  pause
  exit /b 1
)

where py >nul 2>&1
if %ERRORLEVEL%==0 (
  py -3 -m homesynergy.win_agent
  goto stopped
)
where python >nul 2>&1
if %ERRORLEVEL%==0 (
  python -m homesynergy.win_agent
  goto stopped
)

echo Python 3 was not found.
echo Install it from https://www.python.org/downloads/ and check "Add python.exe to PATH".
:stopped
echo.
pause
