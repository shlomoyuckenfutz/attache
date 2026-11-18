"""Intraday ORB15 + HOURLY BREAKS inputs from free 1m bars, for the 15-min Actions refresh.

Writes pipeline/inputs/orb/orb_status.json (the file orb_status.py renders on Command) for the latest
RTH session: ORB15 cards for SPY, QQQ, /ES and SPX (same rules as the nightly rebuild), SPY/QQQ hourly
breaks, and, once a session is complete, that day's R appended to the SPY/QQQ cumulative-R series.

Never moves backwards: an older session, or the same session with fewer bars than the file already has,
leaves the file untouched. A failed or empty pull leaves the file untouched. ORB15 only.
usage: python3 orb_live.py [--inputs DIR]
"""
from __future__ import annotations

import json, logging, os, sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

ET = ZoneInfo("America/New_York")
RTH0, RTH1 = 570, 960          # 09:30 and 16:00 ET in minutes
ENTRY_LAST, EXIT_LAST = 331, 380
FULL = 390
SYMS = (("SPY", "SPY", "SPY"), ("QQQ", "QQQ", "QQQ"), ("ES=F", "/ES", "ES"), ("^GSPC", "SPX", "SPX"))
R_NOTE = "gross R (same rules, no costs)"


def inputs_dir() -> Path:
    if "--inputs" in sys.argv:
        return Path(sys.argv[sys.argv.index("--inputs") + 1])
    return Path(os.environ.get("ORB_INPUTS") or Path(__file__).resolve().parent.parent / "inputs")


def session_bars(df, day):
    """1m RTH bars for one ET date as [[i, o, h, l, c], ...] with gaps forward-filled; None if no bars."""
    import numpy as np, pandas as pd
    if df is None or not len(df):
        return None
    idx = df.index.tz_convert(ET)
    m = idx.hour * 60 + idx.minute
    sel = (idx.date == day) & (m >= RTH0) & (m < RTH1)
    g = df[sel]
    if not len(g):
        return None
    mm = (m[sel] - RTH0).to_numpy()
    nb = int(mm.max()) + 1
    a = np.full((nb, 4), np.nan)
    a[mm] = g[["Open", "High", "Low", "Close"]].to_numpy(dtype=float)
    a = pd.DataFrame(a).ffill().bfill().to_numpy()
    return [[i] + [round(float(x), 2) for x in a[i]] for i in range(nb)]


def card(label, day, bars, complete):
    """ORB15 card. Same rules as the nightly rebuild: 5m close beyond the 15-min range (entries 9:49-15:00 ET),
    stop at the opposite edge, half off at 1R then breakeven, time exit at 15:49 ET."""
    nb = len(bars)
    o = {"sym": label, "date": day.isoformat(), "px": bars[-1][4], "bars": bars}
    hh, ll = max(b[2] for b in bars[:15]), min(b[3] for b in bars[:15])
    o.update(H=round(hh, 2), L=round(ll, 2), M=round((hh + ll) / 2, 2))
    if nb < 15:
        o["status"] = "FORMING"
        return o
    c = [b[4] for b in bars]
    en = None
    for i in range(19, min(ENTRY_LAST, nb), 5):
        if c[i] > hh: en = (i, 1); break
        if c[i] < ll: en = (i, -1); break
    if not en:
        o["status"] = "INSIDE"
        if complete or nb > ENTRY_LAST:
            o.update(R=0.0, result="NO TRADE")
        return o
    i, s = en; e = c[i]; st = ll if s == 1 else hh; risk = (e - st) * s; tg = e + s * risk
    o.update(status="BROKE LONG" if s == 1 else "BROKE SHORT", entry=[i, e], stop=st, target=round(tg, 3), side=s)
    ev, stage, stop, R, j = [], 0, st, None, i
    for j in range(i + 1, min(EXIT_LAST, nb)):
        hi, lo = bars[j][2], bars[j][3]
        adv, fav = (lo, hi) if s == 1 else (hi, lo)
        if (adv - stop) * s <= 0:
            ev.append([j, stop, "STOP" if stage == 0 else "BE"]); R = -1.0 if stage == 0 else 0.5; break
        if stage == 0 and (fav - tg) * s >= 0:
            ev.append([j, round(tg, 3), "1R"]); stage = 1; stop = e
    else:
        x = c[j]; r = (x - e) * s / risk; R = r if stage == 0 else 0.5 + 0.5 * r
        if complete or nb >= EXIT_LAST:
            ev.append([j, x, "TIME"])
        else:  # trade still open: mark to the last bar, labelled OPEN (not a final result)
            o.update(exits=ev, R=round(R, 4), result="OPEN", r_note="open trade, marked to last bar")
            return o
    o.update(exits=ev, R=round(R, 4), result="WIN" if R > 0 else "LOSS" if R < 0 else "FLAT", r_note=R_NOTE)
    return o


def hourly(o):
    b = o["bars"]; hrs = []
    for s0 in range(0, len(b), 60):
        blk, later = b[s0:s0 + 60], b[s0 + 60:]
        H, L = max(x[2] for x in blk), min(x[3] for x in blk)
        hrs.append({"start": s0, "len": len(blk), "H": H, "L": L,
                    "up": next((x[0] for x in later if x[2] > H), None), "dn": next((x[0] for x in later if x[3] < L), None),
                    "upn": sum(1 for x in later if x[2] > H), "dnn": sum(1 for x in later if x[3] < L), "n": len(later)})
    return hrs


def eq_stats(d, r):
    nz = [x for x in r if x != 0]; w = [x for x in nz if x > 0]; l = [x for x in nz if x < 0]
    c = pk = dd = 0.0
    for x in r:
        c += x; pk = max(pk, c); dd = max(dd, pk - c)
    return {"n": len(nz), "days": len(r), "win": round(100 * len(w) / len(nz), 1) if nz else 0.0,
            "pf": round(sum(w) / -sum(l), 3) if l else None, "avg_r": round(sum(nz) / len(nz), 4) if nz else 0.0,
            "tot_r": round(sum(r), 1), "max_dd_r": round(dd, 1), "first": d[0], "last": d[-1]}


def extend_eq(eq, orb, day, complete):
    """Append a completed session's R to the SPY/QQQ cumulative series (once per day)."""
    if not complete:
        return eq
    for s in ("SPY", "QQQ"):
        e, o = (eq or {}).get(s), orb.get(s)
        if not e or not o or o.get("R") is None or o.get("result") == "OPEN":
            continue
        if e["d"] and e["d"][-1] >= day:
            continue
        e["d"].append(day); e["r"].append(o["R"]); e["stats"] = eq_stats(e["d"], e["r"])
    return eq


def fetch():
    import yfinance as yf
    logging.getLogger("yfinance").setLevel(logging.CRITICAL)
    out = {}
    for tk, _, key in SYMS:
        try:
            h = yf.Ticker(tk).history(period="5d", interval="1m", prepost=False, auto_adjust=False)
            out[key] = h if len(h) else None
        except Exception as ex:  # keep going; a missing symbol is handled below
            print(f"orb_live: {key} pull failed: {str(ex)[:80]}", file=sys.stderr); out[key] = None
    return out


def build(frames, prev, now=None):
    """Return the new orb_status payload, or None when the file must be left alone."""
    now = (now or datetime.now(ET)).astimezone(ET)
    spy = frames.get("SPY")
    if spy is None or not len(spy):
        return None
    idx = spy.index.tz_convert(ET); m = idx.hour * 60 + idx.minute
    days = sorted({d for d, mm in zip(idx.date, m) if RTH0 <= mm < RTH1})
    if not days:
        return None
    day = days[-1]
    complete = day < now.date() or now.hour * 60 + now.minute >= RTH1 + 5
    orb = {}
    for _, label, key in SYMS:
        bars = session_bars(frames.get(key), day)
        if bars:
            orb[key] = card(label, day, bars, complete)
    if "SPY" not in orb or "QQQ" not in orb:
        return None
    prev = prev or {}
    pday = prev.get("asof") or ""
    if pday > day.isoformat():
        return None
    if pday == day.isoformat():
        old = ((prev.get("orb") or {}).get("SPY") or {}).get("bars")
        if isinstance(old, list) and len(old) > len(orb["SPY"]["bars"]):
            return None
        for k in ("ES", "SPX"):  # keep a same-day card rather than drop it on a partial pull
            if k not in orb and (prev.get("orb") or {}).get(k):
                orb[k] = prev["orb"][k]
    last = orb["SPY"]["bars"][-1][0] + RTH0
    out = {"asof": day.isoformat(), "asof_t": None if complete else f"{last // 60}:{last % 60:02d}",
           "orb": orb, "hourly": {s: hourly(orb[s]) for s in ("SPY", "QQQ")},
           "eq": extend_eq(json.loads(json.dumps(prev.get("eq") or {})), orb, day.isoformat(), complete),
           "bot": prev.get("bot") or {"paused_since": "10-28", "last_session": "10-27"}}
    return out


def main():
    p = inputs_dir() / "orb" / "orb_status.json"
    try:
        prev = json.loads(p.read_text())
    except (OSError, json.JSONDecodeError):
        prev = {}
    new = build(fetch(), prev)
    if new is None:
        print("orb_live: no newer session data; left alone"); return
    if new == prev:
        print("orb_live: unchanged"); return
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(new, default=float))
    print("orb_live:", new["asof"], new["asof_t"] or "final", {k: (v.get("status"), v.get("R")) for k, v in new["orb"].items()})


if __name__ == "__main__":
    main()
