#!/usr/bin/env python3
"""Strip THE WIRE panel from live command so scheduled refresh cannot re-add it."""
import re, sys
from pathlib import Path

DESK = Path(__file__).resolve().parent

WIRE_RE = re.compile(
    r'(?:<style>\s*\.nw\{.*?</style>)?\s*<section[^>]*id="z-wire".*?</section>\s*'
    r'(?:<script>\(function\(\)\{var m=30\*60e3.*?</script>)?',
    re.S,
)

def strip_file(path: Path) -> bool:
    if not path.exists():
        print(f'WARN: missing {path}', file=sys.stderr)
        return False
    t = path.read_text(encoding='utf-8')
    n = WIRE_RE.sub('', t)
    if n != t:
        path.write_text(n, encoding='utf-8')
        print(f'stripped wire -> {path}')
    else:
        print(f'no wire section in {path}')
    return True

def main(argv):
    site = Path(argv[1]) if len(argv) > 1 else Path(__import__('os').environ.get('ORB_SITE', DESK.parent.parent))
    ok = strip_file(site / 'command' / 'index.html')
    # full wire on hub plain source if present (encrypted hub rebuilt elsewhere)
    plain = DESK / 'hub_src' / 'hub_plain.html'
    if plain.exists():
        strip_file(plain)
    return 0 if ok else 1

if __name__ == '__main__':
    raise SystemExit(main(sys.argv))
