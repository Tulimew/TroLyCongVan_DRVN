@echo off
chcp 65001 >nul
title Dong Bo Len Git - Tro Ly Cong Van DRVN
cd /d "%~dp0"

echo ======================================================================
echo       DONG BO CAP NHAT LEN GITHUB (TroLyCongVan_DRVN)
echo ======================================================================
echo.

git status --short
echo.
set /p msg="Nhap noi dung ghi chu cap nhat (de trong se dung mac dinh): "
if "%msg%"=="" set msg=Update: Cap nhat he thong Tro Ly Cong Van DRVN

echo.
echo Dang them tep vao Git...
git add .
echo Dang tao commit...
git commit -m "%msg%"
echo Dang day len GitHub...
git push origin main

echo.
if %errorlevel% equ 0 (
    echo ======================================================================
    echo  [THANH CONG] Da dong bo toan bo ma nguon len GitHub thanh cong!
    echo  Repository: https://github.com/Tulimew/TroLyCongVan_DRVN
    echo ======================================================================
) else (
    echo ======================================================================
    echo  [THAT BAI] Co loi xay ra khi dong bo len GitHub.
    echo ======================================================================
)
echo.
pause
