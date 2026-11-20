@echo off
chcp 65001 >nul
title Reifen und Teile - Installation
cd /d "%~dp0"
echo.
echo  === Reifen und Teile wird auf diesem PC eingerichtet ===
echo.
if not exist "Reifen-Teile.exe" (
  echo  Reifen-Teile.exe fehlt in diesem Ordner.
  pause
  exit /b 1
)
set "ZIEL=%LOCALAPPDATA%\Programs\Reifen-Teile"
if not exist "%ZIEL%" mkdir "%ZIEL%"
tasklist /FI "IMAGENAME eq Reifen-Teile.exe" | find /I "Reifen-Teile.exe" >nul
if not errorlevel 1 (
  echo  Das Programm laeuft gerade. Bitte zuerst ueber das Symbol neben der Uhr beenden.
  pause
  exit /b 1
)
copy /Y "Reifen-Teile.exe" "%ZIEL%\Reifen-Teile.exe" >nul
if errorlevel 1 (
  echo  Kopieren fehlgeschlagen.
  pause
  exit /b 1
)
powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "$s=(New-Object -ComObject WScript.Shell).CreateShortcut([Environment]::GetFolderPath('Desktop')+'\Reifen und Teile.lnk');" ^
  "$s.TargetPath='%ZIEL%\Reifen-Teile.exe'; $s.WorkingDirectory='%ZIEL%'; $s.Save();" ^
  "$m=(New-Object -ComObject WScript.Shell).CreateShortcut([Environment]::GetFolderPath('Programs')+'\Reifen und Teile.lnk');" ^
  "$m.TargetPath='%ZIEL%\Reifen-Teile.exe'; $m.WorkingDirectory='%ZIEL%'; $m.Save()"
echo  Fertig! Auf dem Desktop liegt jetzt "Reifen und Teile".
echo  Das Programm wird jetzt gestartet ...
echo.
start "" "%ZIEL%\Reifen-Teile.exe"
timeout /t 5 >nul
