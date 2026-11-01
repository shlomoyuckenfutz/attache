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
copy_if "$IN/spartan/plan_b.json" "$DESK/xnews/spartan/plan_b.json"
copy_if "$IN/implied_move/implied_move.json" "$DESK/xnews/implied_move/implied_move.json"
copy_if "$IN/darkpool_levels.json"  "$DESK/es_levels/darkpool_levels.json"
copy_if "$IN/spy_dark_pool.json"    "$SITE/data/spy_dark_pool.json"

# bento markdown issues
if [ -d "$IN/bento" ]; then
  mkdir -p "$DESK/xnews/bento"
  cp -a "$IN/bento/"*.md "$DESK/xnews/bento/" 2>/dev/null || true
  copy_if "$IN/bento/ledger.json" "$DESK/xnews/bento/ledger.json"
fi

# mancini
if [ -d "$IN/mancini" ]; then
  mkdir -p "$DESK/xnews/mancini"
  cp -a "$IN/mancini/"*.json "$DESK/xnews/mancini/" 2>/dev/null || true
fi

# weekly plans already read from inputs/plans by build_weekly
echo "sync_inputs: ok"
