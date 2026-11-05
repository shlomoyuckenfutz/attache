#!/usr/bin/env python3
"""Attaché TERMINAL snapshot builder — free public data only.

Fetches quotes/charts (free_data), filings (SEC EDGAR), macro (FRED CSV),
news/earnings (free_data RSS + Nasdaq calendar + SEC 8-K), options (free_data then CBOE),
and builds a rule-based DESK summary. Writes terminal-test/data/snapshot.json
and embeds into terminal-test/_src/terminal_plain.html (from template).

Usage:
  python3 scripts/terminal_fetch.py
  # then encrypt + publish as documented in terminal-test/README.md

Never creates routines. No paid APIs/keys.
"""
from __future__ import annotations

import csv
import io
import json
import math
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

PT = ZoneInfo("America/Los_Angeles")
ETZ = ZoneInfo("America/New_York")
SITE = Path(os.environ.get("SITE", "/workspace/orb-dash-site"))
OUT_DIR = SITE / "terminal-test" / "data"
OUT_JSON = OUT_DIR / "snapshot.json"
DESK = Path(os.environ.get("DESK", "/workspace/desk/orb-research"))
PLAIN_TEMPLATE = DESK / "terminal_src" / "terminal_plain.template.html"
PLAIN_OUT = DESK / "terminal_src" / "terminal_plain.html"
UA_FEED = "Mozilla/5.0 (compatible; AttacheTerminal/1.0; +mailto:Shlomoyuckenfutz@gmail.com)"
UA_SEC = "AttacheTerminal/1.0 (Shlomoyuckenfutz@gmail.com)"
UA_NASDAQ = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"

WATCH_INDEX = [
    ("SPY", "SPY"),
    ("QQQ", "QQQ"),
    ("SPX", "^GSPC"),
    ("NDX", "^NDX"),
    ("ES", "ES=F"),
    ("NQ", "NQ=F"),
    ("VIX", "^VIX"),
    ("DXY", "DX-Y.NYB"),
    ("TNX", "^TNX"),
    ("BTC", "BTC-USD"),
    ("ETH", "ETH-USD"),
    ("EURUSD", "EURUSD=X"),
]
WATCH_EQUITY = ["AAPL", "NVDA", "MSFT", "TSLA", "META", "AMZN"]
ALL_LABELS = [a for a, _ in WATCH_INDEX] + WATCH_EQUITY

# SEC CIK map (padded). Fallback to company_tickers.json when missing.
CIK = {
    "AAPL": "0000320193",
    "NVDA": "0001045810",
    "MSFT": "0000789019",
    "TSLA": "0001318605",
    "META": "0001326801",
    "AMZN": "0001018724",
    "SPY": "0000884394",  # SPDR S&P 500 ETF Trust
    "QQQ": "0001067839",  # Invesco QQQ Trust
}

FRED_SERIES = [
    ("CPIAUCSL", "CPI"),
    ("PCEPILFE", "Core PCE"),
    ("UNRATE", "UNRATE"),
    ("PAYEMS", "PAYEMS"),
    ("FEDFUNDS", "FEDFUNDS"),
    ("DGS2", "DGS2"),
    ("DGS10", "DGS10"),
    ("T10Y2Y", "T10Y2Y"),
    ("ICSA", "Initial Claims"),
]

OPT_RX = re.compile(r"^([A-Z]+)(\d{6})([CP])(\d{8})$")


def now_pt() -> datetime:
    return datetime.now(PT)


def iso_pt(dt: datetime | None = None) -> str:
    d = dt or now_pt()
    return d.strftime("%Y-%m-%d %H:%M:%S %Z")


def panel(ok: bool, data=None, error: str | None = None, fetched_at: str | None = None):
    return {
        "ok": ok,
        "error": error,
        "fetched_at": fetched_at or iso_pt(),
        "data": data,
    }


def http_get(url: str, headers: dict | None = None, timeout: int = 30, retries: int = 3):
    last = None
    h = {"User-Agent": UA_FEED, "Accept": "*/*"}
    if headers:
        h.update(headers)
    for i in range(retries):
        try:
            req = urllib.request.Request(url, headers=h)
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return resp.read()
        except Exception as e:
            last = e
            time.sleep(0.8 + 0.6 * i)
    raise last


def http_json(url: str, headers: dict | None = None, timeout: int = 30):
    return json.loads(http_get(url, headers=headers, timeout=timeout))


def http_text(url: str, headers: dict | None = None, timeout: int = 30):
    return http_get(url, headers=headers, timeout=timeout).decode("utf-8", "replace")


# ── Quotes / Charts (free_data) ───────────────────────────────────────────────

def fetch_feed_chart(symbol: str, range_: str = "1d", interval: str = "5m"):
    for host in ("query1", "query2"):
        url = (
            f"https://{host}.finance.free_data.com/v8/finance/chart/"
            f"{urllib.parse.quote(symbol, safe='^=')}?range={range_}&interval={interval}"
        )
        try:
            d = http_json(url, headers={"User-Agent": UA_FEED})
            err = d.get("chart", {}).get("error")
            results = d.get("chart", {}).get("result") or []
            if err or not results:
                continue
            return results[0]
        except Exception:
            continue
    raise RuntimeError(f"free_data chart failed for {symbol}")


def spark_from_closes(closes):
    vals = [c for c in closes if c is not None]
    if len(vals) < 2:
        return []
    lo, hi = min(vals), max(vals)
    span = (hi - lo) or 1.0
    # normalize to 0..1 for SVG
    return [round((c - lo) / span, 4) if c is not None else None for c in closes]


def quote_row(label: str, feed_sym: str):
    try:
        # intraday for spark
        try:
            r = fetch_feed_chart(feed_sym, "1d", "5m")
        except Exception:
            r = fetch_feed_chart(feed_sym, "5d", "1d")
        meta = r.get("meta") or {}
        ind = (r.get("indicators") or {}).get("quote") or [{}]
        closes = (ind[0] or {}).get("close") or []
        last = meta.get("regularMarketPrice")
        if last is None:
            for c in reversed(closes):
                if c is not None:
                    last = c
                    break
        prev = meta.get("chartPreviousClose") or meta.get("previousClose")
        chg = None
        chg_pct = None
        if last is not None and prev:
            chg = last - prev
            chg_pct = 100.0 * chg / prev if prev else None
        return {
            "label": label,
            "symbol": feed_sym,
            "last": last,
            "prev": prev,
            "change": chg,
            "change_pct": chg_pct,
            "spark": spark_from_closes(closes[-48:]),
            "currency": meta.get("currency"),
            "ok": True,
            "error": None,
        }
    except Exception as e:
        return {
            "label": label,
            "symbol": feed_sym,
            "last": None,
            "prev": None,
            "change": None,
            "change_pct": None,
            "spark": [],
            "currency": None,
            "ok": False,
            "error": str(e)[:180],
        }


def fetch_quotes():
    rows = []
    specs = list(WATCH_INDEX) + [(t, t) for t in WATCH_EQUITY]
    with ThreadPoolExecutor(max_workers=8) as ex:
        futs = {ex.submit(quote_row, lab, sym): lab for lab, sym in specs}
        for fut in as_completed(futs):
            rows.append(fut.result())
    # stable order
    order = {lab: i for i, (lab, _) in enumerate(specs)}
    rows.sort(key=lambda r: order.get(r["label"], 99))
    ok = any(r["ok"] for r in rows)
    err = None if ok else "all quote fetches failed"
    return panel(ok, {"quotes": rows}, err)


# ── SEC filings ───────────────────────────────────────────────────────────

def load_ticker_ciks():
    try:
        d = http_json(
            "https://www.sec.gov/files/company_tickers.json",
            headers={"User-Agent": UA_SEC},
        )
        out = {}
        for _, row in d.items():
            t = (row.get("ticker") or "").upper()
            if t:
                out[t] = f"{int(row['cik_str']):010d}"
        return out
    except Exception:
        return {}


def sec_submissions(cik: str):
    return http_json(
        f"https://data.sec.gov/submissions/CIK{cik}.json",
        headers={"User-Agent": UA_SEC},
    )


def sec_recent_forms(ticker: str, cik: str, forms=("10-K", "10-Q", "8-K", "4", "13F-HR")):
    d = sec_submissions(cik)
    recent = d.get("filings", {}).get("recent", {})
    forms_l = recent.get("form") or []
    dates = recent.get("filingDate") or []
    acc = recent.get("accessionNumber") or []
    primary = recent.get("primaryDocument") or []
    # Per-form caps so Form 4 flood does not hide 10-K/10-Q/8-K/13F
    caps = {"10-K": 2, "10-Q": 2, "8-K": 4, "4": 4, "4/A": 2, "13F-HR": 3, "13F-HR/A": 2}
    counts = {}
    items = []

    def want(f: str) -> bool:
        if f in forms or f in caps:
            return True
        if "4" in forms and f in ("4", "4/A"):
            return True
        if "13F-HR" in forms and f.startswith("13F"):
            return True
        return False

    for i, f in enumerate(forms_l):
        if not want(f):
            continue
        if counts.get(f, 0) >= caps.get(f, 2):
            continue
        accession = (acc[i] if i < len(acc) else "").replace("-", "")
        doc = primary[i] if i < len(primary) else ""
        url = ""
        if accession and doc:
            url = f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/{accession}/{doc}"
        items.append(
            {
                "ticker": ticker,
                "form": f,
                "filed": dates[i] if i < len(dates) else None,
                "accession": acc[i] if i < len(acc) else None,
                "url": url,
            }
        )
        counts[f] = counts.get(f, 0) + 1
    return {
        "ticker": ticker,
        "name": d.get("name"),
        "cik": cik,
        "filings": items,
    }


def fetch_filings():
    try:
        cik_map = load_ticker_ciks()
        for k, v in CIK.items():
            cik_map.setdefault(k, v)
        tickers = WATCH_EQUITY  # focus watchlist equities + ETF shells lightly
        results = []
        errors = []
        for t in tickers:
            cik = cik_map.get(t)
            if not cik:
                errors.append(f"{t}: no CIK")
                continue
            try:
                time.sleep(0.15)  # SEC fair access
                results.append(sec_recent_forms(t, cik))
            except Exception as e:
                errors.append(f"{t}: {e}"[:160])
        # Form 4 buys heuristic: keep form 4 rows tagged
        insider = []
        thirteen_f = []
        for r in results:
            for f in r.get("filings") or []:
                if f["form"] in ("4", "4/A"):
                    insider.append(f)
                if f["form"] in ("13F-HR", "13F-HR/A"):
                    thirteen_f.append(f)
        ok = bool(results)
        return panel(
            ok,
            {
                "companies": results,
                "insider_form4": insider[:40],
                "thirteen_f": thirteen_f[:20],
                "note": "Form 4 = insider filings; 13F = institutional holdings reports. Numbers moved summarized where filing metadata available.",
            },
            "; ".join(errors) if errors and not ok else ("; ".join(errors[:3]) if errors else None),
        )
    except Exception as e:
        return panel(False, None, str(e)[:200])


# ── FRED macro ────────────────────────────────────────────────────────────

def fred_series(series_id: str):
    url = f"https://fred.stlouisfed.org/graph/fredgraph.csv?id={series_id}"
    text = http_text(url, headers={"User-Agent": UA_FEED})
    # skip comments
    lines = [ln for ln in text.splitlines() if ln and not ln.startswith("#")]
    reader = csv.DictReader(io.StringIO("\n".join(lines)))
    # columns: observation_date, SERIES
    rows = []
    for row in reader:
        # date key may vary
        date_k = None
        val_k = None
        for k in row:
            lk = k.lower()
            if "date" in lk:
                date_k = k
            else:
                val_k = k
        if not date_k or not val_k:
            continue
        v = row[val_k].strip()
        if v in ("", ".", "NA"):
            continue
        try:
            rows.append((row[date_k], float(v)))
        except ValueError:
            continue
    if len(rows) < 2:
        raise RuntimeError(f"FRED {series_id}: insufficient rows")
    latest, prior = rows[-1], rows[-2]
    chg = latest[1] - prior[1]
    chg_pct = (100.0 * chg / prior[1]) if prior[1] else None
    # big move heuristics
    big = False
    abs_chg = abs(chg)
    if series_id in ("UNRATE", "FEDFUNDS", "T10Y2Y", "DGS2", "DGS10") and abs_chg >= 0.2:
        big = True
    if series_id == "ICSA" and abs(chg_pct or 0) >= 5:
        big = True
    if series_id in ("CPIAUCSL", "PCEPILFE", "PAYEMS") and abs(chg_pct or 0) >= 0.3:
        big = True
    if series_id == "PAYEMS" and abs_chg >= 100:  # thousands
        big = True
    return {
        "id": series_id,
        "latest_date": latest[0],
        "latest": latest[1],
        "prior_date": prior[0],
        "prior": prior[1],
        "change": chg,
        "change_pct": chg_pct,
        "big_move": big,
    }


def fetch_macro():
    series = []
    errors = []
    for sid, label in FRED_SERIES:
        try:
            row = fred_series(sid)
            row["label"] = label
            series.append(row)
            time.sleep(0.05)
        except Exception as e:
            errors.append(f"{label}: {e}"[:120])
            series.append(
                {
                    "id": sid,
                    "label": label,
                    "error": str(e)[:120],
                    "latest": None,
                    "big_move": False,
                }
            )
    ok = any(s.get("latest") is not None for s in series)
    return panel(ok, {"series": series}, None if ok else "; ".join(errors))


# ── News / Earnings ───────────────────────────────────────────────────────

def feed_rss(ticker: str, limit: int = 5):
    url = f"https://feeds.finance.free_data.com/rss/2.0/headline?s={ticker}&region=US&lang=en-US"
    text = http_text(url, headers={"User-Agent": UA_FEED})
    root = ET.fromstring(text)
    items = []
    for item in root.findall("./channel/item")[:limit]:
        title = (item.findtext("title") or "").strip()
        link = (item.findtext("link") or "").strip()
        pub = (item.findtext("pubDate") or "").strip()
        # strip analyst/person names? keep headlines as-is but do not attribute people in desk copy
        items.append({"ticker": ticker, "title": title, "link": link, "published": pub, "source": "desk"})
    return items


def nasdaq_earnings_for_dates(dates, watch):
    watch_u = set(watch)
    out = []
    errors = []
    for d in dates:
        url = f"https://api.nasdaq.com/api/calendar/earnings?date={d}"
        try:
            raw = http_json(
                url,
                headers={
                    "User-Agent": UA_NASDAQ,
                    "Accept": "application/json, text/plain, */*",
                    "Origin": "https://www.nasdaq.com",
                    "Referer": "https://www.nasdaq.com/",
                },
                timeout=20,
            )
            rows = (((raw or {}).get("data") or {}).get("rows")) or []
            for r in rows:
                sym = (r.get("symbol") or "").upper()
                if sym in watch_u:
                    out.append(
                        {
                            "ticker": sym,
                            "date": d,
                            "time": r.get("time"),
                            "name": r.get("name"),
                            "eps_forecast": r.get("epsForecast") or r.get("eps_forecast"),
                            "source": "desk",
                        }
                    )
        except Exception as e:
            errors.append(f"{d}: {e}"[:100])
        time.sleep(0.1)
    return out, errors


def sec_8k_headlines(ticker: str, cik: str, limit: int = 3):
    url = (
        "https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany"
        f"&CIK={cik}&type=8-K&dateb=&owner=include&count={limit}&output=atom"
    )
    text = http_text(url, headers={"User-Agent": UA_SEC})
    # namespace
    ns = {"a": "http://www.w3.org/2005/Atom"}
    root = ET.fromstring(text)
    items = []
    for entry in root.findall("a:entry", ns)[:limit]:
        title = (entry.findtext("a:title", default="", namespaces=ns) or "").strip()
        updated = (entry.findtext("a:updated", default="", namespaces=ns) or "").strip()
        link_el = entry.find("a:link", ns)
        href = link_el.get("href") if link_el is not None else ""
        items.append(
            {
                "ticker": ticker,
                "title": title,
                "link": href,
                "published": updated,
                "source": "desk",
            }
        )
    return items


def fetch_news():
    news = []
    errors = []
    watch = WATCH_EQUITY + ["SPY", "QQQ"]
    with ThreadPoolExecutor(max_workers=6) as ex:
        futs = {ex.submit(feed_rss, t): t for t in watch}
        for fut in as_completed(futs):
            t = futs[fut]
            try:
                news.extend(fut.result())
            except Exception as e:
                errors.append(f"RSS {t}: {e}"[:100])

    # SEC 8-K
    cik_map = dict(CIK)
    try:
        cik_map.update(load_ticker_ciks())
    except Exception:
        pass
    for t in WATCH_EQUITY:
        cik = cik_map.get(t)
        if not cik:
            continue
        try:
            time.sleep(0.12)
            news.extend(sec_8k_headlines(t, cik))
        except Exception as e:
            errors.append(f"8-K {t}: {e}"[:100])

    # upcoming earnings ~ next 14 days
    today = datetime.now(ETZ).date()
    dates = [(today + timedelta(days=i)).isoformat() for i in range(0, 14)]
    earnings, e_err = nasdaq_earnings_for_dates(dates, watch)
    errors.extend(e_err)

    # filter news to watchlist tickers only (already tagged)
    news_sorted = sorted(news, key=lambda x: x.get("published") or "", reverse=True)[:60]
    ok = bool(news_sorted) or bool(earnings)
    return panel(
        ok,
        {"news": news_sorted, "earnings": earnings},
        None if ok else ("; ".join(errors[:4]) or "news/earnings empty"),
    )


# ── Options (free_data try → CBOE) ────────────────────────────────────────────

def try_feed_options(symbol: str):
    for host in ("query1", "query2"):
        url = f"https://{host}.finance.free_data.com/v7/finance/options/{symbol}"
        try:
            d = http_json(url, headers={"User-Agent": UA_FEED}, timeout=20)
            chain = (d.get("optionChain") or {}).get("result") or []
            if not chain:
                err = (d.get("optionChain") or {}).get("error") or d.get("finance", {}).get("error")
                raise RuntimeError(str(err) or "empty")
            return chain[0], "free_data"
        except Exception as e:
            last = e
            continue
    raise last


def fetch_cboe_options(symbol: str):
    url = f"https://cdn.cboe.com/api/global/delayed_quotes/options/{symbol}.json"
    d = http_json(url, headers={"User-Agent": UA_FEED}, timeout=40)
    return d, "CBOE delayed"


def analyze_cboe(symbol: str, payload: dict):
    data = payload.get("data") or {}
    px = data.get("current_price")
    opts = data.get("options") or []
    # nearest expiry with liquidity
    by_exp = {}
    for o in opts:
        m = OPT_RX.match(o.get("option") or "")
        if not m:
            continue
        root, yymmdd, cp, strike_raw = m.groups()
        if root != symbol:
            continue
        strike = int(strike_raw) / 1000.0
        exp = yymmdd
        by_exp.setdefault(exp, []).append((cp, strike, o))

    if not by_exp or px is None:
        raise RuntimeError("no options parsed")

    # pick nearest expiry with enough OI
    def exp_score(exp):
        rows = by_exp[exp]
        oi = sum((r[2].get("open_interest") or 0) for r in rows)
        return oi

    exp = sorted(by_exp.keys(), key=lambda e: (-exp_score(e), e))[0]
    # prefer soonest with oi>1000
    soon = sorted(by_exp.keys())
    for e in soon:
        if exp_score(e) >= 500:
            exp = e
            break

    rows = by_exp[exp]
    calls = [(s, o) for cp, s, o in rows if cp == "C"]
    puts = [(s, o) for cp, s, o in rows if cp == "P"]

    def nearest_delta(side_rows, target, sign):
        # sign: +1 calls, -1 puts; find closest |delta| to target
        best = None
        best_diff = 1e9
        for strike, o in side_rows:
            d = o.get("delta")
            if d is None:
                continue
            if sign > 0 and d <= 0:
                continue
            if sign < 0 and d >= 0:
                continue
            diff = abs(abs(d) - target)
            if diff < best_diff:
                best_diff = diff
                best = (strike, o, d)
        return best

    c25 = nearest_delta(calls, 0.25, +1)
    p25 = nearest_delta(puts, 0.25, -1)
    skew = None
    if c25 and p25:
        civ = c25[1].get("iv") or 0
        piv = p25[1].get("iv") or 0
        skew = piv - civ  # put IV minus call IV

    # OTM put vs call IV near 5% OTM
    otm_put = min(puts, key=lambda x: abs(x[0] - px * 0.95)) if puts else None
    otm_call = min(calls, key=lambda x: abs(x[0] - px * 1.05)) if calls else None
    otm = None
    if otm_put and otm_call:
        otm = {
            "put_strike": otm_put[0],
            "put_iv": otm_put[1].get("iv"),
            "call_strike": otm_call[0],
            "call_iv": otm_call[1].get("iv"),
            "put_minus_call_iv": (otm_put[1].get("iv") or 0) - (otm_call[1].get("iv") or 0),
        }

    call_oi = sum((o.get("open_interest") or 0) for _, o in calls)
    put_oi = sum((o.get("open_interest") or 0) for _, o in puts)
    pc_ratio = (put_oi / call_oi) if call_oi else None

    # biggest OI strikes
    ranked = sorted(
        ((cp, s, o.get("open_interest") or 0, o.get("iv"), o.get("delta")) for cp, s, o in rows),
        key=lambda x: -x[2],
    )[:8]
    biggest = [
        {"type": cp, "strike": s, "oi": oi, "iv": iv, "delta": delta}
        for cp, s, oi, iv, delta in ranked
        if oi > 0
    ]

    return {
        "symbol": symbol,
        "underlying": px,
        "expiry": f"20{exp[0:2]}-{exp[2:4]}-{exp[4:6]}",
        "skew_25d": {
            "put_iv": p25[1].get("iv") if p25 else None,
            "call_iv": c25[1].get("iv") if c25 else None,
            "put_strike": p25[0] if p25 else None,
            "call_strike": c25[0] if c25 else None,
            "put_delta": p25[2] if p25 else None,
            "call_delta": c25[2] if c25 else None,
            "put_minus_call_iv": skew,
        },
        "otm_iv": otm,
        "put_call_oi_ratio": pc_ratio,
        "put_oi": put_oi,
        "call_oi": call_oi,
        "biggest_oi": biggest,
    }


def fetch_options():
    results = []
    errors = []
    source = None
    for sym in ("SPY", "QQQ"):
        try:
            try:
                chain, source = try_feed_options(sym)
                # free_data path: minimal summary if somehow works
                quote = chain.get("quote") or {}
                opts = (chain.get("options") or [{}])[0]
                calls = opts.get("calls") or []
                puts = opts.get("puts") or []
                call_oi = sum(c.get("openInterest") or 0 for c in calls)
                put_oi = sum(p.get("openInterest") or 0 for p in puts)
                results.append(
                    {
                        "symbol": sym,
                        "underlying": quote.get("regularMarketPrice"),
                        "expiry": None,
                        "skew_25d": None,
                        "otm_iv": None,
                        "put_call_oi_ratio": (put_oi / call_oi) if call_oi else None,
                        "put_oi": put_oi,
                        "call_oi": call_oi,
                        "biggest_oi": [],
                        "source": source,
                        "note": "free_data options returned; skew not computed in this path",
                    }
                )
            except Exception:
                payload, source = fetch_cboe_options(sym)
                row = analyze_cboe(sym, payload)
                row["source"] = source
                results.append(row)
        except Exception as e:
            errors.append(f"{sym}: {e}"[:160])
            results.append({"symbol": sym, "error": str(e)[:160], "source": None})
    ok = any(r.get("underlying") is not None for r in results)
    return panel(ok, {"chains": results, "source_note": source}, None if ok else "; ".join(errors))


# ── Desk summary (rule-based) ─────────────────────────────────────────────

def desk_summary(quotes_p, macro_p, news_p, options_p, filings_p):
    lines = []
    qrows = ((quotes_p or {}).get("data") or {}).get("quotes") or []
    by = {r["label"]: r for r in qrows if r.get("ok")}

    def pct(lab):
        r = by.get(lab)
        return r.get("change_pct") if r else None

    spy, qqq, vix, tnx, dxy = pct("SPY"), pct("QQQ"), pct("VIX"), pct("TNX"), pct("DXY")
    btc, eth = pct("BTC"), pct("ETH")

    # risk tone
    if spy is not None and qqq is not None:
        if spy <= -1.0 and qqq <= -1.0:
            lines.append(f"Risk-off session: SPY {spy:+.2f}% and QQQ {qqq:+.2f}% are both down hard.")
        elif spy >= 1.0 and qqq >= 1.0:
            lines.append(f"Risk-on bid: SPY {spy:+.2f}% and QQQ {qqq:+.2f}% are both up solidly.")
        else:
            lines.append(f"Equity tape mixed-to-quiet: SPY {spy:+.2f}%, QQQ {qqq:+.2f}%.")

    if vix is not None:
        if vix >= 5:
            lines.append(f"Vol expanding: VIX {vix:+.2f}%.")
        elif vix <= -5:
            lines.append(f"Vol compressing: VIX {vix:+.2f}%.")
        else:
            last = by.get("VIX", {}).get("last")
            if last is not None:
                lines.append(f"VIX last {last:.2f} ({vix:+.2f}%).")

    if tnx is not None:
        last = by.get("TNX", {}).get("last")
        direction = "higher" if tnx > 0 else "lower"
        if abs(tnx) >= 1.5:
            lines.append(f"Rates moving {direction}: 10Y yield {tnx:+.2f}% (last {last}).")
        elif last is not None:
            lines.append(f"10Y yield near {last:.3f} ({tnx:+.2f}%).")

    if dxy is not None and abs(dxy) >= 0.4:
        lines.append(f"Dollar {('bid' if dxy>0 else 'off')}: DXY {dxy:+.2f}%.")

    # mega-cap movers
    movers = []
    for t in WATCH_EQUITY:
        p = pct(t)
        if p is not None and abs(p) >= 1.5:
            movers.append((t, p))
    movers.sort(key=lambda x: -abs(x[1]))
    if movers:
        bits = ", ".join(f"{t} {p:+.2f}%" for t, p in movers[:4])
        lines.append(f"Watchlist movers: {bits}.")

    if btc is not None or eth is not None:
        parts = []
        if btc is not None:
            parts.append(f"BTC {btc:+.2f}%")
        if eth is not None:
            parts.append(f"ETH {eth:+.2f}%")
        lines.append("Crypto: " + ", ".join(parts) + ".")

    # macro big moves
    series = ((macro_p or {}).get("data") or {}).get("series") or []
    big = [s for s in series if s.get("big_move")]
    if big:
        bits = []
        for s in big[:4]:
            bits.append(f"{s.get('label')} {s.get('latest')} (Δ {s.get('change'):+.3g})")
        lines.append("Macro flags: " + "; ".join(bits) + ".")

    # options skew
    chains = ((options_p or {}).get("data") or {}).get("chains") or []
    for c in chains:
        skew = (c.get("skew_25d") or {}).get("put_minus_call_iv")
        pc = c.get("put_call_oi_ratio")
        if skew is not None:
            tone = "put-heavy skew" if skew > 0.02 else ("call-heavy skew" if skew < -0.02 else "balanced 25Δ skew")
            lines.append(
                f"{c.get('symbol')} options ({c.get('expiry')}): {tone} "
                f"(put−call IV {skew:+.3f}; P/C OI {pc:.2f})." if pc else
                f"{c.get('symbol')} options ({c.get('expiry')}): {tone} (put−call IV {skew:+.3f})."
            )

    # filings pulse
    companies = ((filings_p or {}).get("data") or {}).get("companies") or []
    recent8 = []
    for co in companies:
        for f in co.get("filings") or []:
            if f.get("form") == "8-K" and f.get("filed"):
                recent8.append(f"{co['ticker']} 8-K {f['filed']}")
    if recent8:
        lines.append("Fresh 8-Ks: " + ", ".join(recent8[:5]) + ".")

    earn = ((news_p or {}).get("data") or {}).get("earnings") or []
    if earn:
        bits = [f"{e['ticker']} {e['date']}" + (f" {e['time']}" if e.get("time") else "") for e in earn[:6]]
        lines.append("Upcoming earnings (watchlist): " + ", ".join(bits) + ".")

    if not lines:
        lines.append("Insufficient live inputs to summarize — check panel errors.")

    lines.append("Ask Head Shlomo in chat for deeper answers.")
    return panel(True, {"bullets": lines, "generated": iso_pt()})


# ── Merge previous good data on failure ───────────────────────────────────

def merge_prev(new_snap: dict, prev_path: Path) -> dict:
    if not prev_path.exists():
        return new_snap
    try:
        prev = json.loads(prev_path.read_text())
    except Exception:
        return new_snap
    for key in ("quotes", "filings", "macro", "news", "options", "desk"):
        npanel = new_snap.get(key) or {}
        ppanel = prev.get(key) or {}
        if not npanel.get("ok") and ppanel.get("ok"):
            new_snap[key] = {
                **ppanel,
                "ok": False,
                "error": npanel.get("error") or "fetch failed; showing last good data",
                "stale": True,
                "stale_from": ppanel.get("fetched_at"),
                "fetched_at": npanel.get("fetched_at") or iso_pt(),
            }
        elif not npanel.get("ok") and ppanel.get("data") is not None and npanel.get("data") is None:
            new_snap[key] = {
                **npanel,
                "data": ppanel.get("data"),
                "stale": True,
                "stale_from": ppanel.get("fetched_at"),
            }
    return new_snap


def embed_plain(snapshot: dict):
    if not PLAIN_TEMPLATE.exists():
        return
    html = PLAIN_TEMPLATE.read_text()
    blob = json.dumps(snapshot, separators=(",", ":"))
    # escape for script safety
    blob = blob.replace("<", "\\u003c")
    if "/*__SNAPSHOT__*/" in html:
        html = html.replace("/*__SNAPSHOT__*/null", "/*__SNAPSHOT__*/" + blob, 1)
    else:
        # inject
        html = html.replace(
            "</body>",
            f"<script>window.TERMINAL_SNAPSHOT = {blob};</script></body>",
            1,
        )
    PLAIN_OUT.write_text(html)


def main():
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    print("terminal_fetch: start", iso_pt(), flush=True)

    quotes = fetch_quotes()
    print("  quotes", quotes["ok"], flush=True)
    filings = fetch_filings()
    print("  filings", filings["ok"], flush=True)
    macro = fetch_macro()
    print("  macro", macro["ok"], flush=True)
    news = fetch_news()
    print("  news", news["ok"], flush=True)
    options = fetch_options()
    print("  options", options["ok"], flush=True)
    desk = desk_summary(quotes, macro, news, options, filings)
    print("  desk", desk["ok"], flush=True)

    snap = {
        "version": 1,
        "generated_at": iso_pt(),
        "generated_at_epoch": int(time.time()),
        "timezone": "America/Los_Angeles",
        "watchlist": ALL_LABELS,
        "quotes": quotes,
        "filings": filings,
        "macro": macro,
        "news": news,
        "options": options,
        "desk": desk,
        "from_reference": {
            "note": "free_data chart endpoint pattern and free-data desk ethos from public writeup (helicerat0x); French factors not used on this wall.",
            "feed_chart": "https://query1.finance.free_data.com/v8/finance/chart/{SYMBOL}",
        },
    }
    snap = merge_prev(snap, OUT_JSON)
    OUT_JSON.write_text(json.dumps(snap, indent=2))
    embed_plain(snap)
    print("wrote", OUT_JSON, "bytes", OUT_JSON.stat().st_size, flush=True)
    if PLAIN_OUT.exists():
        print("wrote", PLAIN_OUT, "bytes", PLAIN_OUT.stat().st_size, flush=True)
    # panel status summary
    for k in ("quotes", "filings", "macro", "news", "options", "desk"):
        p = snap[k]
        print(f"  panel {k}: ok={p.get('ok')} err={p.get('error')!r} stale={p.get('stale')}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
