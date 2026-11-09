"""Dated, sourced implied-move rows for the Daily plan / Command 'long story short'.

Input: xnews/implied_move/sourced_im.json (synced from pipeline/inputs/implied_move/sourced_im.json)
  {"daily":  [{"symbol": "SPY", "session": "YYYY-MM-DD", "lower": float, "upper": float}],
   "weekly": [{"symbol": "SPY", "week_start": "YYYY-MM-DD", "week_end": "YYYY-MM-DD", "lower": float, "upper": float}]}
Rows only render when the symbol, period and numbers validate for the plan session. Anything missing,
mismatched or malformed renders as plain 'awaiting update' (with a real date) - never raw errors and never
an unlabeled stale value. No source names are stored or rendered here."""
from __future__ import annotations
import json, math, re
from datetime import date, timedelta
from pathlib import Path

AWAIT = "awaiting update"
SYMBOLS = ("SPY",)
_SYM = re.compile(r"^[A-Z]{1,6}$")


def _d(s):
    try:
        return date.fromisoformat(str(s)[:10]) if re.fullmatch(r"\d{4}-\d{2}-\d{2}", str(s or "")) else None
    except ValueError:
        return None


def _day(d: date) -> str:
    return f"{d:%a} {d:%b} {d.day}"


def _week(a: date, b: date) -> str:
    return f"{a:%b} {a.day}–{b.day}" if a.month == b.month else f"{a:%b} {a.day}–{b:%b} {b.day}"


def _num(v):
    if isinstance(v, bool) or not isinstance(v, (int, float, str)):
        return None
    try:
        x = float(v)
    except (TypeError, ValueError):
        return None
    return x if math.isfinite(x) and x > 0 else None


def _band(row):
    lo, hi = _num(row.get("lower")), _num(row.get("upper"))
    if lo is None or hi is None or not lo < hi or hi / lo > 1.25:
        return None
    return lo, hi


def _sym_ok(row, sym):
    s = row.get("symbol")
    return isinstance(s, str) and _SYM.match(s) and s == sym


def week_of(session: date):
    mon = session - timedelta(days=session.weekday())
    return mon, mon + timedelta(days=4)


def load(path: Path) -> dict:
    try:
        d = json.loads(Path(path).read_text(encoding="utf-8"))
        return d if isinstance(d, dict) else {}
    except Exception:
        return {}


def daily_row(data: dict, sym: str, session: date) -> str:
    label = f"{sym} daily · {_day(session)}"
    rows = [r for r in (data.get("daily") or []) if isinstance(r, dict) and _sym_ok(r, sym)]
    for r in rows:
        if _d(r.get("session")) == session:
            b = _band(r)
            if b:
                return f"{label}: {b[0]:.2f}–{b[1]:.2f}"
    return f"{label}: {AWAIT}"


def weekly_row(data: dict, sym: str, session: date) -> str:
    ws, we = week_of(session)
    label = f"{sym} weekly · {_week(ws, we)}"
    rows = [r for r in (data.get("weekly") or []) if isinstance(r, dict) and _sym_ok(r, sym)]
    for r in rows:
        a, b = _d(r.get("week_start")), _d(r.get("week_end"))
        if not a or not b or not a <= session <= b or (b - a).days > 6:
            continue
        band = _band(r)
        if band:
            return f"{sym} weekly · {_week(a, b)}: {band[0]:.2f}–{band[1]:.2f}"
    return f"{label}: {AWAIT}"


def lines(data: dict, session_str) -> tuple[list[str], str]:
    session = _d(session_str)
    if session is None:
        return [f"Implied move: {AWAIT}"], ""
    out = []
    for sym in SYMBOLS:
        out.append(daily_row(data, sym, session))
        out.append(weekly_row(data, sym, session))
    return out, "SPY-scale bounds, not ES/SPX points; not guaranteed limits"
