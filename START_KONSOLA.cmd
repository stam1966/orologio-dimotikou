@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0"
rem Εκκίνηση με κονσόλα: για διάγνωση προβλημάτων. Το παράθυρο πρέπει να μείνει ανοικτό.
"runtime\python.exe" -X utf8 "src\preflight.py"
if errorlevel 1 (
  echo Η εκκίνηση απέτυχε. Δείτε το data\diagnostics.txt
  pause
  exit /b 1
)
"runtime\python.exe" -X utf8 "src\server.py" --stay
if errorlevel 1 pause
