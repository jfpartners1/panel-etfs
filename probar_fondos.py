#!/usr/bin/env python3
"""probar_fondos.py - Diagnostico final: 76 fondos del Excel por EUFUND. No hace commit."""
import os, sys, json, urllib.request
KEY=os.environ.get("EODHD_API_KEY")
if not KEY:
    print("ERROR: falta el secreto EODHD_API_KEY"); sys.exit(1)
API="https://eodhd.com/api"

FUNDS=[
    ("IE00BYX5MX67", "Fidelity S&P 500 Index Fund EUR P Acc"),
    ("ES0165242001", "Myinvestor S&P500 Equiponderado FI"),
    ("ES0184894006", "Myinvestor ACWI FI"),
    ("IE00BYX5NX33", "Fidelity MSCI World Index Fund EUR P Acc"),
    ("IE00B42W3S00", "Vanguard Global Small-Cap Index Fund Investor EU"),
    ("IE0007281425", "Vanguard Japan Stock Index Fund Investor EUR Acc"),
    ("IE0007201266", "Vanguard Pacific ex-Japan Stock Index Fund EUR A"),
    ("IE0031786142", "Vanguard Emerging Markets Stock Index Fund Inves"),
    ("IE0007987690", "Vanguard European Stock Index Fund Investor EUR "),
    ("ES0114105036", "Bankinter EE.UU. Nasdaq 100 R FI"),
    ("LU0625737910", "Pictet-China Index P EUR"),
    ("ES0152741031", "ING Direct Fondo Naranja Ibex 35 FI"),
    ("ES0159201013", "Magallanes Iberian Equity M FI"),
    ("ES0112616000", "Azvalor Iberia FI"),
    ("ES0175902008", "Sigma Internacional FI"),
    ("ES0146309002", "Horos Value Internacional FI"),
    ("ES0156673008", "Japan Deep Value Fund FI"),
    ("ES0124037005", "Cobas Seleccion C FI"),
    ("ES0113728002", "Cobas Grandes Companias C FI"),
    ("ES0119199000", "Cobas Internacional C FI"),
    ("ES0165243009", "Myinvestor Value A FI"),
    ("LU0203975437", "Robeco BP Global Premium Equities D EUR"),
    ("ES0112611001", "Azvalor Internacional FI"),
    ("ES0141116030", "Hamco Global Value Fund R FI"),
    ("ES0112609005", "Azvalor Blue Chips FI"),
    ("LU1278917452", "DWS Invest CROCI Sectors Plus LC"),
    ("LU0094560744", "MFS Meridian Funds - Global Equity Fund A1 EUR"),
    ("LU0360477987", "Morgan Stanley Investment Funds  US Growth Fund "),
    ("LU0552385535", "Morgan Stanley Investment Funds  Global Opportun"),
    ("ES0173311079", "Renta 4 Multigestion Andromeda Value Capital FI"),
    ("ES0168799064", "Gestion Boutique IV Only Compounders FI"),
    ("LU0974293671", "Robeco Global Multi-Thematic D EUR"),
    ("LU0690375182", "Fundsmith Equity Fund Sicav T EUR Acc"),
    ("IE00BZ0X9T58", "Comgest Growth Europe Opportunities EUR Z Acc"),
    ("IE00BJM0B969", "Blue Whale Growth Fund EUR R"),
    ("ES0137768000", "Baelo Dividendo Creciente A FI"),
    ("ES0147897005", "Impassive Wealth FI"),
    ("ES0156572002", "MyInvestor Cartera Permanente FI"),
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
    ("LU0187079347", "Robeco Global Consumer Trends D"),
    ("LU2295319300", "MS INVF Global Brands A EUR"),
    ("LU0329429897", "GAM Multistock Luxury Brands Equity EUR B"),
    ("LU1162516717", "BlackRock Systematic Global Equity Absolute Retu"),
    ("LU1429039461", "Schroder GAIA Two Sigma Diversified"),
    ("LU0705072006", "RAM European Market Neutral Equity"),
    ("FR0013346079", "Groupama Ultra Short Term Bond"),
    ("FR001400CFA4", "OstrumSRI Credit Ultra Short"),
    ("FR0011365212", "Amundi Ultra Short Term Bond"),
    ("LU0080237943", "DWS Euro Ultra Short Fixed"),
    ("LU1585265066", "Tikehau Short Duration*"),
    ("FR0010149120", "Carmignac Securite"),
    ("LU1706854152", "Amundi Diversified Short-Term"),
    ("FR0010116343", "BNP PARIBAS Tresorerie"),
    ("FI0008800511", "Evli Short Corporate Bond"),
    ("LU0346393613", "Fidelity Funds - Euro Short Term"),
    ("FR0010829697", "Amundi Enhanced Ultra Short Term Bond"),
    ("LU1882441907", "Amundi US Short Term Bond"),
    ("IE00BDT57V65", "PIMCO Low Duration Income"),
    ("LU1623762843", "Carmignac Pf Credit"),
    ("LU0694238766", "MS - Global Fixed Income"),
    ("IE00B84J9L26", "PIMCO GIS Income E EUR Hedged"),
    ("LU1984948874", "DNCA Invest Alpha Bonds B EUR"),
    ("LU0942882589", "BrightGate Global Income"),
    ("IE000MI53C66", "MAN Global Investment Grade"),
    ("IE00B246KL88", "Vanguard 20+ Year Euro Treasury Index Fund EUR A"),
    ("LU0241467587", "Pictet EUR Goverment Bonds"),
]

def fetch(url):
    with urllib.request.urlopen(url, timeout=30) as r:
        return r.read().decode()

def eod(sym, frm="2008-01-01"):
    try:
        data=json.loads(fetch(f"{API}/eod/{sym}?api_token={KEY}&fmt=json&from={frm}"))
        if isinstance(data, list) and data: return data
    except Exception: pass
    return None

def search(isin):
    try: return json.loads(fetch(f"{API}/search/{isin}?api_token={KEY}&fmt=json")) or []
    except Exception: return []

def main():
    print("="*82)
    print("  DIAGNOSTICO FINAL - 76 FONDOS (exchange EUFUND)")
    print("="*82)
    ok, ko = [], []
    for isin, name in FUNDS:
        rows=eod(f"{isin}.EUFUND")
        if rows:
            d0,d1=rows[0].get("date"),rows[-1].get("date")
            print(f"OK  {isin}  {name[:48]:<48} {len(rows):>5} pts - {d0} -> {d1}")
            ok.append((isin,name))
        else:
            res=search(isin)
            if res:
                alt=", ".join(f"{r.get('Code')}.{r.get('Exchange')}" for r in res[:2])
                print(f"--  {isin}  {name[:48]:<48} no en EUFUND - search: {alt}")
            else:
                print(f"XX  {isin}  {name[:48]:<48} no encontrado")
            ko.append((isin,name))
    print("="*82)
    print(f"  RESUMEN: {len(ok)} con datos - {len(ko)} sin datos")
    print("="*82)
    if ko:
        print("\n  SIN DATOS (revisar):")
        for isin,name in ko: print(f"    {isin}  {name}")

if __name__=="__main__":
    main()
