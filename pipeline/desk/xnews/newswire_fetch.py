#!/usr/bin/env python3
"""THE WIRE: market news wire feed for the Attaché desk (paper/research only).

Bot sweep writes X search payloads to pipeline/inputs/newswire_raw.json (synced into xnews/newswire/).
Actions then runs: python3 newswire_fetch.py  (reads newswire/newswire_raw.json, or raw_*.txt fallback).
Manual/legacy: save x.search_posts_all dumps to newswire/raw_*.txt then run this script.
It merges into newswire/cache.json (72h), drops non-market items, tags impact, rewrites headlines short, and writes
xnews/newswire.json (top 20, newest first). Output carries NO handles, names or links: only SRC tags (W1, W2 by
order in newswire_handles.json). newswire_handles.json is kept separate from handles.json (trading plan list).
"""
import json, re, sys, glob, html
from pathlib import Path
from datetime import datetime, timezone, timedelta
from zoneinfo import ZoneInfo
X = Path(__file__).resolve().parent; N = X / 'newswire'; N.mkdir(exist_ok=True)
HANDLES = json.loads((X / 'newswire_handles.json').read_text())
SRC = {h.lower(): f'SRC W{i+1}' for i, h in enumerate(HANDLES)}
PT = ZoneInfo('America/Los_Angeles')
CACHE = N / 'cache.json'

TAGS = [  # first match wins (order = priority)
 ('FED', r'\b(fed|fomc|powell|waller|bowman|jefferson|logan|daly|goolsbee|hammack|barkin|kashkari|musalem|schmid|williams|rate (cut|hike)s?|central bank|ecb|boj|bo[ej]|lagarde|ueda|rba|pboc|snb|riksbank)\b'),
 ('ENERGY', r'\b(oil|crude|brent|wti|opec|natural gas|lng|refiner\w*|gasoline|fuel|energy|eia|barrels?)\b'),
 ('RATES', r'\b(yield|yields|treasur\w*|bonds?|jgb|bund|gilt|basis points|bps|curve)\b'),
 ('FX', r'\b(dollar|yen|yuan|euro|peso|rupee|won|sterling|gbp|eur|usd|jpy|aud|cad|chf|cny|currenc\w*|forex|fx)\b'),
 ('EARNINGS', r'\b(earnings|eps|revenue|guidance|q[1-4]\b|quarter(ly)?|profit|price target|pt to|upgrade[sd]?|downgrade[sd]?|beats?|misses|outlook|results)\b'),
 ('MACRO', r'\b(cpi|ppi|pce|inflation|gdp|jobs|payrolls|unemployment|jobless|retail sales|pmi|ism|housing|consumer (sentiment|confidence)|trade (deficit|surplus|balance)|growth|recession|electricity consumption)\b'),
 ('GEO', r'\b(war|missile|strike[s]?|military|iran|israel|gaza|russia|ukraine|north korea|taiwan|sanction\w*|nato|conflict|attack|troops|drone|putin|zelensky|peace (deal|talks|proposal)|ceasefire)\b'),
 ('POLICY', r'\b(tariff\w*|trade (deal|war|talks)|white house|trump|congress|senate|house vote|shutdown|bill|regulat\w*|sec\b|antitrust|executive order|budget|deficit|tax\w*|election|prime minister|treasury secretary|bessent)\b'),
 ('TECH', r'\b(ai|openai|nvidia|chips?|semiconductor\w*|apple|microsoft|google|alphabet|meta|amazon|tesla|spacex|data center)\b'),
 ('EQUITY', r'\b(stocks?|shares|index|s&p|nasdaq|dow|nyse|ipo|equit\w*|futures|nikkei|hang seng|kospi|market[s]?|exchange|bank[s]?|m&a|merger|acqui\w*|layoffs?|jobs cuts?)\b'),
 ('CRYPTO', r'\b(bitcoin|crypto\w*|ether(eum)?|stablecoin)\b'),
]
TAGS = [(t, re.compile(p, re.I)) for t, p in TAGS]
FLUFF = re.compile(r'\b(nfl|nba|mlb|nhl|world series|super bowl|playoffs?|touchdown|recipe|celebrit\w*|halloween|costume|movie|oscars?|grammy|concert|taylor swift|wedding|dating|fashion|travel tips|horoscope|pets?|dog|cat|wellness|sleep|diet|vacation|museum|police forces|personnel information|weather|hollywood|snl|comedy|comedian|podcast\w*|mediatrends\w*|midterm\w*|fundrais\w*|tells @\w+)\b', re.I)
BREAKING_MIN = 30

def load_raw(p):
    s = Path(p).read_text(encoding='utf-8', errors='replace')
    i = s.find('{"data"')
    if i < 0: i = s.find('{')
    if i < 0: return []
    try: d, _ = json.JSONDecoder().raw_decode(s[i:])
    except Exception: return []
    users = {u['id']: u.get('username', '') for u in d.get('includes', {}).get('users', [])}
    out = []
    for t in d.get('data', []):
        h = users.get(t.get('author_id'), '') or (re.search(r'x\.com/([^/]+)/status', t.get('url', '')) or [None, ''])[1]
        out.append({'id': t['id'], 'at': t['created_at'], 'src': SRC.get(h.lower(), 'SRC W?'), 'text': t.get('text', '')})
    return out

def rewrite(t):
    t = html.unescape(t)
    t = re.sub(r'https?://\S+', '', t)
    t = re.sub(r'(?<!\w)[@#](\w+)', r'\1', t)
    t = t.split('\n')[0].strip()
    t = re.sub(r'\s*[-–—]\s*(SCMP|WSJ|RTRS|NA|KYODO|FX|BBG|BLOOMBERG|FT|CNBC|AP|AFP|NIKKEI|XINHUA|DJ|MNI|YONHAP|REUTERS)\s*$', '', t, flags=re.I)
    t = re.sub(r'^(BREAKING|JUST IN|SCOOP|NEW|SCOOPLET)\s*[:\-–—]\s*', '', t, flags=re.I)
    rep = [(r'\bPresident\b', 'Pres.'), (r'\bGovernment\b', 'Govt'), (r'\bPercent\b', '%'), (r'\bBasis Points\b', 'bp'),
           (r'\bPrice Target\b', 'PT'), (r'\bTrillion\b', 'tn'), (r'\bBillion\b', 'bn'), (r'\bMillion\b', 'mn'), (r'\s+', ' ')]
    for a, b in rep: t = re.sub(a, b, t, flags=re.I)
    t = t.strip(' .:-–—')
    if len(t) > 84:
        t = t[:84].rsplit(' ', 1)[0].rstrip(',;:') + '…'
    return t[:1].upper() + t[1:]

def classify(text):
    if FLUFF.search(text) or re.match(r'^\s*["“]', text): return None
    for tag, rx in TAGS:
        if rx.search(text): return tag
    return None  # not market-relevant -> dropped

def plan():
    c = json.loads(CACHE.read_text()) if CACHE.exists() else {}
    since = max((i['id'] for i in c.values()), key=int, default=None)
    base = {'sort_order': 'recency', 'post.fields': 'created_at,author_id', 'expansions': 'author_id', 'user.fields': 'username'}
    for h, n, f in [('FirstSquawk', 25, 'raw_squawk.txt'), ('axios', 15, 'raw_axios.txt')]:
        a = dict(base, query=f'from:{h} -is:retweet -is:reply', max_results=n)
        if since: a['since_id'] = since
        print(json.dumps({'tool': 'x.search_posts_all', 'save_to': str(N / f), 'arguments': a}))

def load_raw_bundle(path):
    """Load bot-written pipeline/inputs/newswire_raw.json (or desk copy).
    Shape: {sources: {Handle: {data, includes, ...}}} or a bare X API payload.
    Also accepts a list of such payloads.
    """
    d = json.loads(Path(path).read_text(encoding='utf-8'))
    out = []
    if isinstance(d, dict) and 'sources' in d:
        for handle, payload in d['sources'].items():
            users = {u['id']: u.get('username', '') for u in payload.get('includes', {}).get('users', [])}
            for t in payload.get('data', []) or []:
                h = users.get(t.get('author_id'), '') or handle
                out.append({'id': t['id'], 'at': t['created_at'], 'src': SRC.get(h.lower(), 'SRC W?'), 'text': t.get('text', '')})
        return out
    # bare payload or list
    payloads = d if isinstance(d, list) else [d]
    for payload in payloads:
        users = {u['id']: u.get('username', '') for u in payload.get('includes', {}).get('users', [])}
        for t in payload.get('data', []) or []:
            h = users.get(t.get('author_id'), '') or (re.search(r'x\.com/([^/]+)/status', t.get('url', '')) or [None, ''])[1]
            out.append({'id': t['id'], 'at': t['created_at'], 'src': SRC.get(h.lower(), 'SRC W?'), 'text': t.get('text', '')})
    return out

def main(files):
    now = datetime.now(timezone.utc)
    c = json.loads(CACHE.read_text()) if CACHE.exists() else {}
    files = list(files) if files else []
    # Prefer bot-written bundle if present (synced from pipeline/inputs/newswire_raw.json)
    bundle = N / 'newswire_raw.json'
    if not files and bundle.exists():
        for p in load_raw_bundle(bundle): c[p['id']] = p
    elif not files:
        files = sorted(glob.glob(str(N / 'raw_*.txt')))
    for f in files:
        fp = Path(f)
        if fp.name == 'newswire_raw.json' or fp.suffix == '.json' and 'newswire_raw' in fp.name:
            for p in load_raw_bundle(fp): c[p['id']] = p
        else:
            for p in load_raw(f): c[p['id']] = p
    cut = now - timedelta(hours=72)
    c = {k: v for k, v in c.items() if datetime.fromisoformat(v['at'].replace('Z', '+00:00')) >= cut}
    CACHE.write_text(json.dumps(c))
    items = []
    for p in sorted(c.values(), key=lambda p: p['at'], reverse=True):
        tag = classify(p['text'])
        if not tag: continue
        h = rewrite(p['text'])
        if not h or any(h.lower() == i['headline'].lower() for i in items): continue
        t = datetime.fromisoformat(p['at'].replace('Z', '+00:00'))
        items.append({'ts_utc': p['at'], 'time_pt': t.astimezone(PT).strftime('%H:%M'), 'date_pt': t.astimezone(PT).strftime('%m/%d'),
                      'headline': h, 'tag': tag, 'src': p['src'], 'breaking': (now - t) <= timedelta(minutes=BREAKING_MIN)})
        if len(items) >= 20: break
    out = {'generated_at_pt': now.astimezone(PT).strftime('%Y-%m-%d %H:%M PT'), 'generated_utc': now.isoformat(timespec='seconds'),
           'breaking_minutes': BREAKING_MIN, 'items': items}
    (X / 'newswire.json').write_text(json.dumps(out, indent=1, ensure_ascii=False))
    print(f'newswire: {len(items)} items, {sum(i["breaking"] for i in items)} breaking, cache {len(c)}')

if __name__ == '__main__':
    if '--plan' in sys.argv: plan()
    else: main([a for a in sys.argv[1:] if not a.startswith('--')])
