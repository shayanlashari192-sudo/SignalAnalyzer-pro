@echo off
setlocal
cd /d "%~dp0"
echo ================================================
echo SIGNAL ANALYZER PRO - MT5 BRIDGE
echo ================================================
echo.
py -3.12 --version >nul 2>&1
if errorlevel 1 (
  echo Python 3.12 64-bit was not found.
  echo Install Python 3.12 from https://www.python.org/downloads/windows/
  echo During setup, enable Add Python to PATH.
  pause
  exit /b 1
)
echo Installing required Python packages...
py -3.12 -m pip install --upgrade pip
py -3.12 -m pip install -r requirements.txt
if errorlevel 1 (
  echo Package installation failed. Check your internet connection and Python installation.
  pause
  exit /b 1
)
echo.
echo Starting bridge at http://0.0.0.0:8765
 echo Keep this window and MetaTrader 5 open while using the app.
py -3.12 -m uvicorn server:app --host 0.0.0.0 --port 8765
pause
