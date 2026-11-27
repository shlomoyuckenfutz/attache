"""US equity early-close days (regular session ends 1:00 PM ET). Source: NYSE holidays & trading hours, 2026–2028.
Shared by orb_live, free_gex, calc_im and the Heat collector so every job agrees on when a session is over."""
from datetime import date

EARLY_CLOSE = frozenset({date(2026, 11, 27), date(2026, 12, 24), date(2027, 11, 26), date(2028, 7, 3), date(2028, 11, 24)})


def close_minute(day) -> int:
    """Regular-session close in minutes after midnight ET: 13:00 on early-close days, else 16:00."""
    return 13 * 60 if day in EARLY_CLOSE else 16 * 60

# FOMC policy-decision days (2nd day of each scheduled meeting; 2:00 PM ET statement). Fed calendar as of 11/18/2026;
# the Oct 26–27, 2027 strategy meeting announces no decision, so it is left out.
FOMC_DECISION = frozenset({
    date(2026, 1, 28), date(2026, 3, 18), date(2026, 4, 29), date(2026, 6, 17), date(2026, 7, 29), date(2026, 9, 16),
    date(2026, 10, 28), date(2026, 12, 9),
    date(2027, 1, 27), date(2027, 3, 17), date(2027, 4, 28), date(2027, 6, 9), date(2027, 7, 28), date(2027, 9, 15),
    date(2027, 11, 17), date(2028, 1, 26)})
FOMC_KNOWN_THROUGH = date(2028, 1, 26)


def is_fomc_decision_day(day):
    """True/False inside the known calendar; None past it (callers then fall back to the plan's own wording)."""
    if day is None or day > FOMC_KNOWN_THROUGH:
        return None
    return day in FOMC_DECISION
