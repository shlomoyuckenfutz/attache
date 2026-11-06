#!/usr/bin/env python3
"""ATTACHÉ DAILY PLAN page. Source of truth: xnews/plan.json (copied to daily/plan.json).
Optional enrich: auction note paths, levels_a latest levels, SRC take — never named on the page (SRC tags only via site_sanitize).
  build_daily.py [ --site DIR ]              -> DIR/daily/index.html
  build_daily.py --patch-desk F             -> insert/refresh DAILY PLAN summary card after WEEKLY card (or at top)
Plan only. No ORB-A/ORB-B. No source names/handles/links."""
from __future__ import annotations
import html, json, os, re, shutil, subprocess, sys
from pathlib import Path
import dark_pool_html as _dp
from datetime import datetime
from zoneinfo import ZoneInfo

PT = ZoneInfo("America/Los_Angeles")
HERE = Path(__file__).resolve().parent  # /workspace/desk/orb-research
DEFAULT_SITE = HERE  # writes daily/ under orb-research; publish copies to orb-dash-site
MK = "<!--DAILYCARD-->"
WK = "<!--WEEKLYCARD-->"


def site_dir():
    if "--site" in sys.argv:
        i = sys.argv.index("--site"); return Path(sys.argv[i + 1])
    return DEFAULT_SITE


def load_plan(site: Path):
    cands = [Path(__file__).resolve().parent.parent / "inputs" / "plan.json", Path(__file__).resolve().parent / "xnews" / "plan.json", site / "daily" / "plan.json"]
    for p in cands:
        if p.exists():
            data = json.loads(p.read_text())
            # keep a working copy next to the page
            (site / "daily").mkdir(parents=True, exist_ok=True)
            if p.resolve() != (site / "daily" / "plan.json").resolve():
                shutil.copy(p, site / "daily" / "plan.json")
            return data, p
    raise FileNotFoundError("plan.json missing")


def esc(s):
    s = html.escape(str(s))
    s = re.sub(r"(?<![\w.,])(~?(?:\d{1,3}(?:,\d{3})+|\d{2,})(?:\.\d+)?)(?![\w,])", r"<b>\1</b>", s)
    s = s.replace("→", '<span class="ar">→</span>')
    return s


def sanitize_text(s: str) -> str:
    """Neutral scrub before HTML (site_sanitize also runs on publish)."""
    s = re.sub(r"https?://(?:www\.|mobile\.)?(?:x|twitter)\.com/\S+", "", s, flags=re.I)
    s = re.sub(r"https?://(?:newsletter\.)?AUCTION_SRC\.com\S+", "", s, flags=re.I)
    s = re.sub(r"https?://\S*(?:free_data|free_feed)\S*", "", s, flags=re.I)
    s = re.sub(r"(?i)\bORB\s*(?:5|30)\b", "OPEN RANGE", s)
    # strip common handles/names (leave content)
    for n in ("AUCTION_SRC", "SRC LEVELS_A", "SRC LEDGER", "auction", "levels_a", "ledger",
              "magnet", "MAGNET_SRC"):
        s = re.sub(re.escape(n), "SRC", s, flags=re.I)
    s = re.sub(r"\bSRC\s*level\b", "plan level", s, flags=re.I)
    s = re.sub(r"\bSRC\b(\s*/\s*SRC)*", "plan", s)
    return s


def ticker_of(note: str) -> str:
    n = (note or "").upper()
    if "SPY" in n: return "SPY"
    if "QQQ" in n: return "QQQ"
    if "SPX" in n: return "SPX"
    if "/NQ" in n or re.search(r"\bNQ\b", n): return "NQ"
    if n.startswith("ES") or "/ES" in n or re.search(r"\bES\b", n): return "ES"
    try:
        px = float(re.findall(r"[\d.]+", note)[0]) if False else None
    except Exception:
        px = None
    return "ES"


def group_levels(plan):
    by = {k: [] for k in ("ES", "SPX", "SPY", "QQQ", "NQ")}
    for x in plan.get("key_levels") or []:
        try: px = float(x["price"])
        except Exception: continue
        note = str(x.get("note") or "")
        t = "ES"
        nu = note.upper()
        # Leading ticker wins (so "ES support (… SPY …)" stays on ES)
        if re.match(r"^(ES|/ES)\b", nu): t = "ES"
        elif re.match(r"^SPY\b", nu): t = "SPY"
        elif re.match(r"^SPX\b", nu): t = "SPX"
        elif re.match(r"^(/?NQ|QQQ)\b", nu): t = "NQ" if "NQ" in nu[:4] else "QQQ"
        elif "QQQ" in nu: t = "QQQ"
        elif "SPX" in nu and "ES" not in nu: t = "SPX"
        elif "/NQ" in nu or re.search(r"\bNQ\b", nu): t = "NQ"
        elif "ES" in nu or "/ES" in nu: t = "ES"
        elif "SPY" in nu: t = "SPY"
        else:
            t = "SPY" if px < 2000 else "ES"
        kind = "P"
        nl = note.lower()
        if any(k in nl for k in ("hinge", "pivot", "flip")): kind = "P"
        elif any(k in nl for k in ("support", "put", "floor", "downside", "fdt", "shelf", "long trigger")): kind = "S"
        elif any(k in nl for k in ("resist", "call", "upside", "magnet", "range top", "mvc", "stretch", "wall")): kind = "R"
        by[t].append((px, kind, sanitize_text(note)))
    return by



def weekly_frame_levels():
    """QQQ/NQ/SPX levels from weekly plan text when daily plan.json has none."""
    for cand in (HERE / "weekly" / "plan.txt", Path(__file__).resolve().parent.parent / "inputs" / "plans" / "yuckenfutz-weekly-2026-10-26.txt",
                 HERE / "weekly_plan.txt"):
        if cand.exists():
            t = cand.read_text(encoding="utf-8", errors="ignore"); break
    else:
        return {}
    out = {}
    for sym, key in (("QQQ", "QQQ"), ("/NQ", "NQ"), ("SPX", "SPX")):
        m = re.search(rf"^{re.escape(sym)}.*?(?=^(?:/ES|/NQ|SPY|QQQ|SPX|[A-Z][A-Z /]{{2,}})|\Z)", t, re.M | re.S)
        block = m.group(0) if m else ""
        rows = []
        for lab, kind in (("Resistance", "R"), ("Support", "S"), ("Pivot", "P")):
            mm = re.search(rf"- {lab}:\s*(.+)", block)
            if not mm: continue
            nums = re.findall(r"~?(\d{{3,5}}(?:,\d{{3}})*(?:\.\d+)?)", mm.group(1))
            for n in nums[:5]:
                rows.append((float(n.replace(",", "")), kind, f"{lab.lower()} (weekly frame)"))
        if rows: out[key] = rows
    return out

def conversion_ratios():
    """SPY↔SPX↔ES ratios from site dark-pool convert block (Fri closes), else current defaults.
    Prefer closes when present so the ratio matches the latest session prints already on disk."""
    spy_per, es_minus = 0.099698, 33.93  # Fri 2026-10-30 closes (SPY 755.72 / SPX 7580.07; ES−SPX)
    root = Path(__file__).resolve().parent
    cands = [
        root.parent.parent / "data" / "spy_dark_pool.json",  # site/data when run from pipeline/desk
        Path("/workspace/orb-dash-site/data/spy_dark_pool.json"),
        root / "es_levels" / "darkpool_levels.json",
    ]
    for cand in cands:
        if not cand.exists():
            continue
        try:
            d = json.loads(cand.read_text())
        except Exception:
            continue
        conv = d.get("convert") or d
        closes = (conv.get("closes") or {}) if isinstance(conv, dict) else {}
        try:
            if closes.get("SPY") and closes.get("SPX"):
                spy_per = float(closes["SPY"]) / float(closes["SPX"])
            elif conv.get("spy_per_spx") is not None:
                spy_per = float(conv["spy_per_spx"])
            elif d.get("spy_per_spx") is not None:
                spy_per = float(d["spy_per_spx"])
        except Exception:
            pass
        try:
            if closes.get("ES") is not None and closes.get("SPX") is not None:
                es_minus = float(closes["ES"]) - float(closes["SPX"])
            elif conv.get("es_minus_spx") is not None:
                es_minus = float(conv["es_minus_spx"])
            elif d.get("es_minus_spx") is not None:
                es_minus = float(d["es_minus_spx"])
        except Exception:
            pass
        break
    return round(spy_per, 6), round(es_minus, 2)


def fill_spx(by: dict) -> dict:
    """Ensure KEY LEVELS SPX is populated from existing SPY (preferred) or ES levels.
    plan.json historically omits leading SPX rows — section would render empty.
    Never invent prices: only convert levels already bucketed into SPY/ES."""
    spy_per, es_minus = conversion_ratios()
    explicit = list(by.get("SPX") or [])
    derived = []
    for px, kind, _note in by.get("SPY") or []:
        spx = round(float(px) / spy_per, 2)
        derived.append((spx, kind, f"SPX {spx:g} ≈ SPY {float(px):g} (÷{spy_per:g})"))
    if not derived:
        for px, kind, _note in by.get("ES") or []:
            spx = round(float(px) - es_minus, 2)
            derived.append((spx, kind, f"SPX {spx:g} ≈ ES {float(px):g} (−{es_minus:g})"))
    if not derived:
        return by
    out = list(explicit)
    have = [float(p) for p, _, _ in explicit]
    for px, kind, note in derived:
        if any(abs(px - h) <= 1.0 for h in have):
            continue
        out.append((px, kind, note))
        have.append(px)
    by["SPX"] = out
    return by


def derive_paths(plan, auction_text=""):
    acts = " ".join(plan.get("actionable") or [])
    blob = sanitize_text(acts + "\n" + auction_text)
    bull, bear = [], []
    # Prefer explicit path.bull / path.bear from plan.json when present
    path = plan.get("path") or {}
    if path.get("bull"):
        bull.append(sanitize_text(path["bull"]))
    if path.get("bear"):
        bear.append(sanitize_text(path["bear"]))
    m = re.search(r"Holding above\s+(\d{4})\s+would target\s+(\d{4})\s*/\s*(\d{4})\s*/\s*(\d{4})", blob, re.I)
    m2 = re.search(r"below\s+(\d{4})\s+would target\s+(\d{4})\s*/\s*(\d{4})", blob, re.I)
    if m and not bull:
        bull.append(f"ES: hold <b>{m.group(1)}</b> <span class='ar'>→</span> <b>{m.group(2)}</b> / <b>{m.group(3)}</b> / <b>{m.group(4)}</b>")
    if m2 and not bear:
        bear.append(f"ES: fail <b>{m2.group(1)}</b> <span class='ar'>→</span> <b>{m2.group(2)}</b> / <b>{m2.group(3)}</b>")
    # from actionable hinge line
    m3 = re.search(r"ES:.*?hinge\s+(\d{4}).*?(\d{4})\s*/\s*(\d{4})\s*/\s*(\d{4}).*?fail.*?(\d{4}).*?(\d{4})", acts, re.I)
    if m3 and not bull:
        bull.append(f"ES: hold <b>{m3.group(1)}</b> <span class='ar'>→</span> <b>{m3.group(2)}</b> / <b>{m3.group(3)}</b> / <b>{m3.group(4)}</b>")
        if not bear:
            bear.append(f"ES: fail <b>{m3.group(1)}</b> <span class='ar'>→</span> <b>{m3.group(5)}</b> / <b>{m3.group(6)}</b>")
    # SPY lean
    if re.search(r"end-week\s*≤?\s*760|lean end-week", acts, re.I):
        bear.append("SPY: lean end-week <b>≤760</b> with <b>755</b> Friday node")
    if re.search(r"773\.84", acts):
        bull.append("SPY bull alt: dovish Fed or clean earnings <span class='ar'>→</span> <b>773.84</b> then <b>777.86</b>")
    if not bull:
        bull.append("No structured bull path parsed — see gameplan.")
    if not bear:
        bear.append("No structured bear path parsed — see gameplan.")
    return bull, bear


def catalysts(plan):
    acts = plan.get("actionable") or []
    out = []
    bias = (plan.get("bias") or {}).get("reason") or ""
    if re.search(r"FOMC", bias + " ".join(acts), re.I):
        out.append("FOMC decision <b>2:00</b> PM ET / <b>11:00</b> AM PT — first reaction often the trap; size light")
    for a in acts:
        if re.search(r"MSFT|GOOG|FDX|INTC|AMZN|SNDK|earnings|GDP|PCE|Claims|ECI", a, re.I):
            out.append(sanitize_text(a))
    # dedupe
    seen, uniq = set(), []
    for x in out:
        if x in seen: continue
        seen.add(x); uniq.append(x)
    return uniq or ["No named catalysts in today's plan."]


def fmt_date(d: str) -> str:
    try:
        return datetime.strptime(d, "%Y-%m-%d").strftime("%a %b %d, %Y")
    except Exception:
        return d


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
.bias{display:flex;gap:10px;align-items:flex-start;border:1px solid var(--amb2);border-radius:6px;padding:8px 12px;background:#0b0800;margin:0 0 10px}
.bias .dir{font-size:18px;font-weight:700;letter-spacing:.08em;color:var(--amb)}.bias .dir.up{color:var(--up)}.bias .dir.dn{color:var(--dn)}
.bias .why{flex:1;color:var(--txt);font-size:12px}
.chg{display:grid;grid-template-columns:1fr 1fr;gap:10px}.ch{margin:0}.ch img{width:100%;height:auto;display:block;border:1px solid #333;border-radius:4px}.ch figcaption{color:#9a8a60;font-size:11px;margin-top:3px}
.sc{border:1px dashed var(--amb2);border-radius:6px;padding:6px 10px;margin:6px 0;background:#100c00;font-size:12px}
@media(max-width:700px){body{font-size:13.5px}.grid{grid-template-columns:1fr}.lb{flex-basis:76px}.sec{padding:8px}.chg{grid-template-columns:1fr}}
</style>"""
CSS = CSS[:-8] + _dp.CSS + "</style>"  # inject DP table styles before </style>


def charts_html(site: Path, plan_date: str, score: dict | None):
    d = site / "daily" / "charts"
    CH = [("es", "/ES"), ("nq", "/NQ"), ("spy", "SPY"), ("qqq", "QQQ")]
    have = [(k, n) for k, n in CH if (d / f"{k}.png").exists()]
    if not have: return ""
    v = int(max((d / f"{k}.png").stat().st_mtime for k, _ in have))
    figs = "".join(
        f'<figure class="ch"><a href="charts/{k}.png?v={v}"><img src="charts/{k}.png?v={v}" alt="{n} daily plan chart" loading="lazy"></a>'
        f'<figcaption>{n}</figcaption></figure>' for k, n in have)
    mode = "PLAN vs ACTUAL" if (score or {}).get("have_actual") else "PLAN (pre-session / in-session)"
    sc_html = ""
    if (score or {}).get("have_actual") and score.get("symbols"):
        rows = []
        for k, n in CH:
            s = (score.get("symbols") or {}).get(k)
            if not s: continue
            rows.append(f"<li><span class='lb'>{n}</span><span class='vv'>path <b>{html.escape(s['path'])}</b> · hi <b>{s['high']}</b> / lo <b>{s['low']}</b> · "
                        f"levels hit {len(s.get('levels_hit') or [])}: {html.escape(', '.join(s.get('levels_hit') or [])[:80])}</span></li>")
        if rows:
            sc_html = f'<div class="sc"><b>SCORECARD</b> — {html.escape(plan_date)}<ul>{"".join(rows)}</ul></div>'
    arch = f' Archive: <code>daily/charts/{html.escape(plan_date)}/</code>.'
    return (f'<section class="sec" id="plan-charts"><h2>PLAN ON THE CHART</h2>'
            f'<p>{mode}. Same weekly layout: last week of 30m bars with the plan levels drawn on. '
            f'Red = resistance, green = support, amber = pivot, shaded = key zones. '
            f'Dashed lines = bull / bear paths across Mon to Fri; purple dotted = FOMC Wed 11:00 PT. '
            f'Bright candles in the MON..FRI columns = actual price action since the plan was made.{arch} Tap a chart to enlarge.</p>'
            f'{sc_html}<div class="chg">{figs}</div></section>')


def page(plan, site: Path):
    by = group_levels(plan)
    wf = weekly_frame_levels()
    for k, rows in wf.items():
        if not by.get(k):
            by[k] = rows
    by = fill_spx(by)
    auction = ""
    sp = HERE / "auction_note.md"
    if not sp.exists():
        sp = HERE / "xnews" / "auction" / f"{plan.get('date')}.md"
    if sp.exists():
        auction = sp.read_text(encoding="utf-8", errors="ignore")
    bull, bear = derive_paths(plan, auction)
    cats = catalysts(plan)
    bias = plan.get("bias") or {}
    direction = (bias.get("direction") or "NEUTRAL").upper()
    dcls = "up" if "BULL" in direction or direction == "LONG" else "dn" if "BEAR" in direction or direction == "SHORT" else ""
    date = plan.get("date") or ""
    title = f"ATTACHÉ — DAILY PLAN — {fmt_date(date)}"
    score = {}
    scp = site / "daily" / "scorecard.json"
    if scp.exists():
        try: score = json.loads(scp.read_text())
        except Exception: score = {}

    toc = [("bias-day", "BIAS (DAY)"), ("key-levels", "KEY LEVELS"), ("spy-dark-pool-levels", "SPY Dark Pool levels"), ("bull-path", "BULL PATH"),
           ("bear-path", "BEAR PATH"), ("catalysts", "CATALYSTS / EVENTS"), ("gameplan", "GAMEPLAN"),
           ("plan-charts", "PLAN ON THE CHART")]
    out = [f'<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">'
           f'<title>ATTACHÉ | DAILY PLAN</title><link rel="icon" href="data:,">'
           f'<link href="https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;600;700&display=swap" rel="stylesheet">{CSS}</head><body><main>',
           f'<h1>{html.escape(title)}</h1>', lss_html(plan),
           f'<div class="hd"><div>Plan only — not investment advice · rebuilt from plan.json on every sweep</div>'
           f'<div>Session date: <b>{html.escape(fmt_date(date))}</b> · sources counted in plan: <b>{html.escape(str(plan.get("sources_count", "–")))}</b></div></div>',
           '<nav class="toc">' + "".join(f'<a href="#{i}">{html.escape(lab)}</a>' for i, lab in toc) + "</nav>",
           f'<section class="sec" id="bias-day"><h2>BIAS (DAY)</h2>'
           f'<div class="bias"><div class="dir {dcls}">{html.escape(direction)}</div>'
           f'<div class="why">{esc(sanitize_text(bias.get("reason") or ""))}</div></div></section>']

    # KEY LEVELS
    labels = [("ES", "/ES"), ("SPX", "SPX"), ("SPY", "SPY"), ("QQQ", "QQQ"), ("NQ", "/NQ")]
    cards = []
    for key, lab in labels:
        rows = by.get(key) or []
        if not rows: continue
        items = []
        for px, kind, note in sorted(rows, key=lambda x: -x[0]):
            cls = "res" if kind == "R" else "sup" if kind == "S" else "piv"
            lb = "Resistance" if kind == "R" else "Support" if kind == "S" else "Pivot"
            items.append(f'<li class="{cls}"><span class="lb">{lb}</span><span class="vv"><b>{px:g}</b> — {esc(note)}</span></li>')
        cards.append(f'<div class="tk"><h3>{html.escape(lab)}</h3><ul>{"".join(items)}</ul></div>')
    if not cards:
        cards.append('<div class="tk"><h3>Levels</h3><p class="mut">No key levels in plan.json</p></div>')
    out.append(f'<section class="sec" id="key-levels"><h2>KEY LEVELS</h2><div class="grid">{"".join(cards)}</div></section>')
    out.append(_dp.section_html())

    out.append(f'<section class="sec" id="bull-path"><h2>BULL PATH</h2><ul>' +
               "".join(f'<li><span class="vv">{x}</span></li>' for x in bull) + "</ul></section>")
    out.append(f'<section class="sec" id="bear-path"><h2>BEAR PATH</h2><ul>' +
               "".join(f'<li><span class="vv">{x}</span></li>' for x in bear) + "</ul></section>")
    out.append(f'<section class="sec" id="catalysts"><h2>CATALYSTS / EVENTS</h2><ul>' +
               "".join(f'<li><span class="vv">{esc(c) if "<" not in c else c}</span></li>' for c in cats) + "</ul></section>")

    gp = [sanitize_text(a) for a in (plan.get("actionable") or [])]
    out.append(f'<section class="sec" id="gameplan"><h2>GAMEPLAN</h2><ul>' +
               "".join(f'<li class="nb"><span class="n">{i}</span><span class="vv">{esc(a)}</span></li>'
                       for i, a in enumerate(gp, 1)) +
               ("</ul></section>" if gp else '<li><span class="vv">No actionable items.</span></li></ul></section>'))

    out.append(charts_html(site, date, score))
    out.append('<div class="ft">Plan only. Not investment advice. Levels are plan levels, not live data. Charts use free data only.</div></main></body></html>')
    return "".join(out), title, direction, bias.get("reason") or ""


LSS_MK = "<!--LSS-->"
_PLAN = None
def _im_lines(plan):
    """Implied-move synopsis from the freshly computed implied_move.json; never use a stale session."""
    f = HERE / "xnews" / "implied_move" / "implied_move.json"
    try: im = json.loads(f.read_text())
    except Exception: return ["Implied move unavailable (calc did not produce data this refresh)."], ""
    want = (plan.get("long_story_short") or {}).get("for_session") or plan.get("date")
    if im.get("session_for") != want:
        return [f"Implied move unavailable for {want} (latest calc is for {im.get('session_for')})."], ""
    out = []
    for sym in ("SPY", "SPX", "QQQ"):
        d = (im.get("symbols") or {}).get(sym, {}).get("daily") or {}
        if not d.get("straddle"): continue
        iv = f" · ATM IV {d['atm_iv']*100:.1f}%" if d.get("atm_iv") else ""
        out.append(f"{sym} ±{d['straddle']:g} ({d.get('move_pct', 0):.2f}%) → {d['lower']:g}–{d['upper']:g} off {d.get('ref', 0):g}{iv}")
    return (out or ["Implied move unavailable."]), f"ATM straddle, {im.get('session_for')} expiry · calc {im.get('generated_pt','')}"

def lss_html(plan, compact=False):
    L = plan.get("long_story_short") or {}
    if not L: return ""
    im, im_note = _im_lines(plan)
    st = "margin:8px 10px;padding:10px 14px;border:1px solid #ffb000;border-radius:6px;background:#0b0800;color:#e6e0cc;font:13px/1.55 'IBM Plex Mono',ui-monospace,monospace"
    tag = "color:#000;background:#ffb000;padding:1px 8px;font-weight:700;letter-spacing:.15em;font-size:11px"
    def blk(lab, col, txt): return f'<div style="margin-top:6px"><b style="color:{col}">{lab}</b> {html.escape(sanitize_text(txt))}</div>'
    h = [f'<section id="long-story-short" style="{st}"><span style="{tag}">long story short</span>']
    if L.get("headline"): h.append(f'<b style="color:#ffb000;margin-left:8px">{html.escape(sanitize_text(L["headline"]))}</b>')
    if L.get("context"): h.append(f'<div style="margin-top:6px">{html.escape(sanitize_text(L["context"]))}</div>')
    h.append('<div style="margin-top:6px"><b style="color:#22c7e8">Implied move (daily):</b> ' + " · ".join(html.escape(x) for x in im) +
             (f' <span style="color:#8a8470">({html.escape(im_note)})</span>' if im_note else "") + "</div>")
    if L.get("levels"): h.append(blk("Key levels:", "#ffb000", L["levels"]))
    h.append(blk("Bearish lean:", "#ff4d4d", L.get("bearish", "")))
    h.append(blk("Bullish lean:", "#3ddc5c", L.get("bullish", "")))
    h.append(blk("General lean:", "#ffb000", L.get("general", "")))
    h.append("</section>")
    return LSS_MK + "".join(h) + LSS_MK


def card(title, direction, reason):
    p = reason
    p = (p[:220].rsplit(" ", 1)[0] + "…") if len(p) > 220 else p
    dcol = "#3ddc5c" if "BULL" in direction or direction == "LONG" else "#ff4d4d" if "BEAR" in direction or direction == "SHORT" else "#ffb000"
    return (f'{MK}<a href="../daily/" style="display:block;margin:8px 10px;padding:8px 12px;border:1px solid #a87400;border-radius:6px;background:#0b0800;'
            f'color:#e6e0cc;text-decoration:none;font:12px/1.5 \'IBM Plex Mono\',ui-monospace,monospace"><span style="color:#000;background:#ffb000;'
            f'padding:1px 8px;font-weight:700;letter-spacing:.15em;font-size:11px">DAILY PLAN</span> '
            f'<b style="color:{dcol}">{html.escape(direction)}</b> <b style="color:#ffb000">{html.escape(title.split("—")[-1].strip())}</b>'
            f'<div style="margin-top:4px">{html.escape(p)}</div>'
            f'<div style="color:#22c7e8;margin-top:4px">Open full plan: levels, paths, catalysts, charts →</div></a>{MK}')


def patch_desk(f: Path, title, direction, reason):
    s = f.read_text(encoding="utf-8")
    s = re.sub(re.escape(MK) + ".*?" + re.escape(MK), "", s, flags=re.S)
    # drop anything accidentally appended after </html>
    if "</html>" in s:
        s = s[: s.rfind("</html>") + 7]
    s = re.sub(re.escape(LSS_MK) + ".*?" + re.escape(LSS_MK), "", s, flags=re.S)
    c = card(title, direction, reason)
    wm = re.search(re.escape(WK) + ".*?" + re.escape(WK), s, flags=re.S)
    if wm:
        s = s[: wm.end()] + c + s[wm.end() :]
    else:
        m = re.search(r"<body[^>]*>", s)
        s = s[: m.end()] + c + s[m.end() :] if m else c + s
    lss = lss_html(_PLAN) if _PLAN else ""
    if lss:
        m = re.search(r"<body[^>]*>", s)
        s = s[: m.end()] + lss + s[m.end() :] if m else lss + s
    f.write_text(s, encoding="utf-8")


if __name__ == "__main__":
    site = site_dir()
    daily = site / "daily"; daily.mkdir(parents=True, exist_ok=True)
    # Charts are built by refresh.sh via make_daily_charts.py (must succeed there).
    plan, _ = load_plan(site)
    _PLAN = plan
    h, title, direction, reason = page(plan, site)
    (daily / "index.html").write_text(h, encoding="utf-8")
    print("daily ->", daily / "index.html")
    if "--patch-desk" in sys.argv:
        i = sys.argv.index("--patch-desk")
        f = Path(sys.argv[i + 1])
        patch_desk(f, title, direction, reason)
        print("daily card ->", f)
