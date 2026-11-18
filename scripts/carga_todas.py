"""Roda carga_tabela.main para todas as tabelas do escopo. Uma falha nao interrompe as outras.

Uso: python carga_todas.py [--forcar] [tabela ...]   (sem tabelas = todas)
Codigos de saida: 0 sucesso/ignorada, 1 erro em alguma tabela, 2 ja existe carga em execucao.
Carga completa com sucesso grava logs/ultimo_sucesso.txt; outra execucao no mesmo dia se auto-ignora
(e o que torna segura a nova tentativa agendada das 12:00). --forcar ignora essa marca.
Fora do escopo (ver mapeamento_paineis.md): painel FAF e tabelas de Ordens Bancarias.
"""
import json, os, re, sys, time, traceback, unicodedata
from datetime import date, datetime
from carga_tabela import RAIZ, NOME_ENV, conecta, main

SP = "transfere_pro_transferegov"
ORIGEM_PARLAMENTAR = "painel_fns"
# (tabela em base_fns, coluna com o nome); colunas "solicitante" trazem varios nomes separados por " / "
FONTES_PARLAMENTAR = [
    ("emendas_instrumentos", "parlamentar"),
    ("emendas_instrumentos", "parlamentar_solicitante_a_partir_de_2025"),
    ("emendas_cadastro_propostas", "parlamentar"),
    ("emendas_indicacao_exercicio_atual", "parlamentar"),
    ("emendas_parlamentares_solicitantes", "parlamentar_solicitante"),
    ("emendas_autores_comissao", "parlamentar_participante_da_indicacao_de_comissao"),
]


def normaliza(nome):
    s = unicodedata.normalize("NFKD", nome).encode("ascii", "ignore").decode().upper()
    return " ".join(re.sub(r"[^A-Z0-9]+", " ", s).split())


def tipo_parlamentar(n):
    if n == "RELATOR GERAL": return n
    if n.startswith("BANCADA"): return "BANCADA"
    if n.startswith(("COM ", "COMISSAO")): return "COMISSAO"
    return "INDIVIDUAL"


def atualiza_parlamentares(con):
    """Cadastra em tab_parlamentares/_alias os nomes do painel ainda nao cadastrados (sem commit; quem chama decide).
    Novos entram com fl_revisar=true: podem ser grafia nova de alguem ja cadastrado e precisam ser mesclados a mao."""
    cur = con.cursor()
    cur.execute("SELECT to_regclass(%s) IS NOT NULL AND to_regclass(%s) IS NOT NULL",
                (f"{SP}.tab_parlamentares", f"{SP}.tab_parlamentares_alias"))
    if not cur.fetchone()[0]:
        print(f"[parlamentares] tabelas {SP}.tab_parlamentares* nao existem neste banco; ignorado")
        return {"tabela": "parlamentares", "novos": 0, "ignorado": True}
    nomes = {}
    for tab, col in FONTES_PARLAMENTAR:
        cur.execute(f"SELECT DISTINCT {col} FROM base_fns.{tab} WHERE fl_ativo AND {col} IS NOT NULL ORDER BY 1")
        for (v,) in cur.fetchall():
            for parte in v.split("/"):
                if (n := normaliza(parte)) and n != "NAO SE APLICA":
                    nomes.setdefault(n, parte.strip())
    cur.execute(f"SELECT nome_normalizado FROM {SP}.tab_parlamentares_alias "
                f"UNION SELECT nome_normalizado FROM {SP}.tab_parlamentares")
    existentes = {r[0] for r in cur.fetchall()}
    novos = {n: o for n, o in nomes.items() if n not in existentes}
    for n, o in sorted(novos.items()):
        cur.execute(f"INSERT INTO {SP}.tab_parlamentares (nome_parlamentar, nome_normalizado, tipo_parlamentar, fl_revisar) "
                    f"VALUES (%s, %s, %s, true) RETURNING id_parlamentar", (o, n, tipo_parlamentar(n)))
        cur.execute(f"INSERT INTO {SP}.tab_parlamentares_alias (nome_normalizado, nome_original, id_parlamentar, origem) "
                    f"VALUES (%s, %s, %s, %s)", (n, o, cur.fetchone()[0], ORIGEM_PARLAMENTAR))
    print(f"[parlamentares] {len(nomes)} nomes no painel; {len(novos)} novos cadastrados (fl_revisar=true)")
    return {"tabela": "parlamentares", "nomes_painel": len(nomes), "novos": len(novos)}

TRAVA = 762731  # pg_advisory_lock: impede duas cargas ao mesmo tempo (por banco)
# marca por destino: .env -> ultimo_sucesso.txt; .env.forge -> ultimo_sucesso.env.forge.txt
MARCA = os.path.join(RAIZ, "logs", "ultimo_sucesso.txt" if NOME_ENV == ".env" else f"ultimo_sucesso{NOME_ENV}.txt")

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
    export_dir = None
    if os.name == "nt" and os.environ.get("FNS_EXPORTAR_ARQUIVOS") == "1":
        export_dir = os.path.join(RAIZ, "arquivos", datetime.now().strftime("%Y%m%d_%H%M%S"))
    for app, oid, tabela in TABELAS:
        if escolhidas and tabela not in escolhidas:
            continue
        try:
            resultado.append(main(app, oid, tabela, export_dir=export_dir))
        except Exception as e:
            traceback.print_exc()
            resultado.append({"tabela": tabela, "erro": f"{type(e).__name__}: {e}"[:300]})
    try:  # nomes de parlamentares novos; uma transacao so, falhou = nada muda
        con = conecta()
        resultado.append(atualiza_parlamentares(con))
        con.commit(); con.close()
    except Exception as e:
        traceback.print_exc()
        resultado.append({"tabela": "parlamentares", "erro": f"{type(e).__name__}: {e}"[:300]})
    erros = sum("erro" in r for r in resultado)
    print(json.dumps(resultado, ensure_ascii=False, indent=1))
    print(f"total {time.time() - t0:.0f}s; tabelas: {len(resultado)}; erros: {erros}")
    if not erros and not escolhidas:
        os.makedirs(os.path.dirname(MARCA), exist_ok=True)
        open(MARCA, "w").write(hoje)
    trava.close()
    sys.exit(1 if erros else 0)
