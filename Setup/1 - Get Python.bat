@echo off
setlocal enabledelayedexpansion
title Get Python 3.11+
color 0B

echo.
echo  ====================================================
echo   STEP 1 of 4  -  Python 3.11+
echo  ====================================================
echo.

REM -- Already installed? ---------------------------------------------------
python --version >nul 2>nul
if errorlevel 1 goto missing

for /f "tokens=2 delims= " %%V in ('python --version 2^>^&1') do set "PYVER=%%V"
for /f "tokens=1,2 delims=." %%A in ("!PYVER!") do (
    set "PYMAJOR=%%A"
    set "PYMINOR=%%B"
)
if not defined PYMAJOR goto missing
if !PYMAJOR! LSS 3 goto too_old
if !PYMAJOR! EQU 3 if !PYMINOR! LSS 11 goto too_old

echo  [OK] Python !PYVER! found on PATH.
echo.
echo  Next:  2 - Get Chrome.bat
echo.
pause
exit /b 0

:too_old
echo  [!] Python !PYVER! found, but LocReach needs 3.11 or newer.
echo.
goto offer

:missing
echo  [!] Python 3.11+ not found on PATH.
echo.

:offer
echo  Python is required to run LocReach.
echo  Download and install Python 3.11 or newer.
echo.
echo  IMPORTANT during install:
echo    [x] Check "Add Python to PATH"
echo    [x] Check "Install for all users" (recommended)
echo.
echo  Opening download page...
echo.

start https://www.python.org/downloads/

echo  After installing, close and reopen this window, then re-run
echo    1 - Get Python.bat
echo  to confirm it is OK. Then run:
echo    2 - Get Chrome.bat
echo.
pause
exit /b 1
