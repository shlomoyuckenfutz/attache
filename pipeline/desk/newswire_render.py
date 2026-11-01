"""THE WIRE: market news wire panel (main page) + 5-line ticker (COMMAND page). Renders xnews/newswire.json only.
Self-contained CSS/JS; breaking (<30 min) is re-evaluated in the browser so it stays correct between rebuilds."""
import json, html
from pathlib import Path
F = Path(__file__).resolve().parent / 'xnews' / 'newswire.json'
TAGC = {'FED': '#ff4d4d', 'MACRO': '#ffb000', 'EARNINGS': '#3ddc5c', 'GEO': '#ff7a1a', 'POLICY': '#c48cff', 'ENERGY': '#e8d21c',
        'RATES': '#22c7e8', 'FX': '#4fd1a5', 'TECH': '#7aa7ff', 'EQUITY': '#d9d2bc', 'CRYPTO': '#f0a0ff'}
CSS = """<style>
.nw{border:1px solid #232323;background:#000;font-family:'IBM Plex Mono',ui-monospace,Menlo,Consolas,monospace;font-variant-numeric:tabular-nums}
.nw .nh{display:flex;justify-content:space-between;gap:8px;align-items:baseline;background:#120d00;border-bottom:1px solid #a87400;padding:3px 8px;color:#ffb000;font-weight:700;letter-spacing:.5px;font-size:12px}
.nw .nh small{color:#857d6a;font-weight:400;font-size:11px}
.nw ol{list-style:none;margin:0;padding:0;display:grid;grid-template-columns:repeat(2,minmax(0,1fr));column-gap:12px}
.nw li{display:grid;grid-template-columns:56px 74px minmax(0,1fr) 46px;gap:8px;align-items:baseline;padding:2px 8px;border-bottom:1px solid #141414;font-size:12px;min-width:0}
.nw li .t{color:#3ddc5c;white-space:nowrap}.nw li .h{color:#e6e0cc;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}.nw li .s{color:#5a5446;font-size:10px;text-align:right}
.nw .g{display:inline-block;min-width:66px;text-align:center;font-size:10px;font-weight:700;color:#000;padding:0 4px;letter-spacing:.5px}
.nw li.bk{background:#1d1200;box-shadow:inset 3px 0 0 #ff4d4d}.nw li.bk .h{color:#ffb000;font-weight:600}
.nw li.bk .t::after{content:' ●';color:#ff4d4d;animation:nwb 1s steps(1) infinite}@keyframes nwb{50%{opacity:0}}
.nw .ft{padding:3px 8px;color:#5a5446;font-size:10px}
.nwt li{grid-template-columns:56px 74px minmax(0,1fr)}.nwt ol{grid-template-columns:minmax(0,1fr)}
@media(max-width:900px){.nw ol{grid-template-columns:minmax(0,1fr)}.nw li{grid-template-columns:40px 70px minmax(0,1fr)}.nw li .s{display:none}.nw li .h{white-space:normal}}
</style>"""
JS = """<script>(function(){var m=30*60e3,n=Date.now();document.querySelectorAll('.nw li[data-ts]').forEach(function(l){var a=n-Date.parse(l.dataset.ts);l.classList.toggle('bk',a>=0&&a<=m)});var c=document.querySelectorAll('.nw li.bk').length;document.querySelectorAll('.nw .nbk').forEach(function(e){e.textContent=c?c+' BREAKING':''})})();</script>"""

def load():
    try: return json.loads(F.read_text())
    except Exception: return {'items': []}

def _li(i, src=True):
    e = html.escape; c = TAGC.get(i['tag'], '#857d6a')
    return (f'<li class="{"bk" if i.get("breaking") else ""}" data-ts="{e(i["ts_utc"])}"><span class="t">{e(i["time_pt"])}</span>'
            f'<span><b class="g" style="background:{c}">{e(i["tag"])}</b></span><span class="h" title="{e(i["headline"])}">{e(i["headline"])}</span>'
            + (f'<span class="s">{e(i["src"].replace("SRC ", ""))}</span>' if src else '') + '</li>')

def main_html(d=None):
    d = d or load(); it = d.get('items', [])[:20]
    body = '<ol>' + ''.join(_li(i) for i in it) + '</ol>' if it else '<div class="ft">Wire quiet. No market headlines in the last pull.</div>'
    return (CSS + '<section class="zone" id="z-wire"><div class="zh"><b>THE WIRE</b><small>market headlines · newest first · times PT · red = breaking (&lt;30m)</small></div>'
            f'<div class="nw"><div class="nh"><span>NEWS WIRE · TOP {len(it)} <span class="nbk" style="color:#ff4d4d"></span></span><small>pulled {html.escape(d.get("generated_at_pt", "n/a"))}</small></div>'
            + body + '<div class="ft">Headlines rewritten and tagged automatically. Research only, not financial advice.</div></div></section>' + JS)

def command_html(d=None):
    d = d or load(); it = d.get('items', [])[:5]
    if not it: return ''
    return (CSS + f'<section class="nw nwt" id="z-wire"><div class="nh"><span>THE WIRE · LAST 5 <span class="nbk" style="color:#ff4d4d"></span></span><small>{html.escape(d.get("generated_at_pt", ""))} · <a href="../#z-wire" style="color:#22c7e8">full wire</a></small></div>'
            '<ol>' + ''.join(_li(i, False) for i in it) + '</ol></section>' + JS)
