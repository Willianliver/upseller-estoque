@echo off
rem Para a interface web (somente o processo que escuta a porta da interface). Nao afeta o agendador nem o MCP.
cd /d "%~dp0"
set PORT=8000
if exist ".env" for /f "tokens=2 delims==" %%a in ('findstr /b "WEB_PORT=" ".env"') do set PORT=%%a
powershell -NoProfile -Command "$c = Get-NetTCPConnection -LocalPort %PORT% -State Listen -ErrorAction SilentlyContinue; if ($c) { $c | ForEach-Object { Stop-Process -Id $_.OwningProcess -Force }; 'Interface parada.' } else { 'A interface nao estava rodando.' }"
timeout /t 2 >nul
