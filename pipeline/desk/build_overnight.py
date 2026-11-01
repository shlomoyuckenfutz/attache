#!/usr/bin/env python3
"""ATTACHÉ OVERNIGHT page builder -> overnight/index.html (published to /attache/overnight/). Reads es_levels/overnight.json."""
import json
from pathlib import Path
from html import escape as e
R = Path(__file__).resolve().parent
D = json.loads((R / "es_levels/overnight.json").read_text())
def dec(v):
    a = abs(v)
    return 6 if a < 0.05 else 4 if a < 20 else 3 if a < 200 else 2 if a < 20000 else 0
def f(v, d=None):
    if v is None: return "—"
    return f"{v:,.{dec(v) if d is None else d}f}"
def sg(v, d):
    if v is None: return "—"
    return ("+" if v > 0 else "") + f"{v:,.{d}f}"
def cls(v): return "up" if v and v > 0 else "dn" if v and v < 0 else "fl"
rows = []
for g in D["groups"]:
    rows.append(f'<tr class="gh"><td colspan="9">{e(g["name"])}</td></tr>')
    for r in g["rows"]:
        q = r["q"]; tag = {"LIVE": "", "PROXY": '<span class="px" title="%s">PROXY</span>' % e(r["note"]), "NA": '<span class="na">N/A</span>'}[r["status"]]
        if not q:
            rows.append(f'<tr><td class="c">{e(r["code"])}</td><td>{e(r["name"])} {tag}</td>' + '<td class="n">—</td>'*6 + '<td></td></tr>'); continue
        d = dec(q["last"]); c = cls(q["chg"])
        fl = '<span class="fh">▲ AT HI</span>' if q["flag"] == "HI" else '<span class="fl2">▼ AT LO</span>' if q["flag"] == "LO" else ""
        rows.append(f'<tr><td class="c">{e(r["code"])}</td><td>{e(r["name"])} {tag}</td><td class="n b">{f(q["last"])}</td>'
                    f'<td class="n {c}">{sg(q["chg"], d)}</td><td class="n {c}">{sg(q["pct"], 2)}%</td><td class="n">{f(q["hi"], d)}</td>'
                    f'<td class="n">{f(q["lo"], d)}</td><td>{fl}</td><td class="m">{e(q["asof"])}</td></tr>')
nw = []
for r in D.get("nightwatch", []):
    q = r["q"]; tag = {"LIVE": "", "PROXY": '<span class="px" title="%s">PROXY</span>' % e(r["note"]), "NA": '<span class="na">N/A</span>'}[r["status"]]
    if not q:
        nw.append(f'<tr><td class="c">{e(r["code"])}</td><td>{e(r["name"])} {tag}</td><td class="n">—</td><td class="n">—</td><td class="n">—</td><td class="m">—</td></tr>'); continue
    d = 3 if r["yld"] else dec(q["last"]); c = cls(q["chg"])
    nw.append(f'<tr><td class="c">{e(r["code"])}</td><td>{e(r["name"])} {tag}</td><td class="n b">{f(q["last"], d)}</td>'
              f'<td class="n {c}">{sg(q["chg"], d)}</td><td class="n {c}">{sg(q["pct"], 2)}%</td><td class="m">{e(q["asof"])}</td></tr>')
nwhtml = (f'<div class="sub">NIGHT WATCH</div><div class="wrap"><table><thead><tr><th>SYM</th><th>INSTRUMENT</th><th class="n">LAST</th><th class="n">CHG</th><th class="n">%CHG</th><th>AS OF ET</th></tr></thead>'
          f'<tbody>{"".join(nw)}</tbody></table></div>') if nw else ""
def strip(k):
    s = D["strip"][k]
    def vs(a, b, hi):
        if a is None or b is None: return ""
        x = a - b; return f' <span class="{cls(x)}">{sg(x,2)}</span>' + (' <span class="fh">ABOVE</span>' if hi and x > 0 else ' <span class="fl2">BELOW</span>' if not hi and x < 0 else ' <span class="m">inside</span>')
    lon = (f'{f(s["lon_hi"],2)} / {f(s["lon_lo"],2)}' if s["lon_open"] else '<span class="m">pending (03:00 ET)</span>')
    extra = (f'<div><i>ASIA</i> H {f(s["asia_hi"],2)} · L {f(s["asia_lo"],2)}</div><div><i>LONDON</i> {lon}</div>' if k == "ES" else "")
    return (f'<div class="sc"><div class="st">/{k} <b>{f(s["last"],2)}</b> <span class="m">{e(s["asof"])} ET</span></div>'
            f'<div><i>GLOBEX H</i> {f(s["on_hi"],2)} vs RTH H {f(s["rth_hi"],2)}{vs(s["on_hi"], s["rth_hi"], True)}</div>'
            f'<div><i>GLOBEX L</i> {f(s["on_lo"],2)} vs RTH L {f(s["rth_lo"],2)}{vs(s["on_lo"], s["rth_lo"], False)}</div>{extra}'
            f'<div class="m">session from {e(s["sess_start"])} ET · prior RTH {e(s["rth_date"] or "—")} 09:30-16:00</div></div>')
import overnight_panels  # OVERNIGHT DETAIL panels (levels, curve & risk, pulse, calendar, night ledger)
try: dethtml, detcss = overnight_panels.build(D)
except Exception as ex: dethtml, detcss = "", ""
try: charthtml = overnight_panels.charts()
except Exception: charthtml = ""
html = f'''<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>ATTACHÉ | OVERNIGHT</title><link rel="icon" href="data:,">
<link href="https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;600;700&display=swap" rel="stylesheet">
<style>
:root{{--bg:#000;--ln:#232323;--ln2:#333;--amb:#ffb000;--amb2:#a87400;--txt:#e6e0cc;--mut:#857d6a;--up:#3ddc5c;--dn:#ff4d4d;--cy:#22c7e8;--hd:#120d00}}
*{{box-sizing:border-box}}body{{margin:0;background:#000;color:var(--amb);font:12px/1.45 'IBM Plex Mono',ui-monospace,Menlo,Consolas,monospace;font-variant-numeric:tabular-nums}}
a{{color:var(--cy);text-decoration:none}}.top{{position:sticky;top:0;z-index:5;background:#000;border-bottom:1px solid var(--amb2)}}
.tb{{display:flex;gap:12px;align-items:center;flex-wrap:wrap;padding:5px 10px}}.brand{{font-weight:700;letter-spacing:3px;color:#000;background:var(--amb);padding:1px 8px}}
.zl{{display:flex;gap:2px;flex-wrap:wrap}}.zl a{{color:var(--amb);border:1px solid var(--ln2);padding:1px 8px;font-weight:600;font-size:11px}}.zl a:hover{{background:var(--amb);color:#000}}
.m{{color:var(--mut)}}.up{{color:var(--up)}}.dn{{color:var(--dn)}}.fl{{color:var(--txt)}}main{{padding:8px 10px;max-width:1400px}}
.strip{{display:grid;grid-template-columns:repeat(auto-fit,minmax(340px,1fr));gap:6px;margin-bottom:8px}}.sc{{border:1px solid var(--ln2);background:#070707;padding:5px 8px;color:var(--txt)}}
.sc i{{font-style:normal;color:var(--amb);display:inline-block;width:84px}}.st{{color:var(--amb);font-weight:700;border-bottom:1px solid var(--ln);margin-bottom:3px}}.st b{{color:var(--txt)}}
table{{width:100%;border-collapse:collapse}}td,th{{padding:2px 6px;border-bottom:1px solid #141414;white-space:nowrap}}th{{text-align:left;color:var(--mut);font-weight:600;border-bottom:1px solid var(--amb2)}}
td{{color:var(--txt)}}.n{{text-align:right}}th.n{{text-align:right}}.b{{font-weight:700;color:#fff}}td.c{{color:var(--amb);font-weight:700;width:52px}}
tr.gh td{{background:var(--hd);color:var(--amb);font-weight:700;letter-spacing:2px;border-top:1px solid var(--amb2);padding-top:4px}}
tr:hover td{{background:#0c0c0c}}.px{{color:#000;background:var(--amb2);font-size:10px;padding:0 4px}}.na{{color:var(--mut);border:1px solid var(--ln2);font-size:10px;padding:0 4px}}
.fh{{color:#000;background:var(--up);font-size:10px;padding:0 4px;font-weight:700}}.fl2{{color:#000;background:var(--dn);font-size:10px;padding:0 4px;font-weight:700}}
.wrap{{overflow-x:auto}}.nwp{{border:1px solid var(--ln2);background:#070707;margin-bottom:8px;max-width:760px}}h2{{font-size:12px;letter-spacing:2px;margin:6px 0;color:var(--amb)}}
{detcss}
</style></head><body>
<div class="top"><div class="tb"><span class="brand">ATTACHÉ</span><small class="m">OVERNIGHT · cross-asset futures board</small>
<nav class="zl"><a href="../">◄ DESK</a><a href="../command/">COMMAND</a><a href="./" style="color:#000;background:var(--amb)">OVERNIGHT</a></nav>
<small class="m">DELAYED ~10-20 MIN · built {e(D["generated_et"])} · continuous front month</small></div></div>
<main><h2>ES / NQ OVERNIGHT vs PRIOR RTH</h2><div class="dp sec"><div class="strip">{strip("ES")}{strip("NQ")}</div>{charthtml}{nwhtml}</div>
{dethtml}
<h2>CROSS-ASSET BOARD</h2><div class="dp sec wrap"><table><thead><tr><th>SYM</th><th>CONTRACT</th><th class="n">LAST</th><th class="n">CHG</th><th class="n">%CHG</th><th class="n">SESS HI</th><th class="n">SESS LO</th><th>FLAG</th><th>AS OF ET</th></tr></thead>
<tbody>{"".join(rows)}</tbody></table></div>
<p class="m">Session = current Globex session (from 18:00 ET) for futures; current trading day for cash/ETF rows. Change vs prior session close. PROXY = nearest freely available instrument (cash index, spot index or ETF). N/A = no free feed. Delayed data; research only, not advice.</p></main>
<script>document.querySelectorAll('tbody tr:not(.gh)').forEach(function(t){{if(t.cells[1])t.title=t.cells[1].textContent.trim()}});</script>
</body></html>'''
(R / "overnight/index.html").write_text(html)
try:
    import ui_shell as _ui; _ui.inject('overnight', str(R / "overnight/index.html"))  # permanent: shared top bar/polish baked into every build
except Exception as _e: print('ui shell failed', _e)

