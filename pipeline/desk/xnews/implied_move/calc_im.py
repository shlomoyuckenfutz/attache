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
if not os.environ.get("ALPACA_API_KEY") or not (os.environ.get("ALPACA_API_SECRET") or os.environ.get("ALPACA_SECRET_KEY")):
    raise SystemExit("ALPACA_API_KEY and ALPACA_SECRET_KEY (or ALPACA_API_SECRET) required")
H={"APCA-API-KEY-ID":os.environ["ALPACA_API_KEY"],"APCA-API-SECRET-KEY":os.environ.get("ALPACA_API_SECRET") or os.environ.get("ALPACA_SECRET_KEY")}
D="https://data.free_feed.markets"; UA={"User-Agent":"Mozilla/5.0"}
YSYM={"SPY":"SPY","QQQ":"QQQ","SPX":"^SPX"}; OROOT={"SPY":["SPY"],"QQQ":["QQQ"],"SPX":["SPXW","SPX"]}

def yahoo_chart(sym,rng="10d"):
    r=requests.get(f"https://query1.finance.free_data.com/v8/finance/chart/{sym}",params={"range":rng,"interval":"1d"},headers=UA,timeout=15).json()["chart"]["result"][0]
    q=r["indicators"]["quote"][0]; days=[dt.datetime.fromtimestamp(t,ET).date() for t in r["timestamp"]]
    return r["meta"]["regularMarketPrice"],[(d,o,c) for d,o,c in zip(days,q["open"],q["close"]) if o is not None]

def spot_and_bars(t):
    last,bars=yahoo_chart(YSYM[t])
    if t!="SPX":
        try:
            s=requests.get(f"{D}/v2/stocks/{t}/snapshot",headers=H,params={"feed":"iex"},timeout=15).json()
            last=s["latestTrade"]["p"]
        except Exception: pass
    return float(last),bars

def expiries(now):
    d=now.date(); after=now.hour>=16
    daily=d if not after and d.weekday()<5 else None
    if daily is None:
        daily=d+dt.timedelta(1)
        while daily.weekday()>=5: daily+=dt.timedelta(1)
    fri=d+dt.timedelta((4-d.weekday())%7)
    if d.weekday()>=5 or (d.weekday()==4 and after): fri+=dt.timedelta(7)
    return daily,fri

def alpaca_chain(t,exp,spot):
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
    s=requests.Session(); s.headers.update(UA); s.get("https://fc.free_data.com",timeout=10)
    crumb=s.get("https://query1.finance.free_data.com/v1/test/getcrumb",timeout=10).text
    ts=int(dt.datetime(exp.year,exp.month,exp.day,tzinfo=dt.timezone.utc).timestamp())
    o=s.get(f"https://query2.finance.free_data.com/v7/finance/options/{YSYM[t]}",params={"date":ts,"crumb":crumb},timeout=15).json()["optionChain"]["result"][0]["options"][0]
    rows={}
    for cp,L in (("C",o["calls"]),("P",o["puts"])):
        for x in L:
            if x.get("bid") and x.get("ask"): rows.setdefault(x["strike"],{})[cp]={"mid":(x["bid"]+x["ask"])/2,"bid":x["bid"],"ask":x["ask"],"iv":x.get("impliedVolatility")}
    rows={k:x for k,x in rows.items() if "C" in x and "P" in x}
    return (rows,"fallback") if rows else (None,None)

def straddle(t,exp,spot,now):
    rows,src=None,None
    try: rows,src=alpaca_chain(t,exp,spot)
    except Exception as e: src=f"free_feed error {e}"
    if not rows:
        try: rows,src=yahoo_chain(t,exp,spot)
        except Exception as e: return {"error":f"no chain ({src}; free_data {e})"}
    if not rows: return {"error":f"no two-sided ATM quotes for {exp} ({src})"}
    k=min(rows,key=lambda s:abs(s-spot)); c,p=rows[k]["C"],rows[k]["P"]; st=c["mid"]+p["mid"]
    close=dt.datetime(exp.year,exp.month,exp.day,16,tzinfo=ET); dte=max((close-now).total_seconds()/86400,1/24)
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
        if (now.hour>=16 or now.weekday()>=5) and bars and bars[-1][0]<=now.date():
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
    hist=[h for h in old.get("history",[]) if not (h["session_for"]==out["session_for"] and h["generated_pt"][:10]==out["generated_pt"][:10])]
    hist.append({"generated_pt":out["generated_pt"],"session_for":out["session_for"],"week_expiry":out["week_expiry"],
                 **{t:{k:{x:v.get(x) for x in ("straddle","upper","lower","ref","atm_iv","iv_move")} for k,v in r.items() if isinstance(v,dict)} for t,r in res.items() if "daily" in r}})
    out["history"]=hist[-400:]; json.dump(out,open(OUT,"w"),indent=1); return out

if __name__=="__main__": print(json.dumps(run()["symbols"],indent=1))
