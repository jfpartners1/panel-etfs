#!/usr/bin/env python3
"""
probar_fondos.py — Diagnóstico: comprueba qué fondos UCITS (por ISIN) tienen datos
en EODHD a través del exchange virtual EUFUND ({ISIN}.EUFUND).

Para cada fondo dice si tiene histórico, cuántos puntos y desde/hasta qué fecha.
Si no está en EUFUND, busca con el Search API por si existe con otro código.

Se ejecuta como workflow temporal (probar-fondos.yml) usando el secreto EODHD_API_KEY.
El resultado sale en el log de Actions. Cuesta ~17 llamadas (1 por fondo). No hace commit.
"""
import os, sys, json, urllib.request

KEY = os.environ.get("EODHD_API_KEY")
if not KEY:
    print("ERROR: falta el secreto EODHD_API_KEY"); sys.exit(1)
API = "https://eodhd.com/api"

FUNDS = [
    ("ES0165242001", "Myinvestor S&P500 Equiponderado FI"),
    ("IE0032620787", "Vanguard U.S. 500 Stock Index Investor EUR Acc"),
    ("IE00BYX5MX67", "Fidelity S&P 500 Index Fund EUR P Acc"),
    ("ES0184894006", "Myinvestor ACWI FI"),
    ("IE00BYX5NX33", "Fidelity MSCI World Index Fund EUR P Acc"),
    ("IE00B03HCZ61", "Vanguard Global Stock Index Investor EUR Acc"),
    ("IE00B42W3S00", "Vanguard Global Small-Cap Index Investor EUR Acc"),
    ("IE0007281425", "Vanguard Japan Stock Index Investor EUR Acc"),
    ("IE0007201266", "Vanguard Pacific ex-Japan Stock Index EUR Acc"),
    ("IE0031786142", "Vanguard Emerging Markets Stock Index Investor EUR Acc"),
    ("IE0007987690", "Vanguard European Stock Index Investor EUR Acc"),
    ("ES0114105036", "Bankinter EE.UU. Nasdaq 100 R FI"),
    ("IE00BYX5MD61", "Fidelity MSCI Europe Index Fund EUR P Acc"),
    ("LU0625737910", "Pictet-China Index P EUR"),
    ("ES0152741031", "ING Direct Fondo Naranja Ibex 35 FI"),
    ("LU0996181599", "Amundi IS MSCI World IE-C"),
]


def fetch(url):
    with urllib.request.urlopen(url, timeout=30) as r:
        return r.read().decode()


def eod(sym, frm="2008-01-01"):
    url = f"{API}/eod/{sym}?api_token={KEY}&fmt=json&from={frm}"
    try:
        data = json.loads(fetch(url))
        if isinstance(data, list) and data:
            return data
    except Exception:
        pass
    return None


def search(isin):
    try:
        return json.loads(fetch(f"{API}/search/{isin}?api_token={KEY}&fmt=json")) or []
    except Exception:
        return []


def main():
    print("=" * 78)
    print("  DIAGNÓSTICO DE FONDOS UCITS EN EODHD (exchange virtual EUFUND)")
    print("=" * 78)
    ok, ko = [], []
    for isin, name in FUNDS:
        rows = eod(f"{isin}.EUFUND")
        if rows:
            d0, d1 = rows[0].get("date"), rows[-1].get("date")
            print(f"OK  {isin}  {name[:44]:<44} {len(rows):>5} pts · {d0} -> {d1}")
            ok.append((isin, name))
        else:
            res = search(isin)
            if res:
                alt = ", ".join(f"{r.get('Code')}.{r.get('Exchange')}" for r in res[:3])
                print(f"--  {isin}  {name[:44]:<44} no en EUFUND · search: {alt}")
            else:
                print(f"XX  {isin}  {name[:44]:<44} no encontrado")
            ko.append((isin, name))

    print("=" * 78)
    print(f"  RESUMEN: {len(ok)} con datos en EUFUND · {len(ko)} sin datos")
    print("=" * 78)
    if ok:
        print("\n  CON DATOS (listos para el backtester):")
        for isin, name in ok:
            print(f"    {isin}  {name}")
    if ko:
        print("\n  SIN DATOS en EUFUND (revisar / pedir a soporte de EODHD):")
        for isin, name in ko:
            print(f"    {isin}  {name}")


if __name__ == "__main__":
    main()
