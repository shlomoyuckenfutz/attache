"""ATTACHÉ composite BIAS gauge. Computes a -100..+100 score from every directional read the main + command pages carry.
Usage: python3 bias_gauge.py [--live] [--patch file.html ...]   (writes es_levels/bias_gauge.json + bias_gauge.html)"""
import json, sys, html, re
from datetime import datetime, timedelta, timezone
from pathlib import Path
import pandas as pd
RES = Path(__file__).resolve().parent; XN = RES / "xnews"; ES = RES / "es_levels"
ET = "America/New_York"
def J(p):
    try: return json.loads(Path(p).read_text())
    except Exception: return None
def fnum(s):
    try: return float(re.sub(r"[^\d.\-]", "", str(s).split("–")[0]))
    except Exception: return None

def bars(live):
    d = pd.read_parquet(RES / "python/data/SPY_1m_ext.parquet", columns=["ts", "open", "high", "low", "close", "volume", "vwap"])
    d = d[d.ts >= d.ts.max() - pd.Timedelta(days=5)]
    src = "delayed"
    if live:
        try:
            sys.path.insert(0, str(RES / "python")); import fetch_ext as F
            st = (d.ts.max() - pd.Timedelta(minutes=5)).tz_convert("UTC").strftime("%Y-%m-%dT%H:%M:%SZ")
            en = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
            r = pd.DataFrame(F.pull("SPY", "iex", st, en)).rename(columns={"t": "ts", "o": "open", "h": "high", "l": "low", "c": "close", "v": "volume", "vw": "vwap"})
            if len(r):
                r["ts"] = pd.to_datetime(r.ts, utc=True).dt.tz_convert(ET)
                d = pd.concat([d, r[d.columns]]).drop_duplicates("ts", keep="first").sort_values("ts"); src = "live"
        except Exception as e: print("live pull failed:", str(e)[:120], file=sys.stderr)
    return d.reset_index(drop=True), src

def price_parts(d):
    t = d.ts; last = d.iloc[-1]; px = float(last.close); now = last.ts
    day = now.date(); tm = t.dt.time; T = lambda s: pd.Timestamp(s).time()
    rth_today = d[(t.dt.date == day) & (tm >= T("09:30")) & (tm < T("16:00"))]
    if not len(rth_today):  # premarket / weekend: use the last completed session for ORB, today's pre-market for VWAP
        sess = d[(t.dt.date == day) & (tm >= T("04:00"))]
    else: sess = rth_today
    if not len(sess): sess = d[t.dt.date == day]
    v = []
    # 1 VWAP
    vw = float((sess.vwap * sess.volume).sum() / max(sess.volume.sum(), 1)) if len(sess) else None
    v.append(("VWAP", "price vs session VWAP", (1 if px > vw * 1.0002 else -1 if px < vw * 0.9998 else 0) if vw else 0, f"{px:.2f} vs {vw:.2f}" if vw else "n/a", 1.5))
    # 2 EMA 9/21 on 5m (last 3 days, all sessions)
    c5 = d.set_index("ts").close.resample("5min").last().dropna()
    e9, e21 = c5.ewm(span=9, adjust=False).mean(), c5.ewm(span=21, adjust=False).mean()
    sl = e9.iloc[-1] - e9.iloc[-4]
    ev = 1 if e9.iloc[-1] > e21.iloc[-1] and sl >= 0 else -1 if e9.iloc[-1] < e21.iloc[-1] and sl <= 0 else 0
    v.append(("EMA", "9 vs 21 EMA on 5m + slope", ev, f"9={e9.iloc[-1]:.2f} 21={e21.iloc[-1]:.2f}", 1.0))
    # 3 ORB15
    orb = rth_today[(rth_today.ts.dt.time < T("09:45"))]
    set_ = len(rth_today) and rth_today.ts.max().time() >= T("09:45") and len(orb)
    ow = 1.5; ov = 0; ot = "range not set"
    if set_:
        hi, lo = float(orb.high.max()), float(orb.low.min())
        after = rth_today[rth_today.ts.dt.time >= T("09:45")].set_index("ts").close.resample("5min").last().dropna()
        brk = 1 if (after > hi).any() and px > hi else -1 if (after < lo).any() and px < lo else 0
        ov = 1 if px > hi else -1 if px < lo else 0
        ot = f"{'ABOVE HIGH' if ov > 0 else 'BELOW LOW' if ov < 0 else 'INSIDE'} {lo:.2f}–{hi:.2f}"
        if brk and now.time() < T("16:00"): ow = 4.5; ot += " · confirmed break (×3)"
    v.append(("ORB15", "price vs today's 15-min opening range", ov, ot, ow))
    # 4 overnight / premarket range (prior 16:00 ET -> 09:30 ET today)
    prev = d[(t < pd.Timestamp(day, tz=ET) + pd.Timedelta(hours=9.5)) & (t >= pd.Timestamp(day, tz=ET) - pd.Timedelta(hours=8))]
    if len(prev):
        h, l = float(prev.high.max()), float(prev.low.min())
        onv = 1 if px > h else -1 if px < l else 0
        v.append(("ON RANGE", "price vs overnight / pre-market high-low", onv, f"{l:.2f}–{h:.2f}", 1.0))
    return px, now, v

def thirds(px, lo, hi):
    if lo is None or hi is None or hi <= lo: return 0
    q = (px - lo) / (hi - lo); return 1 if q > 2 / 3 else -1 if q < 1 / 3 else 0

def desk_parts(px):
    v = []; G = J(XN / "gamma.json") or {}
    cons = {s["symbol"]: s.get("consensus") or {} for s in G.get("symbols", [])}
    qqq = None
    try: qqq = float(pd.read_parquet(RES / "equity_orb15/data/QQQ_1m.parquet", columns=["close"]).close.iloc[-1])
    except Exception: qqq = ((J(XN / "confluence.json") or {}).get("spot") or {}).get("QQQ")
    try: import desk_bands as _db; DB = _db.load()
    except Exception: DB = {"gex": {}, "press": {}}
    dbf = lambda t: (((DB.get("gex") or {}).get(t) or {}).get("all") or {}).get("flip")
    fl = fnum(cons.get("SPY", {}).get("flip"))
    if fl: v.append(("GAMMA FLIP", "SPY price vs gamma flip consensus", 1 if px > fl else -1, f"{px:.2f} vs flip {fl}", 1.5))
    elif dbf("SPY"): fl = dbf("SPY"); v.append(("GAMMA FLIP", "SPY price vs desk gamma flip (all exp; no consensus)", 1 if px > fl else -1, f"{px:.2f} vs flip {fl}", 1.0))
    fq = fnum(cons.get("QQQ", {}).get("flip")); qs = "flip"
    if not fq and dbf("QQQ"): fq = dbf("QQQ"); qs = "desk gamma flip (all exp)"
    if not qqq: qqq = ((DB.get("gex") or {}).get("QQQ") or {}).get("spot")
    if fq and qqq: v.append(("FB · QQQ", f"QQQ price vs {qs}", 1 if qqq > fq else -1, f"{qqq:.2f} vs {fq}", 1.0 if qs == "flip" else 0.75))
    dl = (((DB.get("press") or {}).get("SPY") or {}).get("g") or {}).get("delta_lean")
    if dl is not None: v.append(("DEALER DELTA", "SPY dealer-pressure delta lean (−1…+1; ±0.10 dead zone)", 1 if dl >= 0.1 else -1 if dl <= -0.1 else 0, f"{dl:+.2f}", 0.75))
    fx = fnum(cons.get("SPX", {}).get("flip")); spx = ((J(XN / "confluence.json") or {}).get("spot") or {}).get("SPX")
    if fx and spx: v.append(("FB · SPX", "SPX price vs flip", 1 if spx > fx else -1, f"{spx} vs {fx}", 1.0))
    import first_blade as _fb; sp = _fb.load() or {}
    if sp.get("pivot"):
        pv = float(sp["pivot"]); b = str(sp.get("bias", "")).lower()
        x = 1 if px > pv else -1
        v.append(("FB · SPY", "price vs First Blade pivot", x, f"{px:.2f} vs pivot {pv}", 1.0))
        tb = 1 if "bull" in b and "bear" not in b else -1 if "bear" in b and "bull" not in b else 0
        v.append(("FB · LEAN", "First Blade stated lean", tb, "bullish" if tb > 0 else "bearish" if tb < 0 else "neutral", 0.5))
    esp = (J(ES / "summary.json") or {}).get("price")
    M = (J(XN / "mancini/levels_a.json") or {}).get("latest") or {}
    if esp:
        lv = sorted(set((M.get("supports") or []) + (M.get("resistances") or [])))
        near_s = [x for x in (M.get("supports") or []) if x <= esp]; near_r = [x for x in (M.get("resistances") or []) if x >= esp]
        if lv:
            s, r = (max(near_s) if near_s else None), (min(near_r) if near_r else None)
            x = 1 if r is None else -1 if s is None else thirds(esp, s, r)
            v.append(("IRON LADDER", "/ES vs nearest key support/resistance", x, f"ES {esp} · S {s} / R {r}", 1.0))
    dp = (J(ES / "darkpool_levels.json") or {}).get("levels") or []
    if dp:
        below = sum(1 for x in dp if px * 0.99 <= x < px); above = sum(1 for x in dp if px < x <= px * 1.01)
        x = 1 if below > above + 1 else -1 if above > below + 1 else 0
        v.append(("DARK POOL", "dark-pool levels holding below vs overhead (±1%)", x, f"{below} below / {above} above", 1.5))
    C = ((J(XN / "confluence.json") or {}).get("symbols") or {}).get("SPY") or []
    if C:
        b = sum(z["n_sources"] for z in C if px * 0.99 <= z["price"] < px); a = sum(z["n_sources"] for z in C if px < z["price"] <= px * 1.01)
        x = 1 if b > a * 1.3 else -1 if a > b * 1.3 else 0
        v.append(("GAUNTLET", "confluence weight below vs above (±1%)", x, f"{b} below / {a} above", 1.0))
    im = (((J(XN / "implied_move/implied_move.json") or {}).get("symbols") or {}).get("SPY") or {}).get("daily") or {}
    if im.get("upper"):
        v.append(("BLAST RADIUS", "position inside daily implied-move band (thirds)", thirds(px, im["lower"], im["upper"]), f"{im['lower']}–{im['upper']}", 1.0))
    F = J(XN / "flow/flow.json") or {}; cp = {"C": 0.0, "P": 0.0}
    cut = (datetime.now() - timedelta(days=2)).strftime("%Y-%m-%d")
    for e in F.get("entries", []):
        if str(e.get("posted_at_pt", "")) < cut: continue
        for r in e.get("rows", []):
            k = str(r.get("cp", "")).upper()[:1]; p = fnum(r.get("premium"))
            if k in cp and p and r.get("ticker") in ("SPY", "QQQ", "SPX", "SPXW", "ES"): cp[k] += p
    if cp["C"] + cp["P"] > 0:
        rt = (cp["C"] + 1) / (cp["P"] + 1); x = 1 if rt > 1.25 else -1 if rt < 0.8 else 0
        v.append(("RIPTIDE", "index options flow call vs put premium (2d)", x, f"C/P {rt:.2f}", 1.0))
    else: v.append(("RIPTIDE", "index options flow call vs put premium (2d)", 0, "no recent prints", 1.0))
    P = J(XN / "plan.json") or {}; dr = ((P.get("bias") or {}).get("direction") or "").upper()
    v.append(("NEWS", "news-plan bias", 1 if dr in ("LONG", "BULLISH") else -1 if dr in ("SHORT", "BEARISH") else 0, dr or "n/a", 1.0))
    return v, P

def compute(live=False):
    d, src = bars(live); px, now, pp = price_parts(d); dp, P = desk_parts(px)
    allv = pp + dp; W = sum(x[4] for x in allv); raw = sum(x[2] * x[4] for x in allv)
    sc = round(100 * raw / W) if W else 0
    lab = "BULLISH" if sc >= 25 else "BEARISH" if sc <= -25 else "NEUTRAL"
    pt = now.tz_convert("America/Los_Angeles")
    news = (P.get("bias") or {})
    return {"score": sc, "label": lab, "px": round(px, 2), "asof": pt.strftime("%m-%d %H:%M PT"), "feed": src,
            "built": datetime.now().strftime("%m-%d %H:%M PT"),
            "votes": [{"k": k, "d": dsc, "v": vv, "x": det, "w": w} for k, dsc, vv, det, w in allv],
            "news": {"dir": news.get("direction") or "NEUTRAL", "why": news.get("reason") or ""}}

def render(g):
    e = lambda s: html.escape(str(s))
    col = {"BULLISH": "#3ddc5c", "BEARISH": "#ff3b3b"}.get(g["label"], "#ffb000")
    pos = (g["score"] + 100) / 2
    chip = lambda z: f'<span class="bg-c {"u" if z["v"] > 0 else "d" if z["v"] < 0 else "n"}" title="{e(z["d"])}: {e(z["x"])} · weight {z["w"]:g}">{e(z["k"])} {"▲" if z["v"] > 0 else "▼" if z["v"] < 0 else "■"}</span>'
    rows = "".join(f'<tr><td>{e(z["k"])}</td><td>{e(z["d"])}</td><td class="r">{z["w"]:g}</td></tr>' for z in g["votes"])
    nb = sum(z["v"] > 0 for z in g["votes"]); ns = sum(z["v"] < 0 for z in g["votes"])
    return f'''<!--GAUGE--><style>
#biasG{{background:#000;border:1px solid #333;border-left:4px solid {col};font-family:ui-monospace,Menlo,Consolas,monospace;color:#ffb000;padding:8px 12px;margin:8px 0;font-size:12px}}
#biasG .bg-h{{display:flex;gap:14px;align-items:center;flex-wrap:wrap}}#biasG .bg-l{{font-size:22px;font-weight:700;color:#000;background:{col};padding:0 10px;letter-spacing:2px}}
#biasG .bg-s{{font-size:20px;color:{col};font-weight:700}}#biasG small{{color:#888}}
#biasG .bg-m{{position:relative;height:16px;margin:10px 0 16px;background:linear-gradient(90deg,#ff3b3b 0,#5a1414 37.5%,#3a3000 37.5%,#3a3000 62.5%,#145a1e 62.5%,#3ddc5c 100%);border:1px solid #444}}
#biasG .bg-n{{position:absolute;top:-5px;width:3px;height:26px;background:#fff;box-shadow:0 0 6px #fff;left:calc({pos:.1f}% - 1px)}}
#biasG .bg-t{{position:absolute;top:17px;font-size:10px;color:#888;transform:translateX(-50%)}}
#biasG .bg-c{{display:inline-block;margin:2px 4px 2px 0;padding:0 5px;border:1px solid #444}}#biasG .bg-c.u{{color:#3ddc5c;border-color:#1d6b2c}}#biasG .bg-c.d{{color:#ff3b3b;border-color:#7a1d1d}}#biasG .bg-c.n{{color:#888}}
#biasG .bg-nw{{color:#aaa;margin-top:4px}}#biasG .bg-nw b{{color:#ffb000}}#biasG details{{margin-top:4px;color:#aaa}}#biasG summary{{cursor:pointer;color:#888}}#biasG table{{border-collapse:collapse;margin-top:4px}}#biasG td{{padding:1px 8px 1px 0;border-bottom:1px solid #222}}#biasG .r{{text-align:right}}
</style><div id="biasG"><div class="bg-h"><b style="letter-spacing:2px">BIAS · SPY COMPOSITE</b><span class="bg-l">{g["label"]}</span><span class="bg-s">{g["score"]:+d}</span><small>/ ±100 · {nb} bull · {ns} bear · {len(g["votes"])-nb-ns} flat · SPY {g["px"]} · as of {e(g["asof"])}{" (delayed)" if g["feed"]!="live" else ""} · built {e(g["built"])}</small></div>
<div class="bg-m"><i class="bg-n"></i><span class="bg-t" style="left:0;transform:none">-100 BEARISH</span><span class="bg-t" style="left:37.5%">-25</span><span class="bg-t" style="left:50%">NEUTRAL</span><span class="bg-t" style="left:62.5%">+25</span><span class="bg-t" style="left:100%;transform:translateX(-100%)">BULLISH +100</span></div>
<div>{"".join(chip(z) for z in g["votes"])}</div>
<div class="bg-nw">NEWS <b>{e(g["news"]["dir"])}</b> {e(g["news"]["why"])}</div>
<details><summary>NOTES · weights &amp; method</summary>Each input votes +1 / 0 / -1; score = 100 × Σ(vote × weight) / Σ(weight). ≥ +25 BULLISH, ≤ -25 BEARISH, else NEUTRAL. After 9:45 ET (6:45 PT) a confirmed 5-min close beyond the 15-min opening range triples the ORB15 weight (1.5 → 4.5) so a break can flip a mixed gauge on its own. Desk gamma/pressure inputs (kept modest): GAMMA FLIP falls back to the desk SPY all-expiration flip at weight 1.0 (1.5 when a consensus flip exists); FB · QQQ uses the desk QQQ all-expiration flip at weight 0.75 when no consensus flip exists; DEALER DELTA votes the SPY dealer delta lean (≥ +0.10 bull, ≤ −0.10 bear, else flat) at weight 0.75. Hover a chip for its reading.<table>{rows}</table></details></div><!--/GAUGE-->'''

if __name__ == "__main__":
    g = compute("--live" in sys.argv); h = render(g)
    (ES / "bias_gauge.json").write_text(json.dumps(g, indent=1)); (ES / "bias_gauge.html").write_text(h)
    if "--patch" in sys.argv:
        for f in sys.argv[sys.argv.index("--patch") + 1:]:
            s = Path(f).read_text(); n = re.sub(r"<!--GAUGE-->.*?<!--/GAUGE-->", lambda m: h, s, flags=re.S)
            Path(f).write_text(n); print("patched", f, n != s)
    print(g["label"], g["score"], g["asof"], g["feed"])
