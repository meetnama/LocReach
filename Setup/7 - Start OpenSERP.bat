@echo off
setlocal enabledelayedexpansion
title OpenSERP - Free SERP Fallback
color 0B

set "SILENT=0"
if /i "%~1"=="silent" set "SILENT=1"
if /i "%~1"=="auto" set "SILENT=1"

if "!SILENT!"=="0" (
    echo.
    echo  ====================================================
    echo   OpenSERP  - Free self-hosted SERP API
    echo  ====================================================
    echo.
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

REM -- Does a container named "openserp" already exist? ----------------------
docker inspect openserp >nul 2>nul
if errorlevel 1 goto create

echo  [OK] Starting existing OpenSERP container...
docker start openserp >nul
goto done

:create
echo  [1/2] Pulling OpenSERP image (first time only)...
docker pull karust/openserp:latest

echo.
echo  [2/2] Creating OpenSERP container on port 7000...
docker run -d --name openserp --restart unless-stopped -p 7000:7000 karust/openserp:latest serve -a 0.0.0.0 -p 7000
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
echo   OpenSERP running at: http://localhost:7000
echo   Docs: http://localhost:7000/docs
if "!SILENT!"=="0" (
    echo   Or just start LocReach — it launches OpenSERP automatically.
)
echo  ====================================================
echo.
if "!SILENT!"=="0" pause
exit /b 0
