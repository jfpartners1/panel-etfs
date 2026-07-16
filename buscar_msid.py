#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
buscar_msid.py (v2) - HERRAMIENTA DE UN SOLO USO.

Lee los ISINs de la lista FUNDS de build_history_fondos.py y busca el SecId
de Morningstar (tipo F0GBR04UOL) de cada fondo. Vuelca el mapa en msid.json.

v2: usa el screener JSON de lt.morningstar.com (la misma infraestructura que
la URL del X-Ray, universo FOESP$$ALL) como via principal, con fallbacks y
diagnostico de respuestas crudas en el log.

Uso:  python3 buscar_msid.py            (todos los fondos)
      python3 buscar_msid.py --limit 5  (solo los 5 primeros, para probar)
"""
import argparse
import json
import re
import sys
import time
import urllib.parse
import urllib.request
from datetime import date

FUENTE = "build_history_fondos.py"
SALIDA = "msid.json"

HEADERS = {
    "User-Agent": ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                   "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36"),
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "es-ES,es;q=0.9",
    "Referer": "https://www.morningstar.es/",
}

# ISIN: 2 letras + 9 alfanumericos + 1 digito de control
RE_TUPLA = re.compile(r'\(\s*"([A-Z]{2}[A-Z0-9]{9}[0-9])"\s*,\s*"([^"]+)"')

SCREENER = "https://lt.morningstar.com/api/rest.svc/klr5zyak8x/security/screener"
# Universos a probar, en orden: fondos vendidos en Espana, y sin filtro
UNIVERSOS = ["FOESP$$ALL", ""]

_diagnosticos = 0  # cuantas respuestas crudas hemos volcado ya al log


def leer_isins(ruta):
    """Extrae (isin, nombre) de la lista FUNDS sin importar el modulo."""
    with open(ruta, encoding="utf-8") as f:
        texto = f.read()
    pares = RE_TUPLA.findall(texto)
    vistos, out = set(), []
    for isin, nombre in pares:
        if isin not in vistos:
            vistos.add(isin)
            out.append((isin, nombre))
    return out


def _get(url):
    req = urllib.request.Request(url, headers=HEADERS)
    with urllib.request.urlopen(req, timeout=20) as r:
        return r.read().decode("utf-8", errors="replace")


def _diagnostico(etiqueta, isin, cuerpo):
    """Vuelca al log un trozo de respuesta cruda (solo las 3 primeras veces)."""
    global _diagnosticos
    if _diagnosticos < 3:
        _diagnosticos += 1
        recorte = cuerpo[:400].replace("\n", " ")
        print(f"    [diag {etiqueta}] {isin}: {recorte!r}", flush=True)


def via_screener(isin):
    """Screener JSON de lt.morningstar.com. Devuelve (secid, nombre_ms) o (None, None)."""
    for uni in UNIVERSOS:
        params = {
            "page": "1",
            "pageSize": "10",
            "sortOrder": "LegalName asc",
            "outputType": "json",
            "version": "1",
            "languageId": "es-ES",
            "currencyId": "EUR",
            "securityDataPoints": "SecId|Name|LegalName|isin",
            "term": isin,
        }
        if uni:
            params["universeIds"] = uni
        url = SCREENER + "?" + urllib.parse.urlencode(params)
        for intento in range(3):
            try:
                cuerpo = _get(url)
                datos = json.loads(cuerpo)
                filas = datos.get("rows") or []
                if not filas:
                    _diagnostico(f"screener uni={uni or 'todos'}", isin, cuerpo)
                    break  # prueba el siguiente universo
                # Preferir la fila cuyo isin coincida exactamente
                fila = next((f_ for f_ in filas
                             if str(f_.get("isin", "")).upper() == isin), filas[0])
                secid = fila.get("SecId")
                nombre_ms = fila.get("Name") or fila.get("LegalName") or ""
                if secid:
                    return secid, nombre_ms
                break
            except json.JSONDecodeError:
                _diagnostico("screener no-json", isin, cuerpo)
                break
            except Exception as e:
                espera = 2 * (intento + 1)
                print(f"    aviso screener {isin}: {e} (reintento en {espera}s)", flush=True)
                time.sleep(espera)
    return None, None


def via_ashx(isin):
    """Fallback: buscador clasico SecuritySearch.ashx con parametros completos."""
    for base in ("https://www.morningstar.es/es/util/SecuritySearch.ashx",
                 "https://www.morningstar.co.uk/uk/util/SecuritySearch.ashx"):
        params = {"q": isin, "limit": "10", "preferedList": "",
                  "source": "nav", "moduleId": "6", "ifIncludeAds": "False",
                  "usrtType": "v"}
        url = base + "?" + urllib.parse.urlencode(params)
        try:
            cuerpo = _get(url).strip()
            if not cuerpo:
                continue
            m = re.search(r'"i"\s*:\s*"([^"]+)"', cuerpo)
            if m:
                nombre_ms = cuerpo.splitlines()[0].split("|", 1)[0].strip()
                return m.group(1), nombre_ms
            m2 = re.search(r'\b(F[0-9A-Z]{9}|0P[0-9A-Z]{8})\b', cuerpo)
            if m2:
                return m2.group(1), ""
            _diagnostico("ashx", isin, cuerpo)
        except Exception as e:
            print(f"    aviso ashx {isin}: {e}", flush=True)
    return None, None


def consultar(isin):
    secid, nombre = via_screener(isin)
    if secid:
        return secid, nombre, "screener"
    secid, nombre = via_ashx(isin)
    if secid:
        return secid, nombre, "ashx"
    return None, None, ""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=0, help="procesar solo los N primeros (prueba)")
    args = ap.parse_args()

    fondos = leer_isins(FUENTE)
    if args.limit:
        fondos = fondos[: args.limit]
    total = len(fondos)
    print(f"Fondos a buscar: {total}", flush=True)

    mapa, faltan = {}, []
    for i, (isin, nombre) in enumerate(fondos, 1):
        secid, nombre_ms, via = consultar(isin)
        if secid:
            mapa[isin] = {"msid": secid, "nombre": nombre, "nombre_ms": nombre_ms}
            print(f"[{i}/{total}] OK  {isin} -> {secid}  ({nombre}) [{via}]", flush=True)
        else:
            faltan.append({"isin": isin, "nombre": nombre})
            print(f"[{i}/{total}] --  {isin} SIN RESULTADO  ({nombre})", flush=True)
        time.sleep(0.7)  # ser educados con Morningstar

    salida = {
        "asOf": date.today().isoformat(),
        "encontrados": len(mapa),
        "total": total,
        "faltan": faltan,
        "map": mapa,
    }
    with open(SALIDA, "w", encoding="utf-8") as f:
        json.dump(salida, f, ensure_ascii=False, indent=1)

    print("-" * 50, flush=True)
    print(f"RESUMEN: {len(mapa)}/{total} encontrados -> {SALIDA}", flush=True)
    if faltan:
        print("Sin resultado (habra que buscarlos a mano):", flush=True)
        for f_ in faltan:
            print(f"  - {f_['isin']}  {f_['nombre']}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
