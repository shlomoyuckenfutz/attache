"""Positioning board: one test group per shipped item (1-8). Values must match the dated input; gaps say 'awaiting update'."""
import json, re, tempfile, unittest, copy
from datetime import datetime, timezone, timedelta
from pathlib import Path
import gamma_board as G
from tests import test_public_names as N

ROOT = Path(__file__).resolve().parents[3]
BOARD = ROOT / "pipeline/inputs/positioning/board.json"
RAW = json.loads(BOARD.read_text())
D = G.validate(copy.deepcopy(RAW))
PLAN = json.loads((ROOT / "pipeline/inputs/plan.json").read_text())
SPYW = G.spy_week_levels(ROOT / "pipeline/inputs/plans")
PAGE = G.map_page(D, PLAN, SPYW, "test")
DAILY, WEEKLY = G.daily_section(D), G.weekly_section(D)
CMD = G.command_payload(D)
ALL = PAGE + DAILY + WEEKLY + json.dumps(CMD, ensure_ascii=False)
NEXT_DAY_BANDS = ["7275.87", "7435.19", "649.55", "26501.92", "27787.34"]  # Wed 11/18 next-expiry (Thu) bands stay off the board


class I1_GammaLevels(unittest.TestCase):
    def test_values_and_regimes_per_expiry_board(self):
        L = D["levels"]
        self.assertEqual((L["SPX"]["2026-11-23"]["flip"], L["SPX"]["2026-11-23"]["magnet"], L["SPX"]["2026-11-23"]["regime"]), (7520.5, 7250, "NEG"))
        self.assertEqual(L["SPY"]["2026-12-18"]["regime"], "NEG")
        self.assertEqual(L["SPX"]["2026-11-20"]["regime"], "NEG")
        self.assertEqual(L["SPX"]["2026-11-20"]["net_gex"], "-$37.7B")
        self.assertEqual(L["NDX"]["2026-11-20"]["call_wall"], 28250)

    def test_tables_cover_every_ticker_and_expiry(self):
        for s in G.SYMS:
            for ex in ("11/20", "11/23", "12/18"):
                self.assertRegex(WEEKLY, rf"<td>{s}</td><td>{ex}</td>")
        self.assertIn("awaiting update", WEEKLY)
        for s in G.SYMS:
            self.assertRegex(DAILY, rf"<td>{s}</td><td>11/20</td>")
        self.assertIn("Thu 11/19 close", DAILY); self.assertIn("THU 11/19 CLOSE", WEEKLY); self.assertIn("Thu 11/19 close", CMD["gamma"]["h"])

    def test_bad_input_is_dropped_not_rendered(self):
        r = copy.deepcopy(RAW); r["levels"]["SPX"]["2026-11-23"] = {"flip": "x", "magnet": float("nan")}
        d = G.validate(r); self.assertIsNone(d["levels"]["SPX"]["2026-11-23"])
        self.assertEqual(G.validate({"asof": "bad"}), {})
        self.assertIn("awaiting update", G.daily_section({}))


class I2_EsNqConversion(unittest.TestCase):
    def test_es_is_spx_plus_plan_basis(self):
        self.assertEqual(D["es_basis"], 19.1)
        self.assertIn("<td>7219.10</td>", DAILY)  # SPX 11/20 7200 + 19.1
        es = [r for r in CMD["tiles"] if r["h"].startswith("ES")][0]
        self.assertIn("magnet 7269.10", es["rows"][1][1])  # 11/23 7250 + 19.1

    def test_nq_awaits_without_sourced_basis_and_no_equity_es(self):
        self.assertIsNone(D["nq_basis"])
        self.assertIn("NQ", DAILY); self.assertIn("no sourced NQ–NDX basis", DAILY)
        self.assertNotIn("69.49", ALL)


class I3_WeeklyExpectedMove(unittest.TestCase):
    def test_weekly_rows_shown_next_day_bands_not(self):
        line = G.em_line(D)
        self.assertTrue(line.startswith("Weekly expected move to Fri 11/20 (Thu 11/19 close)"))
        for s in ("SPX 7093.80–7257.88", "SPY 703.14–728.60", "QQQ 627.89–662.19", "NDX 26064.35–26969.77"):
            self.assertIn(s, line)
        for v in NEXT_DAY_BANDS:
            self.assertNotIn(v, ALL)
        self.assertEqual(list(CMD["im_extra"]["rows"][1]), ["SPY", "703.14–728.60 (±1.78%)"])


class I4_Calendar(unittest.TestCase):
    def test_thu_to_fri_pt_times(self):
        pt = timezone(timedelta(hours=-8))
        rows = G.calendar_rows(D)
        c = [r for r in rows if r["day"] == "Fri 11/20" and r["name"] == "Fed Waller"][0]; self.assertEqual(c["pt"], "5:25 AM PT")
        t = datetime.fromisoformat(c["utc"].replace("Z", "+00:00")).astimezone(pt)
        self.assertEqual((t.hour, t.minute), (5, 25))
        self.assertFalse(any(r["day"] in ("Mon 11/16", "Tue 11/17", "Wed 11/18", "Thu 11/19") for r in rows))  # past days drop off the countdown
        self.assertFalse(any(r["name"] == "Anthropic IPO debut" for r in rows))
        self.assertTrue(any(r["day"] == "Fri 11/20" and r["name"] == "Monthly OpEx" for r in rows))


class I5_Flow(unittest.TestCase):
    def test_flow_figures(self):
        f = [r for r in CMD["tiles"] if r["h"] == "FLOW"][0]
        self.assertEqual(f["v"], "+$21.2M bullish"); self.assertEqual(f["d"], "Thu 11/19")  # flow carries its own session date
        self.assertIn(["prints", "17,427"], f["rows"])
        self.assertIn("Largest prints by premium", f["note"])


class I6_Seasonality(unittest.TestCase):
    def test_spx_qqq_week_and_month(self):
        s = [r for r in CMD["tiles"] if r["h"] == "SEASONALITY"][0]
        keys = [k for k, _ in s["rows"]]
        self.assertEqual(keys, ["SPY week", "SPX week", "QQQ week", "SPY Nov", "SPX Nov", "QQQ Nov"])
        self.assertIn("median +3.6%", s["rows"][3][1]); self.assertIn("median +3.4%", s["rows"][4][1]); self.assertIn("median +3.0%", s["rows"][5][1]); self.assertIn("not a forecast", s["note"])
        self.assertIn("Week 47", WEEKLY)


class I7_GammaMap(unittest.TestCase):
    def test_every_ticker_section_and_confluence(self):
        for s in ("es", "spx", "spy", "qqq", "ndx", "nq"):
            self.assertIn(f'id="m-{s}"', PAGE)
        self.assertGreaterEqual(PAGE.count("CONFLUENCE</i>"), 3)
        # QQQ 640: Fri 11/20 put wall + magnet stack with the 12/18 floor
        self.assertRegex(PAGE, r">640 <i>CONFLUENCE</i>")
        self.assertIn("SPX close + basis", PAGE)

    def test_no_empty_cells_and_status_for_gaps(self):
        for td in re.findall(r"<td[^>]*>(.*?)</td>", PAGE, re.S):
            self.assertTrue(re.sub("<[^>]+>", "", td).strip(), "empty cell")
        self.assertIn("awaiting update", PAGE)  # put walls not on the board stay awaiting
        self.assertNotRegex(PAGE.lower(), r"\berror\b")

    def test_linked_from_nav(self):
        import ui_shell
        self.assertIn('href="../gammamap/"', ui_shell.bar("daily", "../"))
        self.assertIn("class=on>GAMMA MAP", ui_shell.bar("gammamap", "../"))
        self.assertIn('href="../live-trades/"', ui_shell.bar("daily", "../"))
        self.assertIn("class=on>LIVE TRADES", ui_shell.bar("livetrades", "../"))


class I8_HeaderStamp(unittest.TestCase):
    def test_stamp_set_and_stable_until_content_changes(self):
        src = (ROOT / "command/index.html").read_text()
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "c.html"; p.write_text(src)
            G.patch_command(p, D); g1 = self._gl(p)
            self.assertRegex(g1["updated_pt"], r"^(Mon|Tue|Wed|Thu|Fri|Sat|Sun) [A-Z][a-z]{2} \d{1,2}, 20\d\d \d{1,2}:\d\d [AP]M PT$")
            t = p.read_text(); m = re.search(r'(<script id="glance-data" type="application/json">)(.*?)(</script>)', t, re.S)
            g = json.loads(m.group(2)); g["updated_pt"] = "SENTINEL"
            p.write_text(t[:m.start(2)] + json.dumps(g, ensure_ascii=False) + t[m.end(2):])
            G.patch_command(p, D); self.assertEqual(self._gl(p)["updated_pt"], "SENTINEL")  # unchanged content keeps stamp
            p.write_text(p.read_text().replace('id="brief"', 'id="brief" '))
            G.patch_command(p, D); self.assertNotEqual(self._gl(p)["updated_pt"], "SENTINEL")
        self.assertIn("$('#ts').textContent=(window.GL&&GL.updated_pt)||D.updated;", src)

    @staticmethod
    def _gl(p):
        return json.loads(re.search(r'<script id="glance-data" type="application/json">(.*?)</script>', p.read_text(), re.S).group(1))


class NoSourceNames(unittest.TestCase):
    def test_outputs_have_no_names_or_jargon(self):
        rx = N.strict_rx()
        self.assertIsNone(rx.search(ALL))
        self.assertTrue(rx.search("Volt 7550") and rx.search("Surge 7570"))  # the scan itself bites


if __name__ == "__main__":
    unittest.main()
