@echo off
REM Build MusicPlayer.exe using PyInstaller
set PYINSTALLER_CMD=pyinstaller
set MAIN_SCRIPT=app.py
set EXE_NAME=MusicPlayer

REM Clean previous build
if exist dist rd /s /q dist
if exist build rd /s /q build
if exist %EXE_NAME%.spec del /q %EXE_NAME%.spec

REM Build
%PYINSTALLER_CMD% --onefile --windowed --hidden-import PySide6 --name %EXE_NAME% %MAIN_SCRIPT%

REM Check result
if exist dist\%EXE_NAME%.exe (
    echo [SUCCESS] dist\%EXE_NAME%.exe built.
) else (
    echo [ERROR] Build failed.
)
