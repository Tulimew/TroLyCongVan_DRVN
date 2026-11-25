@echo off
chcp 65001 >nul
title DRVN - Cong Cu Quan Tri Cap Nhat Google Drive
cls
echo ======================================================================
echo    CONG CU QUAN TRI VIEN - DONG GOI VA CAP NHAT TAI GOOGLE DRIVE
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
pause
