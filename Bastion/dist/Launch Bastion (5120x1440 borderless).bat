@echo off
REM Drop this into your Bastion game folder (next to Bastion.exe) and run it.
REM Launches Bastion in borderless windowed mode. Then pick 5120x1440 in Options > Video.
cd /d "%~dp0"
start "" "%~dp0Bastion.exe" -windowed -noborder
