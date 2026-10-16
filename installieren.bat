@echo off
chcp 65001 >nul
title Werkstatt Sauter - Installation
cd /d "%~dp0"
echo.
echo === Werkstatt Sauter: Installation ===
echo.
where py >nul 2>nul
if errorlevel 1 (
  echo Python wurde nicht gefunden. Es wird jetzt ueber winget installiert ...
  winget install -e --id Python.Python.3.12 --accept-source-agreements --accept-package-agreements
  if errorlevel 1 (
    echo.
    echo Automatische Installation fehlgeschlagen.
    echo Bitte Python von https://www.python.org/downloads/ installieren
    echo und dabei "Add python.exe to PATH" anhaken. Danach diese Datei erneut starten.
    pause
    exit /b 1
  )
  echo Python installiert. Bitte dieses Fenster schliessen und installieren.bat NOCHMAL starten.
  pause
  exit /b 0
)
if not exist ".venv\Scripts\python.exe" (
  echo Lege Programmumgebung an ...
  py -3 -m venv .venv
  if errorlevel 1 ( echo Fehler beim Anlegen der Umgebung. & pause & exit /b 1 )
)
echo Installiere benoetigte Bausteine (einmalig, braucht Internet) ...
".venv\Scripts\python.exe" -m pip install --upgrade pip >nul
".venv\Scripts\python.exe" -m pip install -r requirements.txt
if errorlevel 1 ( echo Fehler bei der Installation. & pause & exit /b 1 )
echo.
echo Fertig! Starten Sie das Programm jetzt mit start.bat
echo.
pause
