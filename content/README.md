# Manual text sections (/edit/)

- `sections.json`: the editable text sections, with where each one sits on each page.
- `overrides.json`: locked text, written only by `/edit/` (one commit per save). The scheduled refresh, sweeps and the Night Ledger never write this file.
- `edit-overrides.js`: finds a section on a page and shows the locked text in place of the generated text. Inlined into Command, Daily, Weekly and Overnight by `apply_overrides.py`; `/edit/` loads it too.

A lock lasts until its expiry (end of the session day, end of the plan week, end of today) or until Release is pressed. The page underneath keeps getting rebuilt, so releasing brings the newest generated text straight back. Add `?ov=off` to a page address to see the generated text.
