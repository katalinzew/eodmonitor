@echo off
setlocal
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0rollout.ps1" %*
exit /b %ERRORLEVEL%
