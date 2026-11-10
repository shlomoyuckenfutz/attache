"""ATTACHÉ shared UI shell: sticky top bar (wordmark, tabs)
+ shared design tokens, collapsible dense tables, mobile rules. Injected post-build into every page.
usage: python3 ui_shell.py PAGE=FILE [PAGE=FILE ...]   PAGE in command|overnight|weekly|daily|study|studylock|exposure|exposurelock|darkpool|darkpoollock|projectb|projectblock|hub|hublock
Note: DESK tab removed — site root redirects to /command/. Pass page=command for the merged Command page.
Legacy page=desk is accepted as an alias for command (active tab) with root=./ for a root-level file.
Ticker strip (SPY/QQQ sparklines, bias chip, market status, PT clock) removed 2026-10-31."""
import sys, re
from pathlib import Path
R = Path(__file__).resolve().parent
MARK = "<!--UISHELL-->"

CSS = """<style id="uishell">
:root{--bg:#000;--ln:#232323;--ln2:#333;--amb:#ffb000;--amb2:#a87400;--txt:#e6e0cc;--mut:#857d6a;--up:#3ddc5c;--dn:#ff4d4d;--acc:#22c7e8;--na:#6b6b6b;--rad:6px;--gap:10px}
html,body{overflow-x:hidden;max-width:100%}
#ub{position:sticky;top:0;z-index:999;display:flex;flex-wrap:wrap;align-items:center;gap:6px 12px;padding:6px 12px;background:rgba(0,0,0,.94);border-bottom:1px solid var(--amb2);font:12px/1.3 'DejaVu Sans Mono',Consolas,monospace;color:var(--txt);backdrop-filter:blur(4px)}
#ub .ub-w{color:var(--amb);font-weight:700;letter-spacing:.18em;text-decoration:none;font-size:14px;flex:0 0 auto}
/* tab SIZE = original (padding 4px 9px); keep horizontal scroll / wrap behavior from mobile-nav pass */
#ub nav{display:flex;flex-wrap:nowrap;gap:4px;align-items:center;max-width:100%;overflow-x:auto;-webkit-overflow-scrolling:touch;scrollbar-width:thin;overscroll-behavior-x:contain;scroll-snap-type:x proximity}
#ub nav a{color:var(--mut);text-decoration:none;padding:4px 9px;border:1px solid var(--ln2);border-radius:var(--rad);display:inline-flex;align-items:center;justify-content:center;box-sizing:border-box;flex:0 0 auto;white-space:nowrap;scroll-snap-align:center;line-height:1.2}
#ub nav a:hover{color:var(--amb);border-color:var(--amb2)}#ub nav a.on{color:#000;background:var(--amb);border-color:var(--amb)}
.chip{display:inline-flex;align-items:center;padding:2px 8px;border-radius:999px;border:1px solid currentColor;font:700 11px/1.4 'DejaVu Sans Mono',Consolas,monospace;text-decoration:none;letter-spacing:.04em}
.chip.up{color:var(--up)}.chip.dn{color:var(--dn)}.chip.lv{color:var(--amb)}.chip.na{color:var(--na)}.chip.acc{color:var(--acc)}
.pn,.dk,.card,.zone>.dk{border-radius:var(--rad)}
.pn,.dk,.card{transition:border-color .15s,box-shadow .15s}.pn:hover,.dk:hover,.card:hover{border-color:var(--amb2)!important;box-shadow:0 0 0 1px rgba(255,176,0,.08)}
.ux-more{display:block;width:100%;margin:4px 0 0;padding:6px;background:transparent;color:var(--amb);border:1px dashed var(--ln2);border-radius:var(--rad);font:11px 'DejaVu Sans Mono',Consolas,monospace;cursor:pointer}
.ux-more:hover{border-color:var(--amb2)}tr.ux-h{display:none}
.ux-tw{overflow-x:auto;max-width:100%;-webkit-overflow-scrolling:touch}
img,svg,canvas,video{max-width:100%;height:auto}
html{-webkit-text-size-adjust:100%;text-size-adjust:100%}
/* Phone / narrow: real reflow — do not rely on overflow clip to "pass" width checks. Desktop unchanged. */
@media(max-width:700px){
html,body{-webkit-text-size-adjust:100%;text-size-adjust:100%;max-width:100%}
body{font-size:13px!important;line-height:1.45;--fs:13px;--fs-s:12px;--fs-l:14px}
#ub{gap:6px;padding:6px 10px;max-width:100%;box-sizing:border-box}
#ub nav{width:100%;padding-bottom:2px}
#ub nav a{flex:1;justify-content:center;min-height:40px;padding:4px 9px;font-size:12px}
a,button,summary,.ux-more,nav.zl a{min-height:40px}
nav.zl{display:flex;flex-wrap:nowrap;gap:4px;overflow-x:auto;-webkit-overflow-scrolling:touch;max-width:100%}
nav.zl a{display:inline-flex;align-items:center;justify-content:center;flex:0 0 auto;padding:4px 9px;font-size:12px}
pre{white-space:pre-wrap;word-break:break-word;overflow-wrap:anywhere}
.top{flex-wrap:wrap}
main,body,#ub{max-width:100%;width:100%;box-sizing:border-box}
main{grid-template-columns:minmax(0,1fr)!important}
main>*,.zone,.pn,.dk,.card,.zg,.g,.g3,.brief,.scr,.ux-tw,.dpx,.tile,.w2,#biasG,.nw{min-width:0!important;max-width:100%;box-sizing:border-box}
.zg,.g,.g3,.brief,.dk .dkg,.eqs,.oc,.il-g,.hr-wrap,.mc-g,.dpd-g,.gauges,.sp-g,#gtRow,#z-levels .zg,.nw ol{grid-template-columns:minmax(0,1fr)!important}
.w2,.w3{grid-column:auto!important}
/* Wire headlines wrap at sane size */
.nw,.nw li,.nw li .h{font-size:13px!important}
.nw li{grid-template-columns:40px 64px minmax(0,1fr)!important;gap:6px}
.nw li .h,.nw li .t,.nw .nh{white-space:normal!important;overflow:visible!important;text-overflow:clip!important;overflow-wrap:anywhere;word-break:break-word}
.nw li .s{display:none}
/* Bias gauge */
#biasG{font-size:13px!important;padding:8px;max-width:100%;overflow:visible}
#biasG .bg-l{font-size:14px!important;padding:0 6px;letter-spacing:1px}
#biasG .bg-s{font-size:14px!important}
#biasG .bg-m{width:100%!important;max-width:100%;box-sizing:border-box;margin:10px 0 18px}
#biasG .bg-h{flex-wrap:wrap;gap:6px 10px}
#biasG .bg-h small{white-space:normal;overflow-wrap:anywhere;flex:1 1 100%}
#biasG>div:not(.bg-h):not(.bg-m):not(.bg-nw){display:flex;flex-wrap:wrap;gap:4px;max-width:100%}
#biasG .bg-c{display:inline-flex;flex:0 1 auto;white-space:normal;font-size:12px;max-width:100%}
#biasG .bg-nw{white-space:normal!important;overflow-wrap:anywhere;word-break:break-word;font-size:13px!important;max-width:100%}
#biasG .bg-nw b{font-size:13px!important}
/* Futures chatter + generic note cells */
#ftX table{font-size:13px!important;width:100%}
#ftX th,#ftX td{font-size:13px!important;white-space:normal!important;overflow-wrap:anywhere;word-break:break-word;vertical-align:top}
#ftX th:first-child,#ftX td:first-child{display:none} /* hide WHEN on phones */
#ftX td.w,#ftX td:last-child{color:var(--txt);font-size:13px!important;font-weight:400}
table{font-size:13px}
th,td{font-size:inherit}
.ux-tw td,.ux-tw th,.scr td,.scr th{white-space:nowrap}
#ftX td,#ftX th,td.w{white-space:normal!important;overflow-wrap:anywhere}
.ux-tw,.scr,.dk,.hr-card,.tbl-wrap,table.sheet{overflow-x:auto;-webkit-overflow-scrolling:touch;max-width:100%}
td.w{min-width:0!important;white-space:normal!important;overflow-wrap:anywhere}
img,svg,canvas,video{max-width:100%!important;height:auto}
.nt,p,li,.mut,small,.cap,.tile .s,.ph small{overflow-wrap:anywhere;word-break:break-word;white-space:normal}
.lad{grid-template-columns:minmax(0,1fr)!important}
/* Dark Pool level cards: keep original multi-col; scroll sideways if needed — do not stack to 1fr */
.dpx{overflow-x:auto;-webkit-overflow-scrolling:touch;max-width:100%}
.dpx .dg{grid-template-columns:repeat(auto-fill,minmax(110px,1fr))!important;min-width:0}
}

@media(max-width:430px){
.brief,.eqs,.sp-g,.fb-lv,.vz-kp{grid-template-columns:minmax(0,1fr)!important}
}
@media(max-width:420px){
#ub nav{flex-wrap:wrap;overflow-x:visible;scroll-snap-type:none;row-gap:4px}
#ub nav a{flex:1 1 calc(33.33% - 4px);min-width:calc(33.33% - 4px);text-align:center;padding:4px 6px;min-height:40px;font-size:11px}
}
</style>"""

JS = """<script>(()=>{
const nav=document.querySelector('#ub nav'),on=nav&&nav.querySelector('a.on');
if(nav&&on&&nav.scrollWidth>nav.clientWidth){try{on.scrollIntoView({inline:'center',block:'nearest',behavior:'instant'})}catch(e){on.scrollIntoView(false)}}
const run=()=>{document.querySelectorAll('table').forEach(tb=>{if(tb.closest('#ub')||tb.closest('.ux-tw'))return;const w=document.createElement('div');w.className='ux-tw';tb.parentNode.insertBefore(w,tb);w.appendChild(tb);
const rs=[...(tb.tBodies[0]||tb).rows].filter(r=>!r.querySelector('th'));if(rs.length>10){const K=6;rs.slice(K).forEach(r=>r.classList.add('ux-h'));const b=document.createElement('button');b.className='ux-more';b.type='button';
const L=()=>b.textContent=b.dataset.o?'less ▲':'more ▼ ('+(rs.length-K)+' rows)';L();b.onclick=()=>{b.dataset.o=b.dataset.o?'':'1';rs.slice(K).forEach(r=>r.classList.toggle('ux-h',!b.dataset.o));L()};w.after(b)}})};document.readyState=='loading'?document.addEventListener('DOMContentLoaded',run):setTimeout(run,0)})()</script>"""

def bar(page, root):
    # No DESK tab — root redirects to command/
    tabs = [("command", "COMMAND CENTER", "command/"), ("overnight", "OVERNIGHT", "overnight/"), ("weekly", "WEEKLY", "weekly/"), ("daily", "DAILY", "daily/"), ("study", "STUDY", "study/"), ("exposure", "HEAT", "exposure/"), ("darkpool", "DARK POOL", "darkpool/"), ("gammamap", "GAMMA MAP", "gammamap/"), ("projectb", "PROJ B", "project-b/")]
    cur = "study" if page in ("studylock", "study") else \
          "exposure" if page in ("exposurelock", "exposure") else \
          "darkpool" if page in ("darkpoollock", "darkpool") else \
          "projectb" if page in ("projectblock", "projectb") else \
          "command" if page in ("desk", "command") else \
          "hub" if page in ("hub", "hublock") else page
    # hub is not a main tab; leave no .on if hub
    nav = "".join(f'<a href="{root}{h}"{" class=on" if k == cur and page not in ("hub","hublock") else ""}>{n}</a>' for k, n, h in tabs)
    # Wordmark → command (merged home)
    home = f"{root}command/"
    if page == "desk":
        home = "./command/"
    return (f'{MARK}{CSS}<header id="ub"><a class="ub-w" href="{home}">ATTACHÉ</a><nav>{nav}</nav></header>{JS}{MARK}')

def inject(page, f):
    s = Path(f).read_text(); s = re.sub(re.escape(MARK) + ".*?" + re.escape(MARK), "", s, flags=re.S)
    # desk alias = root-level file; everything else is one level down
    root = "./" if page == "desk" else "../"
    m = re.search(r"<body[^>]*>", s)
    s = s[:m.end()] + bar(page, root) + s[m.end():] if m else bar(page, root) + s
    Path(f).write_text(s); print("ui shell ->", page, f)

if __name__ == "__main__":
    for a in sys.argv[1:]: inject(*a.split("=", 1))
