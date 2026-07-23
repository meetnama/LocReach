@echo off
setlocal enabledelayedexpansion
title LocReach - Install / Update
color 0B

echo.
echo  ====================================================
echo   LOCREACH  - Install / Update
echo  ====================================================
echo.

REM Resolve the project folder relative to THIS .bat so the installer works
REM no matter where the Sales_Tool folder is copied (new PC, different drive, etc.)
cd /d "%~dp0..\localization-leads"
echo  Project: %CD%
echo.

REM -- Prerequisite checks (fail early with clear next steps) ---------------
echo  Checking prerequisites...
echo.

set "PREOK=1"

python --version >nul 2>nul
if errorlevel 1 (
    echo  [!!] Python not found. Run  1 - Get Python.bat  first.
    set "PREOK=0"
) else (
    for /f "tokens=2 delims= " %%V in ('python --version 2^>^&1') do set "PYVER=%%V"
    for /f "tokens=1,2 delims=." %%A in ("!PYVER!") do (
        set "PYMAJOR=%%A"
        set "PYMINOR=%%B"
    )
    if !PYMAJOR! LSS 3 (
        echo  [!!] Python !PYVER! is too old. Need 3.11+. Run  1 - Get Python.bat
        set "PREOK=0"
    ) else if !PYMAJOR! EQU 3 if !PYMINOR! LSS 11 (
        echo  [!!] Python !PYVER! is too old. Need 3.11+. Run  1 - Get Python.bat
        set "PREOK=0"
    ) else (
        echo  [OK] Python !PYVER!
    )
)

set "CHROME_OK=0"
if exist "%ProgramFiles%\Google\Chrome\Application\chrome.exe" set "CHROME_OK=1"
if exist "%ProgramFiles(x86)%\Google\Chrome\Application\chrome.exe" set "CHROME_OK=1"
if exist "%LocalAppData%\Google\Chrome\Application\chrome.exe" set "CHROME_OK=1"
where chrome.exe >nul 2>nul
if not errorlevel 1 set "CHROME_OK=1"
if "!CHROME_OK!"=="1" (
    echo  [OK] Google Chrome
) else (
    echo  [!!] Chrome not found. Run  2 - Get Chrome.bat  first.
    set "PREOK=0"
)

docker --version >nul 2>nul
if errorlevel 1 (
    echo  [!!] Docker not found. Run  3 - Get Docker.bat  first.
    set "PREOK=0"
) else (
    docker info >nul 2>nul
    if errorlevel 1 (
        echo  [!!] Docker installed but not running. Open Docker Desktop, then retry.
        set "PREOK=0"
    ) else (
        echo  [OK] Docker running
    )
)

echo.
if "!PREOK!"=="0" (
    echo  Fix the items above, then re-run this installer.
    echo.
    pause
    exit /b 1
)

REM -- [1/3] Virtual environment --------------------------------------------
REM A venv is NOT portable: it bakes in absolute paths + the base Python
REM location of the PC that created it. If this folder was copied from another
REM machine, the existing venv is broken and must be rebuilt. Detect that by
REM checking whether its python.exe actually launches here.
if not exist "venv\Scripts\python.exe" goto makevenv

venv\Scripts\python.exe -c "import sys" >nul 2>nul
if errorlevel 1 (
    echo  [1/3] Existing venv does not run on this PC ^(copied from another
    echo        machine^) - rebuilding it for this computer...
    rmdir /s /q venv
    goto makevenv
)
echo  [1/3] Virtual environment OK.
goto deps

:makevenv
echo  [1/3] Creating virtual environment...
python -m venv venv
if errorlevel 1 (
    echo  [!!] Python not found. Install Python 3.11+ first
    echo  [!!] ^(run "1 - Get Python.bat" and tick "Add Python to PATH"^).
    pause
    exit /b 1
)

:deps
echo.
echo  [2/3] Installing Python packages ^(first run downloads ~300 MB^)...
venv\Scripts\python.exe -m pip install --upgrade pip --quiet
venv\Scripts\python.exe -m pip install -r requirements.txt
if errorlevel 1 (
    echo  [!!] pip install failed. Check your internet connection and retry.
    pause
    exit /b 1
)

echo.
echo  [3/3] Verifying install...
venv\Scripts\python.exe -c "import undetected_chromedriver; print('  undetected-chromedriver OK')"
venv\Scripts\python.exe -c "import streamlit; print('  Streamlit OK')"
venv\Scripts\python.exe -c "import dns.resolver; print('  dnspython OK (email verification)')"
venv\Scripts\python.exe -c "import pdfplumber; print('  pdfplumber OK (PDF email scan)')"

echo.
echo  Creating Desktop + Start Menu shortcuts...
call "%~dp0Create LocReach Shortcut.bat" silent

echo.
echo  ====================================================
echo   Install complete!
echo   Start the app with:  LocReach  (Desktop / Start Menu)
echo   or:  6 - Start LocReach.bat
echo   ^(SearXNG + OpenSERP start automatically.^)
echo   Tip: right-click the Desktop shortcut -^> Pin to taskbar
echo  ====================================================
echo.
pause
