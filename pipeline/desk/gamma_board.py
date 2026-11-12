"""Options-positioning board (gamma levels, weekly expected moves, calendar, flow, seasonality).

Input: xnews/positioning/board.json (synced from pipeline/inputs/positioning/board.json).
Renders: a Daily section, a Weekly section, Command tile payload, and the standalone GAMMA MAP page.
Every value is labelled with the board's as-of label (e.g. '11/9 close'). Missing values render as plain
status text ('awaiting update' / 'not posted'), never raw errors. No source names are stored or rendered."""
from __future__ import annotations
import html, json, math, re, sys, hashlib
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
AWAIT = "awaiting update"
NP = "not posted"
SYMS = ("SPX", "SPY", "QQQ", "NDX")
FIELDS = (("regime", "Regime"), ("net_gex", "Net GEX"), ("flip", "Flip"), ("magnet", "Magnet"),
          ("put_wall", "Put wall"), ("call_wall", "Call wall"))
MK = "<!--GAMMABOARD-->"
E = html.escape


# ---------------- load / validate ----------------
def _num(v):
    if isinstance(v, bool) or not isinstance(v, (int, float)):
        return None
    return float(v) if math.isfinite(v) and v > 0 else None


def _iso(s):
    try:
        return date.fromisoformat(s) if isinstance(s, str) and re.fullmatch(r"\d{4}-\d{2}-\d{2}", s) else None
    except ValueError:
        return None


def load(path: Path | None = None) -> dict:
    path = Path(path or HERE / "xnews" / "positioning" / "board.json")
    try:
        d = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return validate(d)


def validate(d) -> dict:
    """Drop anything malformed; keep the rest. Returns {} when the board itself is unusable."""
    if not isinstance(d, dict) or not _iso(d.get("asof")) or not isinstance(d.get("asof_label"), str):
        return {}
    out = dict(d)
    lv = {}
    for s in SYMS:
        per = (d.get("levels") or {}).get(s) or {}
        lv[s] = {}
        for ex in d.get("expiries") or []:
            r = per.get(ex)
            if not isinstance(r, dict) or not _iso(ex):
                lv[s][ex] = None
                continue
            c = {}
            for k in ("flip", "magnet", "put_wall", "call_wall"):
                c[k] = _num(r.get(k))
            c["net_gex"] = r.get("net_gex") if isinstance(r.get("net_gex"), str) and re.fullmatch(r"[+-−]?\$[\d.]+[KMB]", r["net_gex"]) else None
            c["regime"] = r.get("regime") if r.get("regime") in ("POS", "NEG") else None
            c["put_wall_note"] = r.get("put_wall_note") if isinstance(r.get("put_wall_note"), str) else ""
            lv[s][ex] = c if any(c[k] is not None for k in ("flip", "magnet", "put_wall", "call_wall")) else None
    out["levels"] = lv
    b = _num((d.get("basis") or {}).get("ES_minus_SPX"))
    out["es_basis"] = b if b is not None and b < 200 else None
    nq = (d.get("basis") or {}).get("NQ_minus_NDX")
    out["nq_basis"] = float(nq) if isinstance(nq, (int, float)) and not isinstance(nq, bool) and math.isfinite(nq) else None
    em = d.get("weekly_em") or {}
    rows = []
    for r in em.get("rows") or []:
        lo, hi = _num(r.get("lower")), _num(r.get("upper"))
        if r.get("symbol") in SYMS and lo and hi and lo < hi and hi / lo < 1.25:
            rows.append({"symbol": r["symbol"], "lower": lo, "upper": hi, "pct": _num(r.get("pct"))})
    out["weekly_em"] = {"expiry": em.get("expiry") if _iso(em.get("expiry")) else None, "rows": rows}
    out["close"] = {s: _num((d.get("close") or {}).get(s)) for s in SYMS}
    return out


# ---------------- formatting ----------------
def day(dt: date) -> str:
    return f"{dt:%a} {dt.month}/{dt.day}"


def ex_label(ex: str) -> str:
    d = _iso(ex)
    return f"{d.month}/{d.day}" if d else ex


def f(x, nd=None):
    if x is None:
        return None
    if nd is None:
        nd = 0 if abs(x - round(x)) < 1e-9 else (1 if abs(x * 10 - round(x * 10)) < 1e-6 else 2)
    return f"{x:,.{nd}f}".replace(",", "") if x < 10000 else f"{x:.{nd}f}"


def es_of(data, x):
    return None if x is None or data.get("es_basis") is None else round(x + data["es_basis"], 2)


def cell(v, note=""):
    if v is None:
        return f'<td class="gb-na">{NP}</td>'
    return f'<td>{E(v)}{(" <small>" + E(note) + "</small>") if note else ""}</td>'


def regime_td(r):
    if r is None:
        return f'<td class="gb-na">{NP}</td>'
    return '<td class="gb-pos">positive</td>' if r == "POS" else '<td class="gb-neg">negative</td>'


CSS = """<style id="gb-css">
.gb-t{border-collapse:collapse;width:100%;font-variant-numeric:tabular-nums;font-size:12px}
.gb-t th{color:var(--mut,#857d6a);font-weight:600;text-align:right;padding:3px 6px;border-bottom:1px solid #333;font-size:11px;letter-spacing:.04em;text-transform:uppercase}
.gb-t td{text-align:right;padding:3px 6px;border-bottom:1px dotted #1c1c1c;color:#e6e0cc;white-space:nowrap}
.gb-t th:first-child,.gb-t td:first-child,.gb-t th:nth-child(2),.gb-t td:nth-child(2){text-align:left}
.gb-t td.gb-na{color:#6b6355;font-size:11px}.gb-t td.gb-pos{color:#3ddc5c}.gb-t td.gb-neg{color:#ff4d4d}
.gb-t td small{color:#857d6a}.gb-t tr.gb-cv td{color:#c9b98a}.gb-t tr.gb-cv td:first-child{color:#ffb000}
.gb-t td.gb-aw{text-align:left;color:#ffb000;font-size:11px}
.gb-n{color:#857d6a;font-size:11px;margin:4px 0}.gb-n b{color:#e6e0cc}
.gb-l{display:inline-block;margin-top:4px;color:#22c7e8;text-decoration:none;font-size:12px}
.gb-w{overflow-x:auto}
</style>"""


def table(data, expiries, syms=SYMS, with_es=True, with_nq=True):
    asof = data["asof_label"]
    h = ['<div class="gb-w ux-tw"><table class="gb-t"><tr><th>Ticker</th><th>Expiry</th>' +
         "".join(f"<th>{E(n)}</th>" for _, n in FIELDS) + "</tr>"]
    for s in syms:
        for ex in expiries:
            r = data["levels"].get(s, {}).get(ex)
            if r is None:
                h.append(f'<tr><td>{s}</td><td>{ex_label(ex)}</td><td class="gb-aw" colspan="{len(FIELDS)}">{AWAIT} · not captured at the {E(asof)}</td></tr>')
                continue
            h.append(f"<tr><td>{s}</td><td>{ex_label(ex)}</td>" + regime_td(r["regime"]) + cell(r["net_gex"]) +
                     cell(f(r["flip"])) + cell(f(r["magnet"])) + cell(f(r["put_wall"]), r.get("put_wall_note", "")) +
                     cell(f(r["call_wall"])) + "</tr>")
        if s == "SPX" and with_es:
            for ex in expiries:
                r = data["levels"]["SPX"].get(ex)
                if r is None or data.get("es_basis") is None:
                    h.append(f'<tr class="gb-cv"><td>ES</td><td>{ex_label(ex)}</td><td class="gb-aw" colspan="{len(FIELDS)}">{AWAIT}</td></tr>')
                    continue
                h.append(f'<tr class="gb-cv"><td>ES <small>≈SPX+{f(data["es_basis"], 2)}</small></td><td>{ex_label(ex)}</td>' +
                         regime_td(r["regime"]) + '<td class="gb-na">as SPX</td>' +
                         "".join(cell(f(es_of(data, r[k]), 2) if r[k] is not None else None) for k in ("flip", "magnet", "put_wall", "call_wall")) + "</tr>")
        if s == "NDX" and with_nq:
            if data.get("nq_basis") is None:
                h.append(f'<tr class="gb-cv"><td>NQ</td><td>all</td><td class="gb-aw" colspan="{len(FIELDS)}">{AWAIT} · no sourced NQ–NDX basis; NDX levels above are in NDX points</td></tr>')
    h.append("</table></div>")
    return "".join(h)


def em_rows(data):
    em = data.get("weekly_em") or {}
    d = _iso(em.get("expiry") or "")
    if not d or not em.get("rows"):
        return f"Weekly expected move: {AWAIT}", []
    lab = f"Weekly expected move to Fri {d.month}/{d.day} ({data['asof_label']})"
    return lab, [(r["symbol"], f"{f(r['lower'], 2)}–{f(r['upper'], 2)}" + (f" (±{r['pct']:.2f}%)" if r.get("pct") else "")) for r in em["rows"]]


def em_line(data):
    lab, rows = em_rows(data)
    return lab + (": " + " · ".join(f"{s} {v}" for s, v in rows) if rows else "")


def calendar_rows(data):
    out = []
    for c in data.get("calendar") or []:
        d = _iso(c.get("date"))
        if not d:
            continue
        out.append({"day": day(d), "date": c["date"], "utc": c.get("utc"), "pt": c.get("pt"),
                    "name": c.get("name"), "detail": c.get("detail") or "no scheduled release"})
    return out


def calendar_html(data):
    rows = calendar_rows(data)
    if not rows:
        return f'<p class="gb-n">Catalysts: {AWAIT}</p>'
    return ('<div class="gb-w ux-tw"><table class="gb-t"><tr><th>Day (PT)</th><th>Event</th></tr>' +
            "".join(f"<tr><td>{E(r['day'])} {E(r['pt'] or '')}</td><td style=\"text-align:left\">{E(r['detail'])}</td></tr>" for r in rows) +
            "</table></div>")


def seasonality_html(data):
    S = data.get("seasonality") or {}
    if not S:
        return f'<p class="gb-n">Seasonality: {AWAIT}</p>'
    return "".join(f'<p class="gb-n"><b>{E(k)}</b> · {E(v.get("week", AWAIT))} · {E(v.get("month", AWAIT))}</p>' for k, v in S.items()) + \
        '<p class="gb-n">Historical description, not a forecast.</p>'


def flow_html(data):
    F = data.get("flow") or {}
    if not F.get("net"):
        return f'<p class="gb-n">Flow: {AWAIT}</p>'
    return (f'<p class="gb-n"><b>{E(F["net"])} {E(F.get("lean", ""))}</b> · {F.get("prints", 0):,} prints · calls {E(F.get("calls", ""))} / puts {E(F.get("puts", ""))} · put/call {F.get("put_call")} <small>({E(F.get("scope", ""))})</small></p>' +
            "".join(f'<p class="gb-n">SPY: {E(x)}</p>' for x in F.get("spy_notable") or []) +
            (f'<p class="gb-n">{E(F["spy_directional"])}</p>' if F.get("spy_directional") else ""))


# ---------------- page sections ----------------
def _sec(sid, title, body):
    return f'{MK}<section class="sec" id="{sid}"><h2>{E(title)}</h2>{body}</section>{MK}'


def daily_section(data):
    if not data:
        return _sec("gamma-levels", "GAMMA LEVELS", f'<p class="gb-n">{AWAIT}</p>')
    ex = data["expiries"][0]
    body = (f'<p class="gb-n">Options positioning for the <b>{ex_label(ex)}</b> expiry · <b>{E(data["asof_label"])}</b>. '
            f'Regime is for this single expiry. ES = SPX + {f(data["es_basis"], 2)} (plan basis).</p>' +
            table(data, [ex]) + f'<p class="gb-n">{E(em_line(data))}</p>' +
            '<a class="gb-l" href="../gammamap/">Gamma map: walls, flips and bands vs plan levels →</a>')
    return _sec("gamma-levels", f"GAMMA LEVELS · {data['asof_label'].upper()}", body)


def weekly_section(data):
    if not data:
        return _sec("gamma-week", "GAMMA LEVELS · WEEK", f'<p class="gb-n">{AWAIT}</p>')
    body = (f'<p class="gb-n">All three expiries, <b>{E(data["asof_label"])}</b>. Regime is per expiry.</p>' +
            table(data, data["expiries"]) + f'<p class="gb-n">{E(em_line(data))}</p>' +
            f'<h2 style="margin-top:8px">CATALYSTS · REST OF WEEK (PT) · {E(data["asof_label"].upper())}</h2>' + calendar_html(data) +
            f'<h2 style="margin-top:8px">SEASONALITY · {E(data["asof_label"].upper())}</h2>' + seasonality_html(data) +
            '<a class="gb-l" href="../gammamap/">Open the gamma map →</a>')
    return _sec("gamma-week", f"GAMMA LEVELS · WEEK · {data['asof_label'].upper()}", body)


def patch_section(path: Path, section: str, anchor='<div class="ft">'):
    t = Path(path).read_text(encoding="utf-8")
    t = re.sub(re.escape(MK) + ".*?" + re.escape(MK), "", t, flags=re.S)
    t = t.replace('<style id="gb-css">', '<style id="gb-css-old">')
    t = re.sub(r'<style id="gb-css-old">.*?</style>', "", t, flags=re.S)
    i = t.rfind(anchor)
    if i < 0:
        i = t.rfind("</main>")
    if i < 0:
        raise SystemExit(f"no anchor in {path}")
    t = t[:i] + CSS + section + t[i:]
    Path(path).write_text(t, encoding="utf-8")


# ---------------- command payload ----------------
def command_payload(data):
    if not data:
        return {"board": None}
    a = data["asof_label"]
    lab, rows = em_rows(data)
    ex0 = data["expiries"][0]
    def mini(s):
        r = data["levels"][s].get(ex0)
        if r is None:
            return [s, AWAIT]
        parts = [("+" if r["regime"] == "POS" else "−") + "γ" if r["regime"] else None,
                 f"flip {f(r['flip'])}" if r["flip"] else None, f"magnet {f(r['magnet'])}" if r["magnet"] else None]
        return [s, " · ".join(p for p in parts if p)]
    es = data["levels"]["SPX"].get(ex0)
    es_rows = []
    for ex in data["expiries"]:
        r = data["levels"]["SPX"].get(ex)
        if r and data.get("es_basis") is not None:
            es_rows.append([f"ES {ex_label(ex)}", " · ".join(x for x in [
                f"flip {f(es_of(data, r['flip']), 2)}" if r["flip"] else None,
                f"magnet {f(es_of(data, r['magnet']), 2)}" if r["magnet"] else None,
                f"PW {f(es_of(data, r['put_wall']), 2)}" if r["put_wall"] else None,
                f"CW {f(es_of(data, r['call_wall']), 2)}" if r["call_wall"] else None] if x)])
    es_rows.append(["NQ", f"{AWAIT} (no sourced basis; NDX shown in NDX points)" if data.get("nq_basis") is None else "see map"])
    F = data.get("flow") or {}
    S = data.get("seasonality") or {}
    return {
        "board": {"asof_label": a, "expiries": [ex_label(x) for x in data["expiries"]]},
        "im_extra": {"label": lab, "rows": rows},
        "calendar": calendar_rows(data),
        "tiles": [
            {"h": "ES · NQ LEVELS", "d": a, "c": "var(--gn)", "rows": es_rows, "note": f"ES = SPX + {f(data['es_basis'], 2)} plan basis"},
            {"h": "FLOW", "d": a, "c": "var(--up)", "v": f"{F.get('net', AWAIT)} {F.get('lean', '')}".strip(),
             "rows": [["prints", f"{F.get('prints', 0):,}"], ["calls / puts", f"{F.get('calls', '–')} / {F.get('puts', '–')}"], ["put/call", str(F.get("put_call", "–"))]] +
                     [["SPY", x] for x in F.get("spy_notable") or []],
             "note": F.get("spy_directional", "")} if F.get("net") else
            {"h": "FLOW", "d": a, "c": "var(--up)", "v": "—", "rows": [], "note": AWAIT},
            {"h": "SEASONALITY", "d": a, "c": "var(--pu)",
             "rows": [[f"{k} week", v.get("week", AWAIT).split(": ", 1)[-1]] for k, v in S.items()] + [[f"{k} Nov", v.get("month", AWAIT).split(": ", 1)[-1]] for k, v in S.items()],
             "note": "Week 46 and November history · not a forecast"},
        ],
        "gamma": {"h": f"GAMMA LEVELS · {a}", "html": table(data, data["expiries"])},
    }


def _stamp_now():
    pt = timezone(timedelta(hours=-8))  # PST (site convention: PT labels)
    n = datetime.now(timezone.utc).astimezone(pt)
    return f"{n:%a} {n:%b} {n.day}, {n:%Y} {n:%I:%M %p} PT".replace(" 0", " ")


def patch_command(path: Path, data):
    t = Path(path).read_text(encoding="utf-8")
    m = re.search(r'(<script id="glance-data" type="application/json">)(.*?)(</script>)', t, re.S)
    if not m:
        return False
    G = json.loads(m.group(2))
    P = command_payload(data)
    G.update(P)
    cal = P.get("calendar") or []
    if cal:
        G["catalysts"] = {"date_label": f"{cal[0]['day']} – {cal[-1]['day']} · {data['asof_label']}",
                          "items": [c for c in cal], "other": "times PT · scheduled releases only"}
    # real last-update stamp: changes only when page content (minus the stamp) changes
    body = (t[:m.start()] + t[m.end():])
    body = re.sub(r"<!--UPD:[0-9a-f]+-->", "", body)
    core = json.dumps({k: v for k, v in G.items() if k not in ("updated_pt", "content_hash")}, sort_keys=True, ensure_ascii=False)
    h = hashlib.sha1((re.sub(r"[?&]v=\d+", "", body) + core).encode()).hexdigest()[:12]
    if G.get("content_hash") != h or not G.get("updated_pt"):
        G["updated_pt"] = _stamp_now()
        G["content_hash"] = h
    t = t[:m.start()] + m.group(1) + json.dumps(G, ensure_ascii=False).replace("</", "<\\/") + m.group(3) + t[m.end():]
    Path(path).write_text(t, encoding="utf-8")
    return True


# ---------------- gamma map page ----------------
KIND = {"flip": ("FLIP", "#22c7e8"), "magnet": ("MAGNET", "#ffb000"), "put_wall": ("PUT WALL", "#3ddc5c"),
        "call_wall": ("CALL WALL", "#ff4d4d"), "em": ("WEEK EM", "#a06ae0"), "plan": ("PLAN", "#e6e0cc")}


def plan_levels(plan: dict | None, weekly_spy: list | None = None):
    """ES plan levels from plan.json key_levels: list of (lo, hi, label)."""
    out = []
    for k in (plan or {}).get("key_levels") or []:
        p = _num(k.get("price"))
        if p is None:
            continue
        m = re.search(r"ES (\d{4})(?:\s*[–-]\s*(\d{1,4}))?", k.get("note", ""))
        lo = hi = p
        lab = str(int(p))
        if m:
            a = float(m.group(1))
            b = m.group(2)
            if b:
                bb = float(m.group(1)[: 4 - len(b)] + b)
                lo, hi = min(a, bb), max(a, bb)
                lab = f"{m.group(1)}–{b}"
            else:
                lo = hi = a
                lab = m.group(1)
        kind = "pivot" if "pivot" in k.get("note", "").lower() else ("res" if "resist" in k.get("note", "").lower() else "sup")
        out.append((lo, hi, lab, kind))
    return out


def items_for(data, sym, plan_lv, spy_week=None):
    """(lo, hi, column, kind, text) for one ticker's ladder."""
    it = []
    cols = [ex_label(x) for x in data["expiries"]]
    src = "SPX" if sym == "ES" else sym
    conv = (lambda x: es_of(data, x)) if sym == "ES" else (lambda x: x)
    for ex, col in zip(data["expiries"], cols):
        r = data["levels"].get(src, {}).get(ex)
        if not r:
            continue
        for k in ("call_wall", "flip", "magnet", "put_wall"):
            if r[k] is not None:
                v = conv(r[k])
                it.append((v, v, col, k, f(v, 2 if sym == "ES" else None)))
    for r in (data.get("weekly_em") or {}).get("rows") or []:
        if r["symbol"] == src:
            for v in (r["lower"], r["upper"]):
                v = conv(v)
                it.append((v, v, "Wk EM", "em", f(v, 2)))
    b = data.get("es_basis")
    if sym == "ES":
        for lo, hi, lab, kind in plan_lv:
            it.append((lo, hi, "Plan", "plan", f"{lab} {kind}"))
    elif sym == "SPX" and b is not None:
        for lo, hi, lab, kind in plan_lv:
            it.append((round(lo - b, 2), round(hi - b, 2), "Plan", "plan",
                       f"{f(round(lo - b, 2), 2)}{'–' + f(round(hi - b, 2), 2) if hi != lo else ''} {kind} (ES {lab})"))
    elif sym == "SPY" and spy_week:
        for lo, hi, lab, kind in spy_week:
            it.append((lo, hi, "Plan", "plan", f"{lab} {kind} (week)"))
    return it


def clusters(items, tol):
    items = sorted(items, key=lambda x: -x[1])
    out = []
    for x in items:
        if out and out[-1]["lo"] - x[1] <= tol:
            c = out[-1]
            c["lo"] = min(c["lo"], x[0]); c["items"].append(x)
        else:
            out.append({"hi": x[1], "lo": x[0], "items": [x]})
    return out


def spy_week_levels(path: Path | None = None):
    """SPY levels from the weekly plan text (KEY LEVELS > SPY). Empty list if not found."""
    p = path or HERE / "xnews" / "plans"
    files = sorted(Path(p).glob("*weekly*.txt")) if Path(p).is_dir() else []
    if not files:
        return []
    t = files[-1].read_text(encoding="utf-8")
    m = re.search(r"^SPY\n(.*?)(?:\n\n|\Z)", t, re.S | re.M)
    if not m:
        return []
    out = []
    for line in m.group(1).splitlines():
        kind = "res" if "Resist" in line else "pivot" if "Pivot" in line else "sup" if "Support" in line else None
        if not kind:
            continue
        for a, b in re.findall(r"(\d{3}(?:\.\d+)?)(?:\s*[–-]\s*(\d{3}(?:\.\d+)?))?", line.split(":", 1)[-1]):
            lo, hi = float(a), float(b or a)
            out.append((min(lo, hi), max(lo, hi), f"{a}{'–' + b if b else ''}", kind))
    return out


def map_page(data, plan, spy_week=None, built=""):
    a = data.get("asof_label", "") if data else ""
    title = "ATTACHÉ — GAMMA MAP"
    head = (f'<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">'
            f'<title>{title}</title>{MAP_CSS}</head><body><main>')
    if not data:
        return head + f'<h1>GAMMA MAP</h1><p class="hd">{AWAIT}</p></main></body></html>'
    cols = [ex_label(x) for x in data["expiries"]] + ["Wk EM", "Plan"]
    plan_date = (plan or {}).get("date") or ""
    pd = _iso(plan_date)
    pl = plan_levels(plan)
    h = [head, f'<h1>GAMMA MAP</h1><div class="hd"><div>Walls, flips, magnets and weekly expected-move bands by expiry, stacked against the '
         f'{"<b>" + day(pd) + "</b> " if pd else ""}plan levels · positioning <b>{E(a)}</b>.</div>'
         f'<div>Rows merge levels within 0.10% of price. <span class="cf">Highlighted</span> rows = confluence (2+ columns agree); '
         f'darker heat = more levels stacked.</div></div>',
         '<div class="key">' + "".join(f'<span style="--k:{c}">{n}</span>' for n, c in KIND.values()) + f'<span class="sp">◆ {E(a)}</span></div>',
         '<nav class="toc">' + "".join(f'<a href="#m-{s.lower()}">{s}</a>' for s in ("ES", "SPX", "SPY", "QQQ", "NDX", "NQ")) + "</nav>"]
    for sym in ("ES", "SPX", "SPY", "QQQ", "NDX", "NQ"):
        if sym == "NQ" and data.get("nq_basis") is None:
            h.append(f'<section class="tk" id="m-nq"><h2>NQ <small>{E(a)}</small></h2><p class="st">{AWAIT} · no sourced NQ–NDX basis, so no NQ conversion is shown. '
                     f'See <a href="#m-ndx">NDX</a> (NDX points).</p></section>')
            continue
        src = "SPX" if sym == "ES" else sym
        spot = data["close"].get(src)
        spot_v = es_of(data, spot) if sym == "ES" else spot
        its = items_for(data, sym, pl, spy_week if sym == "SPY" else None)
        if not its:
            h.append(f'<section class="tk" id="m-{sym.lower()}"><h2>{sym} <small>{E(a)}</small></h2><p class="st">{AWAIT}</p></section>')
            continue
        ref = spot_v or its[0][0]
        tol = ref * 0.001
        cl = clusters(its, tol)
        missing = [ex_label(ex) for ex in data["expiries"] if not data["levels"].get(src, {}).get(ex)]
        plan_note = {"ES": f"Plan = {day(pd) if pd else ''} ES plan levels", "SPX": f"Plan = {day(pd) if pd else ''} ES plan levels − {f(data['es_basis'], 2)}",
                     "SPY": "Plan = this week's SPY plan levels (Tue SPY intraday levels awaiting update)" if spy_week else f"Plan: {AWAIT}",
                     }.get(sym, f"Plan: {sym} plan levels {AWAIT}")
        sub = []
        if sym == "ES":
            sub.append(f"ES ≈ SPX + {f(data['es_basis'], 2)} (plan basis) · SPX close {f(spot, 2)} + basis ≈ {f(spot_v, 2)} (not an ES print)")
        else:
            sub.append(f"close {f(spot_v, 2)}")
        if missing:
            sub.append(f"{', '.join(missing)} expiry: {AWAIT}")
        sub.append(plan_note)
        rows = []
        spot_done = False
        for c in cl:
            if spot_v is not None and not spot_done and spot_v > c["hi"]:
                rows.append(f'<tr class="spot"><td>◆ {f(spot_v, 2)}</td><td colspan="{len(cols)}">{E(a)}{" (SPX close + basis)" if sym == "ES" else ""}</td></tr>')
                spot_done = True
            ncol = len({x[2] for x in c["items"]})
            heat = min(len(c["items"]), 5)
            cf = ncol >= 2
            lab = f(c["hi"]) if abs(c["hi"] - c["lo"]) < 1e-9 else f"{f(c['lo'])}–{f(c['hi'])}"
            tds = []
            for col in cols:
                xs = [x for x in c["items"] if x[2] == col]
                if not xs:
                    tds.append('<td class="e">·</td>')
                    continue
                tds.append('<td class="h">' + "".join(f'<span class="tag" style="--k:{KIND[x[3]][1]}" title="{E(x[4])}">{KIND[x[3]][0]} <b>{E(x[4])}</b></span>' for x in xs) + "</td>")
            rows.append(f'<tr class="lv{" cf" if cf else ""}" style="--heat:{heat}"><td>{lab}{" <i>CONFLUENCE</i>" if cf else ""}</td>{"".join(tds)}</tr>')
        if spot_v is not None and not spot_done:
            rows.append(f'<tr class="spot"><td>◆ {f(spot_v, 2)}</td><td colspan="{len(cols)}">{E(a)}{" (SPX close + basis)" if sym == "ES" else ""}</td></tr>')
        h.append(f'<section class="tk" id="m-{sym.lower()}"><h2>{sym} <small>{E(a)}</small></h2><p class="st">{E(" · ".join(sub))}</p>'
                 f'<div class="w ux-tw"><table class="hm"><tr><th>Level</th>{"".join(f"<th>{E(x)}</th>" for x in cols)}</tr>{"".join(rows)}</table></div></section>')
    h.append(f'<section class="tk" id="m-cal"><h2>CATALYSTS · REST OF WEEK (PT) <small>{E(a)}</small></h2>{calendar_html(data)}</section>')
    h.append(f'<div class="ft">Positioning is descriptive, recorded at the {E(a)}; not a forecast and not investment advice. '
             f'Expected-move bands are not guaranteed limits. Built {E(built)}.</div></main></body></html>')
    return "".join(h)


MAP_CSS = """<style>
:root{--bg:#000;--ln:#232323;--ln2:#333;--amb:#ffb000;--amb2:#a87400;--txt:#e6e0cc;--mut:#857d6a;--up:#3ddc5c;--dn:#ff4d4d;--cy:#22c7e8}
*{box-sizing:border-box}body{margin:0;background:#000;color:var(--txt);font:13px/1.55 'IBM Plex Mono',ui-monospace,Menlo,Consolas,monospace;font-variant-numeric:tabular-nums}
main{max-width:1100px;margin:0 auto;padding:10px 12px 40px}h1{color:var(--amb);font-size:16px;letter-spacing:.12em;margin:8px 0 4px}
.hd{color:var(--mut);font-size:12px;margin:0 0 8px}.hd div{margin:2px 0}.hd b{color:var(--txt)}
.toc{display:flex;flex-wrap:wrap;gap:4px;margin:0 0 10px}.toc a{color:var(--amb);border:1px solid var(--ln2);border-radius:6px;padding:4px 9px;font-size:11px;text-decoration:none}.toc a:hover{background:var(--amb);color:#000}
.key{display:flex;flex-wrap:wrap;gap:6px;margin:0 0 8px;font-size:10px}.key span{border:1px solid var(--k,#555);color:var(--k,#ccc);padding:1px 6px;border-radius:3px;letter-spacing:.06em}
.key .sp{border-color:var(--amb);color:var(--amb)}
.cf{background:#2a1d00;color:var(--amb);padding:0 4px}
.tk{border:1px solid var(--ln2);border-radius:6px;background:#070707;margin:0 0 10px;padding:8px 12px}
.tk>h2{color:#000;background:var(--amb);display:inline-block;font-size:11px;letter-spacing:.15em;padding:1px 8px;margin:0 0 4px}.tk>h2 small{color:#3b2a00;margin-left:6px;letter-spacing:.04em}
.st{color:var(--mut);font-size:11px;margin:2px 0 6px}.st a{color:var(--cy)}
.w{overflow-x:auto}
table.hm{border-collapse:collapse;width:100%;font-size:11px}
.hm th{color:var(--mut);font-weight:600;text-align:left;padding:3px 6px;border-bottom:1px solid var(--ln2);font-size:10px;letter-spacing:.06em;text-transform:uppercase}
.hm td{padding:3px 6px;border-bottom:1px solid #121212;vertical-align:top}
.hm td:first-child{white-space:nowrap;color:var(--txt);font-weight:600;width:150px}
.hm tr.lv td.h{background:rgba(255,176,0,calc(var(--heat,1)*.045))}
.hm td.e{color:#2b2b2b;text-align:center}
.hm tr.cf td{box-shadow:inset 0 1px 0 #3a2a00,inset 0 -1px 0 #3a2a00}.hm tr.cf td:first-child{box-shadow:inset 3px 0 0 var(--amb);color:var(--amb)}
.hm tr.cf i{font-style:normal;font-size:9px;color:#000;background:var(--amb);padding:0 4px;margin-left:4px;letter-spacing:.08em}
.hm tr.spot td{color:var(--amb);background:#120d00;font-weight:700;border-top:1px dashed var(--amb2);border-bottom:1px dashed var(--amb2)}
.tag{display:inline-block;border-left:3px solid var(--k);padding:0 5px;margin:1px 4px 1px 0;color:var(--k);font-size:10px;letter-spacing:.04em;background:#0b0b0b}
.tag b{color:var(--txt);font-weight:600}
.gb-t{border-collapse:collapse;width:100%;font-size:12px}.gb-t th{color:var(--mut);text-align:left;padding:3px 6px;border-bottom:1px solid #333;font-size:11px}.gb-t td{padding:3px 6px;border-bottom:1px dotted #1c1c1c}.gb-w{overflow-x:auto}
.gb-n{color:var(--mut);font-size:11px}
.ft{color:var(--mut);font-size:11px;margin-top:12px}
@media(max-width:700px){.hm td:first-child{width:auto}.tk{padding:8px}}
</style>"""


def main(argv):
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--board", default=None)
    ap.add_argument("--plan", default=None)
    ap.add_argument("--patch-daily"); ap.add_argument("--patch-weekly"); ap.add_argument("--patch-command")
    ap.add_argument("--page")
    a = ap.parse_args(argv)
    data = load(a.board)
    plan = {}
    for p in [a.plan, HERE.parent / "inputs" / "plan.json", HERE / "daily" / "plan.json"]:
        if p and Path(p).exists():
            try:
                plan = json.loads(Path(p).read_text()); break
            except Exception:
                pass
    if a.patch_daily and Path(a.patch_daily).exists():
        patch_section(Path(a.patch_daily), daily_section(data))
    if a.patch_weekly and Path(a.patch_weekly).exists():
        patch_section(Path(a.patch_weekly), weekly_section(data))
    if a.patch_command and Path(a.patch_command).exists():
        patch_command(Path(a.patch_command), data)
    if a.page:
        Path(a.page).parent.mkdir(parents=True, exist_ok=True)
        sw = spy_week_levels(HERE.parent / "inputs" / "plans") or spy_week_levels()
        Path(a.page).write_text(map_page(data, plan, sw, _stamp_now()), encoding="utf-8")
    print("gamma_board: ok" if data else "gamma_board: board awaiting update")


if __name__ == "__main__":
    main(sys.argv[1:])
