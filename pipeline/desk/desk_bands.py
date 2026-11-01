"""DESK BANDS loader: reads es_levels/voltick/{gex_SPY,gex_QQQ,gex_SPX,expected_moves,flow_pressure}.json
(future refreshes: just overwrite those JSONs and run publish_dashboard.sh). Normalizes to source-neutral data and renders
static HTML for: GAMMA GRID (command), UNDERTOW (command), DESK BANDS + gamma line (main). All visible text is scrubbed."""
import json, re, html
from pathlib import Path
RES = Path(__file__).resolve().parent; DIR = RES / "es_levels" / "voltick"; ES = RES / "es_levels"
TK = ("SPY", "QQQ", "SPX")
def J(p):
    try: return json.loads(Path(p).read_text())
    except Exception: return None
def scrub(s):
    s = str(s if s is not None else "")
    s = re.sub(r"(?i)https?://\S+|\b[\w.-]+\.io\S*", "", s)
    s = re.sub(r"(?i)voltick", "", s)
    s = re.sub(r"(?i)\bfront\s+volts?\b", "FRONT MAGNET", s)
    s = re.sub(r"(?i)\bvolts?\b", "MAGNET", s)
    s = re.sub(r"(?i)\borb ?(5|30)\b", "", s)
    return s.strip()
def num(s):
    m = re.search(r"-?\$?(-?[\d,]+(?:\.\d+)?)", str(s or ""))
    if not m: return None
    v = float(m.group(1).replace(",", "")); return -abs(v) if str(s).strip().startswith("-") else v
def money(s):
    m = re.match(r"\s*([+-]?)\$?([\d.]+)\s*([KMB]?)", str(s or ""))
    if not m: return None
    v = float(m.group(2)) * {"": 1, "K": 1e3, "M": 1e6, "B": 1e9}[m.group(3)]; return -v if m.group(1) == "-" else v
def head(s): return scrub(str(s or "").split(" (")[0])
def factors():
    c = J(ES / "es_conversions.json") or {}; f = (c.get("factors") or {}).get("spy_per_es") or 0.099112
    esc = (c.get("prices") or {}).get("ES=F"); return f, esc

def load_shot():
    D = {"gex": {}, "em": {}, "flow": {}, "press": {}}
    f, esc = factors(); spx_spot = (J(DIR / "gex_SPX.json") or {}).get("spot")
    basis = round(esc - spx_spot, 2) if esc and spx_spot else None
    D["conv"] = {"spy_per_es": f, "spx_basis": basis}
    def to_es(t, p):
        if p is None: return None
        if t == "SPY": return round(p / f, 1)
        if t == "SPX" and basis is not None: return round(p + basis, 1)
        return None
    for t in TK:
        g = J(DIR / f"gex_{t}.json")
        if not g: continue
        o = {"spot": g.get("spot"), "chg": scrub(g.get("chg")), "es_spot": to_es(t, g.get("spot"))}
        for m in ("zero", "all"):
            c = (g.get(m) or {}).get("cards") or {}
            fm = c.get("final_volt", ""); fmv = num(fm.split(":", 1)[1]) if ":" in str(fm) and re.search(r"\$\d", str(fm)) else None
            lv = {"net_gex": head(c.get("net_gex")), "regime": "POS" if str(c.get("net_gex", "")).startswith("+") else "NEG",
                  "call_wall": num(c.get("call_wall")), "magnet": num(c.get("volt")), "front_magnet": fmv, "flip": num(c.get("gamma_flip")),
                  "move": scrub(c.get("move")), "iv": head(c.get("atm_iv")) if "not" not in str(c.get("atm_iv")) else None}
            for k in ("call_wall", "magnet", "front_magnet", "flip"): lv["es_" + k] = to_es(t, lv[k])
            lv["pos"] = [(x["strike"], scrub(x["gex"])) for x in (g.get(m) or {}).get("top5_pos", [])][:5]
            lv["neg"] = [(x["strike"], scrub(x["gex"])) for x in (g.get(m) or {}).get("top5_neg", [])][:5]
            o[m] = lv
        D["gex"][t] = o
    E = J(DIR / "expected_moves.json") or {}
    for t in TK:
        x = E.get(t)
        if not x: continue
        D["em"][t] = {"px": x.get("price"), "read": scrub(x.get("read")).upper(),
                      "day": {k: (x.get("next_expiry") or {}).get(k) for k in ("to", "pct", "low", "high")},
                      "week": {k: (x.get("week") or {}).get(k) for k in ("to", "pct", "low", "high")}}
        for b in ("day", "week"):
            for k in ("low", "high"): D["em"][t][b]["es_" + k] = to_es(t, D["em"][t][b][k])
    F = J(DIR / "flow_pressure.json") or {}
    for t in TK:
        x = F.get(t)
        if not x: continue
        D["flow"][t] = {"net": scrub(x.get("net")), "netv": money(x.get("net")), "calls": scrub(x.get("calls")), "puts": scrub(x.get("puts")),
                        "pc": x.get("put_call"), "lean": scrub(x.get("lean")), "prints": x.get("prints"), "swept": x.get("swept_pct"),
                        "big": [[scrub(v) for v in r] for r in (x.get("large_prints") or [])[:6]]}
        p = (F.get("pressure") or {}).get(t) or {}
        sp = str(p.get("session_pressure", "")); bld = re.search(r"Building ([^;]*)", sp); fad = re.search(r"Fading (.*)", sp)
        D["press"][t] = {"g": {k: p.get(k) for k in ("gamma_speed", "vega_range", "delta_lean", "charm_clock", "vanna_vol_shift")},
                         "build": scrub(bld.group(1)) if bld else "", "fade": scrub(fad.group(1)) if fad else ""}
    for k in ("market_wide_all_tickers", "etf_index_complex"):
        x = F.get(k) or {}; D["flow"]["_" + k] = {"net": scrub(x.get("net")), "pc": x.get("put_call"), "lean": scrub(x.get("lean")), "calls": scrub(x.get("calls")), "puts": scrub(x.get("puts"))}
    return D

FG = ES / "free_gex" / "latest.json"
def _today_pt():
    from datetime import datetime; from zoneinfo import ZoneInfo; return datetime.now(ZoneInfo("America/Los_Angeles")).date()
def shot_date():
    """capture date of the screen data: explicit 'captured YYYY-MM-DD' stamp if present, else file mtime"""
    from datetime import datetime, date
    for n in ("gex_SPY.json", "expected_moves.json", "flow_pressure.json"):
        m = re.search(r"captured (\d{4}-\d{2}-\d{2})", json.dumps((J(DIR / n) or {}).get("as_of", "")))
        if m: return date.fromisoformat(m.group(1))
    try: return datetime.fromtimestamp((DIR / "gex_SPY.json").stat().st_mtime).date()
    except Exception: return None
def shot_fresh(): return shot_date() == _today_pt()
def load():
    """Primary: free computed chain (free_gex.py -> es_levels/free_gex/latest.json). Screenshot data kept as same-day compare row."""
    F = J(FG)
    if not F or not F.get("tick"):
        D = load_shot(); D["meta"] = {"stamp": "SCREEN CAPTURE", "stale": True, "free": False}; return D
    f = F.get("spy_per_es") or factors()[0]; basis = F.get("spx_basis")
    def to_es(t, p):
        if p is None: return None
        if t == "SPY": return round(p / f, 1)
        if t == "SPX" and basis is not None: return round(p + basis, 1)
        return None
    D = {"gex": {}, "em": {}, "flow": {}, "press": {}, "conv": {"spy_per_es": f, "spx_basis": basis}}
    for t in TK:
        x = (F["tick"] or {}).get(t)
        if not x: continue
        o = {"spot": x["spot"], "chg": x.get("chg"), "es_spot": to_es(t, x["spot"]), "stale": x.get("stale")}
        for m in ("zero", "all"):
            lv = dict(x[m]); lv["iv"] = None; lv["move"] = ""
            for k in ("call_wall", "put_wall", "magnet", "front_magnet", "flip"): lv["es_" + k] = to_es(t, lv.get(k))
            o[m] = lv
        em = x.get("em") or {}
        if em.get("day"): o["all"]["move"] = f"±{em['day']['mv']} by {em['day']['to']}"; o["all"]["iv"] = f"{100*em['day']['iv']:.1f}%" if em['day'].get('iv') else None
        D["gex"][t] = o
        if em.get("day") and em.get("week"):
            D["em"][t] = {"px": em["px"], "read": em["read"], "day": dict(em["day"]), "week": dict(em["week"])}
            for b in ("day", "week"):
                for k in ("low", "high"): D["em"][t][b]["es_" + k] = to_es(t, D["em"][t][b][k])
        D["flow"][t] = x["flow"]; D["press"][t] = x["press"]
    T = [x for x in F["tick"].values()]
    cp = sum(x.get("_cp", 0) for x in T); pp = sum(x.get("_pp", 0) for x in T); nt = sum(x.get("_net", 0) for x in T)
    mon = lambda v: ("+" if v >= 0 else "-") + f"${abs(v)/1e9:.2f}B"
    D["flow"]["_etf_index_complex"] = {"net": mon(nt), "pc": round(pp / cp, 2) if cp else None, "lean": "leaning bullish" if nt > 0 else "leaning bearish", "calls": mon(cp), "puts": mon(pp)}
    D["flow"]["_market_wide_all_tickers"] = {}
    asof = (F.get("as_of_pt") or "")[-5:]; stale = bool(F.get("stale")) or (F.get("as_of_pt") or "")[:10] != str(_today_pt())
    hh = ""
    try:
        from datetime import datetime; hh = datetime.strptime(asof, "%H:%M").strftime("%-I:%M %p")
    except Exception: pass
    day = (F.get("as_of_pt") or "")[5:10].replace("-", "/")
    D["meta"] = {"stamp": f"as of {hh} PT {day}", "stale": stale, "free": True, "asof_hm": hh}
    if shot_fresh():
        try: D["shot"] = load_shot()
        except Exception: pass
    return D
def stamp(D):
    m = D.get("meta") or {}
    return e(m.get("stamp", "")) + (' <b class="d">STALE</b>' if m.get("stale") else "")

e = lambda s: html.escape(str(s if s is not None else "—"))
def fx(v, d=2): return "—" if v is None else (f"{v:,.{d}f}".rstrip("0").rstrip(".") if isinstance(v, float) else f"{v:,}")
CSS = """<style>
.dk{background:#000;border:1px solid #2a2a2a;border-left:3px solid #ffb000;font:11px/1.4 'IBM Plex Mono',ui-monospace,Menlo,Consolas,monospace;color:#ffb000;font-variant-numeric:tabular-nums;margin:8px 0;min-width:0;overflow-x:auto}
.dk .dkh{display:flex;gap:10px;align-items:baseline;flex-wrap:wrap;background:#120d00;border-bottom:1px solid #a87400;padding:3px 8px}.dk .dkh b{letter-spacing:3px;font-size:13px}.dk .dkh small{color:#857d6a}
.dk table{border-collapse:collapse;width:100%}.dk th{color:#857d6a;font-weight:400;text-align:right;padding:1px 6px;border-bottom:1px solid #333;white-space:nowrap}.dk td{padding:1px 6px;border-bottom:1px solid #141414;text-align:right;white-space:nowrap;color:#e6e0cc}
.dk th:first-child,.dk td:first-child{text-align:left}.dk .a{color:#ffb000;font-weight:700}.dk .u{color:#3ddc5c}.dk .d{color:#ff4d4d}.dk .m{color:#857d6a}.dk .c{color:#22c7e8}.dk .es{color:#7fe0aa}
.dk .dkg{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:0}.dk .dkg>div{border-right:1px solid #222;padding:4px 6px;min-width:0}.dk .dkg>div:last-child{border-right:0}
.dk .tk{color:#000;background:#ffb000;padding:0 5px;font-weight:700;letter-spacing:1px}.dk .rd{padding:0 5px;font-weight:700;color:#000}
.dk .gb{display:grid;grid-template-columns:7.5em minmax(0,1fr) 3.4em;gap:6px;align-items:center}.dk .gz{position:relative;height:8px;background:#111}.dk .gz::after{content:"";position:absolute;left:50%;top:-1px;bottom:-1px;border-left:1px solid #555}.dk .gz i{position:absolute;top:0;bottom:0}
.dk .nt{color:#857d6a;padding:3px 8px;border-top:1px solid #222}.dk .bd{position:relative;height:10px;background:#111;margin:3px 0}.dk .bd i{position:absolute;top:0;bottom:0;background:#3a3000;border-left:1px solid #ffb000;border-right:1px solid #ffb000}.dk .bd u{position:absolute;top:-3px;bottom:-3px;width:2px;background:#22c7e8}
@media(max-width:900px){.dk .dkg{grid-template-columns:minmax(0,1fr)}.dk .dkg>div{border-right:0;border-bottom:1px solid #222}}
</style>"""
def rdc(r): return "#3ddc5c" if "BULL" in r else "#ff4d4d" if "BEAR" in r else "#ffb000"
def sgn(v): return "u" if (v or 0) > 0 else "d" if (v or 0) < 0 else "m"

def compare(D):
    S = D.get("shot"); lab = "same-day capture vs computed"
    if not S and (D.get("meta") or {}).get("free"):
        try:
            from datetime import datetime; S = load_shot(); lab = "last capture " + shot_date().strftime("%m/%d") + " (old) vs computed now"
        except Exception: S = None
    if not S or not S.get("gex"): return ""
    out = []
    for t in TK:
        a, b = (S["gex"].get(t) or {}).get("all") or {}, (D["gex"].get(t) or {}).get("all") or {}
        if a: out.append(f'<b class="a">{t}</b> flip {fx(a.get("flip"))} <span class="m">vs</span> {fx(b.get("flip"))} · wall {fx(a.get("call_wall"))} <span class="m">vs</span> {fx(b.get("call_wall"))} · magnet {fx(a.get("magnet"))} <span class="m">vs</span> {fx(b.get("magnet"))}')
    return f'<div class="nt">SCREEN COMPARE ({lab}) ▸ ' + " &nbsp;│&nbsp; ".join(out) + '</div>'
def gamma_grid(D):
    G = D["gex"]; cols = []
    for t in TK:
        if t not in G: continue
        g = G[t]; z, a = g.get("zero", {}), g.get("all", {})
        def row(lab, k, cls=""):
            es = lambda x: f' <span class="es">≈{fx(x.get("es_" + k), 1)}</span>' if x.get("es_" + k) is not None else ""
            return f'<tr><td>{lab}</td><td class="{cls}">{fx(z.get(k))}{es(z)}</td><td class="{cls}">{fx(a.get(k))}{es(a)}</td></tr>'
        h = (f'<div><div style="display:flex;justify-content:space-between;margin-bottom:3px"><span><span class="tk">{t}</span> <b class="c">{fx(g["spot"])}</b> <span class="{sgn(num(g["chg"]))}">{e(g["chg"])}</span></span>'
             f'{"<span class=es>ES ≈" + fx(g["es_spot"], 1) + "</span>" if g.get("es_spot") else ""}</div><table><tr><th>LEVEL</th><th>0DTE</th><th>{"NEAR EXP" if D.get("meta",{}).get("free") else "ALL EXP"}</th></tr>'
             f'<tr><td>NET GEX</td><td class="{"u" if z.get("regime")=="POS" else "d"}">{e(z.get("net_gex"))}</td><td class="{"u" if a.get("regime")=="POS" else "d"}">{e(a.get("net_gex"))}</td></tr>'
             + row("CALL WALL", "call_wall", "u") + (row("PUT WALL", "put_wall", "d") if a.get("put_wall") is not None else "") + row("MAGNET", "magnet", "a") + row("GAMMA FLIP", "flip", "c")
             + (f'<tr><td>FRONT MAGNET</td><td class="m">—</td><td class="a">{fx(a.get("front_magnet"))}{" <span class=es>≈"+fx(a.get("es_front_magnet"),1)+"</span>" if a.get("es_front_magnet") else ""}</td></tr>' if a.get("front_magnet") else "")
             + f'<tr><td>MOVE</td><td colspan="2">{e(a.get("move") or z.get("move"))}{" · IV " + e(a["iv"]) if a.get("iv") else ""}</td></tr></table>')
        for m, lab in (("zero", "0DTE"), ("all", "ALL EXP")):
            x = g.get(m, {}); P, N = x.get("pos", []), x.get("neg", [])
            h += f'<table style="margin-top:4px"><tr><th>{lab} +GEX</th><th></th><th>−GEX</th><th></th></tr>' + "".join(
                f'<tr><td class="u">{fx(P[i][0]) if i < len(P) else ""}</td><td class="u">{e(P[i][1]) if i < len(P) else ""}</td><td class="d">{fx(N[i][0]) if i < len(N) else ""}</td><td class="d">{e(N[i][1]) if i < len(N) else ""}</td></tr>' for i in range(5)) + '</table>'
        cols.append(h + "</div>")
    c = D["conv"]
    return (f'<section class="zone" id="z-gg"><div class="dk" id="dkGG"><div class="dkh"><b>GAMMA GRID</b><small>dealer gamma by strike · 0DTE vs near-term expirations (thru next monthly) · {stamp(D)} · SRC DESK</small></div>'
            f'<div class="dkg">{"".join(cols)}</div><div class="nt">MAGNET = largest-pull strike · FRONT MAGNET = nearest-expiry magnet · flip = net-gamma zero line (above = dealers dampen, below = dealers chase). '
            f'<span class="es">≈ES</span> from SPY ÷ {c["spy_per_es"]:.6f} (ES-to-SPY factor) and SPX + basis {fx(c["spx_basis"])} (ES − SPX, live). QQQ has no ES equivalent. GEX = gamma × OI × 100 × spot² × 1% (calls +, puts −); flip solved on a re-priced gamma profile.</div>{compare(D)}</div></section>')

def gauge(v):
    v = max(-1, min(1, v or 0)); w = abs(v) * 50
    return f'<span class="gz"><i style="{"left:50%" if v >= 0 else f"left:{50-w:.0f}%"};width:{w:.0f}%;background:{"#3ddc5c" if v >= 0 else "#ff4d4d"}"></i></span>'
GN = (("gamma_speed", "GAMMA SPEED"), ("vega_range", "VEGA RANGE"), ("delta_lean", "DELTA LEAN"), ("charm_clock", "CHARM CLOCK"), ("vanna_vol_shift", "VANNA VOL"))
def undertow(D):
    cols = []
    for t in TK:
        f, p = D["flow"].get(t), D["press"].get(t)
        if not f: continue
        lc = "u" if "bull" in f["lean"].lower() else "d" if "bear" in f["lean"].lower() else "a"
        h = (f'<div><div style="margin-bottom:3px"><span class="tk">{t}</span> <b class="{sgn(f["netv"])}">NET {e(f["net"])}</b></div><table>'
             f'<tr><td>CALL PREM</td><td class="u">{e(f["calls"])}</td><td>PUT PREM</td><td class="d">{e(f["puts"])}</td></tr>'
             f'<tr><td>P/C</td><td class="a">{fx(f["pc"])}</td><td>LEAN</td><td class="{lc}">{e(f["lean"].upper())}</td></tr>'
             f'<tr><td>PRINTS</td><td>{fx(f["prints"])}</td><td>SWEPT</td><td>{fx(f["swept"])+"%" if f.get("swept") is not None else "—"}</td></tr></table>'
             '<table style="margin-top:4px"><tr><th>STRIKE</th><th>EXP</th><th>C/P</th><th>SIDE</th><th>PREM</th></tr>'
             + "".join(f'<tr><td>{e(r[1])}</td><td class="m">{e(r[2])}</td><td class="{"u" if r[3]=="CALL" else "d"}">{e(r[3][0])}</td><td style="text-align:left;white-space:normal" class="m">{e(r[4])}</td><td class="a">{e(r[5])}</td></tr>' for r in f["big"]) + '</table>')
        if p:
            h += '<div style="margin-top:5px;display:grid;gap:2px"><div class="m">DEALER PRESSURE · −1 … +1</div>' + "".join(
                f'<div class="gb"><span>{lab}</span>{gauge(p["g"].get(k))}<b class="{sgn(p["g"].get(k))}" style="text-align:right">{(p["g"].get(k) or 0):+.2f}</b></div>' for k, lab in GN) + '</div>'
            h += f'<div style="margin-top:4px"><span class="u">▲ {"HOT VOL/OI" if D.get("meta",{}).get("free") else "BUILDING"}</span> {e(p["build"])}<br><span class="d">▼ {"MOST ACTIVE" if D.get("meta",{}).get("free") else "FADING"}</span> {e(p["fade"])}</div>'
        cols.append(h + "</div>")
    mw, ex = D["flow"].get("_market_wide_all_tickers", {}), D["flow"].get("_etf_index_complex", {})
    return (f'<section class="zone" id="z-ut"><div class="dk" id="dkUT" style="border-left-color:#22c7e8"><div class="dkh"><b>UNDERTOW</b><small>pressure &amp; flow · options premium tape + dealer pressure · {stamp(D)} · SRC DESK</small></div>'
            f'<div class="nt" style="border-top:0;border-bottom:1px solid #222">ALL TICKERS <b class="{sgn(money(mw.get("net")))}">{e(mw.get("net"))}</b> · P/C {fx(mw.get("pc"))} · {e(mw.get("lean"))} &nbsp;│&nbsp; ETF/INDEX <b class="{sgn(money(ex.get("net")))}">{e(ex.get("net"))}</b> · P/C {fx(ex.get("pc"))} · {e(ex.get("lean"))}</div>'
            f'<div class="dkg">{"".join(cols)}</div><div class="nt">Large prints = biggest premium prints of the session. Gauges are normalized −1…+1 dealer-hedging pressure from open-interest greeks. Premium = session volume × mid; side by price change. HOT = highest volume/OI strikes; MOST ACTIVE = top volume strikes.</div></div></section>')

def bands(D):
    rows = ""
    for t in TK:
        x = D["em"].get(t)
        if not x: continue
        for b, lab in (("day", "DAILY"), ("week", "WEEKLY")):
            y = x[b]; lo, hi, px = y["low"], y["high"], x["px"]
            pos = 100 * (px - lo) / (hi - lo) if lo and hi and hi > lo else 50
            esb = f'<span class="es">≈{fx(y["es_low"],1)}–{fx(y["es_high"],1)}</span>' if y.get("es_low") else '<span class="m">—</span>'
            rows += (f'<tr><td>{"<span class=tk>"+t+"</span>" if b=="day" else ""}</td><td>{lab} <span class="m">→{e(y["to"])}</span></td><td class="d">{fx(lo)}</td><td class="u">{fx(hi)}</td><td class="a">±{fx(y["pct"])}%</td>'
                     f'<td style="width:22%"><div class="bd"><i style="left:5%;right:5%"></i><u style="left:{5+0.9*max(0,min(100,pos)):.0f}%"></u></div></td><td>{esb}</td>'
                     f'<td>{"<span class=rd style=background:"+rdc(x["read"])+">"+e(x["read"])+"</span>" if b=="day" else ""}</td><td class="c">{fx(px) if b=="day" else ""}</td></tr>')
    return (f'<div class="dk" id="dkEM" style="grid-column:1/-1;border-left-color:#22c7e8"><div class="dkh"><b>BLAST RADIUS // DESK BANDS</b><small>expected-move bands (ATM straddle × 0.85) · {stamp(D)} · day → {e(next(iter(D["em"].values()),{}).get("day",{}).get("to"))} · week → {e(next(iter(D["em"].values()),{}).get("week",{}).get("to"))} · SRC DESK</small></div>'
            f'<div style="padding:3px 8px;border-bottom:1px solid #222;color:#e6e0cc">{gline(D)}</div><table><tr><th>TKR</th><th>BAND</th><th>LOW</th><th>HIGH</th><th>±%</th><th>POSITION</th><th>ES ≈</th><th>READ</th><th>SPOT</th></tr>{rows}</table>'
            f'<div class="nt">Cyan tick = spot inside the band. READ = desk directional read for the next session.</div></div>')

def gline(D):
    out = []
    for t in TK:
        a = (D["gex"].get(t) or {}).get("all") or {}
        if not a: continue
        es = f' <span class="es">(ES≈{fx(a.get("es_flip"),1)} / {fx(a.get("es_call_wall"),1)})</span>' if a.get("es_flip") else ""
        out.append(f'<b class="a">{t}</b> flip <b class="c">{fx(a.get("flip"))}</b> · wall <b class="u">{fx(a.get("call_wall"))}</b> · magnet {fx(a.get("magnet"))}{es}')
    return '<span style="color:#ffb000;font-weight:700">GAMMA LINE · ALL EXP ▸</span> ' + " &nbsp;│&nbsp; ".join(out) if out else ""

def main_html(D): return CSS + bands(D)
def command_html(D): return CSS + gamma_grid(D) + undertow(D)
if __name__ == "__main__":
    D = load(); print(json.dumps(D["conv"]), {k: list(v) for k, v in D.items() if isinstance(v, dict)})
