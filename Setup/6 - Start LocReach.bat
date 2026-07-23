@echo off
title LocReach Lead Discovery
color 0A

echo.
echo  ====================================================
echo   LOCREACH  - Lead Discovery (3-Step Pipeline)
echo  ====================================================
echo.

REM -- Auto-start search backends (SearXNG + OpenSERP) ----------------------
echo  Starting search backends (SearXNG + OpenSERP)...
echo  ^(Docker Desktop must already be running.^)
echo.
call "%~dp05 - Start SearXNG.bat" silent
if errorlevel 1 (
    echo  [!] SearXNG did not start. Google/Chrome search may still work.
    echo.
)
call "%~dp07 - Start OpenSERP.bat" silent
if errorlevel 1 (
    echo  [!] OpenSERP did not start. Other engines may still work.
    echo.
)

cd /d "%~dp0..\localization-leads"

if not exist "venv\Scripts\pythonw.exe" (
    echo  [!!] LocReach is not installed yet.
    echo  [!!] Run  4 - Install LocReach.bat  first.
    echo.
    pause
    exit /b 1
)

:: Kill any leftover process still holding port 8501
for /f "tokens=5" %%a in ('netstat -ano 2^>nul ^| findstr ":8501 "') do (
    taskkill /f /pid %%a >nul 2>nul
)
ping -n 2 127.0.0.1 >nul

echo  Starting LocReach...
echo  Browser will open automatically in a few seconds.
echo  This window will close automatically -- the app keeps running
echo  in the background until you close the browser tab.
echo.
ping -n 3 127.0.0.1 >nul

:: pythonw.exe = no console window; app runs detached in the background.
:: Logs go to localization-leads\logs\run_app.log. Closing the browser tab
:: stops the heartbeat, which the watchdog in run_app.py detects to self-exit.
start "" "venv\Scripts\pythonw.exe" run_app.py

exit
