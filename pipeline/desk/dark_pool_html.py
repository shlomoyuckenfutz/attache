"""Render the SPY Dark Pool levels table (purple). Single source: site data/spy_dark_pool.json."""
import json, html
from pathlib import Path

SITE_DATA = Path(__file__).resolve().parent.parent.parent / "data" / "spy_dark_pool.json"  # repo data/
FALLBACK = Path(__file__).resolve().parent / "es_levels" / "darkpool_levels.json"
SPY_PER_SPX = 0.0997
ES_MINUS_SPX = 34.5

def load():
    if SITE_DATA.exists():
        return json.loads(SITE_DATA.read_text())
    cfg = json.loads(FALLBACK.read_text())
    levels = cfg.get("levels", [])
    rows = []
    for spy in levels:
        spx = round(spy / SPY_PER_SPX, 2)
        rows.append({"spy": spy, "spx": spx, "es": round(spx + ES_MINUS_SPX, 2)})
    return {"label": "Dark Pool", "levels": levels, "rows": rows,
            "convert": {"spy_per_spx": SPY_PER_SPX, "es_minus_spx": ES_MINUS_SPX}}

def section_html():
    d = load()
    rows = d.get("rows") or []
    if not rows and d.get("levels"):
        for spy in d["levels"]:
            spx = round(spy / SPY_PER_SPX, 2)
            rows.append({"spy": spy, "spx": spx, "es": round(spx + ES_MINUS_SPX, 2)})
    tr = "".join(
        f'<tr><td class="dp-spy">{html.escape(_fmt(r["spy"]))}</td>'
        f'<td>{html.escape(_fmt(r["spx"]))}</td>'
        f'<td>{html.escape(_fmt(r["es"]))}</td></tr>'
        for r in rows
    )
    return (
        '<section class="sec" id="spy-dark-pool-levels">'
        '<h2 style="background:#a855f7;color:#fff">SPY Dark Pool levels</h2>'
        '<p>Purple <b style="color:#c084fc">Dark Pool</b> set on SPY. '
        'SPX = SPY ÷ <b>0.0997</b> · ES = SPX + <b>34.5</b> (Fri close basis). '
        'Update via <code>data/spy_dark_pool.json</code> — see README.</p>'
        '<div class="dp-wrap"><table class="dp-tbl">'
        '<thead><tr><th>SPY</th><th>SPX</th><th>ES</th></tr></thead>'
        f'<tbody>{tr}</tbody></table></div></section>'
    )

def _fmt(x):
    try:
        return f"{float(x):.2f}"
    except (TypeError, ValueError):
        return str(x)

CSS = """
.dp-wrap{overflow:auto;margin:4px 0 2px}
.dp-tbl{border-collapse:collapse;width:100%;max-width:420px;font-variant-numeric:tabular-nums}
.dp-tbl th,.dp-tbl td{border:1px solid #333;padding:4px 10px;text-align:right}
.dp-tbl th{color:#c084fc;background:#1a1024;font-size:11px;letter-spacing:.08em;text-align:center}
.dp-tbl td{color:#e6e0cc}
.dp-tbl td.dp-spy{color:#c084fc;font-weight:600}
.dp-tbl tr:nth-child(even) td{background:#0c0812}
"""
