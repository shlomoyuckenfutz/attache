"""COMMAND CENTER page (/command/): layout, honesty (every block dated, past-session sweep blocks dimmed), no names,
no source counts, ORB STATUS carried over above Account, phone fit. The page is rebuilt whole by command_center.py."""
import copy, json, os, re, sys, tempfile, unittest, pathlib

ROOT = pathlib.Path(__file__).resolve().parents[3]
DESK = ROOT / "pipeline" / "desk"
PAGE = ROOT / "command" / "index.html"
sys.path.insert(0, str(DESK))
import command_center as CC  # noqa: E402

ORDER = ["now", "ladder", "scen", "pos", "tape", "reads", "topics", "z-orb", "acct", "ctx"]
BANNED = re.compile(r"mancini|smashelito|\bsmash(?:level)?\b|voltick|kttech|traderjonesy|jonesy|substack|newsletter|rebuilt from", re.I)
DATED = re.compile(r"(Mon|Tue|Wed|Thu|Fri|Sat|Sun) \d{1,2}/\d{1,2}|\d{4}-\d{2}-\d{2}|\d{2}-\d{2} \d{2}:\d{2} PT|awaiting update", re.I)


def section_ids(h):
    return re.findall(r'<section class="(?:z|hero)[^"]*" id="([^"]+)"', h)


class StaticChecks(unittest.TestCase):
    def test_no_source_counts_anywhere(self):
        """'dont ever give away our sourses': no rendered or embedded count of sources on any public page."""
        count = re.compile(r"(\$\{[^}]{1,60}\}|'\s*\+\s*[\w.]+\s*\+\s*'|\b\d+)\s*(sources?|srcs?)\b|\bsources agree|\$\{b\.n_sources\}|\"n_sources\"|'×'\+b\.n", re.I)
        for rel in ("command", "overnight", "weekly", "daily", "gammamap", "darkpool", "exposure"):
            p = ROOT / rel / "index.html"
            if p.exists():
                m = count.search(p.read_text())
                self.assertIsNone(m, f"{rel}: {m and m.group(0)}")

    def test_layout_order_with_orb_above_account(self):
        self.assertEqual(section_ids(PAGE.read_text()), ORDER)

    def test_live_not_demo(self):
        t = PAGE.read_text()
        self.assertNotIn('name="robots"', t); self.assertNotIn('class="demo"', t); self.assertNotRegex(t, r"(?i)\bdemo\b")
        self.assertIn("<title>ATTACHÉ — COMMAND CENTER</title>", t)
        self.assertIn('id="ub"', t)  # shared nav shell

    def test_every_section_dated(self):
        t = PAGE.read_text()
        for sid in ORDER:
            if sid == "now":
                continue
            s = re.search(rf'<section class="z[^"]*" id="{sid}"><div class="zh">.*?<span class="asof[^"]*">(.*?)</span>', t, re.S)
            self.assertTrue(s, sid); self.assertRegex(s.group(1), DATED, sid)
        self.assertRegex(re.search(r'id="now".*?<span class="asof">(.*?)</span>', t, re.S).group(1), DATED)

    def test_no_names_error_paper_orb5_orb30(self):
        t = PAGE.read_text()
        self.assertIsNone(BANNED.search(t))
        self.assertNotRegex(t, r"(?i)\berror\b"); self.assertNotRegex(t, r"(?i)\bpaper\b"); self.assertNotRegex(t, r"(?i)\bORB\s*(5|30)\b")
        self.assertNotIn("no data", t.lower())

    def test_no_wire_section(self):
        t = PAGE.read_text()
        self.assertNotIn('id="z-wire"', t); self.assertNotIn("THE WIRE · LAST 5", t)

    def test_refresh_strips_leftover_wire(self):
        import importlib.util
        spec = importlib.util.spec_from_file_location("patch_newswire", DESK / "patch_newswire.py")
        mod = importlib.util.module_from_spec(spec); spec.loader.exec_module(mod)
        with tempfile.TemporaryDirectory() as td:
            cmd = pathlib.Path(td) / "command"; cmd.mkdir()
            leftover = PAGE.read_text().replace("<main>", "<main><style>\n.nw{border:1px solid #232323}</style><section class=\"nw nwt\" id=\"z-wire\"><div class=\"nh\">THE WIRE · LAST 5</div></section><script>(function(){var m=30*60e3;})();</script>", 1)
            (cmd / "index.html").write_text(leftover)
            self.assertTrue(mod.strip_file(cmd / "index.html"))
            out = (cmd / "index.html").read_text()
            self.assertNotIn('id="z-wire"', out); self.assertIn("<main>", out)

    def test_demo_preview_redirects(self):
        t = (ROOT / "command-demo" / "index.html").read_text()
        self.assertIn('url=../command/', t); self.assertNotIn("DEMO", t)


class Builder(unittest.TestCase):
    """The 15-minute refresh rebuilds /command/ from data; it must keep this layout and stay honest about dates."""

    def test_builder_produces_layout(self):
        h = CC.build(CC.load())
        self.assertEqual(section_ids(h), ORDER)
        self.assertIn("const D=", h)  # orb_status.py patches this payload

    def test_past_session_blocks_dimmed_current_ones_not(self):
        S = CC.load(); C = CC.Ctx(S)
        past = copy.deepcopy(S)
        for k in ("plan", "scenarios", "reads"):
            past["sweep"][k]["for_session"] = "2000-01-03"
        h = CC.build(past)
        for sid in ("scen", "reads"):
            self.assertRegex(h, rf'<section class="z old" id="{sid}">')
        self.assertIn("that session has traded", h)
        cur = copy.deepcopy(S)
        for k in ("plan", "scenarios", "reads"):
            cur["sweep"][k]["for_session"] = "2999-01-04"
        h = CC.build(cur)
        for sid in ("scen", "reads"):
            self.assertRegex(h, rf'<section class="z" id="{sid}">')
        self.assertIn(cur["sweep"]["plan"]["headline"], h)

    def test_missing_inputs_say_awaiting_not_error(self):
        h = CC.build({"sweep": {}, "board": {}, "orb": {}, "journal": {}, "im": {}, "on": {}, "bias": {}})
        self.assertEqual(section_ids(h), [s for s in ORDER])
        self.assertIn("awaiting update", h); self.assertNotRegex(h, r"(?i)\berror\b")

    def test_countdown_never_empty(self):
        C = CC.Ctx(CC.load())
        ev = CC.events(C)
        self.assertTrue(any("Regular session opens" in e["n"] for e in ev))
        for e in ev:
            self.assertRegex(e["t"], r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:00Z$"); self.assertTrue(e["pt"].endswith("PT"))


try:
    from playwright.sync_api import sync_playwright
    HAVE_PW = os.path.exists("/usr/bin/google-chrome")
except Exception:
    HAVE_PW = False


@unittest.skipUnless(HAVE_PW, "headless chrome not available")
class RenderedChecks(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.R, cls.errs = {}, []
        with sync_playwright() as p:
            b = p.chromium.launch(executable_path="/usr/bin/google-chrome", args=["--no-sandbox"])
            for name, w in (("desk", 1440), ("phone", 390)):
                pg = b.new_page(viewport={"width": w, "height": 900})
                pg.on("pageerror", lambda e: cls.errs.append(str(e)))
                pg.route(re.compile(r"^https?://(?!127\.0\.0\.1)"), lambda r: r.abort())
                pg.goto(os.environ.get("CMD_URL", PAGE.as_uri()), wait_until="load", timeout=60000)
                pg.wait_for_timeout(1500)
                cls.R[name] = pg.evaluate("""()=>{const W=document.documentElement.clientWidth;
                  return {sw:document.documentElement.scrollWidth, W,
                    over:[...document.querySelectorAll('main *')].filter(e=>{const r=e.getBoundingClientRect();return r.width>0&&r.right>W+1&&!e.closest('.ux-tw,.jump')}).length,
                    cd:document.getElementById('cdn').innerText, orb:[...document.querySelectorAll('#z-orb svg')].length,
                    txt:document.body.innerText}}""")
                pg.close()
            b.close()

    def test_no_script_errors(self):
        self.assertEqual(self.errs, [])

    def test_phone_fit(self):
        r = self.R["phone"]
        self.assertLessEqual(r["sw"], r["W"]); self.assertEqual(r["over"], 0)

    def test_countdown_live(self):
        self.assertRegex(self.R["desk"]["cd"], r"^(\d+d )?\d+h \d{2}m \d{2}s$|^next sweep$")

    def test_orb_status_renders(self):
        self.assertGreaterEqual(self.R["desk"]["orb"], 5)  # four ORB15 charts + cumulative R

    def test_no_error_or_names(self):
        t = self.R["desk"]["txt"]
        self.assertNotRegex(t.lower(), r"\berror\b"); self.assertIsNone(BANNED.search(t)); self.assertNotRegex(t, r"(?i)\bpaper\b")


if __name__ == "__main__":
    unittest.main()
