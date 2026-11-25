@echo off
chcp 65001 >nul
title Tro Ly Cong Van DRVN
cd /d "%~dp0"

if exist "%~dp0runtime\pythonw.exe" (
    start "" "%~dp0runtime\pythonw.exe" "%~dp0main.py"
    exit /b
)

where python >nul 2>nul
if %errorlevel% neq 0 (
    where py >nul 2>nul
    if %errorlevel% neq 0 goto :no_python
    set "PY_CMD=py"
) else (
    set "PY_CMD=python"
)

%PY_CMD% -c "import PyQt6, pymupdf, requests, bs4, cryptography" >nul 2>nul
if %errorlevel% neq 0 goto :need_install

where pythonw >nul 2>nul
if %errorlevel% equ 0 (
    start "" pythonw main.py
    exit /b
) else (
    start "" %PY_CMD% main.py
    exit /b
)

:need_install
cls
echo ======================================================================
echo  [THONG BAO] Phat hien may tinh chua co du thu vien de chay ung dung!
echo  He thong dang tu dong mo trinh kiem tra va cai dat thu vien...
echo ======================================================================
echo.
%PY_CMD% setup_env.py
echo.
echo Dang khoi dong Tro ly Cong van DRVN...
where pythonw >nul 2>nul
if %errorlevel% equ 0 (
    start "" pythonw main.py
) else (
    start "" %PY_CMD% main.py
)
exit /b

:no_python
cls
echo ======================================================================
echo  [CHU Y] MAY TINH CHUA CAI DAT PYTHON!
echo ======================================================================
echo.
echo Vui long chay file "Cai_Dat_Moi_Truong.bat" de duoc huong dan cai dat.
echo Hoac tai Python tai: https://www.python.org/downloads/
echo (Nho tich chon: Add Python to PATH khi cai dat).
echo ======================================================================
echo.
pause
exit /b
