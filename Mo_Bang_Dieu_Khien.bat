@echo off
title Bang Dieu Khien DRVN
cd /d "C:\Users\tangt\.gemini\antigravity\scratch\drvn-app"
echo Dang khoi dong Bang dieu khien Cong van DRVN...
"C:\Users\tangt\AppData\Local\Programs\Python\Python312\python.exe" main.py
if %ERRORLEVEL% NEQ 0 (
    echo.
    echo [LOI] Khong the khoi dong. Chi tiet loi o tren.
    pause
)
