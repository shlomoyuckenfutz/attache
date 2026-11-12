#!/usr/bin/env python3
"""ATTACHÉ WEEKLY PLAN page. Source of truth: newest /workspace/plans/yuckenfutz-weekly-YYYY-MM-DD.txt (plain-text plan
written in Everett's format); a copy is kept in weekly/plan.txt so a missing plans dir never blanks the page.
  build_weekly.py                 -> weekly/index.html
  build_weekly.py --patch-desk F  -> insert/refresh the WEEKLY PLAN summary card at the top of the desk page F
Plan only. Sources are never named in the plan; site_sanitize + the publish scrub still run after this."""
import os
import re, sys, html, shutil
from pathlib import Path
R = Path(__file__).resolve().parent; W = R / "weekly"; W.mkdir(exist_ok=True)
import dark_pool_html as _dp
MK = "<!--WEEKLYCARD-->"

def src():
    c = sorted((Path(__file__).resolve().parent.parent / "inputs" / "plans").glob("yuckenfutz-weekly-*.txt"))
    if c: shutil.copy(c[-1], W / "plan.txt")
    return (W / "plan.txt").read_text(encoding="utf-8")

def esc(s):
    s = html.escape(s)
    s = re.sub(r"(?<![\w.,])(~?(?:\d{1,3}(?:,\d{3})+|\d{2,})(?:\.\d+)?)(?![\w,])", r"<b>\1</b>", s)  # numbers pop like the desk
    s = s.replace("→", '<span class="ar">→</span>')
    return s

def parse(t):
    L = [l.rstrip() for l in t.splitlines()]
    title = L[0]; head = []; secs = []; cur = None
    for l in L[1:]:
        if not l.strip(): continue
        tkr = re.match(r"^(/ES|/NQ|SPY|QQQ|SPX)\b", l) is not None and len(l) < 100 and not l.endswith(".")
        if cur is not None and l.startswith("SPX (") and ":" in l:
            cur["blocks"].append({"sub": "SPX", "items": ["- " + l.split(":", 1)[0][4:].strip("() ") + ": " + l.split(":", 1)[1].strip()]}); continue
        if not tkr and re.fullmatch(r"[A-Z][A-Z /&,.\-]+( \([^)]*\))?", l.strip()) and not l.startswith("-"):
            cur = {"h": l.strip(), "blocks": []}; secs.append(cur); continue
        if cur is None: head.append(l); continue
        if tkr:   # ticker sub-header: "/ES", "SPY (spot 759.97)"
            cur["blocks"].append({"sub": l.strip(), "items": []}); continue
        if not cur["blocks"] or "sub" not in cur["blocks"][-1] and l[:2] not in ("- ",) and not re.match(r"\d+\. ", l):
            cur["blocks"].append({"p": l}); continue
        b = cur["blocks"][-1]
        if "items" not in b: b = {"items": []}; cur["blocks"].append(b)
        b["items"].append(l)
    return title, head, secs

def item(l):
    k = ""
    m = re.match(r"^- ([A-Za-z/ ]{3,28}): (.*)$", l)
    if m:
        lab = m.group(1); cls = "res" if lab.lower().startswith("res") else "sup" if lab.lower().startswith("sup") else "piv" if lab.lower().startswith("piv") else ""
        return f'<li class="{cls}"><span class="lb">{html.escape(lab)}</span><span class="vv">{esc(m.group(2))}</span></li>'
    m = re.match(r"^(\d+)\. (.*)$", l)
    if m: return f'<li class="nb"><span class="n">{m.group(1)}</span><span class="vv">{esc(m.group(2))}</span></li>'
    return f'<li><span class="vv">{esc(l[2:] if l.startswith("- ") else l)}</span></li>'

CSS = """<style>
:root{--bg:#000;--ln:#232323;--ln2:#333;--amb:#ffb000;--amb2:#a87400;--txt:#e6e0cc;--mut:#857d6a;--up:#3ddc5c;--dn:#ff4d4d;--cy:#22c7e8}
*{box-sizing:border-box}body{margin:0;background:#000;color:var(--txt);font:13px/1.55 'IBM Plex Mono',ui-monospace,Menlo,Consolas,monospace;font-variant-numeric:tabular-nums}
main{max-width:1100px;margin:0 auto;padding:10px 12px 40px}h1{color:var(--amb);font-size:16px;letter-spacing:.12em;margin:8px 0 4px}
.hd{color:var(--mut);font-size:12px;margin:0 0 10px}.hd div{margin:2px 0}.hd b{color:var(--txt)}
.toc{display:flex;flex-wrap:wrap;gap:4px;margin:0 0 10px}.toc a{color:var(--amb);border:1px solid var(--ln2);border-radius:6px;padding:4px 9px;font-size:11px;text-decoration:none}.toc a:hover{background:var(--amb);color:#000}
.sec{border:1px solid var(--ln2);border-radius:6px;background:#070707;margin:0 0 10px;padding:8px 12px}
.sec>h2{color:#000;background:var(--amb);display:inline-block;font-size:11px;letter-spacing:.15em;padding:1px 8px;margin:0 0 6px}
.sec p{margin:4px 0}.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(320px,1fr));gap:8px}
.tk{border:1px solid var(--ln);border-radius:6px;padding:6px 10px;background:#030303}.tk h3{color:var(--amb);font-size:13px;margin:0 0 4px}
ul{list-style:none;margin:0;padding:0}li{display:flex;gap:8px;padding:3px 0;border-bottom:1px dotted #1c1c1c}li:last-child{border:0}
.lb{flex:0 0 92px;color:var(--mut);font-size:11px;text-transform:uppercase;padding-top:1px}.vv{flex:1;min-width:0;overflow-wrap:anywhere}
li.res .lb{color:var(--dn)}li.sup .lb{color:var(--up)}li.piv .lb{color:var(--amb)}.n{flex:0 0 22px;color:#000;background:var(--amb2);border-radius:4px;text-align:center;font-weight:700;height:20px}
b{color:var(--amb);font-weight:600}.ar{color:var(--cy)}.ft{color:var(--mut);font-size:11px;margin-top:12px}
@media(max-width:700px){body{font-size:13.5px}.grid{grid-template-columns:1fr}.lb{flex-basis:76px}.sec{padding:8px}}
.chg{display:grid;grid-template-columns:1fr 1fr;gap:10px}.ch{margin:0}.ch img{width:100%;height:auto;display:block;border:1px solid #333;border-radius:4px}.ch figcaption{color:#9a8a60;font-size:11px;margin-top:3px}
@media(max-width:700px){.chg{grid-template-columns:1fr}}
</style>"""
CSS = CSS[:-8] + _dp.CSS + "</style>"  # inject DP table styles before </style>

def page(t):
    title, head, secs = parse(t)
    ids = [re.sub(r"[^a-z0-9]+", "-", s["h"].lower()).strip("-") for s in secs]
    out = [f'<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">'
           f'<title>ATTACHÉ | WEEKLY PLAN</title><link rel="icon" href="data:,">'
           f'<link href="https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;600;700&display=swap" rel="stylesheet">{CSS}</head><body><main>',
           f'<h1>{html.escape(title)}</h1><div class="hd">' + "".join(f"<div>{esc(h)}</div>" for h in head) + "</div>",
           '<nav class="toc">' + "".join(f'<a href="#{i}">{html.escape(s["h"])}</a>' for i, s in zip(ids, secs)) + '<a href="#spy-dark-pool-levels" style="border-color:#a855f7;color:#c084fc">SPY Dark Pool levels</a>' + "</nav>"]
    for i, s in zip(ids, secs):
        subs = [b for b in s["blocks"] if "sub" in b]
        o = [f'<section class="sec" id="{i}"><h2>{html.escape(s["h"])}</h2>']
        if subs: o.append('<div class="grid">')
        for b in s["blocks"]:
            if "p" in b: o.append(f"<p>{esc(b['p'])}</p>")
            elif "sub" in b: o.append(f'<div class="tk"><h3>{html.escape(b["sub"])}</h3><ul>' + "".join(item(x) for x in b["items"]) + "</ul></div>")
            else: o.append("<ul>" + "".join(item(x) for x in b["items"]) + "</ul>")
        if subs: o.append("</div>")
        o.append("</section>"); out.append("".join(o))
        if s["h"].startswith("KEY LEVELS"):
            out.append(_dp.section_html())
            out.append(charts_html())
    out.append('<div class="ft">Plan only. Not investment advice. Levels are plan levels, not live data.</div></main></body></html>')
    return "".join(out), title, secs

CH = [("es", "/ES"), ("nq", "/NQ"), ("spy", "SPY"), ("qqq", "QQQ")]
def _figs(d, href_prefix, have):
    v = int(max(os.path.getmtime(os.path.join(d, k + ".png")) for k, _ in have))
    return "".join(
        f'<figure class="ch"><a href="{href_prefix}/{k}.png?v={v}">'
        f'<img src="{href_prefix}/{k}.png?v={v}" alt="{n} weekly chart" loading="lazy"></a>'
        f'<figcaption>{n}</figcaption></figure>'
        for k, n in have)

def charts_html():
    base = os.path.join(os.path.dirname(os.path.abspath(__file__)), "weekly", "charts")
    prior = os.path.join(base, "prior")
    plan = os.path.join(base, "plan")
    # prefer prior/ subdir; fall back to top-level weekly/charts/*.png
    prior_dir = prior if os.path.isdir(prior) else base
    have_prior = [(k, n) for k, n in CH if os.path.exists(os.path.join(prior_dir, k + ".png"))]
    have_plan = [(k, n) for k, n in CH if os.path.exists(os.path.join(plan, k + ".png"))]
    if not have_prior and not have_plan:
        return ""
    out = []
    if have_prior:
        href = "charts/prior" if prior_dir == prior else "charts"
        figs = _figs(prior_dir, href, have_prior)
        out.append(
            '<section class="sec" id="plan-charts"><h2>LAST WEEK · PLAN vs ACTUAL</h2>'
            '<p>Week of <b>Nov 2–6</b> mapped end-to-end. Amber = week before; '
            'white = Mon–Thu actual 30m; <b>cyan = jobs Fri</b>. '
            'Green/red bands = plan bull / bear zones. Purple ticks = jobs Fri 5:30 AM PT (edge only — no line through candles). '
            'Dashed plan paths omitted on days with actuals (lines stay off candles). '
            'Each day labeled hi / lo / close. Tap a chart to enlarge.</p>'
            f'<div class="chg">{figs}</div></section>')
    if have_plan:
        figs = _figs(plan, "charts/plan", have_plan)
        out.append(
            '<section class="sec" id="plan-forward"><h2>THIS WEEK · PLAN</h2>'
            '<p>Week of <b>Nov 9–13</b> — neutral to bullish while ES holds 7596–7600 (pivot 7625); risks into Friday: the Nvidia CEO shock, hike pricing after the hot CPI and Friday\'s PPI. Amber = prior week actual; '
            'white = this week\'s actual 30m so far; empty day columns show the <b>bull (green) and bear (red) paths</b> only — no lines through candles. '
            'Day tags: Tue CPI · Wed Veterans Day · Thu jobless claims and 30-year Treasury bond sale · Fri PPI. '
            'Purple ticks = PPI Fri 5:30 AM PT. Levels as right-edge ticks. Nasdaq charts show candles only: levels awaiting update. Tap to enlarge.</p>'
            f'<div class="chg">{figs}</div></section>')
    return "".join(out)

def card(title, secs):
    bias = next((s for s in secs if s["h"].startswith("BIAS")), None)
    p = next((b["p"] for b in (bias or {"blocks": []})["blocks"] if "p" in b), "")
    p = (p[:260].rsplit(" ", 1)[0] + "…") if len(p) > 260 else p
    return (f'{MK}<a href="../weekly/" style="display:block;margin:8px 10px;padding:8px 12px;border:1px solid #a87400;border-radius:6px;background:#0b0800;'
            f'color:#e6e0cc;text-decoration:none;font:12px/1.5 \'IBM Plex Mono\',ui-monospace,monospace"><span style="color:#000;background:#ffb000;'
            f'padding:1px 8px;font-weight:700;letter-spacing:.15em;font-size:11px">WEEKLY PLAN</span> <b style="color:#ffb000">{html.escape(title.split("—")[-1].strip())}</b>'
            f'<div style="margin-top:4px">{html.escape(p)}</div><div style="color:#22c7e8;margin-top:4px">Open full plan: levels, scenarios, day by day, triggers →</div></a>{MK}')

if __name__ == "__main__":
    # Charts are built by refresh.sh via make_daily_charts.py (must succeed there).
    # Do not invoke a missing make_weekly_charts.py or swallow chart errors here.
    h, title, secs = page(src()); (W / "index.html").write_text(h, encoding="utf-8"); print("weekly ->", W / "index.html", len(secs), "sections")
    if len(sys.argv) > 2 and sys.argv[1] == "--patch-desk":
        f = Path(sys.argv[2]); s = f.read_text(); s = re.sub(re.escape(MK) + ".*?" + re.escape(MK), "", s, flags=re.S)
        m = re.search(r"<body[^>]*>", s); c = card(title, secs)
        s = s[:m.end()] + c + s[m.end():] if m else c + s
        f.write_text(s); print("weekly card ->", f)
