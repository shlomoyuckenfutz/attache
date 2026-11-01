#!/usr/bin/env python3
"""OVERNIGHT detail panels fetch (paper/research only; free delayed data only) -> es_levels/overnight_details.json.
Panels: ON levels (ES/NQ), curve, sector/megacap ext-hours pulse + earnings flags, next-session calendar. Source names never reach the page."""
import json, math, warnings, urllib.request, io
from pathlib import Path
from datetime import datetime, timedelta, date
import pandas as pd, yfinance as yf
warnings.filterwarnings("ignore")
HERE = Path(__file__).resolve().parent; ET = "America/New_York"; PT = "America/Los_Angeles"
UA = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64)", "Accept": "application/json"}
def num(v, d=4): return None if v is None or (isinstance(v, float) and math.isnan(v)) else round(float(v), d)
def get(u, t=20): return urllib.request.urlopen(urllib.request.Request(u, headers=UA), timeout=t).read()
def next_session(now):
    d = now.date() + timedelta(days=1 if now.hour >= 16 else 0)
    while d.weekday() >= 5: d += timedelta(days=1)
    return d
def third_fri(y, m):
    d = date(y, m, 15)
    while d.weekday() != 4: d += timedelta(days=1)
    return d
def vix_exp(y, m):  # Wednesday 30 days before the 3rd Friday of the following month
    ny, nm = (y + 1, 1) if m == 12 else (y, m + 1); return third_fri(ny, nm) - timedelta(days=30)
def on_levels(sym, df):
    df = df.dropna(subset=["Close"]).copy(); df.index = df.index.tz_convert(ET)
    days = sorted({i.normalize() for i in df.index}); S = []
    for d in days:  # session = 18:00 ET (d-1) .. 09:30 ET d ; RTH = 09:30..16:00 d
        on = df[(df.index >= d - timedelta(hours=6)) & (df.index < d + timedelta(hours=9, minutes=30))]
        rth = df[(df.index >= d + timedelta(hours=9, minutes=30)) & (df.index < d + timedelta(hours=16))]
        S.append(dict(d=d, on=on, rth=rth))
    last_t = df.index[-1]; st = (last_t.normalize() + timedelta(hours=18)); st = st if last_t >= st else st - timedelta(days=1)
    cur = df[df.index >= st]
    prior = [s for s in S if len(s["rth"]) and s["d"] < st][-1]
    hist = [s for s in S if len(s["on"]) > 100 and s["d"] <= prior["d"]][-10:]
    rth = prior["rth"]; pc = float(rth.Close.iloc[-1]); ph, pl = float(rth.High.max()), float(rth.Low.min())
    oh, ol = float(cur.High.max()), float(cur.Low.min()); last = float(cur.Close.iloc[-1]); vol = float(cur.Volume.sum())
    # comparable volume: same elapsed window of each prior ON session
    el = last_t - st; hv = [float(s["on"][s["on"].index < s["d"] - timedelta(hours=6) + el].Volume.sum()) for s in hist]
    hr = [float(s["on"].High.max() - s["on"].Low.min()) for s in hist]
    rng = oh - ol; avgv = sum(hv) / len(hv) if hv else None; avgr = sum(hr) / len(hr) if hr else None
    pos = "INSIDE" if oh <= ph and ol >= pl else "ABOVE" if ol > ph else "BELOW" if oh < pl else "OUTSIDE (H)" if oh > ph and ol >= pl else "OUTSIDE (L)" if ol < pl and oh <= ph else "OUTSIDE (BOTH)"
    bars = [[t.strftime('%m/%d %H:%M'), num(r.Open, 2), num(r.High, 2), num(r.Low, 2), num(r.Close, 2)] for t, r in cur.iterrows()]
    return dict(last=num(last, 2), on_hi=num(oh, 2), on_lo=num(ol, 2), on_mid=num((oh + ol) / 2, 2), rth_close=num(pc, 2), rth_hi=num(ph, 2), rth_lo=num(pl, 2),
                rth_date=prior["d"].strftime("%m/%d"), gap=num(last - pc, 2), gap_pct=num((last / pc - 1) * 100, 3), pos=pos,
                on_vol=int(vol), avg_vol=int(avgv) if avgv else None, vol_ratio=num(vol / avgv, 2) if avgv else None,
                on_range=num(rng, 2), avg_range=num(avgr, 2), range_pct=num(100 * rng / avgr, 1) if avgr else None,
                n_hist=len(hist), elapsed_h=num(el.total_seconds() / 3600, 1), asof=last_t.strftime("%m/%d %H:%M"), sess_start=st.strftime("%m/%d %H:%M"), bars=bars)
def ust_curve():
    y = datetime.now().year; rows = []
    for yy in (y - 1, y):
        u = f"https://home.treasury.gov/resource-center/data-chart-center/interest-rates/daily-treasury-rates.csv/{yy}/all?type=daily_treasury_yield_curve&field_tdr_date_value={yy}&page&_format=csv"
        try: rows.append(pd.read_csv(io.BytesIO(get(u))))
        except Exception: pass
    df = pd.concat(rows); df["Date"] = pd.to_datetime(df["Date"]); df = df.sort_values("Date")
    a, b = df.iloc[-1], df.iloc[-2]
    return {k: dict(last=num(a[k], 3), prev=num(b[k], 3)) for k in ("3 Mo", "2 Yr", "10 Yr")} | {"date": a["Date"].strftime("%m/%d")}
def yld(sym):
    d = yf.Ticker(sym).history(period="10d", interval="1d", auto_adjust=False).dropna(subset=["Close"])
    i = yf.Ticker(sym).history(period="1d", interval="5m", auto_adjust=False).dropna(subset=["Close"])
    last = float(i.Close.iloc[-1]) if len(i) else float(d.Close.iloc[-1]); t = (i.index[-1] if len(i) else d.index[-1]).tz_convert(ET)
    prev = float(d.Close.iloc[-2]) if t.normalize() == d.index[-1].tz_convert(ET).normalize() else float(d.Close.iloc[-1])
    return dict(last=num(last, 3), prev=num(prev, 3), asof=t.strftime("%m/%d %H:%M"))
PULSE = [("SECTOR", ["XLK", "XLF", "XLE", "XLV", "XLY", "SMH"]), ("MEGACAP", ["NVDA", "AAPL", "MSFT", "AMZN", "META", "GOOGL", "TSLA", "AVGO"])]
def pulse():
    syms = [s for _, l in PULSE for s in l]
    raw = yf.download(syms, period="5d", interval="5m", prepost=True, progress=False, group_by="ticker", threads=True, auto_adjust=False)
    out = {}
    for s in syms:
        try:
            df = raw[s].dropna(subset=["Close"]).copy(); df.index = df.index.tz_convert(ET)
            reg = df[(df.index.time >= datetime.strptime("09:30", "%H:%M").time()) & (df.index.time < datetime.strptime("16:00", "%H:%M").time())]
            lt = df.index[-1]; ld = lt.normalize()
            if lt.time() < datetime.strptime("09:30", "%H:%M").time(): ref = reg[reg.index < ld]; sess = "PRE"
            elif lt.time() >= datetime.strptime("16:00", "%H:%M").time(): ref = reg[reg.index < ld + timedelta(hours=16)]; sess = "AH"
            else: ref = reg[reg.index < ld]; sess = "RTH"
            pc = float(ref.Close.iloc[-1]); last = float(df.Close.iloc[-1])
            out[s] = dict(last=num(last, 2), prev=num(pc, 2), chg=num(last - pc, 2), pct=num((last / pc - 1) * 100, 2), sess=sess, asof=lt.strftime("%m/%d %H:%M"))
        except Exception: out[s] = None
    return out
def earnings(days):
    E = {}
    for d in days:
        try: rows = json.loads(get(f"https://api.nasdaq.com/api/calendar/earnings?date={d.isoformat()}"))["data"]["rows"] or []
        except Exception: rows = []
        for r in rows:
            t = {"time-after-hours": "AMC", "time-pre-market": "BMO"}.get(r.get("time"), "TBD")
            E.setdefault(r["symbol"], []).append(dict(date=d.strftime("%m/%d"), time=t, eps=r.get("epsForecast") or ""))
    return E
def calendar(ns):
    out = dict(econ=[], fed=[], auctions=[], expiries=[], ok=True)
    try:
        ev = json.loads(get("https://nfs.faireconomy.media/ff_calendar_thisweek.json"))
        for x in ev:
            if x.get("country") != "USD": continue
            t = pd.Timestamp(x["date"])
            if t.tz_convert(ET).date() != ns: continue
            r = dict(time_pt=t.tz_convert(PT).strftime("%H:%M") if (t.hour or t.minute) else "ALL DAY", title=x["title"], impact=x.get("impact", ""),
                     fc=x.get("forecast") or "", prev=x.get("previous") or "")
            (out["fed"] if any(k in x["title"] for k in ("Speaks", "FOMC", "Fed ", "Powell", "Testifies")) else out["econ"]).append(r)
    except Exception: out["ok"] = False
    try:
        for a in json.loads(get("https://www.treasurydirect.gov/TA_WS/securities/upcoming?format=json")):
            d = pd.Timestamp(a["auctionDate"] if a.get("auctionDate") else a["competitiveAuctionCloseDate"]).date()
            if ns <= d <= ns + timedelta(days=6):
                tm = a.get("competitiveAuctionCloseTime") or ""
                tp = (datetime.strptime(tm, "%I:%M %p") - timedelta(hours=3)).strftime("%H:%M") if tm else "—"
                out["auctions"].append(dict(date=d.strftime("%a %m/%d"), next=d == ns, time_pt=tp, term=a["securityTerm"], type=a["securityType"],
                                            reopen=a.get("reopening") == "Yes", size=num(float(a["offeringAmount"]) / 1e9, 1) if a.get("offeringAmount") else None))
        out["auctions"].sort(key=lambda r: (r["date"][4:], r["time_pt"]))
    except Exception: pass
    y, m = ns.year, ns.month
    for yy, mm in ((y, m), ((y, m + 1) if m < 12 else (y + 1, 1))):
        o, v = third_fri(yy, mm), vix_exp(yy, mm)
        out["expiries"] += [dict(what="Monthly equity OPEX", d=o), dict(what="VIX expiration (AM settle 06:30 PT)", d=v)]
    out["expiries"] = sorted([dict(what=x["what"], date=x["d"].strftime("%a %m/%d"), days=(x["d"] - ns).days, today=x["d"] == ns) for x in out["expiries"] if x["d"] >= ns], key=lambda r: r["days"])
    return out
def main():
    now = pd.Timestamp.now(tz=ET); ns = next_session(now); out = dict(generated_et=now.strftime("%Y-%m-%d %H:%M ET"), next_session=ns.strftime("%a %m/%d"))
    raw = yf.download(["ES=F", "NQ=F"], period="20d", interval="5m", prepost=True, progress=False, group_by="ticker", auto_adjust=False)
    out["on"] = {}
    for k, s in (("ES", "ES=F"), ("NQ", "NQ=F")):
        try: out["on"][k] = on_levels(s, raw[s])
        except Exception as ex: out["on"][k] = None
    Y = {}
    for k, s in (("3M", "^IRX"), ("5Y", "^FVX"), ("10Y", "^TNX"), ("30Y", "^TYX")):
        try: Y[k] = yld(s)
        except Exception: Y[k] = None
    try: U = ust_curve(); Y["2Y"] = dict(last=U["2 Yr"]["last"], prev=U["2 Yr"]["prev"], asof=U["date"] + " D", proxy="official daily 2Y par yield (no free intraday 2Y)")
    except Exception: U = None; Y["2Y"] = None
    out["yields"] = Y; out["ust"] = U
    out["pulse"] = pulse()
    pd_ = now.date(); E = earnings([pd_, ns] if ns != pd_ else [ns, ns + timedelta(days=1)])
    out["earn"] = {s: E[s] for _, l in PULSE for s in l if s in E}
    out["earn_other"] = {s: v for s, v in E.items() if s in ("NFLX", "IBM", "TXN", "INTC", "AMD", "QCOM", "ORCL", "CRM", "ADBE", "JPM", "BAC", "GS", "UNH", "LLY", "XOM", "CVX", "KO", "T", "VZ", "BA", "CAT", "LMT", "AXP", "SLB", "HCA", "INFY", "FCNCA", "BAH", "ALV")}
    out["cal"] = calendar(ns)
    (HERE / "overnight_details.json").write_text(json.dumps(out, indent=1, default=str))
    print(json.dumps(dict(on={k: (v or {}).get("pos") for k, v in out["on"].items()}, y={k: (v or {}).get("last") for k, v in Y.items()},
                          pulse=sum(1 for v in out["pulse"].values() if v), earn=list(out["earn"]), econ=len(out["cal"]["econ"]), auc=len(out["cal"]["auctions"]))))
if __name__ == "__main__": main()
