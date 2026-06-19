#!/usr/bin/env python3
"""
probar_fondos.py - Diagnostico: comprueba que fondos UCITS (por ISIN) tienen datos
en EODHD a traves del exchange virtual EUFUND ({ISIN}.EUFUND).
Se ejecuta como workflow temporal (probar-fondos.yml) con el secreto EODHD_API_KEY.
El resultado sale en el log de Actions. No hace commit.
"""
import os, sys, json, urllib.request

KEY = os.environ.get("EODHD_API_KEY")
if not KEY:
    print("ERROR: falta el secreto EODHD_API_KEY"); sys.exit(1)
API = "https://eodhd.com/api"

FUNDS = [
    ("ES0119184002", "Cobas Iberia C FI"),
    ("ES0159201013", "Magallanes Iberian Equity M FI"),
    ("ES0112616000", "Azvalor Iberia FI"),
    ("ES0175902008", "Sigma Internacional FI"),
    ("ES0146309002", "Horos Value Internacional FI"),
    ("ES0156673008", "Japan Deep Value Fund FI"),
    ("ES0124037005", "Cobas Seleccion C FI"),
    ("ES0113728002", "Cobas Grandes Companias C FI"),
    ("ES0110407105", "Gestion Boutique VI Gestivalue Cap A FI"),
    ("ES0119199000", "Cobas Internacional C FI"),
    ("ES0165243009", "Myinvestor Value A FI"),
    ("LU0203975437", "Robeco BP Global Premium Equities D EUR"),
    ("ES0112611001", "Azvalor Internacional FI"),
    ("ES0141116030", "Hamco Global Value Fund R FI"),
    ("ES0112609005", "Azvalor Blue Chips FI"),
    ("LU1278917452", "DWS Invest CROCI Sectors Plus LC"),
    ("LU0094560744", "MFS Meridian Global Equity A1 EUR"),
    ("LU0360477987", "Morgan Stanley US Growth ZH EUR"),
    ("LU2015255867", "Morgan Stanley Global Insight ZH EUR"),
    ("ES0173311079", "Renta 4 Andromeda Value Capital FI"),
    ("LU0552385535", "MS Global Opportunity Z USD"),
    ("ES0173311103", "Renta 4 Numantia Patrimonio Global FI"),
    ("ES0168799064", "Gestion Boutique IV Only Compounders FI"),
    ("LU0974293671", "Robeco MegaTrends D EUR"),
    ("IE00BYYLQ421", "Comgest Growth World EUR Z Acc"),
    ("LU0690375182", "Fundsmith Equity Fund Sicav T EUR Acc"),
    ("ES0112617016", "B&H Acciones C FI"),
    ("IE00BZ0X9T58", "Comgest Growth Europe Opportunities EUR Z Acc"),
    ("IE00B2NXKW18", "Seilern World Growth EUR U R"),
    ("ES0137768000", "Baelo Dividendo Creciente A FI"),
    ("ES0147897005", "Impassive Wealth FI"),
    ("ES0156572002", "Myinvestor Cartera Permanente FI"),
    ("ES0116848005", "Global Allocation R FI"),
    ("LU0171307068", "BGF World Healthscience A2"),
    ("LU2441282899", "Janus Henderson Biotechnology"),
    ("IE00B3NLSS43", "Polar Capital Healthcare"),
    ("LU0415391431", "Bellevue (Lux) Bellevue Md & Svc B EUR"),
    ("LU0251853072", "AB International HC A EUR"),
    ("LU1213836080", "Fidelity Global Technology"),
    ("LU0260870158", "Franklin Technology"),
    ("LU0171310443", "BGF World Technology"),
    ("LU0302296495", "DNB Fund - Technology"),
    ("IE00B4468526", "Polar Capital Global Technology Fund"),
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
    print("=" * 80)
    print("  DIAGNOSTICO DE FONDOS UCITS EN EODHD (exchange virtual EUFUND)")
    print("=" * 80)
    ok, ko = [], []
    for isin, name in FUNDS:
        rows = eod(f"{isin}.EUFUND")
        if rows:
            d0, d1 = rows[0].get("date"), rows[-1].get("date")
            print(f"OK  {isin}  {name[:46]:<46} {len(rows):>5} pts - {d0} -> {d1}")
            ok.append((isin, name))
        else:
            res = search(isin)
            if res:
                alt = ", ".join(f"{r.get('Code')}.{r.get('Exchange')}" for r in res[:3])
                print(f"--  {isin}  {name[:46]:<46} no en EUFUND - search: {alt}")
            else:
                print(f"XX  {isin}  {name[:46]:<46} no encontrado")
            ko.append((isin, name))
    print("=" * 80)
    print(f"  RESUMEN: {len(ok)} con datos en EUFUND - {len(ko)} sin datos")
    print("=" * 80)
    if ko:
        print()
        print("  SIN DATOS en EUFUND (revisar / pedir a soporte EODHD):")
        for isin, name in ko:
            print(f"    {isin}  {name}")


if __name__ == "__main__":
    main()
