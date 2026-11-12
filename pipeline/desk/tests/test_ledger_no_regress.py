"""A class-A refresh must not replace a newer Night Ledger with an older issue."""
import importlib.util
import unittest
from pathlib import Path

import overnight_panels as P

_PARSE = Path(__file__).resolve().parents[1] / "xnews/ledger/ledger_parse.py"
_spec = importlib.util.spec_from_file_location("ledger_parse", _PARSE)
ledger_parse = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(ledger_parse)

BLOCK_1111 = (
    '<div class="dp full"><h3>NIGHT LEDGER · 2026-11-11</h3>'
    '<div class="q"><i>NEXT-DAY CALL</i> <span class="tg off">DOWN</span></div>'
    '<div class="q"><i>BASE CASE</i> come back to close the gap and revisit 750, '
    'with a fight expected between 753 and 750.</div></div>'
)
BLOCK_1109 = (
    '<div class="dp full"><h3>NIGHT LEDGER · 2026-11-09 · awaiting update (last issue 2026-11-09)</h3>'
    '<div class="q"><i>NEXT-DAY CALL</i> <span class="tg in">FLAT</span></div>'
    '<div class="q"><i>BASE CASE</i> it depends on CPI tomorrow.</div></div>'
)


class ParseKeepsNewer(unittest.TestCase):
    def test_curated_same_date_kept(self):
        prev = {"date": "2026-11-11", "curated": True, "direction": "DOWN"}
        self.assertTrue(ledger_parse.should_keep_existing(prev, "2026-11-11"))

    def test_older_parse_does_not_replace_newer_json(self):
        prev = {"date": "2026-11-11", "direction": "DOWN"}
        self.assertTrue(ledger_parse.should_keep_existing(prev, "2026-11-09"))

    def test_later_date_is_allowed(self):
        prev = {"date": "2026-11-11", "curated": True, "direction": "DOWN"}
        self.assertFalse(ledger_parse.should_keep_existing(prev, "2026-11-12"))

    def test_empty_prev_not_kept(self):
        self.assertFalse(ledger_parse.should_keep_existing({}, "2026-11-09"))
        self.assertFalse(ledger_parse.should_keep_existing(None, "2026-11-09"))


class PageKeepsNewer(unittest.TestCase):
    def test_refresh_cannot_regress_ledger_date(self):
        kept = P.pick_ledger_html("2026-11-09", BLOCK_1109, BLOCK_1111)
        self.assertIn("NIGHT LEDGER · 2026-11-11", kept)
        self.assertIn("DOWN", kept)
        self.assertIn("close the gap", kept)
        self.assertNotIn("2026-11-09", kept)
        self.assertNotIn("awaiting update", kept)

    def test_later_dated_ledger_still_replaces(self):
        newer = BLOCK_1111.replace("2026-11-11", "2026-11-12")
        kept = P.pick_ledger_html("2026-11-12", newer, BLOCK_1111)
        self.assertIn("NIGHT LEDGER · 2026-11-12", kept)
        self.assertNotIn("NIGHT LEDGER · 2026-11-11", kept)

    def test_equal_date_uses_incoming(self):
        incoming = BLOCK_1111.replace("close the gap", "updated same-day take")
        kept = P.pick_ledger_html("2026-11-11", incoming, BLOCK_1111)
        self.assertIn("updated same-day take", kept)
