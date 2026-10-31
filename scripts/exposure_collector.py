#!/usr/bin/env python3
"""Board dealer-exposure collector for Attaché HEAT app.
Fetches CBOE delayed options for the chip board (+ SPX for Trinity),
computes GEX/VEX/DEX/Charm grids (strike × expiry), walls, King, EM, setups,
scanner scores, Alpaca 5m bars for Antaeus. Writes under orb-dash-site/exposure/data/.
FREE sources only. No routines created here — invoke on a schedule yourself.

Usage:
  python3 /workspace/desk/orb-research/scripts/exposure_collector.py
  PUSH=1 python3 ...   # also git commit+push data (site repo)
  SCAN=close|open      # tag scanner snapshot (default: close if after 15:50 ET else open-ish)
"""
from __future__ import annotations
import json, math, os, re, sys, time, urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, date, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

PT, ET = ZoneInfo("America/Los_Angeles"), ZoneInfo("America/New_York")
SITE = Path(os.environ.get("SITE", "/workspace/orb-dash-site"))
OUT = SITE / "exposure" / "data"
URL = "https://cdn.cboe.com/api/global/delayed_quotes/options/{}.json"
RX = re.compile(r"^([A-Z]+)(\d{6})([CP])(\d{8})$")
R, Q = 0.05, 0.012
BAND = float(os.environ.get("BAND", "0.08"))
MAX_EXPS = int(os.environ.get("MAX_EXPS", "16"))
WORKERS = int(os.environ.get("WORKERS", "10"))

# chip -> (cboe_path_symbol, root_filter or None)
BOARD = [
    "SPY","QQQ","SPXW","IWM","NDXP","DIA","SMH","TLT","GLD","SLV","XLE",
    "TQQQ","SOXL","IBIT","NVDA","AAPL","TSLA","MSFT","AMZN","META","GOOGL",
    "AVGO","NFLX","ORCL","AMD","MU","INTC","TSM","ARM","PLTR","COIN","MSTR",
    "HOOD","SOFI","SMCI","CRWD","UBER","SHOP","RBLX","JPM","BAC","WMT","COST",
    "XOM","BA","LLY","GME","RIVN","MARA","BABA",
]
SPECIAL = {
    "SPXW": ("_SPX", "SPXW"),
    "NDXP": ("_NDX", "NDXP"),
    "SPX": ("_SPX", "SPX"),
    "NDX": ("_NDX", "NDX"),
}
# Always compute these for Trinity even if not chips
EXTRA = ["SPX"]

def cboe_key(sym: str):
    if sym in SPECIAL: return SPECIAL[sym]
    return (sym, sym)

def fetch_json(url, headers=None, timeout=30):
    last = None
    for i in range(3):
        try:
            h = {"User-Agent": "Mozilla/5.0 (compatible; AttacheDesk/1.0)"}
            if headers: h.update(headers)
            req = urllib.request.Request(url, headers=h)
            return json.loads(urllib.request.urlopen(req, timeout=timeout).read())
        except Exception as e:
            last = e; time.sleep(1.2 + i)
    raise last

def fetch_chain(sym: str):
    path, root = cboe_key(sym)
    raw = fetch_json(URL.format(path))
    return raw, root

def norm_pdf(x): return math.exp(-0.5*x*x)/math.sqrt(2*math.pi)
def norm_cdf(x): return 0.5*(1+math.erf(x/math.sqrt(2)))

def bs_charm(S,K,T,iv,cp):
    if iv<=0 or T<=1e-8 or S<=0 or K<=0: return 0.0
    sig=iv; sqrtT=math.sqrt(T)
    d1=(math.log(S/K)+(R-Q+0.5*sig*sig)*T)/(sig*sqrtT); d2=d1-sig*sqrtT
    pdf=norm_pdf(d1)
    common=-pdf*(2*(R-Q)*T - d2*sig*sqrtT)/(2*T*sig*sqrtT)
    if cp=="C": return common-(R-Q)*math.exp(-(R-Q)*T)*norm_cdf(d1)
    return common+(R-Q)*math.exp(-(R-Q)*T)*norm_cdf(-d1)

def bs_gamma(S,K,T,iv):
    if iv<=0 or T<=0 or S<=0: return 0.0
    d1=(math.log(S/K)+(R-Q+0.5*iv*iv)*T)/(iv*math.sqrt(T))
    return math.exp(-0.5*d1*d1)/(math.sqrt(2*math.pi)*S*iv*math.sqrt(T))

def year_frac(ex, now):
    close=datetime.combine(ex, datetime.min.time(), ET).replace(hour=16)
    return max((close-now).total_seconds(), 1800)/(365*86400)

def week_end(today):
    return today + timedelta((4-today.weekday())%7)

def third_friday(y,m):
    d=date(y,m,15); return d+timedelta((4-d.weekday())%7)

def next_monthly(d):
    tf=third_friday(d.year,d.month)
    if tf>=d: return tf
    y,m=(d.year+1,1) if d.month==12 else (d.year,d.month+1)
    return third_friday(y,m)

def fmt_money(v):
    a=abs(v); s="-" if v<0 else ""
    for u,k in ((1e9,"B"),(1e6,"M"),(1e3,"K")):
        if a>=u: return f"{s}${a/u:.2f}{k}".replace("$-","-$") if False else (f"-${a/u:.2f}{k}" if v<0 else f"${a/u:.2f}{k}")
    return f"-${a:.0f}" if v<0 else f"${a:.0f}"

def detect_setup(spot, king, call_w, put_w, zero_g, regime, contested, by_k):
    if not king or spot<=0:
        return {"tag":"NO CLEAR SETUP","detail":"None of the eight patterns fits this book right now.","dir":None}
    dist = spot - king; dist_pct = abs(dist)/spot*100
    toward = "DOWN" if dist>0 else "UP"
    # Rug Pull
    if put_w and spot <= put_w*1.003 and regime=="negative" and dist>0:
        return {"tag":"Rug Pull","detail":f"Spot at/under put wall {put_w:g} with negative gamma","dir":"BEAR"}
    # Floor Bounce
    if put_w and put_w*0.997 <= spot <= put_w*1.012 and spot >= put_w*0.999:
        return {"tag":"Floor Bounce","detail":f"Testing put-wall floor {put_w:g}","dir":"BULL"}
    # Gatekeeper
    if call_w and abs(spot-call_w)/spot <= 0.004:
        return {"tag":"Gatekeeper","detail":f"Pinned near call wall {call_w:g}","dir":None}
    # Whipsaw
    if contested and dist_pct < 0.35:
        return {"tag":"Whipsaw","detail":"Contested King hugging spot — two-way risk","dir":None}
    # Beach Ball
    if regime=="negative" and call_w and spot < call_w:
        above = sum(v for k,v in by_k.items() if k>spot and v<0)
        if above < -5e7:
            return {"tag":"Beach Ball","detail":"Held under water by negative gamma overhead","dir":"BULL"}
    # Reverse Rug / Slingshot
    if put_w and put_w < spot <= put_w*1.02 and regime=="positive":
        return {"tag":"Reverse Rug / Slingshot","detail":f"Bounce off put wall {put_w:g}","dir":"BULL"}
    # Rainbow Road — ladder of same-sign nodes between spot and king
    if abs(dist)/spot > 0.004:
        lo,hi = (king,spot) if king<spot else (spot,king)
        nodes = sorted((k,v) for k,v in by_k.items() if lo < k < hi and abs(v)>1e6)
        if len(nodes) >= 3:
            signs = [1 if v>0 else -1 for _,v in nodes]
            if len(set(signs))==1:
                return {"tag":"Rainbow Road","detail":f"Gamma ladder toward King {king:g}","dir":"BEAR" if dist>0 else "BULL"}
    # Trend
    if (not contested) and dist_pct >= 0.25:
        return {"tag":"Trend","detail":f"DRIFT TOWARD KING {king:g} · ~60% hist tag","dir":"BEAR" if dist>0 else "BULL"}
    return {"tag":"NO CLEAR SETUP","detail":"None of the eight patterns fits this book right now.","dir":None}

def king_of(by_k):
    if not by_k: return None
    items=sorted(by_k.items(), key=lambda kv: -abs(kv[1]))
    k,v=items[0]; nxt=items[1] if len(items)>1 else (None,0)
    contested = bool(nxt[0] is not None and abs(nxt[1]) >= 0.9*abs(v))
    share = abs(v)/(sum(abs(x) for x in by_k.values()) or 1)
    return {"k":k,"v":v,"contested":contested,"next_k":nxt[0],"next_v":nxt[1],"share":round(share,4)}

def pull_score(king, spot, em_daily, regime):
    if not king or not spot: return 0,0,0
    # strength = 50%*(1-next/King) + 50%*min(King gamma share/0.25,1)
    ratio = 0 if not king["next_v"] else min(1, abs(king["next_v"])/(abs(king["v"]) or 1))
    strength = 0.5*(1-ratio) + 0.5*min(king.get("share",0)/0.25, 1)
    dist = abs(spot - king["k"])
    em = (em_daily or {}).get("mv") or 0
    if em <= 0:
        fit = 0.5
        mult = None
    else:
        mult = dist/em
        # 1 for 0.5–2× EM, linear fade to 0 at 0.1× and 4×
        if 0.5 <= mult <= 2: fit = 1.0
        elif mult < 0.5: fit = max(0, (mult-0.1)/(0.5-0.1))
        else: fit = max(0, (4-mult)/(4-2))
    pull = 100*(0.55*strength + 0.45*fit)
    if regime=="positive": pull *= 0.85
    return round(pull,1), round(100*strength,1), (round(mult,2) if mult is not None else None)

def compute_symbol(sym: str, now: datetime):
    raw, root = fetch_chain(sym)
    d = raw["data"]; S=float(d["current_price"])
    today = now.astimezone(ET).date(); fri=week_end(today); mon=next_monthly(today)
    prev = float(d.get("prev_day_close") or 0) or None
    chg = float(d.get("price_change") or (S-(prev or S)))
    chg_pct = float(d.get("price_change_percent") or (100*chg/(prev or S) if prev else 0))
    rows=[]
    for o in d.get("options") or []:
        m=RX.match(o.get("option") or "")
        if not m: continue
        if m.group(1) != root: continue
        ex=datetime.strptime(m.group(2),"%y%m%d").date()
        if ex < today: continue
        K=int(m.group(4))/1000.0
        if K < S*(1-BAND) or K > S*(1+BAND): continue
        oi=float(o.get("open_interest") or 0)
        if oi<=0: continue
        g=float(o.get("gamma") or 0); dl=float(o.get("delta") or 0)
        vg=float(o.get("vega") or 0); iv=float(o.get("iv") or 0)
        mid=((o.get("bid") or 0)+(o.get("ask") or 0))/2 or float(o.get("last_trade_price") or 0)
        cp=m.group(3); T=year_frac(ex, now); sign=1.0 if cp=="C" else -1.0
        gex=g*oi*100*S*S*0.01*sign
        vex=vg*oi*100*sign  # vega$ stand-in; feed has no vanna
        dex=dl*oi*100*S
        charm=bs_charm(S,K,T,iv,cp)*oi*100*S*sign
        rows.append(dict(ex=ex,cp=cp,K=K,oi=oi,g=g,iv=iv,mid=mid,gex=gex,vex=vex,dex=dex,charm=charm,vol=float(o.get("volume") or 0)))
    if not rows:
        raise RuntimeError(f"no rows for {sym} root={root}")

    exps=sorted({r["ex"] for r in rows})
    # keep nearest MAX_EXPS
    exps=exps[:MAX_EXPS]
    rows=[r for r in rows if r["ex"] in exps]
    strikes=sorted({r["K"] for r in rows})

    def matrix(metric):
        # strike x exp
        idx_s={k:i for i,k in enumerate(strikes)}; idx_e={e:i for i,e in enumerate(exps)}
        M=[[0.0]*len(exps) for _ in strikes]
        for r in rows:
            M[idx_s[r["K"]]][idx_e[r["ex"]]] += r[metric]
        return [[round(v,2) for v in row] for row in M]

    def agg(sel_ex, metric):
        by={}
        for r in rows:
            if r["ex"] not in sel_ex: continue
            by[r["K"]]=by.get(r["K"],0)+r[metric]
        return by

    all_ex=set(exps); week_ex={e for e in exps if e<=fri}
    next_ex={exps[0]} if exps else set()
    by_gex_all=agg(all_ex,"gex"); by_vex_all=agg(all_ex,"vex")
    by_gex_week=agg(week_ex,"gex"); by_gex_next=agg(next_ex,"gex")

    def pack_ladder(by):
        ks=sorted(by)
        return {"strikes":ks, "vals":[round(by[k],2) for k in ks]}

    # walls from near-spot band
    band={k:v for k,v in by_gex_all.items() if 0.92*S<=k<=1.08*S}
    cg={}; pg={}
    for r in rows:
        if r["ex"] not in all_ex: continue
        if not (0.92*S<=r["K"]<=1.08*S): continue
        if r["cp"]=="C": cg[r["K"]]=cg.get(r["K"],0)+r["gex"]
        else: pg[r["K"]]=pg.get(r["K"],0)+r["gex"]
    call_w = max(cg.items(), key=lambda kv: kv[1])[0] if cg else None
    put_w = min(pg.items(), key=lambda kv: kv[1])[0] if pg else None
    call_v = cg.get(call_w,0) if call_w else 0
    put_v = pg.get(put_w,0) if put_w else 0

    # zero gamma via BS profile
    def prof(x):
        tot=0.0
        for r in rows:
            if r["iv"]<=0: continue
            if not (0.85*S<=r["K"]<=1.15*S): continue
            tot += bs_gamma(x,r["K"],year_frac(r["ex"],now),r["iv"])*r["oi"]*100*x*x*0.01*(1 if r["cp"]=="C" else -1)
        return tot
    grid=[S*(0.94+i*0.003) for i in range(41)]; pv=[prof(x) for x in grid]; flips=[]
    for i in range(40):
        if pv[i]==0 or (pv[i]<0)!=(pv[i+1]<0):
            a,b=grid[i],grid[i+1]; fa=pv[i]
            for _ in range(16):
                mid=(a+b)/2; fm=prof(mid)
                if (fm<0)==(fa<0): a,fa=mid,fm
                else: b=mid
            flips.append((a+b)/2)
    zero_g = round(min(flips, key=lambda x: abs(x-S)), 2) if flips else None
    net_gex=sum(by_gex_all.values()); regime="positive" if (zero_g and S>zero_g and net_gex>0) or (net_gex>0 and not zero_g) else "negative"
    # refine: classic — spot above zero-g & net pos => positive
    if zero_g is not None:
        regime = "positive" if S >= zero_g else "negative"

    king_g=king_of(by_gex_all); king_v=king_of(by_vex_all)
    king_g_w=king_of(by_gex_week); king_g_n=king_of(by_gex_next)

    # EM straddles
    def straddle(ex):
        R=[r for r in rows if r["ex"]==ex]
        ks=sorted({r["K"] for r in R}, key=lambda k: abs(k-S))
        for k in ks[:5]:
            c=[r for r in R if r["K"]==k and r["cp"]=="C"]
            p=[r for r in R if r["K"]==k and r["cp"]=="P"]
            if c and p and c[0]["mid"]>0 and p[0]["mid"]>0:
                mv=(c[0]["mid"]+p[0]["mid"])*0.85
                return {"mv":round(mv,2),"lo":round(S-mv,2),"hi":round(S+mv,2),"exp":ex.isoformat(),"pct":round(100*mv/S,2)}
        return None
    # After RTH close on an expiry day, today's chain is worthless — use next session for Daily,
    # and the upcoming Friday (strictly after today if today is Friday post-close) for Weekly.
    et_now = now.astimezone(ET)
    after_close = (et_now.hour*60+et_now.minute) >= 16*60 or et_now.weekday() >= 5
    future = [e for e in exps if e > today] if after_close else [e for e in exps if e >= today]
    if not future: future = list(exps)
    em_d = straddle(future[0]) if future else None
    fri_target = fri if (not after_close or today < fri) else (fri + timedelta(7))
    week_cands = [e for e in exps if e >= fri_target]
    em_w = straddle(week_cands[0] if week_cands else future[min(1, len(future)-1)]) if future else None
    mon_cands = [e for e in exps if e >= mon]
    em_m = straddle(mon_cands[0] if mon_cands else exps[-1]) if exps else None
    # Annual: prefer expiry ~250-400d out; else furthest; label with year
    ann_cands = [e for e in exps if 200 <= (e - today).days <= 420]
    if not ann_cands:
        ann_cands = [e for e in exps if (e - today).days >= 120]
    em_a = straddle(ann_cands[-1] if ann_cands else (exps[-1] if exps else None)) if exps else None
    if em_a is None and em_m and em_m.get("mv"):
        # rough annualize monthly move
        mv = round(em_m["mv"] * (252/21) ** 0.5, 2)
        em_a = {"mv": mv, "lo": round(S - mv, 2), "hi": round(S + mv, 2),
                "exp": f"{today.year + (1 if today.month>=10 else 0)}", "pct": round(100*mv/S, 2), "approx": True}
    if em_a and not em_a.get("approx"):
        try:
            y = int(em_a["exp"][:4])
            em_a = dict(em_a, label=f"Annual {y}")
        except Exception:
            em_a = dict(em_a, label="Annual")

    setup = detect_setup(S, king_g["k"] if king_g else None, call_w, put_w, zero_g, regime,
                         bool(king_g and king_g["contested"]), by_gex_all)
    pull, strength, em_mult = pull_score(king_g, S, em_d, regime)
    dist_pts = (king_g["k"]-S) if king_g else None
    dist_pct = (100*dist_pts/S) if (dist_pts is not None and S) else None

    def ladder_metric(by_map):
        ks=sorted(by_map)
        return {"strikes":ks,"gex":[round(by_map.get(k,0),2) for k in ks]}

    # multi-metric ladders
    def full_ladder(sel):
        out={"strikes":[],"gex":[],"vex":[],"dex":[],"charm":[]}
        bg=agg(sel,"gex"); bv=agg(sel,"vex"); bd=agg(sel,"dex"); bc=agg(sel,"charm")
        ks=sorted(set(bg)|set(bv)|set(bd)|set(bc))
        out["strikes"]=ks
        out["gex"]=[round(bg.get(k,0),2) for k in ks]
        out["vex"]=[round(bv.get(k,0),2) for k in ks]
        out["dex"]=[round(bd.get(k,0),2) for k in ks]
        out["charm"]=[round(bc.get(k,0),2) for k in ks]
        return out

    pack = {
        "sym": sym, "root": root,
        "spot": round(S,4), "prev_close": round(prev,4) if prev else None,
        "chg": round(chg,4), "chg_pct": round(chg_pct,4),
        "asof_pt": now.astimezone(PT).strftime("%Y-%m-%d %H:%M PT"),
        "src_ts_utc": raw.get("timestamp"),
        "market": "closed",  # filled by caller
        "net": {
            "gex": round(net_gex,2),
            "vex": round(sum(by_vex_all.values()),2),
            "dex": round(sum(agg(all_ex,"dex").values()),2),
            "charm": round(sum(agg(all_ex,"charm").values()),2),
        },
        "king": {"gex": king_g, "vex": king_v, "week_gex": king_g_w, "next_gex": king_g_n},
        "walls": {"call": call_w, "call_v": round(call_v,2), "put": put_w, "put_v": round(put_v,2), "zero_g": zero_g},
        "regime": regime,
        "em": {"daily": em_d, "weekly": em_w, "monthly": em_m, "annual": em_a},
        "setup": setup,
        "scanner": {
            "pull": pull, "strength": strength, "em_mult": em_mult,
            "dist_pts": round(dist_pts,2) if dist_pts is not None else None,
            "dist_pct": round(dist_pct,3) if dist_pct is not None else None,
        },
        "grid": {
            "strikes": strikes,
            "exps": [e.isoformat() for e in exps],
            "gex": matrix("gex"), "vex": matrix("vex"), "dex": matrix("dex"), "charm": matrix("charm"),
        },
        "ladder": {
            "all": full_ladder(all_ex),
            "week": full_ladder(week_ex),
            "next": full_ladder(next_ex),
        },
        "history": [],  # filled from prior board if present
    }
    return pack

def market_state(now):
    e=now.astimezone(ET); d=e.weekday(); t=e.hour*60+e.minute
    if d>=5: return "closed"
    if 570<=t<960: return "open"
    if 240<=t<570: return "pre"
    if 960<=t<1200: return "ah"
    return "closed"

def fetch_bars(sym, key, sec, timeframe="5Min", limit=100):
    # Alpaca doesn't have index options underlyings as stocks the same way; skip SPXW/NDXP -> use SPY/QQQ? use underlying ETF
    map_sym = {"SPXW":"SPY","NDXP":"QQQ","SPX":"SPY","NDX":"QQQ"}.get(sym, sym)
    headers={"APCA-API-KEY-ID":key,"APCA-API-SECRET-KEY":sec}
    if timeframe.endswith("Day") or timeframe=="1Day":
        start=(datetime.now(timezone.utc)-timedelta(days=160)).strftime("%Y-%m-%d")
        url=(f"https://data.alpaca.markets/v2/stocks/{map_sym}/bars?timeframe={timeframe}"
             f"&start={start}&limit={max(limit,200)}&adjustment=raw&feed=iex")
        try:
            j=fetch_json(url, headers=headers, timeout=20)
            bars=j.get("bars") or []
            return [{"t":b["t"],"o":b["o"],"h":b["h"],"l":b["l"],"c":b["c"],"v":b["v"]} for b in bars][-limit:]
        except Exception as e:
            return {"error": str(e)[:120]}
    # 5m: paginate so we keep the NEWEST session bars (Alpaca returns ascending from start)
    start=(datetime.now(timezone.utc)-timedelta(days=3)).strftime("%Y-%m-%dT00:00:00Z")
    out=[]; page_token=None
    try:
        for _ in range(8):
            url=(f"https://data.alpaca.markets/v2/stocks/{map_sym}/bars?timeframe={timeframe}"
                 f"&start={start}&limit=10000&adjustment=raw&feed=iex")
            if page_token: url += f"&page_token={page_token}"
            j=fetch_json(url, headers=headers, timeout=25)
            bars=j.get("bars") or []
            out.extend({"t":b["t"],"o":b["o"],"h":b["h"],"l":b["l"],"c":b["c"],"v":b["v"]} for b in bars)
            page_token=j.get("next_page_token")
            if not page_token or not bars: break
        return out[-max(limit, 200):] if out else []
    except Exception as e:
        return {"error": str(e)[:120]}

def sma(vals, n):
    if len(vals) < n: return None
    return round(sum(vals[-n:]) / n, 4)

def ema(vals, n):
    if not vals: return None
    if len(vals) < n:
        return round(sum(vals)/len(vals), 4)
    k = 2 / (n + 1)
    e = sum(vals[:n]) / n
    for c in vals[n:]:
        e = c * k + e * (1 - k)
    return round(e, 4)

def mas_from_bars(bars5, bars_d):
    c5 = [b["c"] for b in (bars5 or [])]
    cd = [b["c"] for b in (bars_d or [])]
    return {
        "sma5_d": sma(cd, 5),
        "ema21_d": ema(cd, 21),
        "sma55_d": sma(cd, 55),
        "sma34_5m": sma(c5, 34),
        "n_daily": len(cd),
        "n_5m": len(c5),
    }

def load_env_alpaca():
    for p in Path("/home/box/sand-data/agents").glob("*/secrets/alpaca-paper.env"):
        env={}
        for line in p.read_text().splitlines():
            if "=" in line and not line.strip().startswith("#"):
                k,v=line.split("=",1); env[k.strip()]=v.strip().strip('"')
        if "ALPACA_API_KEY" in env: return env
    return {}

def main():
    now=datetime.now(timezone.utc)
    mkt=market_state(now)
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT/"t").mkdir(exist_ok=True); (OUT/"bars").mkdir(exist_ok=True)

    # merge prior history
    prior_hist={}
    try:
        prev=json.loads((OUT/"board.json").read_text())
        for s,h in (prev.get("histories") or {}).items():
            prior_hist[s]=h
    except Exception:
        pass

    syms=list(dict.fromkeys(BOARD+EXTRA))
    results={}; errors={}
    with ThreadPoolExecutor(max_workers=WORKERS) as pool:
        futs={pool.submit(compute_symbol, s, now): s for s in syms}
        for fut in as_completed(futs):
            s=futs[fut]
            try:
                pack=fut.result(); pack["market"]=mkt
                # append history point
                hist=list(prior_hist.get(s) or [])
                # top exposure nodes for Antaeus bubble reconstruction / replay
                lad = (pack.get("ladder") or {}).get("all") or {}
                strikes = lad.get("strikes") or []
                gexs = lad.get("gex") or []
                vexs = lad.get("vex") or []
                nodes = sorted(
                    [{"k": k, "gex": g, "vex": v} for k, g, v in zip(strikes, gexs, vexs)],
                    key=lambda n: -abs(n["gex"]),
                )[:36]
                hist.append({
                    "t": now.astimezone(PT).isoformat(timespec="seconds"),
                    "spot": pack["spot"],
                    "call": pack["walls"]["call"], "put": pack["walls"]["put"],
                    "zero_g": pack["walls"]["zero_g"],
                    "king": (pack["king"]["gex"] or {}).get("k"),
                    "net_gex": pack["net"]["gex"],
                    "net_vex": pack["net"]["vex"],
                    "nodes": [{"k": n["k"], "gex": round(n["gex"], 2), "vex": round(n["vex"], 2)} for n in nodes],
                })
                pack["history"]=hist[-80:]
                prior_hist[s]=pack["history"]
                results[s]=pack
                print("ok", s, "spot", pack["spot"], "king", (pack["king"]["gex"] or {}).get("k"), "pull", pack["scanner"]["pull"])
            except Exception as e:
                errors[s]=str(e)[:200]; print("ERR", s, e, file=sys.stderr)

    # bars for board (parallel) — 5m + daily
    env=load_env_alpaca(); bars_ok=0
    bars5_map={}; barsd_map={}
    if env:
        key,sec=env["ALPACA_API_KEY"], env["ALPACA_API_SECRET"]
        with ThreadPoolExecutor(max_workers=8) as pool:
            futs5={pool.submit(fetch_bars, s, key, sec, "5Min", 300): s for s in BOARD}
            futsd={pool.submit(fetch_bars, s, key, sec, "1Day", 80): s for s in BOARD}
            for fut in as_completed(futs5):
                s=futs5[fut]; b=fut.result(); bars5_map[s]=b
            for fut in as_completed(futsd):
                s=futsd[fut]; b=fut.result(); barsd_map[s]=b
        for s in BOARD:
            b5=bars5_map.get(s); bd=barsd_map.get(s)
            mas = mas_from_bars(b5 if isinstance(b5,list) else [], bd if isinstance(bd,list) else [])
            (OUT/"bars"/f"{s}.json").write_text(json.dumps({
                "sym":s,
                "bars": b5 if isinstance(b5,list) else [],
                "daily": bd if isinstance(bd,list) else [],
                "mas": mas,
                "error": None if isinstance(b5,list) else b5
            }, separators=(",",":")))
            if isinstance(b5,list) and b5: bars_ok+=1

    # session baselines for Δ-since-open / %-badges (earliest stored grid of the ET day)
    base_dir = OUT/"baselines"; base_dir.mkdir(exist_ok=True)
    day = now.astimezone(ET).date().isoformat()
    for s,pack in results.items():
        bp = base_dir/f"{s}.json"
        base=None
        try:
            prevb=json.loads(bp.read_text())
            if prevb.get("day")==day: base=prevb
        except Exception:
            prevb=None
        if base is None:
            # first snapshot of session → freeze current grid as baseline
            g=pack.get("grid") or {}
            base={
                "day": day,
                "label": f"baseline {now.astimezone(PT).strftime('%Y-%m-%d %H:%M PT')} (earliest stored)",
                "asof_pt": pack.get("asof_pt"),
                "spot": pack.get("spot"),
                "grid": {
                    "strikes": g.get("strikes"),
                    "exps": g.get("exps"),
                    "gex": g.get("gex"), "vex": g.get("vex"),
                    "dex": g.get("dex"), "charm": g.get("charm"),
                },
            }
            bp.write_text(json.dumps(base, separators=(",",":")))
        pack["baseline"]= {
            "day": base["day"], "label": base["label"], "asof_pt": base.get("asof_pt"),
            "spot": base.get("spot"),
            # keep full grid for delta math
            "grid": base.get("grid"),
        }
        # attach MAs if we have bars for this board symbol
        if s in bars5_map or s in BOARD:
            bfile = OUT/"bars"/f"{s}.json"
            try:
                bj=json.loads(bfile.read_text()); pack["mas"]=bj.get("mas")
            except Exception:
                pass

    # write per-ticker
    for s,pack in results.items():
        (OUT/"t"/f"{s}.json").write_text(json.dumps(pack, separators=(",",":")))

    # Trinity
    def toward(sym):
        p=results.get(sym) or results.get({"SPX":"SPX"}.get(sym,sym))
        if not p or not p["king"]["gex"]: return None
        k=p["king"]["gex"]["k"]; spot=p["spot"]
        return "BEAR" if spot>k else "BULL"
    # Use SPX (index), SPY, QQQ
    dirs={s: toward(s) for s in ("SPX","SPY","QQQ")}
    votes=[d for d in dirs.values() if d]
    if votes:
        bear=votes.count("BEAR"); bull=votes.count("BULL")
        agree=max(bear,bull); side="BEARISH" if bear>=bull else "BULLISH"
        trinity={"agree":agree,"total":3,"side":f"{side} TOWARD KING","dirs":dirs}
    else:
        trinity={"agree":0,"total":3,"side":"N/A","dirs":dirs}

    # Scanner cards for board chips only
    et=now.astimezone(ET)
    scan_slot = os.environ.get("SCAN") or ("close" if (et.hour*60+et.minute)>=950 else "open")
    cards=[]
    for s in BOARD:
        p=results.get(s)
        if not p: continue
        kg=p["king"]["gex"] or {}
        cards.append({
            "sym": s, "spot": p["spot"], "chg_pct": p["chg_pct"],
            "pull": p["scanner"]["pull"], "strength": p["scanner"]["strength"],
            "king": kg.get("k"), "king_v": kg.get("v"), "contested": kg.get("contested"),
            "dist_pct": p["scanner"]["dist_pct"], "dist_pts": p["scanner"]["dist_pts"],
            "em_mult": p["scanner"]["em_mult"], "regime": p["regime"],
            "setup": p["setup"]["tag"],
            "king_moved": None,
        })
    cards.sort(key=lambda c: -c["pull"])
    for i,c in enumerate(cards,1): c["rank"]=i

    # merge scanner open/close store
    scan_path=OUT/"scanner.json"
    try: scan_store=json.loads(scan_path.read_text())
    except Exception: scan_store={"open":None,"close":None}
    # king_moved vs previous same slot
    prev_slot=scan_store.get(scan_slot) or {}
    prev_kings={c["sym"]:c.get("king") for c in (prev_slot.get("cards") or [])}
    for c in cards:
        pk=prev_kings.get(c["sym"])
        if pk is None or c["king"] is None: c["king_moved"]=None
        elif pk==c["king"]: c["king_moved"]=0
        else: c["king_moved"]=1 if c["king"]>pk else -1
    scan_store[scan_slot]={"asof_pt": now.astimezone(PT).strftime("%Y-%m-%d %H:%M PT"),
                          "slot": scan_slot, "n": len(cards), "cards": cards}
    scan_path.write_text(json.dumps(scan_store, separators=(",",":")))

    # Recap: append today's session summary for board
    recap_path=OUT/"recap.json"
    try: recap=json.loads(recap_path.read_text())
    except Exception: recap={"sessions":[]}
    sess={
        "date": now.astimezone(ET).date().isoformat(),
        "asof_pt": now.astimezone(PT).strftime("%Y-%m-%d %H:%M PT"),
        "tickers": {}
    }
    for s in BOARD:
        p=results.get(s)
        if not p: continue
        sess["tickers"][s]={
            "spot": p["spot"], "chg_pct": p["chg_pct"],
            "gex_king": (p["king"]["gex"] or {}).get("k"),
            "vex_king": (p["king"]["vex"] or {}).get("k"),
            "call_wall": p["walls"]["call"], "put_wall": p["walls"]["put"],
            "zero_g": p["walls"]["zero_g"],
            "regime": p["regime"], "setup": p["setup"],
            "em": p["em"], "net_gex": p["net"]["gex"],
            "start": None, "end": {
                "gex_king": (p["king"]["gex"] or {}).get("k"),
                "vex_king": (p["king"]["vex"] or {}).get("k"),
                "call_wall": p["walls"]["call"], "put_wall": p["walls"]["put"],
                "zero_g": p["walls"]["zero_g"],
            },
            "moves": {"gex_king":0,"vex_king":0,"call_wall":0,"put_wall":0,"zero_g":0},
        }
    # upsert by date
    sessions=[x for x in recap.get("sessions") or [] if x.get("date")!=sess["date"]]
    # if prior same day exists, compute moves from its start/end
    prior_same=next((x for x in (recap.get("sessions") or []) if x.get("date")==sess["date"]), None)
    if prior_same:
        for s,t in sess["tickers"].items():
            old=prior_same.get("tickers",{}).get(s) or {}
            start=old.get("start") or old.get("end") or {}
            t["start"]=start
            end=t["end"]
            for field in ("gex_king","vex_king","call_wall","put_wall","zero_g"):
                a,b=start.get(field), end.get(field)
                t["moves"][field]=0 if a is None or b is None or a==b else 1
    else:
        for t in sess["tickers"].values():
            t["start"]=t["end"]
    sessions.append(sess)
    sessions=sessions[-10:]
    recap={"sessions":sessions,"updated_pt": now.astimezone(PT).strftime("%Y-%m-%d %H:%M PT")}
    recap_path.write_text(json.dumps(recap, separators=(",",":")))

    board={
        "meta": {
            "source":"CBOE delayed options", "delay":"~15-min delayed",
            "updated_pt": now.astimezone(PT).strftime("%Y-%m-%d %H:%M PT"),
            "market": mkt, "n_ok": len(results), "n_err": len(errors),
            "note":"GEX=γ·OI·100·S²·0.01 (C+,P−); VEX≈ν·OI·100; DEX=Δ·OI·100·S; Charm≈BS ∂Δ/∂t·OI·100·S. SPXW/NDXP=weekly roots on _SPX/_NDX.",
        },
        "board": BOARD,
        "trinity": trinity,
        "errors": errors,
        "histories": prior_hist,
        "spots": {s: results[s]["spot"] for s in results},
        "summaries": {
            s: {
                "spot": results[s]["spot"], "chg_pct": results[s]["chg_pct"],
                "king": (results[s]["king"]["gex"] or {}).get("k"),
                "contested": (results[s]["king"]["gex"] or {}).get("contested"),
                "regime": results[s]["regime"], "setup": results[s]["setup"]["tag"],
                "pull": results[s]["scanner"]["pull"],
                "net_gex": results[s]["net"]["gex"], "net_vex": results[s]["net"]["vex"],
                "call": results[s]["walls"]["call"], "put": results[s]["walls"]["put"],
                "zero_g": results[s]["walls"]["zero_g"],
            } for s in results if s in BOARD or s in EXTRA
        },
        "scan_slot": scan_slot,
        "bars_ok": bars_ok,
    }
    (OUT/"board.json").write_text(json.dumps(board, separators=(",",":")))
    print("BOARD", board["meta"]["updated_pt"], "ok", len(results), "err", len(errors), "bars", bars_ok, "trinity", trinity)

    if os.environ.get("PUSH") == "1":
        import subprocess
        subprocess.check_call(["git","pull","--rebase"], cwd=str(SITE))
        subprocess.check_call(["git","add","exposure/data"], cwd=str(SITE))
        subprocess.check_call([
            "git","-c","user.name=shlomoyuckenfutz","-c","user.email=shlomoyuckenfutz@users.noreply.github.com",
            "commit","-m", f"exposure data {now.astimezone(PT).strftime('%Y-%m-%d %H:%M PT')}"
        ], cwd=str(SITE))
        subprocess.check_call(["git","push"], cwd=str(SITE))
        print("pushed")
    return 0 if results else 1

if __name__ == "__main__":
    sys.exit(main())
