#!/usr/bin/env bash
# Attaché class-A refresh for GitHub Actions (and local dry-runs).
# Reads bot inputs from pipeline/inputs/, writes live site pages at repo root.
set -euo pipefail

PIPE="$(cd "$(dirname "$0")" && pwd)"
export ORB_ROOT="$(cd "$PIPE/.." && pwd)"
export ORB_DESK="$PIPE/desk"
export ORB_SITE="$ORB_ROOT"
export ORB_INPUTS="$PIPE/inputs"
export ORB_CACHE="$PIPE/cache"
export SITE="$ORB_SITE"
mkdir -p "$ORB_CACHE" "$ORB_DESK/equity_orb15/data" "$ORB_DESK/secrets"

# Map secret alias
if [ -n "${ALPACA_SECRET_KEY:-}" ] && [ -z "${ALPACA_API_SECRET:-}" ]; then
  export ALPACA_API_SECRET="$ALPACA_SECRET_KEY"
fi

# Write study password file for encrypt scripts (never echo the value)
if [ -n "${ATOUCHE_STUDY_PASSWORD:-}" ]; then
  printf '%s' "$ATOUCHE_STUDY_PASSWORD" > "$ORB_DESK/secrets/study_password.txt"
  chmod 600 "$ORB_DESK/secrets/study_password.txt"
fi
if [ -n "${ATOUCHE_HEAT_PASSWORD:-}" ]; then
  printf '%s' "$ATOUCHE_HEAT_PASSWORD" > "$ORB_DESK/secrets/heat_password.txt"
  chmod 600 "$ORB_DESK/secrets/heat_password.txt"
fi

cd "$ORB_DESK"
bash "$PIPE/sync_inputs.sh"

run() { # label command...
  local label="$1"; shift
  echo "==> $label"
  if ! "$@"; then
    echo "WARN: $label failed (non-fatal)" >&2
    return 0
  fi
}

# 1) Rolling bars (Alpaca)
run "bars_rolling" python3 equity_orb15/bars_rolling.py SPY QQQ

# 2) First blade calc (uses bars)
run "first_blade" python3 first_blade.py

# 3) X-levels rebuild (needs levels_raw from bot + bars)
run "build_xlevels" bash -c 'cd xnews && timeout 120 python3 build_xlevels.py'
# 3b) newswire.json from bot-written newswire_raw.json; strip any leftover command ticker (section retired)
run "newswire_fetch" bash -c 'cd xnews && python3 newswire_fetch.py'
run "patch_newswire" python3 patch_newswire.py "$ORB_SITE"

# 4) ES conversions (levels_a levels from inputs)
run "convert_es" bash -c 'cd es_levels && timeout 120 python3 convert_es.py'

# 5) Free GEX (CBOE public)
run "free_gex" bash -c 'timeout 120 python3 free_gex.py'

# 6) Implied move
run "calc_im" bash -c 'cd xnews/implied_move && python3 calc_im.py'

# 7) Overnight board + details (yfinance)
run "overnight_fetch" bash -c 'cd es_levels && python3 overnight_fetch.py'
run "overnight_details" bash -c 'cd es_levels && python3 overnight_details.py'

# 8) Night ledger parse (from ledger md inputs)
run "ledger_parse" bash -c 'cd xnews/ledger && python3 ledger_parse.py'

# 9) HEAT / exposure data (CBOE + Alpaca bars) — no git push
run "exposure_collector" env PUSH=0 python3 scripts/exposure_collector.py

# 10) Daily/weekly charts (Yahoo) — FATAL if any symbol fails (no silent stale PNGs)
echo "==> make_daily_charts"
python3 make_daily_charts.py

# 11) Build HTML pages
mkdir -p overnight weekly/charts/prior weekly/charts/plan daily/charts

run "build_overnight" python3 build_overnight.py
run "build_weekly" python3 build_weekly.py --patch-desk "$ORB_SITE/command/index.html"
run "build_daily" python3 build_daily.py --patch-desk "$ORB_SITE/command/index.html"
mkdir -p "$ORB_SITE/gammamap"
run "gamma_board" python3 gamma_board.py --patch-daily daily/index.html --patch-weekly weekly/index.html \
  --patch-command "$ORB_SITE/command/index.html" --page "$ORB_SITE/gammamap/index.html"
run "plan_addenda" python3 plan_addenda.py --daily daily/index.html --weekly weekly/index.html

# 12) Copy pages into site root
mkdir -p "$ORB_SITE/overnight" "$ORB_SITE/weekly/charts/prior" "$ORB_SITE/weekly/charts/plan" \
         "$ORB_SITE/daily/charts" "$ORB_SITE/darkpool" "$ORB_SITE/exposure" "$ORB_SITE/study"
[ -f overnight/index.html ] && cp -a overnight/index.html "$ORB_SITE/overnight/index.html"
[ -f weekly/index.html ] && cp -a weekly/index.html "$ORB_SITE/weekly/index.html"
[ -f daily/index.html ] && cp -a daily/index.html "$ORB_SITE/daily/index.html"
# charts
cp -a weekly/charts/*.png "$ORB_SITE/weekly/charts/" 2>/dev/null || true
cp -a weekly/charts/prior/. "$ORB_SITE/weekly/charts/prior/" 2>/dev/null || true
cp -a weekly/charts/plan/. "$ORB_SITE/weekly/charts/plan/" 2>/dev/null || true
cp -a daily/charts/. "$ORB_SITE/daily/charts/" 2>/dev/null || true

# 13) UI shell on live pages
run "ui_shell" python3 ui_shell.py \
  "command=$ORB_SITE/command/index.html" \
  "overnight=$ORB_SITE/overnight/index.html" \
  "weekly=$ORB_SITE/weekly/index.html" \
  "daily=$ORB_SITE/daily/index.html" \
  "gammamap=$ORB_SITE/gammamap/index.html"

# 14) Study re-encrypt (nav shell may change; payload from study_plain)
if [ -f study_src/study_plain.html ] && [ -f "$ORB_SITE/study/index.html" ]; then
  cp study_src/study_plain.html /tmp/study_plain_ui.html
  python3 ui_shell.py study=/tmp/study_plain_ui.html || true
  node study_src/reencrypt.js /tmp/study_plain_ui.html "$ORB_SITE/study/index.html" || echo "WARN: study reencrypt failed" >&2
  python3 ui_shell.py studylock="$ORB_SITE/study/index.html" || true
  rm -f /tmp/study_plain_ui.html
fi

# 15) Exposure HEAT — plain unlocked (never re-encrypt)
if [ -f exposure_src/exposure_live_plain.html ]; then
  cp exposure_src/exposure_live_plain.html /tmp/exposure_live_ui.html
  python3 ui_shell.py exposure=/tmp/exposure_live_ui.html || true
  mkdir -p "$ORB_SITE/exposure"
  cp /tmp/exposure_live_ui.html "$ORB_SITE/exposure/index.html"
  rm -f /tmp/exposure_live_ui.html
fi

# 16) Darkpool LIVE — plain unlocked (never re-encrypt)
if [ -f darkpool_src/darkpool_live_plain.html ]; then
  cp darkpool_src/darkpool_live_plain.html /tmp/darkpool_live_ui.html
  python3 ui_shell.py darkpool=/tmp/darkpool_live_ui.html || true
  cp /tmp/darkpool_live_ui.html "$ORB_SITE/darkpool/index.html"
  rm -f /tmp/darkpool_live_ui.html
fi

# 17) Sanitize (no trader/source names, no alpaca/yahoo, no ORB5/ORB30)
PAGES=("$ORB_SITE/command/index.html")
for p in overnight weekly daily darkpool gammamap exposure; do
  [ -f "$ORB_SITE/$p/index.html" ] && PAGES+=("$ORB_SITE/$p/index.html")
done
run "site_sanitize" python3 site_sanitize.py "${PAGES[@]}"

# Extra scrub: strip visible 'paper' word from unlocked pages (keep encrypt payloads alone)
python3 - <<'PY'
import re, sys
from pathlib import Path
site = Path(__import__('os').environ['ORB_SITE'])
# unlocked pages only
files = [site/'command/index.html', site/'overnight/index.html', site/'weekly/index.html',
         site/'daily/index.html', site/'darkpool/index.html', site/'gammamap/index.html', site/'exposure/index.html', site/'index.html']
rx = re.compile(r'(?i)\bpaper(?:\s+trading)?\b')
orb = re.compile(r'(?i)\bORB\s*(?:5|30)\b')
for f in files:
    if not f.exists(): continue
    t = f.read_text(encoding='utf-8')
    n = rx.sub('', t)
    n = orb.sub('', n)
    n = re.sub(r'  +', ' ', n)
    if n != t:
        f.write_text(n, encoding='utf-8')
        print('scrubbed', f)
PY

# Abort publish if source names leaked into unlocked pages (same spirit as publish_dashboard)
python3 - <<'PY'
import re, json, sys
from pathlib import Path
desk = Path(__import__('os').environ['ORB_DESK'])
site = Path(__import__('os').environ['ORB_SITE'])
sys.path.insert(0, str(desk))
import site_sanitize as S
handles = []
for name in ('handles.json','newswire_handles.json'):
    p = desk/'xnews'/name
    if p.exists():
        handles += json.loads(p.read_text())
pat = r'yahoo|alpaca|first ?squawk|' + '|'.join(re.escape(h) for h in handles) + r'|voltick|\bvolts?\b|\bORB ?(5|30)\b|x\.com/|twitter\.com/|' + '|'.join(re.escape(n) for n in S.NAMES)
rx = re.compile(pat, re.I)
bad = []
for rel in ('command/index.html','overnight/index.html','weekly/index.html','daily/index.html','darkpool/index.html','gammamap/index.html','exposure/index.html'):
    f = site/rel
    if not f.exists(): continue
    t = f.read_text(encoding='utf-8', errors='replace')
    if rx.search(t):
        m = rx.search(t)
        bad.append(f"{rel}: matched {m.group(0)!r}")
if bad:
    print('ABORT: source name/handle leaked:', *bad, sep='\n  ', file=sys.stderr)
    sys.exit(1)
print('sanitize gate: ok')
PY

echo "refresh complete"
