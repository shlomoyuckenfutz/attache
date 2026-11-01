#!/usr/bin/env python3
"""Patch THE WIRE panel into live command (and optional hub plain) from xnews/newswire.json."""
import re, sys
from pathlib import Path

DESK = Path(__file__).resolve().parent
sys.path.insert(0, str(DESK))
import newswire_render as nw

WIRE_RE = re.compile(
    r'(?:<style>\s*\.nw\{.*?</style>)?\s*<section[^>]*id="z-wire".*?</section>\s*'
    r'(?:<script>\(function\(\)\{var m=30\*60e3.*?</script>)?',
    re.S,
)

def patch_file(path: Path, html: str) -> bool:
    if not path.exists() or not html:
        return False
    t = path.read_text(encoding='utf-8')
    if WIRE_RE.search(t):
        n = WIRE_RE.sub(html, t, count=1)
    elif '<main>' in t:
        n = t.replace('<main>', '<main>' + html, 1)
    else:
        print(f'WARN: no wire anchor in {path}', file=sys.stderr)
        return False
    if n != t:
        path.write_text(n, encoding='utf-8')
        print(f'patched wire -> {path}')
        return True
    print(f'wire unchanged in {path}')
    return False

def main(argv):
    site = Path(argv[1]) if len(argv) > 1 else Path(__import__('os').environ.get('ORB_SITE', DESK.parent.parent))
    cmd = nw.command_html()
    ok = patch_file(site / 'command' / 'index.html', cmd)
    # full wire on hub plain source if present (encrypted hub rebuilt elsewhere)
    plain = DESK / 'hub_src' / 'hub_plain.html'
    if plain.exists():
        patch_file(plain, nw.main_html())
    return 0 if ok else 1

if __name__ == '__main__':
    raise SystemExit(main(sys.argv))
