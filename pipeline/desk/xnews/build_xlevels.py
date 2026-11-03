#!/usr/bin/env python3
"""Build confluence.json, gamma.json, scorecard.json from levels_raw.json + week_raw/posts.json + SPY 1m bars (read-only)."""
import json, re, statistics as st
from pathlib import Path
from datetime import datetime
import pandas as pd
X = Path(__file__).resolve().parent
BARS = X.parent / "equity_orb15" / "data" / "SPY_1m.parquet"
num = lambda s: float(re.split(r"[–-]", str(s).replace(",", ""))[0]) if not re.search(r"[–-]", str(s)) else st.mean(float(v) for v in re.split(r"[–-]", str(s).replace(",", "")))
HALF = {"SPY": 0.5, "QQQ": 0.5, "SPX": 5.0, "NQ": 25.0}
PROMO = re.compile(r"\b(join|discord|trial|sale|% ?off|code|referral|mentorship|subscribe|idea highlights|community|promo)\b", re.I)

bars = pd.read_parquet(BARS)
bars["t"] = pd.to_datetime(bars.ts, utc=True).dt.tz_convert("America/New_York")
bars = bars.set_index("t").sort_index()
rth = bars.between_time("09:30", "15:59")
def spy_at(s):
    """SPY close at-or-before timestamp s (ET). If s is before the rolling window, return None."""
    ts = pd.Timestamp(s, tz="America/New_York")
    sub = bars.loc[:ts]
    if sub.empty:
        return None
    return float(sub.close.iloc[-1])
SPOT = float(bars.close.iloc[-1]); SPOT_T = bars.index[-1]
# Same-time ratios from posted spots (Voltick SPX card 7,742 @ ~10:45 ET 15-min delayed; Cheddar QQQ spot 718.38 @ 10:38 ET).
# Calibration day can roll out of the Alpaca window — freeze last-known ratios so the build never crashes.
_R_FALLBACK = {"SPX": 10.03227, "QQQ": 0.93174, "SPY": 1.0}  # confluence.json as of 2026-10-30
R = {"SPY": 1.0}
for _sym, _px, _when in (("SPX", 7742, "2026-10-20 10:45"), ("QQQ", 718.38, "2026-10-20 10:38")):
    _spy = spy_at(_when)
    R[_sym] = (_px / _spy) if _spy else _R_FALLBACK[_sym]
raw = json.loads((X / "levels_raw.json").read_text())
srcs = {s["handle"]: s for s in json.loads((X / "sources.json").read_text())}
session = raw["session"]

def conv(l, sym):
    p = num(l["raw"])
    if l["symbol"] == sym: return p, False
    if l["symbol"] in R and sym in R: return p / R[l["symbol"]] * R[sym], True
    return None, False

def bands(sym):
    pts = []
    for l in raw["levels"]:
        p, c = conv(l, sym)
        if p is not None: pts.append((p, c, l))
    pts.sort(key=lambda x: x[0]); out = []; h = HALF[sym]
    for p, c, l in pts:
        if out and p - out[-1]["_lo"] <= 2 * h: out[-1]["_m"].append((p, c, l))
        else: out.append({"_lo": p, "_m": [(p, c, l)]})
    res = []
    for b in out:
        ps = [m[0] for m in b["_m"]]; med = st.median(ps)
        hs = sorted({m[2]["handle"] for m in b["_m"]})
        conf = []
        for t in ("GEX", "DP", "IMPLIED", "TA"):
            v = sorted({m[2]["raw"] for m in b["_m"] if m[2]["type"] == t})
        same = {}
        for m in b["_m"]: same.setdefault(m[2]["handle"], set()).add(m[2]["raw"])
        conf = [f"{k}: {', '.join(sorted(v))}" for k, v in same.items() if len(v) > 1]
        res.append({"price": round(med, 2), "lo": round(min(ps), 2), "hi": round(max(ps), 2), "n_sources": len(hs),
                    "weight": round(sum(srcs.get(x, {}).get("weight", 0.5) for x in hs), 2),
                    "types": sorted({m[2]["type"] for m in b["_m"]}),
                    "sources": [{"handle": m[2]["handle"], "raw_price": m[2]["raw"], "native": m[2]["symbol"], "converted": m[1],
                                 "kind": m[2]["kind"], "scope": m[2].get("scope", ""), "post_url": m[2]["url"], "posted_pt": m[2]["posted_pt"],
                                 "age_days": 1} for m in b["_m"]],
                    "conflicts": conf})
    return sorted(res, key=lambda b: -b["price"])

conf = {"date": session, "updated_pt": datetime.now().strftime("%Y-%m-%d %H:%M PT"),
        "spot": {"SPY": round(SPOT, 2), "SPX": round(SPOT * R["SPX"], 1), "QQQ": round(SPOT * R["QQQ"], 2), "asof_et": str(SPOT_T)},
        "ratios": {k: round(v, 5) for k, v in R.items()}, "band_half_width": HALF,
        "note": "Bands = levels within ±half-width (SPY/QQQ ±0.50, SPX ±5). ≈ = converted from another symbol with the posted same-time ratio. NQ levels are native only.",
        "symbols": {s: bands(s) for s in ("SPY", "QQQ", "SPX")},
        "native_only": {"NQ": bands("NQ")}}
(X / "confluence.json").write_text(json.dumps(conf, indent=1, ensure_ascii=False))

# ---- gamma.json
def pick(h, sym, *kinds, scope=None):
    for l in raw["levels"]:
        if l["handle"] == h and l["symbol"] == sym and any(k.lower() in l["kind"].lower() for k in kinds) and (scope is None or scope in l.get("scope", "")):
            return l["raw"]
    return None
G = {"date": session, "updated_pt": conf["updated_pt"], "symbols": []}
U = lambda h, i: f"https://x.com/{h}/status/{i}"
GS = json.loads((X / "gamma_sources.json").read_text())   # per-session gamma sources (curated from posts by the collection pass)
spy_src, spx_src, qqq_src, nq_src = GS.get("SPY", []), GS.get("SPX", []), GS.get("QQQ", []), GS.get("NQ", [])
EM = GS.get("em") or {}
def cons(S, spot, emlo=None, emhi=None):
    m = lambda k: (lambda v: round(st.median(v), 2) if v else None)([num(s[k]) for s in S if s.get(k)])
    regs = [s["regime"] for s in S if s.get("regime")]
    return {"flip": m("flip"), "call_wall": m("call_wall"), "put_wall": m("put_wall"), "em_lo": emlo, "em_hi": emhi, "spot": spot,
            "regime": (max(set(regs), key=regs.count) if regs else None), "regime_votes": {r: regs.count(r) for r in set(regs)}}
G["symbols"] = [
 {"symbol": "SPY", "sources": spy_src, "consensus": cons(spy_src, round(SPOT, 2), EM.get("lo"), EM.get("hi")), "em_note": EM.get("note", "")},
 {"symbol": "SPX", "sources": spx_src, "consensus": cons(spx_src, round(SPOT * R["SPX"], 1))},
 {"symbol": "QQQ", "sources": qqq_src, "consensus": cons(qqq_src, round(SPOT * R["QQQ"], 2))},
 {"symbol": "NQ", "sources": nq_src, "consensus": cons(nq_src, None)}]
G["disagree_threshold"] = 1.0
(X / "gamma.json").write_text(json.dumps(G, indent=1, ensure_ascii=False))

# ---- scorecard.json: auto-extract SPY levels from week posts, grade on RTH 1m bars
posts = json.loads((X / "week_raw" / "posts.json").read_text()) if (X / "week_raw" / "posts.json").exists() else []
LV = re.compile(r"(?<![\d.])\$?(7[4-9]\d(?:\.\d{1,2})?)(?![\d.,]|\s?(?:[cCpP]\b|calls?|puts?|strike|%|[kKmMbB]\b))")
SKIP = re.compile(r"(opened at|close[d]? (?:at|around)|is at|trading (?:at|around)|right now|finished around|reaching)\s*\$?$", re.I)
def week_levels(h):
    out = []
    for p in posts.get(h, []):
        if p.get("rt") or PROMO.search(p["text"]) or not re.search(r"\$?SPY|S&P|SP500|#SPY", p["text"], re.I): continue
        if re.search(r"\$?SPX|NQ|QQQ", p["text"]) and not re.search(r"SPY", p["text"]): continue
        ts = pd.Timestamp(datetime.strptime("2026-" + p["pt"][4:], "%Y-%m-%d %H:%M"), tz="America/Los_Angeles").tz_convert("America/New_York")
        for m in LV.finditer(p["text"]):
            if SKIP.search(p["text"][max(0, m.start() - 20):m.start()]): continue
            out.append((ts, float(m.group(1)), p["id"]))
    return out
def grade(ts, L):
    days = sorted({d for d in rth.index.date if d >= ts.date()})
    seg = rth[rth.index > ts]
    if ts.time() >= pd.Timestamp("16:00").time() or ts.time() < pd.Timestamp("09:30").time():
        pass
    seg = seg[seg.index.date == (seg.index.date[0] if len(seg) else None)] if len(seg) else seg
    if len(seg) < 5: return None
    prev = float(seg.close.iloc[0])
    hit = seg[(seg.low <= L + 0.25) & (seg.high >= L - 0.25)]
    if not len(hit): return {"touched": False}
    i = seg.index.get_loc(hit.index[0]); side = 1 if float(seg.open.iloc[max(i - 1, 0)]) >= L else -1
    w = seg.iloc[i:i + 30]
    back = (w.high - L).max() if side > 0 else (L - w.low).max()
    thru = ((w.close <= L - 1).any() if side > 0 else (w.close >= L + 1).any())
    first_thru = w.index[(w.close <= L - 1) if side > 0 else (w.close >= L + 1)].min() if thru else None
    first_back = w.index[(w.high >= L + 1) if side > 0 else (w.low <= L - 1)].min() if back >= 1 else None
    resp = first_back is not None and (first_thru is None or first_back < first_thru)
    return {"touched": True, "respected": resp, "broken": (not resp) and thru, "reaction": float(back)}
WR = {"QuantData": 24, "unusual_whales": 48, "Basssem666": 14, "GAndersonTrades": 12, "TraderJonesy": 10, "SRC_PLAN_B": 31, "TradeSniperSara": 4, "FlowbyBobby": 42, "SuperLuckeee": 6, "CheddarFlow": 13, "VoltickIO": 11}
S = []
for h in srcs:
    lv = week_levels(h); seen = set(); g = []
    for ts, L, pid in lv:
        k = (ts.date(), L)
        if k in seen: continue
        seen.add(k); r = grade(ts, L)
        if r: g.append(r)
    t = [x for x in g if x["touched"]]; rs = [x for x in t if x["respected"]]; br = [x for x in t if x["broken"]]
    allp = posts.get(h, []); promo = sum(1 for p in allp if PROMO.search(p["text"]))
    S.append({"handle": h, "levels_posted": len(g), "touched": len(t), "respected": len(rs), "broken": len(br),
              "hit_rate": round(len(rs) / len(t), 3) if t else None, "touch_rate": round(len(t) / len(g), 3) if g else None,
              "avg_reaction_pts": round(st.mean(x["reaction"] for x in t), 2) if t else None,
              "promo_pct": round(100 * promo / len(allp), 1) if allp else None, "posts_per_day": WR.get(h),
              "weight": srcs[h].get("weight"), "greyed": bool(t) and len(rs) / len(t) < 0.4})
S.sort(key=lambda s: (s["hit_rate"] is None, -(s["hit_rate"] or 0)))
SC = {"asof": conf["updated_pt"], "window_days": 5, "bars": "SPY 1m (free feed, RTH 09:30-16:00 ET), read-only local copy",
      "rules": "SPY levels auto-extracted from post text (promos/RTs skipped). Graded on the rest of that RTH session (or next session if posted outside RTH). touch = within $0.25; respected = moves ≥$1 back on the approach side within 30 min before a 1m close ≥$1 through; broken = closes ≥$1 through first. hit_rate = respected/touched.",
      "voltick_self_reported": {"2026-10-19": "Volt touched 577 of 1044 · Inside the expected range 1040 of 1043 · Closed between the walls 785 of 1044", "2026-10-20": "Volt touched 644 of 1070 · Inside the expected range 1058 of 1070 · Closed between the walls 829 of 1070"},
      "sources": S}
(X / "scorecard.json").write_text(json.dumps(SC, indent=1, ensure_ascii=False))
print("ok", {k: len(v) for k, v in conf["symbols"].items()})
