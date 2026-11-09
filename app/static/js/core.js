const ICONS={
  home:'<path d="M3 10.5 12 3l9 7.5V20a1 1 0 0 1-1 1h-5v-6H9v6H4a1 1 0 0 1-1-1z"/>',
  briefcase:'<rect x="3" y="7" width="18" height="13" rx="2"/><path d="M8 7V5a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2M3 13h18"/>',
  file:'<path d="M14 3H6a1 1 0 0 0-1 1v16a1 1 0 0 0 1 1h12a1 1 0 0 0 1-1V8z"/><path d="M14 3v5h5M8 13h8M8 17h6"/>',
  rocket:'<path d="M5 15c-1 1-2 4-2 6 2 0 5-1 6-2M9 15l-3-3c1-4 5-9 12-9 0 7-5 11-9 12z"/><circle cx="15" cy="9" r="1.5"/>',
  check:'<path d="M9 11l3 3 8-8"/><path d="M20 12v7a1 1 0 0 1-1 1H5a1 1 0 0 1-1-1V5a1 1 0 0 1 1-1h11"/>',
  chart:'<path d="M4 20V10M10 20V4M16 20v-7M22 20H2"/>',
  building:'<path d="M3 21h18M5 21V8l7-5 7 5v13M9 21v-6h6v6"/>',
  calendar:'<rect x="3" y="5" width="18" height="16" rx="2"/><path d="M3 10h18M8 3v4M16 3v4"/>',
  news:'<rect x="3" y="4" width="18" height="16" rx="2"/><path d="M7 8h10M7 12h10M7 16h6"/>',
  book:'<path d="M4 4h6a3 3 0 0 1 3 3v13a2 2 0 0 0-2-2H4zM20 4h-6a3 3 0 0 0-3 3v13a2 2 0 0 1 2-2h7z"/>',
  search:'<circle cx="11" cy="11" r="7"/><path d="m20 20-3.5-3.5"/>',
  list:'<path d="M9 6h11M9 12h11M9 18h11M4 6h.01M4 12h.01M4 18h.01"/>',
  clock:'<circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/>',
  settings:'<circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.7 1.7 0 0 0 .3 1.8l.1.1a2 2 0 1 1-2.8 2.8l-.1-.1a1.7 1.7 0 0 0-1.8-.3 1.7 1.7 0 0 0-1 1.5V21a2 2 0 1 1-4 0v-.1a1.7 1.7 0 0 0-1.1-1.5 1.7 1.7 0 0 0-1.8.3l-.1.1a2 2 0 1 1-2.8-2.8l.1-.1a1.7 1.7 0 0 0 .3-1.8 1.7 1.7 0 0 0-1.5-1H3a2 2 0 1 1 0-4h.1a1.7 1.7 0 0 0 1.5-1.1 1.7 1.7 0 0 0-.3-1.8l-.1-.1a2 2 0 1 1 2.8-2.8l.1.1a1.7 1.7 0 0 0 1.8.3H9a1.7 1.7 0 0 0 1-1.5V3a2 2 0 1 1 4 0v.1a1.7 1.7 0 0 0 1 1.5 1.7 1.7 0 0 0 1.8-.3l.1-.1a2 2 0 1 1 2.8 2.8l-.1.1a1.7 1.7 0 0 0-.3 1.8V9a1.7 1.7 0 0 0 1.5 1H21a2 2 0 1 1 0 4h-.1a1.7 1.7 0 0 0-1.5 1z"/>',
};
function icon(name){return `<svg class="icon" viewBox="0 0 24 24" aria-hidden="true">${ICONS[name]||''}</svg>`;}
const NAV=[
  {id:'home',label:'Home',icon:'home',group:'main'},
  {id:'daily-briefing',label:'Daily Briefing',icon:'news',group:'main'},
  {id:'jobs',label:'Jobs',icon:'briefcase',group:'jobs'},
  {id:'resumes',label:'Resumes',icon:'file',group:'jobs'},
  {id:'tracker',label:'Applications',icon:'check',group:'jobs'},
  {id:'startups',label:'Startups',icon:'rocket',group:'jobs'},
  {id:'job-market',label:'Skills Market',icon:'chart',group:'jobs'},
  {id:'government',label:'Government & PSU',icon:'building',group:'intel'},
  {id:'exams',label:'Exams',icon:'calendar',group:'intel'},
  {id:'ai-news',label:'AI News',icon:'news',group:'intel'},
  {id:'papers',label:'Research Papers',icon:'book',group:'intel'},
  {id:'research',label:'Research',icon:'search',group:'intel'},
  {id:'planning',label:'Planning',icon:'list',group:'personal'},
  {id:'history',label:'History',icon:'clock',group:'personal'},
  {id:'sources',label:'Sources & coverage',icon:'chart',group:'personal'},
  {id:'settings',label:'Settings',icon:'settings',group:'personal'},
];
const HIDDEN_VIEWS=['ask-intelligence'];
const THEMES=[
  {id:'minimal-light',label:'Minimal Light',swatch:['#fafafa','#ffffff','#18181b','#2563eb']},
  {id:'minimal-dark',label:'Minimal Dark',swatch:['#111113','#18181b','#e4e4e7','#60a5fa']},
  {id:'soft-neutral',label:'Soft Neutral',swatch:['#f3f1ed','#faf9f6','#292524','#0f766e']},
];
const CATEGORY_META={
  jobs:{label:'Jobs',endpoint:'jobs'},
  government:{label:'Government & PSU',endpoint:'government'},
  exams:{label:'Exams',endpoint:'exams'},
  news:{label:'AI News',endpoint:'news'},
  papers:{label:'Research Papers',endpoint:'papers'},
};
const state={
  data:null,feed:null,sources:null,palette:null,view:'home',activeJob:null,pollTimer:null,toastTimer:null,
  models:[],lastJob:null,tailor:{},note:null,suggestions:null,editResume:null,replaceResume:null,confirmDelete:null,
  expanded:{},
  lastQuery:{jobs:'',government:'',exams:'',news:'',papers:'',employers:'',employerTopic:''},editApp:null,
  filters:{
    jobs:{status:'all',q:'',freshness:'30d',recency:'all',role:'',resume:'',sort:'match',layout:'list',undated:true},
    government:{eligibility:'all',doc:'all',q:'',freshness:'90d'},
    exams:{q:'',freshness:'365d'},
    news:{q:'',freshness:'7d',region:'',topic:''},
    papers:{q:'',freshness:'30d'},
    startups:{kind:'',q:'',signal:'',builtin:false},
    apps:{status:'active'},
  },
};
const $=s=>document.querySelector(s);
const esc=v=>String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
/* Links come from scraped pages: allow only http(s), mailto and in-page targets, never javascript:/data:. */
const safeUrl=v=>{const raw=String(v??'').trim();if(!raw||raw==='#')return '#';
  try{const u=new URL(raw,location.href);return ['http:','https:','mailto:'].includes(u.protocol)?esc(u.href):'#';}catch{return '#';}};
const D=()=>state.data||{};
const counts=()=>(D().counts)||{jobs:0,notices:0,exams:0,news:0,papers:0};
const splitList=v=>String(v||'').split(/[,\n]/).map(x=>x.trim()).filter(Boolean);

async function api(path,options={}){
  const res=await fetch(path,options);
  const data=await res.json().catch(()=>({}));
  if(!res.ok)throw Error(data.error||res.statusText||'Request failed');
  return data;
}
function toast(message,error=false){
  const el=$('#toast');if(!el)return;
  el.textContent=message;el.className='toast show'+(error?' error':'');
  clearTimeout(state.toastTimer);
  state.toastTimer=setTimeout(()=>{el.className='toast';},3600);
}
function fmtDate(v){
  if(!v)return '';
  const d=new Date(v);
  if(isNaN(d.getTime()))return String(v).slice(0,24);
  return d.toLocaleDateString(undefined,{year:'numeric',month:'short',day:'numeric'});
}
function fmtDateTime(v){
  if(!v)return '';
  const d=new Date(v);
  if(isNaN(d.getTime()))return String(v).slice(0,24);
  return d.toLocaleString(undefined,{year:'numeric',month:'short',day:'numeric',hour:'2-digit',minute:'2-digit'});
}
function plain(value){
  return String(value??'')
    .replace(/!\[[^\]]*\]\([^)]*\)/g,' ')
    .replace(/\[([^\]]+)\]\([^)]*\)/g,'$1')
    .replace(/https?:\/\/\S+/g,' ')
    .replace(/(^|\s)#{1,6}\s*/g,'$1')
    .replace(/\*\*|__|`|\\\*/g,'')
    .replace(/\s*\|\s*/g,' · ')
    .replace(/\s+/g,' ').trim();
}
function meta(value){return `<span class="meta">${esc(value)}</span>`;}
function badge(value,label){
  const text=String(value||'unverified');
  return `<span class="badge ${esc(text)}">${esc(label||text.replace(/_/g,' '))}</span>`;
}
function kv(label,value){return value?`<div class="kv"><b>${esc(label)}</b><span>${esc(value)}</span></div>`:'';}
function evidence(item){
  const list=item.evidence||[];
  const first=list.find(x=>x&&(x.text||x.quote));
  if(!first)return '';
  return `<div class="reason">Evidence: “${esc(plain(first.text||first.quote).slice(0,260))}”</div>`;
}
function sourceLinks(sources){
  return (sources||[]).slice(0,12).map(s=>{
    const url=s.url||s.original_url;if(!url)return '';
    return `<a class="meta" href="${safeUrl(url)}" target="_blank" rel="noopener">${esc(s.domain||s.title||'source')}</a>`;
  }).join('');
}
function freshnessOptions(selected){
  return [['today','Today'],['3d','Last 3 days'],['7d','Last 7 days'],['30d','Last 30 days'],
    ['90d','Last 90 days'],['365d','Last year'],['all','All dates']]
    .map(([v,l])=>`<option value="${v}" ${selected===v?'selected':''}>${l}</option>`).join('');
}
function stateOf(kind,id){
  const map=(D().item_states||{})[kind]||{};
  return map[id]||'';
}
function stateButtons(kind,id,current,{applied=true}={}){
  if(kind==='job')return trackButtons(id,current);
  const options=applied
    ?[['saved','Save'],['applied','Applied'],['follow_up','Follow up'],['dismissed','Dismiss']]
    :[['saved','Save'],['follow_up','Follow up'],['dismissed','Dismiss']];
  return options.map(([value,label])=>
    `<button class="link-button ${current===value?'active':''}" data-action="item-state" data-kind="${kind}" data-id="${id}" data-state="${value}">${current===value?'✓ ':''}${label}</button>`
  ).join('');
}

/* ------------------------------------------------------------- job tracking */
function activeJob(){
  if(state.activeJob&&typeof state.activeJob==='object')return state.activeJob;
  const s=D().status;
  return s&&['queued','running'].includes(s.status)?s:null;
}
function stepLog(steps){
  steps=(steps||[]).slice(-14);
  if(!steps.length)return '';
  return `<ul class="step-log">${steps.map(s=>`<li><span>${esc(s.at!=null?s.at+'s':'')}</span>${esc(s.message||s)}</li>`).join('')}</ul>`;
}
function progressBox(){
  const job=activeJob();if(!job)return '';
  return `<div class="progress-box visible">
    <div class="progress-top"><span>${esc(job.message||'Working')}</span><span class="view-note">${job.elapsed_seconds!=null?esc(job.elapsed_seconds)+'s':''} <button class="link-button danger" data-action="cancel-job" data-id="${esc(job.id)}">Cancel</button></span></div>
    <div class="progress-track"><span></span></div>
    ${stepLog(job.steps)}
  </div>`;
}
async function pollJob(id){
  clearTimeout(state.pollTimer);
  const tick=async()=>{
    try{
      const job=await api('/api/jobs/'+encodeURIComponent(id));
      state.activeJob=job;
      render();
      if(['queued','running'].includes(job.status)){
        state.pollTimer=setTimeout(tick,1300);
        return;
      }
      state.lastJob=job;
      state.activeJob=null;
      await refresh();
      render();
      if(job.status==='complete')toast('Request complete');
      else if(job.status==='failed')toast(job.error||'Request failed',true);
      else if(job.status==='cancelled')toast('Request cancelled');
    }catch(err){
      state.pollTimer=setTimeout(tick,2600);
    }
  };
  tick();
}
async function cancelJob(id){
  try{
    await api('/api/jobs/'+encodeURIComponent(id)+'/cancel',{method:'POST',headers:{'Content-Type':'application/json'},body:'{}'});
    toast('Cancellation requested');
  }catch(err){toast(err.message,true);}
}
async function refresh(){
  const [data,feed,sources]=await Promise.all([api('/api/bootstrap'),api('/api/feed').catch(()=>null),
    api('/api/sources').catch(()=>null)]);
  state.data=data;
  if(feed)state.feed=feed;
  if(sources)state.sources=sources.sources||[];
}
async function startJobRequest(path,body,label){
  try{
    const res=await api(path,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body||{})});
    state.activeJob=res.id;
    toast(label||'Started');
    render();
    pollJob(res.id);
  }catch(err){toast(err.message,true);}
}

/* ------------------------------------------------------------------ layout */
function renderNav(){
  const nav=$('#navigation');if(!nav)return;
  let last='';
  nav.innerHTML=NAV.map(n=>{
    const sep=n.group!==last&&last?'<div class="nav-divider"></div>':'';last=n.group;
    const count=navCount(n.id);
    return sep+`<button class="nav-item ${state.view===n.id?'active':''}" data-view="${n.id}">${icon(n.icon)}<span>${n.label}</span>${count?`<span class="nav-count" title="New since your last visit">${count}</span>`:''}</button>`;
  }).join('');
  const active=activeResume();
  const side=$('#side-resume');
  if(side)side.innerHTML=`<span>Active resume</span><b title="${esc(active?active.filename||active.label:'')}">${esc(active?active.label:'None selected')}</b>`;
}
function activeResume(){return (D().resumes||[]).find(r=>r.is_active||r.is_default)||null;}
function navCount(id){
  if(!state.data)return 0;
  if(id==='jobs')return (D().jobs||[]).filter(j=>!SEARCH_KINDS.has(j.source_kind)&&isNew(j)).length;
  if(id==='ai-news')return (D().news||[]).filter(isNew).length;
  if(id==='planning'){const p=(D().today_plan||{}).counts||{};return (p.overdue||0)+(p.today||0);}
  return 0;
}
function heading(eyebrow,title,desc,actions){
  return `<div class="page-heading"><div><div class="eyebrow">${esc(eyebrow)}</div><h1>${esc(title)}</h1><p>${desc||''}</p></div><div class="item-actions">${actions||''}</div></div>`;
}
function statCard(label,value){
  return `<div class="panel stat-card"><div class="stat-value">${esc(value??0)}</div><div class="stat-label">${esc(label)}</div></div>`;
}
function emptyRich(title,text,actions){
  return `<div class="empty-rich"><h3>${esc(title)}</h3><p>${esc(text)}</p><div class="item-actions" style="justify-content:center">${actions||''}</div></div>`;
}
function render(){
  renderNav();
  const meta=NAV.find(n=>n.id===state.view)||{label:state.view==='ask-intelligence'?'Ask':'Home'};
  const crumb=$('#page-crumb');if(crumb)crumb.textContent=state.view==='home'?'':meta.label;
  const line=$('#progress-line');if(line)line.hidden=!activeJob();
  document.querySelectorAll('[data-action="discover"]').forEach(b=>{b.disabled=!!activeJob();});
  const content=$('#page-content');if(!content)return;
  if(!state.data){content.innerHTML='<div class="empty-state"><strong>Loading workspace</strong>Connecting to local services…</div>';return;}
  const view=VIEWS[state.view]||VIEWS.home;
  content.innerHTML=view();
}
function setView(view){
  if(!NAV.some(n=>n.id===view)&&!HIDDEN_VIEWS.includes(view))view='home';
  state.view=view;
  if(location.hash!=='#'+view)history.replaceState(null,'','#'+view);
  openDrawer(false);
  render();
  window.scrollTo({top:0,behavior:'smooth'});
}
