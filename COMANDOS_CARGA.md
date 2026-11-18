# Comandos da carga dos painéis InvestSUS

Pasta do projeto: `D:\ProjetosSandro\transfere_pro\APIS\carga_painel_fns`

A carga lê 30 tabelas dos painéis do Qlik e grava em `stg_paineis_fns` (recarga completa). Depois faz o merge em `base_fns` (linhas novas são inseridas e as que sumiram da origem ficam com `fl_ativo = false`). A carga completa leva cerca de 35 a 40 minutos. Configuração: **somente** o arquivo `.env` na raiz deste projeto (modelo em `.env.example`), com `FNS_DB_HOST`, `FNS_DB_PORT`, `FNS_DB_NOME`, `FNS_DB_USUARIO`, `FNS_DB_SENHA` e `FNS_DB_TABLESPACE` (`ts_faf` nesta máquina; pode ficar vazio, mas a linha precisa existir). Sem o `.env`, ou com variável faltando, a carga para com uma mensagem dizendo o que falta. O `.env` está no `.gitignore`.

Códigos de saída: **0** sucesso ou ignorada, **1** erro em alguma tabela, **2** já existe carga em execução.

## Carga completa (Windows)

Abra o **Prompt de Comando (cmd)** e rode:

```bat
cd /d D:\ProjetosSandro\transfere_pro\APIS\carga_painel_fns
carga.bat
```

Esse comando carrega todas as tabelas. Se a carga de hoje já tiver sido concluída com sucesso, ela será ignorada.

Para executar novamente mesmo que a carga de hoje já tenha dado certo:

```bat
carga.bat --forcar
```

Também é possível iniciar a carga completa com duplo clique em `carga.bat`.

Em cada execução pelo Windows, os dados das tabelas carregadas também são salvos em arquivos Excel em `arquivos\AAAAMMDD_HHMMSS`, uma subpasta por execução.
Após atualizar o projeto, instale a nova dependência no ambiente usado pela carga:

```bat
.venv\Scripts\python.exe -m pip install -r requirements.txt
```

## Outros comandos

Para carregar somente tabelas específicas, rode no diretório do projeto:

```bat
carga.bat emendas_instrumentos obras_propostas
```

Nomes das tabelas: lista `TABELAS` em `scripts\carga_todas.py`.

## Tarefa agendada (Windows)

Tarefa **"FNS - Carga Paineis InvestSUS"**: todos os dias às 06:00, com nova tentativa às 12:00. A das 12:00 se ignora se a carga das 06:00 já deu certo.

```powershell
# ver a última e a próxima execução (LastTaskResult 0 = ok)
Get-ScheduledTaskInfo -TaskName 'FNS - Carga Paineis InvestSUS' | Select-Object LastRunTime, LastTaskResult, NextRunTime

# disparar agora
Start-ScheduledTask -TaskName 'FNS - Carga Paineis InvestSUS'

# registrar de novo, rodando só com o usuário logado (sem senha)
D:\ProjetosSandro\transfere_pro\APIS\carga_painel_fns\scripts\agendar_tarefa.ps1 -SomenteLogado

# registrar para rodar MESMO DESLOGADO (PowerShell como Administrador; pede a senha numa janela segura e não a grava)
D:\ProjetosSandro\transfere_pro\APIS\carga_painel_fns\scripts\agendar_tarefa.ps1

# remover a tarefa
D:\ProjetosSandro\transfere_pro\APIS\carga_painel_fns\scripts\agendar_tarefa.ps1 -Remover
```

Hoje a tarefa está no modo "só com o usuário logado": se o Windows estiver bloqueado ou desligado às 06:00, ela roda quando você entrar.

## Logs

- `logs\execucao_AAAAMMDD_HHMMSS.txt`: um arquivo por execução. Logs com mais de 90 dias são apagados automaticamente.
- `logs\ultimo_sucesso.txt`: data da última carga completa sem erro.
- No fim de cada log aparece `total ...s; tabelas: 30; erros: 0`.

```powershell
# última execução
Get-ChildItem D:\ProjetosSandro\transfere_pro\APIS\carga_painel_fns\logs\execucao_*.txt | Sort-Object LastWriteTime | Select-Object -Last 1 | Get-Content -Tail 3
# resumo por tabela da última execução
Get-ChildItem D:\ProjetosSandro\transfere_pro\APIS\carga_painel_fns\logs\execucao_*.txt | Sort-Object LastWriteTime | Select-Object -Last 1 | Select-String 'staging .* linhas'
```

## Conferir no banco (pgAdmin, banco transferepro)

```sql
-- quando cada tabela da staging foi recarregada pela última vez (muda TODO dia, mesmo sem alteração de dados)
SELECT 'instrumentos_investimentos' AS tabela, max(dt_carga), count(*) FROM stg_paineis_fns.instrumentos_investimentos
UNION ALL SELECT 'emendas_instrumentos', max(dt_carga), count(*) FROM stg_paineis_fns.emendas_instrumentos
UNION ALL SELECT 'obras_propostas', max(dt_carga), count(*) FROM stg_paineis_fns.obras_propostas;

-- o que mudou na base em cada dia (dt_inclusao = linha nova; dt_atualizacao = linha desativada/reativada)
SELECT dt_inclusao::date, count(*) FROM base_fns.emendas_instrumentos GROUP BY 1 ORDER BY 1 DESC;
SELECT count(*) FILTER (WHERE fl_ativo) AS ativas, count(*) FILTER (WHERE NOT fl_ativo) AS inativas FROM base_fns.emendas_instrumentos;

-- existe carga rodando agora? (trava 762731)
SELECT pid FROM pg_locks WHERE locktype = 'advisory' AND objid = 762731;
```

Em `base_fns`, as datas `dt_inclusao`/`dt_atualizacao` só mudam quando os dados mudam. Uma tabela sem alterações na origem continua com as datas antigas, mesmo com a carga rodando todo dia. Para saber se a carga rodou, use `dt_carga` na staging ou o log.

Depois de uma carga, atualize a árvore do pgAdmin (botão direito → Refresh) para ver tabelas novas.

## Linux

No terminal do Linux, dentro da pasta do projeto:

```bash
cd /opt/carga_fns
./scripts/executar_carga.sh
```

Esse comando carrega todas as tabelas. Se a carga de hoje já tiver sido concluída com sucesso, ela será ignorada. Para forçar uma nova carga completa:

```bash
./scripts/executar_carga.sh --forcar
```

Na primeira execução, se necessário, dê permissão ao script:

```bash
chmod +x scripts/executar_carga.sh
```

Veja [docs/AGENDAMENTO_LINUX.md](docs/AGENDAMENTO_LINUX.md) para instalação, configuração e agendamento.
