import json, re, sys, tempfile, unittest
from pathlib import Path
DESK = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(DESK))
import implied_sourced as ims
import build_daily as bd

DATA = {"daily": [{"symbol": "SPY", "session": "2026-11-09", "lower": 725.03, "upper": 745.55}],
        "weekly": [{"symbol": "SPY", "week_start": "2026-11-09", "week_end": "2026-11-13", "lower": 713.24, "upper": 757.34}]}
BANNED = re.compile(r"mancini|smash|voltick|kttech|jonesy|substack|newsletter|x\.com|twitter|traceback|error|exception|keyerror|none\b|nan\b", re.I)


class T(unittest.TestCase):
    def test_tuesday_daily_awaits_weekly_renders(self):
        out, note = ims.lines(DATA, "2026-11-10")
        self.assertEqual(out, ["SPY daily · Tue Nov 10: awaiting update", "SPY weekly · Nov 9–13: 713.24–757.34"])
        self.assertIn("not ES/SPX", note)

    def test_matching_daily_renders(self):
        out, _ = ims.lines(DATA, "2026-11-09")
        self.assertEqual(out[0], "SPY daily · Mon Nov 9: 725.03–745.55")

    def test_session_mismatch_never_shows_stale_value(self):
        out, _ = ims.lines(DATA, "2026-11-10")
        self.assertNotIn("725.03", " ".join(out)); self.assertNotIn("745.55", " ".join(out))

    def test_weekly_boundaries(self):
        self.assertIn("713.24–757.34", ims.lines(DATA, "2026-11-13")[0][1])
        self.assertIn("713.24–757.34", ims.lines(DATA, "2026-11-09")[0][1])
        nxt = ims.lines(DATA, "2026-11-16")[0][1]
        self.assertEqual(nxt, "SPY weekly · Nov 16–20: awaiting update")
        prv = ims.lines(DATA, "2026-11-06")[0][1]
        self.assertEqual(prv, "SPY weekly · Nov 2–6: awaiting update")

    def test_cross_month_week_label(self):
        self.assertEqual(ims.lines({}, "2026-12-01")[0][1], "SPY weekly · Nov 30–Dec 4: awaiting update")

    def test_missing_and_malformed(self):
        bad = [
            {}, {"daily": None, "weekly": "x"},
            {"daily": [{"symbol": "SPY", "session": "2026-11-10", "lower": "abc", "upper": 740}]},
            {"daily": [{"symbol": "SPY", "session": "2026-11-10", "lower": 750, "upper": 740}]},
            {"daily": [{"symbol": "SPY", "session": "2026-11-10", "lower": float("nan"), "upper": 740}]},
            {"daily": [{"symbol": "SPY", "session": "2026-11-10", "lower": True, "upper": 740}]},
            {"daily": [{"symbol": "SPY", "session": "11/10/2026", "lower": 730, "upper": 740}]},
            {"daily": [{"symbol": "ES", "session": "2026-11-10", "lower": 7300, "upper": 7400}]},
            {"daily": [{"symbol": "SPY", "session": "2026-11-10", "lower": 100, "upper": 740}]},
            {"daily": ["junk", 3]},
        ]
        for d in bad:
            out, _ = ims.lines(d, "2026-11-10")
            self.assertEqual(out[0], "SPY daily · Tue Nov 10: awaiting update", d)
        for s in (None, "", "garbage", "2026-13-40"):
            self.assertEqual(ims.lines(DATA, s)[0], ["Implied move: awaiting update"])

    def test_weekly_wrong_symbol_or_span(self):
        d = {"weekly": [{"symbol": "QQQ", "week_start": "2026-11-09", "week_end": "2026-11-13", "lower": 600, "upper": 700},
                        {"symbol": "SPY", "week_start": "2026-11-02", "week_end": "2026-11-20", "lower": 700, "upper": 760}]}
        self.assertTrue(ims.lines(d, "2026-11-10")[0][1].endswith("awaiting update"))

    def test_unreadable_file(self):
        self.assertEqual(ims.load(Path("/nonexistent/x.json")), {})
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as f:
            f.write("{not json")
        self.assertEqual(ims.load(Path(f.name)), {})

    def test_build_daily_html_no_raw_errors_or_names(self):
        with tempfile.TemporaryDirectory() as td:
            here = Path(td); (here / "xnews" / "implied_move").mkdir(parents=True)
            old = bd.HERE; bd.HERE = here
            try:
                plan = {"date": "2026-11-10", "long_story_short": {"for_session": "2026-11-10", "headline": "h", "general": "g"}}
                for payload in (json.dumps(DATA), "{broken", None):
                    f = here / "xnews" / "implied_move" / "sourced_im.json"
                    if payload is None:
                        f.unlink(missing_ok=True)
                    else:
                        f.write_text(payload)
                    h = bd.lss_html(plan)
                    self.assertIn("Implied move:", h)
                    self.assertIn("awaiting update", h)
                    self.assertNotIn("Implied move (daily)", h)
                    self.assertIsNone(BANNED.search(re.sub(r"<[^>]+>", " ", h)), h)
                    self.assertNotIn("unavailable", h)
                self.assertNotIn("SPY weekly · Nov 9–13: 713.24–757.34", h)  # file missing -> no value
            finally:
                bd.HERE = old


if __name__ == "__main__":
    unittest.main()
