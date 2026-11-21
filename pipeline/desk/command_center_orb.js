// ORB STATUS section, carried over unchanged from the previous Command page (ORB15 cards, cumulative R, bot box).
const $=s=>document.querySelector(s)||document.createElement("div"),E=s=>String(s??'').replace(/[&<>"]/g,m=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'})[m]);
const f=(x,d=2)=>x==null||isNaN(x)?'–':(+x).toFixed(d),sg=(x,d=2)=>x==null?'–':(x>0?'+':'')+(+x).toFixed(d);
const ND='<div class="nd">awaiting update</div>';
const T=t=>`<title>${E(t)}</title>`;
const hm=i=>{const m=570+i;return `${Math.floor(m/60)}:${String(m%60).padStart(2,'0')}`};
const $m=x=>x>=1e9?'$'+(x/1e9).toFixed(2)+'B':x>=1e6?'$'+(x/1e6).toFixed(2)+'M':x>=1e3?'$'+(x/1e3).toFixed(0)+'K':'$'+x;
// ---------- ORB hero
function orbCard(sym,col){const el=$('#orb'+sym),o=(D.orb||{})[sym];
 let h=`<div class="ph"><span>${o&&o.sym?o.sym:(sym=='ES'?'/ES':sym)} · ORB15</span><small>${o?o.date+' ET':''}</small></div>`;
 if(!o){el.innerHTML=h+ND;return}
 const b=o.bars,W=420,Hh=170,pl=4,pr=46,pt=6,pb=16;let lo=Math.min(...b.map(x=>x[3]),o.stop??o.px??1e9),hi=Math.max(...b.map(x=>x[2]),o.target??o.px??-1e9);const pad=(hi-lo)*.05;lo-=pad;hi+=pad;
 const X=i=>pl+(W-pl-pr)*i/389,Y=p=>pt+(Hh-pt-pb)*(hi-p)/(hi-lo);
 let s=`<svg viewBox="0 0 ${W} ${Hh}">`;
 s+=`<rect x="${X(0)}" y="${Y(o.H)}" width="${X(389)-X(0)}" height="${Y(o.L)-Y(o.H)}" fill="${col}" opacity=".08"/>`;
 s+=`<rect x="${X(0)}" y="${Y(o.H)}" width="${X(14)-X(0)}" height="${Y(o.L)-Y(o.H)}" fill="${col}" opacity=".22">${T('Opening range 9:30–9:44 ET')}</rect>`;
 [[o.H,'OR H',col],[o.M,'MID','#857d6a'],[o.L,'OR L',col]].forEach(([p,l,c])=>s+=`<line x1="${X(0)}" x2="${X(389)}" y1="${Y(p)}" y2="${Y(p)}" stroke="${c}" stroke-dasharray="${l=='MID'?'2 3':'4 2'}"><title>${l} ${f(p,3)}</title></line><text x="${W-pr+3}" y="${Y(p)+3}" fill="${c}" font-size="9">${f(p)}</text>`);
 s+=`<polyline fill="none" stroke="#e6e0cc" stroke-width="1" points="${b.map(x=>X(x[0]).toFixed(1)+','+Y(x[4]).toFixed(1)).join(' ')}"/>`;
 if(o.entry){const[i,e]=o.entry;s+=`<line x1="${X(i)}" x2="${X(389)}" y1="${Y(o.stop)}" y2="${Y(o.stop)}" stroke="var(--dn)" stroke-width=".8"><title>stop ${f(o.stop,3)}</title></line><line x1="${X(i)}" x2="${X(389)}" y1="${Y(o.target)}" y2="${Y(o.target)}" stroke="var(--up)" stroke-width=".8"><title>1R ${f(o.target,3)}</title></line>`;
 s+=`<path d="M${X(i)} ${Y(e)+(o.side>0?9:-9)}l-5 ${o.side>0?6:-6}h10z" fill="var(--up)" transform="translate(0,0)"><title>entry ${hm(i)} ET @ ${f(e,3)}</title></path><circle cx="${X(i)}" cy="${Y(e)}" r="3" fill="var(--up)"><title>entry ${hm(i)} ET @ ${f(e,3)}</title></circle>`;
 (o.exits||[]).forEach(([j,p,k])=>s+=`<rect x="${X(j)-3}" y="${Y(p)-3}" width="6" height="6" fill="${k=='STOP'?'var(--dn)':'var(--amb)'}"><title>${k} ${hm(j)} ET @ ${f(p,3)}</title></rect><text x="${X(j)}" y="${Y(p)-6}" fill="var(--amb)" font-size="8" text-anchor="middle">${k}</text>`)}
 [0,90,180,270,360].forEach(i=>s+=`<text x="${X(i)}" y="${Hh-3}" fill="#857d6a" font-size="8">${hm(i)}</text>`);
 s+='</svg>';
 if(o.px!=null){s=s.replace('</svg>',`<line x1="${X(0)}" x2="${X(389)}" y1="${Y(o.px)}" y2="${Y(o.px)}" stroke="#fff" stroke-width=".7"><title>last ${f(o.px,2)}</title></line><circle cx="${X(o.bars.length-1)}" cy="${Y(o.px)}" r="2.5" fill="#fff"/></svg>`)}
 const st=o.status,cl=st=='INSIDE'||st=='FORMING'?'bn':st=='BROKE LONG'?'bu':'be';
 h+=`<div><span class="bd ${cl}">${st}</span>`+(o.result?`<span class="bd ${o.result=='WIN'?'bu':o.result=='LOSS'?'be':'bn'}">${o.result}</span><span class="bd ${o.R>0?'bu':'be'}" title="R after costs ${o.R}">${sg(o.R)}R</span>`:'')+(o.px!=null?`<span class="bd bn" title="current price">LAST ${f(o.px)}</span>`:'')+`<span class="bd bn" title="OR width">${f(o.H-o.L)} range</span></div>`;
 el.innerHTML=h+s}
orbCard('SPY','var(--yl)');orbCard('QQQ','var(--bl)');orbCard('ES','var(--amb)');orbCard('SPX','var(--pu)');
(()=>{const q=D.eq||{};if(!q.SPY&&!q.QQQ){$('#eqB').innerHTML=ND;return}
 const W=420,H=170,P=[['SPY','var(--yl)'],['QQQ','var(--bl)']];const S={};let mn=0,mx=0,N=0;
 P.forEach(([k])=>{if(!q[k])return;let c=0;S[k]=q[k].r.map(v=>c+=v);mn=Math.min(mn,...S[k]);mx=Math.max(mx,...S[k]);N=Math.max(N,S[k].length)});
 const X=i=>4+(W-40)*i/(N-1),Y=v=>6+(H-22)*(mx-v)/(mx-mn||1);
 let s=`<svg viewBox="0 0 ${W} ${H}"><line x1="4" x2="${W-36}" y1="${Y(0)}" y2="${Y(0)}" stroke="#333"/>`;
 P.forEach(([k,c])=>{if(!S[k])return;const a=S[k],st=q[k].stats,step=Math.max(1,Math.floor(a.length/500));let pts=[];for(let i=0;i<a.length;i+=step)pts.push(X(i).toFixed(1)+','+Y(a[i]).toFixed(1));pts.push(X(a.length-1)+','+Y(a[a.length-1]));
 s+=`<polyline fill="none" stroke="${c}" stroke-width="1.2" points="${pts.join(' ')}"><title>${k}: ${st.tot_r}R total · ${st.n} trades · win ${st.win}% · PF ${st.pf} · max DD ${st.max_dd_r}R · ${st.first}→${st.last}</title></polyline><text x="${W-34}" y="${Y(a[a.length-1])+3}" fill="${c}" font-size="9">${f(a[a.length-1],1)}</text>`});
 const d=q.SPY?q.SPY.d:q.QQQ.d;[...new Set(d.map(x=>x.slice(0,4)))].forEach(y=>{const i=d.findIndex(x=>x.startsWith(y));s+=`<text x="${X(i)}" y="${H-3}" fill="#857d6a" font-size="8">${y}</text>`});
 $('#eqB').innerHTML=s+'</svg>';$('#eqH').innerHTML='<span style="color:var(--yl)">SPY</span> · <span style="color:var(--bl)">QQQ</span> · since 2020'})();
(()=>{const b=D.bot;if(!b){$('#botB').innerHTML=ND;return}const v=b.v,t=x=>x?x.slice(11,19)+' ET':'–';
 $('#botH').textContent=b.day;
 let h=`<div><span class="bd ${v.status=='CLOSED'?'bn':'bu'}">${E(v.status)}</span><span class="bd ${v.side>0?'bu':'be'}">${v.side>0?'LONG':v.side<0?'SHORT':'–'}</span><span class="bd ${v.realized_pnl>0?'bu':'be'}" title="realized ${v.realized_pnl}">${sg(v.realized_pnl)} $</span><span class="bd bn" title="heartbeat ${E(b.hb.ts)}">${E(b.hb.mode||'')} · hb ${E((b.hb.day||''))}</span></div>`;
 h+=`<div class="kv"><span>range</span><b>${f(v.range_low)} – ${f(v.range_high)}</b><span>entry</span><b>${f(v.entry_price)} · ${t(v.entry_time)}</b><span>last tick</span><b>${t(b.last_tick)} · ${b.ticks} ticks</b></div>`;
 const F=b.fills||[];if(F.length){const W=420,H=46,ps=F.map(x=>x.price),lo=Math.min(...ps),hi=Math.max(...ps);let s=`<svg viewBox="0 0 ${W} ${H}">`;F.forEach((x,i)=>{const cx=20+(W-40)*i/Math.max(1,F.length-1),cy=8+(H-20)*(hi-x.price)/((hi-lo)||1);s+=`<circle cx="${cx}" cy="${cy}" r="4" fill="${x.kind=='entry'?'var(--amb)':x.qty<0==(v.side>0)&&x.price>v.entry_price==(v.side>0)?'var(--up)':'var(--dn)'}"><title>${E(x.kind)} ${x.qty} @ ${x.price} · ${t(x.ts)}</title></circle><text x="${cx}" y="${H-2}" fill="#857d6a" font-size="8" text-anchor="middle">${E(x.kind)}</text>`});$('#botB').innerHTML=h+s+'</svg>'}else $('#botB').innerHTML=h})();
