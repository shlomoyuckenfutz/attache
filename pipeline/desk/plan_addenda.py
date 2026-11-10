"""Dated add-on blocks for the Daily and Weekly plan pages (pipeline/inputs/plans/addenda.json).

A block renders only for its own session (Daily) or week (Weekly) against inputs/plan.json's date; otherwise
nothing is inserted, so a stale block never shows as current. Rows with empty text are dropped. No source names."""
from __future__ import annotations
import html, json, re, sys
from datetime import date
from pathlib import Path

HERE = Path(__file__).resolve().parent
INP = HERE.parent / "inputs"
MK = "<!--PLANADDENDA-->"
E = html.escape
KINDS = {"res", "sup", "piv", ""}


def _iso(s):
    try:
        return date.fromisoformat(s) if isinstance(s, str) and re.fullmatch(r"\d{4}-\d{2}-\d{2}", s) else None
    except ValueError:
        return None


def _load(p):
    try:
        d = json.loads(Path(p).read_text(encoding="utf-8"))
        return d if isinstance(d, dict) else {}
    except Exception:
        return {}


def _rows(block):
    out = []
    for r in (block or {}).get("rows") or []:
        if isinstance(r, dict) and isinstance(r.get("t"), str) and r["t"].strip() and isinstance(r.get("lb"), str) and r["lb"].strip():
            out.append((r.get("k") if r.get("k") in KINDS else "", r["lb"].strip(), r["t"].strip()))
    return out


def _num(s):
    return re.sub(r"(?<![\w./:])(\d+(?:\.\d+)?%?)(?![\d/:]|-[a-z])", r"<b>\1</b>", E(s))


def section(sid, title, rows):
    lis = "".join(f'<li class="{k}"><span class="lb">{E(lb)}</span><span class="vv">{_num(t)}</span></li>' for k, lb, t in rows)
    return f'{MK}<section class="sec" id="{sid}"><h2>{E(title.upper())}</h2><ul>{lis}</ul></section>{MK}'


def daily_block(data, plan_date):
    b = (data or {}).get("daily") or {}
    s, pd = _iso(b.get("session")), _iso(plan_date)
    rows = _rows(b)
    if not (s and pd and s == pd and rows and b.get("title")):
        return ""
    return section("cpi-spy-levels", f"{b['title']} · {s:%a} {s.month}/{s.day}", rows)


def weekly_block(data, plan_date):
    b = (data or {}).get("weekly") or {}
    a, z, pd = _iso(b.get("week_start")), _iso(b.get("week_end")), _iso(plan_date)
    rows = _rows(b)
    if not (a and z and pd and a <= pd <= z and (z - a).days <= 6 and rows and b.get("title")):
        return ""
    return section("week-bias-vol", f"{b['title']} · {a:%b} {a.day}–{z.day}" if a.month == z.month else f"{b['title']} · {a:%b} {a.day}–{z:%b} {z.day}", rows)


def patch(path, block):
    """Insert before the positioning section if present, else before the footer. Idempotent."""
    t = Path(path).read_text(encoding="utf-8")
    t = re.sub(re.escape(MK) + ".*?" + re.escape(MK), "", t, flags=re.S)
    if block:
        i = t.find("<!--GAMMABOARD-->")
        if i < 0:
            i = t.rfind('<div class="ft">')
        if i < 0:
            i = t.rfind("</main>")
        if i < 0:
            raise SystemExit(f"no anchor in {path}")
        t = t[:i] + block + t[i:]
    Path(path).write_text(t, encoding="utf-8")


def main(argv):
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--daily"); ap.add_argument("--weekly")
    ap.add_argument("--data", default=str(INP / "plans" / "addenda.json"))
    ap.add_argument("--plan", default=str(INP / "plan.json"))
    a = ap.parse_args(argv)
    data, plan = _load(a.data), _load(a.plan)
    pd = plan.get("date")
    if a.daily and Path(a.daily).exists():
        patch(a.daily, daily_block(data, pd))
    if a.weekly and Path(a.weekly).exists():
        patch(a.weekly, weekly_block(data, pd))
    print("plan_addenda: ok")


if __name__ == "__main__":
    main(sys.argv[1:])
