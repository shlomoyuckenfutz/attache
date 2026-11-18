#!/usr/bin/env bash
# Safe overnight publish (Night Ledger routine). Runs ONLY inside the dedicated publish clone
# (git config attache.publishclone=true), always from a fresh origin/main. It rebuilds and commits only the files
# the overnight job owns (Overnight page + Night Ledger / overnight inputs, see publish_guard.OWNED) with the repo's
# own builders. Never copies Command, Weekly, Daily, Gamma Map, Dark Pool or Study. Never autostashes. On a rebase
# conflict or any regression (publish_guard.py) it aborts, resets to origin/main and pushes nothing.
# DRY_RUN=1 builds, commits and guards but does not push.
set -euo pipefail
REPO="$(cd "$(dirname "$0")/.." && pwd)"
cd "$REPO"
BR=main
if [ "$(git config --local --get attache.publishclone || true)" != "true" ]; then
  echo "ABORT: $REPO is not the dedicated publish clone (git config attache.publishclone true); nothing touched" >&2; exit 1
fi

to_origin() { # hard-sync this clone to origin/main; leaves no rebase state, stash or conflict files
  git rebase --abort >/dev/null 2>&1 || true
  git merge --abort >/dev/null 2>&1 || true
  git cherry-pick --abort >/dev/null 2>&1 || true
  git fetch -q origin "$BR"
  git checkout -q -f -B "$BR" "origin/$BR"
  git reset -q --hard "origin/$BR"
  git clean -qfd
  git stash clear
}
abort() { echo "ABORT: $*; nothing pushed" >&2; to_origin || true; exit 1; }

to_origin
[ -z "$(git status --porcelain)" ] || abort "checkout not clean after sync"

export ORB_ROOT="$REPO" ORB_DESK="$REPO/pipeline/desk" ORB_SITE="$REPO" SITE="$REPO" \
       ORB_INPUTS="$REPO/pipeline/inputs" ORB_CACHE="$REPO/pipeline/cache"
mkdir -p "$ORB_CACHE"
cd "$ORB_DESK"
bash ../sync_inputs.sh >/dev/null
(cd es_levels && python3 overnight_fetch.py >/dev/null) || abort "overnight_fetch failed"
(cd es_levels && python3 overnight_details.py >/dev/null) || echo "WARN: overnight_details failed" >&2
(cd xnews/ledger && python3 ledger_parse.py >/dev/null) || echo "WARN: ledger_parse failed" >&2
mkdir -p overnight
python3 build_overnight.py >/dev/null || abort "build_overnight failed"
cp overnight/index.html "$REPO/overnight/index.html"
python3 ui_shell.py overnight="$REPO/overnight/index.html" >/dev/null || abort "ui_shell failed"
python3 apply_overrides.py "$REPO" >/dev/null || abort "apply_overrides failed"
python3 site_sanitize.py "$REPO/overnight/index.html" >/dev/null || abort "site_sanitize failed"
python3 -c "import re,sys;s=open(sys.argv[1]).read();open('/tmp/overnight_check.js','w').write(chr(10).join(re.findall(r'<script>(.*?)</script>',s,re.S)))" \
  "$REPO/overnight/index.html"
node --check /tmp/overnight_check.js || abort "JS syntax error in overnight page"

# Stage ONLY owned paths, then drop every other change the builders made.
cd "$REPO"
OWNED=$(python3 -c "import sys;sys.path.insert(0,'pipeline/desk');import publish_guard as G;print(' '.join(G.OWNED))")
for g in $OWNED; do git add -A -- ":(glob)$g" 2>/dev/null || true; done
if git diff --cached --quiet; then echo "overnight publish: nothing new"; to_origin; exit 0; fi
git -c user.name=shlomoyuckenfutz -c user.email=shlomoyuckenfutz@users.noreply.github.com \
  commit -qm "overnight ledger $(date '+%F %H:%M')"
git reset -q --hard HEAD && git clean -qfd

(cd pipeline/desk && python3 -m unittest -q tests.test_no_source_disclosure >/dev/null 2>&1) || abort "source scrub failed"

for try in 1 2 3; do
  git fetch -q origin "$BR"
  git rebase -q "origin/$BR" >/dev/null 2>&1 || abort "rebase conflict on origin/$BR"
  python3 pipeline/desk/publish_guard.py --repo . --base "origin/$BR" --head HEAD || abort "publish_guard refused"
  if [ "${DRY_RUN:-0}" = "1" ]; then echo "overnight publish: DRY_RUN ok $(git rev-parse --short HEAD)"; exit 0; fi
  if git push -q origin "HEAD:$BR"; then echo "overnight publish: pushed $(git rev-parse --short HEAD)"; exit 0; fi
  echo "WARN: push rejected (try $try); refetching" >&2
done
abort "push kept failing"
