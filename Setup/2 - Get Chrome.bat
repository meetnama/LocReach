@echo off
setlocal
title Get Google Chrome
color 0B

echo.
echo  ====================================================
echo   STEP 2 of 4  -  Google Chrome
echo  ====================================================
echo.

REM -- Already installed? (common install paths + PATH) ---------------------
if exist "%ProgramFiles%\Google\Chrome\Application\chrome.exe" goto found
if exist "%ProgramFiles(x86)%\Google\Chrome\Application\chrome.exe" goto found
if exist "%LocalAppData%\Google\Chrome\Application\chrome.exe" goto found
where chrome.exe >nul 2>nul
if not errorlevel 1 goto found

echo  [!] Google Chrome not found.
echo.
echo  Chrome is required for the Google search engine mode
echo  (undetected-chromedriver controls a real Chrome window).
echo.
echo  Opening download page...
echo.

start https://www.google.com/chrome/

echo  After installing Chrome, re-run this bat to confirm OK, then:
echo    3 - Get Docker.bat
echo.
pause
exit /b 1

:found
echo  [OK] Google Chrome is installed.
echo.
echo  Next:  3 - Get Docker.bat
echo.
pause
exit /b 0
