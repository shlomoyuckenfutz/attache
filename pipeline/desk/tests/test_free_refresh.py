"""Free 15-minute refresh blocks: intraday ORB15/hourly inputs, journal export, Command live blocks, bias gauge.
All offline (no network): bars and quotes are synthetic or taken from the committed inputs."""
import copy, json, re, sys, tempfile, unittest
from datetime import datetime, date, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd

ROOT = Path(__file__).resolve().parents[3]
DESK = ROOT / "pipeline" / "desk"
sys.path.insert(0, str(DESK))
import orb_live, journal_export, command_live  # noqa: E402

ET = ZoneInfo("America/New_York")
PREV = json.loads((ROOT / "pipeline" / "inputs" / "orb" / "orb_status.json").read_text())


def frame(day, bars):
    """yfinance-shaped 1m frame for one RTH session from [[i,o,h,l,c], ...]."""
    t0 = pd.Timestamp(f"{day} 09:30", tz=ET)
    idx = pd.DatetimeIndex([t0 + pd.Timedelta(minutes=b[0]) for b in bars])
    return pd.DataFrame({"Open": [b[1] for b in bars], "High": [b[2] for b in bars], "Low": [b[3] for b in bars],
                         "Close": [b[4] for b in bars], "Volume": 0}, index=idx)


def frames(day, n):
    return {k: frame(day, PREV["orb"][k]["bars"][:n]) for k in ("SPY", "QQQ", "ES", "SPX")}


class OrbLive(unittest.TestCase):
    DAY = PREV["asof"]

    def test_full_session_reproduces_nightly_rebuild(self):
        new = orb_live.build(frames(self.DAY, 390), copy.deepcopy(PREV), datetime(2026, 11, 18, 6, 0, tzinfo=ET))
        for k in ("SPY", "QQQ", "ES", "SPX"):
            for f in ("H", "L", "status", "entry", "stop", "target", "R", "result", "exits"):
                self.assertEqual(new["orb"][k].get(f), PREV["orb"][k].get(f), (k, f))
        self.assertEqual(new["hourly"], PREV["hourly"])
        self.assertEqual(new["eq"], PREV["eq"])  # same day already in the series: not appended twice
        self.assertIsNone(new["asof_t"])

    def test_intraday_forming_and_open(self):
        d = date.fromisoformat(self.DAY)
        new = orb_live.build(frames(self.DAY, 10), {}, datetime(d.year, d.month, d.day, 9, 40, tzinfo=ET))
        self.assertEqual(new["orb"]["SPY"]["status"], "FORMING")
        self.assertNotIn("result", new["orb"]["SPY"])
        self.assertEqual(new["asof_t"], "9:39")
        new = orb_live.build(frames(self.DAY, 50), {}, datetime(d.year, d.month, d.day, 10, 20, tzinfo=ET))
        o = new["orb"]["SPY"]
        self.assertEqual(o["status"], "BROKE SHORT")
        self.assertEqual(o["result"], "OPEN")
        self.assertFalse(any(e[2] == "TIME" for e in o["exits"]))

    def test_never_backwards(self):
        newer = copy.deepcopy(PREV); newer["asof"] = "2999-01-01"
        self.assertIsNone(orb_live.build(frames(self.DAY, 390), newer, datetime(2026, 11, 18, 6, 0, tzinfo=ET)))
        # same session, fewer bars than already published -> left alone
        self.assertIsNone(orb_live.build(frames(self.DAY, 100), copy.deepcopy(PREV), datetime(2026, 11, 17, 11, 0, tzinfo=ET)))
        self.assertIsNone(orb_live.build({"SPY": None}, copy.deepcopy(PREV)))

    def test_completed_new_session_extends_cum_r_once(self):
        prev = copy.deepcopy(PREV)
        for s in ("SPY", "QQQ"):  # pretend the last published day is the one before
            prev["eq"][s]["d"].pop(); prev["eq"][s]["r"].pop()
        prev["asof"] = "2026-11-16"
        new = orb_live.build(frames(self.DAY, 390), prev, datetime(2026, 11, 18, 6, 0, tzinfo=ET))
        self.assertEqual(new["eq"], PREV["eq"])
        self.assertEqual(new["eq"]["SPY"]["stats"]["tot_r"], PREV["eq"]["SPY"]["stats"]["tot_r"])

    def test_wired_before_orb_status(self):
        s = (ROOT / "pipeline" / "refresh.sh").read_text()
        self.assertLess(s.index("orb_live.py"), s.index("orb_status.py"))
        self.assertNotRegex((DESK / "orb_live.py").read_text(), r"ORB ?(5|30)\b")


class JournalExport(unittest.TestCase):
    CSV = ('"Date","Day","Sym","Root","Setup","D/S","Inst","Side","Type","Qty","Pts","Pt Val","Strike","Entry","Q Out","Exit",'
           '"Q Out P/L","Net","Risk","R","Issue","Equity","Notes"\n'
           '"11/17/2026","Tue","SPX","","x","Day","Call","Long","LO","1","","","$7,320.00","2.60","6.40","10.40","$380.00",'
           '"$780.00","","","","$18,075.97","note"\n,,,,,,,,,,,,,,,,,,,,,,\n')

    def test_parse_matches_published_shape(self):
        t = journal_export.parse(self.CSV)
        self.assertEqual(t, [{"date": "2026-11-17", "sym": "SPX", "root": None, "inst": "Call", "side": "Long", "qty": 1, "pts": None,
                              "pt_val": None, "strike": 7320, "entry": 2.6, "q_out": 6.4, "exit": 10.4, "q_out_pl": 380.0,
                              "net": 780.0, "risk": None, "equity": 18075.97}])
        self.assertEqual(set(t[0]), set(PREV_J["trades"][0]))
        self.assertNotIn("note", json.dumps(t))  # notes/setup columns are never exported

    def test_guards(self):
        self.assertIsNone(journal_export.parse('"Wrong","Header"\n1,2\n'))
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "v2_log.json"; p.write_text(json.dumps(PREV_J))
            import os
            os.environ.pop("JOURNAL_SHEET_ID", None)
            journal_export.main(p)  # no id configured -> untouched
            self.assertEqual(json.loads(p.read_text()), PREV_J)


PREV_J = json.loads((ROOT / "pipeline" / "inputs" / "journal" / "v2_log.json").read_text())


class CommandLive(unittest.TestCase):
    PAGE = (ROOT / "command" / "index.html").read_text()

    def glance(self, h):
        return json.loads(re.search(r'<script id="glance-data" type="application/json">(.*?)</script>', h, re.S).group(1))

    def test_glance_price_only_for_current_session(self):
        G = self.glance(self.PAGE); sess = date.fromisoformat(G["session"])
        ts = pd.Timestamp(f"{sess} 07:05", tz=ET)
        q = lambda: (7400.25, ts)
        h = command_live.patch_glance(self.PAGE, q, datetime(sess.year, sess.month, sess.day, 4, 10, tzinfo=ZoneInfo("America/Los_Angeles")))
        g = self.glance(h)
        self.assertEqual(g["es"]["price"], 7400.25)
        self.assertIn("PT", g["es"]["asof"])
        self.assertEqual({k: v for k, v in g.items() if k != "es"}, {k: v for k, v in G.items() if k != "es"})
        # older quote never replaces a newer one
        self.assertEqual(command_live.patch_glance(h, lambda: (7000.0, ts - pd.Timedelta(hours=1)),
                         datetime(sess.year, sess.month, sess.day, 4, 30, tzinfo=ZoneInfo("America/Los_Angeles"))), h)
        # past plan session: untouched
        later = datetime(sess.year, sess.month, sess.day, 7, 0, tzinfo=ZoneInfo("America/Los_Angeles")) + timedelta(days=1)
        self.assertEqual(command_live.patch_glance(self.PAGE, q, later), self.PAGE)

    def test_bands_sections_replaced_in_place(self):
        h = command_live.patch_bands(self.PAGE)
        for sid in ("z-gg", "z-ut"):
            self.assertEqual(h.count(f'id="{sid}"'), 1)
        self.assertEqual(h.index('id="z-gg"') < h.index('id="z-ut"') < h.index('id="z-fills"'), True)

    def test_quotes_update_and_never_go_backwards(self):
        ts = pd.Timestamp("2999-01-02 10:00", tz=ET)
        q = lambda s: {"last": 1.5, "ref": 1.0, "chg": 0.5, "chg_pct": 50.0, "ts": ts}
        h = command_live.patch_quotes(self.PAGE, q)
        D = [json.JSONDecoder().raw_decode(h[h.index("{", m.end() - 1):])[0] for m in re.finditer(r"const D=", h)]
        D0 = [json.JSONDecoder().raw_decode(self.PAGE[self.PAGE.index("{", m.end() - 1):])[0] for m in re.finditer(r"const D=", self.PAGE)]
        Dq = next(x for x in D if "quotes" in x)
        self.assertEqual(Dq["quotes"]["SPY"]["last"], 1.5)
        self.assertTrue(Dq["quotes"]["SPY"]["asof"].startswith("2999-01-02"))
        self.assertTrue(all(o["last"] == 1.5 for o in Dq["fut"]["quotes"].values()))
        for x, y in zip(D0, D):  # nothing else in the payloads moves
            self.assertEqual({k: v for k, v in x.items() if k not in ("quotes", "fut")}, {k: v for k, v in y.items() if k not in ("quotes", "fut")})
        old = lambda s: {"last": 9.0, "ref": 1.0, "chg": 8.0, "chg_pct": 800.0, "ts": ts - pd.Timedelta(days=1)}
        self.assertEqual(command_live.patch_quotes(h, old), h)
        self.assertEqual(command_live.patch_quotes(self.PAGE, lambda s: None), self.PAGE)

    def test_wired_after_orb_status(self):
        s = (ROOT / "pipeline" / "refresh.sh").read_text()
        self.assertLess(s.index("orb_status.py"), s.index("command_live.py"))
        self.assertLess(s.index("bias_gauge.py --patch"), s.index('"ui_shell"'))


class BiasFreshness(unittest.TestCase):
    def test_stale_inputs_do_not_vote(self):
        import bias_gauge as B
        d = date(2026, 11, 18)
        self.assertTrue(B.fresh("2026-11-17", d)); self.assertFalse(B.fresh("2026-11-06", d)); self.assertFalse(B.fresh(None, d))
        keys = {v[0] for v in B.desk_parts(735.0, d)[0]}
        G = json.loads((DESK / "xnews" / "gamma.json").read_text())
        if not B.fresh(G.get("date"), d):
            self.assertNotIn("FB · SPX", keys)
        LA = (json.loads((DESK / "xnews" / "levels_a" / "levels_a.json").read_text()).get("latest") or {})
        if not B.fresh(LA.get("date"), d):
            self.assertNotIn("IRON LADDER", keys)


if __name__ == "__main__":
    unittest.main()
