#!/usr/bin/env python3
"""OVERNIGHT board fetch (paper/research only). Free delayed data via the desk's existing yfinance feed.
Writes es_levels/overnight.json. Source names must never reach the public page."""
import json, warnings, math
from pathlib import Path
from datetime import datetime, timedelta
import pandas as pd, yfinance as yf
warnings.filterwarnings("ignore")
HERE = Path(__file__).resolve().parent; ET = "America/New_York"
# (label, code, symbol or None, status)  status: LIVE | PROXY:<note> | NA
BOARD = [
 ("INDICES", [("S&P 500","ES","ES=F","LIVE"),("Nasdaq 100","NQ","NQ=F","LIVE"),("DJIA","YM","YM=F","LIVE"),("Russell 2000","RTY","RTY=F","LIVE"),
   ("Nikkei 225","NIY","NIY=F","LIVE"),("Euro Stoxx 50","SX5E","^STOXX50E","PROXY:cash index"),("DAX","DAX","^GDAXI","PROXY:cash index"),("VIX","VIX","^VIX","PROXY:spot index")]),
 ("RATES", [("30-Day Fed Funds","ZQ","ZQ=F","LIVE"),("3-Month SOFR","SR3","SR3=F","LIVE"),("2Y Note","ZT","ZT=F","LIVE"),("5Y Note","ZF","ZF=F","LIVE"),
   ("10Y Note","ZN","ZN=F","LIVE"),("Ultra 10Y","TN","TN=F","LIVE"),("30Y Bond","ZB","ZB=F","LIVE"),("Ultra Bond","UB","UB=F","LIVE")]),
 ("ENERGY", [("Crude WTI","CL","CL=F","LIVE"),("Brent","BZ","BZ=F","LIVE"),("Natural Gas","NG","NG=F","LIVE"),("Gasoline RBOB","RB","RB=F","LIVE"),
   ("Gasoil","GO",None,"NA"),("Heating Oil","HO","HO=F","LIVE"),("Coal Newcastle","NCF",None,"NA"),("Uranium","URA","URA","PROXY:uranium ETF")]),
 ("METALS", [("Gold","GC","GC=F","LIVE"),("Silver","SI","SI=F","LIVE"),("Platinum","PL","PL=F","LIVE"),("Palladium","PA","PA=F","LIVE"),
   ("Copper","HG","HG=F","LIVE"),("Aluminum","ALI","ALI=F","LIVE"),("Iron Ore","TIO","TIO=F","LIVE"),("Steel HRC","HRC","HRC=F","LIVE")]),
 ("GRAINS", [("Soybeans","ZS","ZS=F","LIVE"),("Soybean Meal","ZM","ZM=F","LIVE"),("Soybean Oil","ZL","ZL=F","LIVE"),("Corn","ZC","ZC=F","LIVE"),
   ("Wheat","ZW","ZW=F","LIVE"),("Rough Rice","ZR","ZR=F","LIVE"),("Canola","RS",None,"NA"),("Oats","ZO","ZO=F","LIVE")]),
 ("SOFTS & MEATS", [("Coffee","KC","KC=F","LIVE"),("Cocoa","CC","CC=F","LIVE"),("Sugar","SB","SB=F","LIVE"),("Cotton","CT","CT=F","LIVE"),
   ("Lumber","LBR","LBR=F","LIVE"),("Live Cattle","LE","LE=F","LIVE"),("Feeder Cattle","GF","GF=F","LIVE"),("Lean Hogs","HE","HE=F","LIVE")]),
 ("CURRENCIES", [("USD Index","DX","DX-Y.NYB","PROXY:spot index"),("EUR","6E","6E=F","LIVE"),("JPY","6J","6J=F","LIVE"),("GBP","6B","6B=F","LIVE"),
   ("CAD","6C","6C=F","LIVE"),("CHF","6S","6S=F","LIVE"),("AUD","6A","6A=F","LIVE"),("Bitcoin","BTC","BTC=F","LIVE")]),
]
# NIGHT WATCH panel: (name, code, kind, symbol, status)  kind: yf | ust:<col> | de10
NW = [("KOSPI index","KOSPI","yf","^KS11","LIVE"),("Nikkei 225","N225","yf","^N225","LIVE"),("USD/JPY spot","USDJPY","yf","JPY=X","LIVE"),
 ("US 30Y yield","US30Y","yf","^TYX","LIVE"),("US 20Y yield","US20Y","ust:20 Yr",None,"LIVE"),("US 10Y yield","US10Y","ust:10 Yr",None,"LIVE"),
 ("WTI front month","CL1!","yf","CL=F","LIVE"),("Brent","BRENT","yf","BZ=F","LIVE"),("CBOE 10Y yield index","TNX","yf","^TNX","LIVE"),
 ("US Dollar Index","DXY","yf","DX-Y.NYB","LIVE"),("2-Year Note futures","ZT","yf","ZT=F","LIVE"),("10-Year Note futures","ZN","yf","ZN=F","LIVE"),
 ("Euro-Bund (German 10Y yield)","BUND","de10",None,"PROXY:German 10Y govt yield, daily"),("VIX short-term futures ETN","VXX","yf","VXX","LIVE"),("VIX","VIX","yf","^VIX","LIVE")]
def daily_q(vals, asof):  # vals: list of (date, value) ascending
    (d1, l), (d0, pc) = vals[-1], vals[-2]
    return dict(last=num(l), prev=num(pc), chg=num(l-pc), pct=num((l/pc-1)*100 if pc else None), hi=None, lo=None, flag="", asof=asof, stale=False)
_UST = {}
def ust_q(col):
    import io, urllib.request
    y = datetime.now().year
    if y not in _UST:  # fetch the curve once per run; retry so a timeout can't silently fall back to last year's file
        rows = []
        for yy in (y-1, y):
            u = f"https://home.treasury.gov/resource-center/data-chart-center/interest-rates/daily-treasury-rates.csv/{yy}/all?type=daily_treasury_yield_curve&field_tdr_date_value={yy}&page&_format=csv"
            for _ in range(3):
                try: rows.append(pd.read_csv(io.BytesIO(urllib.request.urlopen(urllib.request.Request(u, headers={"User-Agent": "Mozilla/5.0"}), timeout=40).read()))); break
                except Exception: pass
        _UST[y] = pd.concat(rows)
    df = _UST[y].copy(); df["Date"] = pd.to_datetime(df["Date"]); df = df.dropna(subset=[col]).sort_values("Date")
    v = list(zip(df.Date, df[col].astype(float)))
    q = daily_q(v, v[-1][0].strftime("%m/%d") + " D")
    if (datetime.now() - v[-1][0].to_pydatetime()).days > 5: q["stale"] = True
    return q
def de10_q():
    import urllib.request
    u = "https://api.statistiken.bundesbank.de/rest/data/BBSIS/D.I.ZAR.ZI.EUR.S1311.B.A604.R10XX.R.A.A._Z._Z.A?format=csv&lastNObservations=15"
    t = urllib.request.urlopen(u, timeout=20).read().decode("utf-8", "replace"); v = []
    for ln in t.splitlines():
        a = ln.split(";")
        if len(a) >= 2 and len(a[0]) == 10 and a[0][4] == "-" and a[1] not in (".", ""):
            try: v.append((a[0], float(a[1].replace(",", "."))))
            except ValueError: pass
    return daily_q(v, v[-1][0][5:].replace("-", "/") + " D")
def fsess(ts):  # Globex session start (18:00 ET) containing ts
    s = ts.normalize() + timedelta(hours=18)
    return s if ts >= s else s - timedelta(days=1)
def num(v): return None if v is None or (isinstance(v,float) and math.isnan(v)) else round(float(v), 6)
def one(sym, df):
    df = df.dropna(subset=["Close"])
    if not len(df): return None
    last_t = df.index[-1]; fut = sym.endswith("=F")
    if fut:
        st = fsess(last_t); cur = df[df.index >= st]; prev = df[df.index < st]
    else:
        d = last_t.normalize(); cur = df[df.index >= d]; prev = df[df.index < d]
    if not len(prev): return None
    last = float(cur.Close.iloc[-1]); pc = float(prev.Close.iloc[-1]); hi = float(cur.High.max()); lo = float(cur.Low.min())
    hi = max(hi, last); lo = min(lo, last); rng = hi - lo
    flag = "HI" if rng > 0 and hi - last <= 0.03*rng else "LO" if rng > 0 and last - lo <= 0.03*rng else ""
    stale = (pd.Timestamp.now(tz=ET) - last_t) > timedelta(days=4)
    return dict(last=num(last), prev=num(pc), chg=num(last-pc), pct=num((last/pc-1)*100 if pc else None), hi=num(hi), lo=num(lo),
                flag=flag, asof=last_t.strftime("%m/%d %H:%M"), stale=bool(stale))
def strip(sym, df):
    df = df.dropna(subset=["Close"]); last_t = df.index[-1]; st = fsess(last_t)
    on = df[df.index >= st]
    pd_ = df[df.index < st]; rd = pd_.index[-1].normalize() if len(pd_) else None
    rth = pd_[(pd_.index >= rd + timedelta(hours=9, minutes=30)) & (pd_.index < rd + timedelta(hours=16))] if rd is not None else pd_.iloc[0:0]
    asia = on[on.index < st + timedelta(hours=9)]                                   # 18:00-03:00 ET
    lon = on[(on.index >= st + timedelta(hours=9)) & (on.index < st + timedelta(hours=15, minutes=30))]  # 03:00-09:30 ET
    hl = lambda x: (num(x.High.max()), num(x.Low.min())) if len(x) else (None, None)
    gh, gl = hl(on if len(on) else on); rh, rl = hl(rth); ah, al = hl(asia); lh, ll = hl(lon)
    return dict(last=num(df.Close.iloc[-1]), asof=last_t.strftime("%m/%d %H:%M"), on_hi=gh, on_lo=gl, rth_hi=rh, rth_lo=rl,
                rth_date=rd.strftime("%m/%d") if rd is not None else None, asia_hi=ah, asia_lo=al, lon_hi=lh, lon_lo=ll,
                lon_open=bool(len(lon)), sess_start=st.strftime("%m/%d %H:%M"))
def main():
    syms = sorted({s for _, r in BOARD for *_, s, _st in r if s} | {r[3] for r in NW if r[3]})
    raw = yf.download(syms, period="5d", interval="5m", prepost=True, progress=False, group_by="ticker", threads=True, auto_adjust=False)
    out = {"generated_et": pd.Timestamp.now(tz=ET).strftime("%Y-%m-%d %H:%M ET"), "groups": [], "strip": {}}
    for g, rows in BOARD:
        R = []
        for name, code, sym, st in rows:
            q = None
            if sym:
                try: df = raw[sym].copy(); df.index = df.index.tz_convert(ET); q = one(sym, df)
                except Exception: q = None
            if sym and q is None:  # intraday unavailable -> daily bars (last vs prior settle; day high/low)
                try:
                    d = yf.Ticker(sym).history(period="10d", interval="1d", auto_adjust=False).dropna(subset=["Close"])
                    if len(d) >= 2:
                        l, pc = float(d.Close.iloc[-1]), float(d.Close.iloc[-2]); hi, lo = float(d.High.iloc[-1]), float(d.Low.iloc[-1]); rg = hi - lo
                        q = dict(last=num(l), prev=num(pc), chg=num(l-pc), pct=num((l/pc-1)*100), hi=num(hi), lo=num(lo),
                                 flag="HI" if rg > 0 and hi-l <= .03*rg else "LO" if rg > 0 and l-lo <= .03*rg else "",
                                 asof=d.index[-1].strftime("%m/%d") + " D", stale=False)
                except Exception: q = None
            status = "NA" if q is None else st.split(":")[0]
            R.append(dict(name=name, code=code, status=status, note=st.split(":",1)[1] if ":" in st else "", q=q))
        out["groups"].append(dict(name=g, rows=R))
    W = []
    for name, code, kind, sym, st in NW:
        q = None
        try:
            if kind == "yf":
                try: df = raw[sym].copy(); df.index = df.index.tz_convert(ET); q = one(sym, df)
                except Exception: q = None
                if q is None:
                    d = yf.Ticker(sym).history(period="10d", interval="1d", auto_adjust=False).dropna(subset=["Close"])
                    q = daily_q([(i, float(c)) for i, c in d.Close.items()], d.index[-1].strftime("%m/%d") + " D") if len(d) >= 2 else None
            elif kind.startswith("ust:"): q = ust_q(kind[4:])
            elif kind == "de10": q = de10_q()
        except Exception: q = None
        W.append(dict(name=name, code=code, status="NA" if q is None else st.split(":")[0], note=st.split(":",1)[1] if ":" in st else "",
                      yld=code in ("US30Y","US20Y","US10Y","TNX","BUND"), q=q))
    out["nightwatch"] = W
    for c, sym in (("ES","ES=F"),("NQ","NQ=F")):
        df = raw[sym].copy(); df.index = df.index.tz_convert(ET); out["strip"][c] = strip(sym, df)
    (HERE / "overnight.json").write_text(json.dumps(out, indent=1))
    print(json.dumps({"NW": {r["code"]: r["status"] for r in out["nightwatch"]}}))
    print(json.dumps({g["name"]: {r["code"]: r["status"] for r in g["rows"]} for g in out["groups"]}))
if __name__ == "__main__": main()
