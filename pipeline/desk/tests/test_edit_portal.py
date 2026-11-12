"""/edit/ portal + manual text overrides: registry valid, loader baked into every page, Everett's locked text
applied on top of the pipeline text, releases restore it, nothing banned can be saved, nothing links to /edit/."""
import functools, http.server, json, os, re, shutil, sys, tempfile, threading, unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
DESK = ROOT / "pipeline/desk"
sys.path.insert(0, str(DESK))
import apply_overrides as A  # noqa: E402
import site_sanitize as S  # noqa: E402

SEC = json.loads((ROOT / "content/sections.json").read_text())
OVR = json.loads((ROOT / "content/overrides.json").read_text())
MODES = {"text", "list", "numbered"}


def guard_hits(text):
    return [r["why"] for r in A.guard_rules()["rules"] if re.search(r["re"], text, re.I)]


class Static(unittest.TestCase):
    def test_registry_valid(self):
        ids = [s["id"] for s in SEC["sections"]]
        self.assertEqual(len(ids), len(set(ids)))
        for s in SEC["sections"]:
            self.assertIn(s["mode"], MODES, s["id"])
            self.assertTrue(s["steps"] and all(st.get("sel") for st in s["steps"]), s["id"])
            self.assertTrue(set(s["pages"]) <= set(SEC["pages"]), s["id"])
            self.assertIn(s.get("expiry", "day"), {"day", "week", "none"}, s["id"])
        # data blocks stay pipeline-owned: no key-level, pivot or table sections
        self.assertFalse([i for i in ids if re.search(r"key.?level|pivot|dark.?pool|orb|hourly", i)])

    def test_overrides_file_valid_and_clean(self):
        self.assertIsInstance(OVR.get("overrides"), dict)
        known = {s["id"] for s in SEC["sections"]}
        for k, o in OVR["overrides"].items():
            self.assertIn(k, known)
            self.assertIsInstance(o.get("text"), str)
            self.assertTrue(o.get("set_at"))
            self.assertEqual(guard_hits(o["text"]), [], k)

    def test_every_page_has_one_current_loader_block(self):
        now = datetime.now(timezone.utc)
        for page, rel in SEC["pages"].items():
            t = (ROOT / rel).read_text(encoding="utf-8")
            self.assertEqual(t.count(A.MARK), 2, page)
            state, js = A.read_block(t)
            self.assertIsNotNone(state, page)
            self.assertEqual(js, A.inline_js((ROOT / "content/edit-overrides.js").read_text()), page + ": rerun apply_overrides.py")
            self.assertEqual([s["id"] for s in state["sections"]], [s["id"] for s in SEC["sections"] if page in s["pages"]], page)
            want = A.page_state(SEC, OVR["overrides"], page, now)["overrides"]
            for k, v in want.items():  # every active lock is baked (expired extras are ignored by the page)
                self.assertEqual(state["overrides"].get(k), v, f"{page}:{k} not baked; run apply_overrides.py")

    def test_apply_is_idempotent_and_additive(self):
        with tempfile.TemporaryDirectory() as td:
            site = Path(td)
            for rel in list(SEC["pages"].values()) + ["content/sections.json", "content/overrides.json", "content/edit-overrides.js"]:
                (site / rel).parent.mkdir(parents=True, exist_ok=True); shutil.copy(ROOT / rel, site / rel)
            A.main(site); once = {r: (site / r).read_text() for r in SEC["pages"].values()}
            A.main(site); self.assertEqual(once, {r: (site / r).read_text() for r in SEC["pages"].values()})
            for r in SEC["pages"].values():
                strip = lambda s: re.sub(re.escape(A.MARK) + ".*?" + re.escape(A.MARK), "", s, flags=re.S)
                self.assertEqual(strip(once[r]), strip((ROOT / r).read_text()))

    def test_sanitizer_and_scrub_leave_block_alone(self):
        rx = re.compile(r"(?i)\bpaper(?:\s+trading)?\b|\bORB\s*(?:5|30)\b| {2,}")
        for rel in SEC["pages"].values():
            t = (ROOT / rel).read_text(encoding="utf-8")
            b = re.search(re.escape(A.MARK) + ".*?" + re.escape(A.MARK), t, re.S).group(0)
            self.assertEqual(S.clean(b), b, rel)
            self.assertIsNone(rx.search(b), rel)

    def test_refresh_runs_apply_before_sanitize(self):
        t = (ROOT / "pipeline/refresh.sh").read_text()
        self.assertLess(t.index('python3 apply_overrides.py'), t.index('run "site_sanitize"'))
        self.assertLess(t.index('run "ui_shell"'), t.index('python3 apply_overrides.py'))
        self.assertNotIn("content/overrides.json", re.sub(r"#.*", "", t))  # the pipeline never writes the lock file

    def test_guard_file_in_sync(self):
        self.assertEqual(json.loads((DESK / "edit_guard.json").read_text()), A.guard_rules())
        for bad in ["see the newsletter", "ORB5 broke", "feed error", "via x.com/someone", "<b>hi</b>"]:
            self.assertTrue(guard_hits(bad), bad)
        self.assertEqual(guard_hits("Hold 7625 → 7650–55; **reclaim 7655** opens 7687–90 (target)."), [])

    def test_edit_page_private_and_unlinked(self):
        e = (ROOT / "edit/index.html").read_text()
        self.assertRegex(e, r'<meta name="robots" content="noindex')
        self.assertNotRegex(e.lower(), r"\berror\b")
        for p in ROOT.rglob("*.html"):
            rel = str(p.relative_to(ROOT))
            if rel.startswith((".git/", "pipeline/", "edit/")):
                continue
            self.assertNotRegex(p.read_text(encoding="utf-8", errors="replace"), r'href=["\'][^"\']*\bedit/', rel)

    def test_no_token_committed(self):
        rx = re.compile(r"github_pat_[A-Za-z0-9_]{20,}|gh[pousr]_[A-Za-z0-9]{30,}")
        for d in ("content", "edit", "pipeline/desk"):
            for p in (ROOT / d).rglob("*"):
                if p.is_file() and p.suffix in {".json", ".js", ".html", ".py", ".md", ".txt"}:
                    self.assertIsNone(rx.search(p.read_text(encoding="utf-8", errors="replace")), str(p))


try:
    from playwright.sync_api import sync_playwright
    HAVE_PW = os.path.exists("/usr/bin/google-chrome")
except Exception:
    HAVE_PW = False


def serve(root):
    class Quiet(http.server.SimpleHTTPRequestHandler):
        def log_message(self, *a):
            pass
    h = functools.partial(Quiet, directory=str(root))
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), h)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv


def site_copy(td, overrides):
    site = Path(td)
    for rel in list(SEC["pages"].values()) + ["content/sections.json", "content/edit-overrides.js", "edit/index.html", "pipeline/desk/edit_guard.json"]:
        (site / rel).parent.mkdir(parents=True, exist_ok=True); shutil.copy(ROOT / rel, site / rel)
    (site / "content/overrides.json").write_text(json.dumps({"version": 1, "overrides": overrides}))
    A.main(site)
    return site


@unittest.skipUnless(HAVE_PW, "headless chrome not available")
class Rendered(unittest.TestCase):
    NOW = datetime.now(timezone.utc)
    OV = {
        "lss.bearish": {"text": "Lose 7625 and the 7596–7600 shelf is next.", "set_at": NOW.isoformat()},
        "daily.gameplan": {"text": "Wait for the open.\n**Long** a 7625 hold.\nFlat into PPI.", "set_at": NOW.isoformat()},
        "weekly.bias": {"text": "Manual weekly bias line.", "set_at": NOW.isoformat(), "expires": (NOW + timedelta(days=2)).isoformat()},
        "command.tile.flow": {"text": "Manual flow note.", "set_at": NOW.isoformat()},
        "overnight.ledger.base": {"text": "Manual base case.", "set_at": NOW.isoformat()},
        "daily.bias": {"text": "Expired text must not show.", "set_at": NOW.isoformat(), "expires": (NOW - timedelta(hours=1)).isoformat()},
    }

    @classmethod
    def setUpClass(cls):
        cls.td = tempfile.mkdtemp(); site = site_copy(cls.td, cls.OV); cls.srv = serve(site)
        base = f"http://127.0.0.1:{cls.srv.server_address[1]}/"
        cls.R, cls.errs = {}, []
        with sync_playwright() as p:
            b = p.chromium.launch(executable_path="/usr/bin/google-chrome", args=["--no-sandbox"])
            ctx = b.new_context(viewport={"width": 1440, "height": 1000})
            ctx.route(re.compile(r"^https://(fonts\.|api\.github)"), lambda r: r.abort())
            def grab(url, js, wait=1500):
                pg = ctx.new_page(); pg.on("pageerror", lambda e: cls.errs.append(f"{url}: {e}"))
                pg.goto(base + url, wait_until="load", timeout=60000); pg.wait_for_timeout(wait)
                out = pg.evaluate(js); pg.close(); return out
            secs = json.dumps(SEC["sections"])
            for page in SEC["pages"]:
                cls.R[page] = grab(f"{page}/", "()=>({t:document.body.innerText, tiles:document.querySelectorAll('#brief .tile').length, applied:window.AttacheOV.applied()})")
                cls.R[page + "_off"] = grab(f"{page}/?ov=off", f"""()=>{{const S={secs};return {{t:document.body.innerText,
                    missing:S.filter(s=>s.pages[0]==='{page}'&&!s.optional&&!window.AttacheOV.locate(document,s.steps)).map(s=>s.id),
                    empty:S.filter(s=>s.pages[0]==='{page}'&&window.AttacheOV.locate(document,s.steps)&&!window.AttacheOV.text(window.AttacheOV.locate(document,s.steps),s)).map(s=>s.id)}}}}""")
            cls.R["edit"] = grab("edit/", "()=>({cards:document.querySelectorAll('.card').length, signin:!document.getElementById('signin').hidden, t:document.body.innerText, filled:[...document.querySelectorAll('.card textarea')].filter(t=>t.value.trim()).length})", 6000)
            # release path: page baked with a lock, live file no longer has it -> pipeline text comes back
            (site / "content/overrides.json").write_text(json.dumps({"version": 1, "overrides": {}}))
            cls.R["released"] = grab("daily/", "()=>({t:document.body.innerText, applied:window.AttacheOV.applied()})")
            b.close()

    @classmethod
    def tearDownClass(cls):
        cls.srv.shutdown(); shutil.rmtree(cls.td, ignore_errors=True)

    def test_no_script_errors(self):
        self.assertEqual(self.errs, [])

    def test_every_section_found_on_its_page(self):
        for page in SEC["pages"]:
            self.assertEqual(self.R[page + "_off"]["missing"], [], page)
            self.assertEqual(self.R[page + "_off"]["empty"], [], page)

    def test_locked_text_shows_and_labels_stay(self):
        d = self.R["daily"]["t"]
        self.assertIn("Bearish lean: Lose 7625 and the 7596–7600 shelf is next.", d)
        self.assertIn("Wait for the open.", d); self.assertIn("Flat into PPI.", d); self.assertNotIn("Oppenheimer cut NVDA to Perform (7:43 PM)", d)
        self.assertNotIn("Expired text must not show.", d)
        self.assertRegex(d, r"edited \w{3} \d+/\d+ \d+:\d\d [AP]M PT")
        self.assertIn("Manual weekly bias line.", self.R["weekly"]["t"])
        self.assertIn("BASE CASE Manual base case.", self.R["overnight"]["t"].replace("\n", " "))
        c = self.R["command"]
        self.assertIn("Manual flow note.", c["t"]); self.assertIn("Lose 7625 and the 7596–7600 shelf is next.", c["t"])
        self.assertEqual(c["tiles"], 7)

    def test_ov_off_shows_pipeline_text(self):
        self.assertNotIn("Manual flow note.", self.R["command_off"]["t"])
        self.assertNotIn("Lose 7625 and the 7596–7600", self.R["daily_off"]["t"])

    def test_release_restores_pipeline_text(self):
        self.assertNotIn("Lose 7625 and the 7596–7600", self.R["released"]["t"])
        self.assertEqual(self.R["released"]["applied"], [])

    def test_edit_page_lists_every_section(self):
        e = self.R["edit"]
        self.assertTrue(e["signin"])
        self.assertEqual(e["cards"], len(SEC["sections"]))
        self.assertGreaterEqual(e["filled"], len([s for s in SEC["sections"] if not s.get("optional")]))
        self.assertNotRegex(e["t"].lower(), r"\berror\b")

    def test_no_error_word_or_names_rendered(self):
        for k, v in self.R.items():
            self.assertNotRegex(v["t"].lower(), r"\berror\b", k)
            self.assertIsNone(re.search(r"mancini|smashelito|voltick|newsletter", v["t"], re.I), k)


@unittest.skipUnless(HAVE_PW, "headless chrome not available")
class EditSaveFlow(unittest.TestCase):
    """Sign-in, guard and the Contents API commit, against a mocked api.github.com (no network, no real token)."""

    @classmethod
    def setUpClass(cls):
        import base64
        cls.td = tempfile.mkdtemp(); site = site_copy(cls.td, {}); cls.srv = serve(site)
        base = f"http://127.0.0.1:{cls.srv.server_address[1]}/"
        doc = {"version": 1, "overrides": {}}
        cls.puts, cls.errs = [], []

        def api(route):
            r, u = route.request, route.request.url
            hdr = {"Access-Control-Allow-Origin": "*", "Content-Type": "application/json"}
            if r.method == "OPTIONS":
                return route.fulfill(status=204, headers={**hdr, "Access-Control-Allow-Headers": "*", "Access-Control-Allow-Methods": "GET,PUT"})
            if r.headers.get("authorization") != "Bearer test-token-not-real":
                return route.fulfill(status=401, headers=hdr, body='{"message":"Bad credentials"}')
            if u.endswith("/repos/shlomoyuckenfutz/attache"):
                return route.fulfill(headers=hdr, body='{"permissions":{"push":true}}')
            if u.endswith("/user"):
                return route.fulfill(headers=hdr, body='{"login":"tester"}')
            if "/contents/content/overrides.json" in u and r.method == "GET":
                c = base64.b64encode(json.dumps(doc).encode()).decode()
                return route.fulfill(headers=hdr, body=json.dumps({"sha": "abc", "content": c}))
            if "/contents/content/overrides.json" in u and r.method == "PUT":
                body = json.loads(r.post_data); cls.puts.append(body)
                return route.fulfill(headers=hdr, body='{"commit":{"sha":"1234567890","html_url":"https://example.invalid/c"}}')
            return route.fulfill(status=404, headers=hdr, body='{"message":"Not Found"}')

        with sync_playwright() as p:
            b = p.chromium.launch(executable_path="/usr/bin/google-chrome", args=["--no-sandbox"])
            ctx = b.new_context(viewport={"width": 1280, "height": 1000})
            ctx.route(re.compile(r"^https://fonts\."), lambda r: r.abort())
            ctx.route(re.compile(r"^https://api\.github\.com/"), api)
            pg = ctx.new_page(); pg.on("pageerror", lambda e: cls.errs.append(str(e)))
            pg.goto(base + "edit/", wait_until="load"); pg.wait_for_timeout(5000)
            pg.fill("#tok", "test-token-not-real"); pg.click("#tokGo"); pg.wait_for_timeout(800)
            cls.who = pg.inner_text("#who")
            cls.stored = pg.evaluate("()=>localStorage.getItem('attache_edit_pat')")
            card = pg.locator(".card").nth(2)  # Bearish lean
            card.locator("textarea").fill("Mentions a newsletter here.")
            card.locator("button.sv").click(); pg.wait_for_timeout(500)
            cls.blocked = pg.inner_text("#msg"); cls.puts_after_block = len(cls.puts)
            card.locator("textarea").fill("Lose 7625 and 7596–7600 is next.")
            card.locator("button.sv").click(); pg.wait_for_timeout(1500)
            cls.saved = pg.inner_text("#msg")
            b.close()

    @classmethod
    def tearDownClass(cls):
        cls.srv.shutdown(); shutil.rmtree(cls.td, ignore_errors=True)

    def test_sign_in_keeps_token_in_browser_only(self):
        self.assertIn("tester", self.who)
        self.assertEqual(self.stored, "test-token-not-real")
        for p in self.puts:
            self.assertNotIn("test-token-not-real", json.dumps(p))

    def test_guard_blocks_banned_text_before_any_commit(self):
        self.assertEqual(self.puts_after_block, 0)
        self.assertIn("Not saved", self.blocked)

    def test_save_commits_one_lock(self):
        import base64
        self.assertEqual(len(self.puts), 1, self.saved)
        put = self.puts[0]
        self.assertEqual(put["sha"], "abc"); self.assertEqual(put["branch"], "main")
        self.assertEqual(put["message"], "edit portal: lock lss.bearish")
        o = json.loads(base64.b64decode(put["content"]))["overrides"]["lss.bearish"]
        self.assertEqual(o["text"], "Lose 7625 and 7596–7600 is next.")
        self.assertTrue(o["expires"] is None or re.match(r"^\d{4}-\d\d-\d\dT23:59:00-0[78]:00$", o["expires"]), o["expires"])
        self.assertTrue(o["base"].startswith("Below 7625"), o["base"])
        self.assertIn("Saved", self.saved)
        self.assertEqual(self.errs, [])


if __name__ == "__main__":
    unittest.main()
