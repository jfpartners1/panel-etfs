#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
build_data.py — genera data.json para el panel (resumen-etfs.html)
Fuente: EODHD (https://eodhd.com)

API key por variable de entorno EODHD_API_KEY (NUNCA en el código ni en el navegador):
    export EODHD_API_KEY=tu_clave          (Windows: set EODHD_API_KEY=tu_clave)

Modos:
    python build_data.py --dev      # DESARROLLO: 12 ETFs, sin tiempo real, con caché
    python build_data.py            # completo: 57 ETFs + tiempo real (plan de pago)
    python build_data.py --no-live  # completo solo cierre
    python build_data.py --demo     # sin red, datos sintéticos
    python build_data.py --refresh  # ignora la caché y vuelve a descargar

PLAN GRATUITO de EODHD: 20 llamadas/día · solo cierre (EOD) · ~1 año de histórico.
  -> Usa --dev (gasta ~12 llamadas la 1ª vez del día). La caché evita repetir gasto:
     ejecutándolo otra vez el mismo día = 0 llamadas. Itera el panel sin tocar la cuota.
"""

import argparse, bisect, json, os, random, sys, time, urllib.parse, urllib.request
from datetime import date, datetime, timedelta

API = "https://eodhd.com/api"
KEY = os.environ.get("EODHD_API_KEY", "demo")
CACHE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".cache")
STATE = {"calls": 0}   # llamadas REALES de red hechas en esta ejecución

# ----------------------------------------------------------------------
# UNIVERSO (debe casar con el frontend): ticker, nombre, categoría, key
# ----------------------------------------------------------------------
UNIVERSE = [
    ("SPY","S&P 500","IDX",True),("QQQ","Nasdaq 100","IDX",True),("IWM","Russell 2000","IDX",True),
    ("DIA","Dow 30","IDX",False),("VTI","Total EE.UU.","IDX",False),("EFA","Desarroll. exUS","IDX",False),
    ("EEM","Emergentes","IDX",True),("VGK","Europa","IDX",False),("EWJ","Japón","IDX",False),
    ("FXI","China","IDX",True),("INDA","India","IDX",False),("EWZ","Brasil","IDX",False),
    ("TLT","Treasuries 20Y","ACT",True),("IEF","Treasuries 7-10Y","ACT",False),("LQD","Crédito IG","ACT",False),
    ("HYG","High Yield","ACT",False),("TIP","Ligados inflación","ACT",False),("GLD","Oro","ACT",True),
    ("SLV","Plata","ACT",False),("DBC","Materias primas","ACT",True),("USO","Petróleo","ACT",True),
    ("UNG","Gas natural","ACT",True),("DBA","Agricultura","ACT",False),("VNQ","Inmobiliario","ACT",False),
    ("IBIT","Bitcoin","ACT",True),("DBB","Metales base","ACT",False),
    ("XLK","Tecnología","IND",True),("XLF","Financieras","IND",False),("XLV","Salud","IND",False),
    ("XLE","Energía","IND",True),("XLI","Industria","IND",False),("XLY","Cons. discrec.","IND",False),
    ("XLP","Cons. básico","IND",False),("XLU","Utilities","IND",False),("XLB","Materiales","IND",False),
    ("XLRE","Inmobiliario","IND",False),("XLC","Comunicación","IND",False),("SMH","Semiconductores","IND",True),
    ("KRE","Bancos regionales","IND",True),("XBI","Biotech","IND",True),("XOP","Petróleo E&P","IND",False),
    ("XHB","Construcción","IND",False),("ITA","Defensa","IND",True),
    ("ARKK","Innovación","TEM",True),("BOTZ","Robótica / IA","TEM",True),("ICLN","Energía limpia","TEM",True),
    ("TAN","Solar","TEM",True),("LIT","Litio","TEM",False),("CIBR","Ciberseguridad","TEM",False),
    ("URA","Uranio","TEM",True),("SKYY","Cloud","TEM",False),("FINX","Fintech","TEM",False),
    ("GDX","Mineras oro","TEM",True),("JETS","Aerolíneas","TEM",False),("DRIV","Coches eléctricos","TEM",False),
    ("BLOK","Blockchain","TEM",False),
]
# Subconjunto para DESARROLLO (12 ETFs, cubriendo las 4 categorías)
DEV_TICKERS = {"SPY","QQQ","EEM","VGK","TLT","GLD","USO","XLK","XLE","SMH","ARKK","URA"}

ASSETS_MAP = [("S&P 500","SPY"),("Nasdaq 100","QQQ"),("Small caps","IWM"),("Europa","VGK"),
              ("Emergentes","EEM"),("Bonos 20Y","TLT"),("Oro","GLD"),("Materias primas","DBC"),
              ("Inmobiliario","VNQ"),("Bitcoin","IBIT")]
THEMES_MAP = [("Semis","SMH"),("IA / Robótica","BOTZ"),("Energía limpia","ICLN"),("Ciberseguridad","CIBR"),
              ("Biotech","XBI"),("Defensa","ITA"),("Uranio","URA"),("Mineras oro","GDX"),
              ("Fintech","FINX"),("Cloud","SKYY"),("EV","DRIV")]
SPX_CANDIDATES = ["GSPC.INDX", "SPX.INDX"]   # índice S&P 500 en EODHD (plan de pago)

def eod_sym(tk): return tk + ".US"

# ----------------------------------------------------------------------
# FUENTE: EODHD  (cambia SOLO estas funciones para usar otra fuente)
# ----------------------------------------------------------------------
def _get(url):
    req = urllib.request.Request(url, headers={"User-Agent": "market-panel/1.0"})
    with urllib.request.urlopen(req, timeout=40) as r:
        return json.loads(r.read().decode("utf-8", "replace"))

def fetch_eod(symbol, start):
    """[(date, close_ajustado)] ascendente. Endpoint /api/eod. Cuenta 1 llamada."""
    STATE["calls"] += 1
    url = f"{API}/eod/{symbol}?api_token={KEY}&fmt=json&period=d&from={start.isoformat()}"
    out = []
    for r in _get(url):
        try:
            d = datetime.strptime(r["date"], "%Y-%m-%d").date()
            c = float(r.get("adjusted_close") or r.get("close"))
        except (KeyError, ValueError, TypeError):
            continue
        out.append((d, c))
    out.sort()
    return out

def fetch_live(symbols):
    """{symbol: precio} vía /api/real-time (varios con s=). Solo plan de pago."""
    res, B = {}, 15
    for i in range(0, len(symbols), B):
        chunk = symbols[i:i+B]
        STATE["calls"] += len(chunk)
        url = f"{API}/real-time/{chunk[0]}?api_token={KEY}&fmt=json"
        if len(chunk) > 1:
            url += "&s=" + urllib.parse.quote(",".join(chunk[1:]))
        data = _get(url)
        if isinstance(data, dict): data = [data]
        for q in data:
            try: res[q.get("code")] = float(q.get("close"))
            except (TypeError, ValueError): pass
        time.sleep(0.2)
    return res

def fetch_eod_demo(symbol, start):
    rnd = random.Random(sum(ord(c) for c in symbol)); px, out, d = 100.0, [], start
    while d <= date.today():
        if d.weekday() < 5:
            px *= 1 + rnd.uniform(-0.018, 0.019); out.append((d, round(px, 2)))
        d += timedelta(days=1)
    return out

# ----------------------------------------------------------------------
# CACHÉ EN DISCO  (clave para no quemar las 20 llamadas/día en desarrollo)
# ----------------------------------------------------------------------
def cached_eod(symbol, start, refresh):
    os.makedirs(CACHE_DIR, exist_ok=True)
    path = os.path.join(CACHE_DIR, f"{symbol}.json")
    today = date.today().isoformat()
    if not refresh and os.path.exists(path):
        try:
            blob = json.load(open(path, encoding="utf-8"))
            if blob.get("fetched") == today:   # ya descargado hoy -> 0 llamadas
                return [(date.fromisoformat(d), c) for d, c in blob["rows"]
                        if date.fromisoformat(d) >= start]
        except Exception:
            pass
    rows = fetch_eod(symbol, start)            # descarga real (suma 1 llamada)
    json.dump({"fetched": today, "rows": [[d.isoformat(), c] for d, c in rows]},
              open(path, "w", encoding="utf-8"))
    return rows

# ----------------------------------------------------------------------
# CÁLCULOS
# ----------------------------------------------------------------------
def unified_closes(hist, live_price):
    closes = list(hist)
    if live_price is not None:
        today = date.today()
        if closes and closes[-1][0] == today: closes[-1] = (today, live_price)
        else: closes.append((today, live_price))
    return closes

def weekly_return(closes):
    if len(closes) < 6: return None
    return round((closes[-1][1] / closes[-6][1] - 1) * 100, 1)

def asof_close(rows, target, didx):
    i = bisect.bisect_right(didx, target) - 1
    return rows[i][1] if i >= 0 else None

def build_curve(grid, series_map, hist):
    labels, series = [], []
    for label, tk in series_map:
        rows = hist.get(eod_sym(tk), [])
        if not rows: continue
        didx = [r[0] for r in rows]
        vals = [asof_close(rows, d, didx) for d in grid]
        base = next((v for v in vals if v), None)
        if not base: continue
        labels.append(label)
        series.append([round((v / base) * 100, 2) if v else 100.0 for v in vals])
    return {"labels": labels, "dates": [d.isoformat() for d in grid], "series": series}

def es_num(x, dec=2):
    s = f"{x:,.{dec}f}"
    return s.replace(",", "§").replace(".", ",").replace("§", ".")

def compute_stats(rows):
    if len(rows) < 2:
        return {"spx": "—", "spxChg": "—", "lo52": "—", "hi52": "—"}
    last, prev = rows[-1][1], rows[-2][1]; win = rows[-252:]; chg = (last / prev - 1) * 100
    return {"spx": es_num(last), "spxChg": ("+" if chg >= 0 else "") + es_num(chg, 1) + "%",
            "lo52": es_num(min(r[1] for r in win)), "hi52": es_num(max(r[1] for r in win))}

# ----------------------------------------------------------------------
# MAIN
# ----------------------------------------------------------------------
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dev", action="store_true", help="12 ETFs, sin live, con caché")
    ap.add_argument("--no-live", action="store_true")
    ap.add_argument("--demo", action="store_true")
    ap.add_argument("--refresh", action="store_true", help="ignora la caché")
    ap.add_argument("--out", default="data.json")
    args = ap.parse_args()

    universe_def = [u for u in UNIVERSE if u[0] in DEV_TICKERS] if args.dev else UNIVERSE
    use_live = (not args.demo) and (not args.no_live) and (not args.dev)
    start = date.today() - timedelta(days=420)

    def get_eod(sym):
        if args.demo: return fetch_eod_demo(sym, start)
        return cached_eod(sym, start, args.refresh)

    # 1) Histórico EOD
    hist = {}
    for tk, *_ in universe_def:
        s = eod_sym(tk)
        try:
            rows = get_eod(s)
            if rows: hist[s] = rows
            else: print(f"  · aviso: sin EOD para {s}", file=sys.stderr)
        except Exception as e:
            print(f"  · error EOD {s}: {e}", file=sys.stderr)

    # 2) Precios en vivo (solo plan de pago)
    live = {}
    if use_live:
        try: live = fetch_live(list(hist.keys()))
        except Exception as e: print(f"  · real-time no disponible ({e})", file=sys.stderr)

    # 3) Universo con variación semanal
    universe = []
    for tk, nm, cat, key in universe_def:
        s = eod_sym(tk); rows = hist.get(s)
        if not rows: continue
        w = weekly_return(unified_closes(rows, live.get(s)))
        if w is not None: universe.append([tk, nm, cat, w, key])

    # 4) Curvas base 100 (rejilla semanal YTD desde SPY)
    spy = hist.get("SPY.US", [])
    ytd = [r for r in spy if r[0] >= date(date.today().year, 1, 1)]
    grid = [ytd[i][0] for i in range(0, len(ytd), 5)]
    if ytd and (not grid or grid[-1] != ytd[-1][0]): grid.append(ytd[-1][0])
    assets = build_curve(grid, ASSETS_MAP, hist)
    themes = build_curve(grid, THEMES_MAP, hist)

    # 5) Stats del índice. En --dev / free usamos SPY×10 como aproximación del nivel
    #    (el % y el rango son casi idénticos; el índice real llega con plan de pago).
    spx_rows = []
    if not args.dev and not args.demo:
        for cand in SPX_CANDIDATES:
            try:
                r = cached_eod(cand, start, args.refresh)
                if r: spx_rows = r; break
            except Exception: pass
    if not spx_rows and spy:
        spx_rows = [(d, c * 10) for d, c in spy]   # proxy: SPY ≈ S&P500 / 10
    stats = compute_stats(spx_rows)

    as_of = (datetime.now().strftime("%Y-%m-%d %H:%M") if (use_live and live)
             else (spy[-1][0].isoformat() if spy else date.today().isoformat()))
    data = {"asOf": as_of, "live": True, "stats": stats,
            "universe": universe, "assets": assets, "themes": themes}
    json.dump(data, open(args.out, "w", encoding="utf-8"), ensure_ascii=False, indent=1)

    mode = "DEMO" if args.demo else ("DEV" if args.dev else
           ("EOD+LIVE" if (use_live and live) else "EOD"))
    print(f"OK -> {args.out}  ({len(universe)} ETFs · {as_of} · {mode})")
    print(f"   llamadas reales a EODHD esta ejecución: {STATE['calls']}"
          + ("  (free: 20/día)" if not args.demo else ""))

if __name__ == "__main__":
    main()
