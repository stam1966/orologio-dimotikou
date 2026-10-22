@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0"
title Εγκατάσταση: Ωρολόγιο Δημοτικού
if not exist "%~dp0runtime\pythonw.exe" (
  echo.
  echo  Η εγκατάσταση πρέπει να γίνει από φάκελο, όχι μέσα από το ZIP.
  echo  Κάντε δεξί κλικ στο ZIP, «Εξαγωγή όλων...», και τρέξτε ξανά την
  echo  ΕΓΚΑΤΑΣΤΑΣΗ.cmd από τον φάκελο που θα δημιουργηθεί.
  echo.
  pause
  exit /b 1
)
set "OROLOGIO_DIR=%LOCALAPPDATA%\Programs\OrologioDimotikou"
echo.
echo  Εγκατάσταση του «Ωρολόγιο Δημοτικού» στον υπολογιστή σας...
echo  Φάκελος: %OROLOGIO_DIR%
echo  Αν υπάρχει ήδη, ενημερώνεται· τα δεδομένα σας διατηρούνται.
echo.
powershell -NoProfile -ExecutionPolicy Bypass -EncodedCommand RwBlAHQALQBQAHIAbwBjAGUAcwBzACAAcAB5AHQAaABvAG4AdwAsAHAAeQB0AGgAbwBuACAALQBFAHIAcgBvAHIAQQBjAHQAaQBvAG4AIABTAGkAbABlAG4AdABsAHkAQwBvAG4AdABpAG4AdQBlACAAfAAgAFcAaABlAHIAZQAtAE8AYgBqAGUAYwB0ACAAewAgACQAXwAuAFAAYQB0AGgAIAAtAGEAbgBkACAAJABfAC4AUABhAHQAaAAuAFMAdABhAHIAdABzAFcAaQB0AGgAKAAkAGUAbgB2ADoATwBSAE8ATABPAEcASQBPAF8ARABJAFIAKQAgAH0AIAB8ACAAUwB0AG8AcAAtAFAAcgBvAGMAZQBzAHMAIAAtAEYAbwByAGMAZQAgAC0ARQByAHIAbwByAEEAYwB0AGkAbwBuACAAUwBpAGwAZQBuAHQAbAB5AEMAbwBuAHQAaQBuAHUAZQAKAA== >nul 2>&1
robocopy "%~dp0." "%OROLOGIO_DIR%" /E /XD data __pycache__ /R:2 /W:1 /NFL /NDL /NJH /NJS /NP >nul
if errorlevel 8 (
  echo  Η αντιγραφή απέτυχε. Κλείστε την εφαρμογή αν είναι ανοικτή και ξαναδοκιμάστε.
  pause
  exit /b 1
)
if not exist "%OROLOGIO_DIR%\data" mkdir "%OROLOGIO_DIR%\data"
powershell -NoProfile -ExecutionPolicy Bypass -EncodedCommand JAB0AD0AJABlAG4AdgA6AE8AUgBPAEwATwBHAEkATwBfAEQASQBSAAoAJABzAGgAPQBOAGUAdwAtAE8AYgBqAGUAYwB0ACAALQBDAG8AbQBPAGIAagBlAGMAdAAgAFcAUwBjAHIAaQBwAHQALgBTAGgAZQBsAGwACgBmAG8AcgBlAGEAYwBoACgAJABkAGkAcgAgAGkAbgAgAEAAKABbAEUAbgB2AGkAcgBvAG4AbQBlAG4AdABdADoAOgBHAGUAdABGAG8AbABkAGUAcgBQAGEAdABoACgAJwBEAGUAcwBrAHQAbwBwACcAKQAsAFsARQBuAHYAaQByAG8AbgBtAGUAbgB0AF0AOgA6AEcAZQB0AEYAbwBsAGQAZQByAFAAYQB0AGgAKAAnAFAAcgBvAGcAcgBhAG0AcwAnACkAKQApAHsACgAgACQAcwA9ACQAcwBoAC4AQwByAGUAYQB0AGUAUwBoAG8AcgB0AGMAdQB0ACgAKABKAG8AaQBuAC0AUABhAHQAaAAgACQAZABpAHIAIAAnAKkDwQO/A7sDzAOzA7kDvwMgAJQDtwO8A78DxAO5A7oDvwPNAy4AbABuAGsAJwApACkACgAgACQAcwAuAFQAYQByAGcAZQB0AFAAYQB0AGgAPQAoAEoAbwBpAG4ALQBQAGEAdABoACAAJAB0ACAAJwByAHUAbgB0AGkAbQBlAFwAcAB5AHQAaABvAG4AdwAuAGUAeABlACcAKQAKACAAJABzAC4AQQByAGcAdQBtAGUAbgB0AHMAPQAnAC0AWAAgAHUAdABmADgAIAAiACcAKwAoAEoAbwBpAG4ALQBQAGEAdABoACAAJAB0ACAAJwBzAHIAYwBcAHMAZQByAHYAZQByAC4AcAB5ACcAKQArACcAIgAnAAoAIAAkAHMALgBXAG8AcgBrAGkAbgBnAEQAaQByAGUAYwB0AG8AcgB5AD0AJAB0AAoAIAAkAHMALgBJAGMAbwBuAEwAbwBjAGEAdABpAG8AbgA9ACgASgBvAGkAbgAtAFAAYQB0AGgAIAAkAHQAIAAnAHMAcgBjAFwAYQBwAHAALgBpAGMAbwAnACkACgAgACQAcwAuAEQAZQBzAGMAcgBpAHAAdABpAG8AbgA9ACcAqQPBA78DuwPMA7MDuQO/AyAAlAO3A7wDvwPEA7kDugO/A80DJwAKACAAJABzAC4AUwBhAHYAZQAoACkACgB9AAoA >nul 2>&1
if errorlevel 1 echo  Τα εικονίδια δεν δημιουργήθηκαν· η εφαρμογή ανοίγει από το START.cmd του φακέλου.
echo  Ολοκληρώθηκε. Υπάρχει εικονίδιο «Ωρολόγιο Δημοτικού» στην επιφάνεια εργασίας
echo  και στο μενού Έναρξη. Η εφαρμογή ανοίγει τώρα.
start "" "%OROLOGIO_DIR%\runtime\pythonw.exe" -X utf8 "%OROLOGIO_DIR%\src\server.py"
timeout /t 6 >nul
exit /b 0
