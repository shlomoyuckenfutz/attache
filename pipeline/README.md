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
| Night Ledger issues | `pipeline/inputs/bento/YYYY-MM-DD.md` |
| First Blade post | `pipeline/inputs/spartan/plan_b.json` |
| Mancini ES levels | `pipeline/inputs/mancini/levels_a.json` |
| Dark Pool levels | `pipeline/inputs/spy_dark_pool.json` **and** `pipeline/inputs/darkpool_levels.json` |
| Weekly plan text | `pipeline/inputs/plans/yuckenfutz-weekly-YYYY-MM-DD.txt` |
| Newswire raw (X MCP) | `pipeline/inputs/newswire_raw.json` (Actions runs `newswire_fetch.py` → patches THE WIRE) |

Do **not** commit secrets. `desk/secrets/study_password.txt` is runtime-only (from Actions secret `ATOUCHE_STUDY_PASSWORD`).

## Local dry-run

```bash
export ALPACA_API_KEY=... ALPACA_SECRET_KEY=... ATOUCHE_STUDY_PASSWORD=...
cd pipeline && bash refresh.sh
```
