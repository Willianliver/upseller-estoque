# Registra o agendador no Agendador de Tarefas do Windows (inicia ao fazer logon, sem janela).
# Uso:    powershell -ExecutionPolicy Bypass -File scripts\registrar_tarefa.ps1
# Remover: Unregister-ScheduledTask -TaskName "UpSeller Estoque - Agendador" -Confirm:$false
# Observação: ativar/desativar a sincronização é feito na interface web (Configurações), não aqui.
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
$pyw  = Join-Path $root ".venv\Scripts\pythonw.exe"
if (-not (Test-Path $pyw)) { throw "pythonw.exe não encontrado em $pyw. Crie o venv primeiro." }

$name    = "UpSeller Estoque - Agendador"
$action  = New-ScheduledTaskAction -Execute $pyw -Argument "-m app.scheduler" -WorkingDirectory $root
$trigger = New-ScheduledTaskTrigger -AtLogOn -User $env:USERNAME
$set     = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries `
           -StartWhenAvailable -ExecutionTimeLimit ([TimeSpan]::Zero) -MultipleInstances IgnoreNew `
           -RestartCount 3 -RestartInterval (New-TimeSpan -Minutes 1)
Register-ScheduledTask -TaskName $name -Action $action -Trigger $trigger -Settings $set `
    -Description "Sincroniza o estoque UpSeller (cache local). Liga/desliga pela tela Configurações." -Force | Out-Null
Write-Host "Tarefa '$name' registrada."
