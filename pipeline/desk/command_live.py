"""Command page: refresh the free, live-computable blocks on every Actions run.

  * GAMMA GRID + UNDERTOW sections from the free option-chain compute (desk_bands / free_gex latest.json).
    If that compute is missing or not from today, the sections are left exactly as they are.
  * At-a-glance ES price + its 'as of' time (ES vs pivot, next-level distances) from a free 1m ES quote,
    only while the glance plan session is today or upcoming, and only when the quote is newer than the one shown.
    Plan text, levels, catalysts and every other glance field stay as the nightly sweep wrote them.
usage: python3 command_live.py <command/index.html>
"""
from __future__ import annotations

import json, logging, re, sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

PT, ET = ZoneInfo("America/Los_Angeles"), ZoneInfo("America/New_York")
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))


def patch_bands(h: str) -> str:
    import desk_bands as db
    D = db.load()
    m = D.get("meta") or {}
    if not m.get("free") or m.get("stale") or not D.get("gex"):
        print("command_live: free gamma compute not current; GAMMA GRID / UNDERTOW left as is"); return h
    for sid, html in (("z-gg", db.gamma_grid(D)), ("z-ut", db.undertow(D))):
        tag = f'<section class="zone" id="{sid}"'
        if h.count(tag) != 1 or not html.startswith(tag):
            print(f"command_live: {sid} anchor not found; left as is"); continue
        a = h.index(tag); z = h.index("</section>", a) + len("</section>")
        h = h[:a] + html + h[z:]
    return h


def es_quote():
    """(price, ET timestamp) of the last free 1m ES bar, or (None, None)."""
    import yfinance as yf
    logging.getLogger("yfinance").setLevel(logging.CRITICAL)
    try:
        x = yf.Ticker("ES=F").history(period="1d", interval="1m", prepost=True, auto_adjust=False)
        if not len(x):
            return None, None
        return round(float(x.Close.iloc[-1]) * 4) / 4, x.index[-1].tz_convert(ET)
    except Exception as ex:
        print("command_live: ES quote failed:", str(ex)[:80], file=sys.stderr); return None, None


def asof_label(ts) -> str:
    p = ts.astimezone(PT)
    return f"{p:%a} {p.month}/{p.day} {p:%I:%M %p} PT".replace(" 0", " ")


def patch_glance(h: str, quote=es_quote, now=None) -> str:
    m = re.search(r'(<script id="glance-data" type="application/json">)(.*?)(</script>)', h, re.S)
    if not m:
        return h
    G = json.loads(m.group(2))
    now = (now or datetime.now(PT)).astimezone(PT)
    sess = str(G.get("session") or "")
    if not sess or sess < now.date().isoformat():
        print("command_live: glance plan session is past; ES price left as is"); return h
    px, ts = quote()
    if px is None:
        return h
    es = G.get("es") or {}
    prev = es.get("asof_iso")
    if prev and prev >= ts.isoformat():
        return h
    es.update(price=px, asof=asof_label(ts), asof_iso=ts.isoformat())
    G["es"] = es
    return h[:m.start()] + m.group(1) + json.dumps(G, ensure_ascii=False).replace("</", "<\\/") + m.group(3) + h[m.end():]


def main(f):
    p = Path(f); h = p.read_text(encoding="utf-8"); n = patch_glance(patch_bands(h))
    if n != h:
        p.write_text(n, encoding="utf-8"); print("command_live: patched", f)
    else:
        print("command_live: unchanged")


if __name__ == "__main__":
    main(sys.argv[1])
