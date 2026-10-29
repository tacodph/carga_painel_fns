# Agendamento da carga dos painéis InvestSUS no Linux

Carga diária das 30 tabelas do escopo (Qlik Engine API → `stg_paineis_fns` → merge em `base_fns`), às **06:00** com uma nova tentativa às **12:00** (horário de Brasília). Esses horários não conflitam com a carga FaF (07:30, 10:30 e 14:30). A tentativa das 12:00 se auto-ignora quando a carga completa do dia já deu certo. Se outra carga ainda estiver rodando, a execução sai com código 2, por causa da trava no banco (`pg_advisory_lock`).

Códigos de saída de `scripts/executar_carga.sh`: **0** sucesso ou ignorada, **1** erro em alguma tabela, **2** já em execução.

## 1. Pré-requisitos

```bash
sudo apt update
sudo apt install -y python3 python3-venv tzdata
```

O servidor precisa de acesso HTTPS/WSS de saída para `investsuspaineis.saude.gov.br` e de acesso ao PostgreSQL de destino.

## 2. Copiar o projeto

Copie a pasta `carga_fns` (com `scripts/`, `requirements.txt` e `.env.example`) para o servidor, por exemplo `/opt/carga_fns`:

```bash
sudo mkdir -p /opt/carga_fns && sudo chown "$USER" /opt/carga_fns
# a partir da máquina Windows (Git Bash ou WSL):
#   scp -r scripts requirements.txt .env.example docs usuario@servidor:/opt/carga_fns/
cd /opt/carga_fns
mkdir -p logs
```

## 3. Ambiente virtual e dependências

```bash
cd /opt/carga_fns
python3 -m venv .venv
.venv/bin/pip install --upgrade pip
.venv/bin/pip install -r requirements.txt
```

## 4. Arquivo `.env`

```bash
cp .env.example .env
chmod 600 .env
nano .env
```

Preencha `FNS_DB_HOST`, `FNS_DB_PORT`, `FNS_DB_NOME`, `FNS_DB_USUARIO` e `FNS_DB_SENHA`.

**`FNS_DB_TABLESPACE`**: deixe **vazio**, a menos que o tablespace já exista nesse PostgreSQL. O `ts_faf` só existe na máquina Windows (`D:\pgdata_faf`). Com o campo vazio, as tabelas vão para o tablespace padrão. Para conferir:

```bash
psql -h HOST -p PORTA -U USUARIO -d transferepro -c "select spcname, pg_tablespace_location(oid) from pg_tablespace"
```

O código lê **somente** `<projeto>/.env`. Todas as 6 linhas do `.env.example` precisam existir; só `FNS_DB_TABLESPACE` pode ficar vazia. Se faltar algo, a carga para e lista as variáveis que faltam.

## 5. Teste manual

```bash
cd /opt/carga_fns
chmod +x scripts/*.sh
# rápido: só duas tabelas pequenas
./scripts/executar_carga.sh emendas_impedimentos_tecnicos emendas_dotacao_exercicio_atual
echo "saida=$?"
# completo (~35 min): todas as tabelas
./scripts/executar_carga.sh --forcar
```

O log de cada execução fica em `logs/execucao_AAAAMMDD_HHMMSS.txt`. Logs com mais de 90 dias são apagados automaticamente.

## 6a. Agendar com systemd (recomendado)

```bash
cd /opt/carga_fns
sudo bash scripts/agendar_linux.sh                 # executa como o usuário que chamou o sudo
sudo bash scripts/agendar_linux.sh --usuario fns   # ou como outro usuário
```

O script cria `/etc/systemd/system/fns-paineis-carga.service` e `fns-paineis-carga.timer`, com `OnCalendar` 06:00 e 12:00 no fuso `America/Sao_Paulo` e `Persistent=true` (se o servidor estava desligado no horário, a carga roda ao ligar).

Para conferir e operar:

```bash
systemctl list-timers fns-paineis-carga.timer          # próximas execuções
sudo systemctl start fns-paineis-carga.service         # disparo manual agora
systemctl status fns-paineis-carga.service             # último resultado
journalctl -u fns-paineis-carga.service -n 100         # saída da última execução
journalctl -u fns-paineis-carga.service --since today  # tudo de hoje
ls -lt /opt/carga_fns/logs | head                      # logs por execução
```

Para desativar ou remover:

```bash
sudo systemctl disable --now fns-paineis-carga.timer   # pausa (mantém os arquivos)
sudo systemctl enable --now fns-paineis-carga.timer    # reativa
sudo bash scripts/agendar_linux.sh --remover           # remove service e timer
```

## 6b. Alternativa: cron (sem root)

```bash
cd /opt/carga_fns
bash scripts/agendar_linux.sh --cron           # instala no crontab do usuário atual
crontab -l                                     # conferir
tail -f logs/cron.log                          # acompanhar
bash scripts/agendar_linux.sh --cron --remover # remover
```

O cron usa o fuso do servidor (normalmente UTC), e o script já converte os horários de Brasília para ele: 06:00 e 12:00 de Brasília viram 09:00 e 15:00 em UTC. Para só ver as linhas calculadas, sem instalar nada:

```bash
FNS_TESTE_FUSO="-0300,+0000" bash scripts/agendar_linux.sh --cron
```

## 7. Observações

- A marca de "carga do dia concluída" (`logs/ultimo_sucesso.txt`) usa a data do servidor. Às 06:00 e 12:00 de Brasília a data em UTC é a mesma, então não há problema.
- `--forcar` ignora essa marca (útil para recarregar manualmente no mesmo dia).
- O script **não** grava senha nem altera o `.env`.
- Escopo, tabelas e regras de merge estão em `mapeamento_paineis.md`. A lista de tabelas está em `scripts/carga_todas.py` (`TABELAS`).
