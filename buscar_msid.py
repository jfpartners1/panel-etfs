#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
buscar_msid.py - HERRAMIENTA DE UN SOLO USO.

Lee los ISINs de la lista FUNDS de build_history_fondos.py y busca el SecId
de Morningstar (tipo F0GBR04UOL) de cada fondo usando el buscador publico
de morningstar.es. Vuelca el resultado en msid.json.

Ese mapa ISIN -> SecId se usara luego en fondos.html para construir la URL
de exportacion del X-Ray de Morningstar. Cero dependencias externas (stdlib).

Uso:  python3 buscar_msid.py            (lee build_history_fondos.py del directorio actual)
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

ENDPOINTS = [
    "https://www.morningstar.es/es/util/SecuritySearch.ashx",
    "https://www.morningstar.co.uk/uk/util/SecuritySearch.ashx",
]

HEADERS = {
    "User-Agent": ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                   "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36"),
    "Accept": "*/*",
    "Accept-Language": "es-ES,es;q=0.9",
}

# ISIN: 2 letras + 9 alfanumericos + 1 digito de control
RE_TUPLA = re.compile(r'\(\s*"([A-Z]{2}[A-Z0-9]{9}[0-9])"\s*,\s*"([^"]+)"')
RE_SECID = re.compile(r'"i"\s*:\s*"([^"]+)"')


def leer_isins(ruta):
    """Extrae (isin, nombre) de la lista FUNDS sin importar el modulo."""
    with open(ruta, encoding="utf-8") as f:
        texto = f.read()
    pares = RE_TUPLA.findall(texto)
    # dedup conservando orden
    vistos, out = set(), []
    for isin, nombre in pares:
        if isin not in vistos:
            vistos.add(isin)
            out.append((isin, nombre))
    return out


def consultar(isin):
    """Devuelve (secid, nombre_ms) o (None, None). Prueba varios endpoints con reintentos."""
    for base in ENDPOINTS:
        url = base + "?" + urllib.parse.urlencode({"q": isin, "limit": 5})
        for intento in range(3):
            try:
                req = urllib.request.Request(url, headers=HEADERS)
                with urllib.request.urlopen(req, timeout=20) as r:
                    cuerpo = r.read().decode("utf-8", errors="replace").strip()
                if not cuerpo:
                    break  # respuesta vacia: prueba el siguiente endpoint
                # Formato tipico: una linea por resultado ->  NOMBRE|{"i":"F0GBR04UOL",...}
                primera = cuerpo.splitlines()[0]
                m = RE_SECID.search(primera)
                if m:
                    nombre_ms = primera.split("|", 1)[0].strip()
                    return m.group(1), nombre_ms
                # Sin campo "i": intenta cualquier SecId reconocible en la respuesta
                m2 = re.search(r'\b(F[0-9A-Z]{9}|0P[0-9A-Z]{8})\b', cuerpo)
                if m2:
                    return m2.group(1), ""
                break  # respondio pero sin resultados: siguiente endpoint
            except Exception as e:
                espera = 2 * (intento + 1)
                print(f"    aviso {isin}: {e} (reintento en {espera}s)", flush=True)
                time.sleep(espera)
    return None, None


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
        secid, nombre_ms = consultar(isin)
        if secid:
            mapa[isin] = {"msid": secid, "nombre": nombre, "nombre_ms": nombre_ms}
            print(f"[{i}/{total}] OK  {isin} -> {secid}  ({nombre})", flush=True)
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
    # Salir con 0 aunque falten algunos: el JSON parcial ya es util
    return 0


if __name__ == "__main__":
    sys.exit(main())
