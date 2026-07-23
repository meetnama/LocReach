@echo off
setlocal enabledelayedexpansion
title SearXNG - Local Search Engine
color 0E

set "SILENT=0"
if /i "%~1"=="silent" set "SILENT=1"
if /i "%~1"=="auto" set "SILENT=1"

if "!SILENT!"=="0" (
    echo.
    echo  ====================================================
    echo   SEARXNG  - Local Search Engine
    echo  ====================================================
    echo.
)

REM Settings live in <repo>\searxng\settings.yml  (sibling of this Setup folder).
REM Resolve it relative to THIS .bat so the launcher works no matter where
REM the folder lives, then convert to forward-slash form for Docker.
for %%I in ("%~dp0..\searxng") do set "SEARXNG_DIR=%%~fI"
set "SEARXNG_MOUNT=!SEARXNG_DIR:\=/!"

if not exist "!SEARXNG_DIR!\settings.yml" (
    echo  [!!] settings.yml not found in:
    echo       !SEARXNG_DIR!
    echo  [!!] Make sure the searxng folder sits next to the Setup folder.
    if "!SILENT!"=="0" (
        echo.
        pause
    )
    exit /b 1
)

REM -- Check Docker is installed --------------------------------------------
docker --version >nul 2>nul
if errorlevel 1 (
    echo  [!!] Docker Desktop not found.
    echo  [!!] Download from: https://www.docker.com/products/docker-desktop
    if "!SILENT!"=="0" (
        echo.
        pause
    )
    exit /b 1
)

REM -- Check Docker daemon is running ---------------------------------------
docker info >nul 2>nul
if errorlevel 1 (
    echo  [!!] Docker is installed but not running.
    echo  [!!] Open Docker Desktop and wait for it to start, then try again.
    if "!SILENT!"=="0" (
        echo.
        pause
    )
    exit /b 1
)

REM -- Does a container named "searxng" already exist? ----------------------
docker inspect searxng >nul 2>nul
if errorlevel 1 goto create

REM Container exists - does it still use the OLD (wrong) localization-leads mount?
REM findstr sets errorlevel 0 when the old path is present, 1 when it is not.
docker inspect --format "{{range .Mounts}}{{.Source}}{{end}}" searxng 2>nul | findstr /i "localization-leads" >nul
if errorlevel 1 (
    echo  [OK] Starting existing SearXNG container...
    docker start searxng >nul
    goto done
)

echo  [!] Existing container has the old volume mount (localization-leads\searxng).
echo  [!] Recreating it to use the correct path...
docker stop searxng >nul 2>nul
docker rm searxng >nul

:create
echo  [1/2] Pulling SearXNG image (first time only, ~200 MB)...
docker pull searxng/searxng

echo.
echo  [2/2] Creating SearXNG container...
echo       mount: !SEARXNG_MOUNT!
docker run -d --name searxng --restart unless-stopped -p 8888:8080 -v "!SEARXNG_MOUNT!:/etc/searxng:rw" searxng/searxng
if errorlevel 1 (
    echo  [!!] Failed to start. Check Docker Desktop is running.
    if "!SILENT!"=="0" pause
    exit /b 1
)

:done
if "!SILENT!"=="0" ping -n 5 127.0.0.1 >nul
if "!SILENT!"=="1" ping -n 3 127.0.0.1 >nul
echo.
echo  ====================================================
echo   SearXNG running at: http://localhost:8888
echo   Settings file: !SEARXNG_DIR!\settings.yml
if "!SILENT!"=="0" (
    echo   Keep Docker Desktop open while using SearXNG.
    echo   Or just start LocReach — it launches SearXNG automatically.
)
echo  ====================================================
echo.
if "!SILENT!"=="0" pause
exit /b 0
