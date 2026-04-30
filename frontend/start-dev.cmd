@echo off
REM Avoid PowerShell blocking npx.ps1 (ExecutionPolicy). Run this from Explorer or cmd.exe.
cd /d "%~dp0"
npx.cmd ng serve --host 127.0.0.1 --port 4201
