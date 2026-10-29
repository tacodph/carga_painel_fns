# Mapeamento dos painéis InvestSUS (Qlik Sense) — passo 1

Data: 2026-10-23 · Máquina: notebook do Sandro (Windows) · Projeto em `D:\ProjetosSandro\transfere_pro\APIS\carga_painel_fns` (até 2026-10-27 em `C:\Users\sandro.resende\carga_fns`; os dumps `raw/` ficaram lá). Scripts em `scripts/probe.py`, dumps em `raw/` (`probe.json` tem tudo).

## Fora do escopo (decisão do Sandro, 2026-10-23)

Não entram na carga (o mapeamento abaixo fica só como referência):

| Item | App | Objeto | Motivo |
|---|---|---|---|
| Painel **Repasses Fundo a Fundo** (todas as tabelas, incl. `TuVrwBq` 20,3 mi, `fDmYVYR`) | `8d8da3af-4b18-4305-9584-715ee15b4e40` | todos | já coberto pela carga FAF |
| Ordens Bancárias — Instrumentos | `0ba8c451-0b87-4657-ae70-ee6dcf11aec1` | `qwPUu` (432.361) | tabela de OB |
| Ordens Bancárias — Emendas | `585aca8d-2714-487d-a08e-34150047e7dd` | `NGrJBF` (308.156) | tabela de OB |
| Parcelas/OB das obras — SISMOB | `955106a0-664e-4983-bacf-8f78ef1ee435` | `sHUzg` (46.566), `tejAADX` (46.624) | colunas de ordem bancária das parcelas; excluídas por cautela — reincluir se o Sandro quiser |

## Resumo

- **Servidor**: `https://investsuspaineis.saude.gov.br`, Qlik Sense Enterprise (client 8.423), **sem virtual proxy** (prefixo `/`). Atrás de AWS ELB.
- **Acesso anônimo à Engine API funciona** a partir desta máquina (usuário `anonymous<uuid>`, diretório `NONE`). Receita:
  1. `GET /extensions/CGIN_InvestsusPaineis/CGIN_InvestsusPaineis.html` → cookie `X-Qlik-Session`;
  2. `GET /qps/csrftoken?xrfkey=<16 chars>` com header `X-Qlik-Xrfkey` → header de resposta `qlik-csrf-token`;
  3. websocket `wss://investsuspaineis.saude.gov.br/app/<appId>?qlik-csrf-token=<token>` com o cookie, `Origin: https://investsuspaineis.saude.gov.br` e um User-Agent de navegador.
  Sem o passo 2 o handshake dá **403** (sem User-Agent o ELB também dá 403). QRS (`/qrs/...`) dá 401 — não precisamos.
- O hub `CGIN_InvestsusPaineis` **não tem os dados**: cada card abre outro mashup (`/extensions/<NOME>/<NOME>.html`) com seu próprio `ID_APP`. "Informações Bancárias" é um hub com 12 apps.
- **Métodos de extração testados:**
  - `ExportData` (OOXML e CSV_C) **funciona** anonimamente (URL `/tempcontent/...` baixável com a mesma sessão), **mas trunca em ~5 milhões de células** (`qWarnings: [1000]`). Ex.: Instrumentos `BbeRjR` 430.880 linhas × 18 col → só 277.777 linhas exportadas. Serve só para tabelas pequenas.
  - **`GetHyperCubeData` paginado funciona** até a última linha (testado na linha 430.870 de `BbeRjR`) — limite de 10.000 células por página. **Este é o caminho recomendado.**
  - Muitas tabelas de detalhe têm **condição de cálculo** (ex.: "Selecione UF e Município") e mostram 0 linhas. Dá para contornar criando um **objeto de sessão** (`CreateSessionObject`) com a mesma `qHyperCubeDef` sem `qCalcCond` — ex.: FAF "Tabela extração" passa de 0 para **20.336.101 linhas × 31 col**. Para tabelas gigantes, melhor paginar por seleção (`SelectValues` em UF/ANO/mês) em vez do cubo inteiro, para não pesar no servidor deles.
  - Playwright/“exportar para Excel” do navegador **não é necessário** (e teria o mesmo teto de 5M células).
- Nada foi gravado em banco nem criado repositório.

## Painéis

Contagens = `qHyperCube.qSize.qcy` sem seleções, em 2026-10-23. "Mashup" = o objeto aparece no JS do mashup; os demais existem no app (outras sheets) e também são lidos anonimamente.

### 1. Repasses Fundo a Fundo
- Mashup: `CGIN_Painel_FAF` · **appId `8d8da3af-4b18-4305-9584-715ee15b4e40`** ("CGIN - LOAD - FAF", reload 2026-10-22 11:41Z)
- Tabela principal: **`TuVrwBq` "Tabela extração"** — calc cond "Selecione Ano e UF"; sem a condição (objeto de sessão): **20.336.101 linhas × 31 col**.
  - Dims: NU_PROCESSO, NU_PORTARIA, =DT_PORTARIA, DIA PAGAMENTO, ANO, MÊS, TP_REPASSE, NU_OB, NU_COMPETENCIA, CO_TIPO_RECURSO, UF, CO_MUNICIPIO_IBGE, MUNICIPIO, ENTIDADE, CNPJ, SUBFUNCAO, BLOCO, COMPONENTE, PROGRAMA, NU_PROPOSTA, BANCO, AGENCIA, CONTA, RECURSO COVID OU NORMAL?, =MARCADOR_EMENDA_COVID, =TP_RECURSO_PROP, DT_SALDO_CONTA
  - Medidas: Valor Bruto, Desconto, Valor Liquido, VL_SALDO_CONTA
- Outras: `fDmYVYR` "Consulta Contas Correntes Fundo de Saúde" (mashup; calc cond UF+Município) — UF, MUNICIPIO, TP_REPASSE, BLOCO, BANCO, =AGENCIA, CONTA, Data Saldo - Competência | Valor Saldo em Conta - Competência. `FVQYeJ` "TABELA GERAL" (RAG/planejamento, 251.104 linhas). `tLZCwq` TableBox resumo por bloco (mashup). Mashup tem 36 objetos (gráficos/KPIs).

### 2. Instrumentos de Investimentos
- Mashup: `CGIN_Painel_Instrumentos_V2` · **appId `0ba8c451-0b87-4657-ae70-ee6dcf11aec1`** ("CGIN - PFNS - INSTRUMENTOS NOVAVERSAO", reload 2026-10-22 12:30Z)
- **`BbeRjR` "Tabela de Instrumentos" — 430.880 linhas**: PROPOSTA, PORTARIA OU CONVÊNIO, DATA PORTARIA, UF, MUNICIPIO, CÓD. IBGE, ENTIDADE, CNPJ, OBJETO, ANO, MODALIDADE TRANSF., ESFERA, NAT. JURIDICA, RECURSO, ACAO, VL PROPOSTA, VL EMPENHADO, VL PAGO
- **`jLmPjCM` "Tabela de Notas de Empenho" — 473.837**: PROPOSTA/ANO & SIAFI ou PORTARIA, EMPENHO, DATA EMPENHO, VL EMPENHO
- **`qwPUu` "Tabela de Ordens Bancárias" — 432.361**: PROPOSTA/ANO & SIAFI ou PORTARIA, OB, DATA OB, VL OB
- `MNfPp` "Tabela CNES - Propostas FAF" — 502.356; `HyYdkG` "TB_CNES" — 540.273 (ExportData OOXML ok, 25,6 MB, mas truncado)

### 3. Emendas Parlamentares
- Mashup: `CGIN_Painel_Emendas` · **appId `585aca8d-2714-487d-a08e-34150047e7dd`** ("CGIN - EMENDAS PARLAMENTARES 2026", reload 2026-10-22 20:00Z)
- **`wqkNqZ` "Tabela Instrumentos" — 326.772 linhas × 33**: Ano, N° Emenda, Partido, Parlamentar, Cód./Parlamentar Solicitante (a partir de 2025), UF, Cód. Município IBGE, Municipio, Esfera Administrativa, Tipo de Emenda, Grupo de Despesa, Subfunção, Fonte, Funcional, Data Inicio Proposta, N° Instrumento, TGov Parceria, Tipo de Repasse, Tipo de Instrumento, Ação Orç., Programa Estratégico, Componente, CNPJ Beneficiário, Beneficiário, Nr. Portaria, Data Portaria, Situação (Portal FNS), Situação (DS PROPOSTA), Data Último Pgto | Instrumento (R$), Empenhado (R$), Pago (R$)
- `NGrJBF` "Ordens Bancárias" — 308.156 (N° OB, Data OB, Nº Instrumento, UF, Município, Tipo de Repasse, Situação | Valor Repasse)
- `tjpJm` "Indicação Parlamentar - Exercícios Anteriores" — 253.232; `dfkFC` "Indicação Parlamentar - Exercício Atual" — 35.040; `HMwhMX` "Cadastro de Propostas InvestSus" — 35.040; `sXpUeT` "Dotação Orçamentária - Exercício Atual" — 2.501; `UUWFP` SIDORC — 13.072; `JynxMw` Autores emendas de comissão — 8.055; `YKdbhkW` Parlamentares solicitantes — 6.167; `fbktZP` Impedimentos técnicos — 44; `Sbbkn` CNES — 86.280
- Atenção: o app é "2026" — verificar se exercícios anteriores estão em outro app.

### 4. Obras Fundo a Fundo
- Mashup: `CGIN_Painel_SISMOB` · **appId `955106a0-664e-4983-bacf-8f78ef1ee435`** ("CGIN - SISMOB - PIG", reload 2026-10-22 09:40Z)
- **`PEtgN` "Informações Gerais da Proposta - Base SISMOB" — 46.813 linhas × 44** (a mais completa): Número Proposta, Link Proposta, Portaria, Ano Portaria, Tipo Obra, Tipo Recurso, Secretaria, Programa, Componente, Porte, UF, Município, Cod IBGE, CNES, Nome Estabelecimento, Latitude, Longitude, Situação da Obra (MGI), Situação (MGI - descrição), Detalhamento Situacional, Percentual Executado, Obra reativada, Readequação, Portaria/Data Cancelamento, Registros GRU Devolução, Devolução de recurso, Data Devolução, Elegível/Interesse/Documentação/Tipo/Posição Retomada, Data Assinatura TRR, Última Análise Retomada | Valor Instrumento, Valor Empenho, Valor Total Pago, Valor 1ª/2ª/3ª Parcela
- Outras: `qLPXj` (46.912, versão com campos SISPAG), `NLeNr` (46.724), `rrTzjp` financeiro (35.791), `sHUzg` parcelas/OBs (46.566), `DxwXMMs` ciclo de datas (pivot, 46.565), `hDckPM` monitoramento (pivot, 46.414), `azpeFTp` cancelados/devolução (10.700), `KDunDrN` estabelecimentos (13.574), `sPkTs` SISGRU UG 257001 (178.863), `GMBKY` geo (46.624). Tem tipos de extensão `Tabela_simples` e `swr-sense-export` não varridos.

### 5. Novo PAC
- Mashup: `CGIN_Novo_Pac` · **appId `6c51cf78-c6df-4ed6-b9a7-bfe261704189`** ("CGIN - NOVO_PAC", reload 2026-10-22 21:10Z)
- **`YuHaaW` — 14.592 linhas**: Número da Proposta, UF, Municipio, Programa, Proponente, Situação, CNPJ do Proponente | Valor
- **`bSJRDW` (mashup) — 176.479**: Número da Proposta, Pergunta, Resposta (formulário de seleção). ExportData OOXML ok (3,6 MB, completo).
- Apoio: `ejEYTn`/`SqPtvKZ` municípios/população (4.212), `twXhBJ` NO_PESSOA (4.114)

### 6. Monitoramento de Instrumentos
- Mashup: `CGIN_MONITORAMENTO_INSTRUMENTOS_PUBLICO` · **appId `6a19d3a2-cf45-49a8-8d4e-7c501f41dae9`** (reload 2026-10-23 02:16Z — recarrega com frequência)
- Tabelas do mashup (as 3 trocadas por abas): **`BmzHxr` — 68.034 linhas**: Nº Instrumento, Plano de Ação, Tipo, Recurso, Objeto, Grupo, Ano, UF, Município, Esfera, Banco, CNPJ, Agência, Conta, Percentual de Execução (%), Data do Saldo, Situação do Saldo, Situação da Execução, Situação do Monitoramento | Valor Repassado (R$), Data do Repasse, Saldo (R$), Saldo Sobre o Valor (%). ExportData OOXML ok (8,2 MB, completo).
- **`rmGMxMM` — 67.674** (mesmo núcleo + Conta Migrada, Data da Atualização); **`jnpaty` — 25.416** (núcleo + Data da Atualização)

### 7. Informações Bancárias (hub `CGIN_HUB_PAINEIS_BANCARIOS`, appId `7980a797-d040-4c8b-8731-3845b931fd0b`, sem dados)
12 apps, cada um com a tabela principal no JS (`IdTabelaSaldos` / `IdTabelaExtratos`):

| Mashup | appId | Tabela | Linhas (sem seleção) | Observação |
|---|---|---|---|---|
| SALDOS_DIARIOS_BB | `0074de99-506e-48d7-92c9-10d2b39f891d` | `RpBYrh` (mashup) | calc cond UF+Município+Esfera | Data Saldo, UF, Município, Esfera, Cód. IBGE, Tipo Conta, CNPJ, Agência, Conta, Nº Emenda, Nº Proposta, Tipo Emenda, Parlamentar \| Saldo Total. Alternativa sem condição: `bmyMBmc` "SALDOS_DIARIOS_AUDITORIA" **14.392.120 linhas** × 27 |
| SALDOS_DIARIOS_CEF | `6bee6993-d864-4bc6-88a9-edd5faaaa022` | `fYKBNT` (mashup) | calc cond | Alternativa: `pXfxSV` **17.153.424 linhas** (Data Saldo, UF, Município, CNPJ Conta, Agência, Conta, Tipo Conta, Nº Emenda, Nº Proposta, Tipo Emenda, Parlamentar \| Saldo em Conta) |
| SALDO_COMPETENCIA_BB | `036b49d3-9e96-491e-843a-1c454b451f8c` | `XGQJFj` | 66.365 | UF, Município, CNPJ, Tipo Conta, Agência, Conta \| COMPETENCIA SALDO 08/2026. Export OOXML ok |
| SALDO_COMPETENCIA_CEF | `1eccc3d9-f704-474a-ae52-9177ab37c1cf` | `XGQJFj` | 44.793 | + Conta Migrada. Export OOXML ok |
| EXTRATOS_MENSAIS_BB_ANTERIOR_2018 | `b42b054a-44df-4699-97c5-f96e7e9e7ba1` | `jAJam` | calc cond | Data Movimentação, UF, Município, Tipo Conta, Cred/Deb, Tipo Movimentação, CNPJ Conta, Agência, Conta, CNPJ/Agência/Conta Beneficiária, Beneficiário, CO_SEQ \| Valor Movimentação, Saldo Movimentação |
| EXTRATOS_MENSAIS_CEF_ANTERIOR_2018 | `e472508e-960e-473c-aeb6-f26d299c13ec` | `jAJam` | calc cond | idem |
| EXTRATOS_MENSAIS_CALAMIDADE | `34f02362-7125-40a6-8a26-070414b38792` | `brKbS` | calc cond | idem + Banco, ID |
| EXTRATOS_MENSAIS_CUSTEIOSUS | `64ce3085-161e-443f-862e-6f6ee3a10664` | `jAJam` | calc cond | idem + Banco |
| EXTRATOS_MENSAIS_EMENDA | `f969d4ee-32e1-4755-b01a-923ce3a876e1` | `ZsJNJyt` | calc cond | idem + Banco, Nº Emenda, Nº Proposta, Parlamentar, Tipo Emenda, ID |
| EXTRATOS_MENSAIS_ENFERMAGEM | `7a9dfcc3-469a-4300-adf8-72a7eef99759` | `jAJam` | calc cond | idem + Banco |
| EXTRATOS_MENSAIS_INVESTSUS | `c90a7245-ab2e-46a1-b319-94c9afe328b6` | `jAJam` | calc cond | idem + Banco, ID |
| EXTRATOS_MENSAIS_PES_RIO_DOCE | `dd66a5d2-8d67-484f-8108-c2edf1bda95d` | `brKbS` | calc cond | idem + Banco, ID |

Os extratos mensais exigem seleção UF + Município + Esfera; o volume total sem filtro ficou pendente (ver bloqueios).

## Bloqueios / riscos

1. **Volume**: FAF (20,3 mi linhas), saldos diários BB (14,4 mi) e CEF (17,2 mi) são grandes. Carga completa via `GetHyperCubeData` = ~1 chamada por 10k células → milhares de chamadas; recomendo fatiar por seleção (ANO/UF/mês) e paralelizar pouco, para não derrubar/ser bloqueado pelo servidor do MS.
2. **ExportData trunca em ~5M células** — não serve para as tabelas grandes.
3. **Condições de cálculo**: contornáveis com objeto de sessão, mas o servidor deles pode demorar muito para calcular o cubo inteiro (os extratos mensais sem filtro passaram de 10 min sem resposta) → para extratos, iterar UF × Município × Esfera (ou por mês) é obrigatório na prática.
4. Os nomes de coluna são rótulos de exibição (com acentos, `=expressões`, alguns `None`); no loader vale mapear para snake_case.
5. IDs de objetos podem mudar quando o MS republica os apps — o loader deve validar `qSize` e os títulos de coluna antes de carregar.
6. Nenhuma credencial necessária; nenhum bloqueio de acesso encontrado.

## Recomendação para o passo 2

Loader Python (websocket-client + requests) usando a receita acima: abre o app, cria objeto de sessão com a `qHyperCubeDef` da tabela principal (sem calc cond), seleciona fatias (ANO/UF/mês) e pagina `GetHyperCubeData` (páginas de 10.000/qcx linhas) → `COPY` em `stg_paineis_fns`, merge incremental em `base_fns` (padrão `carga_dados_faf`). Para tabelas < 5M células, `ExportData` CSV é o atalho mais simples.

## Passo 2 — prova de carga (2026-10-23)

- Script: `scripts/carga_tabela.py <appId> <objectId> <tabela>` (Engine API anônima → objeto de sessão sem calc cond → `GetHyperCubeData` paginado → `COPY`). Cria `stg_paineis_fns` se não existir e uma tabela **nova** (falha se já existir; não apaga nada). Credenciais: `FNS_DB_*` de `D:\ProjetosSandro\transfere_pro\APIS\transferencias_fundo_a_fundo\.env` (transferepro @ localhost:5433).
- Criado: schema `stg_paineis_fns` + `stg_paineis_fns.instrumentos_investimentos` (18 colunas snake_case: `vl_*` numeric, `data_portaria` date, resto text; + `dt_carga`). Nenhum outro schema tocado.
- Resultado: **430.879 linhas** (qSize 430.880; a única ausente é uma linha-artefato só com IBGE 260545). Extração ~205–245 s (777 páginas), COPY ~10 s.
- Validação vs `Sum()` do Qlik: vl_proposta 244.569.567.910,23 · vl_empenhado 229.251.978.870,13 · vl_pago 218.136.121.529,33 — **iguais**. Linha de amostra (proposta 00161822000126005) idêntica ao painel.
- Achados para o `base_fns`: 7.139 instrumentos sem PROPOSTA (convênios/contratos de repasse, chave = portaria/convênio); 12.346 linhas só com PROPOSTA (órfãs do modelo, sem valores) → filtrar; `data_portaria` vai de 1999 a 2103 (erro na origem); sem chave única (398.174 propostas distintas).

## Passo 3 — recarga da staging + base_fns (2026-10-26)

- `scripts/carga_tabela.py` agora, numa única transação: recria o conteúdo da staging (`TRUNCATE` + `COPY`), confere `count = qSize` (senão rollback de tudo) e faz merge em `base_fns.<tabela>`.
- `base_fns` já existia (projeto Consulta FNS: `tab_proposta`, `controle_carga`, `controle_carga_dia`) — essas tabelas não foram tocadas; só foi criada `base_fns.instrumentos_investimentos`.
- Sem chave natural → `hash_linha` = md5 da linha inteira (PK). Merge: linha nova é inserida; linha que some da origem vira `fl_ativo = false` (+ `dt_atualizacao`); se voltar, é reativada. Nada é apagado. Colunas de controle: `dt_inclusao`, `dt_atualizacao`, `fl_ativo`. Linhas órfãs do Qlik (só 1 coluna preenchida) não entram na base.
- 1ª execução: staging 430.884 (= qSize), base 418.537 inseridas. 2ª execução: 0 inseridas, 0 desativadas (idempotente). ~4–5,5 min por execução.
- Somas (staging = base ativa = Qlik): vl_proposta 244.572.265.002,32 · vl_empenhado 229.267.191.553,46 · vl_pago 218.136.406.908,33.
- Limite conhecido: uma alteração de valor numa linha aparece como linha nova + linha antiga desativada (não há chave para "update").

## Passo 4 — carga das demais tabelas do escopo (2026-10-26)

- `scripts/carga_todas.py` (lista de 30 tabelas app/objeto/destino) roda `carga_tabela.main` para cada uma; falha de uma não para as outras. Log: `logs/carga_todas_20261026.log`. Duração total ~31 min.
- Correções no extrator: `qColumnOrder = []` (o qMatrix vinha na ordem de exibição → colunas trocadas), remoção das condições de exibição por coluna (colunas ocultas sumiam do qMatrix), descarte de colunas com erro 7005, `qMode = "S"` para pivots, checagem de nº de colunas por linha, tipos inferidos pelos dados (date/numeric só se todos os valores forem numéricos e o nome indicar), nomes duplicados/sem título tratados, saldo por competência → `saldo_competencia` + `competencia`.
- 29/30 carregadas, staging = qSize em todas. `instrumentos_investimentos` re-rodada: 0 mudanças.
- **Falhou: `emendas_instrumentos`** — disco cheio no Postgres (`C:\Program Files\PostgreSQL\17\data`, drive C: com 4 GB livres, 99%). Transação desfeita, nada parcial.
- Diferenças staging → base são linhas duplicadas/órfãs no Qlik (DISTINCT por hash), ex.: instrumentos_cnes_detalhado 540.273 → 502.356, obras_geolocalizacao 46.624 → 44.297.
- Espaço usado: base_fns ~1,0 GB, stg_paineis_fns ~0,66 GB.

## Passo 5 — tablespace no D: + emendas_instrumentos (2026-10-26)

- Tablespace `ts_faf` (já existente, `D:\pgdata_faf`). Movidas para ele, uma a uma (menor → maior), as **58 tabelas criadas por esta carga** (29 em `stg_paineis_fns`, 29 em `base_fns`) e seus índices. **Não movidas** (pré-existentes do projeto Consulta FNS): `base_fns.tab_proposta`, `controle_carga`, `controle_carga_dia`.
- C: livre: 4,74 GB antes → 6,22 GB depois da mudança → 6,4 GB depois da carga de emendas_instrumentos.
- `carga_tabela.py`: a conexão usa `default_tablespace` e `temp_tablespaces` = `ts_faf` (configurável por `FNS_DB_TABLESPACE`, variável de ambiente ou .env) → tabelas, PKs e temporários de sort/hash vão para o D:.
- `emendas_instrumentos` recarregada: staging 326.774 = qSize, base 326.774 ativas, tabela + PK em `ts_faf`. Somas staging = base = Qlik: instrumento_r 159.804.356.794,70 · empenhado_r 159.445.402.762,47 · pago_r 149.652.845.547,76. Tempo 334 s.
- Agora 30/30 tabelas do escopo carregadas.

## Passo 6 — agendamento (2026-10-27)

- Ponto de entrada: `scripts/executar_carga.ps1` (Windows) / `scripts/executar_carga.sh` (Linux) → `scripts/carga_todas.py` (30 tabelas). Log datado em `logs/execucao_AAAAMMDD_HHMMSS.txt`, limpeza de logs > 90 dias, trava no banco (`pg_advisory_lock`; 2ª execução simultânea sai com código 2), saída 1 se alguma tabela falhar. Carga completa com sucesso grava `logs/ultimo_sucesso.txt`; nova execução no mesmo dia se auto-ignora (`--forcar` para recarregar).
- Windows: tarefa **"FNS - Carga Paineis InvestSUS"**, diária 06:00 + nova tentativa 12:00, registrada com `scripts/agendar_tarefa.ps1 -SomenteLogado` (roda só com o Sandro logado). Para rodar deslogado: PowerShell como Administrador → `D:\ProjetosSandro\transfere_pro\APIS\carga_painel_fns\scripts\agendar_tarefa.ps1` (pede a senha numa janela segura, não grava). A tarefa "FAF - Carga Transferegov" não está registrada nesta máquina.
- Linux: `scripts/agendar_linux.sh` (systemd timer `fns-paineis-carga`, ou `--cron`) e passo a passo em `docs/AGENDAMENTO_LINUX.md`; `.env.example` e `requirements.txt` na raiz. No Linux o `.env` fica na raiz do projeto e `FNS_DB_TABLESPACE` deve ficar vazio se o tablespace não existir lá.
- Testes: execução com 2 tabelas pequenas → código 0 e log criado; trava → código 2; cálculo de horários do cron (06:00/12:00 BRT = 09:00/15:00 UTC).

## Passo 7 — configuração só pelo .env do projeto (2026-10-29)

- `scripts/carga_tabela.py` lê **somente** `<projeto>/.env` (não usa mais o `.env` do projeto FAF nem a variável `CARGA_FNS_ENV`). Variáveis obrigatórias: `FNS_DB_HOST`, `FNS_DB_PORT`, `FNS_DB_NOME`, `FNS_DB_USUARIO`, `FNS_DB_SENHA` e `FNS_DB_TABLESPACE` (esta pode ser vazia = tablespace padrão). Sem o arquivo ou com variável faltando, a carga para com mensagem listando o que falta (código 1).
- `.env.example` atualizado; `.gitignore` criado (`.env`, `.venv/`, `__pycache__/`, `logs/`, `raw/`).
- Passo 6 e anteriores: onde diz "credenciais do .env do projeto FAF", vale agora o `.env` do próprio projeto.
