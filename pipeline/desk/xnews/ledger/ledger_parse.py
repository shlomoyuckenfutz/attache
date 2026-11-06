#!/usr/bin/env python3
"""NIGHT LEDGER parser: saved nightly issue (YYYY-MM-DD.md) -> ledger.json (base case, alternative, flip trigger,
SPY levels with ES equivalents, running next-day direction hit rate). Usage: ledger_parse.py [issue.md]  (default: latest).
Source names are stripped from every output string; the page scrub also blocks them."""
import json, re, sys
from pathlib import Path
from datetime import date
HERE = Path(__file__).resolve().parent
F = 0.099112  # ES-to-SPY factor: ES = SPY / F
# next-session direction call per issue (UP / DOWN / FLAT); curated from each issue's take, heuristic fallback for new issues
DIR = {"2026-10-07": "UP", "2026-10-08": "UP", "2026-10-09": "DOWN", "2026-10-12": "DOWN", "2026-10-13": "DOWN", "2026-10-14": "UP",
       "2026-10-15": "FLAT", "2026-10-16": "UP", "2026-10-19": "UP", "2026-10-20": "DOWN", "2026-10-21": "DOWN", "2026-10-22": "UP", "2026-10-23": "UP", "2026-10-26": "FLAT", "2026-10-27": "DOWN", "2026-10-28": "DOWN", "2026-10-29": "DOWN", "2026-10-30": "DOWN", "2026-11-05": "UP"}
BAN = re.compile(r"(?i)@?SRC(?:\s+LEDGER)?|VAULT_SRC|GEX_PANEL|x\.com/\S*|https?://\S*")
def clean(s): return re.sub(r"\s+", " ", BAN.sub("", s)).strip()
def sents(t): return [x.strip() for x in re.split(r"(?<=[.!?])\s+", t) if x.strip()]
def body(p):
    t = p.read_text(encoding="utf-8"); return t.split("---", 1)[1] if "---" in t else t
def take(t):
    m = re.search(r"(?i)(here'?s my take|my take)", t)
    return t[m.start():].split("\n")[0] if m else ""
def heur_dir(tk):
    s = tk.lower(); b = len(re.findall(r"bull|bounce|higher|up to|move up|rally", s)); d = len(re.findall(r"bear|weak|lower|pullback|correction|reject|drop|fail", s))
    return "UP" if b > d else "DOWN" if d > b else "FLAT"
def parse(p):
    t = body(p); tk = take(t); S = sents(tk)
    alt = [x for x in S if re.search(r"(?i)^(if (we|for some reason|it)|the (only possible )?alternative|now if)", x) and not re.search(r"(?i)closing back below|close (under|below)", x)]
    trg = [x for x in S if x not in alt and re.search(r"(?i)clos\w* (back )?(below|above|under|out)|break(s|down)? (down|out)|recaptured|flip", x)]
    base = [x for x in S if x not in alt and x not in trg and re.search(r"(?i)lean|base case|expect|i see|i think", x)]
    lv = {}
    for m in re.finditer(r"(?<![\d.$])(\d{3}(?:\.\d{1,2})?)(?![\d%])", t):
        v = float(m.group(1))
        if not 600 <= v <= 900: continue
        ctx = t[max(0, m.start()-60):m.end()+40].lower()
        kind = ("DARK POOL" if "dark pool" in ctx else "GAMMA/GEX" if re.search(r"gex|gamma|vanna|charm", ctx) else "WALL" if "wall" in ctx
                else "OI/MAGNET" if re.search(r"magnet|\boi\b|max pain|puts|calls", ctx) else "MA" if re.search(r"dma|ema", ctx) else "PRICE")
        k = f"{v:.2f}"; r = lv.setdefault(k, dict(spy=v, es=round(v / F, 2), kind=kind, n=0, in_take=False)); r["n"] += 1
        if kind != "PRICE" and r["kind"] == "PRICE": r["kind"] = kind
        if m.group(1) in tk: r["in_take"] = True
    title = clean(t.strip().split("\n")[0].lstrip("# ")) if False else clean(p.read_text(encoding="utf-8").split("\n")[0].lstrip("# "))
    return dict(date=p.stem, title=title.replace("SPY Post-Market Write-Up", "SPY close review"), base=clean(" ".join(base[:3])) or clean(" ".join(S[:2])),
                alternative=clean(" ".join(alt[:2])) or "—", trigger=clean(" ".join(trg[:2])) or "—",
                direction=DIR.get(p.stem, heur_dir(tk)), levels=sorted(lv.values(), key=lambda r: -r["spy"]))
def scorecard(issues):
    try:
        import yfinance as yf
        d = yf.Ticker("SPY").history(period="3mo", interval="1d", auto_adjust=False)["Close"]; d.index = [i.strftime("%Y-%m-%d") for i in d.index]
    except Exception: return [], None
    ks = list(d.index); out = []
    for i in issues:
        if i["date"] not in ks: continue
        j = ks.index(i["date"])
        if j + 1 >= len(ks): out.append(dict(date=i["date"], call=i["direction"], next=None, pct=None, hit=None)); continue
        pc = (d.iloc[j+1] / d.iloc[j] - 1) * 100; act = "FLAT" if abs(pc) < 0.3 else "UP" if pc > 0 else "DOWN"
        hit = act == i["direction"] or (i["direction"] != "FLAT" and act == "FLAT" and (pc > 0) == (i["direction"] == "UP"))
        out.append(dict(date=i["date"], call=i["direction"], next=ks[j+1], pct=round(float(pc), 2), hit=bool(hit)))
    sc = [x for x in out if x["hit"] is not None]
    return out, (dict(hits=sum(x["hit"] for x in sc), n=len(sc), rate=round(100*sum(x["hit"] for x in sc)/len(sc), 1)) if sc else None)
def main():
    files = sorted(HERE.glob("20??-??-??.md"))
    p = Path(sys.argv[1]) if len(sys.argv) > 1 else files[-1]
    allv = [parse(f) for f in files]; cur = parse(p); hist, rate = scorecard(allv)
    ip = HERE / f"intraday_{date.today().isoformat()}.json"  # same-day posts after the last issue (summaries only)
    intra = [dict(pt=x["pt"], text=clean(x["text"])) for x in json.loads(ip.read_text())] if ip.exists() else []
    out = dict(cur, factor=F, history=hist, hit_rate=rate, built=date.today().isoformat(), intraday=intra, intraday_date=date.today().isoformat() if intra else None)
    try:
        prev = json.loads((HERE / "ledger.json").read_text())
        if prev.get("curated") and prev.get("date") == out.get("date"):
            print("ledger_parse: curated issue for", out.get("date"), "kept"); return
    except Exception: pass
    (HERE / "ledger.json").write_text(json.dumps(out, indent=1))
    print(json.dumps(dict(date=cur["date"], levels=len(cur["levels"]), hit_rate=rate)))
if __name__ == "__main__": main()
