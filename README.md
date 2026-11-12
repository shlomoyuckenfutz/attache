# Attaché

Live site: https://shlomoyuckenfutz.github.io/attache/

## Updating SPY Dark Pool levels

Single source of truth: [`data/spy_dark_pool.json`](data/spy_dark_pool.json).

1. Edit the `levels` array (SPY prices, high → low). Purple chart labels only — label them **Dark Pool** on the site (no source names).
2. Recompute `rows` (or leave them to a rebuild):  
   - `SPX = SPY ÷ 0.0997`  
   - `ES = SPX + 34.5` (Fri close basis)
3. Sync the monitor config used by Command: copy `levels` into `/workspace/desk/orb-research/es_levels/darkpool_levels.json`.
4. Rebuild plan pages from orb-research (reads the JSON via `dark_pool_html.py`):

```bash
cd /workspace/desk/orb-research
python3 -c "import build_weekly; h,_,_=build_weekly.page(build_weekly.src()); build_weekly.W.joinpath('index.html').write_text(h)"
python3 -c "import build_daily; p,_=build_daily.load_plan(build_daily.site_dir()); h,_,_,_=build_daily.page(p, build_daily.site_dir()); (build_daily.site_dir()/'daily'/'index.html').write_text(h)"
cp weekly/index.html /workspace/orb-dash-site/weekly/
cp daily/index.html /workspace/orb-dash-site/daily/
```

5. Desk **DARK POOL POSITION · SPY** reads `data/spy_dark_pool.json` at runtime (embedded `D.dpx` is the fallback). After editing levels, update the baked spot in `D.dpx` / Command `"dpx"` to the latest SPY RTH close (recompute distances / nearest; drop stale crossed-today stamps) — or rebuild via `build_master.py` / `build_command.py` once those builders load this JSON.
6. Commit and push this repo.

Do not put ORB-A/ORB-B wording on the site. Keep annotation lines off the candles (edge ticks only).

## Test pages

The old unlinked test pages (command-test, heat-test, study-test, terminal-test, darkpool-test) were removed from the deployed site on 2026-11-11 at Everett's request.
