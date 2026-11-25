@echo off
chcp 65001 >nul
title Bang Dieu Khien DRVN
cd /d "%~dp0"

echo Dang khoi dong Bang dieu khien Cong van DRVN...

if exist "%~dp0runtime\python.exe" (
    "%~dp0runtime\python.exe" "%~dp0main.py"
    goto :check_err
)

where python >nul 2>nul
if %errorlevel% equ 0 (
    python main.py
    goto :check_err
)

where py >nul 2>nul
if %errorlevel% equ 0 (
    py main.py
    goto :check_err
)

echo.
echo [LOI] Khong tim thay Python tren he thong. Vui long cai dat Python 3.10+
pause
exit /b 1

:check_err
if %ERRORLEVEL% NEQ 0 (
    echo.
    echo [LOI] Khong the khoi dong. Chi tiet loi o tren.
    pause
)
