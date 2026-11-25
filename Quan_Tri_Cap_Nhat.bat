@echo off
chcp 65001 >nul
title DRVN - Tao Ban Cap Nhat
cls
echo ======================================================================
echo    CONG CU QUAN TRI VIEN - DONG GOI VA TAO BAN CAP NHAT
echo ======================================================================
set "PY_CMD=python"
if exist "%~dp0runtime\python.exe" set "PY_CMD=%~dp0runtime\python.exe"
"%PY_CMD%" --version >nul 2>&1
if errorlevel 1 (
    echo [LOI] Khong tim thay Python tren may tinh!
    pause
    exit /b
)
"%PY_CMD%" "%~dp0admin_update_tool.py" %*
set "DRVN_RELEASE_EXIT=%ERRORLEVEL%"
pause
exit /b %DRVN_RELEASE_EXIT%
