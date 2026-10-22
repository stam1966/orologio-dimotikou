@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0"
"runtime\python.exe" -X utf8 "src\preflight.py"
"runtime\python.exe" -X utf8 -m unittest discover -s tests -v
pause
