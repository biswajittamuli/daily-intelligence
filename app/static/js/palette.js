/* ---------------------------------------------------------- command palette */
function paletteItems(q){
  const items=[];const t=q.trim();
  items.push({label:'Discover opportunities',hint:'Run every enabled source',run:()=>startJobRequest('/api/discover',{},'Discovering opportunities')});
  if(t){
    items.push({label:`Search roles: “${t}”`,hint:'Targeted discovery with the same engine',run:()=>startJobRequest('/api/discover',{query:t},'Searching '+t)});
    items.push({label:`Filter feed: “${t}”`,hint:'Narrow what is already stored',run:()=>{const f=feedState();f.q=t;f.lens='all';state.expanded.refine=true;setView('home');}});
    items.push({label:`Ask: “${t}”`,hint:'Research with sources',run:()=>{state.askPrefill=t;setView('ask-intelligence');}});
  }
  const lower=t.toLowerCase();
  NAV.forEach(n=>{if(!t||n.label.toLowerCase().includes(lower))items.push({label:'Go to '+n.label,hint:'',run:()=>setView(n.id)});});
  if(t){
    (F().items||[]).filter(i=>`${i.title} ${i.org||''}`.toLowerCase().includes(lower)).slice(0,6).forEach(i=>
      items.push({label:i.title,hint:[i.org,i.state].filter(Boolean).join(' · '),run:()=>{state.expanded['feed-'+i.kind+'-'+i.id]=true;const f=feedState();f.q=t;f.lens='all';state.expanded.refine=true;setView('home');}}));
  }else{
    (F().items||[]).filter(i=>['saved','applied','interview'].includes(i.state)).slice(0,5).forEach(i=>
      items.push({label:i.title,hint:i.state,run:()=>{state.expanded['feed-'+i.kind+'-'+i.id]=true;setView('home');}}));
    (F().deadlines||[]).slice(0,3).forEach(i=>items.push({label:`Deadline: ${i.title}`,hint:i.deadline_days+' days',run:()=>setView('home')}));
  }
  return items.slice(0,14);
}
function openPalette(){
  const p=$('#palette');if(!p)return;
  state.palette={q:'',sel:0};p.hidden=false;renderPalette();
  setTimeout(()=>p.querySelector('input')?.focus(),0);
}
function closePalette(){const p=$('#palette');if(p){p.hidden=true;p.innerHTML='';}state.palette=null;}
function renderPalette(){
  const p=$('#palette');if(!p||!state.palette)return;
  const items=paletteItems(state.palette.q);state.palette.items=items;
  state.palette.sel=Math.min(state.palette.sel,items.length-1);
  const list=items.map((it,k)=>`<li role="option" aria-selected="${k===state.palette.sel}" class="${k===state.palette.sel?'sel':''}" data-pal="${k}"><span>${esc(it.label)}</span><span class="pal-hint">${esc(it.hint||'')}</span></li>`).join('');
  if(!p.querySelector('input')){
    p.innerHTML=`<div class="palette-box"><input class="palette-input" placeholder="Search roles, ask a question, or jump to a section" aria-label="Command" value=""><ul class="palette-list" role="listbox"></ul><div class="palette-foot">↑↓ to move · Enter to run · Esc to close</div></div>`;
  }
  p.querySelector('.palette-list').innerHTML=list;
}
function runPalette(k){const it=(state.palette||{}).items?.[k];closePalette();if(it)Promise.resolve(it.run()).catch(err=>toast(err.message,true));}
document.addEventListener('keydown',e=>{
  const typing=/input|textarea|select/i.test((e.target||{}).tagName||'')&&!(e.target||{}).classList?.contains('palette-input');
  if((e.ctrlKey||e.metaKey)&&e.key.toLowerCase()==='k'){e.preventDefault();state.palette?closePalette():openPalette();return;}
  if(e.key==='/'&&!typing&&!state.palette){e.preventDefault();openPalette();return;}
  if(!state.palette)return;
  if(e.key==='Escape'){e.preventDefault();closePalette();$('#command-trigger')?.focus();}
  else if(e.key==='ArrowDown'){e.preventDefault();state.palette.sel=Math.min(state.palette.sel+1,(state.palette.items||[]).length-1);renderPalette();}
  else if(e.key==='ArrowUp'){e.preventDefault();state.palette.sel=Math.max(state.palette.sel-1,0);renderPalette();}
  else if(e.key==='Enter'){e.preventDefault();runPalette(state.palette.sel);}
});
document.addEventListener('input',e=>{
  if(e.target.classList?.contains('palette-input')&&state.palette){state.palette.q=e.target.value;state.palette.sel=0;renderPalette();}
});
document.addEventListener('click',e=>{
  const li=e.target.closest('[data-pal]');if(li){runPalette(Number(li.dataset.pal));return;}
  if(e.target.id==='palette')closePalette();
  if(e.target.closest('#command-trigger'))openPalette();
});
function openDrawer(open){
  const d=$('#sidebar'),s=$('#scrim'),b=$('#mobile-menu');
  d?.classList.toggle('open',open);if(s)s.hidden=!open;if(b)b.setAttribute('aria-expanded',String(open));
  if(open)d?.querySelector('.nav-item')?.focus();
}
