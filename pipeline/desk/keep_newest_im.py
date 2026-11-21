#!/usr/bin/env python3
"""Copy an expected-move snapshot into place only when it is newer than the one already there.

sync_inputs.sh used to copy pipeline/inputs/implied_move/implied_move.json over the working snapshot on every
run. When the after-hours chain fetch then failed, the Daily (and anything else reading the working file) fell
back to whatever the inputs copy held, which could be weeks old. Same rule as the Command Center: keep the
newest snapshot, never go backwards.
Usage: keep_newest_im.py SRC DEST"""
import json, shutil, sys
from pathlib import Path


def stamp(p):
    try:
        d = json.loads(Path(p).read_text(encoding="utf-8"))
        return str(d.get("generated_pt") or "") if (d.get("symbols") or {}) else ""
    except Exception:
        return ""


def keep_newest(src, dst):
    src, dst = Path(src), Path(dst)
    if not src.is_file():
        return False
    if stamp(src) > stamp(dst):
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)
        return True
    return False


if __name__ == "__main__":
    s, d = sys.argv[1], sys.argv[2]
    print(("keep_newest_im: copied " if keep_newest(s, d) else "keep_newest_im: kept newer ") + f"{stamp(d) or 'none'}")
