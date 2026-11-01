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

5. Refresh Command / desk DP panels from the same levels (`build_command.py` / publish), or surgically replace the embedded `"dp"` / `"darkpool"` arrays.
6. Commit and push this repo.

Do not put ORB5/ORB30 wording on the site. Keep annotation lines off the candles (edge ticks only).
