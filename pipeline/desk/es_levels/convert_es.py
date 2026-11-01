#!/usr/bin/env python3
"""Convert posted ES levels (+ pinned Iron Ladder) to SPY only. Free delayed data only.
SPY = ES * factor, factor = SPY_close / ES_close at a synchronized timestamp (last 5m bar ending <= 16:00 ET of latest session)."""
import json, sys
from pathlib import Path
from datetime import datetime
import numpy as np, pandas as pd, yfinance as yf
HERE = Path(__file__).resolve().parent
MANC = HERE.parent / "xnews/mancini/levels_a.json"
PINS = HERE / "manual_overrides.json"
OUT = HERE / "es_conversions.json"
SYMS = ["ES=F", "SPY"]

def sync_prices():
    df = yf.download(SYMS, period="5d", interval="5m", progress=False, auto_adjust=False, prepost=True)["Close"]
    df.index = df.index.tz_convert("America/New_York")
    day = df["SPY"].dropna().index[-1].date()
    d = df[df.index.date == day]
    cut = d[d.index.strftime("%H:%M") <= "15:55"].dropna(subset=["SPY", "ES=F"])
    row = cut.iloc[-1]  # bar 15:55-16:00 -> close = 16:00 ET print
    ts = row.name + pd.Timedelta(minutes=5)
    p = {s: float(row[s]) for s in SYMS if pd.notna(row[s])}
    return ts, p

def main():
    ts, p = sync_prices()
    es, spy = p["ES=F"], p["SPY"]
    k = spy / es
    def conv(L):
        return {"es": L, "es_pct": round((L / es - 1) * 100, 3), "spy": round(L * k, 2)}
    M = json.load(open(MANC)); lat = M["latest"]
    mlev = sorted(set(lat["supports"] + lat["resistances"] + lat["key_levels"]), reverse=True)
    res = {"generated_pt": datetime.now().strftime("%Y-%m-%d %H:%M PT"), "sync_timestamp_et": str(ts),
           "prices": p, "factors": {"spy_per_es": k, "es_per_spy": 1 / k},
           "method": __doc__.strip(),
           "mancini": {"date": lat["date"], "levels": [dict(conv(L), role=("S" if L in lat["supports"] else "") + ("R" if L in lat["resistances"] else "") + ("K" if L in lat["key_levels"] else "")) for L in mlev]}}
    if PINS.exists():
        pin = json.load(open(PINS))["pinned"]
        res["iron_ladder"] = [dict(conv(L), role=r) for r in ("resistance", "support") for L in sorted(pin[r], reverse=True)]
    json.dump(res, open(OUT, "w"), indent=1)
    print(json.dumps({k2: res[k2] for k2 in ("sync_timestamp_et", "prices", "factors")}, indent=1))
    for name in ("mancini", "iron_ladder"):
        rows = res[name]["levels"] if name == "mancini" else res.get(name, [])
        print(f"\n{name}\n  ES     role  %ES     SPY")
        for r in rows: print(f"  {r['es']:<6} {r['role']:<10} {r['es_pct']:+.2f}  {r['spy']:.2f}")
if __name__ == "__main__": main()
