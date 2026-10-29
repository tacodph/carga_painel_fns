"""Carrega uma tabela do Qlik (InvestSUS) em stg_paineis_fns (recarga completa) e faz merge em base_fns.

Uso: python carga_tabela.py <appId> <objectId> <tabela_destino>
Tudo numa transacao: se a contagem nao bater com o qSize, nada muda.
base_fns nao tem chave natural: hash_linha = md5 da linha; linha que some da origem vira fl_ativo=false.
"""
import csv, io, os, re, sys, time, unicodedata
from datetime import date, timedelta
import psycopg2
from probe import connect, rpc

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
# .env: CARGA_FNS_ENV > <raiz>/.env (ex.: Linux) > .env do projeto FAF nesta maquina
ENV = os.environ.get("CARGA_FNS_ENV") or (
    os.path.join(RAIZ, ".env") if os.path.exists(os.path.join(RAIZ, ".env"))
    else r"D:\ProjetosSandro\transfere_pro\APIS\transferencias_fundo_a_fundo\.env")
SCHEMA = "stg_paineis_fns"
BASE = "base_fns"
NUM_HINT = re.compile(r"^(vl|valor|saldo|soma|qtd|quantidade|percentual|populacao|gru_valor)|_r$|(^|_)(valor|saldo)(_|$)")
DATE_HINT = re.compile(r"(^|_)(data|dt)(_|$)")
COMPETENCIA = re.compile(r"COMPETENCIA SALDO (\d\d/\d{4})", re.I)  # titulo muda todo mes


def env():
    d = {}
    for line in open(ENV, encoding="utf-8"):
        if "=" in line and not line.lstrip().startswith("#"):
            k, v = line.strip().split("=", 1)
            d[k] = v
    return d


def conecta():
    e = env()
    # tabelas, indices e temporarios (sort/hash) no D:, o C: do Postgres esta cheio
    # vazio = tablespace padrao do servidor (ex.: Linux sem ts_faf)
    ts = os.environ.get("FAF_DB_TABLESPACE", e.get("FAF_DB_TABLESPACE", "ts_faf"))
    opcoes = f"-c default_tablespace={ts} -c temp_tablespaces={ts}" if ts else ""
    return psycopg2.connect(host=e["FAF_DB_HOST"], port=e["FAF_DB_PORT"], dbname=e["FAF_DB_NOME"],
                            user=e["FAF_DB_USUARIO"], password=e["FAF_DB_SENHA"], options=opcoes)


def snake(s):
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9]+", "_", s).strip("_")


def nomes_colunas(titulos):
    cols, extras = [], {}
    for i, t in enumerate(titulos):
        m = COMPETENCIA.search(t or "")
        if m:
            extras["competencia"] = m.group(1)
            c = "saldo_competencia"
        else:
            c = snake(t or "")[:55] or f"col_{i + 1}"
        if c[0].isdigit():
            c = "c_" + c
        while c in cols:
            c += "_2"
        cols.append(c)
    return cols, extras


def numerico(n):
    return n not in (None, "NaN")


def tipo(col, medida, celulas):
    cheias = [c for c in celulas if not (c.get("qIsNull") or c.get("qText") in (None, "-"))]
    todos_num = all(numerico(c.get("qNum")) for c in cheias)
    if DATE_HINT.search(col) and todos_num:
        return "date"
    if (medida or NUM_HINT.search(col)) and todos_num:
        return "numeric"
    return "text"


def valor(cell, t):
    if cell.get("qIsNull") or cell.get("qText") in (None, "-"):
        return None
    n = cell.get("qNum")
    if t == "numeric":
        return repr(n)
    if t == "date":  # serial do Qlik = dias desde 1899-12-30
        return (date(1899, 12, 30) + timedelta(days=int(n))).isoformat()
    return cell.get("qText")


def sessao(ws, h, hc):
    return rpc(ws, "CreateSessionObject", h, {"qProp": {"qInfo": {"qType": "carga"}, "qHyperCubeDef": hc}})["qReturn"]["qHandle"]


def extrai(app, oid):
    ws = connect(app)
    h = rpc(ws, "OpenDoc", params={"qDocName": app})["qReturn"]["qHandle"]
    o = rpc(ws, "GetObject", h, {"qId": oid})["qReturn"]["qHandle"]
    hc = rpc(ws, "GetProperties", o)["qProp"]["qHyperCubeDef"]
    hc.pop("qCalcCond", None); hc.pop("qCalcCondition", None)
    hc["qInitialDataFetch"] = []; hc["qMode"] = "S"  # pivot vira tabela simples
    hc["qColumnOrder"] = []  # qMatrix segue qColumnOrder; vazio = ordem da definicao
    for x in hc.get("qDimensions", []) + hc.get("qMeasures", []):
        x.pop("qCalcCondition", None); x.pop("qCalcCond", None)  # colunas ocultas por condicao somem do qMatrix
    s = sessao(ws, h, hc)
    lay = rpc(ws, "GetLayout", s)["qLayout"]["qHyperCube"]
    nd = len(lay["qDimensionInfo"])
    ruins = [i for i, x in enumerate(lay["qDimensionInfo"] + lay["qMeasureInfo"]) if "qError" in x]
    if ruins:  # coluna com erro (ex.: 7005) nao vem nos dados: tira da definicao
        print(f"  ignorando colunas com erro: {ruins}")
        hc["qDimensions"] = [x for i, x in enumerate(hc["qDimensions"]) if i not in ruins]
        hc["qMeasures"] = [x for i, x in enumerate(hc.get("qMeasures", [])) if i + nd not in ruins]
        hc["qInterColumnSortOrder"] = []
        s = sessao(ws, h, hc)
        lay = rpc(ws, "GetLayout", s)["qLayout"]["qHyperCube"]
    titulos = [x.get("qFallbackTitle") for x in lay["qDimensionInfo"] + lay["qMeasureInfo"]]
    medidas = [False] * len(lay["qDimensionInfo"]) + [True] * len(lay["qMeasureInfo"])
    cx, cy = lay["qSize"]["qcx"], lay["qSize"]["qcy"]
    passo = 10000 // cx
    linhas = []
    for top in range(0, cy, passo):
        pg = rpc(ws, "GetHyperCubeData", s, {"qPath": "/qHyperCubeDef",
                 "qPages": [{"qTop": top, "qLeft": 0, "qWidth": cx, "qHeight": min(passo, cy - top)}]})
        linhas += pg["qDataPages"][0]["qMatrix"]
    assert all(len(r) == len(titulos) for r in linhas), "qMatrix com numero de colunas diferente do layout"
    ws.close()
    return titulos, medidas, cy, linhas


def main(app, oid, tabela):
    t0 = time.time()
    titulos, medidas, cy, linhas = extrai(app, oid)
    cols, extras = nomes_colunas(titulos)
    tipos = [tipo(c, m, [r[i] for r in linhas]) for i, (c, m) in enumerate(zip(cols, medidas))]
    print(f"[{tabela}] extraidas {len(linhas)}/{cy} linhas em {time.time() - t0:.0f}s")

    # staging fiel ao qSize: linhas orfas do modelo Qlik (so PROPOSTA ou so IBGE) ficam; limpar no base_fns
    buf = io.StringIO()
    w = csv.writer(buf)
    for r in linhas:
        w.writerow(["" if (v := valor(c, t)) is None else v for c, t in zip(r, tipos)] + list(extras.values()))
    buf.seek(0)
    cols += list(extras); tipos += ["text"] * len(extras)

    lista = ", ".join(cols)
    ddl = ", ".join(f"{c} {t}" for c, t in zip(cols, tipos))
    con = conecta()
    with con, con.cursor() as cur:
        cur.execute(f"CREATE SCHEMA IF NOT EXISTS {SCHEMA}")
        cur.execute(f"CREATE TABLE IF NOT EXISTS {SCHEMA}.{tabela} ({ddl}, dt_carga timestamp NOT NULL DEFAULT now())")
        cur.execute(f"TRUNCATE {SCHEMA}.{tabela}")
        cur.copy_expert(f"COPY {SCHEMA}.{tabela} ({lista}) FROM STDIN WITH (FORMAT csv)", buf)
        cur.execute(f"SELECT count(*) FROM {SCHEMA}.{tabela}")
        n = cur.fetchone()[0]
        assert n == cy, f"staging {n} != qSize {cy}"  # rollback de tudo

        cur.execute(f"""CREATE TABLE IF NOT EXISTS {BASE}.{tabela} (hash_linha text PRIMARY KEY, {ddl},
            dt_inclusao timestamp NOT NULL DEFAULT now(), dt_atualizacao timestamp, fl_ativo boolean NOT NULL DEFAULT true)""")
        # linhas orfas do modelo Qlik (1 coluna so preenchida) nao vao para a base
        cur.execute(f"""CREATE TEMP TABLE nova ON COMMIT DROP AS SELECT DISTINCT md5(row({lista})::text) AS hash_linha, {lista}
            FROM {SCHEMA}.{tabela} WHERE num_nonnulls({lista}) > 1 + {len(extras)}""")
        cur.execute(f"""INSERT INTO {BASE}.{tabela} (hash_linha, {lista}) SELECT hash_linha, {lista} FROM nova
            ON CONFLICT (hash_linha) DO UPDATE SET fl_ativo = true, dt_atualizacao = now() WHERE NOT {BASE}.{tabela}.fl_ativo""")
        afetadas = cur.rowcount
        # saldo por competencia: so desativa linhas da mesma competencia (as antigas sao historico)
        filtro = f"AND competencia = '{extras['competencia']}'" if "competencia" in extras else ""
        cur.execute(f"""UPDATE {BASE}.{tabela} b SET fl_ativo = false, dt_atualizacao = now()
            WHERE fl_ativo {filtro} AND NOT EXISTS (SELECT 1 FROM nova n WHERE n.hash_linha = b.hash_linha)""")
        desativadas = cur.rowcount
        cur.execute(f"SELECT count(*) FILTER (WHERE fl_ativo), count(*) FROM {BASE}.{tabela}")
        ativas, total = cur.fetchone()
    con.close()
    print(f"[{tabela}] staging {n} linhas (qSize={cy}); base: {afetadas} inseridas/reativadas, "
          f"{desativadas} desativadas, {ativas} ativas de {total}; {time.time() - t0:.0f}s")
    return {"tabela": tabela, "qsize": cy, "staging": n, "inseridas": afetadas, "desativadas": desativadas,
            "ativas": ativas, "segundos": round(time.time() - t0)}


if __name__ == "__main__":
    main(*sys.argv[1:4])
