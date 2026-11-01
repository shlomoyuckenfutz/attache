"""Strip data-source names, X handles and x.com links from published HTML (owner rule).
Handles from xnews/handles.json (+sources.json) -> neutral 'SRC A', 'SRC B', ... (stable by list order)."""
import json, re, sys, string
B = str(__import__('pathlib').Path(__file__).resolve().parent / 'xnews') + '/'
H = json.load(open(B + 'handles.json'))
for s in json.load(open(B + 'sources.json')):
    if s.get('handle') and s['handle'] not in H: H.append(s['handle'])
try:  # THE WIRE news accounts (separate list; never in handles.json, which feeds the trading plan)
    for h in json.load(open(B + 'newswire_handles.json')):
        if h not in H: H.append(h)
except FileNotFoundError: pass
# NIGHT LEDGER source (never in handles.json): appended last so existing SRC tags stay stable
if 'SRC_LEDGER' not in H: H.append('SRC_LEDGER')
# ES auction/profile plans source (never in handles.json): appended after the ledger so SRC tags stay stable
if 'smashelito' not in H: H.append('smashelito')
def tag(i): return 'SRC ' + (string.ascii_uppercase[i] if i < 26 else string.ascii_uppercase[i // 26 - 1] + string.ascii_uppercase[i % 26])
M = {h.lower(): tag(i) for i, h in enumerate(H)}
ALIAS = {'voltick': 'VoltickIO', 'mancini': 'SRC_LEVELS_A', 'jonesy': 'TraderJonesy', 'spartan': 'SRC_PLAN_B',
         'cheddar': 'CheddarFlow', 'unusual whales': 'unusual_whales', 'whales': 'unusual_whales', 'sleuth': 'market_sleuth',
         'bobby': 'FlowbyBobby', 'shark': '_Shark_Trading', 'sniper': 'TradeSniperSara', 'anderson': 'GAndersonTrades', 'yuriy': 'yuriymatso',
         'basssem': 'Basssem666', 'kctrades': 'KCTrades777', 'optionking': 'OptionKing33996', 'luckeee': 'SuperLuckeee', 'first squawk': 'FirstSquawk', 'firstsquawk': 'FirstSquawk', 'bento': 'SRC_LEDGER', 'valois': 'SRC_LEDGER'}
for a, h in ALIAS.items(): M.setdefault(a, M[h.lower()])
NAMES = sorted(M, key=len, reverse=True)
RX = re.compile('@?(' + '|'.join(re.escape(n) for n in NAMES) + ')', re.I)
URL = re.compile(r'https?:(?:\\?/){2}(?:www\.|mobile\.)?(?:x|twitter)\.com(?:\\?/)[^\s"\'<>`)]*', re.I)
def clean(s):
    s = URL.sub('#', s)
    s = re.sub(r'(?i)(?:www\.)?(?:x|twitter)\.com/[^\s"\'<>`)]*', '#', s)
    s = re.sub(r'(?i)alpaca-indicative', 'indicative', s)
    s = re.sub(r'(?i)yahoo finance|yahoo', 'free data', s)
    s = re.sub(r'(?i)alpaca', 'free feed', s)
    # JS property access (D.spartan) -> D["SRC D"] so renamed keys still resolve
    s = re.sub(r'(?<=[\w\)\]])\.(' + '|'.join(re.escape(n) for n in NAMES) + r')\b', lambda m: '["' + M[m.group(1).lower()] + '"]', s, flags=re.I)
    s = RX.sub(lambda m: M[m.group(1).lower()], s)
    # 'Volt' level names -> MAGNET (word-bounded so volatility/voltage-like words are untouched)
    s = re.sub(r'(?i)\bfront volts?\b', 'FRONT MAGNET', s)
    return re.sub(r'\b(?:VOLTS?|[Vv]olts?)\b', 'MAGNET', s)
if __name__ == '__main__':
    for p in sys.argv[1:]:
        t = open(p, encoding='utf-8').read(); n = clean(t)
        if n != t: open(p, 'w', encoding='utf-8').write(n)
