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
    def test_renders_for_tue_with_every_figure(self):
        self.assertEqual(PD, "2026-11-10")
        t = txt(DB)
        self.assertIn("CPI & SPY LEVELS · TUE 11/10".replace("&", "&amp;"), DB)
        for s in ["5:30 AM PT", "MoM only", "0.3% / core 0.2%", "0.4–0.5% / core 0.3%", "0.1–0.2% / core 0.1%", "Fed hike odds",
                  "754.05–755.62", "dark-pool cluster", "757–760", "100-day", "20-week SMA", "~758.6",
                  "750 · 746.77 · 741.26 · 730 put wall", "squeeze into 758–760", "fade a rejection", "daily close above 758",
                  "back toward 741, then the 200-day", "stay flat through the print, trade the reaction"]:
            self.assertIn(s, t.replace(" - ", "–"), s)

    def test_hidden_on_other_sessions(self):
        self.assertEqual(A.daily_block(DATA, "2026-11-11"), "")
        self.assertEqual(A.daily_block({}, PD), "")
        self.assertEqual(A.daily_block(DATA, None), "")


class Weekly(unittest.TestCase):
    def test_renders_for_week_with_every_figure(self):
        t = txt(WB)
        self.assertIn("WEEK BIAS &amp; VOLATILITY · NOV 9–13", WB)
        for s in ["weekly close above SPY 758", "bias flips bullish", "20-day is under the 50-day", "20-week SMA (~711)",
                  "726–727, then 718", "725 for 11/20 monthly opex", "730 put OI for Fri 11/13",
                  "VIX futures front month still above spot", "VIX1D holding above 16"]:
            self.assertIn(s, t, s)
        self.assertNotIn("backwardation", WB.lower())

    def test_hidden_outside_week(self):
        self.assertEqual(A.weekly_block(DATA, "2026-11-16"), "")
        bad = json.loads(json.dumps(DATA)); bad["weekly"]["week_end"] = "2026-11-30"
        self.assertEqual(A.weekly_block(bad, PD), "")


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
            for page, sid, head in (("daily", "cpi-spy-levels", "CPI & SPY LEVELS"), ("weekly", "week-bias-vol", "WEEK BIAS & VOLATILITY")):
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
