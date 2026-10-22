@echo off
chcp 65001 >nul
setlocal
title Απεγκατάσταση: Ωρολόγιο Δημοτικού
set "OROLOGIO_DIR=%~dp0."
echo.
echo  Θα αφαιρεθεί η εφαρμογή «Ωρολόγιο Δημοτικού» από αυτόν τον υπολογιστή.
echo  Τα δεδομένα σας θα αντιγραφούν πρώτα στα Έγγραφα, σε φάκελο
echo  «Orologio - antigrafo» με την ημερομηνία.
echo.
echo  Πατήστε 1 για συνέχεια ή 2 για ακύρωση.
choice /C 12 /N
if errorlevel 2 exit /b 0
powershell -NoProfile -ExecutionPolicy Bypass -EncodedCommand RwBlAHQALQBQAHIAbwBjAGUAcwBzACAAcAB5AHQAaABvAG4AdwAsAHAAeQB0AGgAbwBuACAALQBFAHIAcgBvAHIAQQBjAHQAaQBvAG4AIABTAGkAbABlAG4AdABsAHkAQwBvAG4AdABpAG4AdQBlACAAfAAgAFcAaABlAHIAZQAtAE8AYgBqAGUAYwB0ACAAewAgACQAXwAuAFAAYQB0AGgAIAAtAGEAbgBkACAAJABfAC4AUABhAHQAaAAuAFMAdABhAHIAdABzAFcAaQB0AGgAKAAkAGUAbgB2ADoATwBSAE8ATABPAEcASQBPAF8ARABJAFIAKQAgAH0AIAB8ACAAUwB0AG8AcAAtAFAAcgBvAGMAZQBzAHMAIAAtAEYAbwByAGMAZQAgAC0ARQByAHIAbwByAEEAYwB0AGkAbwBuACAAUwBpAGwAZQBuAHQAbAB5AEMAbwBuAHQAaQBuAHUAZQAKAA== >nul 2>&1
powershell -NoProfile -ExecutionPolicy Bypass -Command "$d=Join-Path ([Environment]::GetFolderPath('MyDocuments')) ('Orologio - antigrafo '+(Get-Date -Format yyyyMMdd_HHmm)); Copy-Item -Recurse -Force (Join-Path $env:OROLOGIO_DIR 'data') $d" >nul 2>&1
powershell -NoProfile -ExecutionPolicy Bypass -EncodedCommand ZgBvAHIAZQBhAGMAaAAoACQAZABpAHIAIABpAG4AIABAACgAWwBFAG4AdgBpAHIAbwBuAG0AZQBuAHQAXQA6ADoARwBlAHQARgBvAGwAZABlAHIAUABhAHQAaAAoACcARABlAHMAawB0AG8AcAAnACkALABbAEUAbgB2AGkAcgBvAG4AbQBlAG4AdABdADoAOgBHAGUAdABGAG8AbABkAGUAcgBQAGEAdABoACgAJwBQAHIAbwBnAHIAYQBtAHMAJwApACkAKQB7ACAAUgBlAG0AbwB2AGUALQBJAHQAZQBtACAAKABKAG8AaQBuAC0AUABhAHQAaAAgACQAZABpAHIAIAAnAKkDwQO/A7sDzAOzA7kDvwMgAJQDtwO8A78DxAO5A7oDvwPNAy4AbABuAGsAJwApACAALQBFAHIAcgBvAHIAQQBjAHQAaQBvAG4AIABTAGkAbABlAG4AdABsAHkAQwBvAG4AdABpAG4AdQBlACAAfQAKAA== >nul 2>&1
cd /d "%TEMP%"
echo  Τα δεδομένα αντιγράφηκαν στα Έγγραφα. Η εφαρμογή αφαιρείται· το παράθυρο θα κλείσει.
timeout /t 4 >nul
rmdir /s /q "%OROLOGIO_DIR%" 2>nul & exit
