"""No wire nav/section leftovers, and every nav href resolves to a real page or in-page anchor."""
import re, unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
SKIP = (".git/", ".github/", "pipeline/")
WIRE_HREF = re.compile(r"(?:^|/)wire/?$|#z-wire|(?:^|/)#wire$", re.I)
WIRE_TEXT = re.compile(r"^\s*(the\s+)?wire\s*$", re.I)


def public_html():
    return [p for p in ROOT.rglob("*.html") if p.is_file() and not str(p.relative_to(ROOT)).startswith(SKIP)]


def ids(html):
    return set(re.findall(r'''\bid=["']([^"']+)["']''', html, re.I))


def nav_links(html):
    links = []
    for nav in re.findall(r"<nav\b[^>]*>.*?</nav>", html, re.I | re.S):
        for m in re.finditer(r'''<a\b[^>]*href=["']([^"']+)["'][^>]*>(.*?)</a>''', nav, re.I | re.S):
            links.append((m.group(1).strip(), re.sub(r"\s+", " ", m.group(2))))
    return links


def resolve(src, href):
    if href.startswith(("http://", "https://", "mailto:", "javascript:")):
        return ("external", href)
    path, _, frag = href.partition("#")
    if not path:
        return ("anchor", frag)
    dest = (src.parent / path).resolve()
    if dest.is_dir():
        dest = dest / "index.html"
    elif not dest.exists() and (dest / "index.html").exists():
        dest = dest / "index.html"
    return ("path", (dest, frag))


class NavIntegrity(unittest.TestCase):
    def test_no_wire_nav_or_dead_nav_hrefs(self):
        problems = []
        for p in public_html():
            t = p.read_text(encoding="utf-8", errors="replace")
            rel = str(p.relative_to(ROOT))
            idset = ids(t)
            for href, text in nav_links(t):
                if WIRE_HREF.search(href) or WIRE_TEXT.search(text):
                    problems.append(f"{rel}: wire nav {text!r} href={href!r}")
                    continue
                kind, info = resolve(p, href)
                if kind == "anchor":
                    if info and info not in idset:
                        problems.append(f"{rel}: nav href=#{info} is a missing anchor")
                elif kind == "path":
                    dest, frag = info
                    try:
                        dest.relative_to(ROOT.resolve())
                    except ValueError:
                        problems.append(f"{rel}: nav href={href!r} escapes the site")
                        continue
                    if not dest.exists():
                        problems.append(f"{rel}: nav href={href!r} is a missing page")
                        continue
                    if frag:
                        dids = ids(dest.read_text(encoding="utf-8", errors="replace"))
                        if frag not in dids:
                            problems.append(f"{rel}: nav href={href!r} is a missing anchor")
            if rel == "command/index.html" and (
                'id="z-wire"' in t or re.search(r'''href=["'][^"']*(#z-wire|/wire/)''', t)
            ):
                problems.append(f"{rel}: leftover wire section or href")
        self.assertEqual(problems, [], "\n".join(problems))


if __name__ == "__main__":
    unittest.main()
