# Attaché Dark Pool (TEST)

Dedicated Dark Pool organizer page. Live at
https://shlomoyuckenfutz.github.io/attache/darkpool-test/
Locked with StaticCrypt (same Study password). **Not linked from main nav.**

Reads [`../data/spy_dark_pool.json`](../data/spy_dark_pool.json) at runtime.
Levels are tagged `current` (Nov 2–6 plan) or `prior` (older desk seeds / notes).

## Contents

1. Dark Pool Position panel (spot, nearest above/below, distance cards, crossed stamps)
2. Full level table SPY / SPX / ES (ratio + basis from `convert` in JSON)
3. PRICE LADDER — baked SPY **4H** candles (Alpaca IEX 30m→RTH 4H, ~3m) with purple
   **edge ticks only** on the right axis (no annotation lines across candles);
   current levels bright / prior dim; de-overlapped labels; spot dashed;
   SPX/ES on hover (ratio 0.099698, ES basis 33.93); full-width primary chart;
   y-range fits candles; off-chart levels listed in chips; level lines behind candles; clusters as cards
4. LEVEL STATS — per-level touch / bounce / break over ~30d of 5m bars
   (sortable table + bounce-vs-break bar); definitions on page
5. CONVERSION — verified SPY÷SPX ratio + ES−SPX basis (Yahoo Fri closes)
6. LEVEL SCORECARD — distance + bounce/break + session cross stamps
7. TIME ABOVE / BELOW — latest session heat strips per level
8. CLUSTERS — zones of levels within $1, distance from spot
9. Levels last updated + how-to-update note

No source names on the page — label levels **Dark Pool** only.

## Rebuild / re-encrypt (only when HTML shell changes)

```bash
cd /workspace/orb-dash-site
git pull --rebase
node /workspace/desk/orb-research/darkpool_src/encrypt_page.js \
  /workspace/desk/orb-research/darkpool_src/darkpool_plain.html \
  /workspace/desk/orb-research/darkpool_src/lock_shell.html \
  darkpool-test/index.html
git add darkpool-test data/spy_dark_pool.json
git commit -m "refresh darkpool-test"
git push
```

`encrypt_page.js` reads the password from
`/workspace/desk/orb-research/secrets/study_password.txt`
(never print it; do not rely on `ATOUCHE_STUDY_PASSWORD`).

JSON-only level / bars / stats updates do **not** need re-encrypt — just edit
and push `data/spy_dark_pool.json`, then reload the page.

## Stats definitions (also on page)

- **Touch** — 5m bar high/low within $0.10 of level
- **Bounce** — rejected and moved ≥$0.50 away without closing through
- **Break** — 5m close through and holds 2+ subsequent bars on through side
