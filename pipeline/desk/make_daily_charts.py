#!/usr/bin/env python3
"""ATTACHÉ DAILY + WEEKLY PLAN vs ACTUAL charts.
Weekly layout + actual 30m overlay. Prior-week amber; plan-week past days white;
event/today cyan. Free free_data 30m (cleaned of seam/garbage-wick artifacts).
Plan paths drawn ONLY on day columns with no actual bars (Everett: lines off candles).
Level / zone fills stay; FOMC/event marker = edge ticks only.
Archives under daily/charts/YYYY-MM-DD/. Also writes weekly/charts/ (+ prior/ + plan/).
Fails loudly if any chart cannot build (no silent stale PNGs).
"""
import os, sys, shutil, datetime as dt, json, urllib.request
from collections import Counter
from pathlib import Path
import matplotlib; matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd
from zoneinfo import ZoneInfo

PT = ZoneInfo("America/Los_Angeles")
HERE = Path(__file__).resolve().parent
SITE = HERE
OUT = str(SITE / "daily" / "charts")
os.makedirs(OUT, exist_ok=True)

R, S, P = "#ff6b6b", "#4ade80", "#ffb000"
TODAY_UP, TODAY_DN = "#22d3ee", "#0891b2"
ACTUAL_UP, ACTUAL_DN = "#f5f5f5", "#b0b0b0"
BULL_ZONE_C, BEAR_ZONE_C = "#4ade80", "#ff6b6b"
COL = {"R": R, "S": S, "P": P}

# SPY Dark Pool levels (purple edge ticks only — no lines through candles)
def _load_dp():
    """Return SPY dark-pool prices as floats.

    data/spy_dark_pool.json stores objects {{"spy": float, ...}};
    es_levels/darkpool_levels.json stores bare floats. Chart code needs floats.
    """
    import json
    from pathlib import Path as _P
    for cand in (_P(__file__).resolve().parent.parent.parent / "data" / "spy_dark_pool.json",
                 _P(__file__).resolve().parent / "es_levels" / "darkpool_levels.json"):
        if not cand.exists():
            continue
        d = json.loads(cand.read_text())
        out = []
        for lv in (d.get("levels") or []):
            if isinstance(lv, (int, float)):
                out.append(float(lv))
            elif isinstance(lv, dict) and lv.get("spy") is not None:
                out.append(float(lv["spy"]))
            else:
                raise TypeError(f"dark-pool level must be float or {{'spy': float}}, got {type(lv).__name__}: {lv!r}")
        return out
    return []
DARK_POOL_SPY = _load_dp()
DP_COLOR = "#c084fc"
def _load_dp_convert():
    """SPY->SPX factor and ES-SPX basis from data/spy_dark_pool.json (same numbers as the Dark Pool tables)."""
    import json
    from pathlib import Path as _P
    f = _P(__file__).resolve().parent.parent.parent / "data" / "spy_dark_pool.json"
    c = json.loads(f.read_text()).get("convert", {}) if f.exists() else {}
    return float(c.get("spy_per_spx", 0.0997)), float(c.get("es_minus_spx", 34.5))
SPY_PER_SPX, ES_MINUS_SPX = _load_dp_convert()

# ── Week of Nov 23 (last week) — PLAN vs ACTUAL (Friday's plan levels as published Thu 11/26) ──
PRIOR_WEEK = [dt.date(2026, 11, 23), dt.date(2026, 11, 24), dt.date(2026, 11, 25),
              dt.date(2026, 11, 27)]
PRIOR_ZONES = {
  "spy": {"bull": (718.0, 727.98), "bear": (695.45, 686.75),
          "bull_lab": "over 718 call wall → Monday high 727.98", "bear_lab": "below 695.45 → 686.75 Friday 11/20 low"},
  "es":  {"bull": (7211.0, 7305.0), "bear": (6982.0, 6898.0),
          "bull_lab": "reclaim 7211–23 → 7240, 7272–78, then 7305–09", "bear_lab": "lose 7160–65, then 6982–93 → 6897"},
  "qqq": None,
  "nq":  None,
}
PRIOR_SPEC = {
 "es": dict(sym="ES=F", title="/ES  ·  week of Nov 23 (plan vs actual · Fri plan levels)", fut=True, lv=[
   (7305,"R","7305–09 control · Mon high 7313"),(7277,"R","7272–78"),(7240,"R","7240–45 Tue high"),
   (7217,"R","7211–23 · Wed high 7214"),(7163,"S","7160–65"),
   (7122,"S","7120–25"),(7086,"S","7086"),(7027,"S","7025–29"),
   (6982,"S","6982–93 Wed low / Sunday FB"),(6963,"P","6960–66 unused pivot"),(6898,"S","6897–98 Fri 11/20 low"),(6846,"S","6841–51")],
   zones=[], bull=[7217,7240,7277,7305], bear=[7163,6982,6963,6898]),
 "nq": dict(sym="NQ=F", title="/NQ  ·  week of Nov 23 (levels · no paths)", fut=True, lv=[
   (27137,"R","27137 Mon high"),(26509.75,"R","26510 Tue high"),
   (25027.5,"S","25027 Wed low"),(24976.5,"S","24976.5 Fri 11/20 low")],
   zones=[], bull=[], bear=[]),
 "spy": dict(sym="SPY", title="SPY  ·  week of Nov 23 (plan vs actual · Fri plan levels)", fut=False, lv=[
   (727.98,"R","727.98 Mon high"),(721.5,"R","721.5 Friday flip"),(718.66,"R","718.66 dark-pool line"),
   (718,"R","718 Friday call wall"),(716.70,"P","716.70 Wed close"),
   (715.02,"S","715.02 dark-pool line"),(700,"S","700 put wall"),(695.45,"S","695.45 Wed low"),(686.75,"S","686.75 Fri 11/20 low")],
   zones=[], bull=[716.70,718,727.98], bear=[716.70,700,686.75]),
 "qqq": dict(sym="QQQ", title="QQQ  ·  week of Nov 23 (levels · no paths)", fut=False, lv=[
   (657.53,"R","657.53 Mon high"),(650,"R","650 Friday call wall"),(647.7,"R","647.7 Friday flip"),
   (640,"R","640 biggest strike"),(633.93,"P","633.93 Wed close"),
   (607.76,"S","607.76 Wed low"),(606.23,"S","606.23 Fri 11/20 low")],
   zones=[], bull=[], bear=[]),
}
PRIOR_EVENT = {  # Wed: PCE · GDP · claims 5:30 AM PT — edge ticks only
  "day": dt.date(2026, 11, 25),
  "label": "PCE · GDP · claims Wed 5:30 AM PT",
  "frac_fut": 0.6, "frac_cash": 0.05,
}
PRIOR_DAY_NOTES = {
  0: "7313 tag",
  1: "Conf Bd",
  2: "PCE·GDP",
  3: "½ day",
}


# ── Week of Nov 30 (this week: month-end Monday, jobs report Friday) — forward PLAN ──
# Sourced levels only (weekly plan + Mon Daily pivot). Paths start at the Mon pivot and move forward only.
PLAN_WEEK_FWD = [dt.date(2026, 11, 30), dt.date(2026, 12, 1), dt.date(2026, 12, 2),
                 dt.date(2026, 12, 3), dt.date(2026, 12, 4)]
FWD_ZONES = {
  "spy": {"bull": (730.0, 737.3), "bear": (724.0, 719.62),
          "bull_lab": "over 730 call wall / 730.98 200-day → 737.3 Monday flip", "bear_lab": "below 724 put wall → 720 / 719.62 Friday low"},
  "es":  {"bull": (7321.0, 7408.0), "bear": (7287.0, 7242.0),
          "bull_lab": "hold 7305–09 → 7320–23, 7334, 7362–65, then 7405–12", "bear_lab": "lose 7305–09 → 7286, 7272–78, 7250–52, then 7240–45"},
  "qqq": None,
  "nq":  None,
}
FWD_SPEC = {
 "es": dict(sym="ES=F", title="/ES  ·  week of Nov 30 (Fri 11/27 close · 1:15 PM PT)", fut=True, lv=[
   (7408,"R","7405–12 gateway · SPX 7400 ≈ 7411.75"),(7363,"R","7362–65"),(7352,"R","7352 Monday flip ≈"),(7334,"R","7334 · SPY 200-day ≈"),
   (7321,"R","7320–23 Friday high"),(7307,"P","7305–09 control line"),(7287,"S","7286–87 Monday put wall ≈"),
   (7275,"S","7272–78"),(7251,"S","7250–52 swept / reclaimed"),(7242,"S","7240–45"),(7217,"S","7211–23 Friday low 7222.75"),(7163,"S","7160–65")],
   zones=[], bull=[7307,7321,7334,7363,7408], bear=[7307,7287,7275,7251,7242]),
 "nq": dict(sym="NQ=F", title="/NQ  ·  week of Nov 30 (levels · no paths)", fut=True, lv=[
   (26816,"R","26816 Friday high"),(26765,"P","26765 Friday close"),(26208.5,"S","26208.5 Friday low"),(25027.5,"S","25027 Wed low")],
   zones=[], bull=[], bear=[]),
 "spy": dict(sym="SPY", title="SPY  ·  week of Nov 30 (Fri 11/27 close · 1:15 PM PT)", fut=False, lv=[
   (737.3,"R","737.3 Monday flip"),(732.5,"R","732.5 week flip"),(731.85,"R","731.85 dark-pool line"),(730.98,"R","730.98 200-day"),
   (730,"R","730 call wall"),(729.26,"R","729.26 dark-pool line"),(728.32,"P","728.32 Fri close"),
   (727.83,"S","727.83 dark-pool line"),(724,"S","724 Monday put wall"),(720,"S","720 week put wall"),(719.62,"S","719.62 Fri low"),(718.66,"S","718.66")],
   zones=[], bull=[728.32,730,732.5,737.3], bear=[728.32,724,720,718.66]),
 "qqq": dict(sym="QQQ", title="QQQ  ·  week of Nov 30 (levels · no paths)", fut=False, lv=[
   (670,"R","670 week call wall"),(661.7,"R","661.7 all-dates flip"),(657.53,"R","657.53 last Mon high"),(651.7,"R","651.7 Monday flip"),
   (650,"P","650 call wall / biggest"),(640,"S","640 Monday put wall"),(636.72,"S","636.72 Fri low"),(630,"S","630 week put wall")],
   zones=[], bull=[], bear=[]),
}
FWD_EVENT = {  # Fri: jobs report 5:30 AM PT — edge ticks only
  "day": dt.date(2026, 12, 4),
  "label": "Jobs report Fri 5:30 AM PT",
  "frac_fut": 0.6, "frac_cash": 0.05,
}
FWD_DAY_NOTES = {
  0: "month-end",
  1: "ISM·JOLTS",
  2: "ADP",
  3: "ISM svcs",
  4: "NFP",
}
FWD_BOX = ["bias: lean bullish while 7305–09 holds · 7320–23 / 7334 first upside · 7272–78 / 7250–52 below",
           "catalysts: Mon month-end · Tue ISM · JOLTS · Wed ADP · Thu ISM services · Fri jobs report 5:30 AM PT"]

def _download(sym):
    """Free free_data 30m with extended hours; clean seam/garbage-wick artifacts."""
    u = (f"https://query1.finance.yahoo.com/v8/finance/chart/{sym}"
         f"?interval=30m&range=15d&includePrePost=true")
    req = urllib.request.Request(u, headers={"User-Agent": "Mozilla/5.0"})
    d = json.loads(urllib.request.urlopen(req, timeout=30).read())
    r = d["chart"]["result"][0]
    ts = r["timestamp"]; q = r["indicators"]["quote"][0]
    rows = []
    for i, t in enumerate(ts):
        if q["close"][i] is None:
            continue
        o, h, l, c = q["open"][i], q["high"][i], q["low"][i], q["close"][i]
        if o is None or h is None or l is None:
            continue
        if o <= 0 or h <= 0 or l <= 0 or c <= 0:
            continue
        rows.append((pd.Timestamp(t, unit="s", tz="UTC").tz_convert(PT), o, h, l, c))
    df = pd.DataFrame(rows, columns=["t", "Open", "High", "Low", "Close"]).set_index("t")
    if df.empty:
        raise RuntimeError("no bars")
    return _clean_bars(df.dropna())


def _clean_bars(df):
    """Root-cause fix for the Friday full-height glitch wick.

    free_data 30m sometimes emits a session-seam bar (esp. futures around cash settle)
    with Open=High=previousClose and Low near the true session low — a vertical
    spike through the whole chart. Also stamps garbage extended-hours Lows far
    below the body while O/H/C stay real (SPY AH). Drop / repair those here so
    nothing downstream draws the stray line.
    """
    if df.empty or len(df) < 5:
        return df
    df = df.copy()
    rng = (df.High - df.Low).astype(float)
    med = float(rng.median())
    if not med or med != med:
        return df
    rmed = rng.rolling(24, min_periods=6).median().fillna(med)
    body_lo = df[["Open", "Close"]].min(axis=1)
    body_hi = df[["Open", "Close"]].max(axis=1)
    lower = body_lo - df.Low
    upper = df.High - body_hi
    prev_c = df.Close.shift(1)
    open_jump = (df.Open - prev_c).abs()

    # Wick clamps are for extended-hours / seam artifacts only.
    # Never rewrite a regular-session high or low (Wed 11/25 6:45 AM PT ES 6982.50
    # is a real flush, not a garbage wick).
    mins = df.index.hour * 60 + df.index.minute
    rth = (mins >= 6 * 60 + 30) & (mins < 13 * 60)

    # Garbage AH/reference low: huge lower wick, almost no upper wick
    bad_low = (~rth) & (lower > 3.5 * rmed) & (lower > 6 * (upper + 1e-9))
    # Session-seam / settle spike: open jumps to prior close area, range enormous
    bad_seam = prev_c.notna() & (open_jump > 5 * rmed) & (rng > 6 * rmed)
    # Classic free_data artifact: Open==High far above Close with huge range
    bad_settle = (df.Open == df.High) & ((df.Open - df.Close).abs() > 5 * rmed) & (rng > 6 * rmed)

    # Garbage print on both sides (e.g. SPY after-hours bar 746.69 / 691.53 around a 735-736 body):
    # range > 10x local median with both wicks huge -> clamp the wicks to the body.
    bad_both = (~rth) & (rng > 10 * rmed) & (lower > 3.5 * rmed) & (upper > 3.5 * rmed)
    if bad_both.any():
        df.loc[bad_both, "Low"] = body_lo[bad_both]
        df.loc[bad_both, "High"] = body_hi[bad_both]
    # Mirror of bad_low: garbage high far above the body with almost no lower wick
    bad_high = (~rth) & (upper > 3.5 * rmed) & (upper > 6 * (lower + 1e-9)) & (rng > 10 * rmed)
    if bad_high.any():
        df.loc[bad_high, "High"] = body_hi[bad_high]
    # Garbage extended-hours low under a real after-hours high (e.g. SPY 11/17 AH bar 734.27/739.73/713.10/732.80):
    # the lower wick is far beyond the local range and well over twice the upper wick -> clamp the low to the body.
    bad_low2 = (~rth) & (lower > 8 * rmed) & (lower > 2 * upper) & ~bad_both
    bad_low = bad_low | bad_low2
    n_repair = int((bad_low | bad_both | bad_high).sum())
    n_drop = int((bad_seam | bad_settle).sum())
    if n_repair:
        df.loc[bad_low, "Low"] = body_lo[bad_low]
    drop = bad_seam | bad_settle
    if drop.any():
        df = df.loc[~drop]
    if n_repair or n_drop:
        print(f"  clean_bars: repaired {n_repair} garbage lows, dropped {n_drop} seam/settle spikes")
    return df


def _scorecard(actual_df, key, sp, zones, event_day):
    z = zones[key]
    b_lo, b_hi = z["bull"]
    e_hi, e_lo = z["bear"]
    if actual_df is None or actual_df.empty:
        return None
    hi = float(actual_df.High.max())
    lo = float(actual_df.Low.min())
    last = float(actual_df.Close.iloc[-1])
    p1 = "HIT" if hi >= b_lo else "MISSED"
    p2 = "HIT" if lo <= e_hi else "MISSED"
    # per-day summary
    days = []
    for d, g in actual_df.groupby(actual_df.index.date):
        days.append({
            "date": d.isoformat(),
            "hi": round(float(g.High.max()), 2),
            "lo": round(float(g.Low.min()), 2),
            "last": round(float(g.Close.iloc[-1]), 2),
            "event": (d == event_day),
        })
    bull_hit = sum(1 for y in sp["bull"] if hi >= y)
    bear_hit = sum(1 for y in sp["bear"] if lo <= y)
    path = ("BULL" if bull_hit > bear_hit and bull_hit > 0
            else ("BEAR" if bear_hit > bull_hit and bear_hit > 0 else "CHOP / MIXED"))
    return dict(high=hi, low=lo, last=last, path=path,
                phase1=p1, phase1_zone=list(z["bull"]), phase1_high=hi,
                phase2=p2, phase2_zone=list(z["bear"]),
                days=days, n_bars=len(actual_df))



def _place_edge_labels(ax, labels, *, xe, D, lo, hi):
    """Right-edge labels: merge near-dupes, drop levels inside zones, min-gap + leaders."""
    if not labels:
        return
    rng = max(hi - lo, 1e-9)
    merge_eps = rng * 0.022  # ~2.2% of range — merge 7665/7677-class neighbors
    min_gap = rng * 0.052    # comfortable monospace line height

    items = sorted(labels, key=lambda d: -d["y"])

    # Zone bands (for swallowing levels that sit inside)
    zone_bands = []
    for lab in items:
        if "tick_a" in lab and "tick_b" in lab:
            zone_bands.append((min(lab["tick_a"], lab["tick_b"]) - merge_eps,
                               max(lab["tick_a"], lab["tick_b"]) + merge_eps,
                               lab))
    filtered = []
    for lab in items:
        if lab.get("kind") == "lv":
            if any(a <= lab["y"] <= b for a, b, _ in zone_bands):
                continue
        filtered.append(lab)
    items = filtered

    def _band(lab):
        if "tick_a" in lab and "tick_b" in lab:
            return min(lab["tick_a"], lab["tick_b"]), max(lab["tick_a"], lab["tick_b"])
        return lab["y"], lab["y"]

    def _bands_overlap(a, b):
        a0, a1 = _band(a); b0, b1 = _band(b)
        a_thin = (a1 - a0) < 1e-9
        b_thin = (b1 - b0) < 1e-9
        # Thin vs thin: only merge if midpoints within merge_eps (no double-expand).
        if a_thin and b_thin:
            return abs(a["y"] - b["y"]) <= merge_eps
        # Thin vs zone: expand the thin side so a level inside/near a zone merges.
        if a_thin:
            a0 -= merge_eps; a1 += merge_eps
        if b_thin:
            b0 -= merge_eps; b1 += merge_eps
        return not (a1 < b0 or b1 < a0)

    def _merge_text(prev, lab):
        a, b = prev["text"].strip(), lab["text"].strip()
        score = lambda s: (sum(ch.isdigit() for ch in s), len(s))
        if score(b) > score(a):
            # Keep a short price tag from the loser so 7626 doesn't vanish under 7616.
            loser = a
            prev["text"] = lab["text"]; prev["color"] = lab["color"]
            if "tick_k" in lab: prev["tick_k"] = lab["tick_k"]
            # extract leading price token from loser
            tok = loser.split()[0] if loser.split() else ""
            if tok and tok[0].isdigit() and tok not in prev["text"]:
                prev["text"] = prev["text"].rstrip() + f" · {tok}"
        elif b.lower() not in a.lower() and a.lower() not in b.lower():
            # keep the more specific (has numbers) as primary; append other tag
            tag = b if score(a) >= score(b) else a
            primary = a if score(a) >= score(b) else b
            # strip shared tokens from tag
            for tok in primary.replace("–", " ").replace("-", " ").split():
                if len(tok) > 1:
                    tag = tag.replace(tok, "")
            tag = " ".join(tag.split())
            if tag:
                prev["text"] = " " + primary + " · " + tag
                if score(b) > score(a):
                    prev["color"] = lab["color"]
        # union bands
        if "tick_a" in lab or "tick_a" in prev:
            a0, a1 = _band(prev); b0, b1 = _band(lab)
            prev["tick_a"], prev["tick_b"] = min(a0, b0), max(a1, b1)
            prev["y"] = (prev["tick_a"] + prev["tick_b"]) / 2
        else:
            prev["y"] = (prev["y"] + lab["y"]) / 2

    # Merge near-duplicate OR overlapping-band labels
    merged = []
    for lab in items:
        hit = None
        for prev in merged:
            if abs(prev["y"] - lab["y"]) <= merge_eps or _bands_overlap(prev, lab):
                hit = prev; break
        if hit is not None:
            _merge_text(hit, lab)
            continue
        merged.append(dict(lab))
    # Cap merged label width so a dense cluster can't squeeze the plot (keep the first tokens).
    for m in merged:
        t = m["text"]
        if len(t) > 64:
            cut = t[:64].rsplit(" · ", 1)[0]
            m["text"] = cut + " · …"

    margin = rng * 0.025
    y_bot, y_top = lo + margin, hi - margin
    placed = []
    for m in merged:
        true = float(m["y"])
        placed.append({**m, "true": true, "y": min(max(true, y_bot), y_top)})

    # Sort low→high; two-pass separation; if overflow, even pack biased to true
    placed.sort(key=lambda d: d["true"])
    n = len(placed)
    if n == 0:
        return
    ys = [p["y"] for p in placed]
    for i in range(1, n):
        ys[i] = max(ys[i], ys[i - 1] + min_gap)
    for i in range(n - 2, -1, -1):
        ys[i] = min(ys[i], ys[i + 1] - min_gap)
    # If packed outside [y_bot, y_top], evenly distribute
    if ys[0] < y_bot - 1e-9 or ys[-1] > y_top + 1e-9 or (n > 1 and (ys[-1] - ys[0]) < (n - 1) * min_gap - 1e-9):
        span = y_top - y_bot
        need = (n - 1) * min_gap
        if need <= span or n == 1:
            # place with gaps, anchored so mean(true) ≈ mean(ys)
            base = [y_bot + i * min_gap for i in range(n)]
            # shift pack to minimize distance to true, clamped
            ideal_shift = sum(p["true"] - base[i] for i, p in enumerate(placed)) / n
            lo_shift = y_bot - base[0]
            hi_shift = y_top - base[-1]
            shift = min(max(ideal_shift, lo_shift), hi_shift)
            ys = [b + shift for b in base]
        else:
            # too many labels — equal spacing across full span
            ys = [y_bot + span * (i / (n - 1)) for i in range(n)]
    for i, p in enumerate(placed):
        p["y"] = ys[i]

    tick_x0 = xe - D * 0.18
    for p in placed:
        true_y, lab_y = p["true"], p["y"]
        col = p["color"]
        ax.plot([tick_x0, xe], [true_y, true_y], color=col,
                lw=1.25 if p.get("tick_k") == "P" else 0.85,
                solid_capstyle="butt", zorder=2, alpha=0.95)
        if abs(lab_y - true_y) > rng * 0.006:
            ax.plot([xe, xe + D * 0.10], [true_y, lab_y], color=col, lw=0.7,
                    alpha=0.8, solid_capstyle="round", zorder=3)
            tx = xe + D * 0.10
        else:
            tx = xe
        ax.text(tx, lab_y, p["text"], color=col,
                fontsize=7.0 if not p.get("bold") else 7.4,
                va="center", ha="left", family="monospace",
                weight="bold" if p.get("bold") else "normal", zorder=4,
                clip_on=False)



def chart(key, sp, plan_week, zones, event, out_path, day_notes=None,
          mode="actual", box_title=None, frozen_sc=None):
    raw = _download(sp["sym"])
    plan_start, plan_end = plan_week[0], plan_week[-1]
    event_day = event["day"]

    hist = raw[raw.index.date < plan_start]
    if not hist.empty:
        days = sorted(set(hist.index.date))
        keep_n = 5 if sp["fut"] else 4
        keep = days[-keep_n:]
        hist = hist[[d in keep for d in hist.index.date]]
    if hist.empty:
        hist = raw.iloc[:1]

    actual = raw[(raw.index.date >= plan_start) & (raw.index.date <= plan_end)]
    if not sp["fut"] and not actual.empty:
        # Premarket always dropped. Keep RTH + after-hours on every plan-week day
        # so evening-session updates show on THIS WEEK · PLAN (and daily scorecards).
        mask = []
        for ts in actual.index:
            hm = ts.hour * 60 + ts.minute
            if hm < 6 * 60 + 30:
                mask.append(False)
            else:
                mask.append(True)
        actual = actual.loc[mask]

    n = len(hist)
    D = 26 if sp["fut"] else 16
    fig, ax = plt.subplots(figsize=(11, 6.2), dpi=110)
    fig.patch.set_facecolor("#0b0b0d"); ax.set_facecolor("#111114")

    for i, (o, h, l, c) in enumerate(zip(hist.Open, hist.High, hist.Low, hist.Close)):
        col = "#ffb000" if c >= o else "#8a5a00"
        ax.vlines(i, l, h, color=col, lw=0.8)
        ax.add_patch(plt.Rectangle((i - 0.35, min(o, c)), 0.7, max(abs(c - o), 1e-6), color=col))

    last = float(hist.Close.iloc[-1])
    x0 = n - 1
    ND = len(plan_week)  # trading days in the plan week (holiday weeks have fewer columns)
    xe = n + ND * D

    z = zones.get(key)  # None = no verified map this week: candles only
    ys = list(hist.Low) + list(hist.High) + list(sp["bull"]) + list(sp["bear"])
    if z:
        ys += [z["bull"][0], z["bull"][1], z["bear"][0], z["bear"][1]]
    if not actual.empty:
        ys += list(actual.Low) + list(actual.High)
    lo, hi = min(ys), max(ys)
    pad = (hi - lo) * 0.06
    lo -= pad; hi += pad

    # Zones (fills only — labels go through collision placer below)
    if z:
        ax.fill_between([-1, xe], z["bull"][0], z["bull"][1], color=BULL_ZONE_C, alpha=0.18, lw=0, zorder=1)
        ax.fill_between([-1, xe], min(z["bear"]), max(z["bear"]), color=BEAR_ZONE_C, alpha=0.18, lw=0, zorder=1)
    for a, b, k_, _t in sp["zones"]:
        ax.fill_between([-1, xe], a, b, color=COL[k_], alpha=0.10, lw=0)

    # Collect right-edge labels (primary bull/bear as bands + SPEC zones + levels).
    edge_labels = []
    if z:
      b0, b1 = z["bull"][0], z["bull"][1]
      e0, e1 = min(z["bear"]), max(z["bear"])
      edge_labels.append({
        "y": (b0 + b1) / 2, "color": BULL_ZONE_C,
        "text": f" {min(b0,b1):g}–{max(b0,b1):g} {z.get('bull_lab', 'bull zone')}",
        "bold": True, "kind": "zone", "tick_a": b0, "tick_b": b1, "tick_k": "S",
      })
      edge_labels.append({
        "y": (e0 + e1) / 2, "color": BEAR_ZONE_C,
        "text": f" {e0:g}–{e1:g} {z.get('bear_lab', 'bear zone')}",
        "bold": True, "kind": "zone", "tick_a": e0, "tick_b": e1, "tick_k": "R",
      })
    for a, b, k_, lab in sp["zones"]:
        edge_labels.append({
            "y": (a + b) / 2, "color": COL[k_],
            "text": f" {a:g}–{b:g} {lab}", "bold": True, "kind": "zone",
            "tick_a": a, "tick_b": b, "tick_k": k_,
        })
    for y, k_, lab in sp["lv"]:
        if lo <= y <= hi:
            edge_labels.append({
                "y": float(y), "color": COL[k_],
                "text": f" {y:g} {lab}", "bold": False, "kind": "lv", "tick_k": k_,
            })
    # Dark Pool: purple right-edge ticks only (no full-width lines through candles)
    if key == "spy":
        for y in DARK_POOL_SPY:
            if lo <= y <= hi:
                edge_labels.append({
                    "y": float(y), "color": DP_COLOR,
                    "text": f" {y:g} Dark Pool", "bold": False, "kind": "lv", "tick_k": "P",
                })
    elif key == "es":
        for spy in DARK_POOL_SPY:
            y = round(spy / SPY_PER_SPX + ES_MINUS_SPX, 2)
            if lo <= y <= hi:
                edge_labels.append({
                    "y": float(y), "color": DP_COLOR,
                    "text": f" {y:g} Dark Pool", "bold": False, "kind": "lv", "tick_k": "P",
                })
    _place_edge_labels(ax, edge_labels, xe=xe, D=D, lo=lo, hi=hi)

    # Day columns
    ax.axvline(n - 0.5, color="#555", lw=0.8)
    day_names = [d.strftime("%a").upper() for d in plan_week]
    for i, dname in enumerate(day_names):
        ax.axvline(n + i * D, color="#2a2a2e", lw=0.7)
        note = (day_notes or {}).get(i, "")
        label = dname if not note else f"{dname}\n{note}"
        ax.text(n + i * D + D / 2, hi, label, color="#9a8a60", fontsize=7.5 if note else 8,
                ha="center", va="top", family="monospace")

    # Event marker — edge ticks only (never a full-height line through candles)
    if event_day in plan_week:
        di = plan_week.index(event_day)
        frac = event["frac_fut"] if sp["fut"] else event["frac_cash"]
        xf = n + di * D + frac * D
        tick = (hi - lo) * 0.035
        ax.plot([xf, xf], [hi - tick, hi], color="#c084fc", lw=1.6, solid_capstyle="butt",
                clip_on=False, zorder=8)
        ax.plot([xf, xf], [lo, lo + tick], color="#c084fc", lw=1.6, solid_capstyle="butt",
                clip_on=False, zorder=8)
        ax.text(xf, hi + (hi - lo) * 0.012, event["label"], color="#c084fc", fontsize=8,
                ha="center", va="bottom", family="monospace", clip_on=False)

    # Actual candles + per-day labels
    by_day = {i: [] for i in range(ND)}
    if not actual.empty:
        for ts, row in actual.iterrows():
            d = ts.date()
            if d not in plan_week:
                continue
            by_day[plan_week.index(d)].append((ts, row))

    days_with_actual = set()
    for di, rows in by_day.items():
        if not rows:
            continue
        days_with_actual.add(di)
        is_event = plan_week[di] == event_day
        for j, (ts, row) in enumerate(rows):
            x = n + di * D + (j + 0.5) * (D / max(len(rows), 1))
            o, h, l, c = float(row.Open), float(row.High), float(row.Low), float(row.Close)
            if is_event:
                col = TODAY_UP if c >= o else TODAY_DN
            else:
                col = ACTUAL_UP if c >= o else ACTUAL_DN
            w = max(0.35, 0.7 * (D / max(len(rows), 1)) * 0.85)
            ax.vlines(x, l, h, color=col, lw=0.9, zorder=5)
            ax.add_patch(plt.Rectangle((x - w / 2, min(o, c)), w, max(abs(c - o), 1e-6),
                                       color=col, ec="#ffffff" if not is_event else TODAY_UP,
                                       lw=0.35, zorder=5))
        # Day hi / lo / close label (clean, above or below the day's range)
        day_hi = max(float(r.High) for _, r in rows)
        day_lo = min(float(r.Low) for _, r in rows)
        day_last = float(rows[-1][1].Close)
        x_mid = n + di * D + D / 2
        tag = f"{day_names[di]} hi {day_hi:g}  lo {day_lo:g}  c {day_last:g}"
        # Park day stats at the floor of the plot, staggered slightly per day so
        # neighboring boxes never stack on top of each other.
        y_lab = lo + (hi - lo) * (0.012 + 0.018 * (di % 2))
        ax.text(x_mid, y_lab, tag, color="#c8c0a8", fontsize=6.0, ha="center", va="bottom",
                family="monospace", zorder=6,
                bbox=dict(boxstyle="round,pad=0.12", fc="#0b0b0d", ec="#333", alpha=0.88))

        if is_event and rows:
            day_df = pd.DataFrame(
                [{"Open": r.Open, "High": r.High, "Low": r.Low, "Close": r.Close} for _, r in rows],
                index=[t for t, _ in rows])
            hi_row = day_df.High.idxmax()
            hi_px = float(day_df.High.max())
            last_px = float(day_df.Close.iloc[-1])
            j_hi = list(day_df.index).index(hi_row)
            x_hi = n + di * D + (j_hi + 0.5) * (D / max(len(rows), 1))
            ax.annotate(f"session high {hi_px:g}", xy=(x_hi, hi_px),
                        xytext=(x_hi + 1.2, hi_px + (hi - lo) * 0.03),
                        color=TODAY_UP, fontsize=7, family="monospace",
                        arrowprops=dict(arrowstyle="->", color=TODAY_UP, lw=0.8))
        # Friday selloff callout on last day with actuals if down hard
        if di == 4 and rows:
            day_hi = max(float(r.High) for _, r in rows)
            day_lo = min(float(r.Low) for _, r in rows)
            day_last = float(rows[-1][1].Close)
            if day_last < day_hi - (hi - lo) * 0.08:
                ax.annotate(f"Fri selloff → {day_last:g}",
                            xy=(n + di * D + D * 0.85, day_last),
                            xytext=(n + di * D + D * 0.35, day_lo - (hi - lo) * 0.08),
                            color=BEAR_ZONE_C, fontsize=7, family="monospace",
                            arrowprops=dict(arrowstyle="->", color=BEAR_ZONE_C, lw=0.8))

    # Plan paths — ONLY across day columns that have NO actual bars (lines off candles).
    # X must be strictly increasing (charts never move backward in time). Same target
    # levels, same order, same day-slot assignments — only frac within a day is monotonic.
    empty_days = [i for i in range(ND) if i not in days_with_actual]
    if empty_days:
        # Anchor price = last actual close (or hist last), but X starts inside the
        # first EMPTY day column — never on a candle (Everett: lines off candles).
        if days_with_actual:
            last_di = max(days_with_actual)
            last_rows = by_day[last_di]
            anchor_px = float(last_rows[-1][1].Close)
        else:
            anchor_px = last
        anchor_x = n + empty_days[0] * D + 0.08 * D
        for path, c, lab in ((sp["bull"], S, "bull path"), (sp["bear"], R, "bear path")):
            if not path:
                continue
            slots = empty_days
            # Day assignment (unchanged): proportional index into empty slots
            day_for = []
            for i in range(len(path)):
                if len(slots) == 1:
                    day_for.append(slots[0])
                else:
                    idx = min(int(i * len(slots) / max(len(path), 1)), len(slots) - 1)
                    day_for.append(slots[idx])
            counts = Counter(day_for)
            seen = Counter()
            xs = [anchor_x]
            ys = [anchor_px]
            prev_x = anchor_x
            for i, px in enumerate(path):
                di = day_for[i]
                local = seen[di]
                seen[di] += 1
                n_local = counts[di]
                if len(slots) == 1:
                    frac = (i + 1) / (len(path) + 0.5)
                elif n_local == 1:
                    frac = 0.55
                else:
                    # strictly increasing within the assigned day (no modulo wrap)
                    frac = 0.2 + 0.6 * (local / (n_local - 1))
                x = n + di * D + frac * D
                if x <= prev_x:
                    x = prev_x + max(0.25, D * 0.04)
                xs.append(x)
                ys.append(px)
                prev_x = x
            ax.plot(xs, ys, color=c, ls="--", lw=1.8, marker="o", ms=3.5, label=lab, zorder=3)
    else:
        # Fully mapped week — no path lines through candles; show legend stubs only
        ax.plot([], [], color=S, ls="--", lw=1.8, label="bull path (done)")
        ax.plot([], [], color=R, ls="--", lw=1.8, label="bear path (done)")

    ax.plot([], [], color=ACTUAL_UP, lw=2, label="plan-week actual")
    ax.plot([], [], color=TODAY_UP, lw=2, label="event day")
    ax.plot([], [], color="#ffb000", lw=2, label="prior week")

    sc = None
    if not actual.empty and z and sp["bull"] and sp["bear"]:
        # frozen_sc: keep the last published scorecard (forecast zones are never graded before they trade)
        sc = frozen_sc or _scorecard(actual, key, sp, zones, event_day)
        if sc:
            day_lines = []
            for d in sc["days"]:
                mark = " ★" if d["event"] else ""
                day_lines.append(
                    f"{d['date'][5:]}{mark}  hi {d['hi']:g}  lo {d['lo']:g}  c {d['last']:g}")
            title = box_title or ("PLAN vs ACTUAL" if mode == "actual" else "WEEK PLAN")
            box = (f"{title}\n"
                   f"bull zone {sc['phase1_zone'][0]:g}–{sc['phase1_zone'][1]:g}: {sc['phase1']} "
                   f"(hi {sc['phase1_high']:g})\n"
                   f"bear zone {sc['phase2_zone'][0]:g}–{sc['phase2_zone'][1]:g}: {sc['phase2']} "
                   f"(lo {sc['low']:g})\n"
                   + "\n".join(day_lines) +
                   f"\npath={sc['path']}  last={sc['last']:g}")
            ax.text(0.01, 0.02, box, transform=ax.transAxes, color="#e6e0cc", fontsize=6.5,
                    family="monospace", va="bottom", ha="left",
                    bbox=dict(boxstyle="round,pad=0.35", fc="#1a1400", ec="#a87400", alpha=0.92))
    elif mode == "plan":
        box = (box_title or "WEEK PLAN") + "\n"
        box += FWD_BOX[0] + "\n"
        if sp["bull"] and sp["bear"]:
            box += f"bull path → {sp['bull'][-1]:g}  ·  bear path → {sp['bear'][-1]:g}\n"
        else:
            box += "levels: awaiting update (no verified map for this week)\n"
        box += FWD_BOX[1]
        ax.text(0.01, 0.02, box, transform=ax.transAxes, color="#e6e0cc", fontsize=7,
                family="monospace", va="bottom", ha="left",
                bbox=dict(boxstyle="round,pad=0.35", fc="#1a1400", ec="#a87400", alpha=0.92))

    ticks = [i for i in range(1, n) if hist.index[i].date() != hist.index[i - 1].date()] + [0]
    ax.set_xticks(sorted(ticks))
    ax.set_xticklabels([hist.index[i].strftime("%a %m/%d") for i in sorted(ticks)], fontsize=7.5)
    ax.set_xlim(-1, xe + 4 * D * 0.85)
    ax.set_ylim(lo - (hi - lo) * 0.04, hi + (hi - lo) * 0.08)
    for s_ in ax.spines.values():
        s_.set_color("#333")
    ax.tick_params(colors="#9a8a60", labelsize=7.5)
    ax.grid(color="#1d1d21", lw=0.5)

    title = sp["title"] + "  ·  PLAN vs ACTUAL  ·  30m bars (PT)"
    ax.text(0.99, 0.98, "PLAN vs ACTUAL" if mode == "actual" else "WEEK PLAN",
            transform=ax.transAxes, color=P, fontsize=9,
            family="monospace", va="top", ha="right", weight="bold")
    ax.set_title(title, color="#ffb000", fontsize=10, loc="left", family="monospace")
    ax.legend(loc="upper left", fontsize=7, facecolor="#111114", edgecolor="#333", labelcolor="#ddd")
    fig.tight_layout()
    os.makedirs(os.path.dirname(out_path) or ".", exist_ok=True)
    fig.savefig(out_path, facecolor=fig.get_facecolor())
    plt.close(fig)
    return out_path, sc


def _snap_paths_to_zones(spec, zones):
    for k, sp in spec.items():
        z = zones.get(k)
        if not z or not sp["bull"] or not sp["bear"]:
            continue
        sp["bull"] = list(sp["bull"])
        sp["bear"] = list(sp["bear"])
        mid_b = (z["bull"][0] + z["bull"][1]) / 2
        mid_e = (z["bear"][0] + z["bear"][1]) / 2
        sp["bull"][-1] = mid_b
        sp["bear"][-1] = mid_e


def main():
    _snap_paths_to_zones(PRIOR_SPEC, PRIOR_ZONES)
    # Forward paths end on sourced targets (not snapped to zone midpoints).

    arch_date = dt.date(2026, 11, 10)
    # Bot input first (build_daily copies it to daily/ only after charts run), so a new
    # session never overwrites the previous session's archive folder.
    plan_json = next((c for c in (HERE.parent / "inputs" / "plan.json", SITE / "daily" / "plan.json") if c.exists()),
                     SITE / "daily" / "plan.json")
    if plan_json.exists():
        try:
            arch_date = dt.date.fromisoformat(json.loads(plan_json.read_text())["date"])
        except Exception:
            pass
    arch = Path(OUT) / arch_date.isoformat()
    arch.mkdir(parents=True, exist_ok=True)

    wdir = SITE / "weekly" / "charts"
    prior_dir = wdir / "prior"
    plan_dir = wdir / "plan"
    for d in (wdir, prior_dir, plan_dir):
        d.mkdir(parents=True, exist_ok=True)

    scores = {}
    failures = []
    # 1) Last week PLAN vs ACTUAL (Nov 23–27)
    print("=== PRIOR WEEK (Nov 23–27) PLAN vs ACTUAL ===")
    for k, sp in PRIOR_SPEC.items():
        try:
            p, sc = chart(k, sp, PRIOR_WEEK, PRIOR_ZONES, PRIOR_EVENT,
                          out_path=str(prior_dir / f"{k}.png"),
                          day_notes=PRIOR_DAY_NOTES,
                          mode="actual",
                          box_title="Nov 23–27 · plan vs actual")
            print("prior", p)
            shutil.copy(p, wdir / f"{k}.png")  # default weekly charts = last week actual
            if sc:
                scores[k] = sc
        except Exception as e:
            msg = f"prior FAILED {k}: {e}"
            print(msg, flush=True)
            failures.append(msg)

    # 2) This week PLAN (Nov 30–Dec 4) — actual candles so far + forward paths on empty days
    print("=== FORWARD WEEK (Nov 30–Dec 4) PLAN ===")
    fwd_scores = {}
    # FREEZE_SCORECARD=1: re-draw levels/paths but keep the published plan-week scorecard as-is
    frozen = {}
    if os.environ.get("FREEZE_SCORECARD") == "1":
        try:
            frozen = json.loads((SITE / "daily" / "scorecard.json").read_text(encoding="utf-8")).get("symbols_plan") or {}
        except (OSError, ValueError):
            frozen = {}
    for k, sp in FWD_SPEC.items():
        try:
            p, sc = chart(k, sp, PLAN_WEEK_FWD, FWD_ZONES, FWD_EVENT,
                          out_path=str(plan_dir / f"{k}.png"),
                          day_notes=FWD_DAY_NOTES,
                          mode="plan",
                          box_title="Nov 30–Dec 4 · week plan",
                          frozen_sc=frozen.get(k))
            print("plan", p)
            shutil.copy(p, Path(OUT) / f"{k}.png")  # daily page = this week's chart (new candles)
            shutil.copy(p, arch / f"{k}.png")
            if sc:
                fwd_scores[k] = sc
        except Exception as e:
            msg = f"plan FAILED {k}: {e}"
            print(msg, flush=True)
            failures.append(msg)

    (SITE / "daily" / "scorecard.json").write_text(json.dumps({
        "date": arch_date.isoformat(),
        "prior_week": [d.isoformat() for d in PRIOR_WEEK],
        "plan_week": [d.isoformat() for d in PLAN_WEEK_FWD],
        "have_actual": bool(scores),
        "symbols_prior": scores,
        "symbols_plan": fwd_scores,
        "note": "Prior week = Nov 23–27 PLAN vs ACTUAL (cleaned free_data bars). "
                "Plan week = Nov 30–Dec 4 actual so far + forward paths only on empty day columns.",
    }, indent=2), encoding="utf-8")
    try:
        (Path(__file__).resolve().parent.parent / "cache").mkdir(parents=True, exist_ok=True); Path(__file__).resolve().parent.parent.joinpath("cache/fomc_zone_status.json").write_text(
            json.dumps({"prior": scores, "plan": fwd_scores}, indent=2))
    except Exception:
        pass
    print("daily/weekly charts ->", OUT, "archive", arch)
    print("weekly/charts (prior actual) + weekly/charts/plan (Nov 30 forward)")
    if failures:
        print("ERROR: chart build failed for:", "; ".join(failures), flush=True)
        raise SystemExit(1)


if __name__ == "__main__":
    main()
