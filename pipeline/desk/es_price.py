"""Robust ES last price: ES=F -> front-month contract -> MES=F -> SPY x (ES/SPY factor), labeled. Returns (price, label)."""
import json, logging
from datetime import date
from pathlib import Path
R = Path(__file__).resolve().parent
logging.getLogger("yfinance").setLevel(logging.CRITICAL)
MC = "HMUZ"
def front_month(d=None):
    d = d or date.today(); y, m = d.year, d.month
    for q in (3, 6, 9, 12):   # roll ~1 week before 3rd-Friday expiry
        if m < q or (m == q and d.day < 12): return f"ES{MC[(q // 3) - 1]}{str(y)[2:]}.CME"
    return f"ESH{str(y + 1)[2:]}.CME"
def _yf(sym):
    import yfinance as yf
    for per in ("1d", "5d"):
        h = yf.Ticker(sym).history(period=per, interval="5m", prepost=True)
        if len(h): return round(float(h["Close"].iloc[-1]), 2)
    return None
def es_price():
    for sym, lab in (("ES=F", "ES"), (front_month(), "ES front-month"), ("MES=F", "MES")):
        try:
            p = _yf(sym)
            if p: return p, lab
        except Exception: pass
    try:
        f = (json.load(open(R / "es_levels/es_conversions.json")).get("factors") or {}).get("es_per_spy")
        spy = _yf("SPY")
        if f and spy: return round(spy * float(f), 2), "ES≈SPY×ratio (proxy)"
    except Exception: pass
    try: return json.load(open(R / "es_levels/summary.json")).get("price"), "ES last summary (stale)"
    except Exception: return None, "N/A"
if __name__ == "__main__": print(es_price(), front_month())
