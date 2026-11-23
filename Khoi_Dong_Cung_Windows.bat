@echo off
chcp 65001 >nul
title Dang ky Khoi dong cung Windows
cd /d "%~dp0"

set "STARTUP_FOLDER=%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup"
set "SHORTCUT_PATH=%STARTUP_FOLDER%\TroLyCongVan_DRVN.lnk"

powershell -Command "$ws = New-Object -ComObject WScript.Shell; $s = $ws.CreateShortcut('%SHORTCUT_PATH%'); $s.TargetPath = '%~dp0Chay_Tro_Ly_Cong_Van.bat'; $s.WorkingDirectory = '%~dp0'; $s.IconLocation = '%~dp0icon.ico'; $s.Save()"

echo.
echo ======================================================================
echo  DA THIET LAP KHOI DONG CUNG WINDOWS THANH CONG!
echo  Ung dung se tu dong chay ngam moi khi ban bat may tinh.
echo  Phim tat duoc tao tai: %SHORTCUT_PATH%
echo ======================================================================
echo.
pause
