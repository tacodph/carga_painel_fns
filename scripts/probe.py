"""Mapeia apps/objetos dos paineis InvestSUS via Qlik Engine API anonima."""
import json, ssl, sys, re, glob, os, time, requests, websocket, urllib3
urllib3.disable_warnings()
H = "investsuspaineis.saude.gov.br"
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/130.0"
TABLE_TYPES = {"table", "sn-table", "pivot-table", "sn-pivot-table", "TableBox", "straight-table"}
RAW = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "raw")

PAGE = f"https://{H}/extensions/CGIN_InvestsusPaineis/CGIN_InvestsusPaineis.html"
BROWSER_HEADERS = {
    "User-Agent": UA,
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "pt-BR,pt;q=0.9,en;q=0.8",
    "Referer": PAGE,
    "Origin": f"https://{H}",
}

def _csrf(tentativas=4):
    """Obtem sessao + token CSRF; refaz a sessao com backoff em 403/429/5xx."""
    for i in range(tentativas):
        s = requests.Session(); s.headers.update(BROWSER_HEADERS); s.verify = False
        s.get(PAGE, timeout=60)
        time.sleep(1 + i)  # pausa curta: evita parecer robo
        r = s.get(f"https://{H}/qps/csrftoken?xrfkey=abcdefghijklmnop",
                  headers={"X-Qlik-Xrfkey": "abcdefghijklmnop"}, timeout=60)
        if r.status_code in (403, 429) or r.status_code >= 500:
            if i < tentativas - 1:
                time.sleep(5 * 2 ** i); continue
            raise RuntimeError(f"HTTP {r.status_code} em {r.url} | Server: {r.headers.get('Server')} | "
                               f"corpo: {r.text[:300]!r} (provavel bloqueio de WAF/IP deste servidor)")
        r.raise_for_status()
        return s, r

def connect(app):
    s, resposta = _csrf()
    tok = resposta.headers.get("qlik-csrf-token")
    if not tok:
        raise RuntimeError(
            "Qlik nao retornou o cabecalho qlik-csrf-token "
            f"(HTTP {resposta.status_code}, Content-Type: "
            f"{resposta.headers.get('Content-Type', 'ausente')}, "
            f"URL final: {resposta.url}). Verifique o acesso ao servico Qlik."
        )
    ck = "; ".join(f"{k}={v}" for k, v in s.cookies.get_dict().items())
    ws = websocket.create_connection(f"wss://{H}/app/{app}?qlik-csrf-token={tok}",
        sslopt={"cert_reqs": ssl.CERT_NONE}, header=[f"User-Agent: {UA}", f"Cookie: {ck}"],
        origin=f"https://{H}", timeout=120)
    ws._id = 0; ws._http = s
    return ws

def rpc(ws, method, handle=-1, params=None):
    ws._id += 1
    ws.send(json.dumps({"jsonrpc": "2.0", "id": ws._id, "method": method, "handle": handle, "params": params or {}}))
    while True:
        m = json.loads(ws.recv())
        if m.get("id") == ws._id:
            if "error" in m: raise RuntimeError(m["error"])
            return m["result"]

def describe(ws, h, oid):
    o = rpc(ws, "GetObject", h, {"qId": oid})["qReturn"]
    if not o: return {"id": oid, "erro": "nao encontrado"}
    lay = rpc(ws, "GetLayout", o["qHandle"])["qLayout"]
    d = {"id": oid, "tipo": lay["qInfo"]["qType"], "titulo": lay.get("title") or ""}
    hc = lay.get("qHyperCube")
    if hc:
        d["dims"] = [x.get("qFallbackTitle") for x in hc.get("qDimensionInfo", [])]
        d["medidas"] = [x.get("qFallbackTitle") for x in hc.get("qMeasureInfo", [])]
        d["linhas"] = hc["qSize"]["qcy"]; d["colunas"] = hc["qSize"]["qcx"]
    d["_handle"] = o["qHandle"]
    return d

def export(ws, handle):
    r = rpc(ws, "ExportData", handle, {"qFileType": "OOXML", "qPath": "/qHyperCubeDef", "qExportState": "A"})
    url = r.get("qUrl"); full = f"https://{H}{url}" if url and url.startswith("/") else url
    resp = ws._http.get(full) if full else None
    return {"qUrl": url, "http": resp.status_code if resp is not None else None,
            "bytes": len(resp.content) if resp is not None else 0}

def objs_from_js(folder):
    txt = "\n".join(open(f, encoding="utf-8", errors="ignore").read() for f in glob.glob(f"{RAW}/{folder}/*.js"))
    txt = re.sub(r"(?m)^\s*//.*$", "", txt)
    app = re.search(r"ID_APP\s*=\s*'([^']+)'", txt).group(1)
    ids = re.findall(r"getObject\(\s*['\"]([^'\"]*)['\"]\s*,\s*['\"]([^'\"]+)['\"]", txt)
    return app, list(dict.fromkeys(i for _, i in ids))

if __name__ == "__main__":
    out = {}
    for folder in sys.argv[1:]:
        app, ids = objs_from_js(folder)
        ws = connect(app)
        h = rpc(ws, "OpenDoc", params={"qDocName": app})["qReturn"]["qHandle"]
        al = rpc(ws, "GetAppLayout", h)["qLayout"]
        res = {"appId": app, "titulo": al["qTitle"], "ultimo_reload": al.get("qLastReloadTime"), "objetos": []}
        infos = rpc(ws, "GetAllInfos", h)["qInfos"]
        res["tipos"] = sorted({i["qType"] for i in infos})
        tbl = [i["qId"] for i in infos if i["qType"] in TABLE_TYPES]
        res["ids_no_js"] = ids
        for oid in tbl:
            try: d = describe(ws, h, oid); d["no_mashup"] = oid in ids; res["objetos"].append(d)
            except Exception as e: res["objetos"].append({"id": oid, "erro": str(e)[:200]})
        tabs = [o for o in res["objetos"] if o.get("linhas")]
        if tabs:
            big = max(tabs, key=lambda o: o["linhas"])
            try: res["export_teste"] = {"obj": big["id"], **export(ws, big["_handle"])}
            except Exception as e: res["export_teste"] = {"obj": big["id"], "erro": str(e)[:200]}
        for o in res["objetos"]: o.pop("_handle", None)
        out[folder] = res; ws.close()
        print(folder, app, len(ids), "objs", file=sys.stderr)
    json.dump(out, open(os.path.join(RAW, "probe.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
