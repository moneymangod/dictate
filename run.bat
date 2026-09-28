@echo off
rem Starts Dictate in the tray (no console window). The first run creates the venv and installs dependencies.
cd /d "%~dp0"
if not exist .venv (
  py -3.12 -m venv .venv || (echo Python 3.12 is required: https://www.python.org & pause & exit /b 1)
  .venv\Scripts\python.exe -m pip install -r requirements.txt || (pause & exit /b 1)
)
start "" .venv\Scripts\pythonw.exe -m dictate
