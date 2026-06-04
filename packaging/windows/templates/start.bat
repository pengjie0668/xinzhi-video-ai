@echo off
chcp 65001 >nul
setlocal enabledelayedexpansion

echo ========================================
echo   芯智未来 AI 视频引擎 - Windows Launcher
echo ========================================
echo.

:: Set environment variables
set "PYTHON_HOME=%~dp0python\python311"
set "PATH=%PYTHON_HOME%;%PYTHON_HOME%\Scripts;%~dp0tools\ffmpeg\bin;%PATH%"
set "PROJECT_ROOT=%~dp0xinzhi-video-ai"

:: Change to project directory
cd /d "%PROJECT_ROOT%"

:: Set PYTHONPATH to project root for module imports
set "PYTHONPATH=%PROJECT_ROOT%"

:: Set XINZHI_VIDEO_AI_ROOT environment variable for reliable path resolution
set "XINZHI_VIDEO_AI_ROOT=%PROJECT_ROOT%"

:: Start Web UI
echo [Starting] Launching 芯智未来 AI 视频引擎 Web UI...
echo Browser will open automatically.
echo.
echo Note: Configure API keys and settings in the Web UI.
echo Press Ctrl+C to stop the server
echo ========================================
echo.

"%PYTHON_HOME%\python.exe" -m streamlit run web\app.py

if errorlevel 1 (
    echo.
    echo [ERROR] Failed to start. Please check:
    echo   1. Python is properly installed
    echo   2. Dependencies are installed
    echo.
    pause
)
