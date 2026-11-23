@echo off
chcp 65001 >nul
title DRVN - Cong Cu Quan Tri Cap Nhat Google Drive
cls
echo ======================================================================
echo    CONG CU QUAN TRI VIEN - DONG GOI VA CAP NHAT TAI GOOGLE DRIVE
echo ======================================================================
python --version >nul 2>&1
if errorlevel 1 (
    echo [LOI] Khong tim thay Python tren may tinh!
    pause
    exit /b
)
python "%~dp0admin_update_tool.py"
pause
