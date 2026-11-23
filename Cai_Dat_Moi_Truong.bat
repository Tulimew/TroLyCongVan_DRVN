@echo off
chcp 65001 >nul
title Cai Dat Moi Truong - Tro Ly Cong Van DRVN
cd /d "%~dp0"

echo ======================================================================
echo    HE THONG TRO LY QUAN LY ^& THEO DOI CONG VAN DRVN
echo    Trinh cai dat tu dong moi truong ^& thu vien
echo ======================================================================
echo.

where python >nul 2>nul
if %errorlevel% equ 0 (
    python setup_env.py
    goto :end
)

where py >nul 2>nul
if %errorlevel% equ 0 (
    py setup_env.py
    goto :end
)

cls
echo ======================================================================
echo  [CHU Y] MAY TINH CHUA CAI DAT PYTHON!
echo ======================================================================
echo.
echo De chay duoc ung dung tren may tinh moi, ban can cai dat Python:
echo.
echo 1. Tai bo cai dat Python chinh thuc tai:
echo    https://www.python.org/downloads/
echo.
echo 2. QUAN TRONG: Khi chay file cai dat Python, hay tich chon vao o:
echo    [x] "Add Python to PATH" (o duoi cung cua so dau tien)
echo.
echo 3. Sau khi cai dat xong, hay mo lai file "Cai_Dat_Moi_Truong.bat" nay!
echo ======================================================================
echo.
pause
exit /b

:end
pause
exit /b
