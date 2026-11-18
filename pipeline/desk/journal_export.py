"""Re-export the journal Log tab to pipeline/inputs/journal/v2_log.json from the sheet's public CSV view.

The sheet id comes from the JOURNAL_SHEET_ID environment variable (an Actions secret), so it never
appears in the public repo or on the site. No id, a failed fetch, an unexpected header, or fewer trade
rows than the file already holds all leave the file untouched (never blanks, never older data).
usage: python3 journal_export.py [OUT.json]
"""
from __future__ import annotations

import csv, io, json, os, sys
from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

HERE = Path(__file__).resolve().parent
OUT = Path(os.environ.get("ORB_INPUTS") or HERE.parent / "inputs") / "journal" / "v2_log.json"
URL = "https://docs.google.com/spreadsheets/d/{}/gviz/tq?tqx=out:csv&sheet=Log"
FIELDS = (("date", "Date"), ("sym", "Sym"), ("root", "Root"), ("inst", "Inst"), ("side", "Side"), ("qty", "Qty"),
          ("pts", "Pts"), ("pt_val", "Pt Val"), ("strike", "Strike"), ("entry", "Entry"), ("q_out", "Q Out"),
          ("exit", "Exit"), ("q_out_pl", "Q Out P/L"), ("net", "Net"), ("risk", "Risk"), ("equity", "Equity"))
TEXT = {"sym", "root", "inst", "side"}
MONEY = {"q_out_pl", "net", "risk", "equity"}


def num(s, money=False):
    s = str(s or "").strip().replace("$", "").replace(",", "")
    neg = s.startswith("(") and s.endswith(")")
    s = s.strip("()")
    if not s:
        return None
    try:
        v = float(s)
    except ValueError:
        return None
    v = -v if neg else v
    if money:
        return round(v, 2)
    return int(v) if v == int(v) else v


def parse(text: str):
    rows = list(csv.reader(io.StringIO(text)))
    if not rows:
        return None
    hdr = [h.strip() for h in rows[0]]
    col = {h: i for i, h in enumerate(hdr) if h}
    if any(h not in col for _, h in FIELDS):
        return None
    out = []
    for r in rows[1:]:
        g = lambda h: r[col[h]].strip() if col[h] < len(r) else ""
        d, sym = g("Date"), g("Sym")
        if not d or not sym:
            continue
        try:
            iso = datetime.strptime(d, "%m/%d/%Y").date().isoformat()
        except ValueError:
            continue
        t = {"date": iso}
        for k, h in FIELDS[1:]:
            t[k] = (g(h) or None) if k in TEXT else num(g(h), k in MONEY)
        out.append(t)
    return out


def main(out=OUT):
    sid = os.environ.get("JOURNAL_SHEET_ID", "").strip()
    if not sid:
        print("journal_export: no sheet id configured; file left as is"); return
    import requests
    try:
        r = requests.get(URL.format(sid), timeout=30)
        ok = r.status_code == 200 and "text/csv" in r.headers.get("content-type", "")
        trades = parse(r.text) if ok else None
    except Exception:
        trades = None
    if not trades:
        print("journal_export: fetch/parse unavailable; file left as is"); return
    out = Path(out)
    try:
        cur = json.loads(out.read_text())
    except (OSError, json.JSONDecodeError):
        cur = {}
    old = cur.get("trades") if isinstance(cur.get("trades"), list) else []
    if len(trades) < len(old):
        print(f"journal_export: sheet has {len(trades)} rows < {len(old)} published; file left as is"); return
    if trades == old:
        print("journal_export: unchanged"); return
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps({"as_of": datetime.now(ZoneInfo("America/Los_Angeles")).date().isoformat(), "trades": trades}, indent=2) + "\n")
    print(f"journal_export: {len(trades)} trades")


if __name__ == "__main__":
    main(*(sys.argv[1:2]))
