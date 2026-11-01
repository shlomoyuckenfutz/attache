# Attaché Dark Pool (TEST)

Dedicated Dark Pool organizer page. Live at
https://shlomoyuckenfutz.github.io/attache/darkpool-test/
Locked with StaticCrypt (same Study password). **Not linked from main nav.**

Reads [`../data/spy_dark_pool.json`](../data/spy_dark_pool.json) at runtime.

## Contents

1. Dark Pool Position panel (spot, nearest above/below, distance cards)
2. Full level table SPY / SPX / ES (`SPX = SPY ÷ 0.0997`, `ES = SPX + 34.5`)
3. Simple price ladder with purple edge ticks (no candle overlays)
4. Levels last updated + how-to-update note

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

JSON-only level updates do **not** need re-encrypt — just edit and push
`data/spy_dark_pool.json`, then reload the page.
