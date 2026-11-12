"""Daily 'CPI & SPY levels' and Weekly bias/vol blocks: render for their own date only, every figure as specified,
no source names, no 'error', no empty boxes."""
import json, os, re, unittest
from pathlib import Path
import plan_addenda as A
from tests import test_public_names as N

ROOT = Path(__file__).resolve().parents[3]
DATA = json.loads((ROOT / "pipeline/inputs/plans/addenda.json").read_text())
PD = json.loads((ROOT / "pipeline/inputs/plan.json").read_text())["date"]
DB, WB = A.daily_block(DATA, PD), A.weekly_block(DATA, PD)
txt = lambda h: re.sub(r"\s+", " ", re.sub(r"<[^>]+>", "", h))


class Daily(unittest.TestCase):
    def test_renders_for_thu_with_every_figure(self):
        self.assertEqual(PD, "2026-11-12")
        t = txt(DB)
        self.assertIn("AFTER HOURS, CATALYSTS &amp; SPY LEVELS · THU 11/12", DB)
        for s in ["Nvidia board reported preparing to remove its CEO", "$173.73", "NQ −0.96% (4:02 PM PT)", "SPY 756.41, −0.45% (4:22 PM PT)",
                  "7,619.22 (+1.31%)", "Thu 5:30 AM PT · weekly initial jobless claims", "Thu 9:00 AM PT", "Fri 5:30 AM PT · October producer prices",
                  "SPY 752.72–761.82 (±0.60%)", "7593.86–7654.28", "762.27 dark-pool line", "758.3 all-expiration flip",
                  "759.57 dark-pool line", "750 all-expiration floor", "borderline disturbing"]:
            self.assertIn(s, t, s)

    def test_hidden_on_other_sessions(self):
        self.assertEqual(A.daily_block(DATA, "2026-11-13"), "")
        self.assertEqual(A.daily_block({}, PD), "")
        self.assertEqual(A.daily_block(DATA, None), "")


class Weekly(unittest.TestCase):
    def test_renders_for_week_with_every_figure(self):
        t = txt(WB)
        self.assertIn("WEEK BIAS &amp; VOLATILITY · NOV 9–13", WB)
        for s in ["weekly close above SPY 758", "bias flips bullish", "759.81", "PPI Fri 5:30 AM PT",
                  "board reported preparing to remove the CEO", "698.1 flip", "SPY 751.89–767.73", "−$8.0B (11/20 monthly opex)"]:
            self.assertIn(s, t, s)
        self.assertNotIn("backwardation", WB.lower()); self.assertNotIn("contango", WB.lower())

    def test_hidden_outside_week(self):
        self.assertEqual(A.weekly_block(DATA, "2026-11-16"), "")
        bad = json.loads(json.dumps(DATA)); bad["weekly"]["week_end"] = "2026-11-30"
        self.assertEqual(A.weekly_block(bad, PD), "")


class Wording(unittest.TestCase):
    def test_750_is_gamma_floor_not_put_wall(self):
        t = txt(DB)
        self.assertIn("750 all-expiration floor", t); self.assertNotRegex(t, r"750 put wall|put wall[^·]*750")

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
        for page, blk in (("daily", DB), ("weekly", WB)):
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
            for page, sid, head in (("daily", "cpi-spy-levels", "AFTER HOURS, CATALYSTS & SPY LEVELS"), ("weekly", "week-bias-vol", "WEEK BIAS & VOLATILITY")):
                pg = b.new_page(viewport={"width": 1200, "height": 900})
                errs = []; pg.on("pageerror", lambda e: errs.append(str(e)))
                pg.goto(f"{base}{page}/?cb=1" if base else (ROOT / page / "index.html").as_uri(), wait_until="load")
                r = pg.evaluate(f"""()=>{{const s=document.getElementById('{sid}');if(!s)return null;const b=s.getBoundingClientRect();
                  return {{h:s.querySelector('h2').innerText,t:s.innerText,vis:b.height>40&&b.width>200,
                  empty:[...s.querySelectorAll('li')].filter(li=>[...li.children].some(c=>!c.innerText.trim())).length,n:s.querySelectorAll('li').length}}}}""")
                self.assertIsNotNone(r, page); self.assertTrue(r["h"].startswith(head)); self.assertTrue(r["vis"])
                self.assertEqual(r["empty"], 0); self.assertGreaterEqual(r["n"], 5); self.assertEqual(errs, [])
                self.assertNotRegex(r["t"].lower(), r"\berror\b"); self.assertIsNone(N.strict_rx().search(r["t"]))
                pg.close()
            b.close()


if __name__ == "__main__":
    unittest.main()
