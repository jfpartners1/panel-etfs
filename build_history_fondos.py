#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
build_history_fondos.py - Genera history_fondos.json con el NAV historico de los
fondos UCITS (por ISIN, exchange virtual EUFUND), para el backtester de fondos.

Reutiliza la descarga de build_data.py (misma API key, misma cache). 1 llamada por
fondo. Pensado para ejecutarse ~1 vez por semana. Todo en EUR.

Salida (mismo formato compacto que history.json de ETFs, con metadatos de bloque):
{ "asOf","dates":[...], "funds":{ ISIN:{ "nm","bloque","sub","nota","px":[...] } } }

Flags: --demo (sin red) · --refresh (ignora cache) · --years N (def. 20) · --out RUTA
"""
import argparse, json, os, sys
from datetime import date, timedelta
import build_data as bd

# (ISIN, nombre, bloque, subbloque, nota)
FUNDS = [
    # (ISIN, nombre, bloque, subbloque, nota)
    ("IE00BYX5MX67", "Fidelity S&P 500 Index Fund EUR P Acc", "Indexado", "", "S&P500"),
    ("ES0165242001", "Myinvestor S&P500 Equiponderado FI", "Indexado", "", "S&P500 Equiponderado"),
    ("ES0184894006", "Myinvestor ACWI FI", "Indexado", "", "MSCI ACWI"),
    ("IE00BYX5NX33", "Fidelity MSCI World Index Fund EUR P Acc", "Indexado", "", "MSCI WORLD"),
    ("IE00B42W3S00", "Vanguard Global Small-Cap Index Fund Investor EUR Acc", "Indexado", "", "SMALL CAP GLOBAL"),
    ("IE0007281425", "Vanguard Japan Stock Index Fund Investor EUR Accumulation", "Indexado", "", "JAPÓN"),
    ("IE0007201266", "Vanguard Pacific ex-Japan Stock Index Fund EUR Acc", "Indexado", "", "PÁCIFICO Ex Japón"),
    ("IE0031786142", "Vanguard Emerging Markets Stock Index Fund Investor EUR Acc", "Indexado", "", "EMERGENTES"),
    ("IE0007987690", "Vanguard European Stock Index Fund Investor EUR Accumulation", "Indexado", "", "EUROPA"),
    ("ES0114105036", "Bankinter EE.UU. Nasdaq 100 R FI", "Indexado", "", "NASDAQ 100"),
    ("LU0625737910", "Pictet-China Index P EUR", "Indexado", "", "CHINA"),
    ("ES0152741031", "ING Direct Fondo Naranja Ibex 35 FI", "Indexado", "", "IBEX"),
    ("ES0159201013", "Magallanes Iberian Equity M FI", "Activo", "Value", "VALUE IBÉRICO"),
    ("ES0112616000", "Azvalor Iberia FI", "Activo", "Value", "VALUE IBÉRICO"),
    ("ES0175902008", "Sigma Internacional FI", "Activo", "Value", "MIXTO VALUE"),
    ("ES0146309002", "Horos Value Internacional FI", "Activo", "Value", "VALUE GLOBAL"),
    ("ES0156673008", "Japan Deep Value Fund FI", "Activo", "Value", "JAPÓN VALUE SMALL"),
    ("ES0124037005", "Cobas Selección C FI", "Activo", "Value", "VALUE GLOBAL"),
    ("ES0113728002", "Cobas Grandes Compañías C FI", "Activo", "Value", "VALUE GRANDES"),
    ("ES0119199000", "Cobas Internacional C FI", "Activo", "Value", "VALUE GLOBAL"),
    ("ES0165243009", "Myinvestor Value A FI", "Activo", "Value", "VALUE EUR SMALL CAPS"),
    ("LU0203975437", "Robeco BP Global Premium Equities D EUR", "Activo", "Value", "VALUE MULTIFACTOR"),
    ("ES0112611001", "Azvalor Internacional FI", "Activo", "Value", "VALUE GLOBAL"),
    ("ES0141116030", "Hamco Global Value Fund R FI", "Activo", "Value", "DEEP VALUE GLOBAL"),
    ("ES0112609005", "Azvalor Blue Chips FI", "Activo", "Value", "BLUE CHIPS VALUE"),
    ("LU1278917452", "DWS Invest CROCI Sectors Plus LC", "Activo", "Value", "VALUE QUANT"),
    ("LU0094560744", "MFS Meridian Funds - Global Equity Fund A1 EUR", "Activo", "Value", "CALIDAD GLOBAL"),
    ("LU0360477987", "Morgan Stanley Investment Funds – US Growth Fund ZH EUR", "Activo", "Growth", "HIPERCRECIMIENTO EEUU"),
    ("LU0552385535", "Morgan Stanley Investment Funds – Global Opportunity Fund Z USD", "Activo", "Growth", "COMPOUNDERS GLOBALES"),
    ("ES0173311079", "Renta 4 Multigestión Andrómeda Value Capital FI", "Activo", "Growth", "GROWTH TECNOLÓGICO FLEXIBLE"),
    ("ES0168799064", "Gestión Boutique IV Only Compounders FI", "Activo", "Growth", "COMPOUNDERS GLOBALES"),
    ("LU0974293671", "Robeco Global Multi-Thematic D EUR", "Activo", "Growth", "MEGATENDENCIAS GLOBALES"),
    ("LU0690375182", "Fundsmith Equity Fund Sicav T EUR Acc", "Activo", "Growth", "COMPOUNDERS GLOBALES"),
    ("IE00BZ0X9T58", "Comgest Growth Europe Opportunities EUR Z Acc", "Activo", "Growth", "CALIDAD-GROWTH EUROPEO"),
    ("IE00BJM0B969", "Blue Whale Growth Fund EUR R", "Activo", "Growth", "CALIDAD-GROWTH TECNOLÓGICA"),
    ("ES0137768000", "Baelo Dividendo Creciente A FI", "Activo", "Growth", "MULTIACTIVO GLOBAL"),
    ("ES0147897005", "Impassive Wealth FI", "Activo", "Growth", "MULTIACTIVO GLOBAL SISTEMÁTICO"),
    ("ES0156572002", "MyInvestor Cartera Permanente FI", "Activo", "Growth", "CARTERA PERMANENTE GLOBAL"),
    ("ES0116848005", "Global Allocation R FI", "Activo", "Growth", "MULTIACTIVO GLOBAL FLEXIBLE"),
    ("LU0171307068", "BGF World Healthscience A2", "Activo", "Salud", "SALUD GLOBAL DIVERSIFICADA"),
    ("LU2441282899", "Janus Henderson Biotechnology", "Activo", "Salud", "BIOTECNOLOGÍA GLOBAL"),
    ("IE00B3NLSS43", "Polar Capital Healthcare", "Activo", "Salud", "SALUD GLOBAL INNOVADORA"),
    ("LU0415391431", "Bellevue (Lux) Bellevue Md & Svc B EUR", "Activo", "Salud", "TECNOLOGÍA MÉDICA Y SERVICIOS SANITARIOS"),
    ("LU0251853072", "AB International HC A EUR", "Activo", "Salud", "SALUD GLOBAL DE CALIDAD"),
    ("LU1213836080", "Fidelity Global Technology", "Activo", "Tecnología", "TECNOLOGÍA GLOBAL"),
    ("LU0260870158", "Franklin Technology", "Activo", "Tecnología", "TECH GROWTH"),
    ("LU0171310443", "BGF World Technology", "Activo", "Tecnología", "MEGACAPS TECH"),
    ("LU0302296495", "DNB Fund - Technology", "Activo", "Tecnología", "TECH NÓRDICA"),
    ("IE00B4468526", "Polar Capital Global Technology Fund", "Activo", "Tecnología", "INNOVACIÓN TECH"),
    ("LU0187079347", "Robeco Global Consumer Trends D €", "Activo", "Consumo", "TENDENCIAS DE CONSUMO"),
    ("LU2295319300", "MS INVF Global Brands A EUR", "Activo", "Consumo", "MARCAS GLOBALES"),
    ("LU0329429897", "GAM Multistock Luxury Brands Equity EUR B", "Activo", "Consumo", "LUJO GLOBAL"),
    ("LU1162516717", "BlackRock Systematic Global Equity Absolute Return", "Activo", "Market Neutral", "MARKET NEUTRAL GLOBAL"),
    ("LU1429039461", "Schroder GAIA Two Sigma Diversified", "Activo", "Market Neutral", "MARKET NEUTRAL CUANTITATIVO"),
    ("LU1883342377", "Amundi Global Equity", "Activo", "Global", "RENTA VARIABLE GLOBAL"),
    ("LU0157178582", "JPM Global Select Equity", "Activo", "Global", "RENTA VARIABLE GLOBAL"),
    ("LU1984712320", "Janus Henderson Global Smaller Companies", "Activo", "Small Caps", "SMALL CAP GLOBAL"),
    ("LU0918140210", "T. Rowe Price US Smlr Cm Eq A EUR", "Activo", "Small Caps", "SMALL CAP GLOBAL"),
    ("LU0300834669", "Alken Small Cap Europe", "Activo", "Small Caps", "SMALL CAP EUROPA"),
    ("LU0125944966", "MFS Meridian European Companies", "Activo", "Small Caps", "SMALL CAP EUROPA"),
    ("LU0491217419", "Robeco Indian Equities D €", "Activo", "Asia", "RENTA VARIABLE INDIA"),
    ("LU0329070915", "Jupiter India Select", "Activo", "Asia", "RENTA VARIABLE INDIA"),
    ("LU0345361124", "Fidelity Funds - Asia Pacific Opportunities", "Activo", "Asia", "RENTA VARIABLE ASIA PACIFICO"),
    ("LU0413543058", "Fidelity Japan Value A-Acc-EUR", "Activo", "Asia", "RENTA VARIABLE JAPÓN"),
    ("LU2295319219", "Morgan Stanley Asia Opportunity", "Activo", "Asia", "RENTA VARIABLE ASIA"),
    ("LU0922334643", "Fidelity Nordic A", "Activo", "Nórdico", "RENTA VARIABLE NÓRDICA"),
    ("LU0273159177", "DWS Invest Gold and Prec Mtl Eqs LC", "Activo", "Alternativo", "RENTA VARIABLE ORO"),
    ("LU0172157280", "Bgf World Mining A2 EUR", "Activo", "Alternativo", "RENTA VARIABLE ORO"),
    ("LU0273158872", "DWS Invest Global Agribusiness LC", "Activo", "Alternativo", "RENTA VARIABLE AGRICULTURA"),
    ("LU1165135440", "BNP Paribas Aqua C C", "Activo", "Alternativo", "RENTA VARIABLE AGUA"),
    ("LU0415415636", "Vontobel Commodity H Hedged EUR", "Activo", "Alternativo", "MATERIAS PRIMAS"),
    ("LU0714179727", "JPMorgan Investment Funds - Global Dividend Fund", "Activo", "Dividendo", "RENTA VARIABLE DIVIDENDO"),
    ("IE00BDGV0183", "Guinness Global Equity Income C EUR Dist", "Activo", "Dividendo", "RENTA VARIABLE DIVIDENDO"),
    ("FR0013346079", "Groupama Ultra Short Term Bond", "Renta Fija", "Ultra Corto Plazo", "CRÉDITO ULTRACORTO"),
    ("FR001400CFA4", "OstrumSRI Credit Ultra Short", "Renta Fija", "Ultra Corto Plazo", "CRÉDITO ESG ULTRACORTO"),
    ("FR0011365212", "Amundi Ultra Short Term Bond", "Renta Fija", "Ultra Corto Plazo", "BONOS ULTRACORTOS"),
    ("LU0080237943", "DWS Euro Ultra Short Fixed", "Renta Fija", "Ultra Corto Plazo", "RENTA FIJA EURO ULTRACORTA"),
    ("LU1585265066", "Tikehau Short Duration*", "Renta Fija", "Ultra Corto Plazo", "CRÉDITO DE CORTA DURACIÓN"),
    ("FR0010149120", "Carmignac Securité", "Renta Fija", "Corto Plazo", "BONOS EURO CORTO PLAZO"),
    ("LU1706854152", "Amundi Diversified Short-Term", "Renta Fija", "Corto Plazo", "RENTA FIJA CORTA DIVERSIFICADA"),
    ("FR0010116343", "BNP PARIBAS Tresorerie", "Renta Fija", "Corto Plazo", "TESORERÍA EURO"),
    ("FI0008800511", "Evli Short Corporate Bond", "Renta Fija", "Corto Plazo", "CRÉDITO CORPORATIVO CORTO"),
    ("LU0346393613", "Fidelity Funds - Euro Short Term", "Renta Fija", "Corto Plazo", "BONOS EURO CORTO PLAZO"),
    ("FR0010829697", "Amundi Enhanced Ultra Short Term Bond", "Renta Fija", "Corto Plazo", "ULTRACORTO OPTIMIZADO"),
    ("LU1882441907", "Amundi US Short Term Bond", "Renta Fija", "Corto Plazo", "BONOS USA CORTO PLAZO"),
    ("IE00BDT57V65", "PIMCO Low Duration Income", "Renta Fija", "Corto Plazo", "RENTA FIJA DE BAJA DURACIÓN"),
    ("LU1623762843", "Carmignac Pf Credit", "Renta Fija", "Medio Plazo", "CRÉDITO GLOBAL FLEXIBLE"),
    ("LU0694238766", "MS - Global Fixed Income", "Renta Fija", "Medio Plazo", "RENTA FIJA GLOBAL"),
    ("IE00B84J9L26", "PIMCO GIS Income E EUR Hedged", "Renta Fija", "Medio Plazo", "RENTA FIJA GLOBAL INCOME"),
    ("LU1984948874", "DNCA Invest Alpha Bonds B EUR", "Renta Fija", "Medio Plazo", "BONOS FLEXIBLES RETORNO ABSOLUTO"),
    ("LU0942882589", "BrightGate Global Income", "Renta Fija", "Medio Plazo", "CRÉDITO GLOBAL INCOME"),
    ("IE000MI53C66", "MAN Global Investment Grade", "Renta Fija", "Medio Plazo", "CRÉDITO GLOBAL INVESTMENT GRADE"),
    ("IE00B246KL88", "Vanguard 20+ Year Euro Treasury Index Fund EUR Acc", "Renta Fija", "Largo Plazo", "DEUDA PÚBLICA EURO LARGA"),
    ("LU0241467587", "Pictet EUR Goverment Bonds", "Renta Fija", "Largo Plazo", "DEUDA PÚBLICA EURO"),
    ("LU0849399786", "Schroder Isf Euro High Yield", "Renta Fija", "High Yield", "HIGH YIELD EUROPA"),
    ("LU0658026512", "Axa Europe Short D High Yield", "Renta Fija", "High Yield", "HIGH YIELD EUROPA"),
    ("LU0170291933", "Candriam Bonds Global High Yield C ACC", "Renta Fija", "High Yield", "HIGH YIELD GLOBAL"),
]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--demo", action="store_true")
    ap.add_argument("--refresh", action="store_true")
    ap.add_argument("--years", type=int, default=20)
    ap.add_argument("--out", default="history_fondos.json")
    args = ap.parse_args()

    try:
        start = date.today().replace(year=date.today().year - args.years)
    except ValueError:
        start = date.today() - timedelta(days=args.years * 365)

    series, alldates = {}, set()
    for isin, nm, bloque, sub, nota in FUNDS:
        sym = f"{isin}.EUFUND"
        try:
            rows = bd.fetch_eod_demo(sym, start) if args.demo else bd.cached_eod(sym, start, args.refresh)
        except Exception as e:
            print(f"  - error {sym}: {e}", file=sys.stderr); continue
        d = {dt.isoformat(): round(c, 4) for dt, c, v in rows if c}
        if len(d) < 30:
            print(f"  - {isin} pocos datos ({len(d)}), omitido", file=sys.stderr); continue
        series[isin] = (nm, bloque, sub, nota, d)
        alldates.update(d.keys())

    dates = sorted(alldates)
    didx = {dt: i for i, dt in enumerate(dates)}
    funds = {}
    for isin, (nm, bloque, sub, nota, d) in series.items():
        px = [None] * len(dates)
        for dt, c in d.items():
            px[didx[dt]] = c
        funds[isin] = {"nm": nm, "bloque": bloque, "sub": sub, "nota": nota, "px": px}

    out = {"asOf": date.today().isoformat(), "start": dates[0] if dates else None,
           "dates": dates, "funds": funds}
    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, separators=(",", ":"))

    mb = os.path.getsize(args.out) / 1e6
    span = f"{dates[0]} -> {dates[-1]}" if dates else "-"
    print(f"OK -> {args.out}  ({len(funds)} fondos - {len(dates)} fechas - {span} - {mb:.2f} MB)")
    print(f"   llamadas reales a EODHD: {bd.STATE['calls']}")


if __name__ == "__main__":
    main()
