import json, sys, tempfile, unittest
from pathlib import Path
DESK = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(DESK))
import keep_newest_im as kn

SYM = {"SPY": {"daily": {"lower": 1, "upper": 2}}}


def put(p, stamp, symbols=SYM):
    p.write_text(json.dumps({"generated_pt": stamp, "symbols": symbols}))


class KeepNewest(unittest.TestCase):
    def setUp(self):
        self.d = Path(tempfile.mkdtemp()); self.src = self.d / "src.json"; self.dst = self.d / "dst.json"

    def stamp(self):
        return json.loads(self.dst.read_text())["generated_pt"]

    def test_older_inputs_never_overwrite_newer_snapshot(self):
        put(self.src, "2026-11-05 20:55 PT"); put(self.dst, "2026-11-21 04:32 PT")
        self.assertFalse(kn.keep_newest(self.src, self.dst))
        self.assertEqual(self.stamp(), "2026-11-21 04:32 PT")

    def test_newer_inputs_replace_snapshot(self):
        put(self.src, "2026-11-21 04:32 PT"); put(self.dst, "2026-11-05 20:55 PT")
        self.assertTrue(kn.keep_newest(self.src, self.dst))
        self.assertEqual(self.stamp(), "2026-11-21 04:32 PT")

    def test_missing_snapshot_is_filled(self):
        put(self.src, "2026-11-05 20:55 PT")
        self.assertTrue(kn.keep_newest(self.src, self.dst))

    def test_empty_source_never_replaces(self):
        put(self.src, "2026-11-22 09:00 PT", symbols={}); put(self.dst, "2026-11-21 04:32 PT")
        self.assertFalse(kn.keep_newest(self.src, self.dst))
        self.assertEqual(self.stamp(), "2026-11-21 04:32 PT")


if __name__ == "__main__":
    unittest.main()
