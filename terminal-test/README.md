# Attaché Terminal (TEST)

Bloomberg-style wall of free-data panels. Live at
https://shlomoyuckenfutz.github.io/attache/terminal-test/
Locked with StaticCrypt (same Study password). Not linked from main nav.

## Refresh snapshot (run by hand — no routine)

```bash
cd /workspace/orb-dash-site
git pull --rebase
python3 scripts/terminal_fetch.py
node /workspace/desk/orb-research/terminal_src/encrypt_page.js \
  /workspace/desk/orb-research/terminal_src/terminal_plain.html \
  /workspace/desk/orb-research/terminal_src/lock_shell.html \
  terminal-test/index.html
git add terminal-test scripts/terminal_fetch.py
git status
git commit -m "refresh terminal-test snapshot"
git push
```

`encrypt_page.js` reads the password from
`/workspace/desk/orb-research/secrets/study_password.txt`
(never print it; do not rely on `ATOUCHE_STUDY_PASSWORD`).

## Panels (free sources only)

1. Quotes/Charts — free_data `query1/query2.finance.free_data.com/v8/finance/chart`
2. Filings — SEC EDGAR (`User-Agent` includes Shlomoyuckenfutz@gmail.com)
3. Macro — FRED `fredgraph.csv` (no API key)
4. News/Earnings — free_data RSS, SEC 8-K atom, Nasdaq earnings calendar JSON
5. Options — free_data options if reachable, else CBOE delayed quotes JSON
6. The Desk — rule-based plain-English summary + “Ask Head Shlomo…”

Each panel shows its error and keeps last-good data on failure.
