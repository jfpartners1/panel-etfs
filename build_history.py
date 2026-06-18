#!/usr/bin/env python3
"""
build_history.py — Genera history.json con ~12 años de cierres ajustados de cada ETF,
para la página de backtesting de carteras (cartera.html).

Reutiliza la lógica de descarga de build_data.py (misma API key, misma caché en disco).
Cuesta 1 llamada por ETF (igual que el panel); solo cambia la fecha de inicio, que pide
más histórico en esa misma llamada. Pensado para ejecutarse ~1 vez por semana.

Formato de salida (compacto, alineado por un eje de fechas común):
{
  "asOf": "2026-06-18",
  "dates": ["2014-06-18", ...],            # eje común (unión de todas las fechas de trading)
  "etfs": {
    "SPY": {"nm":"S&P 500","cat":"IDX","px":[123.4, 124.1, null, ...]},  # null antes de existir
    ...
  }
}
El frontend recorta al periodo común (donde todos los ETFs elegidos tienen dato) y calcula
rentabilidad, riesgo y correlaciones a partir de los precios.

Flags: --demo (sin red, datos sintéticos) · --refresh (ignora caché) · --years N · --out RUTA
"""
import argparse, json, os, sys
from datetime import date, timedelta
import build_data as bd


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--demo", action="store_true", help="sin red, datos sintéticos")
    ap.add_argument("--refresh", action="store_true", help="ignora la caché en disco")
    ap.add_argument("--years", type=int, default=12, help="años de histórico (por defecto 12)")
    ap.add_argument("--out", default="history.json")
    args = ap.parse_args()

    try:
        start = date.today().replace(year=date.today().year - args.years)
    except ValueError:                                  # 29 feb
        start = date.today() - timedelta(days=args.years * 365)

    series, alldates = {}, set()
    for tk, nm, cat, key in bd.UNIVERSE:
        sym = bd.eod_sym(tk)
        try:
            rows = bd.fetch_eod_demo(sym, start) if args.demo else bd.cached_eod(sym, start, args.refresh)
        except Exception as e:
            print(f"  · error {sym}: {e}", file=sys.stderr)
            continue
        d = {dt.isoformat(): round(c, 4) for dt, c, v in rows if c}
        if len(d) < 30:                                  # ignora series demasiado cortas
            continue
        series[tk] = (nm, cat, d)
        alldates.update(d.keys())

    dates = sorted(alldates)
    didx = {dt: i for i, dt in enumerate(dates)}
    etfs = {}
    for tk, (nm, cat, d) in series.items():
        px = [None] * len(dates)
        for dt, c in d.items():
            px[didx[dt]] = c
        etfs[tk] = {"nm": nm, "cat": cat, "px": px}

    out = {"asOf": date.today().isoformat(),
           "start": dates[0] if dates else None,
           "dates": dates, "etfs": etfs}
    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, separators=(",", ":"))

    mb = os.path.getsize(args.out) / 1e6
    span = f"{dates[0]} → {dates[-1]}" if dates else "—"
    print(f"OK -> {args.out}  ({len(etfs)} ETFs · {len(dates)} fechas · {span} · {mb:.2f} MB)")
    print(f"   llamadas reales a EODHD: {bd.STATE['calls']}")


if __name__ == "__main__":
    main()
