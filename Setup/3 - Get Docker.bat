@echo off
setlocal
title Get Docker Desktop
color 0B

echo.
echo  ====================================================
echo   STEP 3 of 4  -  Docker Desktop
echo  ====================================================
echo.
echo  Docker is required for SearXNG + OpenSERP fallbacks.
echo  LocReach will start those automatically with the app.
echo.

REM -- CLI present? ---------------------------------------------------------
docker --version >nul 2>nul
if errorlevel 1 goto missing

for /f "tokens=*" %%V in ('docker --version 2^>^&1') do set "DKVER=%%V"
echo  [OK] Docker CLI found: %DKVER%

REM -- Daemon running? ------------------------------------------------------
docker info >nul 2>nul
if errorlevel 1 (
    echo  [!] Docker Desktop is installed but not running.
    echo  [!] Open Docker Desktop and wait until it says "Running",
    echo      then re-run this bat to confirm.
    echo.
    pause
    exit /b 1
)

echo  [OK] Docker daemon is running.
echo.
echo  Next:  4 - Install LocReach.bat
echo.
pause
exit /b 0

:missing
echo  [!] Docker Desktop not found.
echo.
echo  Opening download page...
echo.

start https://www.docker.com/products/docker-desktop/

echo  IMPORTANT after installing Docker:
echo    - Open Docker Desktop and wait until it says "Running"
echo    - Re-run this bat to confirm OK
echo    - Then run  4 - Install LocReach.bat
echo.
pause
exit /b 1
