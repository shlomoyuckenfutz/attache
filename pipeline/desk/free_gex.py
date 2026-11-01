"""FREE GEX compute: pulls public delayed option chains (greeks + OI, no key, no cost) for SPY/QQQ/SPX,
computes per-strike dealer GEX (call +, put -, gamma*OI*100*spot^2*0.01), zero-gamma flip (BS re-gamma over a spot grid),
call/put walls, magnets, expected-move bands, premium tape + dealer-pressure gauges. Writes es_levels/free_gex/latest.json.
On any failure the previous latest.json is kept (desk_bands then shows it with a STALE tag). Places no orders."""
import time, json, math, re, sys, urllib.request
from datetime import datetime, date, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo
RES = Path(__file__).resolve().parent; OUT = RES / "es_levels" / "free_gex"; OUT.mkdir(parents=True, exist_ok=True)
PT, ET = ZoneInfo("America/Los_Angeles"), ZoneInfo("America/New_York")
URL = "https://cdn.cboe.com/api/global/delayed_quotes/options/{}.json"
SYM = {"SPY": "SPY", "QQQ": "QQQ", "SPX": "_SPX"}
RX = re.compile(r"^([A-Z]+)(\d{6})([CP])(\d{8})$")

def fetch(t):
    # sweep 2026-10-25: was one 45s try per symbol, run serially (3x45s > the 120s publish timeout, so 10/23 runs were killed
    # before writing anything). Now 2 tries x 20s, and symbols fetch in parallel (see main).
    last = None
    for i in range(2):
        try:
            r = urllib.request.Request(URL.format(SYM[t]), headers={"User-Agent": "Mozilla/5.0"})
            return json.loads(urllib.request.urlopen(r, timeout=20).read())
        except Exception as ex:
            last = ex; time.sleep(2)
    raise last
def third_friday(y, m):
    d = date(y, m, 15); return d + timedelta((4 - d.weekday()) % 7)
def next_monthly(d):
    tf = third_friday(d.year, d.month)
    if tf >= d: return tf
    y, m = (d.year + 1, 1) if d.month == 12 else (d.year, d.month + 1); return third_friday(y, m)
def bs_gamma(S, K, T, iv):
    if iv <= 0 or T <= 0: return 0.0
    d1 = (math.log(S / K) + 0.5 * iv * iv * T) / (iv * math.sqrt(T)); return math.exp(-d1 * d1 / 2) / (math.sqrt(2 * math.pi) * S * iv * math.sqrt(T))
def fm(v):
    a = abs(v); s = "-" if v < 0 else "+"
    for u, k in ((1e9, "B"), (1e6, "M"), (1e3, "K")):
        if a >= u: return f"{s}${a/u:.1f}{k}"
    return f"{s}${a:.0f}"

def compute(t, now):
    raw = fetch(t); d = raw["data"]; S = float(d["current_price"]); today = now.astimezone(ET).date()
    close_et = datetime.combine(today, datetime.min.time(), ET).replace(hour=16)
    rows = []
    for o in d["options"]:
        m = RX.match(o["option"])
        if not m: continue
        ex = datetime.strptime(m.group(2), "%y%m%d").date()
        if ex < today: continue
        if t == "SPX" and m.group(1) == "SPX" and ex.weekday() == 4: pass  # AM-settled monthly; kept (same strikes)
        rows.append(dict(ex=ex, cp=m.group(3), K=int(m.group(4)) / 1000, oi=float(o.get("open_interest") or 0), g=float(o.get("gamma") or 0),
                         iv=float(o.get("iv") or 0), vol=float(o.get("volume") or 0), dl=float(o.get("delta") or 0), vg=float(o.get("vega") or 0),
                         mid=((o.get("bid") or 0) + (o.get("ask") or 0)) / 2 or float(o.get("last_trade_price") or 0), ch=float(o.get("change") or 0)))
    exps = sorted({r["ex"] for r in rows}); e0 = exps[0]; mon = next_monthly(today)
    fri = today + timedelta((4 - today.weekday()) % 7)
    near = [x for x in exps if x <= max(mon, fri)]
    def T(ex):
        c = datetime.combine(ex, datetime.min.time(), ET).replace(hour=16); return max((c - now).total_seconds(), 1800) / (365 * 86400)
    def level(sel, lab):
        R = [r for r in rows if r["ex"] in sel and r["oi"] > 0]; by = {}; cg = {}; pg = {}
        for r in R:
            v = r["g"] * r["oi"] * 100 * S * S * 0.01 * (1 if r["cp"] == "C" else -1)
            by[r["K"]] = by.get(r["K"], 0) + v
            (cg if r["cp"] == "C" else pg)[r["K"]] = (cg if r["cp"] == "C" else pg).get(r["K"], 0) + v
        net = sum(by.values()); band = {k: v for k, v in by.items() if 0.9 * S <= k <= 1.1 * S}
        def prof(x):
            return sum(bs_gamma(x, r["K"], T(r["ex"]), r["iv"]) * r["oi"] * 100 * x * x * 0.01 * (1 if r["cp"] == "C" else -1) for r in R if r["iv"] > 0 and 0.8 * S <= r["K"] <= 1.2 * S)
        grid = [S * (0.95 + i * 0.0025) for i in range(41)]; pv = [prof(x) for x in grid]; flips = []
        for i in range(40):
            if pv[i] == 0 or (pv[i] < 0) != (pv[i + 1] < 0):
                a, b = grid[i], grid[i + 1]; fa = pv[i]
                for _ in range(18):
                    mid = (a + b) / 2; fmv = prof(mid)
                    if (fmv < 0) == (fa < 0): a, fa = mid, fmv
                    else: b = mid
                flips.append((a + b) / 2)
        flip = min(flips, key=lambda x: abs(x - S)) if flips else None
        nb = lambda dct: {k: v for k, v in dct.items() if 0.9 * S <= k <= 1.1 * S}
        cw = max(nb(cg).items(), key=lambda kv: kv[1])[0] if nb(cg) else None
        pw = min(nb(pg).items(), key=lambda kv: kv[1])[0] if nb(pg) else None
        mag = max(band.items(), key=lambda kv: abs(kv[1]))[0] if band else None
        pos = sorted([kv for kv in band.items() if kv[1] > 0], key=lambda kv: -kv[1])[:5]
        neg = sorted([kv for kv in band.items() if kv[1] < 0], key=lambda kv: kv[1])[:5]
        prof_at = pv[20]
        return {"label": lab, "net": net, "net_gex": fm(net), "regime": "POS" if prof_at >= 0 else "NEG", "flip": round(flip, 2) if flip else None,
                "call_wall": cw, "put_wall": pw, "magnet": mag, "pos": [(k, fm(v)) for k, v in pos], "neg": [(k, fm(v)) for k, v in neg],
                "exps": [x.isoformat() for x in sorted(sel)]}
    zero = level([e0], "0DTE" if e0 == today else e0.strftime("%m/%d")); allx = level(near, "NEAR")
    allx["front_magnet"] = zero["magnet"]
    def straddle(ex):
        R = [r for r in rows if r["ex"] == ex]; ks = sorted({r["K"] for r in R}, key=lambda k: abs(k - S))
        for k in ks[:3]:
            c = [r for r in R if r["K"] == k and r["cp"] == "C"]; p = [r for r in R if r["K"] == k and r["cp"] == "P"]
            if c and p and c[0]["mid"] > 0 and p[0]["mid"] > 0:
                mv = (c[0]["mid"] + p[0]["mid"]) * 0.85; return {"to": ex.strftime("%m/%d"), "pct": round(100 * mv / S, 2), "low": round(S - mv, 2), "high": round(S + mv, 2), "mv": round(mv, 2), "iv": c[0]["iv"]}
        return None
    dayx = [x for x in exps if x >= today][0]; wk = [x for x in exps if x >= fri][0]
    em_d, em_w = straddle(dayx), straddle(wk)
    # premium tape (session volume x mid x 100) + dealer pressure from OI greeks, 0DTE + near
    R = [r for r in rows if r["ex"] in near]
    cp = sum(r["vol"] * r["mid"] * 100 for r in R if r["cp"] == "C"); pp = sum(r["vol"] * r["mid"] * 100 for r in R if r["cp"] == "P")
    bull = sum(r["vol"] * r["mid"] * 100 for r in R if (r["cp"] == "C") == (r["ch"] >= 0)); bear = cp + pp - bull
    netp = bull - bear; lean = "leaning bullish" if netp > 0.05 * (cp + pp) else "leaning bearish" if netp < -0.05 * (cp + pp) else "two-sided"
    big = sorted(R, key=lambda r: -r["vol"] * r["mid"])[:6]
    bigrows = [["", fx(r["K"]), r["ex"].strftime("%m/%d"), "CALL" if r["cp"] == "C" else "PUT", ("bid up" if r["ch"] >= 0 else "offered") + f" · {int(r['vol']):,} ct", fm(r["vol"] * r["mid"] * 100).lstrip("+")] for r in big]
    tot = lambda f_: sum(f_(r) for r in R if r["oi"] > 0)
    dg = tot(lambda r: r["dl"] * r["oi"]) ; dga = tot(lambda r: abs(r["dl"]) * r["oi"]) or 1
    vgc = tot(lambda r: r["vg"] * r["oi"] * (1 if r["cp"] == "C" else -1)); vga = tot(lambda r: r["vg"] * r["oi"]) or 1
    gsum = sum(abs(v) for v in [allx["net"]]); gabs = tot(lambda r: abs(r["g"]) * r["oi"] * 100 * S * S * 0.01) or 1
    g0 = sum(r["g"] * r["oi"] * (1 if r["cp"] == "C" else -1) for r in rows if r["ex"] == e0); g0a = sum(r["g"] * r["oi"] for r in rows if r["ex"] == e0) or 1
    volk = {}
    for r in R: volk[(r["K"], r["cp"])] = volk.get((r["K"], r["cp"]), 0) + r["vol"] - 0 * r["oi"]
    act = sorted(volk.items(), key=lambda kv: -kv[1])[:3]
    rel = sorted(((k, sum(r["vol"] for r in R if (r["K"], r["cp"]) == k) / max(1, sum(r["oi"] for r in R if (r["K"], r["cp"]) == k))) for k in volk if volk[k] > 500), key=lambda kv: -kv[1])
    press = {"gamma_speed": round(allx["net"] / gabs, 2), "vega_range": round(vgc / vga, 2), "delta_lean": round(dg / dga, 2),
             "charm_clock": round(g0 / g0a, 2), "vanna_vol_shift": round(-(d.get("iv30_change") or 0) / max(1, d.get("iv30") or 1) * 5, 2)}
    flow = {"net": fm(netp) + (" bullish" if netp > 0 else " bearish"), "netv": netp, "calls": fm(cp).lstrip("+"), "puts": fm(pp).lstrip("+"),
            "pc": round(pp / cp, 2) if cp else None, "lean": lean, "prints": int(sum(r["vol"] for r in R)), "swept": None, "big": bigrows}
    pr = {"g": {k: max(-1, min(1, v)) for k, v in press.items()},
          "build": ", ".join(f"{fx(k[0])}{k[1]}" for k, _ in rel[:3]), "fade": ", ".join(f"{fx(k[0])}{k[1]}" for k, _ in act[:3])}
    flip = allx["flip"]; read = "BULLISH" if (flip and S > flip and netp >= 0) else "BEARISH" if (flip and S < flip and netp <= 0) else "NEUTRAL"
    return {"spot": S, "chg": f"{d.get('price_change',0):+.2f} ({d.get('price_change_percent',0):+.2f}%)", "src_ts_utc": raw.get("timestamp"),
            "zero": zero, "all": allx, "em": {"px": S, "read": read, "day": em_d, "week": em_w}, "flow": flow, "press": pr, "_cp": cp, "_pp": pp, "_net": netp}
def fx(v): return f"{v:g}"

def main():
    now = datetime.now(timezone.utc); out = {"ok": {}, "err": {}}
    prev = {}
    try: prev = json.loads((OUT / "latest.json").read_text())
    except Exception: pass
    from concurrent.futures import ThreadPoolExecutor
    with ThreadPoolExecutor(len(SYM)) as ex_:
        fut = {t: ex_.submit(compute, t, now) for t in SYM}
    for t in SYM:
        try: out["ok"][t] = fut[t].result()
        except Exception as ex:
            out["err"][t] = str(ex)[:200]
            if t in (prev.get("tick") or {}): out["ok"][t] = dict(prev["tick"][t], stale=True)
    if not out["ok"]: print("free_gex: no data", out["err"], file=sys.stderr); return 1
    c = json.loads((RES / "es_levels/es_conversions.json").read_text()); f = c["factors"]["spy_per_es"]; esp = (c.get("prices") or {}).get("ES=F")
    spy = out["ok"].get("SPY", {}).get("spot"); spx = out["ok"].get("SPX", {}).get("spot")
    ratio = (spy / esp) if (spy and esp) else f
    ts = [v.get("src_ts_utc") for v in out["ok"].values() if v.get("src_ts_utc") and not v.get("stale")]
    src = datetime.strptime(max(ts), "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc).astimezone(PT) if ts else None
    res = {"as_of_pt": src.strftime("%Y-%m-%d %H:%M") if src else (prev.get("as_of_pt")), "run_pt": now.astimezone(PT).strftime("%Y-%m-%d %H:%M"),
           "spy_per_es": ratio, "es_ref": esp, "spx_basis": round(esp - spx, 2) if (esp and spx) else None, "tick": out["ok"], "err": out["err"],
           "stale": bool(out["err"]) or not ts}
    tmp = OUT / "latest.tmp"; tmp.write_text(json.dumps(res, default=str)); tmp.replace(OUT / "latest.json")
    print("free_gex ok", res["as_of_pt"], {t: (v["all"]["flip"], v["all"]["call_wall"], v["all"]["put_wall"]) for t, v in out["ok"].items()}, out["err"]); return 0
if __name__ == "__main__": sys.exit(main())
