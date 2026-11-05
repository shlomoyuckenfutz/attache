#!/usr/bin/env python3
"""Maintain a rolling ~12-day SPY/QQQ 1m bar cache for Actions (no multi-year parquet in repo).
Uses free_feed IEX (free) with SIP fallback. Writes equity_orb15/data/{SYM}_1m.parquet."""
import os, sys, json
from datetime import datetime, timedelta, timezone
from pathlib import Path
import pandas as pd
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "python"))
from fetch import pull

D = Path(__file__).resolve().parent / "data"
D.mkdir(parents=True, exist_ok=True)
KEEP_DAYS = 12

def feed_pick():
    try:
        pull("SPY", "sip", "2024-01-02T14:30:00Z", "2024-01-02T14:35:00Z")
        return "sip"
    except Exception:
        return "iex"

def refresh(sym, feed):
    end = datetime.now(timezone.utc) - timedelta(minutes=16)
    start = end - timedelta(days=KEEP_DAYS)
    p = D / f"{sym}_1m.parquet"
    # If we already have recent data, only top up
    if p.exists():
        old = pd.read_parquet(p)
        if len(old) and (end - old.ts.max().to_pydatetime().astimezone(timezone.utc)).total_seconds() < 90:
            print(sym, "up to date", old.ts.max()); return
        # drop older than keep window then top up from last bar
        cutoff = (end - timedelta(days=KEEP_DAYS)).astimezone(timezone.utc)
        old = old[old.ts >= cutoff.tz_convert("America/New_York") if hasattr(cutoff, 'tz_convert') else pd.Timestamp(cutoff).tz_convert("America/New_York")]
        start_s = (old.ts.max() + pd.Timedelta(minutes=1)).tz_convert("UTC").strftime("%Y-%m-%dT%H:%M:%SZ") if len(old) else start.strftime("%Y-%m-%dT%H:%M:%SZ")
        base = old
    else:
        start_s = start.strftime("%Y-%m-%dT%H:%M:%SZ")
        base = pd.DataFrame()
    end_s = end.strftime("%Y-%m-%dT%H:%M:%SZ")
    if start_s >= end_s:
        print(sym, "up to date"); return
    rows = pull(sym, feed, start_s, end_s)
    if not rows:
        print(sym, "no new bars"); 
        if len(base): base.to_parquet(p)
        return
    new = pd.DataFrame(rows).rename(columns={"t":"ts","o":"open","h":"high","l":"low","c":"close","v":"volume","n":"trades","vw":"vwap"})
    new["ts"] = pd.to_datetime(new.ts, utc=True).dt.tz_convert("America/New_York")
    hm = new.ts.dt.hour * 60 + new.ts.dt.minute
    new = new[(hm >= 240) & (hm < 960)]
    cols = ["ts","open","high","low","close","volume","trades","vwap"]
    new = new[[c for c in cols if c in new.columns]]
    df = pd.concat([base, new], ignore_index=True) if len(base) else new
    df = df.drop_duplicates("ts").sort_values("ts").reset_index(drop=True)
    # trim
    cut = pd.Timestamp(end - timedelta(days=KEEP_DAYS)).tz_convert("America/New_York")
    df = df[df.ts >= cut].reset_index(drop=True)
    df.to_parquet(p)
    meta = {"symbol": sym, "feed": feed, "rows": len(df), "first": str(df.ts.min()), "last": str(df.ts.max()),
            "pulled_at": datetime.now().isoformat(), "rolling_days": KEEP_DAYS}
    (D / f"{sym}_meta.json").write_text(json.dumps(meta, indent=1))
    print(sym, "rows", len(df), "->", df.ts.max())

if __name__ == "__main__":
    feed = feed_pick(); print("feed", feed)
    for sym in (sys.argv[1:] or ["SPY", "QQQ"]):
        try: refresh(sym, feed)
        except Exception as e: print(sym, "FAILED", e); raise
