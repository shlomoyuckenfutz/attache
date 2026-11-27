#!/usr/bin/env python3
"""Attaché implied-move calculator (free data only).
Daily  = nearest expiry ATM straddle (call mid + put mid at strike nearest spot); bands = spot ± straddle.
Weekly = this week's Friday expiry ATM straddle; bands anchored on Monday open (also reports prior-Friday-close bands).
Cross-check = spot × ATM IV × sqrt(DTE/365). Also reports 0.85 × straddle (common ~1σ adjustment).
Source: free_feed options snapshots (feed=indicative, free) -> fallback free_data option chains. Read-only.
Writes implied_move.json (latest + history)."""
import os, json, math, datetime as dt, requests
from zoneinfo import ZoneInfo
ET=ZoneInfo("America/New_York"); PT=ZoneInfo("America/Los_Angeles")
HERE=os.path.dirname(os.path.abspath(__file__)); OUT=os.path.join(HERE,"implied_move.json")
# Credentials from env (GitHub Actions secrets or pre-exported local env).
# Accept ALPACA_SECRET_KEY as alias for ALPACA_API_SECRET.
if os.environ.get("ALPACA_SECRET_KEY") and not os.environ.get("ALPACA_API_SECRET"):
    os.environ["ALPACA_API_SECRET"] = os.environ["ALPACA_SECRET_KEY"]
# sweep 2026-11-27: keys are optional; without them (or when the indicative feed has no two-sided quotes) the free
# Yahoo option chains are used, same as free_gex.py.
_KEY=os.environ.get("ALPACA_API_KEY"); _SEC=os.environ.get("ALPACA_API_SECRET") or os.environ.get("ALPACA_SECRET_KEY")
H={"APCA-API-KEY-ID":_KEY,"APCA-API-SECRET-KEY":_SEC} if (_KEY and _SEC) else None
import sys; sys.path.insert(0,os.path.abspath(os.path.join(HERE,"..","..")))
from market_calendar import close_minute
D="https://data.alpaca.markets"; UA={"User-Agent":"Mozilla/5.0"}
YSYM={"SPY":"SPY","QQQ":"QQQ","SPX":"^SPX"}; OROOT={"SPY":["SPY"],"QQQ":["QQQ"],"SPX":["SPXW","SPX"]}

def yahoo_chart(sym,rng="10d"):
    r=requests.get(f"https://query1.finance.yahoo.com/v8/finance/chart/{sym}",params={"range":rng,"interval":"1d"},headers=UA,timeout=15).json()["chart"]["result"][0]
    q=r["indicators"]["quote"][0]; days=[dt.datetime.fromtimestamp(t,ET).date() for t in r["timestamp"]]
    return r["meta"]["regularMarketPrice"],[(d,o,c) for d,o,c in zip(days,q["open"],q["close"]) if o is not None]

def spot_and_bars(t):
    last,bars=yahoo_chart(YSYM[t])
    if t!="SPX" and H:
        try:
            s=requests.get(f"{D}/v2/stocks/{t}/snapshot",headers=H,params={"feed":"iex"},timeout=15).json()
            last=s["latestTrade"]["p"]
        except Exception: pass
    return float(last),bars

def expiries(now):
    d=now.date(); after=now.hour*60+now.minute>=close_minute(d)
    daily=d if not after and d.weekday()<5 else None
    if daily is None:
        daily=d+dt.timedelta(1)
        while daily.weekday()>=5: daily+=dt.timedelta(1)
    fri=d+dt.timedelta((4-d.weekday())%7)
    if d.weekday()==4 and after: fri+=dt.timedelta(7)   # weekends already land on next Friday
    return daily,fri

def alpaca_chain(t,exp,spot):
    if not H: return None,None
    w=max(spot*0.01,2)
    for root in OROOT[t]:
        snaps={};tok=None
        while True:
            p={"feed":"indicative","expiration_date":exp.isoformat(),"strike_price_gte":round(spot-w,2),"strike_price_lte":round(spot+w,2),"limit":1000}
            if tok:p["page_token"]=tok
            r=requests.get(f"{D}/v1beta1/options/snapshots/{root}",headers=H,params=p,timeout=20); r.raise_for_status(); j=r.json()
            snaps.update({k:v for k,v in j.get("snapshots",{}).items() if k.startswith(root+exp.strftime('%y%m%d'))}); tok=j.get("next_page_token")
            if not tok:break
        rows={}
        for sym,v in snaps.items():
            n=len(root)+6; cp=sym[n]; k=int(sym[n+1:])/1000; q=v.get("latestQuote") or {}
            if q.get("bp") and q.get("ap"): rows.setdefault(k,{})[cp]={"mid":(q["bp"]+q["ap"])/2,"bid":q["bp"],"ask":q["ap"],"iv":v.get("impliedVolatility")}
        rows={k:x for k,x in rows.items() if "C" in x and "P" in x}
        if rows: return rows,f"indicative:{root}"
    return None,None

def yahoo_chain(t,exp,spot):
    """Free Yahoo chain for one expiry (yfinance). Mid = (bid+ask)/2; when a side has no quote (Yahoo zeroes them on
    some expiries outside the session) the last trade stands in, so a straddle is still read from real prints."""
    import logging, yfinance as yf
    logging.getLogger("yfinance").setLevel(logging.CRITICAL)
    tk=yf.Ticker(YSYM[t]); e=exp.isoformat()
    if e not in tk.options: return None,None
    ch=tk.option_chain(e); rows={}; last_used=False
    for cp,df in (("C",ch.calls),("P",ch.puts)):
        df=df.fillna({"bid":0,"ask":0,"lastPrice":0,"impliedVolatility":0})
        for x in df.itertuples():
            if t=="SPX" and not str(x.contractSymbol).startswith("SPXW"): continue
            if abs(x.strike-spot)>max(spot*0.02,3): continue
            if x.bid>0 and x.ask>0: mid=(x.bid+x.ask)/2
            elif x.lastPrice>0: mid=float(x.lastPrice); last_used=True
            else: continue
            iv=float(x.impliedVolatility) if x.impliedVolatility>0.01 else None
            rows.setdefault(float(x.strike),{})[cp]={"mid":mid,"bid":float(x.bid),"ask":float(x.ask),"iv":iv}
    rows={k:x for k,x in rows.items() if "C" in x and "P" in x}
    return (rows,"free chain"+(" (last trade)" if last_used else "")) if rows else (None,None)

def straddle(t,exp,spot,now):
    rows,src=None,None
    try: rows,src=alpaca_chain(t,exp,spot)
    except Exception as e: src=f"free_feed error {e}"
    if not rows:
        try: rows,src=yahoo_chain(t,exp,spot)
        except Exception as e: return {"error":f"no chain ({src}; free_data {e})"}
    if not rows: return {"error":f"no two-sided ATM quotes for {exp} ({src})"}
    k=min(rows,key=lambda s:abs(s-spot)); c,p=rows[k]["C"],rows[k]["P"]; st=c["mid"]+p["mid"]
    cm=close_minute(exp); close=dt.datetime(exp.year,exp.month,exp.day,cm//60,cm%60,tzinfo=ET); dte=max((close-now).total_seconds()/86400,1/24)
    ivs=[x for x in (c["iv"],p["iv"]) if x]; iv=sum(ivs)/len(ivs) if ivs else None
    return {"expiry":exp.isoformat(),"strike":k,"call_mid":round(c["mid"],2),"put_mid":round(p["mid"],2),"straddle":round(st,2),
            "straddle_085":round(0.85*st,2),"atm_iv":round(iv,4) if iv else None,"dte_cal":round(dte,3),
            "iv_move":round(spot*iv*math.sqrt(dte/365),2) if iv else None,"source":src}

def run():
    now=dt.datetime.now(ET); dexp,wexp=expiries(now); res={}
    for t in ("SPY","SPX","QQQ"):
        try: spot,bars=spot_and_bars(t)
        except Exception as e: res[t]={"error":f"spot {e}"}; continue
        rk="spot at calc"
        if (now.hour*60+now.minute>=close_minute(now.date()) or now.weekday()>=5) and bars and bars[-1][0]<=now.date():
            spot=bars[-1][2]; rk=f"{bars[-1][0]} regular close"   # after the bell: anchor on the close, like posted levels
        d=straddle(t,dexp,spot,now); w=straddle(t,wexp,spot,now)
        if "straddle" in d: d.update(ref=round(spot,2),ref_kind=rk,upper=round(spot+d["straddle"],2),lower=round(spot-d["straddle"],2),move_pct=round(100*d["straddle"]/spot,3))
        mon=wexp-dt.timedelta(4); mo=[o for (dd,o,c) in bars if dd==mon]; pf=[c for (dd,o,c) in bars if dd<mon]
        if "straddle" in w:
            ref=mo[0] if mo else (pf[-1] if pf else spot); w.update(ref=round(ref,2),ref_kind="Monday open" if mo else "prior Friday close" if pf else "spot",
                upper=round(ref+w["straddle"],2),lower=round(ref-w["straddle"],2),move_pct=round(100*w["straddle"]/ref,3))
            if pf: w.update(prior_fri_close=round(pf[-1],2),upper_from_fri=round(pf[-1]+w["straddle"],2),lower_from_fri=round(pf[-1]-w["straddle"],2))
        res[t]={"spot":round(spot,2),"daily":d,"weekly":w}
    out={"generated_pt":dt.datetime.now(PT).strftime("%Y-%m-%d %H:%M PT"),"session_for":dexp.isoformat(),"week_expiry":wexp.isoformat(),
         "method":"ATM straddle = call mid + put mid at strike nearest spot; bands = ref ± straddle; iv_move = spot*IV*sqrt(DTE/365); straddle_085 = 0.85×straddle (~1σ)","symbols":res}
    old=json.load(open(OUT)) if os.path.exists(OUT) else {}
    if not any("straddle" in (r.get("daily") or {}) for r in res.values()) and any("straddle" in ((r or {}).get("daily") or {}) for r in (old.get("symbols") or {}).values()):
        print("calc_im: no chain this run; keeping the newer snapshot from "+str(old.get("generated_pt"))); return old   # never step back
    hist=[h for h in old.get("history",[]) if not (h["session_for"]==out["session_for"] and h["generated_pt"][:10]==out["generated_pt"][:10])]
    hist.append({"generated_pt":out["generated_pt"],"session_for":out["session_for"],"week_expiry":out["week_expiry"],
                 **{t:{k:{x:v.get(x) for x in ("straddle","upper","lower","ref","atm_iv","iv_move")} for k,v in r.items() if isinstance(v,dict)} for t,r in res.items() if "daily" in r}})
    out["history"]=hist[-400:]; json.dump(out,open(OUT,"w"),indent=1); return out

if __name__=="__main__": print(json.dumps(run()["symbols"],indent=1))
