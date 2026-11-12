# Attaché pipeline (class-A refresh)

GitHub Actions runs `refresh.sh` on a schedule. Bot-only inputs (X / LLM / browser) are written here by the desk sweep; Actions reads them and rebuilds the public site.

## Bot sweep must write to these paths

| Artifact | Path |
|---|---|
| Trading plan | `pipeline/inputs/plan.json` |
| Flow tape | `pipeline/inputs/flow.json` |
| X-levels raw | `pipeline/inputs/xlevels/levels_raw.json` |
| Handles / sources | `pipeline/inputs/xlevels/handles.json`, `newswire_handles.json`, `sources.json` |
| Optional derived xlevels | `pipeline/inputs/xlevels/{confluence,gamma,scorecard}.json` |
| Night Ledger issues | `pipeline/inputs/ledger/YYYY-MM-DD.md` |
| First Blade post | `pipeline/inputs/plan_b/plan_b.json` |
| Iron Ladder ES levels | `pipeline/inputs/levels_a/levels_a.json` |
| Dark Pool levels | `pipeline/inputs/spy_dark_pool.json` **and** `pipeline/inputs/darkpool_levels.json` |
| Weekly plan text | `pipeline/inputs/plans/yuckenfutz-weekly-YYYY-MM-DD.txt` |
| Newswire raw (X MCP) | `pipeline/inputs/newswire_raw.json` (Actions runs `newswire_fetch.py` → patches THE WIRE) |

Do **not** commit secrets. `desk/secrets/study_password.txt` is runtime-only (from Actions secret `ATOUCHE_STUDY_PASSWORD`).

## Local dry-run

```bash
export FEED_API_KEY=... FEED_SECRET_KEY=...  # mapped from Actions secrets ATOUCHE_STUDY_PASSWORD=...
cd pipeline && bash refresh.sh
```

## Manual text overrides (`/edit/`)

Everett edits text sections at `/edit/` (unlinked, noindex). A save commits `content/overrides.json` through the GitHub Contents API with his own fine-grained token, which stays in his browser. The token is never in the repo.

How his text survives rebuilds:

1. Nothing automated writes `content/overrides.json`. Not `refresh.sh`, sweeps, the Night Ledger, or `publish_dashboard.sh`.
2. The builders keep writing their own text. `apply_overrides.py` (step 16b in `refresh.sh`, after `ui_shell`, before sanitize) bakes one `<!--EDITOV-->` block into Command, Daily, Weekly and Overnight. The block holds the section map, the active locks and the loader. On load, the page swaps in his locked text, then re-reads `content/overrides.json` so a new save or release shows right after the Pages deploy.
3. Any job that rebuilds or patches those four pages outside `refresh.sh` must run `python3 pipeline/desk/apply_overrides.py` before it pushes. `tests/test_edit_portal.py` fails if a page is missing the block or an active lock isn't baked in, so pushes gated on the test suite can't drop his edits.

Locks expire at the end of the session day or plan week, or at end of today (PT), or stay until released, depending on what he picks. Each edited section shows a small `edited <time> PT` stamp. Key levels, pivots, tables, ORB15 and hourly data are not editable.
