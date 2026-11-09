#!/usr/bin/env bash
# Copy pipeline/inputs (bot sweep writes here) into pipeline/desk working paths.
set -euo pipefail
PIPE="$(cd "$(dirname "$0")" && pwd)"
IN="$PIPE/inputs"
DESK="$PIPE/desk"
SITE="$(cd "$PIPE/.." && pwd)"

copy_if() { # src dest
  if [ -f "$1" ]; then mkdir -p "$(dirname "$2")"; cp -a "$1" "$2"; fi
}

copy_if "$IN/plan.json"            "$DESK/xnews/plan.json"
copy_if "$IN/flow.json"            "$DESK/xnews/flow/flow.json"
copy_if "$IN/xlevels/levels_raw.json" "$DESK/xnews/levels_raw.json"
copy_if "$IN/xlevels/confluence.json" "$DESK/xnews/confluence.json"
copy_if "$IN/xlevels/gamma.json"      "$DESK/xnews/gamma.json"
copy_if "$IN/xlevels/scorecard.json"  "$DESK/xnews/scorecard.json"
copy_if "$IN/xlevels/handles.json"    "$DESK/xnews/handles.json"
copy_if "$IN/xlevels/newswire_handles.json" "$DESK/xnews/newswire_handles.json"
copy_if "$IN/xlevels/sources.json"    "$DESK/xnews/sources.json"
copy_if "$IN/xlevels/week_raw_posts.json" "$DESK/xnews/week_raw/posts.json"
# THE WIRE raw X pulls (bot writes; Actions runs newswire_fetch.py)
copy_if "$IN/newswire_raw.json"     "$DESK/xnews/newswire/newswire_raw.json"
copy_if "$IN/plan_b/plan_b.json" "$DESK/xnews/plan_b/plan_b.json"
copy_if "$IN/implied_move/implied_move.json" "$DESK/xnews/implied_move/implied_move.json"
copy_if "$IN/implied_move/sourced_im.json" "$DESK/xnews/implied_move/sourced_im.json"
copy_if "$IN/darkpool_levels.json"  "$DESK/es_levels/darkpool_levels.json"
copy_if "$IN/spy_dark_pool.json"    "$SITE/data/spy_dark_pool.json"

# Night Ledger markdown issues
if [ -d "$IN/ledger" ]; then
  mkdir -p "$DESK/xnews/ledger"
  cp -a "$IN/ledger/"*.md "$DESK/xnews/ledger/" 2>/dev/null || true
  copy_if "$IN/ledger/ledger.json" "$DESK/xnews/ledger/ledger.json"
  # same-day intraday sidecars for ledger_parse (intraday_YYYY-MM-DD.json)
  shopt -s nullglob
  for f in "$IN/ledger"/intraday_*.json; do
    cp -a "$f" "$DESK/xnews/ledger/"
  done
  shopt -u nullglob
fi

# levels_a
if [ -d "$IN/levels_a" ]; then
  mkdir -p "$DESK/xnews/levels_a"
  cp -a "$IN/levels_a/"*.json "$DESK/xnews/levels_a/" 2>/dev/null || true
fi

# weekly plans already read from inputs/plans by build_weekly
echo "sync_inputs: ok"
