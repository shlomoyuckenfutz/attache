#!/usr/bin/env python3
"""ATTACHÉ DAILY + WEEKLY PLAN vs ACTUAL charts.
Weekly layout + actual 30m overlay. Prior-week amber; plan-week past days white;
event/today cyan. Free Yahoo 30m (cleaned of seam/garbage-wick artifacts).
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
SPY_PER_SPX = 0.0997
ES_MINUS_SPX = 34.5

# ── Week of Oct 26 (last week) — PLAN vs ACTUAL scorecard ──────────────────
PRIOR_WEEK = [dt.date(2026, 10, 26), dt.date(2026, 10, 27), dt.date(2026, 10, 28),
              dt.date(2026, 10, 29), dt.date(2026, 10, 30)]
PRIOR_ZONES = {
  "spy": {"bull": (775.0, 778.0), "bear": (765.0, 760.0),
          "bull_lab": "plan bull zone", "bear_lab": "plan bear zone"},
  "qqq": {"bull": (725.0, 730.0), "bear": (715.0, 708.0),
          "bull_lab": "plan bull zone", "bear_lab": "plan bear zone"},
  "es":  {"bull": (7805.0, 7830.0), "bear": (7730.0, 7710.0),
          "bull_lab": "plan bull zone", "bear_lab": "plan bear zone"},
  "nq":  {"bull": (30150.0, 30273.0), "bear": (29580.0, 29330.0),
          "bull_lab": "plan bull zone", "bear_lab": "plan bear zone"},
}
PRIOR_SPEC = {
 "es": dict(sym="ES=F", title="/ES  ·  week of Oct 26 (actual)", fut=True, lv=[
   (7697,"R","Fri high"),(7731,"R","resistance"),(7803,"R","resistance"),(7835,"R","magnet"),
   (7690,"P","most-traded"),(7656,"S","support"),(7649,"S","support"),(7636,"S","support"),
   (7616,"S","support"),(7575,"S","line in sand")],
   zones=[(7705,7710,"R","must clear"),(7675,7677,"P","pivot shelf"),(7751,7755,"R","gap fill")],
   bull=[7707,7731,7753,7803,7817], bear=[7677,7656,7649,7636,7616]),
 "nq": dict(sym="NQ=F", title="/NQ  ·  week of Oct 26 (actual)", fut=True, lv=[
   (29304,"R","ovn high"),(29520,"R","~gap mid"),(29740,"R","~720 wall eq"),
   (29228,"S","ovn low"),(28987,"S","Fri low"),(28915,"S","~700 wall eq"),
   (28875,"S","~699 eq"),(28710,"S","~695 eq"),(28295,"S","~685 eq")],
   zones=[(29320,29326,"R","FVG + Fri high")],
   bull=[29323,29520,29740,30160], bear=[29228,28915,28710,28295]),
 "spy": dict(sym="SPY", title="SPY  ·  week of Oct 26 (actual)", fut=False, lv=[
   (762.27,"R","resistance"),(770,"R","call wall"),(774.7,"R","gamma flip"),
   (760.29,"P","gamma pin"),(758.52,"P","weekly pivot"),
   (750.04,"S","put wall")],
   zones=[(755,757,"S","100 DMA · 755 put"),(765,765.27,"R","bounce target"),
          (747,748,"S","prior FOMC lows")],
   bull=[760.29,762.27,765.1,770,776.5], bear=[758.52,756,752,750,747.5]),
 "qqq": dict(sym="QQQ", title="QQQ  ·  week of Oct 26 (actual)", fut=False, lv=[
   (710,"R","resistance"),(720,"R","call wall"),(730.5,"R","gamma flip"),
   (700,"S","put wall"),(695,"S","support"),(685.22,"S","support"),(676,"S","200 DMA")],
   zones=[(715,718,"R","20-wk SMA")],
   bull=[707.27,710,716.5,720,727.5], bear=[700,699.07,695,685.22]),
}
PRIOR_EVENT = {  # Wed FOMC — edge ticks only
  "day": dt.date(2026, 10, 28),
  "label": "FOMC Wed 11:00 PT",
  "frac_fut": 0.53, "frac_cash": 0.69,
}

# ── Week of Nov 2 (this week) — forward PLAN ───────────────────────────────
PLAN_WEEK_FWD = [dt.date(2026, 11, 2), dt.date(2026, 11, 3), dt.date(2026, 11, 4),
                 dt.date(2026, 11, 5), dt.date(2026, 11, 6)]
FWD_ZONES = {
  "spy": {"bull": (770.0, 775.0), "bear": (750.0, 746.5),
          "bull_lab": "770–775 call-wall / FOMC", "bear_lab": "air-pocket zone"},
  "qqq": {"bull": (710.0, 715.0), "bear": (685.0, 676.0),
          "bull_lab": "710–715 / 20-wk", "bear_lab": "air-pocket zone"},
  "es":  {"bull": (7703.0, 7755.0), "bear": (7558.0, 7520.0),
          "bull_lab": "7703–7755 late-week bounce", "bear_lab": "air-pocket zone"},
  "nq":  {"bull": (29740.0, 30100.0), "bear": (28295.0, 27900.0),
          "bull_lab": "29740–30100 late-week bounce", "bear_lab": "air-pocket zone"},
}
FWD_SPEC = {
 "es": dict(sym="ES=F", title="/ES  ·  week of Nov 2 (plan)", fut=True, lv=[
   (7803,"R","prior range top"),(7731,"R","resistance"),(7703,"R","bear-trigger retake"),
   (7677,"R","old shelf"),(7616,"S","support · ≈SPY 755.9"),(7585,"S","support · ≈SPY 752.8"),
   (7575,"P","line in sand"),(7558,"S","Fri low"),(7540,"S","Mon flush undercut")],
   zones=[(7751,7755,"R","gap fill"),(7645,7649,"R","bounce step")],
   bull=[7575,7540,7560,7626,7677,7703,7755], bear=[7575,7560,7558,7525,7500]),
 "nq": dict(sym="NQ=F", title="/NQ  ·  week of Nov 2 (plan)", fut=True, lv=[
   (30178,"R","Wed AH high"),(29740,"R","~720 wall eq"),(29320,"R","old high"),
   (28915,"R","≈QQQ 700"),(28543,"P","Fri settle"),
   (28295,"S","support"),(28233,"S","Fri low"),(27900,"S","bear target")],
   zones=[(28900,28930,"R","700-eq reclaim")],
   bull=[28295,28100,28250,28915,29320,29740,30100], bear=[28295,28233,27900,27500]),
 "spy": dict(sym="SPY", title="SPY  ·  week of Nov 2 (plan)", fut=False, lv=[
   (775,"R","FOMC-week high area"),(770,"R","call wall / flip"),(765,"R","magnet"),
   (762.27,"R","LOST dark-pool"),(760,"R","LOST put wall"),
   (755.9,"S","≈ES 7616"),(755,"P","Fri close / put node"),
   (752.8,"S","≈ES 7585"),(750,"S","put floor")],
   zones=[(754,755,"P","pivot shelf")],
   bull=[752,750,754,760,765,770,775], bear=[754.07,750,746.77,740]),
 "qqq": dict(sym="QQQ", title="QQQ  ·  week of Nov 2 (plan)", fut=False, lv=[
   (718,"R","20-wk top"),(715,"R","expansion"),(710,"R","resistance"),(707,"R","prior shelf"),
   (690.49,"P","Fri close"),
   (685,"S","support"),(683.45,"S","Fri low"),(676,"S","200 DMA")],
   zones=[(698,702,"R","700 reclaim"),(674,678,"S","200 DMA zone")],
   bull=[690,688,692,700,707,710,715], bear=[685,683.45,676,670]),
}
FWD_EVENT = {  # Fri jobs — edge ticks; Tue midterms noted in blurb not as a price line
  "day": dt.date(2026, 11, 6),
  "label": "Jobs Fri 5:30 AM PT",
  "frac_fut": 0.15, "frac_cash": 0.15,
}
FWD_DAY_NOTES = {
  0: "ISM Mfg",
  1: "Midterms",
  2: "ADP / ISM Svc",
  3: "Claims",
  4: "NFP",
}


def _download(sym):
    """Free Yahoo 30m with extended hours; clean seam/garbage-wick artifacts."""
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

    Yahoo 30m sometimes emits a session-seam bar (esp. futures around cash settle)
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

    # Garbage AH/reference low: huge lower wick, almost no upper wick
    bad_low = (lower > 3.5 * rmed) & (lower > 6 * (upper + 1e-9))
    # Session-seam / settle spike: open jumps to prior close area, range enormous
    bad_seam = prev_c.notna() & (open_jump > 5 * rmed) & (rng > 6 * rmed)
    # Classic Yahoo artifact: Open==High far above Close with huge range
    bad_settle = (df.Open == df.High) & ((df.Open - df.Close).abs() > 5 * rmed) & (rng > 6 * rmed)

    n_repair = int(bad_low.sum())
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
          mode="actual", box_title=None):
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
    xe = n + 5 * D

    z = zones[key]
    ys = list(hist.Low) + list(hist.High) + list(sp["bull"]) + list(sp["bear"])
    ys += [z["bull"][0], z["bull"][1], z["bear"][0], z["bear"][1]]
    if not actual.empty:
        ys += list(actual.Low) + list(actual.High)
    lo, hi = min(ys), max(ys)
    pad = (hi - lo) * 0.06
    lo -= pad; hi += pad

    # Zones (fills only — labels go through collision placer below)
    ax.fill_between([-1, xe], z["bull"][0], z["bull"][1], color=BULL_ZONE_C, alpha=0.18, lw=0, zorder=1)
    ax.fill_between([-1, xe], min(z["bear"]), max(z["bear"]), color=BEAR_ZONE_C, alpha=0.18, lw=0, zorder=1)
    for a, b, k_, _t in sp["zones"]:
        ax.fill_between([-1, xe], a, b, color=COL[k_], alpha=0.10, lw=0)

    # Collect right-edge labels (primary bull/bear as bands + SPEC zones + levels).
    edge_labels = []
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
    day_names = ["MON", "TUE", "WED", "THU", "FRI"]
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
    by_day = {i: [] for i in range(5)}
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
    empty_days = [i for i in range(5) if i not in days_with_actual]
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
    if not actual.empty:
        sc = _scorecard(actual, key, sp, zones, event_day)
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
        box += f"bias: bearish / neg-gamma · bounce fade into resistance\n"
        box += f"bull path → {sp['bull'][-1]:g}  ·  bear path → {sp['bear'][-1]:g}\n"
        box += "catalysts: Mon ISM · Tue midterms · Wed ADP/ISM Svc · Fri jobs"
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
        z = zones[k]
        sp["bull"] = list(sp["bull"])
        sp["bear"] = list(sp["bear"])
        mid_b = (z["bull"][0] + z["bull"][1]) / 2
        mid_e = (z["bear"][0] + z["bear"][1]) / 2
        sp["bull"][-1] = mid_b
        sp["bear"][-1] = mid_e


def main():
    _snap_paths_to_zones(PRIOR_SPEC, PRIOR_ZONES)
    _snap_paths_to_zones(FWD_SPEC, FWD_ZONES)

    arch_date = dt.date(2026, 11, 2)
    plan_json = SITE / "daily" / "plan.json"
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
    # 1) Last week PLAN vs ACTUAL (Oct 26–30)
    print("=== PRIOR WEEK (Oct 26–30) PLAN vs ACTUAL ===")
    for k, sp in PRIOR_SPEC.items():
        try:
            p, sc = chart(k, sp, PRIOR_WEEK, PRIOR_ZONES, PRIOR_EVENT,
                          out_path=str(prior_dir / f"{k}.png"),
                          mode="actual",
                          box_title="Oct 26–30 · FOMC week actual")
            print("prior", p)
            shutil.copy(p, wdir / f"{k}.png")  # default weekly charts = last week actual
            shutil.copy(p, Path(OUT) / f"{k}.png")
            shutil.copy(p, arch / f"{k}.png")
            if sc:
                scores[k] = sc
        except Exception as e:
            msg = f"prior FAILED {k}: {e}"
            print(msg, flush=True)
            failures.append(msg)

    # 2) This week PLAN (Nov 2–6) — clean forward paths, no candles in plan slots yet
    print("=== FORWARD WEEK (Nov 2–6) PLAN ===")
    fwd_scores = {}
    for k, sp in FWD_SPEC.items():
        try:
            p, sc = chart(k, sp, PLAN_WEEK_FWD, FWD_ZONES, FWD_EVENT,
                          out_path=str(plan_dir / f"{k}.png"),
                          day_notes=FWD_DAY_NOTES,
                          mode="plan",
                          box_title="Nov 2–6 · bearish / neg-gamma plan")
            print("plan", p)
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
        "note": "Prior week = Oct 26–30 PLAN vs ACTUAL (cleaned Yahoo bars). "
                "Plan week = Nov 2–6 forward paths only on empty day columns.",
    }, indent=2), encoding="utf-8")
    try:
        (Path(__file__).resolve().parent.parent / "cache").mkdir(parents=True, exist_ok=True); Path(__file__).resolve().parent.parent.joinpath("cache/fomc_zone_status.json").write_text(
            json.dumps({"prior": scores, "plan": fwd_scores}, indent=2))
    except Exception:
        pass
    print("daily/weekly charts ->", OUT, "archive", arch)
    print("weekly/charts (prior actual) + weekly/charts/plan (Nov 2 forward)")
    if failures:
        print("ERROR: chart build failed for:", "; ".join(failures), flush=True)
        raise SystemExit(1)


if __name__ == "__main__":
    main()
