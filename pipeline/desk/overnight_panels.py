#!/usr/bin/env python3
"""ATTACHÉ OVERNIGHT detail panels (HTML fragment + CSS) for build_overnight.py.
Reads es_levels/overnight.json (cross-asset board), es_levels/overnight_details.json, xnews/ledger/ledger.json. No source names."""
import json, re
from pathlib import Path
from html import escape as e
R = Path(__file__).resolve().parent
def L(p):
    try: return json.loads((R / p).read_text())
    except Exception: return {}
def f(v, d=2): return "—" if v is None else f"{v:,.{d}f}"
def sg(v, d=2): return "—" if v is None else ("+" if v > 0 else "") + f"{v:,.{d}f}"
def cls(v): return "up" if v and v > 0 else "dn" if v and v < 0 else "fl"
CSS = """main{max-width:1400px}h2{font-size:12px;font-weight:700;letter-spacing:2px;margin:10px 0 4px;color:var(--amb)}
.dp{border:1px solid var(--ln2);background:#070707;padding:6px 8px;color:var(--txt);min-width:0;overflow-x:auto}.dp.sec{margin-bottom:8px}
.dgrid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:8px;margin-bottom:8px;align-items:stretch}.dgrid .full{grid-column:1/-1}
@media(max-width:900px){.dgrid{grid-template-columns:minmax(0,1fr)}.strip{grid-template-columns:minmax(0,1fr)!important}}
.strip{grid-template-columns:repeat(2,minmax(0,1fr));gap:8px;margin-bottom:0}.sc{background:#000}
.dp h3,.sub{font-size:11px;font-weight:700;letter-spacing:2px;margin:0 0 4px;padding-bottom:2px;color:var(--amb);border-bottom:1px solid var(--amb2)}.sub{margin:8px 0 2px;color:var(--mut);border-bottom:1px solid var(--ln)}
.dp table td,.dp table th{padding:2px 6px;font-size:12px}.dp th{font-weight:600}.dp td.n,.dp th.n{text-align:right;font-variant-numeric:tabular-nums}.dp .m{font-size:11px}
.dp table td:first-child{width:1%}.dp td.c{width:52px}
.tg{font-size:10px;padding:0 4px;font-weight:700;color:#000;white-space:nowrap}.tg.in{background:var(--mut)}.tg.out{background:var(--amb)}.tg.e{background:var(--cy)}.tg.on{background:var(--up)}.tg.off{background:var(--dn)}
.rbar{position:relative;height:16px;border:1px solid var(--ln2);background:linear-gradient(90deg,#3a0d0d,#111 50%,#0d3a16);margin:4px 0}.rbar i{position:absolute;top:-3px;width:3px;height:20px;background:var(--amb)}.rbar b{position:absolute;left:50%;top:0;height:14px;width:1px;background:var(--ln2)}
details.nt summary{cursor:pointer;color:var(--mut);font-size:11px}details.nt{margin-top:4px}.q{color:var(--txt);margin:2px 0;white-space:normal}.q i{font-style:normal;color:var(--amb);display:inline-block;width:110px}
.dp .q,.dp div.m{white-space:normal}.dp td.wr{white-space:normal}"""
def on_panel(D):
    on = D.get("on") or {}
    def col(k):
        s = on.get(k)
        if not s: return f'<td colspan="1" class="m">N/A</td>'
        return s
    rows = [("ON HIGH", "on_hi"), ("ON LOW", "on_lo"), ("ON MIDPOINT", "on_mid"), ("LAST", "last"), ("PRIOR RTH CLOSE", "rth_close"), ("PRIOR RTH HIGH", "rth_hi"), ("PRIOR RTH LOW", "rth_lo")]
    h = ['<tr><th>FIELD</th><th class="n">/ES</th><th class="n">/NQ</th></tr>']
    for lab, k in rows: h.append(f'<tr><td>{lab}</td>' + "".join(f'<td class="n{" b" if k=="last" else ""}">{f((on.get(c) or {}).get(k))}</td>' for c in ("ES", "NQ")) + '</tr>')
    def cell(c, fn):
        s = on.get(c); return f'<td class="n">{fn(s) if s else "—"}</td>'
    h.append('<tr><td>GAP vs PRIOR CLOSE</td>' + "".join(cell(c, lambda s: f'<span class="{cls(s["gap"])}">{sg(s["gap"])} pts · {sg(s["gap_pct"])}%</span>') for c in ("ES", "NQ")) + '</tr>')
    h.append('<tr><td>ON vs PRIOR RANGE</td>' + "".join(cell(c, lambda s: f'<span class="tg {"in" if s["pos"]=="INSIDE" else "out"}">{e(s["pos"])}</span>') for c in ("ES", "NQ")) + '</tr>')
    h.append('<tr><td>ON VOLUME vs 10-SESS AVG</td>' + "".join(cell(c, lambda s: f'{s["on_vol"]:,} / {s["avg_vol"]:,} · <b>{f(s["vol_ratio"])}x</b>' if s.get("vol_ratio") else "N/A") for c in ("ES", "NQ")) + '</tr>')
    h.append('<tr><td>ON RANGE vs 10-DAY ON AVG</td>' + "".join(cell(c, lambda s: f'{f(s["on_range"])} / {f(s["avg_range"])} · <b>{f(s["range_pct"],1)}%</b>' if s.get("range_pct") else "N/A") for c in ("ES", "NQ")) + '</tr>')
    s = on.get("ES") or on.get("NQ") or {}
    return (f'<div class="dp"><h3>OVERNIGHT LEVELS</h3><table>{"".join(h)}</table><div class="m">ON = Globex from {e(s.get("sess_start","—"))} ET, as of {e(s.get("asof","—"))} ET ({s.get("elapsed_h","—")}h in). '
            f'Prior RTH {e(s.get("rth_date","—"))} 09:30-16:00 ET on the continuous front month. Volume avg = same elapsed window of the prior {s.get("n_hist","—")} ON sessions; range avg = full 18:00-09:30 ON range.</div></div>')
W = [("ES", "S&P fut", 2, 1), ("NQ", "Nasdaq fut", 2, 1), ("VIX", "VIX", 2, -1), ("DX", "DXY", 1, -1), ("GC", "Gold", 1, -1), ("6J", "JPY fut", 1, -1), ("10Y", "10Y yield", 1, -1), ("BTC", "Bitcoin", 1, 1)]
def curve_panel(D, B):
    Y = D.get("yields") or {}
    def sp(a, b):
        A, Bq = Y.get(a), Y.get(b)
        if not A or not Bq: return None, None
        return (A["last"] - Bq["last"]) * 100, ((A["last"] - Bq["last"]) - (A["prev"] - Bq["prev"])) * 100
    yr = "".join(f'<tr><td>{k}</td><td class="n b">{f((Y.get(k) or {}).get("last"),3)}%</td><td class="n {cls(((Y.get(k) or {}).get("last") or 0)-((Y.get(k) or {}).get("prev") or 0))}">'
                 f'{sg(((Y[k]["last"]-Y[k]["prev"])*100) if Y.get(k) else None,1)} bp</td><td class="m">{e((Y.get(k) or {}).get("asof","N/A"))}{" · PROXY" if (Y.get(k) or {}).get("proxy") else ""}</td></tr>' for k in ("3M", "2Y", "5Y", "10Y", "30Y"))
    s1, d1 = sp("10Y", "2Y"); s2, d2 = sp("10Y", "3M")
    spr = (f'<tr><td>2s10s</td><td class="n b {cls(s1)}">{sg(s1,1)} bp</td><td class="n {cls(d1)}">{sg(d1,1)} bp</td><td class="m">{"inverted" if s1 is not None and s1 < 0 else "positive"}</td></tr>'
           f'<tr><td>3m10y</td><td class="n b {cls(s2)}">{sg(s2,1)} bp</td><td class="n {cls(d2)}">{sg(d2,1)} bp</td><td class="m">{"inverted" if s2 is not None and s2 < 0 else "positive"}</td></tr>')
    pct = {}
    for g in B.get("groups", []):
        for r in g["rows"]:
            if r.get("q") and r["q"].get("pct") is not None: pct[r["code"]] = r["q"]["pct"]
    t = Y.get("10Y")
    if t: pct["10Y"] = (t["last"] / t["prev"] - 1) * 100
    tot = sc = 0; vr = []
    for c, n, w, sign in W:
        p = pct.get(c)
        v = 0 if p is None or abs(p) < 0.05 else (1 if p > 0 else -1) * sign
        if p is not None: tot += w; sc += w * v
        vr.append(f'<tr><td>{n}</td><td class="n {cls(p)}">{sg(p)}%</td><td class="n">{w}</td><td><span class="tg {"on" if v>0 else "off" if v<0 else "in"}">{"RISK-ON" if v>0 else "RISK-OFF" if v<0 else "NEUTRAL" if p is not None else "N/A"}</span></td></tr>')
    score = 100 * sc / tot if tot else 0; lab = "RISK-ON" if score >= 20 else "RISK-OFF" if score <= -20 else "MIXED"
    notes = ("Each input votes +1 (risk-on), -1 (risk-off) or 0 (|move| under 0.05%) from its % change vs prior close, times its weight. "
             "Score = weighted sum / total weight × 100. ≥ +20 RISK-ON, ≤ -20 RISK-OFF, else MIXED. Weights: ES 2 (up = on), NQ 2 (up = on), VIX 2 (up = off), "
             "DXY 1 (up = off), Gold 1 (up = off), JPY futures 1 (yen up = off), 10Y yield 1 (up = off), Bitcoin 1 (up = on).")
    return (f'<div class="dp"><h3>CURVE &amp; RISK</h3><table><tr><th>TENOR</th><th class="n">YIELD</th><th class="n">CHG</th><th>AS OF ET</th></tr>{yr}'
            f'<tr><th>SPREAD</th><th class="n">LEVEL</th><th class="n">CHG</th><th></th></tr>{spr}</table>'
            f'<div class="q" style="margin-top:5px"><i>COMPOSITE</i> <span class="tg {"on" if lab=="RISK-ON" else "off" if lab=="RISK-OFF" else "in"}">{lab}</span> <b>{sg(score,0)}</b> <span class="m">(-100 … +100)</span></div>'
            f'<div class="rbar"><b></b><i style="left:calc({(score+100)/2:.1f}% - 1px)"></i></div><div class="m" style="display:flex;justify-content:space-between"><span>RISK-OFF -100</span><span>0</span><span>+100 RISK-ON</span></div>'
            f'<table><tr><th>INPUT</th><th class="n">%CHG</th><th class="n">WT</th><th>VOTE</th></tr>{"".join(vr)}</table>'
            f'<details class="nt"><summary>notes · weights</summary><div class="m">{notes} 2Y = official daily par yield (no free intraday 2Y); 3M/5Y/10Y/30Y = delayed yield indices. '
            f'Spread change uses each leg\'s own prior close.</div></details></div>')
def pulse_panel(D):
    P = D.get("pulse") or {}; E = D.get("earn") or {}; O = D.get("earn_other") or {}
    names = {"XLK": "Technology", "XLF": "Financials", "XLE": "Energy", "XLV": "Health Care", "XLY": "Cons. Discretionary", "SMH": "Semiconductors",
             "NVDA": "NVIDIA", "AAPL": "Apple", "MSFT": "Microsoft", "AMZN": "Amazon", "META": "Meta", "GOOGL": "Alphabet", "TSLA": "Tesla", "AVGO": "Broadcom"}
    h = []
    for g, l in (("SECTORS", ["XLK", "XLF", "XLE", "XLV", "XLY", "SMH"]), ("MEGACAPS", ["NVDA", "AAPL", "MSFT", "AMZN", "META", "GOOGL", "TSLA", "AVGO"])):
        h.append(f'<tr class="gh"><td colspan="7">{g}</td></tr>')
        for s in l:
            q = P.get(s); er = " ".join(f'<span class="tg e">ER {e(x["date"])} {e(x["time"])}</span>' for x in E.get(s, []))
            if not q: h.append(f'<tr><td class="c">{s}</td><td>{names[s]}</td><td class="n" colspan="4">N/A</td><td>{er}</td></tr>'); continue
            h.append(f'<tr><td class="c">{s}</td><td>{names[s]}</td><td class="n b">{f(q["last"])}</td><td class="n {cls(q["chg"])}">{sg(q["chg"])}</td><td class="n {cls(q["pct"])}">{sg(q["pct"])}%</td>'
                     f'<td class="m">{e(q["sess"])} {e(q["asof"])}</td><td>{er}</td></tr>')
    oth = " · ".join(f'{e(s)} {e(v[0]["date"])} {e(v[0]["time"])}' for s, v in O.items())
    return (f'<div class="dp"><h3>SECTOR &amp; MEGACAP PULSE</h3><table><tr><th>SYM</th><th>NAME</th><th class="n">LAST</th><th class="n">CHG</th><th class="n">%CHG</th><th>SESS · AS OF ET</th><th>EARNINGS</th></tr>{"".join(h)}</table>'
            f'<div class="m">Extended-hours last (PRE/AH) vs the prior regular-session close. ER = reports tonight or next session (BMO before open, AMC after close).'
            f'{" Other large caps reporting: " + oth + "." if oth else ""}</div></div>')
def cal_panel(D):
    C = D.get("cal") or {}; ns = D.get("next_session", "—")
    ec = "".join(f'<tr><td class="n">{e(r["time_pt"])}</td><td>{e(r["title"])}</td><td class="m">{e(r["impact"])}</td><td class="n">{e(r["fc"] or "—")}</td><td class="n">{e(r["prev"] or "—")}</td></tr>' for r in C.get("econ", [])) \
         or '<tr><td colspan="5" class="m">No scheduled US releases listed.</td></tr>'
    fd = "".join(f'<tr><td class="n">{e(r["time_pt"])}</td><td colspan="4">{e(r["title"])}</td></tr>' for r in C.get("fed", [])) or '<tr><td colspan="5" class="m">No Fed speakers listed.</td></tr>'
    au = "".join(f'<tr><td class="n">{e(r["time_pt"])}</td><td>{e(r["date"])} · {e(r["term"])} {e(r["type"])}{" (reopen)" if r["reopen"] else ""}</td><td class="m">{"NEXT SESSION" if r["next"] else ""}</td><td class="n" colspan="2">{f(r["size"],1)}B</td></tr>' for r in C.get("auctions", [])) \
         or '<tr><td colspan="5" class="m">No auctions in the next week.</td></tr>'
    _ex_bits = []
    for r in C.get("expiries", []):
        tag = '<span class="tg out">NEXT SESSION</span>' if r["today"] else ('<span class="m">in ' + str(r["days"]) + 'd</span>')
        _ex_bits.append(f'<div class="q"><i>{e(r["date"])}</i> {e(r["what"])} {tag}</div>')
    ex = "".join(_ex_bits)
    warn = "" if C.get("ok", True) else '<div class="m">Economic calendar feed unavailable this run.</div>'
    return (f'<div class="dp"><h3>TODAY\'S CALENDAR · {e(ns)}</h3>{warn}<table><tr><th class="n">PT</th><th>US RELEASE</th><th>IMPACT</th><th class="n">CONS</th><th class="n">PRIOR</th></tr>{ec}'
            f'<tr><th class="n">PT</th><th colspan="4">FED SPEAKERS</th></tr>{fd}<tr><th class="n">PT</th><th>TREASURY AUCTIONS (7D)</th><th></th><th class="n" colspan="2">SIZE</th></tr>{au}</table>'
            f'<div style="margin-top:4px">{ex}</div><div class="m">Times PT (auction = competitive close). OPEX = 3rd Friday; VIX expiry = Wednesday 30 days before the next month\'s OPEX.</div></div>')
def _ledger_stale_tag(issue_date, today=None):
    """' · awaiting update (last issue <date>)' when the issue predates the previous weekday (PT)."""
    import datetime as _dt
    from zoneinfo import ZoneInfo as _Z
    try:
        d = _dt.date.fromisoformat(str(issue_date)[:10])
    except ValueError:
        return " · awaiting update"
    t = today or _dt.datetime.now(_Z("America/Los_Angeles")).date()
    prev = t - _dt.timedelta(days=1)
    while prev.weekday() >= 5:
        prev -= _dt.timedelta(days=1)
    return f" · awaiting update (last issue {d.isoformat()})" if d < prev else ""



LEDGER_BLOCK_RE = re.compile(r'<div class="dp(?: full)?"><h3>NIGHT LEDGER[\s\S]*?</div></div>')
LEDGER_DATE_RE = re.compile(r'NIGHT LEDGER · (\d{4}-\d{2}-\d{2})')


def page_ledger_date(html):
    m = LEDGER_DATE_RE.search(html or "")
    return m.group(1) if m else ""


def extract_ledger_block(html):
    m = LEDGER_BLOCK_RE.search(html or "")
    return m.group(0) if m else ""


def pick_ledger_html(incoming_date, new_html, existing_html=""):
    """Keep the on-page Night Ledger when its issue date is newer than the incoming parse."""
    old = page_ledger_date(existing_html)
    incoming = str(incoming_date or "")[:10]
    if old and incoming and old > incoming:
        kept = extract_ledger_block(existing_html)
        if kept:
            return kept
    return new_html


def ledger_panel(N, D):
    if not N: return '<div class="dp"><h3>NIGHT LEDGER</h3><div class="m">No issue parsed.</div></div>'
    es = ((D.get("on") or {}).get("ES") or {}).get("last")
    _lv_bits = []
    for l in N.get("levels", []):
        _tag = '<span class="tg out">IN TAKE</span>' if l["in_take"] else ""
        _delta = sg(l["es"]-es) if es else "—"
        _cls = cls((l["es"]-es) if es else None)
        _lv_bits.append(f'<tr><td class="n b">{f(l["spy"])}</td><td class="n">{f(l["es"])}</td><td class="n {_cls}">{_delta}</td><td>{e(l["kind"])}</td><td>{_tag}</td></tr>')
    lv = "".join(_lv_bits)
    hr = N.get("hit_rate"); hist = N.get("history", [])
    hh = " ".join(f'<span class="tg {"on" if x["hit"] else "off" if x["hit"] is False else "in"}" title="{e(x["date"])} call {e(x["call"])} → {x["pct"] if x["pct"] is not None else "pending"}%">{e(x["date"][5:])} {e(x["call"][0])}</span>' for x in hist)
    d = N.get("direction", "—")
    return (f'<div class="dp"><h3>NIGHT LEDGER · {e(N.get("date",""))}{_ledger_stale_tag(N.get("date",""))}</h3><div class="q"><i>NEXT-DAY CALL</i> <span class="tg {"on" if d=="UP" else "off" if d=="DOWN" else "in"}">{e(d)}</span></div>'
            + (f'<div class="q"><i>SINCE ISSUE · {e(N.get("intraday_date") or "")}</i></div>' + "".join(f'<div class="q"><span class="m">{e(x["pt"])} PT</span> {e(x["text"])}</div>' for x in N.get("intraday", [])) if N.get("intraday") else "") +
            f'<div class="q"><i>BASE CASE</i> {e(N.get("base","—"))}</div><div class="q"><i>ALTERNATIVE</i> {e(N.get("alternative","—"))}</div><div class="q"><i>FLIP TRIGGER</i> {e(N.get("trigger","—"))}</div>'
            f'<table style="margin-top:4px"><tr><th class="n">SPY</th><th class="n">ES EQUIV</th><th class="n">vs ES LAST</th><th>TYPE</th><th></th></tr>{lv}</table>'
            f'<div class="q" style="margin-top:4px"><i>HIT RATE</i> <b>{f(hr["rate"],1) if hr else "—"}%</b> <span class="m">({hr["hits"] if hr else 0}/{hr["n"] if hr else 0} next-day direction calls)</span></div><div>{hh}</div>'
            f'<div class="m">ES = SPY ÷ {N.get("factor")}. Call scored vs next SPY close-to-close (|move| under 0.3% = FLAT; a directional call with a flat same-sign day counts as a hit).</div></div>')
def build(B, existing_html=""):
    D = L("es_levels/overnight_details.json"); N = L("xnews/ledger/ledger.json")
    if not D: return "", CSS
    gen = e(D.get("generated_et", ""))
    ledger = ledger_panel(N, D).replace('<div class="dp">', '<div class="dp full">', 1)
    if not existing_html:
        _p = R / "overnight/index.html"
        if _p.exists():
            existing_html = _p.read_text(encoding="utf-8", errors="replace")
    ledger = pick_ledger_html((N or {}).get("date", ""), ledger, existing_html)
    return (f'<h2>OVERNIGHT DETAIL <span class="m" style="letter-spacing:0;font-weight:400">· built {gen}</span></h2><div class="dgrid">{on_panel(D)}{curve_panel(D, B)}'
            f'{pulse_panel(D)}{cal_panel(D)}{ledger}</div>'), CSS

def chart(k, s):
    if not s or not s.get("bars"): return f'<div class="sc"><div class="st">/{k} OVERNIGHT</div><div class="m">N/A</div></div>'
    B = s["bars"]; W, H, pl, pr, pt, pb = 640, 220, 6, 118, 8, 18
    lv = [("PRIOR CLOSE", s["rth_close"], "#857d6a"), ("ON HI", s["on_hi"], "#3ddc5c"), ("ON LO", s["on_lo"], "#ff4d4d"), ("ON MID", s["on_mid"], "#ffb000")]
    lo = min([b[3] for b in B] + [v for _, v, _ in lv if v]); hi = max([b[2] for b in B] + [v for _, v, _ in lv if v]); pad = (hi - lo) * .06 or 1; lo -= pad; hi += pad
    n = 108  # 18:00-09:00 ET (Globex open .. 9h later) at 5m = full window; Asia 18:00-03:00, London 03:00-09:30
    tot = max(186, len(B)); xw = (W - pl - pr) / tot
    X = lambda i: pl + i * xw + xw / 2; Y = lambda v: pt + (hi - v) / (hi - lo) * (H - pt - pb)
    g = [f'<rect x="{pl}" y="{pt}" width="{108*xw:.1f}" height="{H-pt-pb}" fill="#22c7e8" opacity=".05"/>',
         f'<rect x="{pl+108*xw:.1f}" y="{pt}" width="{78*xw:.1f}" height="{H-pt-pb}" fill="#ffb000" opacity=".05"/>',
         f'<text x="{pl+3}" y="{H-5}" fill="#22c7e8" font-size="9">ASIA 15:00-00:00 PT</text>', f'<text x="{pl+108*xw+3:.1f}" y="{H-5}" fill="#ffb000" font-size="9">LONDON 00:00-06:30 PT</text>']
    for lab, v, c in lv:
        if v is None: continue
        y = Y(v); g.append(f'<line x1="{pl}" x2="{W-pr}" y1="{y:.1f}" y2="{y:.1f}" stroke="{c}" stroke-dasharray="3 3" stroke-width="1"/><text x="{W-pr+3}" y="{y+3:.1f}" fill="{c}" font-size="9">{lab} {v:,.2f}</text>')
    for i, (t, o, h, l, c) in enumerate(B):
        col = "#3ddc5c" if c >= o else "#ff4d4d"; x = X(i)
        g.append(f'<line x1="{x:.1f}" x2="{x:.1f}" y1="{Y(h):.1f}" y2="{Y(l):.1f}" stroke="{col}" stroke-width="1"/><rect x="{x-xw*.35:.1f}" y="{Y(max(o,c)):.1f}" width="{xw*.7:.1f}" height="{max(.8,abs(Y(o)-Y(c))):.1f}" fill="{col}"/>')
    return (f'<div class="sc"><div class="st">/{k} OVERNIGHT <b>{s["last"]:,.2f}</b> <span class="m">5m · {e(s["sess_start"])} → {e(s["asof"])} ET</span></div>'
            f'<svg viewBox="0 0 {W} {H}" width="100%" preserveAspectRatio="none" style="display:block;height:auto;font-family:inherit" role="img" aria-label="/{k} overnight 5 minute chart">{"".join(g)}</svg></div>')
def charts():
    D = L("es_levels/overnight_details.json"); on = D.get("on") or {}
    if not on: return ""
    return f'<div class="sub">OVERNIGHT CHARTS</div><div class="strip">{chart("ES", on.get("ES"))}{chart("NQ", on.get("NQ"))}</div>'
