<#
.SYNOPSIS
  Executa a carga dos paineis InvestSUS (scripts\carga_todas.py) e devolve o codigo de saida.
.DESCRIPTION
  Usa o .venv da raiz do projeto se existir; senao o Python indicado em CARGA_FNS_PYTHON ou C:\Python313\python.exe.
  Grava a saida em logs\execucao_AAAAMMDD_HHMMSS.txt e apaga arquivos de logs\ com mais de 90 dias.
  Argumentos extras vao direto para carga_todas.py, ex.:
    .\scripts\executar_carga.ps1 --forcar
    .\scripts\executar_carga.ps1 emendas_impedimentos_tecnicos
  Codigos de saida: 0 sucesso/ignorada, 1 erro, 2 ja em execucao.
#>
$ErrorActionPreference = 'Stop'
$raiz = Split-Path -Parent $PSScriptRoot
Set-Location $raiz

$py = Join-Path $raiz '.venv\Scripts\python.exe'
if (-not (Test-Path $py)) { $py = if ($env:CARGA_FNS_PYTHON) { $env:CARGA_FNS_PYTHON } else { 'C:\Python313\python.exe' } }
if (-not (Test-Path $py)) { Write-Error "Python nao encontrado em $py"; exit 1 }

$logs = Join-Path $raiz 'logs'
New-Item -ItemType Directory -Force -Path $logs | Out-Null
$saida = Join-Path $logs ('execucao_{0:yyyyMMdd_HHmmss}.txt' -f (Get-Date))

$env:PYTHONIOENCODING = 'utf-8'
$env:PYTHONUNBUFFERED = '1'
$ErrorActionPreference = 'Continue'   # avisos em stderr nao viram excecao no PS 5.1
# log em UTF-8 (o Tee-Object do PS 5.1 grava UTF-16, que aparece com espacos entre as letras)
& $py -W ignore (Join-Path $raiz 'scripts\carga_todas.py') @args *>&1 |
    ForEach-Object { $l = "$_"; $l; Add-Content -Path $saida -Value $l -Encoding UTF8 }
$codigo = $LASTEXITCODE

Get-ChildItem -Path $logs -File | Where-Object { $_.LastWriteTime -lt (Get-Date).AddDays(-90) } | Remove-Item -Force
exit $codigo
