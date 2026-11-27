"""Free option-chain fallbacks (expected moves, Heat), early-close session end, and the FOMC catalyst line.
Offline: network calls are replaced with stubs."""
import importlib, json, sys, unittest, urllib.error
from datetime import date, datetime
from pathlib import Path
from unittest import mock
from zoneinfo import ZoneInfo

import pandas as pd

DESK = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(DESK)); sys.path.insert(0, str(DESK / "scripts")); sys.path.insert(0, str(DESK / "xnews" / "implied_move"))
import market_calendar as MC, orb_live, build_daily  # noqa: E402

ET = ZoneInfo("America/New_York")


def frame(day, n, px=100.0):
    t0 = pd.Timestamp(f"{day} 09:30", tz=ET)
    idx = pd.DatetimeIndex([t0 + pd.Timedelta(minutes=i) for i in range(n)])
    return pd.DataFrame({"Open": px, "High": px + 0.1, "Low": px - 0.1, "Close": px, "Volume": 0}, index=idx)


class EarlyClose(unittest.TestCase):
    def test_calendar(self):
        self.assertEqual(MC.close_minute(date(2026, 11, 27)), 780)
        self.assertEqual(MC.close_minute(date(2026, 12, 24)), 780)
        self.assertEqual(MC.close_minute(date(2026, 11, 30)), 960)
        self.assertNotIn(date(2027, 12, 24), MC.EARLY_CLOSE)  # a full holiday in 2027, not a half day

    def test_half_day_final_at_105_pm_et(self):
        fr = {k: frame("2026-11-27", 210) for k in ("SPY", "QQQ", "ES", "SPX")}
        r = orb_live.build(fr, {}, now=datetime(2026, 11, 27, 13, 6, tzinfo=ET))
        self.assertIsNone(r["asof_t"])  # session complete
        r = orb_live.build(fr, {}, now=datetime(2026, 11, 27, 13, 0, tzinfo=ET))
        self.assertIsNotNone(r["asof_t"])  # still inside the 5-minute settle window

    def test_normal_day_unchanged(self):
        fr = {k: frame("2026-11-30", 210) for k in ("SPY", "QQQ", "ES", "SPX")}
        r = orb_live.build(fr, {}, now=datetime(2026, 11, 30, 13, 6, tzinfo=ET))
        self.assertIsNotNone(r["asof_t"])


class FomcLine(unittest.TestCase):
    LINE = "FOMC decision"

    def cat(self, d, acts):
        return " ".join(build_daily.catalysts({"date": d, "actionable": acts, "bias": {"reason": ""}}))

    def test_mention_of_next_meeting_is_not_a_decision_day(self):
        self.assertNotIn(self.LINE, self.cat("2026-11-30", ["FOMC Dec 8–9 (quiet period)."]))

    def test_decision_day_gets_the_line(self):
        self.assertIn(self.LINE, self.cat("2026-12-09", ["CPI tomorrow."]))

    def test_past_known_calendar_needs_explicit_same_day_wording(self):
        self.assertIn(self.LINE, self.cat("2028-03-15", ["FOMC decision today."]))
        self.assertNotIn(self.LINE, self.cat("2028-03-14", ["FOMC next week."]))


def yf_payload(S=100.0):
    return {"timestamp": "2026-11-27 20:00:00", "source": "yahoo",
            "data": {"current_price": S, "price_change": 1.0, "price_change_percent": 1.0,
                     "options": [{"option": f"SPY261130{cp}{int(k*1000):08d}", "open_interest": 1000.0, "gamma": 0.05, "iv": 0.2,
                                  "volume": 10.0, "delta": 0.5 if cp == "C" else -0.5, "vega": 0.1, "bid": 1.0, "ask": 1.2,
                                  "last_trade_price": 1.1, "change": 0.0} for k in (98, 99, 100, 101, 102) for cp in "CP"]}}


class HeatFallback(unittest.TestCase):
    def setUp(self):
        import exposure_collector as X
        self.X = importlib.reload(X)

    def test_cboe_refusal_falls_back_and_stops_asking(self):
        X = self.X; calls = []

        def refuse(*a, **k):
            calls.append(1); raise urllib.error.HTTPError("u", 403, "Forbidden", None, None)
        with mock.patch.object(X.urllib.request, "urlopen", refuse), mock.patch.object(X, "_fetch_yf", lambda s, r: yf_payload()):
            raw, root = X.fetch_chain("SPY")
            self.assertEqual(raw["source"], "yahoo"); self.assertEqual(root, "SPY")
            X.fetch_chain("QQQ")
            self.assertEqual(len(calls), 1)  # CBOE asked once per run after a refusal
            with self.assertRaises(RuntimeError):
                X.fetch_chain("GME")  # outside the limited free board

    def test_compute_symbol_on_fallback_payload(self):
        X = self.X
        with mock.patch.object(X, "fetch_chain", lambda s: (yf_payload(), "SPY")):
            pack = X.compute_symbol("SPY", datetime(2026, 11, 27, 15, 0, tzinfo=ET))
        self.assertTrue(pack)

    def test_market_closed_after_half_day(self):
        self.assertEqual(self.X.market_state(datetime(2026, 11, 27, 13, 30, tzinfo=ET)), "ah")
        self.assertEqual(self.X.market_state(datetime(2026, 11, 30, 13, 30, tzinfo=ET)), "open")


class ExpectedMoveFallback(unittest.TestCase):
    def test_runs_without_keys_and_uses_free_chain(self):
        import os
        with mock.patch.dict(os.environ, {}, clear=False):
            for k in ("ALPACA_API_KEY", "ALPACA_SECRET_KEY", "ALPACA_API_SECRET"):
                os.environ.pop(k, None)
            import calc_im
            calc_im = importlib.reload(calc_im)
        self.assertIsNone(calc_im.H)
        rows = {728.0: {"C": {"mid": 4.4, "bid": 4.3, "ask": 4.5, "iv": None}, "P": {"mid": 4.25, "bid": 4.2, "ask": 4.3, "iv": None}}}
        with mock.patch.object(calc_im, "yahoo_chain", lambda t, e, s: (rows, "free chain")):
            st = calc_im.straddle("SPY", date(2026, 11, 30), 728.32, datetime(2026, 11, 27, 15, 0, tzinfo=ET))
        self.assertEqual((st["straddle"], st["source"]), (8.65, "free chain"))

    def test_half_day_rolls_expiry_after_close(self):
        import calc_im
        d, w = calc_im.expiries(datetime(2026, 11, 27, 13, 30, tzinfo=ET))
        self.assertEqual((d, w), (date(2026, 11, 30), date(2026, 12, 4)))
        d, w = calc_im.expiries(datetime(2026, 11, 27, 12, 30, tzinfo=ET))
        self.assertEqual(d, date(2026, 11, 27))


if __name__ == "__main__":
    unittest.main()
