"""Roda carga_tabela.main para todas as tabelas do escopo. Uma falha nao interrompe as outras.

Uso: python carga_todas.py [--forcar] [tabela ...]   (sem tabelas = todas)
Codigos de saida: 0 sucesso/ignorada, 1 erro em alguma tabela, 2 ja existe carga em execucao.
Carga completa com sucesso grava logs/ultimo_sucesso.txt; outra execucao no mesmo dia se auto-ignora
(e o que torna segura a nova tentativa agendada das 12:00). --forcar ignora essa marca.
Fora do escopo (ver mapeamento_paineis.md): painel FAF e tabelas de Ordens Bancarias.
"""
import json, os, sys, time, traceback
from datetime import date
from carga_tabela import RAIZ, conecta, main

TRAVA = 762731  # pg_advisory_lock: impede duas cargas ao mesmo tempo
MARCA = os.path.join(RAIZ, "logs", "ultimo_sucesso.txt")

INSTRUMENTOS = "0ba8c451-0b87-4657-ae70-ee6dcf11aec1"
EMENDAS = "585aca8d-2714-487d-a08e-34150047e7dd"
OBRAS = "955106a0-664e-4983-bacf-8f78ef1ee435"
NOVO_PAC = "6c51cf78-c6df-4ed6-b9a7-bfe261704189"
MONITORAMENTO = "6a19d3a2-cf45-49a8-8d4e-7c501f41dae9"

TABELAS = [
    (INSTRUMENTOS, "BbeRjR", "instrumentos_investimentos"),
    (INSTRUMENTOS, "jLmPjCM", "instrumentos_empenhos"),
    (INSTRUMENTOS, "MNfPp", "instrumentos_cnes_propostas_faf"),
    (INSTRUMENTOS, "HyYdkG", "instrumentos_cnes_detalhado"),
    (EMENDAS, "wqkNqZ", "emendas_instrumentos"),
    (EMENDAS, "tjpJm", "emendas_indicacao_exercicios_anteriores"),
    (EMENDAS, "dfkFC", "emendas_indicacao_exercicio_atual"),
    (EMENDAS, "HMwhMX", "emendas_cadastro_propostas"),
    (EMENDAS, "sXpUeT", "emendas_dotacao_exercicio_atual"),
    (EMENDAS, "UUWFP", "emendas_sidorc"),
    (EMENDAS, "JynxMw", "emendas_autores_comissao"),
    (EMENDAS, "YKdbhkW", "emendas_parlamentares_solicitantes"),
    (EMENDAS, "fbktZP", "emendas_impedimentos_tecnicos"),
    (EMENDAS, "Sbbkn", "emendas_cnes"),
    (OBRAS, "PEtgN", "obras_propostas"),
    (OBRAS, "qLPXj", "obras_propostas_sismob_sispag"),
    (OBRAS, "rrTzjp", "obras_financeiro"),
    (OBRAS, "DxwXMMs", "obras_ciclo_datas"),
    (OBRAS, "hDckPM", "obras_monitoramento"),
    (OBRAS, "azpeFTp", "obras_cancelados_devolucao"),
    (OBRAS, "KDunDrN", "obras_estabelecimentos"),
    (OBRAS, "sPkTs", "obras_sisgru"),
    (OBRAS, "GMBKY", "obras_geolocalizacao"),
    (NOVO_PAC, "YuHaaW", "novo_pac_propostas"),
    (NOVO_PAC, "bSJRDW", "novo_pac_respostas_selecao"),
    (MONITORAMENTO, "rmGMxMM", "monitoramento_visao_geral"),
    (MONITORAMENTO, "BmzHxr", "monitoramento_saldos_rastreabilidade"),
    (MONITORAMENTO, "jnpaty", "monitoramento_nao_monitorados"),
    ("036b49d3-9e96-491e-843a-1c454b451f8c", "XGQJFj", "saldo_competencia_bb"),
    ("1eccc3d9-f704-474a-ae52-9177ab37c1cf", "XGQJFj", "saldo_competencia_cef"),
]

if __name__ == "__main__":
    forcar = "--forcar" in sys.argv
    escolhidas = {a for a in sys.argv[1:] if not a.startswith("--")}
    hoje = date.today().isoformat()
    if not forcar and not escolhidas and os.path.exists(MARCA) and open(MARCA).read().strip() == hoje:
        print(f"IGNORADA: carga completa de {hoje} ja concluida com sucesso (use --forcar)")
        sys.exit(0)
    trava = conecta(); trava.autocommit = True
    cur = trava.cursor()
    cur.execute("SELECT pg_try_advisory_lock(%s)", (TRAVA,))
    if not cur.fetchone()[0]:
        print("Ja existe uma carga em execucao (trava do banco); saindo.")
        sys.exit(2)
    resultado = []
    t0 = time.time()
    for app, oid, tabela in TABELAS:
        if escolhidas and tabela not in escolhidas:
            continue
        try:
            resultado.append(main(app, oid, tabela))
        except Exception as e:
            traceback.print_exc()
            resultado.append({"tabela": tabela, "erro": f"{type(e).__name__}: {e}"[:300]})
    erros = sum("erro" in r for r in resultado)
    print(json.dumps(resultado, ensure_ascii=False, indent=1))
    print(f"total {time.time() - t0:.0f}s; tabelas: {len(resultado)}; erros: {erros}")
    if not erros and not escolhidas:
        os.makedirs(os.path.dirname(MARCA), exist_ok=True)
        open(MARCA, "w").write(hoje)
    trava.close()
    sys.exit(1 if erros else 0)
