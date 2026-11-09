"""Fails if any served site asset (repo root outside pipeline/) or a bot-written plan input names a private source."""
import os, re, sys, unittest
from pathlib import Path
ROOT = Path(os.environ.get("ORB_SITE") or Path(__file__).resolve().parents[3])
BANNED = re.compile(r"mancini|smashelito|\bsmash(?:level)?\b|voltick|kttech|traderjonesy|jonesy|substack|newsletter", re.I)
TEXT = {".html", ".json", ".js", ".css", ".txt", ".md", ".svg", ".xml"}
INPUTS = ["pipeline/inputs/plan.json", "pipeline/inputs/implied_move/sourced_im.json",
          "pipeline/inputs/newswire_raw.json"] + [str(p.relative_to(ROOT)) for p in (ROOT / "pipeline/inputs/plans").glob("yuckenfutz-weekly-2026-11-*.txt")]


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


if __name__ == "__main__":
    hits = scan()
    print("\n".join(hits) or "public-name scan: ok"); sys.exit(1 if hits else 0)
