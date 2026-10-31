#!/usr/bin/env python3
"""Append one timestamped per-strike dealer-exposure snapshot (GEX/VEX/DEX/Charm)
for SPY + SPX from CBOE free delayed options JSON. Writes/merges into the GitHub Pages
data file the heatmap page reads. FREE sources only. Places no orders.

Usage:
  python3 /workspace/desk/orb-research/scripts/exposure_collector.py
  # optional: OUT=/path/to/snapshots.json MAX_SNAPS=400 BAND=0.05

Typical interval (you schedule): every 5–15 min during RTH.
"""
from __future__ import annotations
import json, math, os, re, sys, time, urllib.request
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, date, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

PT = ZoneInfo("America/Los_Angeles")
ET = ZoneInfo("America/New_York")
URL = "https://cdn.cboe.com/api/global/delayed_quotes/options/{}.json"
SYM = {"SPY": "SPY", "SPX": "_SPX"}
RX = re.compile(r"^([A-Z]+)(\d{6})([CP])(\d{8})$")
OUT = Path(os.environ.get(
    "OUT",
    "/workspace/orb-dash-site/exposure/data/snapshots.json",
))
MAX_SNAPS = int(os.environ.get("MAX_SNAPS", "400"))
BAND = float(os.environ.get("BAND", "0.06"))  # keep strikes within ±BAND of spot
R, Q = 0.05, 0.012  # BS rates for charm approx only


def fetch(ticker: str) -> dict:
    last = None
    for _ in range(3):
        try:
            req = urllib.request.Request(
                URL.format(SYM[ticker]),
                headers={"User-Agent": "Mozilla/5.0 (compatible; AttacheDesk/1.0)"},
            )
            return json.loads(urllib.request.urlopen(req, timeout=25).read())
        except Exception as ex:
            last = ex
            time.sleep(1.5)
    raise last


def norm_pdf(x: float) -> float:
    return math.exp(-0.5 * x * x) / math.sqrt(2 * math.pi)


def norm_cdf(x: float) -> float:
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2)))


def bs_charm(S: float, K: float, T: float, iv: float, cp: str) -> float:
    """Analytic BS charm (∂Δ/∂t, calendar-year). Approximation when feed has no charm."""
    if iv <= 0 or T <= 1e-8 or S <= 0 or K <= 0:
        return 0.0
    sig = iv
    sqrtT = math.sqrt(T)
    d1 = (math.log(S / K) + (R - Q + 0.5 * sig * sig) * T) / (sig * sqrtT)
    d2 = d1 - sig * sqrtT
    pdf = norm_pdf(d1)
    common = -pdf * (2 * (R - Q) * T - d2 * sig * sqrtT) / (2 * T * sig * sqrtT)
    if cp == "C":
        return common - (R - Q) * math.exp(-(R - Q) * T) * norm_cdf(d1)
    # put
    return common + (R - Q) * math.exp(-(R - Q) * T) * norm_cdf(-d1)


def year_frac(ex: date, now: datetime) -> float:
    close = datetime.combine(ex, datetime.min.time(), ET).replace(hour=16)
    return max((close - now).total_seconds(), 1800) / (365.0 * 86400)


def week_end(today: date) -> date:
    return today + timedelta((4 - today.weekday()) % 7)


def compute_symbol(ticker: str, raw: dict, now: datetime) -> dict:
    d = raw["data"]
    S = float(d["current_price"])
    today = now.astimezone(ET).date()
    fri = week_end(today)
    rows = []
    for o in d.get("options") or []:
        m = RX.match(o.get("option") or "")
        if not m:
            continue
        ex = datetime.strptime(m.group(2), "%y%m%d").date()
        if ex < today:
            continue
        K = int(m.group(4)) / 1000.0
        if K < S * (1 - BAND) or K > S * (1 + BAND):
            continue
        oi = float(o.get("open_interest") or 0)
        if oi <= 0:
            continue
        g = float(o.get("gamma") or 0)
        dl = float(o.get("delta") or 0)
        vg = float(o.get("vega") or 0)
        iv = float(o.get("iv") or 0)
        cp = m.group(3)
        T = year_frac(ex, now)
        sign = 1.0 if cp == "C" else -1.0
        # Dealer-convention exposures (customer long → dealer short; we report customer-signed
        # then flip sign for "dealer" view: calls +, puts − matches common GEX heatmap convention).
        gex = g * oi * 100.0 * S * S * 0.01 * sign
        vex = vg * oi * 100.0 * sign  # vega$ approx; vanna not in CBOE delayed feed
        dex = dl * oi * 100.0 * S  # delta dollars; put delta already negative
        ch = bs_charm(S, K, T, iv, cp) * oi * 100.0 * S * sign
        rows.append({"ex": ex, "K": K, "gex": gex, "vex": vex, "dex": dex, "charm": ch})

    def pack(sel_rows):
        by = {}
        for r in sel_rows:
            b = by.setdefault(r["K"], {"gex": 0.0, "vex": 0.0, "dex": 0.0, "charm": 0.0})
            for k in ("gex", "vex", "dex", "charm"):
                b[k] += r[k]
        strikes = sorted(by)
        def rnd(xs):
            return [round(x, 2) for x in xs]
        return {
            "strikes": strikes,
            "gex": rnd([by[k]["gex"] for k in strikes]),
            "vex": rnd([by[k]["vex"] for k in strikes]),
            "dex": rnd([by[k]["dex"] for k in strikes]),
            "charm": rnd([by[k]["charm"] for k in strikes]),
        }

    all_rows = rows
    week_rows = [r for r in rows if r["ex"] <= fri]
    dte0_rows = [r for r in rows if r["ex"] == today]
    # If no true 0DTE (weekend / after last expiry rolled), use nearest expiry
    if not dte0_rows and rows:
        nearest = min(r["ex"] for r in rows)
        dte0_rows = [r for r in rows if r["ex"] == nearest]

    return {
        "spot": round(S, 4),
        "src_ts_utc": raw.get("timestamp"),
        "filters": {
            "all": pack(all_rows),
            "week": pack(week_rows),
            "0dte": pack(dte0_rows),
        },
    }


def load_out(path: Path) -> dict:
    if path.exists():
        try:
            return json.loads(path.read_text())
        except Exception:
            pass
    return {
        "meta": {
            "source": "CBOE delayed options",
            "delay": "~15-min delayed",
            "note": "GEX=γ·OI·100·S²·0.01 (C+,P−); VEX≈ν·OI·100 (C+,P−); DEX=Δ·OI·100·S; Charm≈BS ∂Δ/∂t·OI·100·S (C+,P−). Vanna not in feed.",
        },
        "snapshots": [],
    }


def main() -> int:
    now = datetime.now(timezone.utc)
    out = load_out(OUT)
    err = {}
    ok = {}
    with ThreadPoolExecutor(max_workers=2) as pool:
        futs = {t: pool.submit(fetch, t) for t in SYM}
        for t, fut in futs.items():
            try:
                ok[t] = compute_symbol(t, fut.result(), now)
            except Exception as ex:
                err[t] = str(ex)[:200]
    if not ok:
        print("exposure_collector: no data", err, file=sys.stderr)
        return 1
    snap = {
        "ts": now.astimezone(PT).isoformat(timespec="seconds"),
        "ts_utc": now.isoformat(timespec="seconds"),
        "symbols": ok,
        "err": err,
    }
    snaps = list(out.get("snapshots") or [])
    snaps.append(snap)
    if len(snaps) > MAX_SNAPS:
        snaps = snaps[-MAX_SNAPS:]
    out["snapshots"] = snaps
    out["meta"] = {
        **(out.get("meta") or {}),
        "source": "CBOE delayed options",
        "delay": "~15-min delayed",
        "updated_pt": now.astimezone(PT).strftime("%Y-%m-%d %H:%M PT"),
        "n_snapshots": len(snaps),
        "note": "GEX=γ·OI·100·S²·0.01 (C+,P−); VEX≈ν·OI·100 (C+,P−, vega$); DEX=Δ·OI·100·S; Charm≈BS ∂Δ/∂t·OI·100·S (C+,P−). No vanna in CBOE delayed feed.",
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    tmp = OUT.with_suffix(".tmp")
    tmp.write_text(json.dumps(out, separators=(",", ":")))
    tmp.replace(OUT)
    sizes = {t: {f: len(ok[t]["filters"][f]["strikes"]) for f in ok[t]["filters"]} for t in ok}
    print("exposure_collector ok", out["meta"]["updated_pt"], "spots", {t: ok[t]["spot"] for t in ok}, "strikes", sizes, "err", err)
    return 0


if __name__ == "__main__":
    sys.exit(main())
