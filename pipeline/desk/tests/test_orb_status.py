"""Command ORB15 / Cum R / bot box / Hourly come from inputs/orb/orb_status.json via orb_status.py, which
refresh.sh runs; the live page must never sit behind those inputs. Every public page carries every nav tab."""
import json, re, shutil, sys, tempfile, unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
DESK = ROOT / "pipeline" / "desk"
INP = json.loads((ROOT / "pipeline" / "inputs" / "orb" / "orb_status.json").read_text())
PAGE = ROOT / "command" / "index.html"
sys.path.insert(0, str(DESK))
import orb_status  # noqa: E402


class OrbStatus(unittest.TestCase):
    def test_wired_into_refresh(self):
        s = (ROOT / "pipeline" / "refresh.sh").read_text()
        self.assertIn("orb_status.py", s)
        self.assertLess(s.index("orb_status.py"), s.index('"ui_shell"'))

    def test_page_matches_inputs(self):
        _, _, D = orb_status.payload(PAGE.read_text())
        for sym in ("SPY", "QQQ", "ES", "SPX"):
            self.assertGreaterEqual(D["orb"][sym]["date"], INP["asof"], sym)
        self.assertEqual(D["eq"]["SPY"]["d"][-1], INP["eq"]["SPY"]["d"][-1])
        self.assertEqual(D["bot"]["v"]["status"], "PAUSED")
        h = PAGE.read_text()
        orb = re.search(r'<section class="z" id="z-orb">.*?</section>', h, re.S).group(0)  # ORB STATUS carried over
        for el in ("orbSPY", "orbQQQ", "orbES", "orbSPX", "eqB", "botB"):
            self.assertIn(f'id="{el}"', orb)
        self.assertLess(h.index('id="z-orb"'), h.index('id="acct"'))  # sits right above the P&L / Account section
        tape = re.search(r'<section class="z" id="tape">.*?</section>', h, re.S).group(0)  # hourly breaks live in TAPE CHECK
        d = __import__("datetime").date.fromisoformat(INP["asof"])
        self.assertIn(f"{d:%a} {d.month}/{d.day}", tape); self.assertIn("HOURLY BREAKS", tape)

    def test_idempotent_and_never_backwards(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "index.html"; shutil.copy(PAGE, p)
            orb_status.main(str(p)); a = re.sub(r'"built": "[^"]*"', "", p.read_text())
            orb_status.main(str(p)); b = re.sub(r'"built": "[^"]*"', "", p.read_text())
            self.assertEqual(a, b)
            h = p.read_text().replace(f'"date": "{INP["orb"]["SPY"]["date"]}"', '"date": "2999-01-01"', 1)
            p.write_text(h); orb_status.main(str(p)); self.assertEqual(h, p.read_text())


class NavTabs(unittest.TestCase):
    def test_gamma_map_tab_everywhere(self):
        for rel in ("command", "overnight", "weekly", "daily", "darkpool", "gammamap", "study", "live-trades"):
            html = (ROOT / rel / "index.html").read_text()
            self.assertIn("gammamap/", html, rel)
            self.assertIn("live-trades/", html, rel)


if __name__ == "__main__":
    unittest.main()
