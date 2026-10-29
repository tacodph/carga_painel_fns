<#
.SYNOPSIS
  Cria/atualiza a tarefa agendada "FNS - Carga Paineis InvestSUS" (diaria 06:00, nova tentativa 12:00).
.DESCRIPTION
  Nao conflita com a tarefa "FAF - Carga Transferegov" (07:30, 10:30, 14:30): a carga leva ~35 min.
  A tentativa das 12:00 e segura: se a carga completa do dia ja deu certo, a rotina se auto-ignora (IGNORADA);
  se uma carga ainda estiver rodando, sai com codigo 2 (trava do banco).

  Para rodar MESMO SEM USUARIO LOGADO a tarefa precisa das credenciais do Windows do usuario. O script pede a
  senha com Get-Credential (janela segura), usa-a apenas em memoria no registro da tarefa e nao a grava em
  arquivo nem em log. Use -SomenteLogado para dispensar a senha (a tarefa so roda com o usuario conectado).
  Requer PowerShell elevado (Administrador) no modo com senha.
.EXAMPLE
  .\scripts\agendar_tarefa.ps1
  .\scripts\agendar_tarefa.ps1 -Usuario "DOMINIO\svc_carga"
  .\scripts\agendar_tarefa.ps1 -SomenteLogado
  .\scripts\agendar_tarefa.ps1 -Remover
#>
param(
    [string]$Usuario = "$env:USERDOMAIN\$env:USERNAME",
    [switch]$SomenteLogado,
    [switch]$Remover
)
$ErrorActionPreference = 'Stop'
$nome = 'FNS - Carga Paineis InvestSUS'

if ($Remover) { Unregister-ScheduledTask -TaskName $nome -Confirm:$false; Write-Host "Tarefa removida."; return }

$raiz = Split-Path -Parent $PSScriptRoot
$script = Join-Path $raiz 'scripts\executar_carga.ps1'
$acao = New-ScheduledTaskAction -Execute 'powershell.exe' -WorkingDirectory $raiz `
    -Argument "-NoProfile -ExecutionPolicy Bypass -File `"$script`""
$gatilhos = '06:00', '12:00' | ForEach-Object { New-ScheduledTaskTrigger -Daily -At $_ }
$config = New-ScheduledTaskSettingsSet -StartWhenAvailable -MultipleInstances IgnoreNew `
    -ExecutionTimeLimit (New-TimeSpan -Hours 3) -RestartCount 0

if ($SomenteLogado) {
    $principal = New-ScheduledTaskPrincipal -UserId $Usuario -LogonType Interactive
    Register-ScheduledTask -TaskName $nome -Action $acao -Trigger $gatilhos -Settings $config -Principal $principal -Force | Out-Null
} else {
    $cred = Get-Credential -UserName $Usuario -Message 'Conta do Windows que executara a tarefa'
    Register-ScheduledTask -TaskName $nome -Action $acao -Trigger $gatilhos -Settings $config `
        -User $cred.UserName -Password $cred.GetNetworkCredential().Password -RunLevel Limited -Force | Out-Null
}
Write-Host "Tarefa '$nome' registrada (06:00, 12:00). Teste agora com: Start-ScheduledTask -TaskName '$nome'"
