"""Read-only Alpaca market-data pull of SPY 1m bars (4:00-16:00 ET). No trading endpoints used."""
import os, sys, time, json, requests, pandas as pd
from datetime import datetime, timedelta, timezone
# Credentials from env (GitHub Actions secrets or pre-exported local env).
# Accept ALPACA_SECRET_KEY as alias for ALPACA_API_SECRET.
if os.environ.get("ALPACA_SECRET_KEY") and not os.environ.get("ALPACA_API_SECRET"):
    os.environ["ALPACA_API_SECRET"] = os.environ["ALPACA_SECRET_KEY"]
if not os.environ.get("ALPACA_API_KEY") or not (os.environ.get("ALPACA_API_SECRET") or os.environ.get("ALPACA_SECRET_KEY")):
    raise SystemExit("ALPACA_API_KEY and ALPACA_SECRET_KEY (or ALPACA_API_SECRET) required")
H={"APCA-API-KEY-ID":os.environ["ALPACA_API_KEY"],"APCA-API-SECRET-KEY":os.environ.get("ALPACA_API_SECRET") or os.environ.get("ALPACA_SECRET_KEY")}
URL="https://data.alpaca.markets/v2/stocks/bars"
def pull(sym,feed,start,end):
    rows=[];tok=None
    while True:
        p={"symbols":sym,"timeframe":"1Min","start":start,"end":end,"limit":10000,"feed":feed,"adjustment":"split"}
        if tok:p["page_token"]=tok
        r=requests.get(URL,headers=H,params=p,timeout=60)
        if r.status_code==429: time.sleep(3);continue
        if r.status_code!=200: raise RuntimeError(f"{r.status_code} {r.text[:200]}")
        j=r.json(); rows+=j["bars"].get(sym,[]); tok=j.get("next_page_token")
        if not tok:break
    return rows
if __name__=="__main__":
    sym=sys.argv[1] if len(sys.argv)>1 else "SPY"
    end=(datetime.now(timezone.utc)-timedelta(minutes=20)).strftime("%Y-%m-%dT%H:%M:%SZ")
    start=sys.argv[2] if len(sys.argv)>2 else "2016-01-01T00:00:00Z"
    feed="sip"
    try: pull(sym,"sip","2024-01-02T14:30:00Z","2024-01-02T14:35:00Z")
    except Exception as e: print("sip failed:",e); feed="iex"
    rows=pull(sym,feed,start,end)
    df=pd.DataFrame(rows).rename(columns={"t":"ts","o":"open","h":"high","l":"low","c":"close","v":"volume","n":"trades","vw":"vwap"})
    df["ts"]=pd.to_datetime(df.ts,utc=True).dt.tz_convert("America/New_York")
    hm=df.ts.dt.hour*60+df.ts.dt.minute
    df=df[(hm>=240)&(hm<960)].reset_index(drop=True)
    os.makedirs("data",exist_ok=True)
    df.to_parquet(f"data/{sym}_1m.parquet")
    meta={"symbol":sym,"feed":feed,"adjustment":"split","rows":len(df),"first":str(df.ts.min()),"last":str(df.ts.max()),"pulled_at":datetime.now().isoformat()}
    json.dump(meta,open(f"data/{sym}_meta.json","w"),indent=1); print(meta)
