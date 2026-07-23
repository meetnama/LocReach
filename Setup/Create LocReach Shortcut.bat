@echo off
setlocal
title LocReach - Create Shortcut
color 0B

set "SILENT=0"
if /i "%~1"=="silent" set "SILENT=1"

set "TARGET=%~dp06 - Start LocReach.bat"
set "WORKDIR=%~dp0"

if not exist "%TARGET%" (
    echo  [!!] App launcher not found:
    echo       %TARGET%
    if "%SILENT%"=="0" pause
    exit /b 1
)

powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0_create_shortcut.ps1" -Target "%TARGET%" -WorkDir "%WORKDIR%"
if errorlevel 1 (
    echo  [!!] Failed to create shortcuts.
    if "%SILENT%"=="0" pause
    exit /b 1
)

if "%SILENT%"=="0" (
    echo.
    echo  ====================================================
    echo   Shortcuts created:
    echo     Desktop\LocReach
    echo     Start Menu\LocReach
    echo   If taskbar pin did not appear: right-click the
    echo   Desktop icon -^> Pin to taskbar
    echo  ====================================================
    echo.
    pause
)
exit /b 0
