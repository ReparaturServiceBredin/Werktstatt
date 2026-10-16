@echo off
chcp 65001 >nul
title Werkstatt Sauter - Installation
cd /d "%~dp0"
echo.
echo  === Werkstatt Sauter wird auf diesem PC eingerichtet ===
echo.
if not exist "Werkstatt-Sauter.exe" (
  echo  Werkstatt-Sauter.exe fehlt in diesem Ordner.
  pause
  exit /b 1
)
set "ZIEL=%LOCALAPPDATA%\Programs\Werkstatt-Sauter"
if not exist "%ZIEL%" mkdir "%ZIEL%"
tasklist /FI "IMAGENAME eq Werkstatt-Sauter.exe" | find /I "Werkstatt-Sauter.exe" >nul
if not errorlevel 1 (
  echo  Das Programm laeuft gerade. Bitte zuerst ueber das Symbol neben der Uhr beenden.
  pause
  exit /b 1
)
copy /Y "Werkstatt-Sauter.exe" "%ZIEL%\Werkstatt-Sauter.exe" >nul
if errorlevel 1 (
  echo  Kopieren fehlgeschlagen.
  pause
  exit /b 1
)
powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "$s=(New-Object -ComObject WScript.Shell).CreateShortcut([Environment]::GetFolderPath('Desktop')+'\Werkstatt Sauter.lnk');" ^
  "$s.TargetPath='%ZIEL%\Werkstatt-Sauter.exe'; $s.WorkingDirectory='%ZIEL%'; $s.Save();" ^
  "$m=(New-Object -ComObject WScript.Shell).CreateShortcut([Environment]::GetFolderPath('Programs')+'\Werkstatt Sauter.lnk');" ^
  "$m.TargetPath='%ZIEL%\Werkstatt-Sauter.exe'; $m.WorkingDirectory='%ZIEL%'; $m.Save()"
echo  Fertig! Auf dem Desktop liegt jetzt "Werkstatt Sauter".
echo  Das Programm wird jetzt gestartet ...
echo.
start "" "%ZIEL%\Werkstatt-Sauter.exe"
timeout /t 5 >nul
