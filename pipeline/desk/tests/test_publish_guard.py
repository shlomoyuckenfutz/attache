"""Overnight publish job guards: owns only Overnight/Night Ledger files, never regresses Command ORB/Hourly,
Daily/Weekly dates or the Gamma Map nav tab, never autostashes, cleans up a failed rebase, guards before push."""
import json, os, re, subprocess, sys, tempfile, unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
SCRIPT = ROOT / "pipeline" / "publish_overnight.sh"
WRAPPER = Path("/workspace/desk/orb-research/publish_dashboard.sh")
sys.path.insert(0, str(ROOT / "pipeline" / "desk"))
import publish_guard as G  # noqa: E402

NAV = '<nav><a href="../command/">C</a><a href="../gammamap/">GAMMA MAP</a></nav>'
NAV_OLD = '<nav><a href="../command/">C</a></nav>'


def cmd(day, hour=None):
    D = {"orb": {s: {"date": day} for s in ("SPY", "QQQ", "ES", "SPX")}}
    return (f"{NAV}<script>const D={json.dumps(D)};</script>"
            f'<section class="zone" id="z-hr"><small>last data Tue {hour or day} ET</small></section>'
            "<b>Mon Nov 16 to Fri Nov 20, 2026</b>")


def pages(day="2026-11-17", daily="Wed Nov 18, 2026", weekly="Mon Nov 16 to Fri Nov 20, 2026", nav=NAV):
    return {"command/index.html": cmd(day), "daily/index.html": f"{nav}DAILY PLAN — {daily}",
            "weekly/index.html": f"{nav}{weekly}", "overnight/index.html": f"{nav}night", "gammamap/index.html": NAV}


class Guard(unittest.TestCase):
    def test_owned_only(self):
        self.assertTrue(G.owned("overnight/index.html"))
        self.assertTrue(G.owned("pipeline/inputs/ledger/2026-11-18.md"))
        self.assertTrue(G.owned("pipeline/desk/xnews/ledger/ledger.json"))
        for p in ("command/index.html", "weekly/index.html", "daily/index.html", "gammamap/index.html",
                  "darkpool/index.html", "study/index.html", "weekly/charts/a.png", "index.html"):
            self.assertFalse(G.owned(p), p)

    def test_clean_overnight_change_passes(self):
        b = pages(); h = dict(b, **{"overnight/index.html": f"{NAV}night 2"})
        self.assertEqual(G.compare(b, h, ["overnight/index.html", "pipeline/inputs/ledger/2026-11-18.md"]), [])

    def test_regressions_refused(self):
        b = pages()
        cases = {
            "ORB": dict(b, **{"command/index.html": cmd("2026-11-11", "2026-11-17")}),
            "HOURLY": dict(b, **{"command/index.html": cmd("2026-11-17", "2026-11-11")}),
            "Daily": dict(b, **{"daily/index.html": f"{NAV}DAILY PLAN — Mon Nov 2, 2026"}),
            "Weekly plan": dict(b, **{"weekly/index.html": f"{NAV}Mon Nov 9 to Fri Nov 13, 2026"}),
            "Gamma Map": dict(b, **{"overnight/index.html": f"{NAV_OLD}night"}),
        }
        for label, h in cases.items():
            bad = G.compare(b, h, ["overnight/index.html"])
            self.assertTrue(any(label in x for x in bad), (label, bad))

    def test_unowned_file_and_markers_refused(self):
        b = pages()
        self.assertTrue(G.compare(b, b, ["command/index.html"]))
        h = dict(b, **{"overnight/index.html": f"{NAV}\n<<<<<<< Updated upstream\nx\n=======\ny\n>>>>>>> Stash\n"})
        self.assertTrue(any("conflict" in x for x in G.compare(b, h, ["overnight/index.html"])))

    def test_tonights_stale_push_would_be_refused(self):
        if subprocess.run(["git", "-C", str(ROOT), "cat-file", "-e", "b72628c48^{commit}"], capture_output=True).returncode:
            self.skipTest("history not present")
        r = subprocess.run([sys.executable, str(ROOT / "pipeline/desk/publish_guard.py"), "--repo", str(ROOT),
                            "--base", "72f3d6e32", "--head", "b72628c48"], capture_output=True, text=True)
        self.assertEqual(r.returncode, 1)
        for k in ("ORB SPY", "HOURLY", "Daily plan", "Weekly plan", "Gamma Map", "not owned"):
            self.assertIn(k, r.stderr)


class Script(unittest.TestCase):
    def setUp(self):
        self.s = SCRIPT.read_text()
        self.code = "\n".join(l for l in self.s.splitlines() if not l.lstrip().startswith("#"))

    def test_no_autostash_and_guard_before_push(self):
        self.assertNotIn("autostash", self.code)
        self.assertNotIn("orb-dash-site", self.code)
        self.assertIn("rebase --abort", self.s)
        self.assertLess(self.s.index("publish_guard.py"), self.s.index("git push"))
        self.assertLess(self.s.index('git rebase -q "origin/$BR"'), self.s.index("publish_guard.py --repo"))
        for page in ("command/index.html", "weekly/index.html", "daily/index.html", "gammamap", "darkpool", "study"):
            self.assertNotRegex(self.s, rf"cp [^\n]*{re.escape(page)}", page)

    def test_refuses_outside_publish_clone(self):
        with tempfile.TemporaryDirectory() as d:
            subprocess.run(["git", "init", "-q", d], check=True)
            (Path(d) / "pipeline").mkdir(); (Path(d) / "pipeline/publish_overnight.sh").write_text(self.s)
            (Path(d) / "keep.txt").write_text("mine")
            r = subprocess.run(["bash", f"{d}/pipeline/publish_overnight.sh"], capture_output=True, text=True)
            self.assertEqual(r.returncode, 1); self.assertIn("not the dedicated publish clone", r.stderr)
            self.assertEqual((Path(d) / "keep.txt").read_text(), "mine")

    def test_failed_rebase_is_cleaned_up(self):
        fn = re.search(r"^to_origin\(\) \{.*?^\}", self.s, re.S | re.M).group(0)
        with tempfile.TemporaryDirectory() as d:
            sh = lambda c, cwd: subprocess.run(c, shell=True, cwd=cwd, check=True, capture_output=True, text=True)
            env = "git -c user.name=t -c user.email=t@t"
            sh(f"git init -q --bare -b main o.git && git clone -q o.git a 2>/dev/null && cd a && echo 1 > f && git add f && {env} commit -qm 1 && git push -q origin HEAD:main", d)
            sh(f"git clone -q o.git b && cd a && echo 2 > f && {env} commit -qam 2 && git push -q", d)
            b = f"{d}/b"
            sh(f"echo 3 > f && {env} commit -qam 3 && git fetch -q && ({env} rebase origin/main || true) && echo dirty > g && echo x > f", b)
            sh(f"{env} stash -q || true", b)
            subprocess.run(["bash", "-c", f"set -e; BR=main; {fn}\nto_origin"], cwd=b, check=True, capture_output=True)
            self.assertEqual(sh("git status --porcelain", b).stdout, "")
            self.assertFalse((Path(b) / ".git/rebase-merge").exists() or (Path(b) / ".git/rebase-apply").exists())
            self.assertEqual(sh("git stash list", b).stdout, "")
            self.assertEqual((Path(b) / "f").read_text(), "2\n")
            self.assertEqual(sh("git rev-parse HEAD", b).stdout, sh("git rev-parse origin/main", b).stdout)


@unittest.skipUnless(WRAPPER.exists(), "local publish wrapper not on this machine")
class Wrapper(unittest.TestCase):
    def test_wrapper_never_writes_sweep_pages(self):
        s = WRAPPER.read_text()
        code = "\n".join(l for l in s.splitlines() if not l.lstrip().startswith("#"))
        self.assertNotIn("autostash", code)
        self.assertNotIn("orb-dash-site", code)
        self.assertIn("publish_overnight.sh", code)
        self.assertNotRegex(code, r"\bcp\b[^\n]*(command|weekly|daily|gammamap|darkpool|study)/index\.html")


class NoFeedOrFileNames(unittest.TestCase):
    def test_public_pages_clean(self):
        for rel in ("command", "overnight", "weekly", "daily", "darkpool", "gammamap"):
            t = (ROOT / rel / "index.html").read_text()
            self.assertNotRegex(t, r"(?i)free feed|read-only local copy", rel)
            self.assertEqual(re.sub(r"new URL\('\.\./data/spy_dark_pool\.json'", "", t).count("spy_dark_pool"), 0, rel)

    def test_sanitize_keeps_fetch_url(self):
        import site_sanitize as S
        js = "const url=new URL('../data/spy_dark_pool.json', document.baseURI);"
        self.assertEqual(S.clean(js), js)
        self.assertNotIn("spy_dark_pool", S.clean('"levels_source": "data/spy_dark_pool.json"'))
        self.assertNotIn("free feed", S.clean("spot=Fri RTH close free feed IEX"))


if __name__ == "__main__":
    unittest.main()
