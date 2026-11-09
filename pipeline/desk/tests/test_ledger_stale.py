import sys, unittest, datetime as dt
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from overnight_panels import _ledger_stale_tag as tag

class T(unittest.TestCase):
    def test_stale_and_fresh(self):
        mon = dt.date(2026, 11, 9)
        self.assertEqual(tag("2026-11-05", mon), " · awaiting update (last issue 2026-11-05)")
        self.assertEqual(tag("2026-11-06", mon), "")   # Friday issue is current on Monday
        self.assertEqual(tag("2026-11-09", dt.date(2026, 11, 10)), "")
        self.assertEqual(tag("bad", mon), " · awaiting update")

if __name__ == "__main__":
    unittest.main()
