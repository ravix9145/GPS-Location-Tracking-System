@echo off
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo Creating Python virtual environment...
  py -m venv .venv
  if errorlevel 1 goto error
)
call ".venv\Scripts\activate.bat"
echo Installing or checking project dependencies...
python -m pip install -r requirements.txt
if errorlevel 1 goto error
echo.
echo Starting GPS Location Tracking Simulation System...
echo Open http://127.0.0.1:5000 in your browser.
python app.py
goto end
:error
echo.
echo Setup failed. Check that Python is installed and that your internet connection is working.
pause
:end
