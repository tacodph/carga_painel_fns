@echo off
rem Carga dos paineis InvestSUS. Exemplos:
rem   carga.bat                          todas as tabelas (se a carga completa de hoje ja deu certo, ela se ignora)
rem   carga.bat --forcar                 todas as tabelas, mesmo que ja tenha rodado hoje
rem   carga.bat emendas_instrumentos     so as tabelas informadas (nomes em scripts\carga_todas.py)
rem Codigo de saida: 0 sucesso/ignorada, 1 erro, 2 ja existe carga em execucao.
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\executar_carga.ps1" %*
exit /b %ERRORLEVEL%
