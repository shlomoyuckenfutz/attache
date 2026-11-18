"""Build the public /live-trades/ page from pipeline/inputs/journal/v2_log.json.

The input is an export of the V2 journal Log tab (trade rows only). The page never
names the file, a sheet, or a source. Missing data renders as 'awaiting', never 'error'.
usage: python3 live_trades.py [OUT.html]
"""
from __future__ import annotations

import json, sys
from datetime import datetime
from html import escape
from pathlib import Path

DESK = Path(__file__).resolve().parent
ROOT = Path(__import__("os").environ.get("ORB_SITE") or DESK.parents[1])
INPUT = Path(__import__("os").environ.get("ORB_INPUTS") or ROOT / "pipeline" / "inputs") / "journal" / "v2_log.json"
AWAITING = "awaiting"


def load(path=None):
    p = Path(path or INPUT)
    if not p.is_file():
        return None
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    trades = data.get("trades") if isinstance(data, dict) else None
    if not isinstance(trades, list):
        return None
    return [t for t in trades if isinstance(t, dict) and (t.get("sym") or t.get("date"))]


def is_futures(t):
    return str(t.get("sym") or "").startswith("/")


def money_val(v):
    if v is None or v == "":
        return None
    try:
        return round(float(v), 2)
    except (TypeError, ValueError):
        return None


def entry_dollars(t):
    """Dollar cost at entry: option premium, stock notional. Futures use planned risk when present."""
    inst = t.get("inst") or ""
    entry, qty = money_val(t.get("entry")), money_val(t.get("qty"))
    if inst == "Futures":
        return money_val(t.get("risk"))
    if entry is None or qty is None:
        return None
    if inst == "Stock":
        return round(entry * qty, 2)
    px = entry / 100.0 if entry >= 100 else entry
    return round(px * qty * 100.0, 2)


def net_pct(t):
    net, cost = money_val(t.get("net")), entry_dollars(t)
    if net is None or not cost:
        return None
    return net / cost


def contract(t):
    sym = str(t.get("sym") or "").strip()
    inst = t.get("inst") or ""
    strike = t.get("strike")
    if inst in ("Call", "Put") and strike not in (None, ""):
        try:
            s = float(strike)
            label = str(int(s)) if s == int(s) else f"{s:g}"
        except (TypeError, ValueError):
            label = str(strike).replace("$", "").replace(",", "")
        return f"{sym} {label}{'C' if inst == 'Call' else 'P'}"
    return sym or AWAITING


def fmt_money(v, awaiting=AWAITING):
    n = money_val(v)
    if n is None:
        return awaiting
    sign = "-" if n < 0 else ""
    body = f"{abs(n):,.2f}".replace(".00", "") if abs(n - round(n)) < 0.005 else f"{abs(n):,.2f}"
    if abs(n - round(n)) < 0.005:
        body = f"{abs(round(n)):,}"
    return f"{sign}${body}"


def fmt_px(v, inst=None):
    n = money_val(v)
    if n is None:
        return AWAITING
    if inst == "Futures" or (abs(n) >= 100 and n == int(n)):
        return f"{int(n):,}"
    if n == int(n):
        return str(int(n))
    text = f"{n:.2f}".rstrip("0").rstrip(".")
    return text


def fmt_pct(v):
    if v is None:
        return AWAITING
    pct = v * 100.0
    if abs(pct - round(pct)) < 0.05:
        return f"{pct:.0f}%"
    return f"{pct:.1f}%"


def fmt_qty(v):
    n = money_val(v)
    if n is None:
        return AWAITING
    return str(int(n)) if n == int(n) else f"{n:g}"


def fmt_date(iso):
    try:
        d = datetime.strptime(str(iso)[:10], "%Y-%m-%d")
    except (TypeError, ValueError):
        return AWAITING
    return d.strftime("%b %-d, %Y") if sys.platform != "win32" else d.strftime("%b %d, %Y").replace(" 0", " ")


def as_of_iso(trades):
    dates = []
    for t in trades or []:
        raw = str(t.get("date") or "")[:10]
        try:
            dates.append(datetime.strptime(raw, "%Y-%m-%d").date())
        except ValueError:
            pass
    return max(dates).isoformat() if dates else None


def summary(trades):
    trades = trades or []
    q = opt = fut = None
    q_any = opt_any = fut_any = False
    for t in trades:
        qv, nv = money_val(t.get("q_out_pl")), money_val(t.get("net"))
        if qv is not None:
            q = (q or 0) + qv
            q_any = True
        if nv is None:
            continue
        if is_futures(t):
            fut = (fut or 0) + nv
            fut_any = True
        else:
            opt = (opt or 0) + nv
            opt_any = True
    equity = None
    for t in trades:
        ev = money_val(t.get("equity"))
        if ev is not None:
            equity = ev
    return {
        "q_out": round(q, 2) if q_any else None,
        "options": round(opt, 2) if opt_any else None,
        "futures": round(fut, 2) if fut_any else None,
        "equity": equity,
        "as_of": as_of_iso(trades),
        "count": len(trades),
    }


def _cls(v):
    n = money_val(v)
    if n is None or n == 0:
        return ""
    return "up" if n > 0 else "dn"


def _td(text, cls="", extra=""):
    c = f' class="{cls}"' if cls else ""
    return f"<td{c}{extra}>{escape(str(text))}</td>"


def rows_html(trades):
    # Newest first; later sheet rows of the same day stay above earlier ones.
    ordered = list(reversed(trades or []))
    out = []
    for t in ordered:
        net = money_val(t.get("net"))
        inst = t.get("inst")
        cost = entry_dollars(t)
        cost_txt = fmt_money(cost) if not is_futures(t) else (fmt_money(cost) if cost is not None else AWAITING)
        out.append(
            "<tr>"
            + _td(fmt_date(t.get("date")))
            + _td(contract(t))
            + _td(t.get("side") or AWAITING)
            + _td(fmt_qty(t.get("qty")), extra=' style="text-align:right"')
            + _td(cost_txt, extra=' style="text-align:right"')
            + _td(fmt_px(t.get("q_out"), inst), extra=' style="text-align:right"')
            + _td(fmt_px(t.get("exit"), inst), extra=' style="text-align:right"')
            + _td(fmt_money(net), _cls(net), ' style="text-align:right"')
            + _td(fmt_pct(net_pct(t)), _cls(net), ' style="text-align:right"')
            + "</tr>"
        )
    return "\n".join(out)


def tile(label, value, cls=""):
    shown = fmt_money(value) if value is not None else AWAITING
    klass = cls or _cls(value)
    return (
        f'<div class="tile"><div class="lb">{escape(label)}</div>'
        f'<div class="vv{" " + klass if klass else ""}">{escape(shown)}</div></div>'
    )


def page(trades):
    s = summary(trades)
    if not trades:
        stamp = "Journal is awaiting the latest trades."
        tiles = "".join(tile(lb, None) for lb in ("Q OUT ONLY", "OPTIONS · FULL OUT", "FUTURES", "EQUITY"))
        table = f'<p class="hd">{AWAITING}</p>'
    else:
        asof = s["as_of"]
        when = fmt_date(asof) if asof else AWAITING
        # weekday prefix when we have a real date
        try:
            wd = datetime.strptime(asof, "%Y-%m-%d").strftime("%a")
            when = f"{wd} {when}"
        except (TypeError, ValueError):
            pass
        n = s["count"]
        stamp = f"{n} trade{'s' if n != 1 else ''} · as of {when}"
        tiles = (
            tile("Q OUT ONLY", s["q_out"])
            + tile("OPTIONS · FULL OUT", s["options"])
            + tile("FUTURES", s["futures"])
            + tile("EQUITY", s["equity"], "eq")
        )
        body = rows_html(trades)
        table = (
            '<div class="tw"><table><thead><tr>'
            "<th>Date</th><th>Contract</th><th>Side</th><th>Qty</th><th>Cost</th>"
            "<th>Q Out</th><th>All Out</th><th>Net $</th><th>Net %</th>"
            f"</tr></thead><tbody>\n{body}\n</tbody></table></div>"
        )
    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>ATTACHÉ | MY LIVE TRADES</title><link rel="icon" href="data:,">
<link href="https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;600;700&display=swap" rel="stylesheet">
<style>
:root{{--bg:#000;--ln:#232323;--ln2:#333;--amb:#ffb000;--amb2:#a87400;--txt:#e6e0cc;--mut:#857d6a;--up:#3ddc5c;--dn:#ff4d4d;--cy:#22c7e8}}
*{{box-sizing:border-box}}body{{margin:0;background:#000;color:var(--txt);font:13px/1.55 'IBM Plex Mono',ui-monospace,Menlo,Consolas,monospace;font-variant-numeric:tabular-nums}}
main{{max-width:1100px;margin:0 auto;padding:10px 12px 40px}}h1{{color:var(--amb);font-size:16px;letter-spacing:.12em;margin:8px 0 4px}}
.hd{{color:var(--mut);font-size:12px;margin:0 0 10px}}
.tiles{{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:8px;margin:0 0 12px}}
.tile{{border:1px solid var(--ln2);border-radius:6px;background:#070707;padding:8px 12px}}
.tile .lb{{color:var(--mut);font-size:11px;letter-spacing:.12em;margin:0 0 4px}}
.tile .vv{{font-size:20px;font-weight:700;color:var(--txt);letter-spacing:.02em}}
.tile .vv.up{{color:var(--up)}}.tile .vv.dn{{color:var(--dn)}}.tile .vv.eq{{color:var(--amb)}}
.tw{{overflow-x:auto;max-width:100%;border:1px solid var(--ln2);border-radius:6px;background:#070707}}
table{{border-collapse:collapse;width:100%;font-variant-numeric:tabular-nums}}
th,td{{border-bottom:1px solid #1c1c1c;padding:6px 10px;text-align:left;white-space:nowrap}}
th{{color:var(--mut);font-size:11px;letter-spacing:.08em;font-weight:600;background:#0c0c0c}}
td{{color:var(--txt)}}tr:last-child td{{border-bottom:0}}
td.up{{color:var(--up)}}td.dn{{color:var(--dn)}}
@media(max-width:800px){{.tiles{{grid-template-columns:repeat(2,minmax(0,1fr))}}.tile .vv{{font-size:18px}}}}
@media(max-width:700px){{body{{font-size:13.5px}}main{{padding:10px 8px 40px}}th,td{{padding:6px 8px}}}}
</style></head><body>
<main>
<h1>MY LIVE TRADES</h1>
<p class="hd">{escape(stamp)}</p>
<div class="tiles">{tiles}</div>
{table}
</main>
</body></html>
"""


def write(trades, dest):
    dest = Path(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(page(trades), encoding="utf-8")
    return dest


def main(argv=None):
    argv = list(argv or sys.argv[1:])
    dest = Path(argv[0]) if argv else ROOT / "live-trades" / "index.html"
    src = argv[1] if len(argv) > 1 else None
    trades = load(src)
    write(trades, dest)
    print("live-trades ->", dest)
    return 0


if __name__ == "__main__":
    sys.exit(main())
