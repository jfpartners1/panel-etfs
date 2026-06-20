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

import argparse, bisect, csv, json, os, random, statistics, sys, time, urllib.parse, urllib.request
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
              ("Emergentes","EEM"),("Japón","EWJ"),("China","FXI"),("Bonos 20Y","TLT"),
              ("Crédito IG","LQD"),("High Yield","HYG"),("Oro","GLD"),("Plata","SLV"),
              ("Materias primas","DBC"),("Petróleo","USO"),("Inmobiliario","VNQ"),("Bitcoin","IBIT")]
THEMES_MAP = [("Semis","SMH"),("IA / Robótica","BOTZ"),("Tecnología","XLK"),("Cloud","SKYY"),
              ("Ciberseguridad","CIBR"),("Fintech","FINX"),("Blockchain","BLOK"),("Innovación","ARKK"),
              ("Biotech","XBI"),("Salud","XLV"),("Energía","XLE"),("Energía limpia","ICLN"),
              ("Solar","TAN"),("Uranio","URA"),("Mineras oro","GDX"),("Defensa","ITA")]
SPX_CANDIDATES = ["GSPC.INDX", "SPX.INDX"]   # índice S&P 500 en EODHD (plan de pago)

# Factor map 3x3: estilo (Value/Core/Growth) x tamaño (Large/Mid/Small). ETFs iShares Russell.
FACTORS = [("IWD","L","V"),("IWB","L","C"),("IWF","L","G"),
           ("IWS","M","V"),("IWR","M","C"),("IWP","M","G"),
           ("IWN","S","V"),("IWM","S","C"),("IWO","S","G")]
FACTOR_NM = {"L":"Grande","M":"Media","S":"Pequeña","V":"Value","C":"Core","G":"Growth"}

def eod_sym(tk): return tk + ".US"

# ----------------------------------------------------------------------
# FUENTE: EODHD  (cambia SOLO estas funciones para usar otra fuente)
# ----------------------------------------------------------------------
def _get(url):
    req = urllib.request.Request(url, headers={"User-Agent": "market-panel/1.0"})
    with urllib.request.urlopen(req, timeout=40) as r:
        return json.loads(r.read().decode("utf-8", "replace"))

def fetch_eod(symbol, start):
    """[(date, close_ajustado, volumen)] ascendente. Endpoint /api/eod. Cuenta 1 llamada."""
    STATE["calls"] += 1
    url = f"{API}/eod/{symbol}?api_token={KEY}&fmt=json&period=d&from={start.isoformat()}"
    out = []
    for r in _get(url):
        try:
            d = datetime.strptime(r["date"], "%Y-%m-%d").date()
            c = float(r.get("adjusted_close") or r.get("close"))
            v = float(r.get("volume") or 0)
        except (KeyError, ValueError, TypeError):
            continue
        out.append((d, c, v))
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
            px *= 1 + rnd.uniform(-0.018, 0.019)
            out.append((d, round(px, 2), rnd.randint(400000, 6000000)))
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
                return [(date.fromisoformat(d), c, v) for d, c, v in blob["rows"]
                        if date.fromisoformat(d) >= start]
        except Exception:
            pass
    rows = fetch_eod(symbol, start)            # descarga real (suma 1 llamada)
    json.dump({"fetched": today, "rows": [[d.isoformat(), c, v] for d, c, v in rows]},
              open(path, "w", encoding="utf-8"))
    return rows

# ----------------------------------------------------------------------
# CÁLCULOS
# ----------------------------------------------------------------------
def unified_closes(hist, live_price):
    """Mezcla el histórico EOD con el precio en vivo SOLO si es un precio intradía real.
    Si el mercado está cerrado, EODHD en tiempo real devuelve el último cierre: en ese caso
    no se añade nada, para que el cambio diario sea el de la última sesión y no 0%."""
    closes = list(hist)
    if live_price is not None and closes:
        today = date.today()
        last_d, last_c = closes[-1]
        if last_d >= today:
            closes[-1] = (today, live_price)                 # hoy ya en EOD -> refresca con el vivo
        elif abs(live_price - last_c) > last_c * 1e-5:
            closes.append((today, live_price))               # precio intradía nuevo -> añade hoy
        # si el vivo == último cierre (mercado cerrado), no se añade: cambio diario = última sesión
    return closes

def returns(closes, rows):
    """Retornos D/S/M/YTD en % desde los cierres (precio en vivo ya incluido)."""
    def chg(n):
        return round((closes[-1][1] / closes[-1-n][1] - 1) * 100, 1) if len(closes) > n else None
    out = {"d": chg(1), "w": chg(5), "m": chg(21)}
    jan1 = date(date.today().year, 1, 1)
    didx = [r[0] for r in rows]
    i = bisect.bisect_left(didx, jan1) - 1
    base = rows[i][1] if i >= 0 else (rows[0][1] if rows else None)
    out["ytd"] = round((closes[-1][1] / base - 1) * 100, 1) if base else None
    return out

def asof_close(rows, target, didx):
    i = bisect.bisect_right(didx, target) - 1
    return rows[i][1] if i >= 0 else None

def build_curve(grid, series_map, hist):
    """Series de cierre BRUTO (sin rebasar) alineadas a `grid`. El navegador recorta
    el periodo y rebasa a 100 -> un solo download sirve para 1M / 3M / YTD / 1A."""
    labels, series = [], []
    for label, tk in series_map:
        rows = hist.get(eod_sym(tk), [])
        if not rows: continue
        didx = [r[0] for r in rows]
        vals = [asof_close(rows, d, didx) for d in grid]
        vals = [round(v, 4) if v else None for v in vals]
        if all(v is None for v in vals): continue
        labels.append(label); series.append(vals)
    return {"labels": labels, "dates": [d.isoformat() for d in grid], "series": series}

def _ret(cl, n):
    return (cl[-1] / cl[-1-n] - 1) * 100 if len(cl) > n else None

def rs_block(universe_def, hist, full_dates):
    """Fuerza relativa: cierres SEMANALES (un punto por semana) de todos los ETFs sobre
    ~5 años, para calcular ratios A/B en el navegador. Semanal = ligero (~260 puntos) y
    suficiente para tendencias de medio/largo plazo. Cero llamadas extra: reutiliza `hist`.
    `full_dates` es la lista completa de fechas (diaria) del histórico descargado."""
    # un punto por semana ISO: nos quedamos con el ÚLTIMO día de cada semana
    wk_last = {}
    for d in full_dates:
        iso = d.isocalendar()
        wk_last[(iso[0], iso[1])] = d
    wdates = sorted(wk_last.values())
    px = {}
    for tk, *_ in universe_def:
        rows = hist.get(eod_sym(tk), [])
        if not rows: continue
        didx = [r[0] for r in rows]
        vals = [asof_close(rows, d, didx) for d in wdates]
        vals = [round(v, 4) if v else None for v in vals]
        if all(v is None for v in vals): continue
        px[tk] = vals
    return {"dates": [d.isoformat() for d in wdates], "px": px, "freq": "w"}

def momentum_block(universe_def, hist, live, volh):
    """Momentum Composite (0-100): tendencia multi-plazo, aceleración, proximidad a
    máximos de 52s y baja volatilidad. Pesos 45/15/25/15. Percentiles dentro del universo.
    Añade retornos 1M/3M/6M/12M, distancia a máximos y volumen relativo (hoy vs media 20s)."""
    data = []
    for tk, nm, cat, key in universe_def:
        cl = [c for _, c in unified_closes(hist.get(eod_sym(tk), []), live.get(eod_sym(tk)))]
        if len(cl) < 253: continue                    # necesita ~1 año de histórico
        r21, r63, r126, r252 = _ret(cl,21), _ret(cl,63), _ret(cl,126), _ret(cl,252)
        if None in (r21, r63, r126, r252): continue
        trend = 0.10*r21 + 0.25*r63 + 0.30*r126 + 0.35*r252   # multi-plazo, peso al largo
        accel = r63 - r252/4                                  # trimestre reciente vs ritmo anual
        hi = max(cl[-252:]); dist = (cl[-1]/hi - 1) * 100     # distancia a máximo 52s (<=0)
        dr = [cl[i]/cl[i-1]-1 for i in range(len(cl)-63, len(cl))]
        vol = statistics.pstdev(dr) * (252**0.5) * 100 if len(dr) > 1 else 0
        vv = [v for _, v in volh.get(eod_sym(tk), [])]        # volumen relativo
        rvol = round(vv[-1] / (sum(vv[-21:-1])/20), 2) if len(vv) >= 21 and sum(vv[-21:-1]) > 0 else None
        data.append({"tk":tk,"nm":nm,"cat":cat,"trend":trend,"accel":accel,"dist":dist,"vol":vol,
                     "r1":r21,"r3":r63,"r6":r126,"r12":r252,"rvol":rvol})
    if not data: return []
    def pct(vals, v): return round(sum(1 for x in vals if x <= v) / len(vals) * 100)
    T=[d["trend"] for d in data]; A=[d["accel"] for d in data]
    H=[d["dist"] for d in data];  V=[d["vol"] for d in data]
    out = []
    for d in data:
        st, sa = pct(T, d["trend"]), pct(A, d["accel"])
        sh, sv = pct(H, d["dist"]), 100 - pct(V, d["vol"])    # vol: menos es mejor
        score = round(0.45*st + 0.15*sa + 0.25*sh + 0.15*sv)
        out.append([d["tk"], d["nm"], d["cat"], score, st, sa, sh, sv,
                    round(d["r1"],1), round(d["r3"],1), round(d["r6"],1), round(d["r12"],1),
                    round(d["dist"],1), d["rvol"]])
    out.sort(key=lambda r: -r[3])
    return out

def momentum_evolution(universe_def, hist, live, top, weeks=26, step=5):
    """Evolución semanal del Z-score de fuerza (momentum multi-plazo) frente al universo.
    Z = (tendencia del ETF − media del universo) / desviación típica, en cada fecha."""
    spy = hist.get("SPY.US", [])
    if len(spy) < weeks*step: return {}
    sdates = [spy[i][0] for i in range(len(spy)-1, -1, -step)][:weeks][::-1]
    rowsmap = {}
    for tk, *_ in universe_def:
        r = hist.get(eod_sym(tk))
        if r: rowsmap[tk] = (r, [x[0] for x in r])
    def trend_at(tk, ds):
        r, didx = rowsmap.get(tk, (None, None))
        if not r: return None
        base = asof_close(r, ds, didx)
        if base is None: return None
        def R(days):
            p = asof_close(r, ds - timedelta(days=days), didx)
            return (base/p - 1) * 100 if p else None
        a, b, c, e = R(30), R(91), R(182), R(365)
        if None in (a, b, c, e): return None
        return 0.10*a + 0.25*b + 0.30*c + 0.35*e
    Z = {tk: [] for tk in top}
    for ds in sdates:
        vals = {tk: trend_at(tk, ds) for tk in rowsmap}
        arr = [v for v in vals.values() if v is not None]
        if len(arr) < 5:
            for tk in top: Z[tk].append(None)
            continue
        mu = statistics.fmean(arr); sd = statistics.pstdev(arr) or 1
        for tk in top:
            v = vals.get(tk)
            Z[tk].append(round((v-mu)/sd, 2) if v is not None else None)
    return {"dates": [d.isoformat() for d in sdates], "labels": top, "series": [Z[tk] for tk in top]}

def _rvol(vv):
    return round(vv[-1] / (sum(vv[-21:-1])/20), 2) if len(vv) >= 21 and sum(vv[-21:-1]) > 0 else None

def breakout_block(universe_def, hist, live, volh, near=-3.0):
    """Rupturas y proximidad a máximos de 52s. Estado SOLO de precio:
    max = nuevo máximo de 52s (dist>=-0,1%) · near = a punto (entre -0,1% y -3%).
    El volumen (RVol) va aparte y lo interpreta el frontend (alto/normal/bajo)."""
    out = []
    for tk, nm, cat, key in universe_def:
        s = eod_sym(tk)
        cl = [c for _, c in unified_closes(hist.get(s, []), live.get(s))]
        if len(cl) < 40: continue
        hi = max(cl[-252:]) if len(cl) >= 252 else max(cl)
        dist = (cl[-1]/hi - 1) * 100
        if dist < near: continue
        rvol = _rvol([v for _, v in volh.get(s, [])])
        r1m = _ret(cl, 21)
        estado = "max" if dist >= -0.1 else "near"
        out.append([tk, nm, cat, round(dist, 1), rvol,
                    round(r1m, 1) if r1m is not None else None, estado])
    # nuevos máximos primero; dentro, los de más volumen arriba (rupturas con fuerza); luego "a punto" por cercanía
    grp = {"max": 0, "near": 1}
    out.sort(key=lambda r: (grp[r[6]], -(r[4] or 0) if r[6] == "max" else -r[3]))
    return out

def squeeze_block(universe_def, hist, live, volh):
    """Bases apretadas pegadas a máximos: precio entre -5% y -0,5% del máximo de 52s, POR ENCIMA
    de la media de 50 (tendencia de fondo) y con la amplitud de precio de las últimas ~2 semanas
    más estrecha que la de las 2 anteriores. 'aprieto' = amplitud reciente / previa (bajo = más comprimida)."""
    out = []
    for tk, nm, cat, key in universe_def:
        s = eod_sym(tk)
        cl = [c for _, c in unified_closes(hist.get(s, []), live.get(s))]
        if len(cl) < 60: continue
        hi = max(cl[-252:]) if len(cl) >= 252 else max(cl)
        dist = (cl[-1]/hi - 1) * 100
        if not (-5.0 <= dist <= -0.5): continue            # pegado a máximos, en zona de base
        if cl[-1] < sum(cl[-50:]) / 50: continue           # tendencia de fondo alcista
        rec, prev = cl[-10:], cl[-20:-10]
        amp_rec = (max(rec) - min(rec)) / cl[-1]
        amp_prev = (max(prev) - min(prev)) / cl[-1]
        if amp_prev <= 0: continue
        rvol = _rvol([v for _, v in volh.get(s, [])])
        out.append([tk, nm, cat, round(dist, 1), round(amp_rec/amp_prev, 2), rvol])
    out.sort(key=lambda r: r[4])      # más apretado arriba
    return out[:18]

def fetch_news(symbol, limit=6):
    """Últimas noticias de un símbolo vía /api/news (incluye sentimiento). ~5 llamadas."""
    STATE["calls"] += 5
    url = f"{API}/news?api_token={KEY}&fmt=json&s={symbol}&limit={limit}&offset=0"
    try:
        data = _get(url)
    except Exception:
        return []
    return data if isinstance(data, list) else []

def _news_item(a, label, cat):
    title = (a.get("title") or "").strip()
    if not title: return None
    sent = a.get("sentiment") or {}
    pol = sent.get("polarity")
    s = "neu"
    if isinstance(pol, (int, float)):
        s = "pos" if pol > 0.12 else ("neg" if pol < -0.12 else "neu")
    link = a.get("link") or ""
    src = ""
    try:
        src = urllib.parse.urlparse(link).netloc.replace("www.", "")
    except Exception:
        pass
    return [title[:180], link, src, a.get("date") or "", label, cat, s]

def news_block(total=4, per_symbol=8):
    """Solo titulares de mercado general (SPY/QQQ), los más recientes. Nivel 1: titular + sentimiento."""
    uniq = {}
    for tk in ("SPY", "QQQ"):
        for a in fetch_news(eod_sym(tk), per_symbol):
            it = _news_item(a, "Mercado", "IDX")
            if it and it[0] not in uniq:
                uniq[it[0]] = it
    return sorted(uniq.values(), key=lambda x: x[3], reverse=True)[:total]

def factor_block(hist, live):
    """Rejilla de factores estilo x tamaño con retornos D/S/M/YTD por celda."""
    out = []
    for tk, row, col in FACTORS:
        rows = hist.get(eod_sym(tk))
        if not rows: continue
        rets = returns(unified_closes(rows, live.get(eod_sym(tk))), rows)
        out.append([tk, row, col, rets])
    return out

def breadth_block(universe_def, hist, live):
    """Amplitud del mercado: % sobre media 50/200, nuevos máx/mín, % en positivo, con la lista de ETFs de cada grupo."""
    n = d200 = 0
    L = {"ma50": [], "ma200": [], "hi": [], "lo": [], "up": [], "down": []}
    for tk, nm, cat, key in universe_def:
        rows = hist.get(eod_sym(tk))
        if not rows: continue
        cl = [c for _, c in unified_closes(rows, live.get(eod_sym(tk)))]
        if len(cl) < 2: continue
        n += 1
        if len(cl) >= 50 and cl[-1] > sum(cl[-50:])/50: L["ma50"].append(tk)
        if len(cl) >= 200:
            d200 += 1
            if cl[-1] > sum(cl[-200:])/200: L["ma200"].append(tk)
        win = cl[-252:] if len(cl) >= 252 else cl
        if cl[-1] >= max(win): L["hi"].append(tk)
        if cl[-1] <= min(win): L["lo"].append(tk)
        if cl[-1]/cl[-2] - 1 >= 0: L["up"].append(tk)
        else: L["down"].append(tk)
    pct = lambda a, b: round(a/b*100) if b else None
    return {"n": n, "ma50": pct(len(L["ma50"]), n), "ma200": pct(len(L["ma200"]), d200),
            "hi": len(L["hi"]), "lo": len(L["lo"]), "up": len(L["up"]), "down": len(L["down"]),
            "upPct": pct(len(L["up"]), n), "lists": L}

def load_ucits():
    """Lee ucits.csv (equivalencias ETF USA → UCITS europeo). Estático, no gasta API."""
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "ucits.csv")
    out = {}
    try:
        with open(path, encoding="utf-8") as f:
            for r in csv.DictReader(f, delimiter=";"):
                tk = (r.get("ticker_usa") or "").strip()
                if not tk: continue
                out[tk] = {"nombre": (r.get("nombre") or "").strip(),
                           "isin": (r.get("isin") or "").strip(),
                           "tickerEur": (r.get("ticker_eur") or "").strip(),
                           "ter": (r.get("ter") or "").strip(),
                           "accDis": (r.get("acc_dis") or "").strip(),
                           "nota": (r.get("nota") or "").strip()}
    except FileNotFoundError:
        print("  · aviso: ucits.csv no encontrado", file=sys.stderr)
    return out

def radar_block(universe_def, hist, live):
    """Radar de fuerza para decisión rápida:
    - strong/weak: fuerza relativa pura (retorno multiplazo ponderado, percentil del universo).
    - gaining: señales de mejora -> 'máximos' (rompe/pegado a máx 52s), 'media 50' (recupera MA50), 'acelera' (momentum reciente > trimestral).
    - losing: señales de deterioro -> 'pierde 50' (cae bajo MA50), 'frena' (momentum reciente flojea), 'lejos de máx' (a >12% o en mínimos)."""
    data = []
    for tk, nm, cat, key in universe_def:
        cl = [c for _, c in unified_closes(hist.get(eod_sym(tk), []), live.get(eod_sym(tk)))]
        if len(cl) < 60: continue
        r21, r63, r126 = _ret(cl, 21), _ret(cl, 63), _ret(cl, 126)
        r252 = _ret(cl, 252) if len(cl) >= 253 else None
        wr = [(w, v) for w, v in ((0.10, r21), (0.25, r63), (0.30, r126), (0.35, r252)) if v is not None]
        if not wr: continue
        trend = sum(w*v for w, v in wr) / sum(w for w, _ in wr)   # fuerza relativa multiplazo
        hi = max(cl[-252:]) if len(cl) >= 252 else max(cl)
        lo = min(cl[-252:]) if len(cl) >= 252 else min(cl)
        dist = (cl[-1]/hi - 1) * 100
        ma50 = sum(cl[-50:]) / 50
        ma50_prev = sum(cl[-60:-10]) / 50 if len(cl) >= 60 else ma50
        price_then = cl[-11] if len(cl) >= 11 else cl[0]
        gain, lose = [], []
        if dist >= -0.5: gain.append("máximos")                       # rompiendo / pegado a máximos
        if cl[-1] > ma50 and price_then <= ma50_prev: gain.append("media 50")   # recupera la MA50
        if r21 is not None and r63 is not None and r21 > r63/3 and r21 > 0: gain.append("acelera")
        if cl[-1] < ma50 and price_then >= ma50_prev: lose.append("pierde 50")  # cae bajo la MA50
        if r21 is not None and r63 is not None and r21 < r63/3: lose.append("frena")
        if dist <= -12 or cl[-1] <= lo*1.005: lose.append("lejos de máx")
        data.append({"tk": tk, "nm": nm, "cat": cat, "trend": trend, "gain": gain, "lose": lose})
    if not data: return {}
    T = sorted(d["trend"] for d in data)
    for d in data:
        d["rs"] = round(bisect.bisect_right(T, d["trend"]) / len(T) * 100)
    by_rs = sorted(data, key=lambda d: -d["rs"])
    strong = [[d["tk"], d["nm"], d["cat"], d["rs"]] for d in by_rs[:5]]
    weak = [[d["tk"], d["nm"], d["cat"], d["rs"]] for d in by_rs[-5:][::-1]]
    gains = sorted((d for d in data if d["gain"]), key=lambda d: (-len(d["gain"]), -d["rs"]))
    loses = sorted((d for d in data if d["lose"]), key=lambda d: (-len(d["lose"]), d["rs"]))
    gaining = [[d["tk"], d["nm"], d["cat"], d["gain"]] for d in gains[:5]]
    losing = [[d["tk"], d["nm"], d["cat"], d["lose"]] for d in loses[:5]]
    return {"strong": strong, "weak": weak, "gaining": gaining, "losing": losing}

def market_pulse(hist, volh, window=25):
    """Pulso de mercado estilo IBD. Día de distribución = índice cae >=0,2% con volumen
    mayor que el anterior; acumulación = sube >=0,2% con más volumen. Ventana 25 sesiones.
    Semáforo por el PEOR de SPY/QQQ: <4 verde · 4-7 amarillo · >7 rojo."""
    res = {}
    for key, sym in (("spx", "SPY"), ("ndx", "QQQ")):
        s = eod_sym(sym)
        cl = [c for _, c in hist.get(s, [])]
        vl = [v for _, v in volh.get(s, [])]
        if len(cl) < window + 1 or len(vl) < len(cl):
            res[key] = None; continue
        dist = acc = 0
        for i in range(len(cl) - window, len(cl)):
            if i < 1: continue
            ch = cl[i] / cl[i-1] - 1
            if vl[i] > vl[i-1]:
                if ch <= -0.002: dist += 1
                elif ch >= 0.002: acc += 1
        ma = sum(cl[-50:]) / min(len(cl), 50)
        res[key] = {"dist": dist, "acc": acc, "above50": cl[-1] >= ma}
    dvals = [res[k]["dist"] for k in ("spx", "ndx") if res.get(k)]
    worst = max(dvals) if dvals else None
    res["worst"] = worst
    res["light"] = ("green" if worst < 4 else "yellow" if worst <= 7 else "red") if worst is not None else "na"
    return res

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
    # 5 años de histórico: EODHD devuelve todo en la MISMA llamada (cero coste extra).
    # El panel (momentum, curvas…) usa solo el tramo final que necesita; el plazo largo
    # sirve al bloque de fuerza relativa (muestreado semanal).
    start = date.today() - timedelta(days=365*5 + 90)

    def get_eod(sym):
        if args.demo: return fetch_eod_demo(sym, start)
        return cached_eod(sym, start, args.refresh)

    # 1) Histórico EOD (cierres + volúmenes)
    hist, volh = {}, {}
    for tk, *_ in universe_def:
        s = eod_sym(tk)
        try:
            raw = get_eod(s)
            if raw:
                hist[s] = [(d, c) for d, c, _ in raw]
                volh[s] = [(d, v) for d, _, v in raw]
            else: print(f"  · aviso: sin EOD para {s}", file=sys.stderr)
        except Exception as e:
            print(f"  · error EOD {s}: {e}", file=sys.stderr)

    # 1b) ETFs de factores (estilo x tamaño) para el factor map
    for tk, _, _ in FACTORS:
        s = eod_sym(tk)
        if s in hist: continue
        try:
            raw = get_eod(s)
            if raw:
                hist[s] = [(d, c) for d, c, _ in raw]
                volh[s] = [(d, v) for d, _, v in raw]
        except Exception as e:
            print(f"  · error EOD factor {s}: {e}", file=sys.stderr)

    # 2) Precios en vivo (solo plan de pago)
    live = {}
    if use_live:
        try: live = fetch_live(list(hist.keys()))
        except Exception as e: print(f"  · real-time no disponible ({e})", file=sys.stderr)

    # 3) Universo con retornos D/S/M/YTD + volumen relativo por ETF
    universe = []
    for tk, nm, cat, key in universe_def:
        s = eod_sym(tk); rows = hist.get(s)
        if not rows: continue
        rets = returns(unified_closes(rows, live.get(s)), rows)
        if rets["w"] is None and rets["d"] is None: continue
        vv = [v for _, v in volh.get(s, [])]
        rvol = round(vv[-1] / (sum(vv[-21:-1])/20), 2) if len(vv) >= 21 and sum(vv[-21:-1]) > 0 else None
        universe.append([tk, nm, cat, rets, key, rvol])

    # 4) Curvas: rejilla DIARIA (último ~año) desde SPY. Cierre bruto + fechas; el
    #    navegador elige 1M/3M/YTD/1A y rebasa. Una descarga, muchas vistas.
    spy = hist.get("SPY.US", [])
    grid = [d for d, _ in spy][-260:]
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
    mom = momentum_block(universe_def, hist, live, volh)
    momz = momentum_evolution(universe_def, hist, live, [r[0] for r in mom[:12]])
    bo = breakout_block(universe_def, hist, live, volh)
    sq = squeeze_block(universe_def, hist, live, volh)
    data = {"asOf": as_of, "live": True, "stats": stats, "universe": universe,
            "assets": assets, "themes": themes, "momentum": mom, "momentumZ": momz,
            "pulse": market_pulse(hist, volh),
            "breakouts": bo, "squeeze": sq,
            "factors": factor_block(hist, live), "breadth": breadth_block(universe_def, hist, live),
            "radar": radar_block(universe_def, hist, live),
            "rs": rs_block(universe_def, hist, [d for d, _ in spy]),
            "ucits": load_ucits()}
    json.dump(data, open(args.out, "w", encoding="utf-8"), ensure_ascii=False, indent=1)

    mode = "DEMO" if args.demo else ("DEV" if args.dev else
           ("EOD+LIVE" if (use_live and live) else "EOD"))
    print(f"OK -> {args.out}  ({len(universe)} ETFs · {as_of} · {mode})")
    print(f"   llamadas reales a EODHD esta ejecución: {STATE['calls']}"
          + ("  (free: 20/día)" if not args.demo else ""))

if __name__ == "__main__":
    main()
