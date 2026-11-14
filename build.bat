@echo off
chcp 65001 >nul
title Сборка tbr PRO (OneFile / OneDir)

set "ROOT=%~dp0"
if "%ROOT:~-1%"=="\" set "ROOT=%ROOT:~0,-1%"

set "ADD_DATA=%ROOT%\web;web"
set "ENTRY=%ROOT%\main.py"

echo ==================================================
echo            СБОРКА tbr PRO (PyInstaller)
echo ==================================================
echo.
echo [1] Только ONEFILE  (-^> dist\onefile\tbr.exe)
echo [2] Только ONEDIR   (-^> dist\onedir\tbr\tbr.exe)
echo [3] ОБА ВАРИАНТА    (-^> разложит по разным папкам)
echo.
set /p mode="Выберите режим [1, 2 или 3]: "

if "%mode%"=="1" goto build_onefile
if "%mode%"=="2" goto build_onedir
if "%mode%"=="3" goto build_onefile

echo.
echo ❌ Неверный выбор! Введите 1, 2 или 3.
pause
exit /b 1

:build_onefile
echo.
echo [1/2] Сборка ONEFILE в dist\onefile\...
if not exist "%ROOT%\build\onefile" mkdir "%ROOT%\build\onefile"
pyinstaller --noconfirm --clean --onefile --windowed --name "tbr" ^
    --distpath "%ROOT%\dist\onefile" ^
    --workpath "%ROOT%\build\onefile" ^
    --specpath "%ROOT%\build\onefile" ^
    --add-data "%ADD_DATA%" "%ENTRY%"
if %ERRORLEVEL% neq 0 goto build_error
if "%mode%"=="3" goto build_onedir
goto done

:build_onedir
echo.
echo [2/2] Сборка ONEDIR в dist\onedir\...
if not exist "%ROOT%\build\onedir" mkdir "%ROOT%\build\onedir"
pyinstaller --noconfirm --clean --onedir --windowed --name "tbr" ^
    --distpath "%ROOT%\dist\onedir" ^
    --workpath "%ROOT%\build\onedir" ^
    --specpath "%ROOT%\build\onedir" ^
    --add-data "%ADD_DATA%" "%ENTRY%"
if %ERRORLEVEL% neq 0 goto build_error
goto done

:done
echo.
echo ==================================================
echo ✅ Сборка успешно завершена!
if not "%mode%"=="2" echo    OneFile: dist\onefile\tbr.exe
if not "%mode%"=="1" echo    OneDir:  dist\onedir\tbr\tbr.exe
echo ==================================================
pause
exit /b 0

:build_error
echo.
echo ❌ Произошла ошибка при компиляции!
pause
exit /b 1