"""Incremental top-up of data/{SYM}_1m.parquet (read-only Alpaca SIP market data, ~20 min delayed). Usage: append_today.py SPY QQQ"""
import sys, json, pandas as pd
from datetime import datetime, timedelta, timezone
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "python"))
from fetch import pull
D = Path(__file__).resolve().parent / "data"
end = (datetime.now(timezone.utc) - timedelta(minutes=16)).strftime("%Y-%m-%dT%H:%M:%SZ")
for sym in sys.argv[1:] or ["SPY", "QQQ"]:
    p = D / f"{sym}_1m.parquet"; old = pd.read_parquet(p)
    start = (old.ts.max() + pd.Timedelta(minutes=1)).tz_convert("UTC").strftime("%Y-%m-%dT%H:%M:%SZ")
    if start >= end: print(sym, "up to date"); continue
    new = pd.DataFrame(pull(sym, "sip", start, end))
    if new.empty: print(sym, "no new bars"); continue
    new = new.rename(columns={"t":"ts","o":"open","h":"high","l":"low","c":"close","v":"volume","n":"trades","vw":"vwap"})
    new["ts"] = pd.to_datetime(new.ts, utc=True).dt.tz_convert("America/New_York")
    hm = new.ts.dt.hour * 60 + new.ts.dt.minute; new = new[(hm >= 240) & (hm < 960)]
    df = pd.concat([old, new[old.columns.intersection(new.columns)]]).drop_duplicates("ts").sort_values("ts").reset_index(drop=True)
    df.to_parquet(p); m = D / f"{sym}_meta.json"; meta = json.load(open(m))
    meta.update(rows=len(df), last=str(df.ts.max()), pulled_at=datetime.now().isoformat()); json.dump(meta, open(m, "w"), indent=1)
    print(sym, "+", len(new), "->", df.ts.max())
