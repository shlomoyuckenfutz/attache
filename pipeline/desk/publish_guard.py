"""Pre-push guard for the overnight publish job (pipeline/publish_overnight.sh).

Compares the commit about to be pushed (HEAD) with origin (BASE) and refuses the push when:
  * HEAD touches any file outside the job's allowlist (it owns only the Overnight / Night Ledger page and inputs);
  * a changed file carries git conflict markers;
  * Command's ORB15 or Hourly session, the Daily plan date, or the Weekly plan date (page or Command card) is older
    than on BASE;
  * a page that has the Gamma Map or Live Trades nav tab on BASE lost it;
  * the Live Trades as-of date would move backwards, or the page would disappear.
Usage: publish_guard.py [--repo DIR] [--base origin/main] [--head HEAD]. Exit 0 = safe to push."""
import argparse, fnmatch, json, re, subprocess, sys
from datetime import datetime

OWNED = (
    "overnight/index.html",
    "pipeline/desk/es_levels/overnight.json",
    "pipeline/desk/es_levels/overnight_details.json",
    "pipeline/desk/xnews/ledger/ledger.json",
    "pipeline/desk/xnews/ledger/*.md",
    "pipeline/desk/xnews/ledger/intraday_*.json",
    "pipeline/inputs/ledger/*",
)
NAV_PAGES = ("command", "overnight", "weekly", "daily", "gammamap", "darkpool", "study", "exposure", "project-b", "live-trades")
MARKER = re.compile(r"^(<<<<<<< |>>>>>>> |=======$)", re.M)


def owned(path):
    return any(fnmatch.fnmatchcase(path, g) for g in OWNED)


def orb_sessions(html):
    """{'ORB SPY': 'YYYY-MM-DD', ..., 'HOURLY': 'YYYY-MM-DD'} from Command; missing keys are simply absent."""
    out = {}
    m = re.search(r"const D=", html or "")
    if m:
        try:
            D, _ = json.JSONDecoder().raw_decode(html[html.index("{", m.end() - 1):])
            for s, o in (D.get("orb") or {}).items():
                if isinstance(o, dict) and o.get("date"):
                    out[f"ORB {s}"] = o["date"]
        except ValueError:
            pass
    hr = re.search(r'<section class="zone" id="z-hr">.*?</section>', html or "", re.S)
    if hr:
        d = re.search(r"last data \w{3} (\d{4}-\d{2}-\d{2})", hr.group(0))
        if d:
            out["HOURLY"] = d.group(1)
    return out


def _d(s, fmt):
    try:
        return datetime.strptime(s, fmt).date().isoformat()
    except ValueError:
        return None


def daily_date(html):
    m = re.search(r"DAILY PLAN — \w{3} (\w{3} \d{1,2}, \d{4})", html or "")
    return m and _d(m.group(1), "%b %d, %Y")


def weekly_date(html):
    m = re.search(r"\w{3} (\w{3} \d{1,2}) to \w{3} \w{3} \d{1,2}, (\d{4})", html or "")
    return m and _d(f"{m.group(1)}, {m.group(2)}", "%b %d, %Y")


def _nav(html):
    return re.findall(r"<nav\b.*?</nav>", html or "", re.S | re.I)


def has_gamma_tab(html):
    return any("gammamap/" in n for n in _nav(html))


def has_live_trades_tab(html):
    return any("live-trades/" in n for n in _nav(html))


def live_trades_asof(html):
    m = re.search(r"as of \w{3} (\w{3} \d{1,2}, \d{4})", html or "")
    return m and _d(m.group(1), "%b %d, %Y")


def compare(base, head, changed):
    """base/head: {path: html or None}; changed: list of paths. Returns a list of reasons (empty = safe)."""
    bad = [f"not owned by the overnight job: {p}" for p in changed if not owned(p)]
    bad += [f"conflict markers: {p}" for p in changed if head.get(p) and MARKER.search(head[p])]
    cb, ch = base.get("command/index.html"), head.get("command/index.html")
    b, h = orb_sessions(cb), orb_sessions(ch)
    bad += [f"Command {k} would regress {v} -> {h.get(k)}" for k, v in b.items() if (h.get(k) or "") < v]
    for label, page, fn in (("Daily plan", "daily/index.html", daily_date), ("Weekly plan", "weekly/index.html", weekly_date),
                            ("Command weekly card", "command/index.html", weekly_date)):
        bv, hv = fn(base.get(page)), fn(head.get(page))
        if bv and (hv or "") < bv:
            bad.append(f"{label} would regress {bv} -> {hv}")
    for p in NAV_PAGES:
        k = f"{p}/index.html"
        if has_gamma_tab(base.get(k)) and not has_gamma_tab(head.get(k)):
            bad.append(f"Gamma Map nav tab lost on {k}")
        if has_live_trades_tab(base.get(k)) and not has_live_trades_tab(head.get(k)):
            bad.append(f"Live Trades nav tab lost on {k}")
    if base.get("live-trades/index.html") is not None and head.get("live-trades/index.html") is None:
        bad.append("Live Trades page missing")
    bv, hv = live_trades_asof(base.get("live-trades/index.html")), live_trades_asof(head.get("live-trades/index.html"))
    if bv and (hv or "") < bv:
        bad.append(f"Live Trades as-of would regress {bv} -> {hv}")
    return bad


def _git(repo, *a):
    r = subprocess.run(["git", "-C", repo, *a], capture_output=True)
    r.stdout = r.stdout.decode("utf-8", "replace")
    return r


def _show(repo, rev, path):
    if not path.endswith((".html", ".json", ".md", ".txt", ".js", ".py", ".sh", ".css")):
        return None
    r = _git(repo, "show", f"{rev}:{path}")
    return r.stdout if r.returncode == 0 else None


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo", default=".")
    ap.add_argument("--base", default="origin/main")
    ap.add_argument("--head", default="HEAD")
    a = ap.parse_args(argv)
    r = _git(a.repo, "diff", "--name-only", a.base, a.head)
    if r.returncode:
        print("publish_guard: cannot diff", a.base, a.head, file=sys.stderr); return 2
    changed = [p for p in r.stdout.splitlines() if p]
    pages = set(changed) | {f"{p}/index.html" for p in NAV_PAGES}
    base = {p: _show(a.repo, a.base, p) for p in pages}
    head = {p: _show(a.repo, a.head, p) for p in pages}
    bad = compare(base, head, changed)
    for b in bad:
        print("publish_guard: ABORT:", b, file=sys.stderr)
    if not bad:
        print(f"publish_guard: ok ({len(changed)} owned file(s) changed)")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
