"""Live Trades page builds from the journal export, hides file/source names, and never shows 'error'."""
import json, os, re, sys, tempfile, unittest
from html import unescape
from pathlib import Path

DESK = Path(__file__).resolve().parents[1]
ROOT = Path(os.environ.get("ORB_SITE") or DESK.parents[1])
sys.path.insert(0, str(DESK))
import live_trades as lt  # noqa: E402
import ui_shell  # noqa: E402

BANNED = re.compile(
    r"mancini|smashelito|\bsmash(?:level)?\b|voltick|kttech|traderjonesy|jonesy|substack|newsletter|"
    r"v2_log|pipeline/|rebuilt from|\bgoogle\b|spreadsheet|\.json\b|\.csv\b|docs\.google",
    re.I,
)
ERROR_RX = re.compile(r"error", re.I)


def visible(raw):
    s = re.sub(r"<script\b[^>]*>.*?</script>", " ", raw, flags=re.I | re.S)
    s = re.sub(r"<style\b[^>]*>.*?</style>", " ", s, flags=re.I | re.S)
    s = re.sub(r"<!--.*?-->", " ", s, flags=re.S)
    s = re.sub(r"<[^>]+>", " ", s)
    return unescape(re.sub(r"\s+", " ", s))


def fixture_trades():
    return [
        {"date": "2026-11-01", "sym": "/ES", "inst": "Futures", "side": "Long", "qty": 1,
         "pts": 90, "pt_val": 50, "entry": 7575, "q_out": 7625, "exit": 7665,
         "q_out_pl": 2500, "net": 4500, "risk": 1100, "equity": 4500},
        {"date": "2026-11-17", "sym": "SPX", "inst": "Put", "side": "Short", "qty": 1,
         "strike": 7290, "entry": 5.3, "q_out": 6.4, "exit": 6.4,
         "q_out_pl": 110, "net": 110, "equity": 4610},
        {"date": "2026-11-17", "sym": "SPX", "inst": "Call", "side": "Long", "qty": 1,
         "strike": 7320, "entry": 2.6, "q_out": 6.4, "exit": 10.4,
         "q_out_pl": 380, "net": 780, "equity": 5390},
    ]


class Builder(unittest.TestCase):
    def test_summary_order_and_short_profit(self):
        s = lt.summary(fixture_trades())
        self.assertEqual(s["q_out"], 2990)
        self.assertEqual(s["options"], 890)
        self.assertEqual(s["futures"], 4500)
        self.assertEqual(s["equity"], 5390)
        self.assertEqual(s["as_of"], "2026-11-17")
        self.assertEqual(s["count"], 3)
        html = lt.page(fixture_trades())
        vis = visible(html)
        # Profit tiles appear in Everett's order, then equity.
        q = vis.index("Q OUT ONLY")
        o = vis.index("OPTIONS · FULL OUT")
        f = vis.index("FUTURES")
        e = vis.index("EQUITY")
        self.assertLess(q, o)
        self.assertLess(o, f)
        self.assertLess(f, e)
        self.assertIn("$2,990", vis)
        self.assertIn("$890", vis)
        self.assertIn("$4,500", vis)
        self.assertIn("$5,390", vis)
        self.assertIn("as of Tue Nov 17, 2026", vis)
        # Newest first; later same-day row (7320C) above 7290P; shorts stay green profits.
        self.assertLess(vis.index("SPX 7320C"), vis.index("SPX 7290P"))
        self.assertLess(vis.index("SPX 7290P"), vis.index("/ES"))
        self.assertIn("Short", vis)
        self.assertIn("+$110" if False else "$110", vis)
        # the short row itself carries the up class and a profit figure
        self.assertRegex(html, r"SPX 7290P</td><td>Short</td>.*class=\"up\".*\$110", re.S)
        self.assertIsNone(ERROR_RX.search(vis))
        self.assertIsNone(BANNED.search(vis))
        self.assertIsNone(BANNED.search(html))
        self.assertIn("MY LIVE TRADES", html)
        self.assertNotIn("error", html.lower())

    def test_missing_input_is_awaiting_not_an_error(self):
        with tempfile.TemporaryDirectory() as d:
            out = Path(d) / "index.html"
            missing = Path(d) / "nope.json"
            self.assertIsNone(lt.load(missing))
            lt.write(lt.load(missing), out)
            html = out.read_text()
            vis = visible(html)
            self.assertIn("awaiting", vis.lower())
            self.assertIn("Q OUT ONLY", vis)
            self.assertNotIn("error", html.lower())
            self.assertIsNone(BANNED.search(html))

    def test_wired_into_refresh(self):
        s = (ROOT / "pipeline" / "refresh.sh").read_text()
        self.assertIn("live_trades.py", s)
        self.assertLess(s.index("live_trades.py"), s.index('"ui_shell"'))
        self.assertIn('livetrades=$ORB_SITE/live-trades/index.html', s)
        self.assertRegex(s, r"for p in [^\n]*live-trades")

    def test_nav_tab(self):
        bar = ui_shell.bar("livetrades", "../")
        self.assertIn('href="../live-trades/"', bar)
        self.assertIn("class=on>LIVE TRADES", bar)
        self.assertIn('href="../gammamap/"', bar)
        self.assertIn("GAMMA MAP", bar)
        daily = ui_shell.bar("daily", "../")
        self.assertIn('href="../live-trades/"', daily)
        self.assertNotIn("class=on>LIVE TRADES", daily)


class RepoPage(unittest.TestCase):
    def test_committed_page_matches_export_and_stays_clean(self):
        html = (ROOT / "live-trades" / "index.html").read_text(encoding="utf-8")
        trades = lt.load()
        self.assertTrue(trades)
        s = lt.summary(trades)
        vis = visible(html)
        self.assertEqual(s["as_of"], "2026-11-19")
        self.assertIn("as of Thu Nov 19, 2026", vis)
        self.assertIn(lt.fmt_money(s["q_out"]), vis)
        self.assertIn(lt.fmt_money(s["options"]), vis)
        self.assertIn(lt.fmt_money(s["futures"]), vis)
        self.assertIn(lt.fmt_money(s["equity"]), vis)
        self.assertLess(vis.index("Q OUT ONLY"), vis.index("OPTIONS · FULL OUT"))
        self.assertLess(vis.index("OPTIONS · FULL OUT"), vis.index("FUTURES"))
        self.assertIn("SPX 7290P", vis)
        self.assertIn("SPX 7320C", vis)
        self.assertLess(vis.index("SPX 7320C"), vis.index("SPX 7290P"))
        self.assertIn("$110", vis)
        self.assertIn("$780", vis)
        self.assertNotIn("error", html.lower())
        self.assertIsNone(BANNED.search(html))
        self.assertIsNone(BANNED.search(vis))
        self.assertIn('href="../live-trades/"', html)
        self.assertIn("gammamap/", html)


if __name__ == "__main__":
    unittest.main()
