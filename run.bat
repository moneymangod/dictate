@echo off
rem Starts Dictate in the tray (no console window). The first run creates the venv and installs dependencies;
rem if that was interrupted or failed, the next run picks up where it left off.
cd /d "%~dp0"
if not exist .venv\.installed (
  if not exist .venv\Scripts\python.exe (
    py -3.12 -m venv .venv || (echo Python 3.12 is required: https://www.python.org & pause & exit /b 1)
  )
  .venv\Scripts\python.exe -m pip install -r requirements.txt || (echo Installing the dependencies failed. Fix the error above and run again. & pause & exit /b 1)
  echo done> .venv\.installed
)
start "" .venv\Scripts\pythonw.exe -m dictate
