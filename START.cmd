@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0"
if not exist "runtime\pythonw.exe" (
  echo Λείπει ο φάκελος runtime. Αποσυμπιέστε ΟΛΟ το ZIP σε φάκελο και ξαναδοκιμάστε.
  pause
  exit /b 1
)
rem Ανοίγει την εφαρμογή σε δικό της παράθυρο, χωρίς κονσόλα.
start "" "runtime\pythonw.exe" -X utf8 "src\server.py"
exit /b 0
