"""Command page: ORB15 cards, Cumulative R, bot box and HOURLY BREAKS, built from the committed
inputs/orb/orb_status.json. Idempotent. Never moves the page backwards: if the page already carries a
newer ORB session than the inputs, it is left alone. Usage: orb_status.py <command/index.html>"""
import json, os, re, sys
from datetime import date, datetime
from pathlib import Path

INP = Path(os.environ.get("ORB_INPUTS", Path(__file__).resolve().parent.parent / "inputs")) / "orb" / "orb_status.json"


def payload(h):
    m = re.search(r"const D=", h)
    i = h.index("{", m.end() - 1)
    o, n = json.JSONDecoder().raw_decode(h[i:])
    return i, n, o


def hm(i):
    t = 570 + i
    return f"{t // 60}:{t % 60:02d}"


def brk(bars, idx, lvl, up):
    if idx is None:
        return "—", False
    held = bars[idx][4] > lvl if up else bars[idx][4] < lvl
    cls = "up" if up else "dn"
    return f"<span class='{cls}'><span class='hr-dot {cls}'></span>{hm(idx)} <span class='mut'>{'held' if held else 'wick'}</span></span>", True


def card(sym, o, hrs, dow):
    rows, nu, nd = [], 0, 0
    for r in hrs:
        u, bu = brk(o["bars"], r["up"], r["H"], True)
        d, bd = brk(o["bars"], r["dn"], r["L"], False)
        nu += bu; nd += bd
        st = ('<span class="mut">both sides</span>' if bu and bd else '<span class="up">strong / highs lost</span>' if bu
              else '<span class="dn">weak / lows lost</span>' if bd else '<span class="mut">held</span>')
        rows.append(f"<tr><td>{hm(r['start'])} ET</td><td>{r['H']:.2f}</td><td>{r['L']:.2f}</td><td>{u}</td><td>{d}</td><td>{st}</td></tr>")
    html = (f'<div class="hr-card" id="hr{sym}"><h3>{sym} · HOURLY BREAKS <small>{dow} {o["date"]} · 1m bars · times ET</small></h3>\n'
            '<table class="hr-tbl"><thead><tr><th>hour</th><th>H</th><th>L</th><th>broke high</th><th>broke low</th><th>status</th></tr></thead>\n'
            f'<tbody>{"".join(rows)}</tbody></table></div>')
    return html, nu, nd, len(hrs)


def main(f):
    src = json.loads(INP.read_text())
    h = Path(f).read_text()
    i, n, D = payload(h)
    cur = ((D.get("orb") or {}).get("SPY") or {}).get("date") or ""
    if cur > src["asof"]:
        print(f"orb_status: page has {cur} > inputs {src['asof']}; left alone"); return
    orb = src["orb"]
    dow = date.fromisoformat(src["asof"]).strftime("%a")
    D["built"] = datetime.now().strftime("%Y-%m-%d %H:%M PT")
    D["orb"], D["hourly"], D["eq"] = orb, src["hourly"], src["eq"]
    b, bp = D.get("bot") or {}, src["bot"]
    D["bot"] = {"day": f"paused since {bp['paused_since']} · last session {bp['last_session']}",
                "last_tick": b.get("last_tick"), "ticks": b.get("ticks"),
                "v": {"status": "PAUSED", "range_high": (b.get("v") or {}).get("range_high"), "range_low": (b.get("v") or {}).get("range_low"),
                      "side": None, "entry_price": None, "entry_time": None, "stop": None, "target": None, "realized_pnl": 0.0},
                "fills": [], "hb": {"ts": (b.get("hb") or {}).get("ts"), "mode": "paused", "day": bp["paused_since"],
                                    "phase": f"paused since {bp['paused_since']}"}}
    h = h[:i] + json.dumps(D, ensure_ascii=False, default=float).replace("</", "<\\/") + h[i + n:]
    cs, cq = (card(s, orb[s], src["hourly"][s], dow) for s in ("SPY", "QQQ"))
    up, dn = cs[1] + cq[1], cs[2] + cq[2]
    tape = "weak tape (lows kept giving way)" if dn > up else "strong tape (highs kept giving way)" if up > dn else "two-sided tape"
    take = (f"SPY: {cs[2]}/{cs[3]} hour lows broke later · {cs[1]}/{cs[3]} hour highs broke later · QQQ: {cq[2]}/{cq[3]} hour lows broke later · "
            f"{cq[1]}/{cq[3]} hour highs broke later — {tape}.")
    sec = (f'<section class="zone" id="z-hr"><div class="zh"><b>HOURLY BREAKS</b><small>RTH hour hi/lo · later breaks · last data {dow} {src["asof"]} ET</small></div>\n'
           f'<div class="hr-wrap">{cs[0]}{cq[0]}</div><div class="hr-take">{take}</div></section>')
    a = h.index('<section class="zone" id="z-hr"'); z = h.index("</section>", a) + len("</section>")
    h = h[:a] + sec + h[z:]
    Path(f).write_text(h)
    print("orb_status:", f, src["asof"], {k: v.get("R") for k, v in orb.items()})


if __name__ == "__main__":
    main(sys.argv[1])
