"""FIRST BLADE plan loader. Uses the collected morning post when it is for TODAY; otherwise computes a labeled CALC plan
from data on hand (SPY 1m SIP parquet, topped up each refresh): floor pivots from the prior RTH H/L/C plus today's
04:00-09:30 ET pre-market range and the current session price. Same keys as plan_b.json + calc/asof/basis."""
import json
from datetime import datetime
from pathlib import Path
import pandas as pd
R = Path(__file__).resolve().parent
POST = R / "xnews/spartan/plan_b.json"; OUT = R / "xnews/spartan/first_blade_calc.json"

def calc(sym="SPY"):
    d = pd.read_parquet(R / f"equity_orb15/data/{sym}_1m.parquet", columns=["ts", "open", "high", "low", "close"])
    d = d[d.ts >= d.ts.max() - pd.Timedelta(days=10)]; t = d.ts.dt.tz_localize(None); m = t.dt.hour * 60 + t.dt.minute; day = t.dt.date
    today = datetime.now(d.ts.dt.tz).date() if hasattr(d.ts.dt, "tz") else max(day)
    rth = d[(m >= 570) & (m < 960)]; prior = sorted(set(rth.ts.dt.date[rth.ts.dt.date < today]))[-1]
    p = rth[rth.ts.dt.date == prior]; H, L, C = float(p.high.max()), float(p.low.min()), float(p.close.iloc[-1])
    pre = d[(day == today) & (m >= 240) & (m < 570)]; ses = d[(day == today) & (m >= 570) & (m < 960)]
    P = (H + L + C) / 3; R1, S1, R2, S2 = 2 * P - L, 2 * P - H, P + (H - L), P - (H - L)
    last = float((ses if len(ses) else pre if len(pre) else p).close.iloc[-1]); bar_t = (ses if len(ses) else pre if len(pre) else p).ts.iloc[-1]
    onh = float(pre.high.max()) if len(pre) else None; onl = float(pre.low.min()) if len(pre) else None
    lean = ("Leaning bullish" if last > P else "Leaning bearish") + (" · above pre-mkt high" if onh and last > onh else " · below pre-mkt low" if onl and last < onl else " · inside pre-mkt range" if onh else "")
    r2 = lambda x: round(x, 2)
    asof_pt = bar_t.tz_convert("America/Los_Angeles").strftime("%H:%M PT")
    o = {"symbol": sym, "date": str(today), "calc": True, "posted_pt": f"CALC {asof_pt}", "asof": f"{today} {asof_pt}",
         "pivot": r2(P), "room_higher": r2(R1), "resistance_break": r2(R2), "room_lower": r2(S1), "support_break": r2(S2), "bias": lean,
         "pdh": r2(H), "pdl": r2(L), "pdc": r2(C), "prior_day": str(prior), "onh": onh and r2(onh), "onl": onl and r2(onl), "last": r2(last),
         "basis": f"floor pivots from {prior} RTH H {H:.2f} / L {L:.2f} / C {C:.2f}" + (f"; pre-mkt {onl:.2f}–{onh:.2f}" if onh else "") + f"; last {last:.2f} @ {asof_pt} (delayed)",
         "updates": []}
    OUT.write_text(json.dumps(o, indent=1)); return o

def load():
    try: post = json.loads(POST.read_text())
    except Exception: post = {}
    today = datetime.now().strftime("%Y-%m-%d")
    if post.get("date") == today and post.get("pivot"): return post
    try: return calc()
    except Exception as e:
        print("first blade calc failed", e); return post
if __name__ == "__main__": print(json.dumps(load())[:600])
