@echo off
chcp 65001 >nul
title Сборка tbr PRO

echo ==================================================
echo              СБОРКА tbr PRO (PyInstaller)
echo ==================================================
echo.
echo [1] ONEFILE (один цельный .exe)
echo [2] ONEDIR  (папка с файлами, быстрее запускается)
echo.
set /p mode="Выберите режим [1 или 2]: "

set ADD_DATA=--add-data "web/templates;web/templates"

if "%mode%"=="1" (
    echo.
    echo Запуск сборки ONEFILE...
    pyinstaller --noconfirm --onedir --windowed --name "tbr" %ADD_DATA% main.py
) else (
    echo.
    echo Запуск сборки ONEDIR...
    pyinstaller --noconfirm --onedir --windowed --name "tbr" %ADD_DATA% main.py
)

if %ERRORLEVEL% equ 0 (
    echo.
    echo ==================================================
    echo ✅ Сборка успешно завершена в папку dist!
    echo ==================================================
) else (
    echo.
    echo ❌ Произошла ошибка при компиляции!
)

pause