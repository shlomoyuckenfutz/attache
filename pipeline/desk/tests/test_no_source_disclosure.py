"""Fails if built pages or a fresh daily render disclose plan sources."""
import os, re, sys, unittest
from pathlib import Path
from html import unescape

DESK = Path(__file__).resolve().parents[1]
ROOT = Path(os.environ.get("ORB_SITE") or DESK.parents[1])
sys.path.insert(0, str(DESK))

import build_daily as bd

TEXT = {".html", ".json", ".js", ".css", ".txt", ".md", ".svg", ".xml"}
SKIP_PREFIX = ("pipeline/", ".git/", ".github/")

EXACT = (
    "Plan only — not investment advice · rebuilt from plan.json on every sweep",
    "sources counted in plan",
)
COUNT_RX = re.compile(
    r"sources counted|\brebuilt from plan\.json\b|\b\d+\s+sources\b|\b0 feeds\b|Awaiting feed list",
    re.I,
)
# Visible (rendered) text only: file names are allowed as fetch paths in JS.
VISIBLE_FILES_RX = re.compile(r"\bplan\.json\b|\bpipeline/", re.I)
SOURCE_COLON_RX = re.compile(r"\bsources?\s*:", re.I)
BANNED = re.compile(
    r"mancini|smashelito|\bsmash(?:level)?\b|voltick|kttechprivate|\bkttech\b|"
    r"traderjonesy|\bjonesy\b|substack|newsletter",
    re.I,
)
# Don't treat CSS @media / @keyframes or mailto as @handles.
HANDLE_RX = re.compile(r"(?<![A-Za-z0-9_@])@(?!media\b|keyframes\b|import\b|supports\b|font-face\b|charset\b|page\b|param\b|returns\b|type\b)[A-Za-z][A-Za-z0-9_]{2,}")


def public_files(root=ROOT):
    out = []
    for p in root.rglob("*"):
        if not p.is_file() or p.suffix.lower() not in TEXT:
            continue
        rel = str(p.relative_to(root)).replace("\\", "/")
        if rel.startswith(SKIP_PREFIX):
            continue
        out.append(p)
    return out


def visible_text(raw: str) -> str:
    s = re.sub(r"<script\b[^>]*>.*?</script>", " ", raw, flags=re.I | re.S)
    s = re.sub(r"<style\b[^>]*>.*?</style>", " ", s, flags=re.I | re.S)
    s = re.sub(r"<!--.*?-->", " ", s, flags=re.S)
    s = re.sub(r"<[^>]+>", " ", s)
    return unescape(re.sub(r"\s+", " ", s))


def hits_in(text, rel, visible=False):
    found = []
    for phrase in EXACT:
        if phrase in text:
            found.append(f"{rel}: exact {phrase!r}")
    if m := COUNT_RX.search(text):
        found.append(f"{rel}: count/rebuild {m.group(0)!r}")
    src = visible_text(text) if visible else text
    if visible:
        if m := VISIBLE_FILES_RX.search(src):
            found.append(f"{rel}: visible file name {m.group(0)!r}")
        if m := SOURCE_COLON_RX.search(src):
            found.append(f"{rel}: source-colon {m.group(0)!r}")
    if m := BANNED.search(src if visible else text):
        found.append(f"{rel}: banned {m.group(0)!r}")
    if visible:
        if m := HANDLE_RX.search(src):
            found.append(f"{rel}: handle {m.group(0)!r}")
    return found


class RepoPages(unittest.TestCase):
    def test_repo_pages_have_no_source_disclosure(self):
        found = []
        for p in public_files():
            rel = str(p.relative_to(ROOT))
            t = p.read_text(encoding="utf-8", errors="replace")
            found += hits_in(t, rel, visible=False)
            if p.suffix.lower() in {".html", ".md", ".txt"}:
                found += hits_in(t, rel + " [visible]", visible=True)
        self.assertEqual(found, [], "\n".join(found))

    def test_generator_source_does_not_emit_the_phrases(self):
        src = (DESK / "build_daily.py").read_text(encoding="utf-8")
        found = []
        for phrase in EXACT:
            if phrase in src:
                found.append(f"build_daily.py: exact {phrase!r}")
        if "sources counted in plan" in src or "rebuilt from plan.json on every sweep" in src:
            found.append("build_daily.py still contains the footer template")
        self.assertEqual(found, [], "\n".join(found))


class FreshRender(unittest.TestCase):
    def test_fresh_daily_render_omits_source_lines(self):
        plan, _ = bd.load_plan(ROOT)
        plan = dict(plan)
        plan["sources_count"] = 99
        html, title, direction, reason = bd.page(plan, ROOT)
        vis = visible_text(html)
        self.assertIn("DAILY PLAN", title)
        self.assertIn(str(plan.get("date", "")).split("-")[0], html)  # year still on the page
        self.assertNotIn("rebuilt from plan.json on every sweep", html)
        self.assertNotIn("sources counted in plan", html)
        self.assertIsNone(COUNT_RX.search(html), html[html.find("source"):html.find("source")+80] if "source" in html.lower() else "")
        self.assertIsNone(VISIBLE_FILES_RX.search(vis), vis)
        self.assertIsNone(BANNED.search(html))
        self.assertNotIn("class=\"hd\"", html)
        self.assertNotIn("99", vis.split("PLAN")[0] if False else "")  # don't require this
        # the padded count must not appear as a source count
        self.assertIsNone(re.search(r"\b99\s+sources\b", html, re.I))
        self.assertIn("<nav class=\"toc\">", html)


if __name__ == "__main__":
    unittest.main()
