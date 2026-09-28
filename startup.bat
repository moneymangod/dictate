@echo off
rem Starts Dictate hidden in the tray every time you log in to Windows.
rem   startup.bat       turn it on
rem   startup.bat off   turn it off
cd /d "%~dp0"
set "LINK=%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup\Dictate.lnk"
if /i "%~1"=="off" (
  del "%LINK%" 2>nul
  echo Dictate will no longer start when you log in.
  exit /b 0
)
if not exist .venv\Scripts\pythonw.exe (echo Run run.bat once first to set up Dictate. & pause & exit /b 1)
powershell -NoProfile -Command "$s = (New-Object -ComObject WScript.Shell).CreateShortcut($env:LINK); $s.TargetPath = '%~dp0.venv\Scripts\pythonw.exe'; $s.Arguments = '-m dictate --hidden'; $s.WorkingDirectory = '%~dp0'; $s.Description = 'Dictate: hold Right Shift to dictate'; $s.Save()" || (pause & exit /b 1)
echo Dictate will now start hidden in the tray when you log in. To undo: startup.bat off
