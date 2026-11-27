"""Daily 'CPI & SPY levels' and Weekly bias/vol blocks: render for their own date only, every figure as specified,
no source names, no 'error', no empty boxes."""
import json, os, re, unittest
from pathlib import Path
import plan_addenda as A
from tests import test_public_names as N

ROOT = Path(__file__).resolve().parents[3]
DATA = json.loads((ROOT / "pipeline/inputs/plans/addenda.json").read_text())
PD = "2026-11-27"  # addenda session; Daily plan.json moves with the live date
DB, WB = A.daily_block(DATA, PD), A.weekly_block(DATA, PD)
txt = lambda h: re.sub(r"\s+", " ", re.sub(r"<[^>]+>", "", h))


class Daily(unittest.TestCase):
    def test_renders_for_mon_with_every_figure(self):
        self.assertEqual(PD, "2026-11-27")
        t = txt(DB)
        self.assertIn("HOLIDAY CLOSE, CATALYSTS &amp; SPY LEVELS · FRI 11/27", DB)
        for s in ["SPX 7,182.78", "SPY 716.70", "QQQ 633.93", "ES 7196.75", "VIX 26.81",
                  "Monday ES high 7313.25", "flushed to 6982.50", "GDP 4.3%", "core PCE 3.3%",
                  "Thursday closed", "Friday stocks close 10:00 AM PT", "715.02 nearest dark-pool line",
                  "695.45 Wednesday low", "686.75 Friday 11/20 low", "jobs report Fri Dec 4"]:
            self.assertIn(s, t, s)

    def test_hidden_on_other_sessions(self):
        self.assertEqual(A.daily_block(DATA, "2026-11-25"), "")
        self.assertEqual(A.daily_block({}, PD), "")
        self.assertEqual(A.daily_block(DATA, None), "")


class Weekly(unittest.TestCase):
    def test_renders_for_week_with_every_figure(self):
        wb = A.weekly_block(DATA, "2026-11-23")
        t = txt(wb)
        self.assertIn("WEEK BIAS &amp; VOLATILITY · NOV 23–27", wb)
        for s in ["ES accepted over 7211–23, then 7240–45", "VIX 26.81",
                  "Wed 5:30 AM PT: GDP 4.3%", "Thu 11/26 closed", "stocks close 10:00 AM PT", "8 of the last 9 years",
                  "SPX 7066.71–7298.85 (±1.62%)"]:
            self.assertIn(s, t, s)
        self.assertEqual(A.weekly_block(DATA, "2026-11-27"), wb)
        self.assertNotIn("backwardation", wb.lower()); self.assertNotIn("contango", wb.lower())

    def test_hidden_outside_week(self):
        self.assertEqual(A.weekly_block(DATA, "2026-11-20"), ""); self.assertEqual(A.weekly_block(DATA, "2026-11-30"), "")
        bad = json.loads(json.dumps(DATA)); bad["weekly"]["week_end"] = "2026-12-04"
        self.assertEqual(A.weekly_block(bad, "2026-11-23"), "")


class Wording(unittest.TestCase):
    def test_biggest_strike_not_called_a_put_wall(self):
        t = txt(DB)
        self.assertIn("700 put wall", t)
        self.assertNotRegex(t, r"Friday.{0,40}700 put wall|Fri 11/20.{0,40}put wall 700")

    def test_stale_spy_awaiting_line_gone_from_source_and_page(self):
        import build_daily
        plan_txt = (ROOT / "pipeline/inputs/plan.json").read_text()
        page = (ROOT / "daily/index.html").read_text()
        for h in (plan_txt, page):
            self.assertNotIn("No SPY intraday levels", h)
            self.assertNotRegex(h, r"SPY / QQQ / NQ intraday levels: awaiting")
        lss = build_daily.lss_html(json.loads(plan_txt))
        self.assertNotIn("SPY intraday", lss); self.assertIn("General lean:", lss)
        self.assertNotRegex(txt(lss), r"General lean:\s*(Bearish|Bullish|$)")  # line still has its text
        # no empty list rows / paragraphs left on the Daily page
        self.assertNotRegex(page, r"<li>\s*(<span[^>]*>\s*</span>\s*)*</li>|<p>\s*</p>|<span class=\"vv\">\s*</span>")


class Hygiene(unittest.TestCase):
    def test_no_names_no_error_no_empty(self):
        rx = N.strict_rx()
        for h in (DB, WB):
            self.assertIsNone(rx.search(h)); self.assertNotRegex(h.lower(), r"\berror\b")
            for lb, vv in re.findall(r'<span class="lb">(.*?)</span><span class="vv">(.*?)</span>', h):
                self.assertTrue(txt(lb).strip() and txt(vv).strip())
        bad = json.loads(json.dumps(DATA)); bad["daily"]["rows"].append({"k": "res", "lb": "Empty", "t": "  "})
        self.assertNotIn("Empty", A.daily_block(bad, PD))

    def test_patch_idempotent_and_placed_before_positioning(self):
        import tempfile
        for page, blk in (("daily", DB), ("weekly", A.weekly_block(DATA, "2026-11-23"))):
            src = (ROOT / page / "index.html").read_text()
            with tempfile.TemporaryDirectory() as td:
                p = Path(td) / "i.html"; p.write_text(src)
                A.patch(p, blk); A.patch(p, blk); t = p.read_text()
                self.assertEqual(t.count('id="cpi-spy-levels"' if page == "daily" else 'id="week-bias-vol"'), 1)
                if "<!--GAMMABOARD-->" in t:
                    self.assertLess(t.find(A.MK), t.find("<!--GAMMABOARD-->"))


try:
    from playwright.sync_api import sync_playwright
    HAVE = os.path.exists("/usr/bin/google-chrome")
except Exception:
    HAVE = False


@unittest.skipUnless(HAVE, "headless chrome not available")
class Rendered(unittest.TestCase):
    def test_blocks_render_on_pages(self):
        base = os.environ.get("SITE_URL")
        with sync_playwright() as p:
            b = p.chromium.launch(executable_path="/usr/bin/google-chrome", args=["--no-sandbox"])
            for page, sid, head in (("daily", "cpi-spy-levels", "CATALYSTS & SPY LEVELS"), ("weekly", "week-bias-vol", "WEEK BIAS & VOLATILITY")):
                pg = b.new_page(viewport={"width": 1200, "height": 900})
                errs = []; pg.on("pageerror", lambda e: errs.append(str(e)))
                pg.goto(f"{base}{page}/?cb=1" if base else (ROOT / page / "index.html").as_uri(), wait_until="load")
                r = pg.evaluate(f"""()=>{{const s=document.getElementById('{sid}');if(!s)return null;const b=s.getBoundingClientRect();
                  return {{h:s.querySelector('h2').innerText,t:s.innerText,vis:b.height>40&&b.width>200,
                  empty:[...s.querySelectorAll('li')].filter(li=>[...li.children].some(c=>!c.innerText.trim())).length,n:s.querySelectorAll('li').length}}}}""")
                live_date = json.loads((ROOT / "pipeline/inputs/plan.json").read_text())["date"]
                if page == "daily" and live_date != DATA["daily"]["session"]:
                    self.assertIsNone(r, "daily addenda must stay hidden off its session")
                    pg.close(); continue
                self.assertIsNotNone(r, page); self.assertIn(head, r["h"]); self.assertTrue(r["vis"])
                self.assertEqual(r["empty"], 0); self.assertGreaterEqual(r["n"], 5); self.assertEqual(errs, [])
                self.assertNotRegex(r["t"].lower(), r"\berror\b"); self.assertIsNone(N.strict_rx().search(r["t"]))
                pg.close()
            b.close()


if __name__ == "__main__":
    unittest.main()
