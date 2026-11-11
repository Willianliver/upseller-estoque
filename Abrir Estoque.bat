@echo off
rem Abre a interface de estoque: inicia o servidor local (se ainda nao estiver rodando) e abre o navegador.
rem Uso: duplo clique. Para o servidor: Gerenciador de Tarefas -> "pythonw.exe" (ou use "Parar Estoque.bat").
rem Parametro opcional: "semnavegador" (apenas inicia o servidor).
cd /d "%~dp0"

set PORT=8000
if exist ".env" for /f "tokens=2 delims==" %%a in ('findstr /b "WEB_PORT=" ".env"') do set PORT=%%a

if not exist ".venv\Scripts\pythonw.exe" (
    echo Ambiente virtual nao encontrado. Veja docs\instalacao.md
    pause
    exit /b 1
)

rem Inicia o servidor somente se a porta ainda nao estiver em uso
powershell -NoProfile -Command "if (-not (Get-NetTCPConnection -LocalPort %PORT% -State Listen -ErrorAction SilentlyContinue)) { Start-Process -WindowStyle Hidden -FilePath '.venv\Scripts\pythonw.exe' -ArgumentList '-m','app.web' }"

rem Aguarda o servidor responder (ate ~15 s)
powershell -NoProfile -Command "for($i=0;$i -lt 30;$i++){ if(Get-NetTCPConnection -LocalPort %PORT% -State Listen -ErrorAction SilentlyContinue){exit 0}; Start-Sleep -Milliseconds 500 }; exit 1"
if errorlevel 1 (
    echo O servidor nao iniciou. Veja logs\web.log
    pause
    exit /b 1
)

if /i not "%~1"=="semnavegador" start "" "http://127.0.0.1:%PORT%"
