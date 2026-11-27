"""COMMAND CENTER page builder (/command/). Rebuilds the whole page from data on every refresh.

Live inputs (refreshed by the 15-minute GitHub Actions run):
  es_levels/overnight.json            delayed futures quotes (ES, VIX)
  xnews/implied_move/implied_move.json next-session and week expected-move bands
  inputs/orb/orb_status.json           ORB15, hourly breaks, cumulative R, bot box (1m bars)
  es_levels/bias_gauge.json            composite bias
  inputs/journal/v2_log.json           journal
Sweep inputs (written by the nightly sweep, read-only here):
  inputs/command_center/sweep.json     plan, scenarios, reads, sweep topics, dark-pool lines, gamma notes
  inputs/positioning/board.json        options positioning board, calendar, flow, seasonality
Every block carries an as-of. A sweep block whose session has already traded is dimmed and labelled, never shown as current.
usage: command_center.py <command/index.html>"""
import html, json, os, re, statistics, sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

DESK = Path(__file__).resolve().parent
INP = Path(os.environ.get("ORB_INPUTS", DESK.parent / "inputs"))
PT, ET = ZoneInfo("America/Los_Angeles"), ZoneInfo("America/New_York")
E = html.escape
CSS = (DESK / "command_center.css").read_text(encoding="utf-8")
ORB_JS = (DESK / "command_center_orb.js").read_text(encoding="utf-8")


def jload(p, default=None):
    try:
        return json.loads(Path(p).read_text(encoding="utf-8"))
    except Exception:
        return default


def dlab(d):  # 2026-11-20 -> Fri 11/20
    d = date.fromisoformat(d) if isinstance(d, str) else d
    return f"{d.strftime('%a')} {d.month}/{d.day}"


def fnum(x, nd=2):
    return "—" if x is None else f"{x:,.{nd}f}"


# ------------------------------------------------------------------ load
def load():
    S = {}
    S["sweep"] = jload(INP / "command_center" / "sweep.json", {}) or {}
    S["board"] = jload(INP / "positioning" / "board.json", {}) or {}
    S["orb"] = jload(INP / "orb" / "orb_status.json", {}) or {}
    S["journal"] = jload(INP / "journal" / "v2_log.json", {}) or {}
    S["im"] = jload(DESK / "xnews" / "implied_move" / "implied_move.json", {}) or {}
    S["on"] = jload(DESK / "es_levels" / "overnight.json", {}) or {}
    S["bias"] = jload(DESK / "es_levels" / "bias_gauge.json", {}) or {}
    return S


def quote(on, code):
    for g in on.get("groups") or []:
        for r in g.get("rows") or []:
            if r.get("code") == code and r.get("q") and r["q"].get("last") is not None:
                q = dict(r["q"])
                try:  # '11/20 16:55' is ET (board generated_et carries the year)
                    yr = int(str(on.get("generated_et", ""))[:4])
                    t = datetime.strptime(f"{yr}/{q['asof']}", "%Y/%m/%d %H:%M").replace(tzinfo=ET).astimezone(PT)
                    q["t"] = t
                    q["label"] = t.strftime("%a %-m/%-d %-I:%M %p PT")
                except Exception:
                    q["t"], q["label"] = None, "time not posted"
                return q
    return None



def _zone(p, lab):
    """(low, high) of a plan label: '7211–23' -> (7211, 7223); a single number -> (p, p)."""
    m = re.match(r"\s*(\d{3,5})(?:\.\d+)?\s*[–-]\s*(\d{1,5})(?:\.\d+)?\b", str(lab or ""))
    if not m:
        return p, p
    a, z = m.group(1), m.group(2)
    hi = float(a[:len(a) - len(z)] + z) if len(z) < len(a) else float(z)
    lo = float(a)
    return (min(lo, hi), max(lo, hi)) if abs(hi - lo) <= 100 else (p, p)

# ------------------------------------------------------------------ context
class Ctx:
    def __init__(self, S, now=None):
        self.S, self.now = S, now or datetime.now(PT)
        o = S["orb"]
        self.tape_day = o.get("asof")                                    # last session with 1m bars
        self.tape_live = bool(o.get("asof_t"))                           # session still in progress
        im = S["im"]
        im_day = str(im.get("generated_pt", ""))[:10]
        self.im_ok = bool(im.get("symbols")) and im_day >= (self.tape_day or "")
        self.next_session = im.get("session_for") if self.im_ok else None
        if not self.next_session and self.tape_day:
            d = date.fromisoformat(self.tape_day) + timedelta(days=1)
            while d.weekday() >= 5:
                d += timedelta(days=1)
            self.next_session = d.isoformat() if not self.tape_live else self.tape_day
        self.es = quote(S["on"], "ES")
        self.vix = quote(S["on"], "VIX")
        self.basis, self.basis_note = self._basis()
        spx, spy = self.im_spot("SPX"), self.im_spot("SPY")
        self.ratio = (spx / spy) if spx and spy else 1 / 0.099761

    def im_spot(self, s):
        v = (self.S["im"].get("symbols") or {}).get(s) or {}
        return v.get("spot") if self.im_ok else None

    def _basis(self):
        o = self.S["orb"].get("orb") or {}
        es, spx = (o.get("ES") or {}), (o.get("SPX") or {})
        if es.get("bars") and spx.get("bars") and es.get("date") == spx.get("date"):
            m = {b[0]: b[4] for b in spx["bars"]}
            d = [b[4] - m[b[0]] for b in es["bars"] if b[0] in m]
            if len(d) > 30:
                return round(statistics.median(d), 1), f"{dlab(es['date'])} regular-session median"
        b = (self.S["board"].get("basis") or {}).get("ES_minus_SPX")
        return (b or 19.1), f"{self.S['board'].get('asof_label', 'last posted')} basis"

    def es_of_spx(self, x):
        return x + self.basis

    def es_of_spy(self, s):
        return s * self.ratio + self.basis

    def spy_of_es(self, e):
        return (e - self.basis) / self.ratio

    def current(self, for_session):
        """A sweep block is current while its session has not finished trading."""
        if not for_session:
            return False
        if self.tape_day and for_session < self.tape_day:
            return False
        if self.tape_day and for_session == self.tape_day and not self.tape_live:
            return False
        return True


# ------------------------------------------------------------------ html helpers
def chip(s):
    m = {"fresh": ("FRESH", "var(--up)"), "quiet": ("QUIET", "var(--mut)"), "awaiting": ("AWAITING UPDATE", "var(--amb2)")}.get(s, ("QUIET", "var(--mut)"))
    return f'<span class="st" style="border-color:{m[1]};color:{m[1]}">{m[0]}</span>'


def sec(id_, title, sub, body, t, old=False, oldnote=""):
    note = f'<div class="oldn">{E(oldnote)}</div>' if old and oldnote else ""
    return (f'<section class="z{" old" if old else ""}" id="{id_}"><div class="zh"><b>{E(title)}</b><small>{E(sub)}</small>'
            f'<span class="asof{" old" if old else ""}">{E(t)}</span></div>{note}{body}</section>')


def old_msg(for_session, C):
    return (f"Written for {dlab(for_session)} — that session has traded. Shown for reference until the next sweep posts "
            f"the {dlab(C.next_session) if C.next_session else 'next'} read.")


# ------------------------------------------------------------------ ES map rows
def ladder_rows(C):
    sw, rows = C.S["sweep"], []
    plan = sw.get("plan") or {}
    plan_cur = C.current(plan.get("for_session"))
    for L in plan.get("levels") or []:
        tags = list(L.get("tags") or [])
        note = L["note"] if plan_cur else f"{dlab(plan['for_session'])} plan level — " + L["note"]
        rows.append({"p": L["es"], "k": "T" if L.get("kind") == "T" and plan_cur else "L", "lab": L["label"], "note": note,
                     "tags": tags + ([] if plan_cur else [f"plan {dlab(plan['for_session'])}"]), "w": 2.5 if L.get("kind") == "T" else 1})
    im = C.S["im"].get("symbols") or {}
    if C.im_ok and im.get("SPX"):
        for key, name in (("daily", "next-session"), ("weekly", "week")):
            v = im["SPX"].get(key) or {}
            if v.get("upper") and v.get("lower"):
                ex = dlab(v["expiry"])
                rows.append({"p": round(C.es_of_spx(v["upper"])), "k": "B", "lab": f"{C.es_of_spx(v['upper']):.0f}",
                             "note": f"Top of the {name} SPX expected range to {ex} ({v['upper']:,.2f}).", "tags": [f"range {ex}"]})
                rows.append({"p": round(C.es_of_spx(v["lower"])), "k": "B", "lab": f"{C.es_of_spx(v['lower']):.0f}",
                             "note": f"Bottom of the {name} SPX expected range to {ex} ({v['lower']:,.2f}).", "tags": [f"range {ex}"]})
    es = (C.S["orb"].get("orb") or {}).get("ES") or {}
    if es.get("bars"):
        b = es["bars"]; hi = max(x[2] for x in b); lo = min(x[3] for x in b)
        ih = next(x[0] for x in b if x[2] == hi); il = next(x[0] for x in b if x[3] == lo)
        d = dlab(es["date"])
        rows.append({"p": hi, "k": "P", "lab": f"{hi:.2f}", "note": f"{d} regular-session high ({pt_of_idx(es['date'], ih)}).", "tags": ["session"]})
        rows.append({"p": lo, "k": "P", "lab": f"{lo:.2f}", "note": f"{d} regular-session low ({pt_of_idx(es['date'], il)}).", "tags": ["session"]})
    bd = C.S["board"]
    for sym, keys in (("SPX", ("magnet", "call_wall", "put_wall")), ("SPY", ("magnet", "put_wall"))):
        for ex, lv in ((bd.get("levels") or {}).get(sym) or {}).items():
            if C.next_session and ex < C.next_session:
                continue
            for k in keys:
                x = lv.get(k)
                if x is None:
                    continue
                p = C.es_of_spx(x) if sym == "SPX" else C.es_of_spy(x)
                nm = {"magnet": "biggest strike", "call_wall": "call wall", "put_wall": "put wall"}[k]
                rows.append({"p": round(p), "k": "G", "lab": f"{p:.0f}", "note": f"{sym} {x:g} — {dlab(ex)} expiry {nm}.",
                             "tags": [f"gamma {bd.get('asof_label', '')}".strip()]})
    for L in (sw.get("darkpool") or {}).get("lines") or []:
        p = C.es_of_spy(L["spy"])
        rows.append({"p": round(p), "k": "N", "lab": f"{p:.0f}", "note": f"SPY {L['label']} dark pool — {L['note']}.", "tags": ["dark pool"]})
    return rows, plan_cur


def pt_of_idx(day, i):
    t = datetime.fromisoformat(day).replace(hour=9, minute=30, tzinfo=ET) + timedelta(minutes=i)
    return t.astimezone(PT).strftime("%-I:%M %p PT")


def ladder_window(C, rows):
    px = C.es["last"] if C.es else None
    if px is None:
        ps = [r["p"] for r in rows]
        px = statistics.median(ps) if ps else 0
    lo, hi = px * 0.955, px * 1.045
    keep = [r for r in rows if lo <= r["p"] <= hi]
    keep.sort(key=lambda r: -r["p"])
    out = []
    for r in keep:  # merge near-duplicates (within 3 ES points) into one row
        if out and abs(out[-1]["p"] - r["p"]) <= 3 and r["k"] not in ("T",) and out[-1]["k"] not in ("T",):
            o = out[-1]; o["note"] += " " + r["note"]; o["tags"] += [t for t in r["tags"] if t not in o["tags"]]
            if r["k"] == "L": o["k"], o["lab"] = "L", r["lab"]
            continue
        out.append(dict(r))
    return out, px


def ladder_svg(C, rows, px):
    ps = [r["p"] for r in rows] + [px]
    top, bot = max(ps) + 12, min(ps) - 12
    W, H = 560, max(470, min(900, 14 * len(rows) + 60))
    y = lambda p: 18 + (top - p) / ((top - bot) or 1) * (H - 36)
    col = {"R": "#ff4d4d", "S": "#3ddc5c", "T": "#ffb000", "B": "#22c7e8", "P": "#e6e0cc", "G": "#ffb000", "N": "#a06ae0"}
    out = [f'<svg viewBox="0 0 {W} {H}" class="lad" role="img" aria-label="ES level ladder">',
           '<defs><pattern id="hatch" width="8" height="8" patternUnits="userSpaceOnUse" patternTransform="rotate(45)"><line x1="0" y1="0" x2="0" y2="8" stroke="#3a2a00" stroke-width="3"/></pattern></defs>']
    bands = [r for r in rows if r["k"] == "B" and any("range" in t for t in r["tags"])]
    by = {}
    for r in bands:
        by.setdefault(r["tags"][0], []).append(r["p"])
    for i, (tg, v) in enumerate(sorted(by.items(), key=lambda kv: max(kv[1]) - min(kv[1]))):
        if len(v) == 2:
            out.append(f'<rect x="{64 + 12 * i}" y="{y(max(v)):.1f}" width="10" height="{y(min(v)) - y(max(v)):.1f}" fill="#22c7e8" opacity="{.28 - .1 * i:.2f}"><title>{E(tg)}</title></rect>')
    if C.es and C.es.get("hi") and C.es.get("lo"):
        out.append(f'<rect x="90" y="{y(C.es["hi"]):.1f}" width="10" height="{y(C.es["lo"]) - y(C.es["hi"]):.1f}" fill="#a06ae0" opacity=".55"><title>futures day range</title></rect>')
    ly_prev = -99
    for r in rows:
        k = r["k"] if r["k"] in ("T", "B", "P", "G", "N") else ("R" if r["p"] > px else "S")
        yy, c = y(r["p"]), col[k]
        ly = max(yy, ly_prev + 13); ly_prev = ly
        dash = ' stroke-dasharray="4 4"' if k in ("B", "G", "N") else ""
        out.append(f'<line x1="106" x2="{W - 6}" y1="{yy:.1f}" y2="{yy:.1f}" stroke="{c}" stroke-width="{r.get("w", 1)}"{dash} opacity=".9"/>')
        out.append(f'<text x="58" y="{ly + 4:.1f}" text-anchor="end" fill="{c}" font-size="12">{E(r["lab"])}</text>')
        if k == "T":
            out.append(f'<text x="{W - 8}" y="{yy - 5:.1f}" text-anchor="end" fill="{c}" font-size="11" font-weight="700">TRAP DOOR</text>')
    yy = y(px)
    lab = f"ES {px:,.2f}"
    out.append(f'<polygon points="100,{yy:.1f} 108,{yy - 5:.1f} 108,{yy + 5:.1f}" fill="#e6e0cc"/>')
    out.append(f'<line x1="108" x2="{W - 6}" y1="{yy:.1f}" y2="{yy:.1f}" stroke="#e6e0cc" stroke-width="1.5"/>')
    out.append(f'<text x="{W - 8}" y="{yy + 14:.1f}" text-anchor="end" fill="#e6e0cc" font-size="11">{E(lab)}</text>')
    out.append("</svg>")
    return "".join(out)


# ------------------------------------------------------------------ sections
def build(S, now=None):
    C = Ctx(S, now)
    sw, bd, im = S["sweep"], S["board"], S["im"].get("symbols") or {}
    plan = sw.get("plan") or {}
    rows, plan_cur = ladder_rows(C)
    lrows, px = ladder_window(C, rows)
    for r in lrows:
        if r["k"] == "L":
            r["k"] = "R" if r["p"] > px else "S"
    es_lab = C.es["label"] if C.es else "awaiting update"
    fresh = []

    # ---- NOW
    bias = S["bias"]
    b_dir = (plan.get("bias") if plan_cur else bias.get("label")) or "NEUTRAL"
    pcls = "dn" if "BEAR" in b_dir.upper() else "up" if "BULL" in b_dir.upper() else "mut"
    nxt = C.next_session
    day = (f"{date.fromisoformat(nxt).strftime('%a %b %-d').upper()} · NEXT SESSION" if nxt and not C.tape_live
           else f"{date.fromisoformat(C.tape_day).strftime('%a %b %-d').upper()} · SESSION LIVE" if C.tape_day else "")
    above = sorted([r for r in lrows if r["p"] > px], key=lambda r: r["p"])
    below = sorted([r for r in lrows if r["p"] < px], key=lambda r: -r["p"])
    if plan_cur:
        h1 = plan["headline"]
        ctx_p = plan.get("context", "")
        a, b = plan["above"], plan["below"]
        a_k = (a["label"], f"{a['es'] - px:+.2f} {a['note']}", a["then"])
        b_k = (b["label"], f"{b['es'] - px:+.2f} {b['note']}", b["then"])
    else:
        h1, ctx_p = auto_headline(C)
        a_k = ((above[0]["lab"], f"{above[0]['p'] - px:+.2f} · " + short(above[0]), "then " + " · ".join(r["lab"] for r in above[1:4])) if above
               else ("—", "nothing mapped above", ""))
        b_k = ((below[0]["lab"], f"{below[0]['p'] - px:+.2f} · " + short(below[0]), "then " + " · ".join(r["lab"] for r in below[1:4])) if below
               else ("—", "nothing mapped below", ""))
    es_last = C.es["last"] if C.es else None
    es_line = (f'<b>{es_last:,.2f}</b><i class="{"dn" if (C.es.get("chg") or 0) < 0 else "up"}">{C.es["chg"]:+.2f} ({C.es["pct"]:+.2f}%) on the day</i>'
               f'<em>{E(es_lab)} · day {C.es["lo"]:,.2f}–{C.es["hi"]:,.2f}</em>') if C.es else '<b>—</b><i>awaiting update</i><em></em>'
    bias_line = (f'composite {bias.get("score"):+d} · {E(str(bias.get("asof", "")))}' if isinstance(bias.get("score"), int) else "")
    hero = f'''
<section class="hero" id="now">
 <div class="h-bias"><span class="pill {pcls}">{E(b_dir.upper())}</span><span class="h-day">{E(day)}</span><span class="asof">{E(plan["asof_label"] if plan_cur else "bias " + bias_line + " · read auto-built from the " + (dlab(C.tape_day) if C.tape_day else "last") + " close")}</span></div>
 <h1>{h1}</h1>
 <div class="h-grid">
  <div class="h-k"><small>ES (delayed)</small>{es_line}</div>
  <div class="h-k"><small>Above</small><b class="up2">{E(a_k[0])}</b><i>{E(a_k[1])}</i><em>{E(a_k[2])}</em></div>
  <div class="h-k"><small>Below</small><b class="dn">{E(b_k[0])}</b><i>{E(b_k[1])}</i><em>{E(b_k[2])}</em></div>
  <div class="h-k"><small>Next catalyst</small><b id="cdn">—</b><i id="cdw">—</i><em id="cdl">—</em></div>
 </div>
 <p class="h-ctx">{ctx_p}</p>
</section>'''
    fresh.append(("Plan & ladder", plan.get("asof_label", "") if plan_cur else f"levels auto-built · {dlab(C.tape_day) if C.tape_day else 'last'} close", "ok" if plan_cur or C.im_ok else "old"))
    fresh.append(("ES quote", es_lab + " (delayed)", "ok" if C.es else "old"))

    # ---- ES MAP
    lad_rows = "".join(
        f'<tr class="k{r["k"]}"><td class="lv">{E(r["lab"])}</td><td>{E(r["note"])}{"".join(f"<span class=tg>{E(t)}</span>" for t in r["tags"])}</td>'
        f'<td class="r">{C.spy_of_es(r["p"]):.2f}</td><td class="r {"dn" if r["p"] < px else "up"}">{r["p"] - px:+.1f}</td></tr>' for r in lrows)
    bands_txt = []
    for key in ("daily", "weekly"):
        v = (im.get("SPX") or {}).get(key) or {}
        if C.im_ok and v.get("upper"):
            bands_txt.append(f'{dlab(v["expiry"])} SPX expected range in ES ({C.es_of_spx(v["lower"]):.0f}–{C.es_of_spx(v["upper"]):.0f})')
    ladder = sec("ladder", "ES MAP", "one ladder · plan + gamma + expected range + dark pool, all in ES points",
      f'''<div class="two"><div class="card">{ladder_svg(C, lrows, px)}
  <p class="lg"><span style="color:#22c7e8">▮</span> {E(" · ".join(bands_txt) or "expected range awaiting update")} · <span style="color:#a06ae0">▮</span> futures day range · dashed = gamma, expected range and dark pool · white = ES last</p></div>
  <div class="card"><table class="t"><thead><tr><th>ES</th><th>Why it matters</th><th class="r">SPY≈</th><th class="r">vs ES</th></tr></thead><tbody>{lad_rows}</tbody></table>
  <p class="lg">ES = SPX {C.basis:+.1f} ({E(C.basis_note)}) · SPY = SPX ÷ {C.ratio:.4f} · conversions are approximate.</p></div></div>''',
      (plan.get("asof_label", "") if plan_cur else f"levels as of the {dlab(C.tape_day) if C.tape_day else 'last'} close") + " · ES quote " + es_lab)

    # ---- SCENARIOS
    sc = sw.get("scenarios") or {}
    sc_cur = C.current(sc.get("for_session"))
    cards = []
    for c in sc.get("cards") or []:
        body = (f'<ol>{"".join(f"<li>{s}</li>" for s in c["steps"])}</ol>' if c.get("steps") else
                f'<ul>{"".join(f"<li>{s}</li>" for s in c.get("bullets") or [])}</ul>')
        res = "" if sc_cur else scenario_result(C, c, sc.get("for_session"))
        cards.append(f'<div class="card sc {c.get("cls", "")}"><h3>{E(c["title"])}</h3>{body}'
                     + (f'<p class="cf">{E(c["confirm"])}</p>' if c.get("confirm") else "") + res + "</div>")
    scen = sec("scen", "SCENARIOS", "triggers · confirmation · invalidation", f'<div class="three">{"".join(cards)}</div>',
               sc.get("asof_label", "awaiting update"), old=not sc_cur, oldnote=old_msg(sc.get("for_session"), C) if sc.get("for_session") else "")
    fresh.append(("Scenarios", sc.get("asof_label", "awaiting update"), "ok" if sc_cur else "old"))

    # ---- POSITIONING
    g_old = bd.get("asof", "") < (C.tape_day or "") if bd.get("asof") else True
    gcards = "".join(gcard(C, t) for t in ("SPX", "SPY", "QQQ", "NDX"))
    em_rows = ""
    wem = bd.get("weekly_em") or {}
    # Friday session bands from the chain snapshot; week bands prefer the Wed close board read to Fri 11/27.
    for key, title in (("daily", "NEXT SESSION"), ("weekly", "WEEK")):
        if key == "weekly" and wem.get("rows"):
            ex = wem.get("expiry")
            lab = wem.get("asof_label") or ""
            em_rows += f'<p class="sm amb" style="margin:6px 0 0">{title} · to {dlab(ex) if ex else ""}{" · " + E(lab) if lab else ""}</p>'
            close = bd.get("close") or {}
            for r in wem["rows"]:
                sname = r.get("symbol")
                if sname not in ("SPX", "SPY", "QQQ", "NDX"):
                    continue
                lo, hi = r.get("lower"), r.get("upper")
                if not (lo and hi and hi > lo):
                    continue
                spot = close.get(sname) or (C.im_spot(sname) if sname != "NDX" else None)
                pos = ((spot - lo) / ((hi - lo) or 1) * 100) if spot is not None else 50
                pct = f'±{r["pct"]:.2f}%' if r.get("pct") is not None else ""
                em_rows += (f'<div class="em"><b>{sname}</b><div class="bar"><i style="left:{max(0, min(100, pos)):.1f}%"></i></div><span class="r">{lo:,.2f}</span>'
                            f'<span class="r">{hi:,.2f}</span><span class="r">{pct}</span><span class="r mut"></span></div>')
            continue
        ex = ((im.get("SPX") or {}).get(key) or {}).get("expiry")
        if C.im_ok and ex:
            em_rows += f'<p class="sm amb" style="margin:6px 0 0">{title} · to {dlab(ex)}</p>'
        for s in ("SPX", "SPY", "QQQ"):
            v = (im.get(s) or {}).get(key) or {}
            if not (C.im_ok and v.get("upper")):
                continue
            spot = im[s]["spot"]
            pos = (spot - v["lower"]) / ((v["upper"] - v["lower"]) or 1) * 100
            iv = f' · {v["atm_iv"] * 100:.0f}% IV' if v.get("atm_iv") else ""
            em_rows += (f'<div class="em"><b>{s}</b><div class="bar"><i style="left:{max(0, min(100, pos)):.1f}%"></i></div><span class="r">{v["lower"]:,.2f}</span>'
                        f'<span class="r">{v["upper"]:,.2f}</span><span class="r">±{v["move_pct"]:.2f}%</span><span class="r mut">±{v["straddle"]:,.2f}{iv}</span></div>')
    im_asof = (C.S.get("im") or {}).get("generated_pt") or ""
    range_when = (im_asof + " · session still open") if (C.tape_live and im_asof) else ((wem.get("asof_label") or (f"{dlab(C.tape_day)} close" if C.tape_day else "awaiting update")))
    em_note = (f'Week bands are the Fri 11/27 close read to Fri 12/4. Monday session bands are from the {E(im_asof) or "chain"} snapshot '
               f'(SPX {fnum(C.im_spot("SPX"))} · SPY {fnum(C.im_spot("SPY"))} · QQQ {fnum(C.im_spot("QQQ"))}). Not a guaranteed limit.') if (C.im_ok or wem.get("rows")) else "Expected-move bands awaiting update."
    vx = sw.get("vix") or {}
    vv = C.vix["last"] if C.vix else None
    if vv is not None and vx.get("wall"):
        lo_w, hi_w = vx.get("put_wall", 17), vx["wall"]
        vpos = max(0, min(100, (vv - lo_w) / (hi_w - lo_w) * 100))
        where = "above its" if vv > hi_w else "under its"
        vtxt = (f'VIX {vv:.2f} ({C.vix["pct"]:+.2f}% · {E(C.vix["label"])}) sits {where} {hi_w} wall. Walls as of {E(vx.get("asof_label", ""))}: {E(vx.get("note", ""))}')
        vix_box = f'<h3>VIX · walls {lo_w} to {hi_w} ({E(vx.get("asof_label", ""))})</h3><div class="vix"><div class="vb"><i style="left:{vpos:.1f}%"></i><span style="left:0">{lo_w} put wall</span><span style="right:0">{hi_w} wall</span></div></div><p class="sm">{vtxt}</p>'
    else:
        vix_box = '<h3>VIX</h3><p class="sm mut">awaiting update</p>'
    fl, fx = bd.get("flow") or {}, sw.get("flow") or {}
    pc_prev = f'<s>{fx["prev_put_call"]}</s>' if fx.get("prev_put_call") and fx.get("asof") == bd.get("asof") else ""
    tape_box = (f'<h3 style="margin-top:10px">OPTIONS TAPE · {E(fl.get("asof_label", ""))}</h3><div class="flow"><div><small>net</small><b class="{"up" if str(fl.get("net", "")).startswith("+") else "dn"}">{E(str(fl.get("net", "—")))}</b></div>'
                f'<div><small>calls</small><b>{E(str(fl.get("calls", "—")))}</b></div><div><small>puts</small><b class="dn">{E(str(fl.get("puts", "—")))}</b></div>'
                f'<div><small>put/call</small><b class="dn">{E(str(fl.get("put_call", "—")))}</b>{pc_prev}</div><div><small>prints</small><b>{(format(fl["prints"], ",") if isinstance(fl.get("prints"), (int, float)) else "—")}</b></div></div>') if fl else ""
    prints = "".join(f"<li>{E(p)}</li>" for p in (fx.get("prints") or [])) if fx.get("asof") == bd.get("asof") else ""
    secs = fx.get("sectors") or []
    mx = max([abs(v) for _, v in secs] or [1]) or 1
    sect = "".join(f'<div class="sb"><span>{E(n)}</span><div><i style="{"left:50%" if v >= 0 else "right:50%"};width:{abs(v) / mx * 50:.1f}%;background:{"var(--up)" if v > 0 else "var(--dn)" if v < 0 else "var(--mut)"}"></i></div><b class="{"up" if v > 0 else "dn" if v < 0 else ""}">{v:+d}M</b></div>' for n, v in secs)
    pos = sec("pos", "DEALER POSITIONING", "gamma board · expected range · VIX · flow · what changed since the prior read", f'''
<div class="four">{gcards}</div>
<div class="two" style="margin-top:10px">
 <div class="card"><h3>EXPECTED RANGE · {E(dlab(C.next_session) if C.next_session else "next session")} and week{(" to " + E(dlab((im.get("SPX") or {}).get("weekly", {}).get("expiry", "")))) if C.im_ok and (im.get("SPX") or {}).get("weekly") else ""}</h3><div class="em hd"><b></b><span>position in band</span><span class="r">low</span><span class="r">high</span><span class="r">move</span><span class="r">± straddle</span></div>{em_rows or '<p class="sm mut">awaiting update</p>'}
 <p class="lg">{em_note}</p></div>
 <div class="card">{vix_box}{tape_box}<ul class="pr">{prints}</ul></div>
</div>
''' + (f'<div class="card" style="margin-top:10px"><h3>SECTOR NET FLOW · {E(fx.get("asof_label", ""))} ($M) · {E(fx.get("sector_note", ""))}</h3><div class="sbs">{sect}</div></div>' if sect else ""),
      f'gamma {bd.get("asof_label", "awaiting update")} · ranges {range_when if C.im_ok else "awaiting update"} · VIX {C.vix["label"] if C.vix else "awaiting update"}',
      old=g_old, oldnote=(f"Gamma walls, flow and sector reads are from the {bd.get('asof_label', 'last')} board — the next sweep refreshes them. Prices, expected ranges and VIX above are current.") if g_old else "")
    fresh.append(("Gamma board · flow", bd.get("asof_label", "awaiting update"), "old" if g_old else "ok"))
    fresh.append(("Expected ranges", (range_when if C.im_ok else "awaiting update"), "ok" if C.im_ok else "old"))

    # ---- TAPE
    tape, tday = tape_section(C, plan)
    fresh.append(("Tape check", tday, "ok"))

    # ---- READS
    rd = sw.get("reads") or {}
    rd_cur = C.current(rd.get("for_session"))
    dp = sw.get("darkpool") or {}
    dprow = "".join(f'<tr><td>{E(L["label"])}</td><td>{C.es_of_spy(L["spy"]):.0f}</td><td>{E(L["note"])}</td></tr>' for L in dp.get("lines") or [])
    reads = sec("reads", "POST-MARKET READS", "the evening's level reads, merged · dark pool lines near price", f'''<div class="two">
<div class="card"><h3>WHAT THE EVENING READS AGREE ON</h3><ul class="pr">{"".join(f"<li>{b}</li>" for b in rd.get("bullets") or []) or "<li>awaiting update</li>"}</ul></div>
<div class="card"><h3>DARK POOL · lines near price · {E(dp.get("asof_label", ""))}</h3><table class="t"><thead><tr><th>SPY</th><th>ES≈</th><th>note</th></tr></thead><tbody>{dprow}</tbody></table>
<p class="lg"><a href="../darkpool/">Dark Pool →</a> full ladder, stats, crosses</p></div></div>''', rd.get("asof_label", "awaiting update"),
               old=not rd_cur, oldnote=old_msg(rd.get("for_session"), C) if rd.get("for_session") else "")
    fresh.append(("Evening reads", rd.get("asof_label", "awaiting update"), "ok" if rd_cur else "old"))

    # ---- SWEEP DESK
    tp = sw.get("topics") or {}
    tp_old = tp.get("asof", "") < (C.tape_day or "")
    groups = [("levels", "LEVELS & PLANS"), ("gamma", "GAMMA & POSITIONING"), ("flow", "FLOW & DARK POOL"), ("macro", "MACRO & NEWS"), ("swing", "SWING & STRUCTURE")]
    tg = ""
    for g, gt in groups:
        items = "".join(f'<div class="tp"><div class="tph"><b>{E(t["name"])}</b>{chip(t["status"])}</div><p>{E(t["text"])}</p><small>→ {E(t["where"])}</small></div>'
                        for t in tp.get("items") or [] if t["group"] == g)
        if items:
            tg += f'<div class="tgrp"><h3>{gt}</h3><div class="tps">{items}</div></div>'
    topics = sec("topics", "SWEEP DESK", "every sweep topic has a home · status since the last sweep", tg or '<p class="sm mut">awaiting update</p>',
                 tp.get("asof_label", "awaiting update"), old=tp_old,
                 oldnote=f"Last sweep: {dlab(tp['asof'])}. Statuses refresh with the next sweep." if tp_old and tp.get("asof") else "")
    fresh.append(("Sweep desk", f"last sweep {dlab(tp['asof'])}" if tp.get("asof") else "awaiting update", "old" if tp_old else "ok"))

    # ---- ORB STATUS (carried over)
    o = S["orb"]
    orb_sec = ('<section class="z" id="z-orb"><div class="zh"><b>ORB STATUS</b><small>ORB15 · today</small>'
               f'<span class="asof">{E(dlab(o["asof"]) if o.get("asof") else "awaiting update")}{" · session live" if o.get("asof_t") else " · last session"}</span></div>'
               '<div class="g"><div class="pn" style="--c:var(--yl)" id="orbSPY"></div><div class="pn" style="--c:var(--bl)" id="orbQQQ"></div>'
               '<div class="pn" style="--c:var(--amb)" id="orbES"></div><div class="pn" style="--c:var(--pu)" id="orbSPX"></div>'
               '<div class="pn" id="eqP"><div class="ph"><span>CUMULATIVE R · ORB15</span><small id="eqH"></small></div><div id="eqB"></div></div>'
               '<div class="pn" style="--c:var(--gn)" id="botP"><div class="ph"><span>BOT · ORB15</span><small id="botH"></small></div><div id="botB"></div></div></div></section>')
    D = {"built": C.now.strftime("%Y-%m-%d %H:%M PT"), "orb": o.get("orb") or {}, "hourly": o.get("hourly") or {}, "eq": o.get("eq") or {}, "bot": bot_box(o, S.get("prior_bot"))}

    # ---- ACCOUNT
    acct, jl = account(C, S["journal"], o)
    fresh.append(("Account", jl, "ok"))

    # ---- CONTEXT
    se = bd.get("seasonality") or {}
    se_rows = "".join(f"<tr><td>{s}</td><td>{E(se[s].get('week', ''))}</td></tr>" for s in ("SPY", "SPX", "QQQ") if se.get(s))
    m = re.search(r"history through ([A-Za-z]{3} \d+/\d+)", json.dumps(se, ensure_ascii=False))
    se_asof = f"history through {m.group(1)}" if m else bd.get("asof_label", "awaiting update")
    ctx = sec("ctx", "CONTEXT", "seasonality · links", f'''<div class="two"><div class="card"><h3>SEASONALITY</h3><table class="t">{se_rows or "<tr><td>awaiting update</td></tr>"}</table>
<p class="lg">{E(se_asof)}. Not a forecast.</p></div>
<div class="card"><h3>GO DEEPER</h3><div class="lk"><a href="../daily/">Daily plan</a><a href="../weekly/">Weekly plan</a><a href="../overnight/">Overnight</a><a href="../gammamap/">Gamma Map</a><a href="../darkpool/">Dark Pool</a><a href="../live-trades/">Live Trades</a></div>
<p class="lg">Archive: October desk cards, bot fills, legacy ladders and confluence boards moved off this page.</p></div></div>''', se_asof)
    fresh.append(("Seasonality", se_asof, "old"))

    n_ok = sum(1 for f in fresh if f[2] == "ok")
    rail = (f'<details class="railw" id="railw"><summary>DATA FRESHNESS · {n_ok} current · {len(fresh) - n_ok} older or awaiting</summary><div class="rail">'
            + "".join(f'<span class="{c}"><b>{E(a)}</b> {E(b)}</span>' for a, b, c in fresh) + "</div></details>")

    ev = events(C)
    built = C.now.strftime("%a %b %-d, %Y %-I:%M %p PT")
    js = ('<script>if(innerWidth>700)document.getElementById("railw").open=true;(()=>{const ev=' + json.dumps(ev) + ''';const f=()=>{const now=Date.now();const n=ev.find(e=>Date.parse(e.t)>now);const a=document.getElementById('cdn'),b=document.getElementById('cdw'),c=document.getElementById('cdl');
if(!n){a.textContent='next sweep';b.textContent='calendar awaiting update';c.textContent='';return}let s=Math.floor((Date.parse(n.t)-now)/1000);const d=Math.floor(s/86400);s%=86400;const h=Math.floor(s/3600);s%=3600;const m=Math.floor(s/60);s%=60;
a.textContent=(d?d+'d ':'')+h+'h '+String(m).padStart(2,'0')+'m '+String(s).padStart(2,'0')+'s';b.textContent=n.n;const r=ev.filter(e=>Date.parse(e.t)>Date.parse(n.t)).slice(0,3).map(e=>e.pt);c.textContent=n.pt+(r.length?' · then '+r.join(' · '):'')};f();setInterval(f,1000)})()</script>''')
    imx = {k: v for k, v in (S["im"] or {}).items() if k in ("generated_pt", "session_for", "week_expiry", "symbols")}
    im_tag = ('<script id="cc-im" type="application/json">' + json.dumps(imx, ensure_ascii=False).replace("</", "<\\/") + "</script>") if imx.get("symbols") else ""
    orb_js = "<script>const D=" + json.dumps(D, ensure_ascii=False, default=float).replace("</", "<\\/") + ";\n" + ORB_JS + "</script>"

    page = f'''<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>ATTACHÉ — COMMAND CENTER</title><link rel="icon" href="data:,"><style>{CSS}</style></head><body>
<main>
<div class="top"><span class="brand">ATTACHÉ COMMAND CENTER</span><div class="jump"><a href="#now">NOW</a><a href="#ladder">ES MAP</a><a href="#scen">SCENARIOS</a><a href="#pos">POSITIONING</a><a href="#tape">TAPE</a><a href="#reads">READS</a><a href="#topics">SWEEP DESK</a><a href="#z-orb">ORB</a><a href="#acct">ACCOUNT</a></div></div>
{rail}{hero}{ladder}{scen}{pos}{tape}{reads}{topics}{orb_sec}{acct}{ctx}
<footer>Research only. Not financial advice. Expected-move bands are not guaranteed limits. Futures quotes delayed. Built {E(built)}.</footer>
</main>{js}{orb_js}{im_tag}</body></html>'''
    return page


def short(r):
    n = r["note"]
    return (n[:70] + "…") if len(n) > 72 else n


def auto_headline(C):
    es = C.es
    day = dlab(C.tape_day) if C.tape_day else "Last session"
    im = C.S["im"].get("symbols") or {}
    parts = []
    if es:
        parts.append(f'{day}: ES {es["last"]:,.2f} ({es["pct"]:+.2f}%), day range {es["lo"]:,.2f}–{es["hi"]:,.2f}.')
    d = (im.get("SPX") or {}).get("daily") or {}
    if C.im_ok and d.get("upper"):
        parts.append(f' <span class="amb">{dlab(d["expiry"])} expected range ≈ ES {C.es_of_spx(d["lower"]):,.0f}–{C.es_of_spx(d["upper"]):,.0f}</span> '
                     f'(SPX {d["lower"]:,.2f}–{d["upper"]:,.2f}, ±{d["move_pct"]:.2f}%).')
    h1 = "".join(parts) or "Awaiting the next plan."
    bd = C.S["board"]; cl = bd.get("close") or {}
    ctx = []
    for s in ("SPX", "SPY", "QQQ"):
        sp = C.im_spot(s)
        if sp:
            prev = cl.get(s) if bd.get("asof", "") < (C.tape_day or "") else None
            ctx.append(f"{s} {sp:,.2f}" + (f" ({(sp / prev - 1) * 100:+.2f}%)" if prev else ""))
    if C.vix:
        ctx.append(f'VIX {C.vix["last"]:.2f} ({C.vix["pct"]:+.2f}%)')
    txt = (f"{day} close: " + ", ".join(ctx) + ". ") if ctx else ""
    txt += f"The next plan posts with the weekend sweep; until then the levels here are built from the close, the expected ranges and the last gamma board."
    return h1, txt


def scenario_result(C, c, for_session):
    """How a past session's scenario played, from that session's 1m ES bars (regular session)."""
    es = (C.S["orb"].get("orb") or {}).get("ES") or {}
    if not c.get("targets") or es.get("date") != for_session or not es.get("bars"):
        return ""
    b = es["bars"]; hi = max(x[2] for x in b); lo = min(x[3] for x in b)
    hits = []
    for t in c["targets"]:
        ix = next((x[0] for x in b if x[3] <= t <= x[2]), None)
        if ix is None and ((c.get("dir") == "down" and b[0][1] < t) or (c.get("dir") == "up" and b[0][1] > t)):
            hits.append(f"{t} already through at the open")
        elif ix is None:
            hits.append(f"{t} not reached")
        else:
            hits.append(f"{t} at {pt_of_idx(for_session, ix)}")
    return (f'<p class="res"><b>HOW IT PLAYED · {E(dlab(for_session))}</b> · ES regular session {lo:,.2f}–{hi:,.2f} · ' + E(" · ".join(hits)) + "</p>")


def gcard(C, t):
    bd, sw = C.S["board"], C.S["sweep"].get("gamma") or {}
    cur = (sw.get("cards") or {}).get(t) if sw.get("asof") == bd.get("asof") else None
    lv = (bd.get("levels") or {}).get(t) or {}
    nx = [e for e in sorted(lv) if not C.next_session or e >= C.next_session]
    spot = C.im_spot(t) if t != "NDX" else None
    px = f"{spot:,.2f}" if spot else (f'{(bd.get("close") or {}).get(t):,.2f}' if (bd.get("close") or {}).get(t) else "—")
    im_asof = (C.S.get("im") or {}).get("generated_pt") or ""
    px_when = (im_asof + " · session still open") if (C.tape_live and im_asof) else (f"{dlab(C.tape_day)} close" if C.tape_day else "")
    px_l = px_when if spot else bd.get("asof_label", "")
    d = lambda a: (f'<b>{E(str(a[0]))}</b>' + (f' <s>{E(str(a[1]))}</s>' if a[0] != a[1] else ' <em>=</em>')) if isinstance(a, list) else f"<b>{E(str(a))}</b>"
    if cur:
        rows = (f'<tr><td>biggest strike</td><td>{d(cur["strike"])}</td></tr><tr><td>call wall</td><td>{d(cur["call_wall"])}</td></tr><tr><td>put wall</td><td><b>{E(cur["put_wall"])}</b></td></tr>'
                f'<tr><td>flip</td><td>{d(cur["flip"])}</td></tr><tr><td>net GEX</td><td>{d(cur["net"])}</td></tr>')
        note = (f'{bd.get("asof_label", "")}: ' if bd.get("asof", "") < (C.tape_day or "") else "") + cur.get("note", "")
    elif nx:
        v = lv[nx[-1]]
        rows = "".join(f'<tr><td>{k}</td><td><b>{E(str(v.get(kk) if v.get(kk) is not None else "none"))}</b></td></tr>' for k, kk in
                       (("biggest strike", "magnet"), ("call wall", "call_wall"), ("put wall", "put_wall"), ("flip", "flip"), ("net GEX", "net_gex")))
        note = ""
    else:
        return f'<div class="card g"><div class="gh"><b>{t}</b><span>{px}</span></div><p class="sm mut">awaiting update</p></div>'
    nrow = ""
    if nx:
        v = lv[nx[0]]
        nrow = (f'{dlab(nx[0])}: strike {v.get("magnet") or "—"}' + (f' · put wall {v["put_wall"]}' if v.get("put_wall") else "")
                + f' · call wall {v.get("call_wall") or "—"} · flip {v.get("flip") or "none"} · {v.get("net_gex") or ""}')
    reg = "NEG γ" if all((lv[e].get("regime") == "NEG") for e in lv) and lv else "MIXED γ"
    return (f'<div class="card g"><div class="gh"><b>{t}</b><span title="{E(px_l)}">{px}</span><span class="pill {"dn" if reg.startswith("NEG") else "amb"}">{reg}</span></div>'
            f'<table class="kv">{rows}</table><p class="sm">{E(nrow)}</p><p class="sm amb">{E(note)}</p><p class="sm mut">levels {E(bd.get("asof_label", ""))} · price {E(px_l)}</p></div>')


def tape_section(C, plan):
    o = C.S["orb"]
    day = o.get("asof")
    if not day:
        return sec("tape", "TAPE CHECK", "how the last session traded", '<p class="sm mut">awaiting update</p>', "awaiting update"), "awaiting update"
    orb = o.get("orb") or {}
    cards = ""
    for k in ("SPY", "QQQ", "ES", "SPX"):
        x = orb.get(k)
        if not x:
            continue
        st = x.get("status", "")
        pc = "dn" if "SHORT" in st else "up" if "LONG" in st else "mut"
        res = x.get("result")
        rc = "up" if res == "WIN" else "dn" if res == "LOSS" else "mut"
        rtxt = f'<b>{x["R"]:+.2f}R</b> {res}' if res and x.get("R") is not None else (res or "open")
        cards += (f'<div class="card o"><div class="gh"><b>{E(x.get("sym", k))}</b><span class="pill {pc}">{E(st)}</span></div><table class="kv">'
                  f'<tr><td>opening range</td><td>{x["L"]:,.2f}–{x["H"]:,.2f}</td></tr><tr><td>width</td><td>{x["H"] - x["L"]:,.2f}</td></tr>'
                  f'<tr><td>result</td><td class="{rc}">{rtxt}</td></tr><tr><td>last</td><td>{fnum(x.get("px"))}</td></tr></table></div>')
    hb = ""
    tallies = []
    for sym in ("SPY", "QQQ"):
        hrs = (o.get("hourly") or {}).get(sym) or []
        cells, nu, nd = "", 0, 0
        for r in hrs:
            u = hm_et(r["up"]) if r.get("up") is not None else "–"
            dn = hm_et(r["dn"]) if r.get("dn") is not None else "–"
            nu += u != "–"; nd += dn != "–"
            c = "both" if u != "–" and dn != "–" else ("up" if u != "–" else ("dn" if dn != "–" else "none"))
            cells += f'<div class="hc {c}"><small>{hm_et(r["start"])}</small><span>▲{u}</span><span>▼{dn}</span></div>'
        if hrs:
            hb += f'<div class="hbr"><b>{sym}</b>{cells}</div>'
            tallies.append(f"{sym}: {nd} of {len(hrs)} hour lows broke later, {nu} of {len(hrs)} highs")
    up = sum(int(t.split(", ")[1].split(" of")[0]) for t in tallies) if tallies else 0
    dn = sum(int(t.split(": ")[1].split(" of")[0]) for t in tallies) if tallies else 0
    tone = "weak tape, lows kept giving way" if dn > up else "strong tape, highs kept giving way" if up > dn else "two-sided tape"
    grade = ""
    es = orb.get("ES") or {}
    if plan.get("for_session") != day:  # the sweep has posted the next plan: grade the session against the plan written for it
        plan = next((q for q in (C.S["sweep"].get("prior_plans") or []) if q.get("for_session") == day), plan)
    if plan.get("for_session") == day and es.get("bars"):
        b = es["bars"]
        lv = sorted({L["es"]: L["label"] for L in plan.get("levels") or []}.items(), key=lambda kv: -kv[0])
        for p, lab in lv:
            lo, hi = _zone(p, lab)  # a zone such as '7211–23' is reached when price trades anywhere inside it
            ix = next((x[0] for x in b if x[3] <= hi and x[2] >= lo), None)
            if ix is None:
                above = b[0][1] > hi
                reached = (min(x[3] for x in b) <= hi) if above else (max(x[2] for x in b) >= lo)
                note = "opened through it" if reached else "not reached in the regular session"
                grade += f"<tr><td>{E(lab)}</td><td>—</td><td class='mut'>{note}</td></tr>"
            else:
                grade += f"<tr><td>{E(lab)}</td><td>{pt_of_idx(day, ix)}</td><td class='mut'></td></tr>"
        grade_card = (f'<div class="card"><h3>{E(dlab(day)).upper()} PLAN GRADE · first regular-session trade at each level</h3><table class="t">{grade}</table>')
    else:
        grade_card = f'<div class="card"><h3>PLAN GRADE</h3><p class="sm mut">No plan posted for {E(dlab(day))}; grading resumes with the next plan.</p>'
    eq = o.get("eq") or {}
    cum = " · ".join(f'{s} {eq[s]["stats"]["tot_r"]}' for s in ("SPY", "QQQ") if (eq.get(s) or {}).get("stats"))
    first = next(((eq[s]["stats"].get("first") or "")[:4] for s in ("SPY", "QQQ") if (eq.get(s) or {}).get("stats")), "2020")
    live = f' {o["asof_t"]}' if o.get("asof_t") else ""
    tday = f"{dlab(day)} RTH{live}"
    body = f'''
<div class="four">{cards}</div>
<div class="two" style="margin-top:10px"><div class="card"><h3>HOURLY BREAKS · times ET</h3>{hb}
<p class="sm">{E(" · ".join(tallies))} — {tone}.</p>
<p class="lg">green = a later bar broke that hour's high · red = low · amber = both</p></div>
{grade_card}<p class="sm">Cumulative ORB15 R since {first}: {E(cum or "awaiting update")}.</p></div></div>'''
    return sec("tape", f"TAPE CHECK · {dlab(day).upper()}", "how the last session traded · ORB15 · hourly breaks · plan grade", body, tday), tday


def hm_et(i):
    t = 570 + int(i)
    return f"{t // 60}:{t % 60:02d}"


def bot_box(o, prior=None):
    bp = o.get("bot") or {}
    if prior and isinstance(prior.get("v"), dict):
        pv = prior["v"]
        bp = {**bp, "last_tick": prior.get("last_tick"), "ticks": prior.get("ticks", 0), "range_high": pv.get("range_high"),
              "range_low": pv.get("range_low"), "hb_ts": (prior.get("hb") or {}).get("ts")}
    return {"day": f"paused since {bp.get('paused_since', '—')} · last session {bp.get('last_session', '—')}", "last_tick": bp.get("last_tick"),
            "ticks": bp.get("ticks", 0), "v": {"status": "PAUSED", "range_high": bp.get("range_high"), "range_low": bp.get("range_low"), "side": None,
            "entry_price": None, "entry_time": None, "stop": None, "target": None, "realized_pnl": 0.0},
            "fills": [], "hb": {"ts": bp.get("hb_ts"), "mode": "paused", "day": bp.get("paused_since"), "phase": f"paused since {bp.get('paused_since')}"}}


def account(C, J, o):
    T = J.get("trades") or []
    asof = J.get("as_of")
    if not T:
        return sec("acct", "ACCOUNT", "journal · bot", '<p class="sm mut">awaiting update</p>', "awaiting update"), "awaiting update"
    eq = T[-1].get("equity")
    fut = [t for t in T if t.get("inst") == "Futures"]
    opt = [t for t in T if t.get("inst") != "Futures"]
    sys.path.insert(0, str(DESK))
    import live_trades as LT  # same totals as the Live Trades page
    sm = LT.summary(T)
    o_full, o_q, f_net = sm["options"] or 0, sm["q_out"] or 0, sm["futures"] or 0
    eq = sm["equity"] if sm["equity"] is not None else eq
    lf = fut[-1] if fut else None
    lf_txt = (f'{lf["sym"]} {lf["side"].lower()} {lf["entry"]:,} → {lf["exit"]:,} {dlab(lf["date"])}: {lf["net"]:+,.0f}' if lf and lf.get("exit") is not None else "")
    wins = sum(1 for t in T if (t.get("net") or 0) > 0)
    bp = o.get("bot") or {}
    jl = f"journal as of {dlab(asof)}" if asof else "journal"
    body = f'''<div class="four">
<div class="card k"><small>equity</small><b>${eq:,.2f}</b><em>after {E(dlab(T[-1]["date"]))}'s last trade</em></div>
<div class="card k"><small>Q out only</small><b class="{"up" if o_q >= 0 else "dn"}">${o_q:,.2f}</b><em>options · full out ${o_full:,.2f}</em></div>
<div class="card k"><small>futures</small><b class="{"up" if f_net >= 0 else "dn"}">${f_net:,.0f}</b><em>{E(lf_txt)}</em></div>
<div class="card k"><small>ORB15 bot</small><b class="mut">PAUSED</b><em>since {E(str(bp.get("paused_since", "—")))} · history only</em></div></div>
<p class="lg">{len(T)} trades in the journal as of {E(dlab(asof) if asof else "—")} · {round(wins / len(T) * 100)}% winners · <a href="../live-trades/">Live Trades →</a></p>'''
    return sec("acct", "ACCOUNT", "journal · bot", body, jl), jl


def events(C):
    now = datetime.now(timezone.utc)
    ev = []
    for e in (C.S["sweep"].get("events") or []) + [{"utc": c.get("utc"), "name": c.get("name"), "pt": c.get("pt")} for c in C.S["board"].get("calendar") or []]:
        if not e.get("utc"):
            continue
        t = datetime.fromisoformat(e["utc"].replace("Z", "+00:00"))
        lab = t.astimezone(PT).strftime("%a %-m/%-d %-I:%M %p PT")
        if not any(x["t"] == e["utc"] for x in ev):
            ev.append({"t": e["utc"], "n": e["name"], "pt": lab})
    if C.next_session:  # market clock: futures reopen and the regular-session open (always known; never 'none scheduled')
        d = date.fromisoformat(C.next_session)
        rth = datetime(d.year, d.month, d.day, 6, 30, tzinfo=PT)
        prev = d - timedelta(days=1)
        globex = datetime(prev.year, prev.month, prev.day, 15, 0, tzinfo=PT)
        for t, n in ((globex, "Futures reopen"), (rth, f"Regular session opens · {dlab(d)}")):
            u = t.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:00Z")
            ev.append({"t": u, "n": n, "pt": t.strftime("%a %-m/%-d %-I:%M %p PT")})
    ev.sort(key=lambda x: x["t"])
    return ev


def prior_bot(out):
    """Keep the bot box's recorded last tick / range from the page already published (the inputs only carry the pause dates)."""
    try:
        h = out.read_text(encoding="utf-8")
        i = h.index("{", h.index("const D="))
        return (json.JSONDecoder().raw_decode(h[i:])[0] or {}).get("bot")
    except Exception:
        return None


def prior_im(out):
    """Expected-move snapshot the published page was built from (the chain fetch can fail after hours and leave an older file)."""
    try:
        h = out.read_text(encoding="utf-8")
        m = re.search(r'<script id="cc-im" type="application/json">(.*?)</script>', h, re.S)
        return json.loads(m.group(1)) if m else None
    except Exception:
        return None


def main(argv):
    out = Path(argv[1]) if len(argv) > 1 else DESK.parent.parent / "command" / "index.html"
    S = load()
    S["prior_bot"] = prior_bot(out)
    pim = prior_im(out)
    if pim and str(pim.get("generated_pt", "")) > str(S["im"].get("generated_pt", "")):
        S["im"] = pim  # never step back to an older expected-move snapshot
    page = build(S)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(page, encoding="utf-8")
    print("command_center:", out, len(page))


if __name__ == "__main__":
    main(sys.argv)
