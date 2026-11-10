"""Command page brief/glance checks: removed tiles gone, every cell dated, honest status, no names."""
import json, os, re, unittest, pathlib

ROOT = pathlib.Path(__file__).resolve().parents[3]
PAGE = ROOT / "command" / "index.html"
REMOVED = ["NEWS BIAS", "GAMMA ·", "TOP CONFLUENCE", "ORB15 ·", "NEAREST ES", "BLAST RADIUS ·"]
EXPECTED = ["TODAY'S PLAN · ES", "IMPLIED MOVE", "CATALYSTS", "OVERNIGHT · ES", "FUTURES · ES", "THE WIRE"]
BANNED = re.compile(r"mancini|smashelito|\bsmash(?:level)?\b|voltick|kttech|traderjonesy|jonesy|substack|newsletter", re.I)
DATED = re.compile(r"(Mon|Tue|Wed|Thu|Fri|Sat|Sun) Nov \d|Nov \d+–\d+|\d{4}-\d{2}-\d{2}|awaiting", re.I)


def glance_data():
    t = PAGE.read_text()
    m = re.search(r'<script id="glance-data" type="application/json">(.*?)</script>', t, re.S)
    return json.loads(m.group(1))


class StaticChecks(unittest.TestCase):
    def test_brief_code_has_no_removed_tiles(self):
        t = PAGE.read_text()
        s = t.index("window.drawBrief=t=>{"); body = t[s:t.index("$('#brief').innerHTML", s)]
        for r in REMOVED:
            self.assertNotIn(r, body.upper(), r)
        self.assertNotIn("window.imTile", t)

    def test_glance_data_honest(self):
        G = glance_data()
        es = G["es"]
        if es["price"] is None:
            self.assertIsNone(es["asof"]); self.assertIn("awaiting update", es["status"])
            self.assertRegex(es["last_data"], r"^\d{4}-\d{2}-\d{2}$")
        else:
            self.assertTrue(es["asof"])
        self.assertEqual(G["session"], "2026-11-10")
        for c in G["catalysts"]["items"]:
            self.assertRegex(c["utc"], r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:00Z$"); self.assertTrue(c["pt"].endswith("PT"))
        dn = G["im"]["daily_next"]
        self.assertTrue(("lo" in dn) or dn.get("status") == "awaiting tonight's post")
        self.assertIsNone(G["overnight"]["high"]) if "in progress" in G["overnight"]["status"] else None
        self.assertFalse(BANNED.search(json.dumps(G, ensure_ascii=False)))


try:
    from playwright.sync_api import sync_playwright
    HAVE_PW = os.path.exists("/usr/bin/google-chrome")
except Exception:
    HAVE_PW = False


@unittest.skipUnless(HAVE_PW, "headless chrome not available")
class RenderedChecks(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with sync_playwright() as p:
            b = p.chromium.launch(executable_path="/usr/bin/google-chrome", args=["--no-sandbox"])
            pg = b.new_page(viewport={"width": 1440, "height": 1000})
            cls.errs = []
            pg.on("pageerror", lambda e: cls.errs.append(str(e)))
            pg.goto(os.environ.get("CMD_URL", PAGE.as_uri()), wait_until="load", timeout=60000)
            pg.wait_for_timeout(2000)
            cls.R = pg.evaluate("""()=>({
              glance:[...document.querySelectorAll('#glance .gc')].map(c=>({k:c.querySelector('.gk').innerText, t:c.innerText})),
              tiles:[...document.querySelectorAll('#brief .tile')].map(c=>({h:c.querySelector('h4').innerText, d:(c.querySelector('h4 span')||{}).innerText||'', t:c.innerText, body:c.innerText.replace(c.querySelector('h4').innerText,'').trim()})),
              cd:(document.getElementById('glCd')||{}).innerText||'', qs:document.getElementById('qs').innerText,
              cols:getComputedStyle(document.getElementById('brief')).gridTemplateColumns.split(' ').length})""")
            b.close()

    def test_no_script_errors(self):
        self.assertEqual(self.errs, [])

    def test_tiles_exact_and_dated(self):
        hs = [t["h"].split("\n")[0].upper() for t in self.R["tiles"]]
        for x in EXPECTED:
            self.assertTrue(any(h.startswith(x) for h in hs), (x, hs))
        for r in REMOVED:
            self.assertFalse(any(h.startswith(r) for h in hs), r)
        for t in self.R["tiles"]:
            self.assertRegex(t["d"] + " " + t["body"], DATED, t["h"])

    def test_no_empty_cells(self):
        self.assertEqual(len(self.R["tiles"]) % self.R["cols"], 0, "partial grid row")
        for t in self.R["tiles"]:
            self.assertTrue(t["body"], t["h"])
        self.assertEqual(len(self.R["glance"]), 4)
        for g in self.R["glance"]:
            self.assertTrue(g["t"].replace(g["k"], "").strip(), g["k"]); self.assertRegex(g["t"], DATED)

    def test_futures_es_honest(self):
        f = [t for t in self.R["tiles"] if t["h"].upper().startswith("FUTURES · ES")][0]
        G = glance_data()
        if G["es"]["price"] is None:
            self.assertIn("awaiting update · last data " + G["es"]["last_data"], f["t"])
            self.assertNotIn("7571", f["t"]); self.assertNotIn("7571", self.R["qs"])

    def test_countdown_live(self):
        self.assertRegex(self.R["cd"], r"(in (\d+h )?\d+m \d{2}s|released)$")

    def test_no_error_or_names(self):
        txt = json.dumps(self.R, ensure_ascii=False)
        self.assertNotRegex(txt.lower(), r"\berror\b")
        self.assertIsNone(BANNED.search(txt))


if __name__ == "__main__":
    unittest.main()
