@echo off
setlocal
cd /d "%~dp0"

echo ============================================================
echo   KODA - Zero-Cost Jarvis AI OS ($0 OpenCode Model Router)
echo ============================================================
echo.

where python >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Python was not found in PATH. Install Python 3.11+ first.
    pause
    exit /b 1
)

echo [1/3] Running workstation doctor check...
python -m koda.cli doctor
if errorlevel 1 (
    echo [WARN] OpenCode binary not found at default path. Set OPENCODE_EXE in .env if needed.
)

echo [2/3] Launching Koda FastAPI Gateway + Managed OpenCode Serve on http://127.0.0.1:8765 ...
start "Koda Gateway" cmd /k "cd /d ""%~dp0"" && python -m koda.cli serve --host 127.0.0.1 --port 8765"

timeout /t 4 /nobreak >nul

echo [3/3] Opening Spatial Command Deck and Launching Dynamic Island Pill...
start "" "http://127.0.0.1:8765/"
start "Koda Dynamic Island" cmd /k "cd /d ""%~dp0"" && python -m koda.cli island"

echo.
echo Koda launched. Close the gateway/island windows to stop cleanly.
endlocal
