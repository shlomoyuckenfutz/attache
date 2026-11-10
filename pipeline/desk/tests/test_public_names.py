"""Fails if any served site asset (repo root outside pipeline/) or a bot-written plan input names a private source."""
import os, re, sys, unittest
from pathlib import Path
ROOT = Path(os.environ.get("ORB_SITE") or Path(__file__).resolve().parents[3])
BANNED = re.compile(r"mancini|smashelito|\bsmash(?:level)?\b|voltick|kttech|traderjonesy|jonesy|substack|newsletter", re.I)
TEXT = {".html", ".json", ".js", ".css", ".txt", ".md", ".svg", ".xml"}
INPUTS = ["pipeline/inputs/plan.json", "pipeline/inputs/implied_move/sourced_im.json",
          "pipeline/inputs/newswire_raw.json", "pipeline/inputs/positioning/board.json"] + [str(p.relative_to(ROOT)) for p in (ROOT / "pipeline/inputs/plans").glob("yuckenfutz-weekly-2026-11-*.txt")]


# Stricter scan for the pages/inputs carrying options-positioning data: also no source-specific jargon
# (level names, band names) and no saved handle anywhere.
STRICT_FILES = ["command/index.html", "daily/index.html", "weekly/index.html", "gammamap/index.html",
                "pipeline/inputs/positioning/board.json", "pipeline/desk/gamma_board.py"]
JARGON = r"\bvolts?\b|\bsurge\b|\bcoil\b|\breversal level|learned (?:band|move)|grower|first ?squawk|\baxios\b"


def strict_rx(root=ROOT):
    import json
    hs = []
    for n in ("handles.json", "newswire_handles.json"):
        f = root / "pipeline/desk/xnews" / n
        if f.exists():
            hs += [h for h in json.loads(f.read_text()) if isinstance(h, str) and len(h) > 3]
    return re.compile(BANNED.pattern + "|" + JARGON + ("|" + "|".join(re.escape(h) for h in hs) if hs else ""), re.I)


def strict_scan(root=ROOT):
    rx, hits = strict_rx(root), []
    for f in STRICT_FILES:
        p = root / f
        if not p.exists():
            continue
        t = p.read_text(encoding="utf-8", errors="replace")
        if f == "command/index.html":  # the wire block carries outside headlines; scan everything else
            import re as _re
            t = _re.sub(r'<section class="nw nwt" id="z-wire">.*?</section>', "", t, flags=_re.S)
        m = rx.search(t)
        if m:
            hits.append(f"{f}: {m.group(0)!r} …{t[max(0, m.start()-40):m.end()+40]!r}")
    return hits


def scan(root=ROOT):
    hits = []
    files = [p for p in root.rglob("*") if p.is_file() and p.suffix.lower() in TEXT
             and not str(p.relative_to(root)).startswith(("pipeline/", ".git/", ".github/"))]
    files += [root / f for f in INPUTS if (root / f).exists()]
    for p in files:
        t = p.read_text(encoding="utf-8", errors="replace")
        m = BANNED.search(t)
        if m:
            hits.append(f"{p.relative_to(root)}: {m.group(0)!r} …{t[max(0, m.start()-40):m.end()+40]!r}")
    return hits


class T(unittest.TestCase):
    def test_no_source_names_in_public_assets(self):
        hits = scan()
        self.assertEqual(hits, [], "\n".join(hits))

    def test_strict_scan_positioning_pages(self):
        hits = strict_scan()
        self.assertEqual(hits, [], "\n".join(hits))


if __name__ == "__main__":
    hits = scan() + strict_scan()
    print("\n".join(hits) or "public-name scan: ok"); sys.exit(1 if hits else 0)
