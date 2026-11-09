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
    return `<a class="meta" href="${esc(url)}" target="_blank" rel="noopener">${esc(s.domain||s.title||'source')}</a>`;
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

/* --------------------------------------------------------------- dashboard */
function centralSearch(){
  const last=(state.lastJob&&['universal','scan_all'].includes(state.lastJob.kind))?state.lastJob:null;
  return `<div class="panel">
    <form data-form="universal" class="search-hero">
      <input class="input" name="request" placeholder="Search anything: “backend developer jobs in Pune”, “GATE 2027 dates”, “AI policy India news”, “papers on RAG evaluation”…" autocomplete="off">
      <button class="primary-button" type="submit">${icon('search')} Search</button>
      <button class="quiet-button" type="button" data-action="scan-all" title="Run every enabled section with your saved preferences">Scan all</button>
    </form>
    <div class="view-note" style="margin-top:6px">One search detects the relevant sections (jobs, government, exams, news, papers or general research), runs the shared search engine for each, and updates those sections.</div>
    ${last&&last.result?universalResult(last.result):''}
  </div>`;
}
function universalResult(result){
  const labels={jobs:'Jobs',government:'Government & PSU',exams:'Exams',news:'AI News',papers:'Research Papers',research:'Research'};
  const views={jobs:'jobs',government:'government',exams:'exams',news:'ai-news',papers:'papers',research:'research'};
  const intent=result.intent||{};
  const rows=Object.entries(result.results||{});
  return `<div class="section-space">
    <div class="view-note">Detected: ${(intent.categories||[]).map(c=>esc(labels[c]||c)).join(', ')||'—'} (${esc(intent.source||'rules')})${intent.query?` · query “${esc(intent.query)}”`:''}</div>
    <div class="table-wrap section-space"><table class="data-table"><thead><tr><th>Section</th><th>Status</th><th class="num">Discovered</th><th class="num">Pages fetched</th><th class="num">Saved</th><th>Notes</th></tr></thead><tbody>
    ${rows.map(([cat,r])=>`<tr><td><a href="#${views[cat]||cat}" data-view="${views[cat]||cat}">${esc(labels[cat]||cat)}</a></td><td>${badge(r.status||'—')}</td>
      <td class="num">${esc(r.raw_results??r.sources_found??'—')}</td><td class="num">${esc(r.pages_fetched??'—')}</td>
      <td class="num">${esc(r.stored??r.records??'—')}${r.strong!=null?` <span class="view-note">(${esc(r.strong)} strong)</span>`:''}</td>
      <td class="view-note">${esc(r.error||r.reason||(r.failures||r.errors||[]).slice(0,2).join('; ')||(r.answer?String(r.answer).slice(0,140)+'…':''))}</td></tr>`).join('')}
    </tbody></table></div></div>`;
}
function viewBriefing(){
  const d=D(),briefing=(d.briefings||[])[0];
  const c=counts();
  const content=briefing?briefing.content||{}:{};
  const tiers=(d.jobs||[]).reduce((m,j)=>{const t=(j.eligibility||{}).tier;if(t)m[t]=(m[t]||0)+1;return m;},{});
  return heading('Workspace','Daily briefing',
    `${esc(d.date||'today')} · everything below is assembled from your local data.`,
    `<button class="quiet-button" data-action="briefing">Generate briefing</button>`) +
    progressBox() + centralSearch() +
    `<div class="grid grid-3 section-space">
      ${statCard('Strong job matches',tiers.strong||0)}
      ${statCard('Possible matches',tiers.possible||0)}
      ${statCard('Recruitment notices',c.notices)}
      ${statCard('Exam events',c.exams)}
      ${statCard('AI news',c.news)}
      ${statCard('Papers',c.papers)}
    </div>
    <div class="section-space">${todayPlanPanel(d.today_plan,{compact:true})}</div>` +
    (briefing?briefingBody(content,briefing):emptyBriefing());
}
function emptyBriefing(){
  return `<div class="panel section-space">${emptyRich('No briefing yet',
    'Generate a briefing to assemble your planning tasks, saved intelligence and deadlines. If no intelligence is stored yet, one bounded live search runs first.',
    `<button class="primary-button" data-action="briefing">Generate briefing</button><button class="quiet-button" data-action="quick-search" data-category="jobs" data-query="">Search jobs</button>`)}</div>`;
}
function briefingBody(content,briefing){
  if(content.actionable)return actionableBriefing(content.actionable)+legacyBriefing(content,briefing,true);
  return legacyBriefing(content,briefing,false);
}
function legacyBriefing(content,briefing,folded){
  if(folded)return `<details class="collapsible section-space" data-details="legacy-brief" ${state.expanded['legacy-brief']?'open':''}><summary>Search sections, priorities and execution details</summary>${legacyBriefing(content,briefing,false)}</details>`;
  const priorities=(content.priorities||[]).slice(0,6);
  const deadlines=(content.deadlines||[]).slice(0,8);
  const sections=(content.sections||[]).map(section=>`<div class="panel section-space">
      <div class="panel-head"><h3 class="panel-title">${esc(section.title)}</h3>${badge(section.status||'complete')}</div>
      ${section.answer?`<div class="section-answer">${esc(section.answer)}</div>`:''}
      ${(section.items||[]).length?`<div class="item-meta">${section.items.slice(0,6).map(item=>{
        const label=item.title||item.post_name||item.exam_name||'item';
        return item.original_url?`<a class="meta" href="${esc(item.original_url)}" target="_blank" rel="noopener">${esc(label).slice(0,80)}</a>`:meta(label);
      }).join('')}</div>`:''}
      ${(section.sources||[]).length?`<div class="item-meta">${sourceLinks(section.sources)}</div>`:''}
    </div>`).join('');
  const changes=content.changes||{};
  const actions=content.recommended_actions||[];
  return `<div class="grid grid-2 section-space">
    <div class="panel">
      <div class="panel-head"><h3 class="panel-title">Today's priorities</h3><span class="panel-kicker">${priorities.length} pending</span></div>
      ${priorities.length?`<div class="task-list">${priorities.map(t=>`<div class="task-row"><span class="task-text">${esc(t.text)}</span>${t.due_date?`<span class="task-due ${t.due_date<D().date?'overdue':''}">${esc(fmtDate(t.due_date))}</span>`:''}</div>`).join('')}</div>`:'<div class="empty-state">No pending planning tasks.</div>'}
    </div>
    <div class="panel">
      <div class="panel-head"><h3 class="panel-title">Deadlines & reminders</h3><span class="panel-kicker">${deadlines.length}</span></div>
      ${deadlines.length?`<div class="timeline">${deadlines.map(item=>`<div class="timeline-row"><div class="timeline-date">${esc(fmtDate(item.date))}</div><div class="timeline-body"><b>${esc(item.title||item.kind)}</b><br>${esc(item.kind||'')}${item.overdue?' · overdue':''}</div></div>`).join('')}</div>`:'<div class="empty-state">No dated deadlines found.</div>'}
    </div>
  </div>
  ${sections||'<div class="panel section-space"><div class="empty-state">No intelligence sections yet.</div></div>'}
  <div class="grid grid-2 section-space">
    <div class="panel">
      <div class="panel-head"><h3 class="panel-title">Changes since previous briefing</h3><span class="panel-kicker">${esc(changes.new_count||0)} new</span></div>
      ${(changes.new_items||[]).length?`<div class="source-list">${changes.new_items.slice(0,10).map(item=>`<div class="source-card"><a class="source-title" href="${esc(item.url)}" target="_blank" rel="noopener">${esc(item.title||'item')}</a></div>`).join('')}</div>`:'<div class="empty-state">No new items compared with the previous briefing.</div>'}
    </div>
    <div class="panel">
      <div class="panel-head"><h3 class="panel-title">Recommended actions</h3><span class="panel-kicker">local</span></div>
      ${actions.length?`<div class="source-list">${actions.map(a=>`<div class="source-card"><div class="source-summary">${esc(a)}</div></div>`).join('')}</div>`:'<div class="empty-state">No actions suggested.</div>'}
    </div>
  </div>
  <div class="banner section-space">Briefing generated ${esc(fmtDateTime(briefing.created_at))}. Execution: ${esc(JSON.stringify((content.execution||{}).stored_items||{}))} · ${esc((content.execution||{}).duration_seconds||'—')}s.</div>`;
}

/* ------------------------------------------------------------------- jobs */
const SEARCH_KINDS=new Set(['search_page','index_page']);
function isNew(item){
  const last=D().last_visit;
  return !!(last&&item.first_seen&&item.first_seen>last);
}
function daysAgo(value){
  if(!value)return null;
  const d=new Date(value);if(isNaN(d.getTime()))return null;
  return Math.floor((Date.now()-d.getTime())/86400000);
}
function ageLabel(value){
  const days=daysAgo(value);
  if(days==null)return '';
  if(days<=0)return 'today';
  if(days===1)return 'yesterday';
  if(days<60)return days+'d ago';
  return Math.round(days/30)+' mo ago';
}
function tierOf(job){return (job.eligibility||{}).tier||(job.match_score==null?'low':job.match_score>=70?'strong':job.match_score>=50?'possible':'low');}
function elig(job){return job.eligibility||{};}
function employerMap(){
  const map={};(D().employers||[]).forEach(e=>{map[e.id]=e;});return map;
}
function isIndianStartup(job,emps){
  const e=job.employer_id!=null?emps[job.employer_id]:null;
  return !!(e&&e.classification==='startup'&&(e.country==='India'||!e.country));
}
function sourceKind(job){
  const via=String(job.discovered_via||'').toLowerCase();
  if(via.includes('career board'))return 'board';
  if(via.includes('career page'))return 'career';
  if(via.includes('index'))return 'index';
  return 'web';
}
function sourceMatch(job,key){
  const types=job.source_types||[];
  if(key==='board'||key==='ats')return types.includes('ats');
  if(key==='career')return types.includes('career');
  if(key==='portal')return types.includes('portal');
  if(key==='index')return String(job.discovered_via||'').includes('index');
  if(key==='web')return types.includes('web');
  return true;
}
function statusGroup(job){
  const s=(job.lifecycle||{}).state||'unverified';
  if(s==='open_verified')return 'verified';
  if(s==='open_page_checked'||s==='open_not_recent')return 'third';
  if(s==='inaccessible')return 'inaccessible';
  if(['closed','expired'].includes(s))return 'closed';
  return 'unverified';
}
function employmentOf(job){
  const t=String(job.employment_type||'');
  if(/intern/i.test(t)||/\bintern(ship)?\b/i.test(job.title||''))return 'Internship';
  if(/contract|freelance|temporary/i.test(t))return 'Contract';
  if(/part/i.test(t))return 'Part-time';
  if(/full/i.test(t))return 'Full-time';
  return t?t.slice(0,30):'Not stated';
}
function cityOf(job){
  const raw=String(job.location||'').trim();
  if(!raw)return 'Not stated';
  if(/\bremote\b/i.test(raw)&&!/hybrid|on-?site/i.test(raw))return 'Remote';
  const aliases={bangalore:'Bengaluru',gurgaon:'Gurugram',bombay:'Mumbai','new delhi':'Delhi',madras:'Chennai',calcutta:'Kolkata',cochin:'Kochi'};
  let first=raw.split(/[,/|]/)[0].replace(/^(on-?site|in-?office|hybrid|based)\s*(in|at|-|:)?\s*/i,'').trim();
  const key=first.toLowerCase();
  if(aliases[key])return aliases[key];
  return first?first.charAt(0).toUpperCase()+first.slice(1):'Not stated';
}
function expBucket(job){
  const min=(elig(job).experience||{}).required_min;
  if(min==null)return 'unknown';
  if(min<=1)return '0-1';if(min<=2)return '1-2';return '3+';
}
function feedJobs({includeIneligible=false}={}){
  const f=state.filters.jobs;
  const q=(f.q||'').toLowerCase();
  const days={'week':7,'month':30,'quarter':90,'all':null}[f.recency||'all'];
  const emps=employerMap();
  return (D().jobs||[]).filter(job=>{
    if(SEARCH_KINDS.has(job.source_kind))return false;
    const tier=tierOf(job);
    if(tier==='excluded')return false;
    if(tier==='ineligible'&&!includeIneligible)return false;
    const life=(job.lifecycle||{}).state;
    if(['expired','closed'].includes(life||job.status)&&!f.showExpired&&f.life!=='closed')return false;
    if(days!=null){const age=daysAgo(job.posted_date);if(age==null?!f.undated:age>days)return false;}
    if(f.role&&job.role_family!==f.role)return false;
    if(f.city&&cityOf(job)!==f.city)return false;
    if(f.exp&&expBucket(job)!==f.exp)return false;
    if(f.employment&&employmentOf(job)!==f.employment)return false;
    if(f.source&&!sourceMatch(job,f.source))return false;
    if(f.life&&statusGroup(job)!==f.life)return false;
    if(f.verifiedRecent&&!(job.last_verified&&daysAgo(job.last_verified)!=null&&daysAgo(job.last_verified)<=7))return false;
    if(f.intern&&!(job.flags||{}).intern)return false;
    if(f.fresher&&!(job.flags||{}).fresher)return false;
    if(f.remote&&!(job.flags||{}).remote)return false;
    if(f.fresh&&((elig(job).freshness||{}).label||'unknown')!==f.fresh)return false;
    if(f.eligibility&&(elig(job).status||'unknown')!==f.eligibility)return false;
    if(f.minMatch&&(job.match_score??0)<Number(f.minMatch))return false;
    if(f.startup&&!isIndianStartup(job,emps))return false;
    if(f.tracked){const s=stateOf('job',job.id);if(!s||s==='dismissed')return false;}
    else if(stateOf('job',job.id)==='dismissed')return false;
    if(q&&!`${job.title} ${job.employer||''} ${job.location||''} ${(job.skills||[]).join(' ')}`.toLowerCase().includes(q))return false;
    return true;
  });
}
function sortJobs(list,key){
  const comp=j=>elig(j).composite??j.match_score??-1;
  const by={
    match:(a,b)=>comp(b)-comp(a)||String(b.posted_date||'').localeCompare(String(a.posted_date||'')),
    fit:(a,b)=>(b.match_score??-1)-(a.match_score??-1)||comp(b)-comp(a),
    posted:(a,b)=>String(b.posted_date||'').localeCompare(String(a.posted_date||''))||comp(b)-comp(a),
    newest:(a,b)=>String(b.first_seen||'').localeCompare(String(a.first_seen||''))||comp(b)-comp(a),
    confidence:(a,b)=>(elig(b).confidence??-1)-(elig(a).confidence??-1)||comp(b)-comp(a),
  };
  return list.slice().sort(by[key]||by.match);
}
function activeResumeBar(){
  const resumes=(D().resumes||[]).filter(r=>r.status==='processed');
  const active=activeResume();
  if(!resumes.length)return `<div class="active-resume"><span class="label">No resume selected — ranking uses your job preferences only.</span><a class="primary-button" href="#resumes" data-view="resumes">Upload a resume</a></div>`;
  const titles=((active||{}).profile||{}).job_titles||[];
  return `<div class="active-resume">
    <span class="label">Ranking for</span>
    <select class="select" data-action="switch-resume" aria-label="Active resume">${resumes.map(r=>`<option value="${r.id}" ${active&&r.id===active.id?'selected':''}>${esc(r.label)}${r.filename?' — '+esc(r.filename):''}</option>`).join('')}</select>
    ${titles.length?`<span class="view-note">Targets: ${titles.map(esc).join(', ')}</span>`:''}
    <a class="link-button" href="#resumes" data-view="resumes" style="margin-left:auto">Manage resumes</a>
  </div>`;
}
function optionList(values,current,allLabel){
  return `<option value="">${esc(allLabel)}</option>`+values.map(([v,l,n])=>`<option value="${esc(v)}" ${current===v?'selected':''}>${esc(l)}${n!=null?` (${n})`:''}</option>`).join('');
}
function counted(list,fn){
  const m={};list.forEach(j=>{const k=fn(j);if(k)m[k]=(m[k]||0)+1;});
  return Object.entries(m).sort((a,b)=>b[1]-a[1]);
}
function jobFilters(base){
  const f=state.filters.jobs;
  const families=counted(base,j=>j.role_family);
  const cities=counted(base,cityOf).slice(0,18);
  const employment=counted(base,employmentOf);
  const active=[f.role,f.city,f.exp,f.employment,f.source,f.life,f.fresh,f.eligibility,f.minMatch,f.startup,f.tracked,f.verifiedRecent,f.intern,f.fresher,f.remote,f.q].filter(Boolean).length;
  return `<details class="collapsible" ${state.expanded.filters?'open':''} data-details="filters"><summary>Filters and sorting${active?` <span class="badge">${active} active</span>`:''}</summary>
    <div class="filter-grid">
      <label class="field"><span>Location</span><select class="select" data-filter="city">${optionList(cities.map(([v,n])=>[v,v,n]),f.city||'','Any location')}</select></label>
      <label class="field"><span>Role family</span><select class="select" data-filter="role">${optionList(families.map(([v,n])=>[v,v,n]),f.role||'','All roles')}</select></label>
      <label class="field"><span>Experience asked</span><select class="select" data-filter="exp">${optionList([['0-1','0–1 years'],['1-2','up to 2 years'],['3+','3+ years'],['unknown','Not stated']],f.exp||'','Any')}</select></label>
      <label class="field"><span>Employment type</span><select class="select" data-filter="employment">${optionList(employment.map(([v,n])=>[v,v,n]),f.employment||'','Any type')}</select></label>
      <label class="field"><span>Source</span><select class="select" data-filter="source">${optionList([['ats','Employer ATS board'],['career','Employer career page'],['portal','Job portal'],['web','Open web search'],['index','Expanded from index page']],f.source||'','All sources')}</select></label>
      <label class="field"><span>Listing status</span><select class="select" data-filter="life">${optionList([['verified','Open · employer verified'],['third','Open · third-party only'],['unverified','Unverified / pending'],['inaccessible','Inaccessible'],['closed','Closed / expired']],f.life||'','Any status')}</select></label>
      <label class="field"><span>Freshness</span><select class="select" data-filter="fresh">${optionList([['new','New (≤3 days)'],['fresh','Fresh (≤14 days)'],['recent','Recent (≤30 days)'],['aging','Aging (31–60 days)'],['stale','Stale (60+ days)'],['unknown','Date not stated']],f.fresh||'','Any freshness')}</select></label>
      <label class="field"><span>Eligibility</span><select class="select" data-filter="eligibility">${optionList([['eligible','Eligible'],['uncertain','Uncertain'],['not_eligible','Not eligible']],f.eligibility||'','Any (not eligible hidden)')}</select></label>
      <label class="field"><span>Profile match ≥</span><select class="select" data-filter="minMatch">${optionList([['40','40'],['50','50'],['60','60'],['70','70'],['80','80']],String(f.minMatch||''),'Any')}</select></label>
      <label class="field"><span>Sort by</span><select class="select" data-filter="sort">${[['match','Overall rank'],['fit','Profile match'],['posted','Posted date'],['newest','First discovered'],['confidence','Evidence confidence']].map(([v,l])=>`<option value="${v}" ${(f.sort||'match')===v?'selected':''}>${l}</option>`).join('')}</select></label>
    </div>
    <div class="filter-row">
      <span class="filter-label">Posted</span>
      ${[['week','7 days'],['month','30 days'],['quarter','90 days'],['all','Any time']].map(([v,l])=>`<button class="chip ${(f.recency||'all')===v?'active':''}" data-action="job-recency" data-value="${v}">${l}</button>`).join('')}
      <label class="chip"><input type="checkbox" data-action="job-undated" ${f.undated?'checked':''}> include undated</label>
      <label class="chip"><input type="checkbox" data-filter-check="startup" ${f.startup?'checked':''}> Indian startups only</label>
      <label class="chip"><input type="checkbox" data-filter-check="tracked" ${f.tracked?'checked':''}> saved / applied only</label>
      <label class="chip"><input type="checkbox" data-filter-check="verifiedRecent" ${f.verifiedRecent?'checked':''}> verified in last 7 days</label>
      <label class="chip"><input type="checkbox" data-filter-check="intern" ${f.intern?'checked':''}> internships</label>
      <label class="chip"><input type="checkbox" data-filter-check="fresher" ${f.fresher?'checked':''}> fresher roles</label>
      <label class="chip"><input type="checkbox" data-filter-check="remote" ${f.remote?'checked':''}> remote</label>
      <label class="chip"><input type="checkbox" data-action="job-expired" ${f.showExpired?'checked':''}> show closed & expired</label>
    </div>
    <div class="filter-row">
      <input class="input" style="width:240px" data-action="job-q" placeholder="Filter by text, skill, employer…" value="${esc(f.q||'')}">
      <span class="filter-gap"></span>
      ${active?'<button class="link-button" data-action="job-clear-filters">Clear filters</button>':''}
    </div>
  </details>`;
}
function viewJobs(){
  const f=state.filters.jobs;
  const showInel=f.eligibility==='not_eligible';
  const all=feedJobs({includeIneligible:showInel});
  const strong=sortJobs(all.filter(j=>tierOf(j)==='strong'),f.sort);
  const possible=sortJobs(all.filter(j=>tierOf(j)==='possible'),f.sort);
  const low=sortJobs(all.filter(j=>tierOf(j)==='low'),f.sort);
  const ineligible=sortJobs(feedJobs({includeIneligible:true}).filter(j=>tierOf(j)==='ineligible'),f.sort);
  const recent=sortJobs(all.filter(j=>isNew(j)||daysAgo(j.first_seen)!=null&&daysAgo(j.first_seen)<=2),'newest').slice(0,15);
  const base=(D().jobs||[]).filter(j=>!SEARCH_KINDS.has(j.source_kind)&&tierOf(j)!=='excluded');
  const excludedCount=(D().jobs||[]).filter(j=>tierOf(j)==='excluded').length;
  const pool=((D().preferences||{}).jobs||{}).pool_size||100;
  const lastRe=D().last_reverify;
  return heading('Jobs','Job shortlist',
    'Broad discovery across job portals, employer job boards and the open web, ranked against your active resume. Each job shows four separate measures — profile match, eligibility, freshness and evidence confidence — and a requirement-by-requirement breakdown.',
    `<button class="quiet-button" data-action="reverify" title="Re-check saved, applied and shortlisted listings">Re-verify listings</button><a class="quiet-button" href="/api/export/jobs.csv?fresh=1">Export CSV</a>`) +
    activeResumeBar() + progressBox() +
    `<div class="toolbar section-space"><form data-form="jobsearch">
      <input class="input" name="query" placeholder="Optional: “entry-level AI engineer Bengaluru”, “fresher Python backend India”, “remote ML internship”, “jobs at funded Indian AI startups”" value="${esc(state.lastQuery.jobs||'')}">
      <select class="select" name="pool_size" title="Candidate pool size">${[50,100,200].map(n=>`<option value="${n}" ${Number(pool)===n?'selected':''}>Pool ${n}</option>`).join('')}</select>
      <button class="primary-button" type="submit">${icon('search')} Discover jobs</button>
    </form>
    <div class="view-note" style="margin-top:6px">Mention a city, “remote”, “fresher/intern”, “startups” or a company name to steer the search. Your resume never leaves this computer; only short role keywords are sent to the search provider.${lastRe?` Last re-verification: ${esc(fmtDateTime(lastRe))}.`:''}</div></div>
    ${coveragePanel()}
    ${jobFilters(base)}
    <div class="legend-row"><span><span class="score strong">80</span> profile match</span><span>${eligBadge('eligible')} eligibility gate</span><span>${freshBadge({label:'fresh',age_days:5})} freshness</span><span>${confBadge(80,'high')} evidence confidence</span><span class="view-note">${excludedCount} stored listings hidden as irrelevant (articles, search pages, non-technical)</span></div>` +
    jobSection('Strong matches','eligible, all mandatory skills met, fresh, well-evidenced',strong,'strong') +
    jobSection('Possible matches','worth a look — see the gaps listed on each card',possible,'possible') +
    jobSection('Weak matches','low profile match',low,'low',{collapsed:true}) +
    jobSection('Not eligible (stretch roles)','fails an explicit requirement such as experience, degree, batch or location — never shown as a strong match',ineligible,'ineligible',{collapsed:!showInel}) +
    jobSection('Recently discovered','new since your last visit or in the last 2 days',recent,'recent',{collapsed:true}) +
    (!strong.length&&!possible.length&&!(showInel&&ineligible.length)?emptyRich('No ranked jobs match these filters','Run “Discover jobs”, or clear filters. Discovery searches several portals and employer job boards, then ranks the pool against your active resume.',`<button class="primary-button" data-action="discover-jobs">Discover jobs</button>`):'');
}
function jobSection(title,note,list,key,{collapsed=false}={}){
  if(!list.length)return '';
  const limit=state.expanded['section-'+key]?list.length:8;
  const body=`<div class="job-list">${list.slice(0,limit).map(jobRow).join('')}</div>
    ${list.length>limit?`<button class="link-button section-space" data-action="expand" data-key="section-${key}">Show all ${list.length}</button>`:''}`;
  if(collapsed){
    const open=state.expanded['open-'+key];
    return `<section class="job-section"><h2><button class="link-button" data-action="expand" data-key="open-${key}">${open?'▾':'▸'} ${esc(title)}</button> <span>${list.length} · ${esc(note)}</span></h2>${open?body:''}</section>`;
  }
  return `<section class="job-section"><h2>${esc(title)} <span>${list.length} · ${esc(note)}</span></h2>${body}</section>`;
}
const SOURCE_TYPE_LABEL={ats:'employer ATS',career:'career page',portal:'job portal',web:'web search'};
const SOURCE_TYPE_HINT={ats:'Read from the employer’s public applicant-tracking board',career:'Found on the employer’s own career page',portal:'Seen on a job portal (search result or portal page)',web:'Found through open web search'};
function tentative(job){const e=elig(job);return e.confidence_label==='low'||e.status==='uncertain'||e.status==='unknown';}
const ELIG_LABEL={eligible:'Eligible',uncertain:'Eligibility uncertain',not_eligible:'Not eligible'};
function eligBadge(status){return `<span class="dim elig-${esc(status||'unknown')}" title="Eligibility gate (separate from the match score)">${esc(ELIG_LABEL[status]||'Eligibility unknown')}</span>`;}
function freshBadge(fr){
  fr=fr||{};const label=fr.label||'unknown';
  const text=label==='unknown'?'date not stated':`${label}${fr.age_days!=null?' · '+(fr.age_days<=0?'today':fr.age_days+'d'):''}`;
  return `<span class="dim fresh-${esc(label)}" title="Freshness from the posting date">${esc(text)}</span>`;
}
function confBadge(value,label){return `<span class="dim conf-${esc(label||'low')}" title="Evidence confidence: how complete and reliable the listing data is — not your suitability">evidence ${esc(label||'—')}${value!=null?' '+esc(value):''}</span>`;}
function lifeBadge(life){
  life=life||{};const s=life.state||'unknown';
  return `<span class="dim life-${esc(s)}" title="${esc(life.detail||'')}">${esc(life.label||s)}</span>`;
}
function jobRow(job){
  const tier=tierOf(job);
  const current=stateOf('job',job.id);
  const e=elig(job);
  const fr=e.freshness||{};
  const others=(job.resume_scores||[]).filter(s=>!s.active&&s.score!=null);
  const better=others.find(s=>s.score>(job.match_score||0)+8);
  const open=state.expanded['job-'+job.id];
  const sources=(job.sources||[]).length;
  const matched=(e.matched||[]),partial=(e.partial||[]),missM=(e.missing_mandatory||[]),missP=(e.missing_preferred||[]);
  const oldCls=['aging','stale'].includes(fr.label)?' is-old':'';
  const closed=['closed','expired'].includes((job.lifecycle||{}).state)?' is-closed':'';
  return `<div class="job-row${oldCls}${closed}">
    <span class="score ${tier}${tentative(job)?' tentative':''}" title="${tentative(job)?'Profile match only — evidence is incomplete or eligibility is uncertain, so this is not a recommendation':'Profile match against your active resume (eligibility is shown separately)'}">${job.match_score??'—'}</span>
    <div class="job-main">
      <div class="item-title"><a href="${esc(job.original_url||'#')}" target="_blank" rel="noopener">${esc(job.title||'Untitled role')}</a> ${isNew(job)?'<span class="badge new">new</span>':''}</div>
      <div class="item-meta">${meta(job.employer||'Employer not stated')}${meta(job.location||'Location not stated')}${job.posted_date?meta('posted '+fmtDate(job.posted_date)):meta('posting date not stated')}${job.last_verified?meta(((job.lifecycle||{}).state==='open_verified'?'verified ':'checked ')+ageLabel(job.last_verified)):''}${meta(job.discovered_via||job.source_platform||'')}${sources>1?meta(sources+' sources'):''}</div>
      <div class="dims">${eligBadge(e.status)}${freshBadge(fr)}${confBadge(e.confidence,e.confidence_label)}${lifeBadge(job.lifecycle)}${(job.source_types||[]).map(t=>`<span class="dim src-type" title="${esc(SOURCE_TYPE_HINT[t]||'')}">${esc(SOURCE_TYPE_LABEL[t]||t)}</span>`).join('')}${current&&current!=='dismissed'?`<span class="dim app-state">${esc(current)}</span>`:''}</div>
      ${(e.gates||[]).length?`<div class="warning-line bad">✕ ${e.gates.map(esc).join(' · ')}</div>`:''}
      ${matched.length||partial.length||missM.length||missP.length?`<div class="item-meta">${matched.slice(0,6).map(s=>`<span class="tag have" title="On your resume">${esc(s)}</span>`).join('')}${partial.slice(0,3).map(s=>`<span class="tag part" title="Only inferred from your projects">${esc(s)} ½</span>`).join('')}${missM.slice(0,4).map(s=>`<span class="tag miss" title="Required, not on your resume">${esc(s)}</span>`).join('')}${missP.slice(0,3).map(s=>`<span class="tag pref" title="Preferred, not on your resume">${esc(s)}</span>`).join('')}</div>`:''}
      ${(e.warnings||[]).length?`<div class="warning-line">⚠ ${e.warnings.map(esc).join(' ')}</div>`:''}
      ${better?`<div class="view-note">Your “${esc(better.label)}” resume scores ${esc(better.score)} for this role.</div>`:''}
      ${open?jobDetail(job):''}
    </div>
    <div class="item-actions">
      <button class="link-button" data-action="expand" data-key="job-${job.id}">${open?'Less':'Why'}</button>
      ${trackButtons(job.id,current)}
      ${open&&activeResume()?`<button class="link-button" data-action="tailor" data-id="${job.id}">Tailor</button>`:''}
    </div>
  </div>`;
}
const REQ_ICON={satisfied:'✓',not_satisfied:'✕',partial:'½',unknown:'?',not_applicable:'–'};
const REQ_TEXT={satisfied:'Satisfied',not_satisfied:'Not satisfied',partial:'Partially',unknown:'Unknown',not_applicable:'N/A'};
const COMPONENT_LABEL={role:'Role relevance',mandatory_skills:'Mandatory skills',preferred_skills:'Preferred skills',experience:'Experience',education:'Education',location_employment:'Location & employment',freshness:'Freshness'};
function jobDetail(job){
  const e=elig(job);
  const reqs=e.requirements||[];
  const order={not_satisfied:0,partial:1,unknown:2,satisfied:3,not_applicable:4};
  const sorted=reqs.slice().sort((a,b)=>(a.priority==='mandatory'?0:1)-(b.priority==='mandatory'?0:1)||(order[a.status]??5)-(order[b.status]??5));
  const unknown=reqs.filter(r=>r.status==='unknown').map(r=>r.name+(r.detail?` (${r.detail})`:''));
  const ex=e.experience||{};
  const life=job.lifecycle||{};
  const history=(job.verify_history||[]).slice(-4).reverse();
  return `<div class="job-detail">
    <div class="reason"><b>Why it is ranked here:</b> ${esc(e.why||job.match_reason||'No explanation stored; re-score to compute.')}</div>
    <div class="grid grid-2 section-space">
      <div>
        <div class="section-title">Requirements (${reqs.length})</div>
        ${reqs.length?`<div class="table-wrap"><table class="data-table req-table"><thead><tr><th></th><th>Requirement</th><th>Priority</th><th>Status</th></tr></thead><tbody>
        ${sorted.map(r=>`<tr class="req-${esc(r.status)}"><td class="req-icon" aria-label="${esc(REQ_TEXT[r.status]||r.status)}">${REQ_ICON[r.status]||'?'}</td>
          <td><b>${esc(r.name)}</b> <span class="view-note">${esc(r.type)}</span>${r.detail?`<div class="view-note">${esc(r.detail)}</div>`:''}${r.evidence?`<div class="req-evidence" title="Text from the listing">“${esc(String(r.evidence).replace(/[*#]/g,'').slice(0,160))}”</div>`:''}</td>
          <td>${esc(r.priority||'not stated')}</td><td>${esc(REQ_TEXT[r.status]||r.status)}</td></tr>`).join('')}
        </tbody></table></div>`:'<div class="empty-state">No requirements could be read from this listing.</div>'}
      </div>
      <div>
        <div class="section-title">Profile match breakdown</div>
        <div class="table-wrap"><table class="data-table"><thead><tr><th>Component</th><th class="num">Weight</th><th class="num">Score</th></tr></thead><tbody>
        ${(e.breakdown||[]).map(b=>`<tr><td>${esc(COMPONENT_LABEL[b.component]||b.component)}</td><td class="num">${esc(b.weight)}%</td><td class="num">${b.value==null?'<span class="view-note">no data — excluded</span>':esc(b.value)}</td></tr>`).join('')}
        </tbody></table></div>
        <div class="kv-grid section-space">
          ${kv('Profile match',job.match_score!=null?job.match_score+' / 100':'')}
          ${kv('Overall rank score',e.composite!=null?String(e.composite):'')}
          ${kv('Eligibility',ELIG_LABEL[e.status]||e.status||'')}
          ${kv('Experience',ex.required_min!=null?`needs ${ex.required_min}${ex.required_max?'–'+ex.required_max:'+'} yrs · you ${ex.candidate} · ${ex.difference>=0?'meets it':'short by '+Math.abs(ex.difference)}`:'not stated in the listing')}
          ${kv('Mandatory mismatches',(e.gates||[]).join('; ')||((e.missing_mandatory||[]).length?'skills: '+e.missing_mandatory.join(', '):'none'))}
          ${kv('Missing preferred skills',(e.missing_preferred||[]).join(', '))}
          ${kv('Unknown requirements',unknown.join(', '))}
          ${kv('Evidence confidence',e.confidence!=null?`${e.confidence} (${e.confidence_label})${(e.confidence_notes||[]).length?' — '+e.confidence_notes.join('; '):''}`:'')}
        </div>
      </div>
    </div>
    <div class="section-title section-space">Listing status</div>
    <div class="kv-grid">
      ${kv('Status',`${life.label||job.status||'unknown'}${life.detail?' — '+life.detail:''}`)}
      ${kv('Posted',job.posted_date?fmtDate(job.posted_date):'not stated')}
      ${kv('Updated',job.updated_date?fmtDate(job.updated_date):'')}
      ${kv('First discovered',fmtDateTime(job.first_seen))}
      ${kv('Last verified',job.last_verified?fmtDateTime(job.last_verified):'never')}
      ${kv('Deadline',job.deadline?fmtDate(job.deadline):'')}
      ${kv('Requisition ID',job.requisition_id||'')}
      ${kv('Reposted from',job.repost_of?'listing #'+job.repost_of:'')}
    </div>
    ${history.length?`<div class="view-note section-space">Verification history: ${history.map(h=>`${esc(fmtDate(h.at))} ${esc(h.outcome)} (${esc(h.status)})`).join(' · ')}</div>`:''}
    ${sourceDetails(job)}
    <div class="item-actions section-space">
      <a class="link-button" href="${esc(job.original_url||'#')}" target="_blank" rel="noopener">Original listing</a>
      ${job.application_url?`<a class="link-button primary" href="${esc(job.application_url)}" target="_blank" rel="noopener">Official application page</a>`:''}
      ${job.employer_url?`<a class="link-button" href="${esc(job.employer_url)}" target="_blank" rel="noopener">Employer site</a>`:''}
      ${(job.sources||[]).filter(s=>s.url!==job.original_url).map(s=>`<a class="link-button" href="${esc(s.url)}" target="_blank" rel="noopener">Also on ${esc(s.via||s.platform||'source')}</a>`).join('')}
      <button class="link-button" data-action="reverify-one" data-id="${job.id}">Re-verify now</button>
    </div>
    ${state.tailor[job.id]?tailorBox(state.tailor[job.id]):''}
  </div>`;
}
function sourceDetails(job){
  const sources=job.sources||[];
  const conflicts=job.conflicts||[];
  return `<div class="section-title section-space">Where this listing came from</div>
    <div class="kv-grid">
      ${kv('Extraction method',job.extraction_method||'not recorded (older listing)')}
      ${kv('Evidence confidence',job.evidence_confidence!=null?String(job.evidence_confidence):'')}
      ${kv('Verification source',job.verification_source||'not verified')}
      ${kv('Employer ATS',job.ats_ref||'')}
      ${kv('Retrieved',job.retrieved_at?fmtDateTime(job.retrieved_at):'')}
      ${kv('Salary currency',job.salary_currency||'')}
      ${kv('Education',job.education||'')}
    </div>
    ${sources.length?`<div class="table-wrap section-space"><table class="data-table"><thead><tr><th>Source</th><th>Found via</th><th>Method</th><th>Access policy</th><th>Seen</th></tr></thead><tbody>
      ${sources.map(s=>`<tr><td><a href="${esc(s.url)}" target="_blank" rel="noopener">${esc(s.portal||s.platform||hostOf(s.url))}</a>${s.url===job.original_url?' <span class="view-note">(canonical)</span>':''}</td><td>${esc(s.via||s.kind||'')}</td><td class="view-note">${esc(s.method||'')}</td><td class="view-note">${esc(s.policy==='search_results_only'?'search results only — not fetched':s.policy==='provider_fetch'?'fetched only via search provider':'')}</td><td class="view-note">${esc(s.retrieved_at?fmtDate(s.retrieved_at):'')}</td></tr>`).join('')}
    </tbody></table></div>`:''}
    ${conflicts.length?`<div class="banner warn section-space"><b>Sources disagree:</b> ${conflicts.map(c=>`${esc(c.field)}: stored “${esc(c.stored)}” vs “${esc(c.value)}” (${esc(hostOf(c.source))})`).join('; ')}</div>`:''}`;
}
function hostOf(url){try{return new URL(url).hostname.replace(/^www\./,'');}catch(e){return String(url||'');}}
function coverageStages(s){
  // Five honest stages per source: targeted → returned results → page fetched → listing extracted → verified on the employer's system.
  const rows={};
  const get=name=>rows[name]=rows[name]||{name,methods:new Set(),targeted:0,returned:0,fetched:0,extracted:0,stored:0,verified:0,status:new Set()};
  (s.coverage||[]).forEach(c=>{
    const r=get(c.platform);r.methods.add(c.method);
    r.targeted+=c.queries||(/API|board|discovery/i.test(c.method)?1:0);
    r.returned+=(c.results||0);r.fetched+=(c.fetched||0);r.extracted+=(c.listings||0);
    if(c.status)r.status.add(c.results===0&&!c.listings&&/^ok/.test(c.status)?'no results':c.status);
  });
  Object.entries(s.funnel||{}).forEach(([name,f])=>{
    const r=get(name);r.extracted=Math.max(r.extracted,f.extracted||0);r.stored+=f.stored||0;r.verified+=f.verified||0;
  });
  return Object.values(rows).sort((a,b)=>b.stored-a.stored||b.returned-a.returned||a.name.localeCompare(b.name));
}
const CATEGORY_LABEL={government:'Government',news:'News',feed:'Public feeds',renderer:'Renderers',search_engine:'Search',ats_board:'ATS board',career_page:'Career page',job_portal:'Job portal',employer_discovery:'Employer discovery',browser_render:'Browser',third_party_extractor:'Extractor'};
function stateClass(state){
  if(['extraction_successful','fetch_successful','search_successful','partially_successful'].includes(state))return 'status-ok';
  if(['no_results','targeted','not_targeted','skipped_by_access_policy'].includes(state))return 'status-warn';
  return 'status-bad';
}
function acquisitionPanel(s){
  const a=s.acquisition||{};
  const f=state.filters.jobs;
  const funnel=a.funnel_stages||[];
  const get=k=>(funnel.find(x=>x.stage===k)||{}).count||0;
  const rows=(a.sources||[]).filter(r=>!f.covCat||r.category===f.covCat);
  const limit=state.expanded.covall?rows.length:40;
  const cats=Array.from(new Set((a.sources||[]).map(r=>r.category)));
  const res=s.resources||{};const http=res.http||{};const br=res.browser||{};const t=res.timings||{};
  const reasons=Object.entries(a.exclusion_reasons||{});
  const ex=state.exclusions;
  const cell=v=>v?`<td class="num">${esc(v)}</td>`:'<td class="num view-note">–</td>';
  return `<details class="collapsible" ${state.expanded.coverage?'open':''} data-details="coverage"><summary>Source coverage — ${esc(a.sources_successful??0)} of ${esc(a.sources_targeted??0)} sources returned data · ${esc(get('search_results'))} search results + ${esc(get('ats_openings'))} board openings + ${esc(get('career_page_listings'))} career-page listings → ${esc(s.unique_candidates)} unique → ${esc(get('relevant_jobs'))} relevant → ${esc(s.stored)} stored <span class="view-note">· ${esc(fmtDateTime(s.created_at))} · ${esc(s.duration_seconds)}s · resume ${esc(s.resume||'none')}</span></summary>
    <div class="view-note">A source counts as reached only when it returned data. Job portals whose terms forbid automated access (LinkedIn, Indeed, Glassdoor, Naukri, Wellfound) are used only through search-engine results and are never fetched. Coverage is never complete: this shows exactly what was attempted and what came back.</div>
    <div class="funnel section-space">${funnel.map((x,i)=>`<div class="funnel-step"><div class="funnel-count">${esc(x.count)}</div><div class="funnel-label">${esc(x.label)}</div></div>${i<funnel.length-1?'<span class="funnel-arrow">→</span>':''}`).join('')}</div>
    <div class="filter-row section-space"><label class="field"><span>Source type</span><select class="select" data-filter="covCat">${optionList(cats.map(c=>[c,CATEGORY_LABEL[c]||c,(a.sources||[]).filter(r=>r.category===c).length]),f.covCat||'','All source types')}</select></label>
      <span class="view-note">Paths searched: ${esc((s.search_paths||[]).join(', '))} · ${esc(s.search_calls)} search calls · ${esc(s.boards_discovered??0)} new boards found</span></div>
    <div class="table-wrap section-space"><table class="data-table coverage-table"><thead><tr><th>Source</th><th>Type</th><th>Method</th><th>State</th><th class="num">Results</th><th class="num">Listings</th><th class="num">Unique</th><th class="num">Dup.</th><th class="num">Rejected</th><th class="num">Stored</th><th class="num">Verified</th><th class="num">ms</th><th>Detail</th></tr></thead><tbody>
      ${rows.slice(0,limit).map(r=>`<tr><td>${esc(r.name)}</td><td class="view-note">${esc(CATEGORY_LABEL[r.category]||r.category)}</td><td class="view-note">${esc(r.method)}</td><td class="${stateClass(r.state)}">${esc(r.state_label)}${r.http_status?' ('+esc(r.http_status)+')':''}</td>${cell(r.search_results)}${cell(r.listings)}${cell(r.unique)}${cell(r.duplicates)}${cell(r.rejected)}${cell(r.stored)}${cell(r.verified)}${cell(r.duration_ms)}<td class="view-note">${esc(r.failure_reason||r.detail||'')}</td></tr>`).join('')}
    </tbody></table></div>
    ${rows.length>limit?`<button class="link-button" data-action="expand" data-key="covall">Show all ${rows.length} sources</button>`:''}
    <div class="grid grid-2 section-space">
      <div>
        <div class="section-title">Inaccessible or failed (${esc((a.sources_inaccessible||[]).length)})</div>
        ${(a.sources_inaccessible||[]).length?`<div class="table-wrap"><table class="data-table"><tbody>${a.sources_inaccessible.slice(0,30).map(r=>`<tr><td>${esc(r.name)}</td><td class="status-bad">${esc(r.state)}</td><td class="view-note">${esc(r.reason||'')}</td></tr>`).join('')}</tbody></table></div>`:'<div class="view-note">None in this run.</div>'}
        <div class="section-title section-space">Resources</div>
        <div class="kv-grid">${kv('Time by stage',Object.entries(t).map(([k,v])=>`${k.replace(/_s$/,'').replace(/_/g,' ')} ${v}s`).join(' · '))}${kv('App memory (peak)',res.peak_app_rss_mb!=null?res.peak_app_rss_mb+' MB':'')}${kv('Direct HTTP',http.requests!=null?`${http.requests} requests · ${http.cache_hits} cache hits · ${http.revalidated} revalidated · ${http.robots_blocked} robots-blocked · ${http.challenges} bot challenges`:'not used')}${kv('Browser',br.launched?`${br.engine} · ${br.renders} renders · peak ${br.peak_concurrent} page(s) · ${br.peak_browser_rss_mb??'?'} MB · closed ${br.closed_cleanly?'cleanly':'with errors'}`:(br.unavailable_reason||'not needed'))}</div>
      </div>
      <div>
        <div class="section-title">Why results were not stored (${esc(reasons.reduce((n,[,c])=>n+c,0))})</div>
        <div class="view-note">Click a reason to inspect the individual results.</div>
        <div class="reason-list">${reasons.map(([name,count])=>`<button class="chip ${ex&&ex.reason===name?'active':''}" data-action="load-exclusions" data-reason="${esc(name)}" data-session="${esc(s.session_id||'')}">${esc(name)} <span class="chip-count">${esc(count)}</span></button>`).join('')}</div>
        ${ex?`<div class="table-wrap section-space exclusion-scroll"><table class="data-table"><thead><tr><th>Result</th><th>Source</th><th>Detail</th></tr></thead><tbody>${ex.loading?'<tr><td colspan="3">Loading…</td></tr>':(ex.items||[]).map(e=>`<tr><td>${e.url?`<a href="${esc(e.url)}" target="_blank" rel="noopener">${esc(e.title||e.url)}</a>`:esc(e.title||'')}${e.employer?`<div class="view-note">${esc(e.employer)}</div>`:''}</td><td class="view-note">${esc(e.source||'')}</td><td class="view-note">${esc(e.detail||e.stage||'')}</td></tr>`).join('')}</tbody></table></div><div class="view-note">${esc(ex.total??0)} result(s) for “${esc(ex.reason)}”${(ex.items||[]).length<(ex.total||0)?` — showing first ${esc(ex.items.length)}`:''}.</div>`:''}
      </div>
    </div></details>`;
}
function coveragePanel(){
  const s=D().job_search;
  if(!s)return '';
  if(s.acquisition)return acquisitionPanel(s);
  const stages=coverageStages(s);
  const excluded=Object.entries(s.excluded||{}).sort((a,b)=>b[1]-a[1]);
  const inel=Object.entries(s.ineligible_reasons||{}).sort((a,b)=>b[1]-a[1]);
  const reached=stages.filter(r=>r.returned||r.extracted).length;
  const blocked=stages.filter(r=>[...r.status].some(x=>/fail|block|not retriev|error|403|429|404/i.test(x)));
  const cell=(v,ok)=>v?`<td class="num ${ok?'status-ok':''}">${esc(v)}</td>`:'<td class="num view-note">–</td>';
  const ed=s.employer_discovery;
  return `<details class="collapsible" ${state.expanded.coverage?'open':''} data-details="coverage"><summary>Source coverage — last discovery: ${esc(s.raw_results)} results from ${esc(reached)} of ${esc(stages.length)} targeted sources → ${esc(s.unique_candidates)} unique → ${esc(s.stored)} stored (${esc(s.strong)} strong, ${esc(s.possible)} possible) <span class="view-note">· ${esc(fmtDateTime(s.created_at))} · ${esc(s.duration_seconds)}s · resume ${esc(s.resume||'none')}</span></summary>
    <div class="view-note">A source counts as <b>searched</b> only when it returned results. “Targeted” means it was included in a query; “verified” means the listing was read from the employer’s own job system.</div>
    <div class="table-wrap section-space"><table class="data-table coverage-table"><thead><tr><th>Source</th><th>Method</th><th class="num">Targeted</th><th class="num">Returned</th><th class="num">Fetched</th><th class="num">Extracted</th><th class="num">Stored</th><th class="num">Verified</th><th>Status</th></tr></thead><tbody>
      ${stages.map(r=>`<tr><td>${esc(r.name)}</td><td class="view-note">${esc([...r.methods].join(', '))}</td>${cell(r.targeted)}${cell(r.returned,1)}${cell(r.fetched,1)}${cell(r.extracted,1)}${cell(r.stored,1)}${cell(r.verified,1)}
        <td class="${[...r.status].some(x=>/^ok/.test(x))&&(r.returned||r.extracted)?'status-ok':[...r.status].some(x=>/fail|block|not retriev|error/i.test(x))?'status-bad':'status-warn'}">${esc([...r.status].join('; ')||'—')}</td></tr>`).join('')}
    </tbody></table></div>
    <div class="grid grid-2 section-space">
      <div>
        <div class="section-title">How the pool was narrowed</div>
        <div class="kv-grid">${kv('Search request',s.request||'(resume and preferences)')}${kv('Role variations searched',(s.targets||[]).join(', '))}${kv('Raw results',s.raw_results)}${kv('Web search results',s.mcp_results)}${kv('Expanded from index pages',s.harvested)}${kv('Employer job-board openings',s.ats_openings)}${kv('Duplicates merged',s.duplicates)}${kv('Unique candidates',s.unique_candidates)}${kv('Excluded as irrelevant',s.excluded_total)}${kv('Ranked as relevant',s.ranked)}${kv('Not eligible (kept as stretch)',`${s.ineligible??0} (${s.ineligible_stored??0} stored)`)}${kv('Stored (pool size)',`${s.stored} / ${s.pool_size}`)}${kv('Search calls · pages fetched',`${s.search_calls} · ${s.pages_fetched}`)}${kv('Inaccessible sources',blocked.map(r=>r.name).join(', ')||'none reported')}</div>
        ${ed?`<div class="banner section-space">Employer discovery ran in this search: ${esc(ed.companies_found??0)} companies, ${esc(ed.with_website??0)} websites, ${esc(ed.with_career_page??0)} career pages, ${esc(ed.ats_readable??0)} public job boards. <a href="#startups" data-view="startups">Open Startups</a></div>`:''}
        ${(s.failures||[]).length?`<div class="banner warn section-space">${s.failures.map(esc).join('<br>')}</div>`:''}
      </div>
      <div>
        <div class="section-title">Excluded (${esc(s.excluded_total)})</div>
        ${barList(excluded.map(([name,count])=>({name,count})),{unit:'listing',series:2,limit:8})}
        ${inel.length?`<div class="section-title section-space">Not eligible, by reason</div>${barList(inel.map(([name,count])=>({name,count})),{unit:'listing',series:2,limit:6})}`:''}
      </div>
    </div></details>`;
}
function tailorBox(t){
  if(t.loading)return '<div class="reason">Preparing tailoring hints with the local model…</div>';
  return `<div class="reason"><b>Tailoring “${esc(t.resume)}”</b> (skill fit ${esc(t.fit??'—')}%)
    ${(t.missing||[]).length?`<div>Not evidenced: ${t.missing.map(esc).join(', ')} — add only if you genuinely have them.</div>`:''}
    ${(t.matched||[]).length?`<div>Emphasise: ${t.matched.map(esc).join(', ')}</div>`:''}
    ${(t.bullets||[]).length?`<ul>${t.bullets.map(b=>`<li>${esc(b)}</li>`).join('')}</ul>`:''}
    <div class="view-note">${t.source==='local_model'?'Suggestions from your local model; review before use.':'Deterministic hints (local model unavailable).'}</div></div>`;
}
const TRACK_STATES=[['saved','Save'],['applied','Applied'],['interview','Interview'],['offer','Offer'],['rejected','Rejected'],['dismissed','Hide']];
function trackButtons(id,current){
  const visible=current&&current!=='saved'&&current!=='dismissed'
    ?TRACK_STATES.filter(([v])=>['applied','interview','offer','rejected'].includes(v))
    :TRACK_STATES.filter(([v])=>['saved','applied','dismissed'].includes(v));
  return visible.map(([value,label])=>
    `<button class="link-button ${current===value?'active':''}" data-action="item-state" data-kind="job" data-id="${id}" data-state="${current===value?'none':value}">${current===value?'✓ ':''}${label}</button>`).join('');
}

/* ------------------------------------------------------------- applications */
const APP_LABEL={interested:'Interested',saved:'Saved',preparing:'Preparing',applied:'Applied',assessment:'Assessment',interview:'Interview',offer:'Offer',rejected:'Rejected',withdrawn:'Withdrawn',closed:'Closed'};
const APP_ACTIVE=['interested','saved','preparing','applied','assessment','interview','offer'];
function appStatuses(){return D().application_statuses||Object.keys(APP_LABEL);}
function upcoming(item){
  const today=D().date||new Date().toISOString().slice(0,10);
  const out=[];
  if(item.follow_up_date&&!['rejected','withdrawn','closed','offer'].includes(item.status))out.push({at:item.follow_up_date,what:'Follow up',overdue:item.follow_up_date<today});
  (item.interview_dates||[]).forEach(i=>{if(String(i.at).slice(0,10)>=today)out.push({at:i.at,what:'Interview'+(i.note?' · '+i.note:'')});});
  return out.sort((a,b)=>String(a.at).localeCompare(String(b.at)));
}
function viewTracker(){
  const items=D().applications||[];
  const f=state.filters.apps=state.filters.apps||{status:'active'};
  const shown=items.filter(i=>f.status==='all'?true:f.status==='active'?APP_ACTIVE.includes(i.status):i.status===f.status);
  const counts=items.reduce((m,i)=>{m[i.status]=(m[i.status]||0)+1;return m;},{});
  const reminders=items.flatMap(i=>upcoming(i).map(u=>({...u,item:i}))).sort((a,b)=>String(a.at).localeCompare(String(b.at))).slice(0,8);
  const editing=state.editApp;
  return heading('Jobs','Applications',
    'A local record of the applications you make yourself — nothing is ever submitted automatically. Follow-up dates and interviews become Planning tasks and appear in the Daily Briefing.',
    `<button class="primary-button" data-action="app-new">Add application</button><a class="quiet-button" href="/api/export/jobs.csv">Export jobs (CSV)</a>`) +
    `<div class="filter-row"><span class="filter-label">Status</span>
      ${[['active','Active'],['all','All'],...appStatuses().map(s=>[s,APP_LABEL[s]||s])].map(([v,l])=>`<button class="chip ${f.status===v?'active':''}" data-action="app-filter" data-value="${v}">${esc(l)}${v==='all'?` <span class="chip-count">${items.length}</span>`:counts[v]?` <span class="chip-count">${counts[v]}</span>`:''}</button>`).join('')}
    </div>
    ${reminders.length?`<div class="panel section-space"><div class="panel-head"><h3 class="panel-title">Upcoming reminders</h3><span class="panel-kicker">${reminders.length}</span></div>
      <div class="timeline">${reminders.map(r=>`<div class="timeline-row"><div class="timeline-date ${r.overdue?'overdue':''}">${esc(String(r.at).length>10?fmtDateTime(r.at):fmtDate(r.at))}</div><div class="timeline-body"><b>${esc(r.what)}</b> — ${esc(r.item.role)}${r.item.company?' at '+esc(r.item.company):''}${r.overdue?' · overdue':''}</div></div>`).join('')}</div></div>`:''}
    ${editing==='new'?`<div class="panel section-space"><div class="panel-head"><h3 class="panel-title">New application</h3></div>${appForm({status:'applied'})}</div>`:''}
    <div class="section-space">${shown.length?`<div class="app-list">${shown.map(appRow).join('')}</div>`
      :emptyRich(items.length?'No applications with this status':'No applications tracked yet','Use “Save” or “Applied” on any job card, or add one you applied to elsewhere.',`<button class="primary-button" data-action="app-new">Add application</button><button class="quiet-button" data-view="jobs">Browse jobs</button>`)}</div>`;
}
function appRow(item){
  const open=state.editApp===item.id;
  const life=item.job_status;
  const e=item.eligibility||{};
  const next=upcoming(item)[0];
  const resume=(D().resumes||[]).find(r=>r.id===item.resume_id);
  return `<div class="app-row status-${esc(item.status)}">
    <div class="app-main">
      <div class="item-title">${item.job_url?`<a href="${esc(item.job_url)}" target="_blank" rel="noopener">${esc(item.role)}</a>`:esc(item.role)}</div>
      <div class="item-meta">${meta(item.company||'Company not recorded')}${item.location?meta(item.location):''}${item.applied_at?meta('applied '+fmtDate(item.applied_at)+' ('+ageLabel(item.applied_at)+')'):''}${resume?meta('resume: '+resume.label):''}${item.match_score!=null?meta('match '+item.match_score):''}${e.status?meta(ELIG_LABEL[e.status]||e.status):''}${life&&['closed','expired'].includes(life)?`<span class="dim life-closed">listing ${esc(life)}</span>`:''}</div>
      ${item.next_action||next?`<div class="view-note">${item.next_action?'Next: '+esc(item.next_action):''}${item.next_action&&next?' · ':''}${next?`${esc(next.what)} ${esc(fmtDate(next.at))}${next.overdue?' (overdue)':''}`:''}</div>`:''}
      ${item.recruiter_name||item.recruiter_contact?`<div class="view-note">Recruiter: ${esc([item.recruiter_name,item.recruiter_contact].filter(Boolean).join(' · '))}</div>`:''}
      ${open?appForm(item):''}
    </div>
    <div class="item-actions">
      <select class="select app-status" data-action="app-status" data-id="${item.id}" aria-label="Application status">${appStatuses().map(s=>`<option value="${s}" ${item.status===s?'selected':''}>${esc(APP_LABEL[s]||s)}</option>`).join('')}</select>
      <button class="link-button" data-action="app-edit" data-id="${item.id}">${open?'Close':'Edit'}</button>
      <button class="link-button danger" data-action="app-delete" data-id="${item.id}">Delete</button>
    </div>
  </div>`;
}
function appForm(item){
  const resumes=D().resumes||[];
  const interviews=(item.interview_dates||[]).map(i=>`${i.at}${i.note?' '+i.note:''}`).join('\n');
  return `<form class="app-form section-space" data-form="application" data-id="${esc(item.id||'')}">
    <div class="field-grid">
      <label class="field"><span>Role *</span><input class="input" name="role" required value="${esc(item.role||'')}"></label>
      <label class="field"><span>Company</span><input class="input" name="company" value="${esc(item.company||'')}"></label>
      <label class="field"><span>Job URL</span><input class="input" name="job_url" type="url" value="${esc(item.job_url||'')}"></label>
      <label class="field"><span>Resume used</span><select class="select" name="resume_id"><option value="">—</option>${resumes.map(r=>`<option value="${r.id}" ${item.resume_id===r.id?'selected':''}>${esc(r.label)}</option>`).join('')}</select></label>
      <label class="field"><span>Status</span><select class="select" name="status">${appStatuses().map(s=>`<option value="${s}" ${item.status===s?'selected':''}>${esc(APP_LABEL[s]||s)}</option>`).join('')}</select></label>
      <label class="field"><span>Application date</span><input class="input" name="applied_at" type="date" value="${esc(String(item.applied_at||'').slice(0,10))}"></label>
      <label class="field"><span>Follow-up date</span><input class="input" name="follow_up_date" type="date" value="${esc(item.follow_up_date||'')}"></label>
      <label class="field"><span>Next action</span><input class="input" name="next_action" value="${esc(item.next_action||'')}" placeholder="e.g. finish the take-home"></label>
      <label class="field"><span>Recruiter name</span><input class="input" name="recruiter_name" value="${esc(item.recruiter_name||'')}"></label>
      <label class="field"><span>Recruiter contact</span><input class="input" name="recruiter_contact" value="${esc(item.recruiter_contact||'')}" placeholder="email or phone you entered yourself"></label>
    </div>
    <label class="field"><span>Interview dates — one per line: YYYY-MM-DD or YYYY-MM-DDTHH:MM, then an optional note</span><textarea class="textarea" name="interviews" rows="2">${esc(interviews)}</textarea></label>
    <label class="field"><span>Notes</span><textarea class="textarea" name="notes" rows="3">${esc(item.notes||'')}</textarea></label>
    ${(item.history||[]).length?`<div class="view-note">History: ${item.history.map(h=>`${esc(APP_LABEL[h.status]||h.status)} ${esc(fmtDate(h.at))}`).join(' → ')}</div>`:''}
    <div class="item-actions"><button class="primary-button" type="submit">Save</button><button class="link-button" type="button" data-action="app-edit" data-id="${esc(item.id||'new')}">Cancel</button></div>
  </form>`;
}

/* ------------------------------------------------------------- job market */
function barList(items,{empty='No data yet.',unit='listing',series=1,limit=12}={}){
  const rows=(items||[]).filter(item=>item&&item.count).slice(0,limit);
  if(!rows.length)return `<div class="empty-state">${esc(empty)}</div>`;
  const max=Math.max(...rows.map(item=>item.count),1);
  return `<div class="chart">${rows.map(item=>`
    <div class="chart-row" data-tip="${esc(item.name)}: ${esc(item.count)} ${unit}${item.count===1?'':'s'}">
      <span class="chart-label" title="${esc(item.name)}">${esc(item.name)}</span>
      <span class="chart-track"><span class="chart-fill ${series===2?'series-2':''}" style="width:${Math.max(3,Math.round(item.count/max*100))}%"></span></span>
      <span class="chart-value">${esc(item.count)}</span>
    </div>`).join('')}</div>`;
}
function portalList(items){
  const rows=(items||[]).filter(item=>item&&item.count);
  if(!rows.length)return '<div class="empty-state">No portals detected yet.</div>';
  const max=Math.max(...rows.map(item=>item.count),1);
  return `<div class="split-legend"><span><i style="background:var(--series-1)"></i>Job board</span><span><i style="background:var(--series-2)"></i>Company career page / other</span></div>
  <div class="chart">${rows.map(item=>`
    <div class="chart-row" data-tip="${esc(item.name)} (${esc(item.kind)}): ${esc(item.count)} listings">
      <span class="chart-label" title="${esc(item.name)}">${esc(item.name)}</span>
      <span class="chart-track"><span class="chart-fill ${item.kind==='Job board'?'':'series-2'}" style="width:${Math.max(3,Math.round(item.count/max*100))}%"></span></span>
      <span class="chart-value">${esc(item.count)}</span>
    </div>`).join('')}</div>`;
}
function heatmap(matrix,{rowKey='portals',rowLabel='source',empty='Not enough skill data yet.'}={}){
  const rows=matrix[rowKey]||[],skills=matrix.skills||[],cells=matrix.matrix||[];
  if(!rows.length||!skills.length)return `<div class="empty-state">${esc(empty)}</div>`;
  const max=Math.max(1,...cells.flat());
  return `<div class="heatmap-wrap"><table class="heatmap">
    <thead><tr><th scope="col"><span class="view-note">${esc(rowLabel)} ↓ · skill →</span></th>${skills.map(skill=>`<th scope="col">${esc(skill)}</th>`).join('')}</tr></thead>
    <tbody>${rows.map((name,row)=>`<tr><th scope="row">${esc(name)}</th>${skills.map((skill,col)=>{
      const value=cells[row]?.[col]||0;const heat=value?Math.max(.15,value/max):0;
      return `<td><span class="heat-cell ${heat>.6?'hot':''}" style="--heat:${heat}" data-tip="${esc(name)} · ${esc(skill)}: ${value} listing${value===1?'':'s'}">${value||''}</span></td>`;
    }).join('')}</tr>`).join('')}</tbody>
  </table></div>
  <div class="heat-legend"><span>Fewer</span><i class="heat-cell" style="--heat:.15"></i><i class="heat-cell" style="--heat:.45"></i><i class="heat-cell" style="--heat:.75"></i><i class="heat-cell" style="--heat:1"></i><span>More listings</span></div>`;
}
function splitBars(rows){
  rows=(rows||[]).filter(r=>r.board||r.company);
  if(!rows.length)return '<div class="empty-state">No skills recorded yet.</div>';
  const max=Math.max(1,...rows.map(r=>r.board+r.company));
  return `<div class="split-legend"><span><i style="background:var(--series-1)"></i>Job boards</span><span><i style="background:var(--series-2)"></i>Company career pages</span></div>
    ${rows.map(r=>`<div class="split-row" data-tip="${esc(r.name)}: ${r.board} on job boards · ${r.company} on career pages">
      <span class="chart-label">${esc(r.name)}</span>
      <span class="split-bar">${r.board?`<span class="board" style="width:${r.board/max*100}%"></span>`:''}${r.company?`<span class="company" style="width:${r.company/max*100}%"></span>`:''}</span>
      <span class="chart-value">${r.board} · ${r.company}</span></div>`).join('')}`;
}
function weeklyColumns(weeks){
  weeks=weeks||[];
  if(!weeks.some(w=>w.count))return '<div class="empty-state">No dated listings in the last 12 weeks.</div>';
  const max=Math.max(1,...weeks.map(w=>w.count));
  return `<div class="columns">${weeks.map((w,i)=>`<div class="column ${i===weeks.length-1?'current':''}" data-tip="Week of ${esc(fmtDate(w.name))}: ${w.count} listing${w.count===1?'':'s'}"><span style="height:${w.count?Math.max(3,w.count/max*100):0}%"></span></div>`).join('')}</div>
    <div class="column-labels">${weeks.map((w,i)=>`<span>${i%3===0||i===weeks.length-1?esc(new Date(w.name).toLocaleDateString(undefined,{month:'short',day:'numeric'})):''}</span>`).join('')}</div>
    <div class="view-note" style="margin-top:6px">Listings by posting week (or first seen when undated). The current week is highlighted in orange.</div>`;
}
function resumeFitTable(fit){
  if(!(fit||[]).length)return '<div class="empty-state">Upload resumes on the Resumes page to compare how each fits each role family.</div>';
  const families=Array.from(new Set(fit.flatMap(r=>Object.keys(r.families||{})))).filter(f=>f!=='Other');
  return `<div class="table-wrap"><table class="data-table fit-table"><thead><tr><th>Resume</th>${families.map(f=>`<th>${esc(f)}</th>`).join('')}</tr></thead>
    <tbody>${fit.map(r=>`<tr><td><b>${esc(r.label)}</b></td>${families.map(f=>{const v=(r.families||{})[f];
      return `<td>${v==null?'—':`<span class="heat-cell ${v/100>.6?'hot':''}" style="--heat:${Math.max(.12,v/100)}">${v}</span>`}</td>`;}).join('')}</tr>`).join('')}</tbody></table></div>
    <div class="view-note" style="margin-top:6px">Average combined match score of each resume per role family, across stored listings.</div>`;
}
function viewMarket(){
  const market=D().job_insights||{};
  const totals=market.totals||{};
  const recent=market.recent||[];
  const hasResumes=(D().resumes||[]).length>0;
  return heading('Intelligence','Skills market',
    'Which skills and roles appear in the listings this app has discovered. Each unique listing is counted once (cross-posted duplicates are merged), skill names are normalised through an alias dictionary, and sample sizes are shown so you can judge how much to trust each chart.',
    `<button class="primary-button" data-action="market-scan">Scan the market</button>`) +
    progressBox() +
    `<div class="market-hero">
      ${statCard('Fresh listings analysed',totals.listings??0,'▤')}
      ${statCard('Posted in 30 days',totals.recent_30d??0,'◷')}
      ${statCard('Boards & career sites',totals.portals??0,'◫')}
      ${statCard('Role families',totals.roles??0,'◧')}
      ${statCard('Distinct skills',totals.skills??0,'✳')}
    </div>
    ${datasetPanel(market)}
    <div class="market-grid section-space">
      <div class="panel">
        <div class="panel-head"><h3 class="panel-title">Most-requested skills</h3><span class="panel-kicker">listings mentioning</span></div>
        ${barList(market.skills,{empty:'No skills extracted from listings yet.'})}
      </div>
      <div class="panel">
        <div class="panel-head"><h3 class="panel-title">Your skill gap</h3><span class="panel-kicker">in demand · not on your resumes</span></div>
        ${hasResumes&&market.resume_complete===false?'<div class="empty-state">Skill gap hidden: the active resume\u2019s extracted profile looks incomplete. Review it on the Resumes page.</div>':hasResumes?barList(market.skill_gap,{empty:'Your resumes already cover the most-requested skills.',series:2}):'<div class="empty-state">Upload a resume on the Resumes page to see which in-demand skills it is missing.</div>'}
        ${hasResumes&&(market.skill_strengths||[]).length?`<div class="item-meta">${market.skill_strengths.slice(0,8).map(s=>`<span class="meta skill-have">✓ ${esc(s.name)} · ${esc(s.count)}</span>`).join('')}</div>`:''}
      </div>
      <div class="panel">
        <div class="panel-head"><h3 class="panel-title">Roles being hired</h3><span class="panel-kicker">role families</span></div>
        ${barList(market.roles,{empty:'No role titles stored yet.'})}
      </div>
      <div class="panel">
        <div class="panel-head"><h3 class="panel-title">Hiring trend</h3><span class="panel-kicker">last 12 weeks</span></div>
        ${weeklyColumns(market.weekly)}
      </div>
    </div>
    ${marketV2(market)}
    <div class="panel section-space">
      <div class="panel-head"><h3 class="panel-title">Skills × role family</h3><span class="panel-kicker">which roles ask for which skills</span></div>
      ${heatmap(market.skills_by_role||{},{rowKey:'roles',rowLabel:'role family',empty:'Scan more roles to build this matrix.'})}
    </div>
    <div class="market-grid section-space">
      <div class="panel">
        <div class="panel-head"><h3 class="panel-title">Job boards vs company career pages</h3><span class="panel-kicker">per skill</span></div>
        ${splitBars(market.board_vs_company)}
      </div>
      <div class="panel">
        <div class="panel-head"><h3 class="panel-title">Where listings come from</h3><span class="panel-kicker">top sources</span></div>
        ${portalList(market.portals)}
      </div>
    </div>
    <div class="panel section-space">
      <div class="panel-head"><h3 class="panel-title">Skills × source</h3><span class="panel-kicker">which skills each portal asks for</span></div>
      ${heatmap(market.skills_by_portal||{},{rowKey:'portals',rowLabel:'source'})}
    </div>
    <div class="market-grid section-space">
      <div class="panel">
        <div class="panel-head"><h3 class="panel-title">Resume fit by role family</h3><span class="panel-kicker">${(D().resumes||[]).length} resume(s)</span></div>
        ${resumeFitTable(market.resume_fit)}
      </div>
      <div class="panel">
        <div class="panel-head"><h3 class="panel-title">Top hiring employers</h3><span class="panel-kicker">named in listings</span></div>
        ${barList(market.employers,{empty:'Employers are not stated in enough listings yet.'})}
      </div>
      <div class="panel">
        <div class="panel-head"><h3 class="panel-title">Locations</h3><span class="panel-kicker">top ${(market.locations||[]).length}</span></div>
        ${barList(market.locations,{empty:'No locations stated in stored listings.'})}
      </div>
      <div class="panel">
        <div class="panel-head"><h3 class="panel-title">Listing freshness</h3><span class="panel-kicker">${totals.recent_ratio??0}% in 30 days</span></div>
        ${barList(market.freshness,{empty:'No dated listings yet.'})}
      </div>
    </div>
    <div class="panel section-space">
      <div class="panel-head"><h3 class="panel-title">Most recent listings</h3><span class="panel-kicker">${recent.length}</span></div>
      ${recent.length?`<div class="source-list">${recent.map(job=>`<div class="source-card">
        <div class="market-recent-head"><a class="source-title" href="${esc(job.original_url||'#')}" target="_blank" rel="noopener">${esc(job.title||'Untitled role')}</a>${badge(job.status||'unverified')}</div>
        <div class="item-meta">${meta(job.employer||'Employer not stated')}${meta(job.location||'Location not stated')}${job.posted_date?meta('Posted '+ageLabel(job.posted_date)):meta('Date unverified')}${job.source_platform?meta(job.source_platform):''}</div>
      </div>`).join('')}</div>`:emptyRich('No listings to chart yet',
        'Run a market scan. The page reads only stored listings and never invents skills, roles or dates.',
        `<button class="primary-button" data-action="market-scan">Scan the market</button>`)}
    </div>`;
}

/* -------------------------------------------------------------- government */
function viewGovernment(){
  const notices=D().notices||[];
  const f=state.filters.government;
  const filtered=notices.filter(notice=>{
    if(f.eligibility!=='all'&&notice.cse_eligibility!==f.eligibility)return false;
    if(f.doc!=='all'&&(notice.document_type||'')!==f.doc)return false;
    return true;
  });
  const eligibility=[['all','All eligibility'],['explicitly_eligible','CSE explicitly eligible'],
    ['eligible_based_on_listed_equivalent_degree','Equivalent degree'],['potentially_eligible_needs_verification','Needs verification'],
    ['not_eligible','Not eligible'],['not_verified','Not verified']];
  const docs=['all',...Array.from(new Set(notices.map(n=>n.document_type).filter(Boolean)))];
  return heading('Intelligence','Government & PSU',
    'Official recruitment discovery. Aggregators are used only for discovery; official notifications and application links are preserved where found.',
    `<button class="quiet-button" data-action="quick-search" data-category="government" data-query="">Discover notices</button>`) +
    progressBox() +
    `<div class="toolbar"><form data-form="discover" data-category="government">
      <input class="input" name="query" placeholder="Organisation, post, discipline or location…" value="${esc(state.lastQuery.government||'')}">
      <select class="select" name="freshness">${freshnessOptions(f.freshness)}</select>
      <button class="primary-button" type="submit">Search recruitment</button>
    </form></div>
    <div class="filter-row">
      <select class="select" data-action="gov-eligibility" style="width:auto">${eligibility.map(([v,l])=>`<option value="${v}" ${f.eligibility===v?'selected':''}>${l}</option>`).join('')}</select>
      <select class="select" data-action="gov-doc" style="width:auto">${docs.map(v=>`<option value="${esc(v)}" ${f.doc===v?'selected':''}>${v==='all'?'All document types':esc(v)}</option>`).join('')}</select>
    </div>` +
    (filtered.length?`<div class="list-grid">${filtered.map(noticeCard).join('')}</div>`:emptyRich('No recruitment notices stored',
      'Search by organisation or discipline. The engine prioritises official advertisements and notifications, extracts qualifications and deadlines, and never assumes CSE eligibility without explicit wording.',
      `<button class="primary-button" data-action="quick-search" data-category="government" data-query="">Search recruitment</button>`));
}
function noticeCard(notice){
  const current=stateOf('notice',notice.id);
  return `<article class="item-card">
    <div class="item-head">
      <div><h3 class="item-title">${notice.notification_url?`<a href="${esc(notice.notification_url)}" target="_blank" rel="noopener">${esc(notice.post_name||notice.organization||'Recruitment notice')}</a>`:esc(notice.post_name||notice.organization||'Recruitment notice')}</h3>
        <div class="item-sub">${esc(notice.organization||'Organisation not stated')}${notice.discipline?' · '+esc(notice.discipline):''}${notice.advertisement_number?' · Adv. '+esc(notice.advertisement_number):''}</div></div>
      <div class="chips">${badge(notice.status||'unverified')}${badge(notice.cse_eligibility||'not_verified')}</div>
    </div>
    <div class="kv-grid">
      ${kv('Vacancies',notice.vacancies)}
      ${kv('Qualifications',notice.qualifications)}
      ${kv('GATE paper',notice.gate_paper)}
      ${kv('Age limit',notice.age_limit)}
      ${kv('Salary',notice.salary)}
      ${kv('Location',notice.location)}
      ${kv('Applications open',notice.opening_date?fmtDate(notice.opening_date):'')}
      ${kv('Closing date',notice.closing_date?fmtDate(notice.closing_date):'')}
      ${kv('Exam date',notice.exam_date?fmtDate(notice.exam_date):'')}
      ${kv('Selection',notice.selection_process)}
      ${kv('Document type',notice.document_type)}
    </div>
    ${evidence(notice)}
    <div class="item-actions">
      ${notice.notification_url?`<a class="link-button" href="${esc(notice.notification_url)}" target="_blank" rel="noopener">Official notification</a>`:''}
      ${notice.application_url&&notice.application_url!==notice.notification_url?`<a class="link-button primary" href="${esc(notice.application_url)}" target="_blank" rel="noopener">Apply / portal</a>`:''}
      ${stateButtons('notice',notice.id,current)}
    </div>
  </article>`;
}

/* ------------------------------------------------------------------ exams */
function viewExams(){
  const events=D().exams||[];
  const f=state.filters.exams;
  const watch=(D().watchlists||{}).exam||[];
  const filtered=events;
  return heading('Intelligence','Examinations',
    'Dated events extracted from official notifications. Announced and tentative dates are labelled separately; past dates stay visible for context.',
    `<button class="quiet-button" data-action="quick-search" data-category="exams" data-query="">Discover exams</button>`) +
    progressBox() +
    `<div class="panel">
      <div class="panel-head"><h3 class="panel-title">Followed examinations</h3><span class="panel-kicker">${watch.length} tracked</span></div>
      <div class="watchlist">${watch.length?watch.map(name=>`<span class="watch-item">${esc(name)}<button data-action="remove-watch" data-kind="exam" data-name="${esc(name)}" title="Remove">×</button></span>`).join(''):'<span class="view-note">No examinations followed yet.</span>'}</div>
      <form data-form="watchlist" data-kind="exam" class="inline-form section-space"><input class="input" name="name" placeholder="Add an examination, e.g. GATE"><button class="quiet-button" type="submit">Follow</button></form>
    </div>
    <div class="toolbar section-space"><form data-form="discover" data-category="exams">
      <input class="input" name="query" placeholder="Examination name or organisation…" value="${esc(state.lastQuery.exams||'')}">
      <select class="select" name="freshness">${freshnessOptions(f.freshness)}</select>
      <button class="primary-button" type="submit">Search exams</button>
    </form></div>` +
    (filtered.length?`<div class="list-grid">${filtered.map(examCard).join('')}</div>`:emptyRich('No examination events stored',
      'Add examinations to your watchlist, then run a search. Events are extracted only when an official source states a date; missing dates are never generated from model knowledge.',
      `<button class="primary-button" data-action="quick-search" data-category="exams" data-query="">Search exams</button>`));
}
function examCard(event){
  const current=stateOf('exam',event.id);
  return `<article class="item-card">
    <div class="item-head">
      <div><h3 class="item-title">${event.notification_url?`<a href="${esc(event.notification_url)}" target="_blank" rel="noopener">${esc(event.exam_name||'Examination')}</a>`:esc(event.exam_name||'Examination')}</h3>
        <div class="item-sub">${esc(event.organization||'Conducting organisation not stated')} · ${esc(event.event_type||'event')}</div></div>
      <div class="chips">${badge(event.date_status||'unverified')}</div>
    </div>
    <div class="item-meta">${event.event_date?meta(fmtDate(event.event_date)):meta('Date unavailable')}${event.event_date?meta(event.event_date):''}</div>
    ${evidence(event)}
    <div class="item-actions">
      ${event.notification_url?`<a class="link-button" href="${esc(event.notification_url)}" target="_blank" rel="noopener">Official source</a>`:''}
      ${event.application_url&&event.application_url!==event.notification_url?`<a class="link-button primary" href="${esc(event.application_url)}" target="_blank" rel="noopener">Application portal</a>`:''}
      ${stateButtons('exam',event.id,current,{applied:false})}
    </div>
  </article>`;
}

/* ------------------------------------------------------------------- news */
function viewNews(){
  const items=D().news||[];
  const f=state.filters.news;
  const prefs=(D().preferences||{}).news||{};
  const presets=D().news_presets||{regions:[],topics:[]};
  const regions=Array.from(new Set([...presets.regions,...items.map(i=>i.region).filter(Boolean)]));
  const topics=Array.from(new Set([...presets.topics,...items.map(i=>i.topic).filter(Boolean)]));
  const count=(key,value)=>items.filter(i=>String(i[key]||'')===value).length;
  const filtered=items.filter(item=>{
    if(f.region&&String(item.region||'Global')!==f.region)return false;
    if(f.topic&&String(item.topic||'')!==f.topic)return false;
    if(f.q){const hay=`${item.title||''} ${item.summary||''} ${item.publisher||''}`.toLowerCase();if(!hay.includes(f.q.toLowerCase()))return false;}
    return true;
  });
  const searchLabel=[f.region&&f.region!=='Global'?f.region:'',f.topic].filter(Boolean).join(' · ')||'my interests';
  return heading('Intelligence','AI news',
    'Specific, dated AI stories from original publishers. Pick a region and topic: the filters narrow stored stories, and “Search” runs a live search targeted at that region’s publishers and that topic. Regions are detected from each story’s content and publisher.',
    `<button class="primary-button" data-action="news-search">Search ${esc(searchLabel)}</button>`) +
    progressBox() +
    `<div class="panel">
      <div class="filter-row" style="margin-top:0"><span class="filter-label">Region</span>
        <button class="chip ${!f.region?'active':''}" data-action="news-region" data-value="">All <span class="chip-count">${items.length}</span></button>
        ${regions.map(r=>`<button class="chip ${f.region===r?'active':''}" data-action="news-region" data-value="${esc(r)}">${esc(r)} <span class="chip-count">${count('region',r)}</span></button>`).join('')}
      </div>
      <div class="filter-row" style="margin-bottom:0"><span class="filter-label">Topic</span>
        <button class="chip ${!f.topic?'active':''}" data-action="news-topic" data-value="">All</button>
        ${topics.map(t=>`<button class="chip ${f.topic===t?'active':''}" data-action="news-topic" data-value="${esc(t)}">${esc(t)} <span class="chip-count">${count('topic',t)}</span></button>`).join('')}
      </div>
    </div>
    <div class="toolbar section-space"><form data-form="discover" data-category="news">
      <input class="input" name="query" placeholder="Optional: company, model or keyword (e.g. “Sarvam”, “IndiaAI mission”)" value="${esc(state.lastQuery.news||'')}">
      <select class="select" name="freshness">${freshnessOptions(f.freshness)}</select>
      <button class="primary-button" type="submit">Search ${esc(searchLabel)}</button>
    </form></div>
    <div class="filter-row"><div class="banner" style="flex:1">${filtered.length} of ${items.length} stored stories${f.region?' · '+esc(f.region):''}${f.topic?' · '+esc(f.topic):''}${prefs.region?` · default region: ${esc(prefs.region)}`:''}</div>
      <input class="input" style="width:200px" data-action="news-q" placeholder="Filter text…" value="${esc(f.q||'')}"></div>` +
    (filtered.length?`<div class="list-grid">${filtered.map(item=>intelCard(item,'news',false)).join('')}</div>`:emptyRich('No stories for this region and topic yet',
      `Run a search for ${searchLabel}. Regional searches target that region’s publishers (for India: Analytics India Magazine, Inc42, YourStory, Economic Times, Mint, MediaNama) and government sources.`,
      `<button class="primary-button" data-action="news-search">Search ${esc(searchLabel)}</button>`));
}

/* ----------------------------------------------------------------- papers */
function viewPapers(){
  const items=D().papers||[];
  const f=state.filters.papers;
  const interests=((D().preferences||{}).papers||{}).interests||[];
  const filtered=items;
  return heading('Intelligence','Research papers',
    'Papers, technical reports, datasets and resources. Peer-review status is shown only when the source supports it.',
    `<button class="quiet-button" data-action="quick-search" data-category="papers" data-query="">Discover research</button>`) +
    progressBox() +
    `<div class="toolbar"><form data-form="discover" data-category="papers">
      <input class="input" name="query" placeholder="Topic, method or benchmark…" value="${esc(state.lastQuery.papers||'')}">
      <select class="select" name="freshness">${freshnessOptions(f.freshness)}</select>
      <button class="primary-button" type="submit">Search papers</button>
    </form></div>
    ${interests.length?`<div class="chips">${interests.map(topic=>`<button class="chip" data-action="quick-search" data-category="papers" data-query="${esc(topic)}">${esc(topic)}</button>`).join('')}</div>`:''}` +
    (filtered.length?`<div class="list-grid">${filtered.map(item=>intelCard(item,'paper',false)).join('')}</div>`:emptyRich('No research stored',
      'Run a topic search across arXiv, OpenReview, ACL Anthology, PMLR and other repositories. Only source-supported fields are stored.',
      `<button class="primary-button" data-action="quick-search" data-category="papers" data-query="">Search papers</button>`));
}
function intelCard(item,kind,applied){
  const current=stateOf(kind,item.id);
  const label=kind==='news'?'news':'paper';
  return `<article class="item-card">
    <div class="item-head">
      <div><h3 class="item-title"><a href="${esc(item.original_url||'#')}" target="_blank" rel="noopener">${esc(item.title||'Untitled')}</a></h3>
        <div class="item-sub">${esc(item.publisher||'Publisher not stated')}${item.authors?' · '+esc(item.authors):''}${item.published_date?' · '+esc(fmtDate(item.published_date)):''}</div></div>
      <div class="chips">${badge(item.freshness||'date_unavailable')}${kind==='paper'?badge(item.peer_reviewed||'not_verified'):''}</div>
    </div>
    ${item.summary?`<div class="item-body">${esc(plain(item.summary).slice(0,520))}</div>`:''}
    ${item.why_it_matters?`<div class="reason"><b>Why it matters:</b> ${esc(item.why_it_matters)}</div>`:''}
    <div class="item-meta">
      ${item.region?meta('Region: '+item.region):''}
      ${item.topic?meta('Topic: '+item.topic):''}
      ${item.code_url?`<a class="meta" href="${esc(item.code_url)}" target="_blank" rel="noopener">Code</a>`:''}
      ${item.dataset_url?`<a class="meta" href="${esc(item.dataset_url)}" target="_blank" rel="noopener">Dataset</a>`:''}
    </div>
    ${evidence(item)}
    <div class="item-actions">
      <a class="link-button primary" href="${esc(item.original_url||'#')}" target="_blank" rel="noopener">Open source</a>
      ${stateButtons(label,item.id,current,{applied})}
    </div>
  </article>`;
}

/* ---------------------------------------------------------------- research */
function viewAsk(){
  return heading('Intelligence','Ask intelligence',
    'Describe what you need in your own words. The planner generates focused queries, searches multiple sources, fetches promising pages and validates evidence.',
    '') +
    progressBox() +
    `<div class="panel">
      <form data-form="research" class="research-box">
        <textarea class="textarea" name="request" placeholder="e.g. Which of my saved roles close this week? What do startups in Pune ask for in backend roles?">${esc(state.askPrefill||'')}</textarea>
        <div class="item-actions"><button class="primary-button" type="submit">Run request</button></div>
      </form>
      <div class="chips">${[
        'Find current entry-level AI engineer jobs in India',
        'Find open government and PSU technical recruitment where B.Tech CSE graduates are eligible',
        'Find the latest GATE examination notifications and upcoming important dates',
        'Find recent research on agent memory',
      ].map(text=>`<button class="chip" data-action="fill-request" data-text="${esc(text)}">${esc(text)}</button>`).join('')}</div>
    </div>` + researchResult();
}
function viewResearch(){
  return heading('Research','Research workspace',
    'Submit arbitrary research questions and inspect the generated query plan, retrieved sources and final evidence-backed answer.',
    '') +
    progressBox() +
    `<div class="panel">
      <form data-form="research" class="research-box">
        <textarea class="textarea" name="request" placeholder="Ask a research question, name a website to search, or compare two sources."></textarea>
        <div class="item-actions"><button class="primary-button" type="submit">Research</button></div>
      </form>
    </div>` +
    researchResult() +
    `<div class="panel section-space"><div class="panel-head"><h3 class="panel-title">Recent search sessions</h3><span class="panel-kicker">discovery</span></div>${sessionsHtml()}</div>`;
}
function researchResult(){
  const history=(D().history||[]).filter(item=>item.kind==='research'&&item.status==='complete'&&item.result);
  const last=history[0];
  if(!last)return '';
  const result=last.result;
  const queries=result.queries||[];
  return `<div class="panel section-space">
    <div class="panel-head"><h3 class="panel-title">Last research result</h3><span class="panel-kicker">${esc(fmtDateTime(last.created_at))}</span></div>
    <div class="banner">Interpreted request: ${esc(result.request||last.request)}</div>
    ${queries.length?`<div class="chips">${queries.map(q=>`<span class="chip">${esc(q)}</span>`).join('')}</div>`:''}
    <div class="section-answer">${esc(result.answer||'No answer was produced.')}</div>
    ${(result.sources||[]).length?`<div class="item-meta">${sourceLinks(result.sources)}</div>`:''}
    ${(result.source_changes||[]).length?`<div class="banner warn section-space">${result.source_changes.length} source(s) changed since they were last seen.</div>`:''}
  </div>`;
}
function sessionsHtml(){
  const sessions=D().search_sessions||[];
  if(!sessions.length)return '<div class="empty-state">No discovery sessions yet.</div>';
  return sessions.slice(0,10).map(session=>{
    const summary=session.summary||{};
    return `<div class="session-card"><div class="session-head"><b>${esc(session.category)}</b><span>${badge(session.status||'running')}</span></div>
      <div class="session-body">${esc(session.request||'')}</div>
      <div class="item-meta">${meta('sources '+esc(summary.sources_found||0))}${meta('fetched '+esc(summary.pages_fetched||0))}${meta('records '+esc(summary.records||0))}${summary.duration_seconds!=null?meta(summary.duration_seconds+'s'):''}</div>
      ${session.error?`<div class="reason">${esc(session.error)}</div>`:''}
    </div>`;
  }).join('');
}

/* ---------------------------------------------------------------- planning */
function catBadge(cat){return cat?`<span class="cat cat-${esc(cat)}">${esc(cat)}</span>`:'';}
function recurrenceLabel(value){
  if(!value)return '';
  if(value.startsWith('weekly:'))return 'every '+value.split(':')[1];
  return {daily:'every day',weekdays:'weekdays',weekends:'weekends',weekly:'weekly',monthly:'monthly'}[value]||value;
}
function taskRow(task){
  const done=task.status==='completed';
  const fromNote=task.source&&!['user','tracker'].includes(task.source);
  const overdue=task.due_date&&task.due_date<D().date&&!done&&!task.recurrence;
  return `<div class="task-row">
    <button class="check-button ${done?'done':''}" data-action="toggle-task" data-id="${task.id}" title="Mark ${done?'pending':'done'}" aria-label="Toggle task">${done?'✓':''}</button>
    <span class="task-text ${done?'completed':''}">${esc(task.text)}</span>
    ${catBadge(task.category)}
    ${task.recurrence?`<span class="task-due">↻ ${esc(recurrenceLabel(task.recurrence))}</span>`:''}
    ${task.due_time?`<span class="task-due">${esc(task.due_time)}</span>`:''}
    ${task.due_date&&!task.recurrence?`<span class="task-due ${overdue?'overdue':''}">${esc(fmtDate(task.due_date))}</span>`:''}
    <span class="badge source ${fromNote?'open':'unverified'}">${esc(fromNote?String(task.source).split('/').pop():task.source==='tracker'?'Tracker':'Manual')}</span>
    ${fromNote?'':`<button class="link-button danger" data-action="delete-task" data-id="${task.id}" title="Delete">✕</button>`}
    ${task.original_text&&task.original_text!==task.text?`<span class="task-original">from note: “${esc(task.original_text)}”</span>`:''}
  </div>`;
}
function todayPlanPanel(plan,{compact=false}={}){
  plan=plan||{};
  const schedule=plan.schedule||[];
  const suggestions=plan.suggestions||[];
  return `<div class="grid grid-2">
    <div class="panel">
      <div class="panel-head"><h3 class="panel-title">Today’s plan</h3><span class="panel-kicker">${esc(fmtDate(plan.date))}</span></div>
      ${schedule.length?`<div class="schedule">${schedule.map(item=>`<div class="slot ${item.overdue?'overdue':''} ${item.done?'done':''}">
        <span class="slot-time">${esc(item.time||'Any time')}</span>
        <span class="slot-title">${item.url?`<a href="${esc(item.url)}" target="_blank" rel="noopener">${esc(item.title)}</a>`:esc(item.title)}${item.overdue?' <span class="badge expired">overdue</span>':''}${item.recurrence?` <span class="view-note">↻ ${esc(recurrenceLabel(item.recurrence))}</span>`:''}</span>
        <span>${item.task_id?`<button class="link-button" data-action="toggle-task" data-id="${item.task_id}">${item.done?'Undo':'Done'}</button>`:catBadge(item.category)}</span>
      </div>`).join('')}</div>`:'<div class="empty-state">Nothing scheduled for today. Write tasks in your notes, e.g. “walk my dog every evening”.</div>'}
    </div>
    <div class="panel">
      <div class="panel-head"><h3 class="panel-title">Suggested next steps</h3><span class="panel-kicker">from your jobs & skills</span></div>
      ${suggestions.length?suggestions.map(s=>`<div class="suggestion"><span class="suggestion-icon ${esc(s.kind)}">${s.kind==='learn'?'✎':s.kind==='follow_up'?'↻':'➚'}</span><div><b>${s.url?`<a href="${esc(s.url)}" target="_blank" rel="noopener">${esc(s.title)}</a>`:esc(s.title)}</b><div class="view-note">${esc(s.detail||'')}</div></div></div>`).join(''):'<div class="empty-state">Run a market scan and upload a resume to get job and learning suggestions.</div>'}
      ${!compact&&(plan.deadlines||[]).length?`<div class="section-title section-space">Upcoming deadlines (14 days)</div><div class="timeline">${plan.deadlines.map(d=>`<div class="timeline-row"><div class="timeline-date">${esc(fmtDate(d.date))}</div><div class="timeline-body">${d.url?`<a href="${esc(d.url)}" target="_blank" rel="noopener"><b>${esc(d.title)}</b></a>`:`<b>${esc(d.title)}</b>`}<br>${esc(d.kind)}</div></div>`).join('')}</div>`:''}
    </div>
  </div>`;
}
function viewPlanning(){
  const tasks=D().tasks||[];
  const planning=D().planning||{};
  const plan=D().today_plan||{};
  const groups=plan.groups||{};
  const files=planning.files||[];
  const note=state.note;
  const groupDefs=[['overdue','Overdue'],['today','Today'],['this_week','This week'],['later','Later'],['no_date','Anytime']];
  return heading('Personal','Planning',
    'Write plans in plain language in your notes — “i want to walk my dog every evening”, “apply to 3 AI jobs by friday”. They become dated, categorised tasks, feed today’s plan and the daily briefing, and stay in sync when you edit the note.',
    `<button class="quiet-button" data-action="planning-refresh">Re-import notes</button><a class="quiet-button" href="/api/export/calendar.ics">Add to calendar (.ics)</a>`) +
    todayPlanPanel(plan) +
    `<div class="grid grid-2 section-space">
      <div class="panel">
        <div class="panel-head"><h3 class="panel-title">Tasks</h3><span class="panel-kicker">${tasks.filter(t=>t.status!=='completed').length} pending · ${tasks.length} total</span></div>
        <form data-form="task" class="inline-form"><input class="input" name="text" placeholder="Type naturally: “call mom on friday at 6pm”"><input class="input" name="due_date" type="date" style="flex:0 0 150px"><button class="primary-button" type="submit">Add</button></form>
        ${groupDefs.map(([key,label])=>{const list=groups[key]||[];return list.length?`<div class="section-title section-space">${label} <span class="panel-kicker">${list.length}</span></div><div class="task-list">${list.map(t=>taskRow(tasks.find(x=>x.id===t.id)||t)).join('')}</div>`:'';}).join('')}
        ${tasks.filter(t=>t.status==='completed'&&!t.recurrence).length?`<details class="collapsible"><summary>Completed <span class="panel-kicker">${tasks.filter(t=>t.status==='completed'&&!t.recurrence).length}</span></summary><div class="task-list">${tasks.filter(t=>t.status==='completed'&&!t.recurrence).map(taskRow).join('')}</div></details>`:''}
        ${!tasks.length?'<div class="empty-state section-space">No tasks yet. Add one above or write a line in a note file.</div>':''}
      </div>
      <div class="panel">
        <div class="panel-head"><h3 class="panel-title">Notes</h3><span class="panel-kicker">${esc(planning.notes_dir||'')}</span></div>
        ${planning.missing?'<div class="banner warn">The notes directory does not exist yet. Saving a note below creates it.</div>':`<div class="banner good">${esc(planning.tasks_found??0)} task(s) read from ${esc(files.length)} note file(s)${planning.sync&&planning.sync.archived?` · ${esc(planning.sync.archived)} archived after removal from notes`:''}.</div>`}
        ${(planning.errors||[]).length?`<div class="banner warn section-space">${planning.errors.map(esc).join('<br>')}</div>`:''}
        <div class="filter-row">${files.filter(f=>/\.(txt|md|markdown)$/i.test(f)).map(file=>`<button class="chip ${note&&note.name===file?'active':''}" data-action="open-note" data-name="${esc(file)}">${esc(file)}</button>`).join('')}
          <button class="chip" data-action="new-note">+ New note</button></div>
        ${note?`<form data-form="note" data-name="${esc(note.name)}">
          ${note.isNew?`<div class="field"><label>File name</label><input class="input" name="name" value="${esc(note.name)}" placeholder="today.txt"></div>`:`<div class="view-note">Editing <span class="mono">${esc(note.name)}</span></div>`}
          <textarea class="textarea notes-editor section-space" name="content" spellcheck="true">${esc(note.content||'')}</textarea>
          <div class="field-actions"><button class="primary-button" type="submit">Save & extract tasks</button><button class="quiet-button" type="button" data-action="close-note">Close</button></div>
        </form>`:'<div class="view-note">Open a note to edit it here. Saving re-extracts its tasks immediately.</div>'}
        <div class="settings-section">
          <h3>Smarter extraction</h3>
          <div class="view-note">Let your local model turn long free-form paragraphs into separate tasks. Nothing leaves your machine.</div>
          <div class="field-actions"><button class="quiet-button" data-action="interpret-notes">Interpret notes with local model</button></div>
          ${state.suggestions?`<div class="task-list section-space">${state.suggestions.items.length?state.suggestions.items.map((s,i)=>`<div class="task-row"><span class="task-text">${esc(s.text)}</span>${catBadge(s.category)}${s.due_date?`<span class="task-due">${esc(fmtDate(s.due_date))}</span>`:''}${s.due_time?`<span class="task-due">${esc(s.due_time)}</span>`:''}${s.recurrence?`<span class="task-due">↻ ${esc(recurrenceLabel(s.recurrence))}</span>`:''}<button class="link-button" data-action="add-suggestion" data-index="${i}">Add</button></div>`).join(''):'<div class="empty-state">No additional tasks found.</div>'}</div><div class="view-note">Source: ${esc(state.suggestions.source)}</div>`:''}
        </div>
        <div class="notes-help section-space">
          <div class="section-title">Understood automatically</div>
          <pre class="notes-example">i want to walk my dog every evening
need to go for a run tomorrow at 6pm
remind me to pay rent by 15 nov
- [ ] Apply to 3 AI roles due 2026-11-15
revise GATE CS every morning</pre>
        </div>
      </div>
    </div>`;
}

/* ----------------------------------------------------------------- history */
function viewHistory(){
  const history=D().history||[];
  return heading('Personal','History',
    'Local execution history for briefings, research and discovery sessions. Errors are retained rather than hidden.',
    `<button class="quiet-button" data-action="refresh">Refresh</button>`) +
    `<div class="panel"><div class="panel-head"><h3 class="panel-title">Requests</h3><span class="panel-kicker">${history.length}</span></div>
      ${history.length?`<div class="source-list">${history.map(item=>`<div class="history-item"><div class="history-head"><b>${esc(item.kind)}</b><span>${badge(item.status||'')}</span></div><p>${esc(item.request)}</p><div class="item-meta">${meta(fmtDateTime(item.created_at))}${item.error?meta(item.error):''}</div></div>`).join('')}</div>`:'<div class="empty-state">No history yet.</div>'}
    </div>
    <div class="panel section-space"><div class="panel-head"><h3 class="panel-title">Discovery sessions</h3><span class="panel-kicker">${(D().search_sessions||[]).length}</span></div>${sessionsHtml()}</div>`;
}

/* ---------------------------------------------------------------- settings */
function viewSettings(){
  const settings=D().settings||{};
  const prefs=D().preferences||{};
  const jobs=prefs.jobs||{};
  const government=prefs.government||{};
  const news=prefs.news||{};
  const papers=prefs.papers||{};
  const exams=prefs.exams||{};
  const watchlists=D().watchlists||{};
  const portals=Object.entries(jobs.portals||{}).map(([name,portal])=>
    `<label class="portal-card"><input type="checkbox" name="portal:${esc(name)}" ${portal.enabled?'checked':''}><span>${esc(name)}</span><small>${esc(portal.domain||'custom')}</small></label>`).join('');
  const profile=D().profile;
  return heading('Personal','Settings','Preferences are stored locally and applied to future searches, matching and briefings.','') +
    appearancePanel() + `<div class="panel section-space">
      <div class="panel-head"><h3 class="panel-title">Local model & resources</h3><span class="panel-kicker">Ollama</span></div>
      <form data-form="settings">
        <div class="settings-grid">
          <div class="field"><label>Installed Ollama model</label><select class="select" name="ollama_model">${modelOptions()}</select><small>Only installed models are accepted. Nothing is pulled automatically.</small></div>
          <div class="field"><label>Max search queries</label><input class="input" name="max_search_queries" type="number" min="1" max="8" value="${esc(settings.max_search_queries||6)}"></div>
          <div class="field"><label>Max fetch URLs</label><input class="input" name="max_fetch_urls" type="number" min="1" max="8" value="${esc(settings.max_fetch_urls||4)}"></div>
          <div class="field"><label>Max content characters</label><input class="input" name="max_content_chars" type="number" min="2000" max="120000" value="${esc(settings.max_content_chars||120000)}"></div>
          <div class="field"><label>Ollama timeout (s)</label><input class="input" name="ollama_timeout" type="number" min="5" max="180" value="${esc(settings.ollama_timeout||120)}"></div>
          <div class="field"><label>MCP timeout (s)</label><input class="input" name="mcp_timeout" type="number" min="5" max="60" value="${esc(settings.mcp_timeout||25)}"></div>
          <div class="field"><label>Planning notes directory</label><input class="input" name="notes_dir" value="${esc(settings.notes_dir||'')}"></div>
          <div class="field full"><label>Briefing preferences</label><input class="input" name="briefing_preferences" value="${esc(settings.briefing_preferences||'')}" placeholder="Location, priorities, constraints"></div>
        </div>
        <div class="field-actions"><button class="primary-button" type="submit">Save settings</button><button class="quiet-button" type="button" data-action="load-models">Reload installed models</button><button class="quiet-button" type="button" data-action="diagnostics">Run MCP diagnostic</button></div>
      </form>
      ${state.lastJob&&state.lastJob.kind==='mcp_diagnostics'&&state.lastJob.result?`<div class="diagnostic-output section-space">${esc(JSON.stringify(state.lastJob.result,null,2))}</div>`:''}
    </div>

    <div class="panel section-space">
      <div class="panel-head"><h3 class="panel-title">Job preferences</h3><span class="panel-kicker">editable</span></div>
      <form data-form="preferences">
        <div class="settings-grid">
          <div class="field full"><label>Roles</label><input class="input" name="roles" value="${esc((jobs.roles||[]).join(', '))}" placeholder="AI Engineer, LLM Engineer, Python Developer"><small>Comma-separated. Leave blank to use your request.</small></div>
          <div class="field"><label>Experience</label><select class="select" name="experience">${['any','fresher','internship','0-1 years','1-2 years','2-3 years','experienced'].map(v=>`<option value="${v}" ${jobs.experience===v?'selected':''}>${v}</option>`).join('')}</select></div>
          <div class="field"><label>Remote preference</label><select class="select" name="remote">${['any','remote','hybrid','on-site'].map(v=>`<option value="${v}" ${jobs.remote===v?'selected':''}>${v}</option>`).join('')}</select></div>
          <div class="field"><label>Employment types</label><input class="input" name="employment_types" value="${esc((jobs.employment_types||[]).join(', '))}" placeholder="Full-time, Internship, Contract"></div>
          <div class="field"><label>Locations</label><input class="input" name="locations" value="${esc((jobs.locations||[]).join(', '))}" placeholder="India, Bengaluru, Remote"></div>
          <div class="field"><label>Minimum salary</label><input class="input" name="salary_min" type="number" min="0" value="${esc(jobs.salary_min??'')}" placeholder="Ignore if blank"></div>
          <div class="field"><label>Maximum salary</label><input class="input" name="salary_max" type="number" min="0" value="${esc(jobs.salary_max??'')}" placeholder="Ignore if blank"></div>
          <div class="field"><label>Freshness</label><select class="select" name="job_freshness">${freshnessOptions(jobs.freshness||'30d')}</select></div>
          <div class="field full"><label>Skills</label><input class="input" name="skills" value="${esc((jobs.skills||[]).join(', '))}" placeholder="Python, FastAPI, PyTorch, RAG, MCP"></div>
          <div class="field full"><label>Market scan roles</label><input class="input" name="scan_roles" value="${esc((jobs.scan_roles||[]).join(', '))}" placeholder="AI Engineer, Backend Developer, Data Engineer"><small>One search pass per role (max 12; about 30–60 s each). Suggestions: ${(jobs.scan_role_suggestions||[]).map(esc).join(', ')}</small></div>
          <div class="field"><label class="check-row"><input type="checkbox" name="ignore_salary" ${jobs.ignore_salary!==false?'checked':''}> Ignore salary filters</label></div>
          <div class="field"><label class="check-row"><input type="checkbox" name="match_resume" ${jobs.match_resume!==false?'checked':''}> Use local resume profile for matching</label></div>
        </div>
        <div class="settings-section"><h3>Job portals</h3><div class="view-note">Enabled portals contribute targeted site queries. Add any custom website below.</div><div class="portal-grid">${portals}</div></div>
        <div class="field section-space"><label>Custom websites</label><input class="input" name="custom_sites" value="${esc((jobs.custom_sites||[]).join(', '))}" placeholder="careers.example.com, jobs.example.org"></div>
        <div class="field-actions"><button class="primary-button" type="submit">Save preferences</button></div>
      </form>
    </div>

    <div class="panel section-space">
      <div class="panel-head"><h3 class="panel-title">Government, exams, news & research</h3><span class="panel-kicker">interests</span></div>
      <form data-form="preferences">
        <div class="settings-grid">
          <div class="field"><label>Government disciplines</label><input class="input" name="disciplines" value="${esc((government.disciplines||[]).join(', '))}" placeholder="Computer Science, Information Technology"></div>
          <div class="field"><label>GATE paper</label><input class="input" name="gate_paper" value="${esc(government.gate_paper||'')}" placeholder="CS"></div>
          <div class="field"><label>Government freshness</label><select class="select" name="gov_freshness">${freshnessOptions(government.freshness||'90d')}</select></div>
          <div class="field"><label>Exam freshness</label><select class="select" name="exam_freshness">${freshnessOptions(exams.freshness||'365d')}</select></div>
          <div class="field full"><label>AI news interests</label><input class="input" name="news_interests" value="${esc((news.interests||[]).join(', '))}" placeholder="AI agents, LLM inference, open source AI"></div>
          <div class="field"><label>Default news region</label><select class="select" name="news_region">${((D().news_presets||{}).regions||['Global','India']).map(r=>`<option value="${esc(r)}" ${(news.region||'India')===r?'selected':''}>${esc(r)}</option>`).join('')}</select></div>
          <div class="field"><label>News freshness</label><select class="select" name="news_freshness">${freshnessOptions(news.freshness||'7d')}</select></div>
          <div class="field full"><label>Research interests</label><input class="input" name="paper_interests" value="${esc((papers.interests||[]).join(', '))}" placeholder="LLM agents, RAG, efficient inference"></div>
          <div class="field"><label>Papers freshness</label><select class="select" name="paper_freshness">${freshnessOptions(papers.freshness||'30d')}</select></div>
        </div>
        <div class="field-actions"><button class="primary-button" type="submit">Save interests</button></div>
      </form>
    </div>

    <div class="panel section-space">
      <div class="panel-head"><h3 class="panel-title">Watchlists</h3><span class="panel-kicker">persisted</span></div>
      <div class="grid grid-2">
        <div>
          <div class="section-title">Examinations</div>
          <div class="watchlist">${(watchlists.exam||[]).length?(watchlists.exam||[]).map(name=>`<span class="watch-item">${esc(name)}<button data-action="remove-watch" data-kind="exam" data-name="${esc(name)}">×</button></span>`).join(''):'<span class="view-note">None followed.</span>'}</div>
          <form data-form="watchlist" data-kind="exam" class="inline-form section-space"><input class="input" name="name" placeholder="Add examination"><button class="quiet-button" type="submit">Add</button></form>
        </div>
        <div>
          <div class="section-title">Organisations & PSUs</div>
          <div class="watchlist">${(watchlists.organization||[]).length?(watchlists.organization||[]).map(name=>`<span class="watch-item">${esc(name)}<button data-action="remove-watch" data-kind="organization" data-name="${esc(name)}">×</button></span>`).join(''):'<span class="view-note">None followed.</span>'}</div>
          <form data-form="watchlist" data-kind="organization" class="inline-form section-space"><input class="input" name="name" placeholder="Add organisation"><button class="quiet-button" type="submit">Add</button></form>
        </div>
      </div>
    </div>

    <div class="panel section-space"><div class="panel-head"><h3 class="panel-title">Resumes</h3><a class="link-button" href="#resumes" data-view="resumes">Open resume manager</a></div><div class="view-note">Active resume: <b>${esc((activeResume()||{}).label||'none')}</b></div></div>
    ${sourcesPanel(prefs)}

    <div class="panel section-space">
      <div class="panel-head"><h3 class="panel-title">Automation & exports</h3><span class="panel-kicker">optional</span></div>
      <form data-form="automation">
        <div class="settings-grid">
          <div class="field"><label class="check-row"><input type="checkbox" name="daily_refresh" ${(prefs.automation||{}).daily_refresh?'checked':''}> Refresh automatically every day</label><small>Runs while the app is open, once per day after the chosen time.</small></div>
          <div class="field"><label>Refresh time</label><input class="input" type="time" name="refresh_time" value="${esc((prefs.automation||{}).refresh_time||'08:00')}"></div>
          <div class="field"><label>What to refresh</label><div class="chips">${['jobs','news','papers','government','exams'].map(c=>`<label class="chip"><input type="checkbox" name="auto:${c}" ${((prefs.automation||{}).categories||['jobs','news']).includes(c)?'checked':''}> ${c}</label>`).join('')}</div></div>
        </div>
        <div class="field-actions"><button class="primary-button" type="submit">Save automation</button><a class="quiet-button" href="/api/export/calendar.ics">Download calendar (.ics)</a><a class="quiet-button" href="/api/export/jobs.csv">Download jobs (.csv)</a></div>
      </form>
    </div>

    <div class="panel section-space">
      <div class="panel-head"><h3 class="panel-title">Privacy & local data</h3><span class="panel-kicker">local-first</span></div>
      <div class="banner good">All preferences, intelligence records, resumes and history are stored in the local SQLite database. No cloud LLM fallback is used.</div>
      <div class="item-actions">
        <button class="quiet-button" data-action="export">Export local data (JSON)</button>
        <button class="danger-button" data-action="clear-intel">Clear discovered intelligence</button>
      </div>
      <div class="view-note section-space">Clearing intelligence removes jobs, notices, exam events, news, papers, sessions and saved states. Tasks, history, briefings and preferences are preserved.</div>
    </div>`;
}
function modelOptions(){
  const current=(D().settings||{}).ollama_model||'';
  const models=state.models.length?state.models:[current].filter(Boolean);
  if(!models.length)return '<option value="">No installed model detected</option>';
  return models.map(model=>`<option value="${esc(model)}" ${model===current?'selected':''}>${esc(model)}</option>`).join('');
}
function profileEditor(profile){
  const prof=profile?profile.profile||{}:{};
  const fields=['job_titles','education','skills','languages','frameworks','projects','certifications','keywords'];
  return `<div class="profile-editor section-space" id="profile-editor" data-resume-id="${esc(profile&&profile.id||'')}">
    <div class="field-grid">
      <div class="field"><label>Graduation year</label><input class="input" name="graduation_year" type="number" min="1980" max="2100" value="${esc(prof.graduation_year??'')}"></div>
      <div class="field"><label>Experience years</label><input class="input" name="experience_years" type="number" min="0" max="60" value="${esc(prof.experience_years??0)}"></div>
    </div>
    ${fields.map(field=>`<div class="field"><label>${field}</label><textarea class="textarea" name="${field}" placeholder="One item per line">${esc((prof[field]||[]).join('\n'))}</textarea></div>`).join('')}
    <div class="item-actions"><button class="quiet-button" type="button" data-action="save-profile">Save reviewed profile</button></div>
  </div>`;
}

/* ----------------------------------------------------------------- resumes */
function viewResumes(){
  const resumes=D().resumes||[];
  const active=activeResume();
  const editing=resumes.find(r=>r.id===state.editResume)||null;
  return heading('Jobs','Resumes',
    'Upload one resume per direction. The active resume drives job ranking everywhere. Files and extracted profiles stay on this computer; only short role titles and a few skill keywords are used in web searches.',
    `<button class="primary-button" data-action="resume-pick">Upload resume</button><input id="resume-file" type="file" accept=".pdf,.docx,.txt,.md" onchange="handleResumeFile(event)" hidden>`) +
    progressBox() +
    `<div class="panel">
      <div class="panel-head"><h3 class="panel-title">Active resume</h3><span class="panel-kicker">${active?esc(active.filename||''):''}</span></div>
      ${active?`<div><b style="font-size:15px">${esc(active.label)}</b> <span class="badge active">active</span></div>
        <div class="item-meta">${meta('Target titles: '+((active.profile||{}).job_titles||[]).join(', '))}${meta((((active.profile||{}).skills)||[]).length+' skills')}${meta('Experience: '+((active.profile||{}).experience_years??0)+' yrs')}${meta('Graduation: '+((active.profile||{}).graduation_year||'—'))}</div>`
        :'<div class="banner warn">No active resume. Upload one below; job ranking currently uses your job preferences only.</div>'}
    </div>
    <div class="panel section-space">
      <div class="panel-head"><h3 class="panel-title">All resumes</h3><span class="panel-kicker">${resumes.length} uploaded</span></div>
      ${resumes.length?`<div class="resume-list">${resumes.map(r=>{
        const prof=r.profile||{};
        return `<div class="resume-row">
          <input type="radio" name="active-resume" data-action="activate-resume" data-id="${r.id}" ${r.is_active?'checked':''} ${r.status!=='processed'?'disabled':''} aria-label="Make ${esc(r.label)} active">
          <div style="min-width:0"><b>${esc(r.label)}</b> ${r.is_active?'<span class="badge active">active</span>':''} ${badge(r.status||'processed')}
            <div class="item-meta">${meta(r.filename||'no file')}${meta('uploaded '+fmtDate(r.created_at))}${r.file_size?meta(Math.round(r.file_size/1024)+' KB'):''}${meta((prof.skills||[]).length+' skills')}${(prof.job_titles||[]).length?meta(prof.job_titles.join(', ')):''}</div>
            ${r.error?`<div class="warning-line">Extraction error: ${esc(r.error)}</div>`:''}
          </div>
          <div class="item-actions">
            <button class="link-button" data-action="resume-edit" data-id="${r.id}">${editing&&editing.id===r.id?'Close':'Edit profile'}</button>
            <button class="link-button" data-action="resume-rename" data-id="${r.id}" data-label="${esc(r.label)}">Rename</button>
            <button class="link-button" data-action="resume-reprocess" data-id="${r.id}" title="Re-extract from the stored file">Reprocess</button>
            <button class="link-button" data-action="resume-replace" data-id="${r.id}">Replace file</button>
            <button class="link-button danger" data-action="resume-delete" data-id="${r.id}" data-label="${esc(r.label)}">Delete</button>
          </div></div>`;}).join('')}</div>`:'<div class="empty-state">No resumes yet.</div>'}
      <div class="upload-box section-space">
        <div class="inline-form" style="width:min(560px,100%)"><input class="input" id="resume-label" placeholder="Label for the next upload or rename, e.g. “AI Engineer” or “Backend SDE”"><label class="check-row"><input type="checkbox" id="resume-default" checked> make active</label></div>
        <button class="quiet-button" type="button" data-action="resume-pick">Choose PDF or DOCX…</button>
        <div class="view-note">Extraction uses your local Ollama model when available and a deterministic parser otherwise. Errors are shown here, never hidden.</div>
      </div>
    </div>
    ${editing?`<div class="panel section-space"><div class="panel-head"><h3 class="panel-title">Edit extracted profile — ${esc(editing.label)}</h3><span class="panel-kicker">one item per line</span></div>${profileEditor(editing)}</div>`:''}`;
}

function appearancePanel(){
  const current=document.documentElement.dataset.theme||'minimal-light';
  return `<div class="panel">
    <div class="panel-head"><h3 class="panel-title">Appearance</h3><span class="panel-kicker">saved across restarts</span></div>
    <div class="theme-options">${THEMES.map(t=>`<button class="theme-option ${current===t.id?'active':''}" data-action="set-theme" data-theme="${t.id}" aria-pressed="${current===t.id}">
      <span class="theme-swatch">${t.swatch.map(c=>`<i style="background:${c}"></i>`).join('')}</span><b>${esc(t.label)}</b></button>`).join('')}</div>
  </div>`;
}
function sourcesPanel(prefs){
  const jobs=prefs.jobs||{};
  const companies=D().companies||[];
  const scanAll=((prefs.scan_all||{}).categories)||['jobs','government','exams','news','papers'];
  return `<div class="panel section-space">
    <div class="panel-head"><h3 class="panel-title">Search sources & coverage</h3><span class="panel-kicker">jobs discovery</span></div>
    <form data-form="sources">
      <div class="settings-grid">
        <div class="field"><label>Default candidate pool</label><select class="select" name="pool_size">${[50,100,200].map(n=>`<option value="${n}" ${Number(jobs.pool_size||100)===n?'selected':''}>${n} candidates</option>`).join('')}</select><small>About 3, 6 or 10 web searches plus company boards. Larger pools take longer.</small></div>
        <div class="field"><label>Scan all includes</label><div class="chips">${['jobs','government','exams','news','papers'].map(c=>`<label class="chip"><input type="checkbox" name="scan:${c}" ${scanAll.includes(c)?'checked':''}> ${c}</label>`).join('')}</div></div>
        <div class="field full"><label>Company career boards (one per line: ats slug Display name)</label>
          <textarea class="textarea mono" name="companies" rows="8">${esc(companies.map(c=>`${c.ats} ${c.slug} ${c.name}`).join('\n'))}</textarea>
          <small>Supported: greenhouse, lever, ashby. Public job-board APIs are read directly (idea from the MIT-licensed Career-Ops project); only the company identifier is sent.</small></div>
      </div>
      <div class="field-actions"><button class="primary-button" type="submit">Save sources</button></div>
    </form>
  </div>`;
}


/* --------------------------------------------------------------- startups */
const SIGNAL_LABEL={funding:'Funding',hiring:'Hiring announcement',launch:'Product launch',product_launch:'Product launch',expansion:'Expansion',office:'New office',acquisition:'Acquisition',team:'New team'};
function viewStartups(){
  const emps=(D().employers||[]).filter(e=>!(e.discovery_sources||[]).includes('built-in verified board list')||state.filters.startups.builtin);
  const all=D().employers||[];
  const signals=D().signals||[];
  const f=state.filters.startups;
  const last=D().employer_search;
  const jobsByEmp={};(D().jobs||[]).forEach(j=>{if(j.employer_id!=null&&!SEARCH_KINDS.has(j.source_kind)&&tierOf(j)!=='excluded')(jobsByEmp[j.employer_id]=jobsByEmp[j.employer_id]||[]).push(j);});
  const list=emps.filter(e=>{
    if(f.kind==='startup'&&e.classification!=='startup')return false;
    if(f.kind==='india'&&e.country!=='India')return false;
    if(f.kind==='careers'&&!e.career_url&&!e.ats_provider)return false;
    if(f.kind==='jobs'&&!(jobsByEmp[e.id]||[]).length&&!e.open_jobs)return false;
    if(f.q&&!`${e.name} ${e.website||''} ${e.industry||''}`.toLowerCase().includes(f.q.toLowerCase()))return false;
    return true;
  }).sort((a,b)=>String(b.last_discovery||'').localeCompare(String(a.last_discovery||'')));
  const news=(D().news||[]).filter(n=>String(n.region||'')==='India'&&/funding|hiring|product|startup/i.test(String(n.topic||'')));
  const newSince=D().last_visit;
  const stat=(label,value)=>statCard(label,value);
  const events=D().signal_events||signals.map(s=>({...s,sources:[{url:s.source_url,publisher:s.publisher}],source_count:1}));
  const sigFiltered=events.filter(s=>!f.signal||s.signal_type===f.signal);
  const sigTypes=Array.from(new Set(events.map(s=>s.signal_type)));
  const outcomes=counted(all.filter(e=>e.career_outcome),e=>(e.career_discovery||{}).outcome_label||e.career_outcome);
  return heading('Jobs','Indian startup intelligence',
    'Employers discovered dynamically from startup publications, directories and accelerators, VC portfolios and job platforms. Each company’s website, career page and public job board are found from links that actually exist — never guessed. Funding and hiring news are <b>signals</b>, kept apart from vacancies.',
    '') + progressBox() +
    `<div class="toolbar"><form data-form="employers">
      <input class="input" name="request" placeholder="e.g. “Indian AI startups”, “recently funded fintech startups Bengaluru”, “Sarvam AI”" value="${esc(state.lastQuery.employers||'')}">
      <input class="input" name="topic" style="width:140px" placeholder="Topic (AI)" value="${esc(state.lastQuery.employerTopic||'')}">
      <select class="select" name="search_calls" title="Search budget">${[[4,'4 searches'],[6,'6 searches'],[10,'10 searches']].map(([n,l])=>`<option value="${n}" ${n===6?'selected':''}>${l}</option>`).join('')}</select>
      <button class="primary-button" type="submit">${icon('search')} Discover employers</button>
      <button class="quiet-button" type="button" data-action="rediscover-due" title="Re-run career-page discovery for employers whose retry time has come">Re-check career pages</button>
    </form><div class="view-note" style="margin-top:6px">The search budget is the number of web searches; more searches find more companies but use more of the free-tier quota.</div></div>
    <div class="grid grid-3 section-space">
      ${stat('Employers discovered',all.filter(e=>!(e.discovery_sources||[]).includes('built-in verified board list')).length)}
      ${stat('Startups',all.filter(e=>e.classification==='startup').length)}
      ${stat('Based in India',all.filter(e=>e.country==='India').length)}
      ${stat('Career pages found',all.filter(e=>e.career_url).length)}
      ${stat('Readable public job boards',all.filter(e=>e.ats_slug).length)}
      ${stat('Signal events (articles clustered)',`${events.length} <span class="view-note">from ${signals.length} articles</span>`)}
    </div>
    ${outcomes.length?`<div class="filter-row section-space"><span class="filter-label">Career discovery</span>${outcomes.map(([k,n])=>`<span class="chip">${esc(k)} <span class="chip-count">${n}</span></span>`).join('')}</div>`:''}
    ${last?employerCoverage(last):''}
    <div class="grid grid-2 section-space">
      <div class="panel">
        <div class="panel-head"><h3 class="panel-title">Signals</h3><span class="panel-kicker">not vacancies</span></div>
        <div class="view-note">Several articles about the same funding round or announcement count as one event. Funding and hiring news are not vacancies.</div>
        <div class="filter-row"><button class="chip ${!f.signal?'active':''}" data-action="startup-signal" data-value="">All <span class="chip-count">${events.length}</span></button>${sigTypes.map(t=>`<button class="chip ${f.signal===t?'active':''}" data-action="startup-signal" data-value="${esc(t)}">${esc(SIGNAL_LABEL[t]||t)} <span class="chip-count">${events.filter(s=>s.signal_type===t).length}</span></button>`).join('')}</div>
        ${sigFiltered.length?`<div class="source-list">${sigFiltered.slice(0,30).map(s=>{const src=(s.sources||[]);return `<div class="source-card">
          <div class="market-recent-head"><a class="source-title" href="${esc((src[0]||{}).url||s.source_url||'#')}" target="_blank" rel="noopener">${esc(s.title||s.company_name)}</a><span class="dim sig">${esc(SIGNAL_LABEL[s.signal_type]||s.signal_type)}</span></div>
          <div class="item-meta">${meta(s.company_name)}${s.amount?meta(s.amount):''}${meta(s.signal_date?fmtDate(s.signal_date):'date not stated')}${src.length>1?meta(src.length+' articles'):''}</div>
          ${src.length?`<div class="view-note">${src.slice(0,5).map(x=>`<a href="${esc(x.url)}" target="_blank" rel="noopener">${esc(x.publisher||hostOf(x.url))}</a>`).join(' · ')}</div>`:''}
        </div>`;}).join('')}</div>`:'<div class="empty-state">No signals yet. Run “Discover employers”.</div>'}
      </div>
      <div class="panel">
        <div class="panel-head"><h3 class="panel-title">Indian startup news</h3><span class="panel-kicker">funding · hiring · launches</span></div>
        ${news.length?`<div class="source-list">${news.slice(0,12).map(n=>`<div class="source-card"><a class="source-title" href="${esc(n.original_url)}" target="_blank" rel="noopener">${esc(n.title)}</a><div class="item-meta">${meta(n.publisher||'')}${meta(n.topic||'')}${n.published_date?meta(fmtDate(n.published_date)):''}</div></div>`).join('')}</div>`
          :`<div class="empty-state">No Indian startup stories stored. <button class="link-button" data-action="startup-news">Search Indian startup funding news</button></div>`}
      </div>
    </div>
    <div class="panel section-space">
      <div class="panel-head"><h3 class="panel-title">Employers</h3><span class="panel-kicker">${list.length} shown</span></div>
      <div class="filter-row" style="margin-top:0">
        ${[['','All'],['startup','Startups'],['india','India'],['careers','Career page / job board'],['jobs','With vacancies']].map(([v,l])=>`<button class="chip ${(f.kind||'')===v?'active':''}" data-action="startup-kind" data-value="${v}">${l}</button>`).join('')}
        <label class="chip"><input type="checkbox" data-filter-check="startups-builtin" ${f.builtin?'checked':''}> include built-in boards</label>
        <span class="filter-gap"></span><input class="input" style="width:200px" data-action="startup-q" placeholder="Filter companies…" value="${esc(f.q||'')}">
      </div>
      ${list.length?`<div class="table-wrap"><table class="data-table employer-table"><thead><tr><th>Company</th><th>Type</th><th>Career page / job system</th><th class="num">Vacancies</th><th>Signals</th><th>Discovered via</th><th>Last check</th></tr></thead><tbody>
      ${list.slice(0,f.all?list.length:60).map(e=>{const jobs=jobsByEmp[e.id]||[];const funding=(e.funding||[])[0];
        return `<tr><td><b>${e.website?`<a href="${esc(e.website)}" target="_blank" rel="noopener">${esc(e.name)}</a>`:esc(e.name)}</b>${newSince&&e.first_discovered>newSince?' <span class="badge new">new</span>':''}${e.industry?`<div class="view-note">${esc(e.industry)}</div>`:''}</td>
          <td>${esc(e.classification||'unknown')}${e.country?' · '+esc(e.country):''}</td>
          <td>${e.career_url?`<a href="${esc(e.career_url)}" target="_blank" rel="noopener">career page</a>`:''}${e.ats_provider?`${e.career_url?' · ':''}${esc(e.ats_provider)}${e.ats_slug?' (readable)':''}`:''}<div class="view-note">${esc(e.career_status||'')}</div>${careerDiscoveryCell(e)}</td>
          <td class="num">${jobs.length?`<button class="link-button" data-action="startup-jobs" data-name="${esc(e.name)}">${jobs.length} stored</button>`:''}${e.open_jobs?`<div class="view-note">${esc(e.open_jobs)} on board</div>`:''}${!jobs.length&&!e.open_jobs?'–':''}</td>
          <td>${e.signal_count?esc(e.signal_count):''}${funding?`<div class="view-note">${esc(funding.amount||funding.title||'funding')}</div>`:''}</td>
          <td class="view-note">${esc((e.discovery_sources||[]).filter(s=>!s.startsWith('category:')).slice(0,2).join(', '))}</td>
          <td class="view-note">${esc(fmtDate(e.last_career_check||e.last_discovery))}</td></tr>`;}).join('')}
      </tbody></table></div>${list.length>60&&!f.all?'<button class="link-button section-space" data-action="startup-all">Show all '+list.length+'</button>':''}`
      :emptyRich('No employers discovered yet','Run “Discover employers”. The engine searches startup publications (YourStory, Inc42, Entrackr…), directories and accelerators (Startup India, YC, Techstars…), VC portfolios and job platforms, then resolves each company’s website, career page and job board.','')}
    </div>
    ${last&&(last.career_listings||[]).length?`<div class="panel section-space"><div class="panel-head"><h3 class="panel-title">Vacancy links found on career pages</h3><span class="panel-kicker">last discovery · not yet ranked</span></div>
      <div class="source-list">${last.career_listings.slice(0,30).map(l=>`<div class="source-card"><a class="source-title" href="${esc(l.url)}" target="_blank" rel="noopener">${esc(l.title||l.url)}</a><div class="item-meta">${meta(l.employer)}</div></div>`).join('')}</div>
      <div class="view-note">Run “Discover jobs” with “startups” in the request to fetch, rank and store these against your resume.</div></div>`:''}`;
}
function careerDiscoveryCell(e){
  const d=e.career_discovery;
  if(!d&&!e.website)return '';
  const open=state.expanded['cd-'+e.id];
  const methods=(d&&d.methods)||[];
  return `<div class="view-note">${d?`${esc(methods.length)} method(s) tried${d.last_method?' · last success: '+esc(d.last_method):''}${d.next_retry_at?' · next check '+esc(fmtDate(d.next_retry_at)):''}`:'career discovery not run yet'}
    ${d?`<button class="link-button" data-action="expand" data-key="cd-${e.id}">${open?'hide':'details'}</button>`:''}${e.website?`<button class="link-button" data-action="rediscover" data-id="${e.id}">re-check</button>`:''}</div>
    ${open?`<div class="table-wrap"><table class="data-table"><tbody>${methods.map(m=>`<tr><td>${esc(m.stage)}</td><td>${esc(m.method)}</td><td class="${stateClass(m.state)}">${esc((m.state||'').replace(/_/g,' '))}</td><td class="view-note">${esc(m.detail||'')}</td></tr>`).join('')}</tbody></table></div>`:''}`;
}
function employerCoverage(s){
  return `<details class="collapsible section-space" ${state.expanded.empcov?'open':''} data-details="empcov"><summary>Last employer discovery${s.via?' (inside a job search)':''}: ${esc(s.results??0)} search results → ${esc(s.companies_found??0)} companies → ${esc(s.with_website??0)} websites → ${esc(s.with_career_page??0)} career pages → ${esc(s.ats_readable??0)} readable job boards <span class="view-note">· ${esc(fmtDateTime(s.created_at))}${s.duration_seconds?' · '+esc(s.duration_seconds)+'s':''}${s.new_employers!=null?' · '+esc(s.new_employers)+' new employers, '+esc(s.signals_saved??0)+' signals':''}</span></summary>
    <div class="table-wrap"><table class="data-table"><thead><tr><th>Source category</th><th>Queries</th><th class="num">Results</th><th>Publishers returned</th><th>Status</th></tr></thead><tbody>
    ${(s.coverage||[]).map(c=>`<tr><td>${esc(c.source)}</td><td class="view-note">${esc((c.queries||[]).join(' | '))}</td><td class="num">${esc(c.results??0)}</td><td class="view-note">${esc((c.domains||[]).slice(0,6).join(', '))}</td><td class="${c.results?'status-ok':/fail/.test(c.status||'')?'status-bad':'status-warn'}">${esc(c.status||'')}</td></tr>`).join('')}
    </tbody></table></div>
    ${(s.failures||[]).length?`<div class="banner warn section-space">${s.failures.slice(0,8).map(esc).join('<br>')}</div>`:''}
  </details>`;
}

/* ------------------------------------------------------------- briefing v2 */
function actionableBriefing(a){
  const sections=(a.sections||[]);
  const total=a.total_new||0;
  return `<div class="banner section-space">${total?`${esc(total)} new item${total===1?'':'s'} since the previous briefing`:'Nothing new since the previous briefing'}${a.since?` (${esc(fmtDateTime(a.since))})`:''}. Older items that are still relevant are counted, not repeated. Closed and expired listings are never suggested.</div>
  <div class="briefing-grid section-space">${sections.map(s=>`<div class="panel brief-${esc(s.key)}">
    <div class="panel-head"><h3 class="panel-title">${esc(s.title)}</h3><span class="panel-kicker">${s.new_count?`<span class="badge new">${esc(s.new_count)} new</span>`:''}${s.still_relevant?` +${esc(s.still_relevant)} earlier`:''}</span></div>
    ${s.note?`<div class="view-note">${esc(s.note)}</div>`:''}
    ${(s.items||[]).length?`<div class="brief-list">${s.items.map(i=>`<div class="brief-item">${i.url?`<a href="${esc(i.url)}" target="_blank" rel="noopener">${esc(i.title||'item')}</a>`:`<b>${esc(i.title||'item')}</b>`}${i.detail?`<div class="view-note">${esc(i.detail)}</div>`:''}</div>`).join('')}</div>`:'<div class="empty-state">Nothing new.</div>'}
  </div>`).join('')}</div>`;
}

/* --------------------------------------------------------- skills market v2 */
function datasetPanel(market){
  const d=market.dataset||{};
  if(!d.unique_listings)return '';
  return `<div class="banner section-space"><b>Observations from the listings this app has discovered — not a complete picture of the Indian job market.</b>
    ${esc(d.unique_listings)} unique listings${d.duplicates_removed?` (${esc(d.duplicates_removed)} duplicates removed)`:''} · ${esc(d.unique_employers)} employers named${d.listings_without_employer?` (${esc(d.listings_without_employer)} listings don’t name one)`:''} · ${esc(d.unique_sources)} sources · ${esc(d.reliable_dates)} with a reliable posting date${d.date_from?` · posted ${esc(fmtDate(d.date_from))} – ${esc(fmtDate(d.date_to))}`:''}.
    ${(d.geography||[]).length?`<div class="view-note" style="margin-top:4px">Geography: ${d.geography.map(g=>`${esc(g.name)} ${esc(g.count)}`).join(' · ')}</div>`:''}</div>`;
}
function trendLines(trend){
  trend=(trend||[]).filter(t=>(t.weeks||[]).some(w=>w.count));
  if(!trend.length)return '<div class="empty-state">Not enough dated listings to show changes over time.</div>';
  return `<div class="table-wrap"><table class="data-table trend-table"><thead><tr><th>Skill</th>${trend[0].weeks.map(w=>`<th class="num">${esc(new Date(w.week).toLocaleDateString(undefined,{month:'short',day:'numeric'}))}</th>`).join('')}</tr></thead>
    <tbody>${trend.map(t=>{const max=Math.max(1,...t.weeks.map(w=>w.count));return `<tr><th scope="row">${esc(t.skill)}</th>${t.weeks.map(w=>`<td class="num"><span class="heat-cell ${w.count/max>.6?'hot':''}" style="--heat:${w.count?Math.max(.15,w.count/max):0}" data-tip="${esc(t.skill)} · week of ${esc(w.week)}: ${w.count}">${w.count||''}</span></td>`).join('')}</tr>`;}).join('')}</tbody></table></div>
    <div class="view-note" style="margin-top:6px">Listings mentioning each skill, by posting week. Undated listings are left out.</div>`;
}
function marketV2(market){
  const gapNote=market.resume_complete===false?'<div class="banner warn">Your active resume looks incomplete (few skills extracted), so no skill gap is shown — a missing extraction is not a missing skill. Review it on the Resumes page.</div>':'';
  return `<div class="market-grid section-space">
      <div class="panel"><div class="panel-head"><h3 class="panel-title">Skills in newly discovered listings</h3><span class="panel-kicker">last 7 days</span></div>${barList(market.new_listing_skills,{empty:'No listings discovered in the last 7 days.'})}</div>
      <div class="panel"><div class="panel-head"><h3 class="panel-title">Changes over time</h3><span class="panel-kicker">top skills by week</span></div>${trendLines(market.skill_trend)}</div>
    </div>
    ${gapNote}
    <div class="panel section-space"><div class="panel-head"><h3 class="panel-title">Skills × location</h3><span class="panel-kicker">city-level, spelling variants merged</span></div>${heatmap({portals:(market.skills_by_location||{}).rows||[],skills:(market.skills_by_location||{}).skills||[],matrix:(market.skills_by_location||{}).matrix||[]},{rowLabel:'location',empty:'Not enough located listings.'})}</div>
    <div class="panel section-space"><div class="panel-head"><h3 class="panel-title">Skills × experience asked</h3><span class="panel-kicker">from each listing’s stated requirement</span></div>${heatmap({portals:(market.skills_by_experience||{}).rows||[],skills:(market.skills_by_experience||{}).skills||[],matrix:(market.skills_by_experience||{}).matrix||[]},{rowLabel:'experience',empty:'Not enough listings state experience.'})}</div>
    <div class="panel section-space"><div class="panel-head"><h3 class="panel-title">Employer-level skill demand</h3><span class="panel-kicker">named employers only</span></div>${heatmap({portals:(market.skills_by_employer||{}).rows||[],skills:(market.skills_by_employer||{}).skills||[],matrix:(market.skills_by_employer||{}).matrix||[]},{rowLabel:'employer',empty:'Too few listings name their employer.'})}</div>`;
}

const VIEWS={
  home:viewHome,
  sources:viewSources,
  'daily-briefing':viewBriefing,
  'ask-intelligence':viewAsk,
  research:viewResearch,
  jobs:viewJobs,
  'job-market':viewMarket,
  tracker:viewTracker,
  startups:viewStartups,
  resumes:viewResumes,
  government:viewGovernment,
  exams:viewExams,
  'ai-news':viewNews,
  papers:viewPapers,
  planning:viewPlanning,
  history:viewHistory,
  settings:viewSettings,
};


/* ------------------------------------------------------------------ home (v4) */
const FEED_SECTIONS=[['all','All'],['new','New'],['strong','Strong'],['good','Good'],['internship','Internships'],['fresher','Fresher'],
  ['remote','Remote'],['startup','Startups'],['product','Product cos'],['followed','Following'],['government','Government'],['exam','Exams'],['stretch','Stretch']];
function greeting(d=new Date()){const h=d.getHours();return h<5?'Good evening':h<12?'Good morning':h<17?'Good afternoon':'Good evening';}
function longDate(d=new Date()){return d.toLocaleDateString(undefined,{weekday:'long',day:'numeric',month:'long'});}
function F(){return state.feed||{items:[],summary:{},deadlines:[],news:[]};}
function homeStatus(f){
  const s=f.summary||{};
  if(!(f.items||[]).length)return 'Nothing discovered yet. Run Discover to build your feed from every enabled source.';
  const parts=[];
  if(s.strong_matches)parts.push(`${s.strong_matches} strong match${s.strong_matches===1?'':'es'}`);
  if(s.new_opportunities)parts.push(`${s.new_opportunities} new opportunit${s.new_opportunities===1?'y':'ies'}`);
  if(s.deadlines_14d)parts.push(`${s.deadlines_14d} deadline${s.deadlines_14d===1?'':'s'} in the next two weeks`);
  return parts.length?`${parts.join(', ').replace(/, ([^,]*)$/,' and $1')}. Here’s what matters today.`:'Here’s what matters today.';
}
function metric(label,value,hint,action){
  return `<button class="metric" ${action?`data-action="${action[0]}" data-value="${esc(action[1])}"`:'disabled'} title="${esc(hint||'')}"><span class="metric-value">${esc(value??0)}</span><span class="metric-label">${esc(label)}</span></button>`;
}
function feedFilter(){
  const f=state.filters.feed=state.filters.feed||{section:'all',q:'',fresh:'',elig:'',source:''};
  const q=(f.q||'').toLowerCase();
  return (F().items||[]).filter(i=>{
    if(f.section&&f.section!=='all'&&!(i.sections||[]).includes(f.section))return false;
    if(f.section==='all'&&i.tier==='ineligible')return false;
    if(f.fresh&&((i.freshness||{}).key||'')!==f.fresh&&!(f.fresh==='week'&&['new_today','new_24h','new_3d','new_7d'].includes((i.freshness||{}).key)))return false;
    if(f.elig&&i.eligibility!==f.elig)return false;
    if(f.source&&i.source_type!==f.source)return false;
    if(q&&!`${i.title} ${i.org||''} ${i.location||''} ${(i.matched||[]).join(' ')}`.toLowerCase().includes(q))return false;
    return true;
  });
}
function feedRow(i){
  const open=state.expanded['feed-'+i.kind+'-'+i.id];
  const fresh=i.freshness||{};
  const deadline=i.deadline_days!=null?`<span class="due ${i.deadline_days<=3?'due-soon':''}">${i.deadline_days===0?'due today':i.deadline_days+'d left'}</span>`:'';
  const score=i.kind==='job'?`<span class="feed-score ${esc(i.tier)}${i.eligibility==='uncertain'||i.confidence==='low'?' tentative':''}" title="Profile match${i.resume?' · '+esc(i.resume):''}">${i.match??'—'}</span>`
    :`<span class="feed-score kind">${i.kind==='exam'?'Exam':'Gov'}</span>`;
  const meta=[i.org,i.location,i.arrangement,i.kind==='exam'?(i.event||'').replace(/_/g,' '):null].filter(Boolean).map(esc).join(' · ');
  return `<article class="feed-row${open?' open':''}">
    ${score}
    <div class="feed-main">
      <button class="feed-title" data-action="expand" data-key="feed-${i.kind}-${i.id}">${esc(i.title||'Untitled')}</button>
      <div class="feed-meta">${meta}</div>
      <div class="feed-tags">${i.kind==='job'?`<span class="tag-elig elig-${esc(i.eligibility)}">${esc(i.eligibility_label||'')}</span>`:''}${fresh.label?`<span title="${esc(fresh.basis||'')}">${esc(fresh.label)}</span>`:''}${deadline}${i.state&&i.state!=='dismissed'?`<span class="tag-state">${esc(i.state)}</span>`:''}${(i.sections||[]).includes('followed')?'<span class="tag-state">following</span>':''}</div>
      ${open?feedDetail(i):''}
    </div>
    <div class="feed-actions">${i.url?`<a class="link-button" href="${esc(i.application_url||i.url)}" target="_blank" rel="noopener">Open</a>`:''}</div>
  </article>`;
}
function feedDetail(i){
  if(i.kind!=='job')return `<div class="feed-detail">${i.eligibility_label?`<div>Eligibility: ${esc(i.eligibility_label)}</div>`:''}<div class="item-actions">${i.url?`<a class="link-button" href="${esc(i.url)}" target="_blank" rel="noopener">Original notice</a>`:''}${i.application_url?`<a class="link-button" href="${esc(i.application_url)}" target="_blank" rel="noopener">Application page</a>`:''}</div></div>`;
  const current=stateOf('job',i.id);
  const reporting=state.expanded['report-'+i.id];
  return `<div class="feed-detail">
    <p class="why">${esc(i.why||'No explanation stored yet.')}</p>
    ${(i.matched||[]).length||(i.missing||[]).length?`<div class="skills">${(i.matched||[]).map(s=>`<span class="tag have">${esc(s)}</span>`).join('')}${(i.missing||[]).map(s=>`<span class="tag miss" title="Required, not on your resume">${esc(s)}</span>`).join('')}</div>`:''}
    <div class="feed-facts">${[(i.lifecycle||{}).label,i.posted?'posted '+fmtDate(i.posted):'posting date not stated',(i.freshness||{}).basis,i.sources>1?i.sources+' sources':null,i.source_type?'via '+i.source_type:null].filter(Boolean).map(esc).join(' · ')}</div>
    <div class="item-actions">
      ${i.url?`<a class="link-button" href="${esc(i.url)}" target="_blank" rel="noopener">Original listing</a>`:''}
      ${i.application_url&&i.application_url!==i.url?`<a class="link-button primary" href="${esc(i.application_url)}" target="_blank" rel="noopener">Application page</a>`:''}
      ${trackButtons(i.id,current)}
      ${i.employer_id!=null?`<button class="link-button" data-action="follow" data-id="${i.employer_id}" data-on="${(i.sections||[]).includes('followed')?0:1}">${(i.sections||[]).includes('followed')?'Unfollow':'Follow'} company</button>`:''}
      <button class="link-button" data-action="expand" data-key="report-${i.id}">Report inaccurate</button>
      <a class="link-button" href="#jobs" data-view="jobs" title="Full requirement breakdown on the Jobs page">Why this match?</a>
    </div>
    ${reporting?`<div class="report-row">${[['closed','No longer open'],['wrong_location','Wrong location'],['wrong_details','Wrong details'],['duplicate','Duplicate'],['not_a_job','Not a job'],['scam','Looks like a scam']].map(([v,l])=>`<button class="chip" data-action="report" data-id="${i.id}" data-reason="${v}">${l}</button>`).join('')}</div>`:''}
  </div>`;
}
function viewHome(){
  const f=F(),s=f.summary||{};
  const ff=state.filters.feed=state.filters.feed||{section:'all',q:'',fresh:'',elig:'',source:''};
  const items=feedFilter();
  const limit=state.expanded.feedall?items.length:25;
  const plan=(f.today_plan||D().today_plan||{});
  const priorities=((plan.counts||{}).today||0)+((plan.counts||{}).overdue||0);
  const disc=f.discovery;
  const counts=s.sections||{};
  return `<section class="home-head">
      <h1>${esc(greeting())}.</h1>
      <p class="home-date">${esc(longDate())}</p>
      <p class="home-status">${esc(homeStatus(f))}</p>
    </section>
    ${progressBox()}
    <section class="metrics" aria-label="Today at a glance">
      ${metric('New opportunities',s.new_opportunities,'Posted (or first seen) in the last 3 days',['feed-section','new'])}
      ${metric('Strong matches',s.strong_matches,'Eligible, mandatory skills met, fresh and well evidenced',['feed-section','strong'])}
      ${metric('Deadlines · 14 days',s.deadlines_14d,'Jobs, notices and exams with a date in the next 14 days',['feed-section','deadline'])}
      ${metric('Exam updates',s.exam_updates,'Exam events in the next 60 days',['feed-section','exam'])}
      ${metric('AI developments',(f.news||[]).length,'Recent AI stories',['go','ai-news'])}
      ${metric('Today’s priorities',priorities,'Tasks due today or overdue',['go','planning'])}
    </section>
    <div class="home-grid">
      <section class="feed" aria-label="Opportunity feed">
        <div class="feed-controls">
          <div class="feed-sections" role="tablist">${FEED_SECTIONS.filter(([k])=>k==='all'||counts[k]).map(([k,l])=>`<button class="seg ${ff.section===k?'active':''}" data-action="feed-section" data-value="${k}" role="tab" aria-selected="${ff.section===k}">${l}${k!=='all'&&counts[k]?` <span>${counts[k]}</span>`:''}</button>`).join('')}</div>
          <div class="feed-filters">
            <input class="input" data-action="feed-q" placeholder="Filter by role, skill, company, city…" value="${esc(ff.q||'')}">
            <select class="select" data-feed="fresh">${optionList([['week','Last 7 days'],['new_today','New today'],['new_24h','Last 24 hours'],['new_3d','Last 3 days'],['older_open','Older, still open'],['date_unknown','Date unknown'],['verification_required','Needs verification']],ff.fresh||'','Any freshness')}</select>
            <select class="select" data-feed="elig">${optionList([['eligible','Eligible'],['likely_eligible','Likely eligible'],['uncertain','Uncertain'],['not_eligible','Not eligible']],ff.elig||'','Any eligibility')}</select>
            <select class="select" data-feed="source">${optionList([['ats','Employer ATS'],['career','Career page'],['feed','Public feed'],['portal','Job portal'],['web','Web search']],ff.source||'','Any source')}</select>
          </div>
        </div>
        ${ff.section==='deadline'?deadlineList(f.deadlines||[]):
          items.length?`<div class="feed-list">${items.slice(0,limit).map(feedRow).join('')}</div>${items.length>limit?`<button class="link-button more" data-action="expand" data-key="feedall">Show all ${items.length}</button>`:''}`
          :`<div class="feed-empty">${(f.items||[]).length?'Nothing matches these filters.':'Your feed is empty.'} ${(f.items||[]).length?'<button class="link-button" data-action="feed-clear">Clear filters</button>':'<button class="discover-button" data-action="discover">Discover opportunities</button>'}</div>`}
      </section>
      <aside class="side-panels">
        <section class="mini"><h2>Deadlines</h2>${deadlineList((f.deadlines||[]).slice(0,5),true)}</section>
        <section class="mini"><h2>Today</h2>${[...(plan.schedule||[]),...(plan.suggestions||[])].slice(0,5).map(t=>`<div class="mini-row"><span>${t.url?`<a href="${esc(t.url)}" target="_blank" rel="noopener">${esc(t.title||'')}</a>`:esc(t.title||'')}</span><span class="mini-sub">${esc(t.time||t.detail||'')}</span></div>`).join('')||'<div class="mini-empty">Nothing scheduled for today.</div>'}<a class="link-button" href="#planning" data-view="planning">Plan</a></section>
        <section class="mini"><h2>AI developments</h2>${(f.news||[]).slice(0,4).map(n=>`<div class="mini-row"><a href="${esc(n.url)}" target="_blank" rel="noopener">${esc(n.title)}</a><span class="mini-sub">${esc(n.publisher||'')}</span></div>`).join('')||'<div class="mini-empty">No stories yet.</div>'}</section>
        ${(f.alerts||[]).length?`<section class="mini"><h2>Alerts</h2>${f.alerts.slice(0,5).map(a=>`<div class="mini-row"><a href="${esc(a.url||'#')}" target="_blank" rel="noopener">${esc(a.title)}</a><span class="mini-sub">${esc(a.score??'')}</span></div>`).join('')}<button class="link-button" data-action="alerts-read">Mark read</button></section>`:''}
        <section class="mini"><h2>Last discovery</h2>${disc?discoverySummary(disc):'<div class="mini-empty">Not run yet.</div>'}
          ${(f.automation||{}).daily_refresh?`<div class="mini-kv"><span>Daily discovery</span><b>${esc((f.automation||{}).refresh_time||'08:00')}</b></div>`:`<div class="mini-empty">Daily discovery is off. <button class="link-button" data-action="auto-on">Turn on</button></div>`}<a class="link-button" href="#sources" data-view="sources">Sources &amp; coverage</a></section>
      </aside>
    </div>`;
}
function deadlineList(list,compact){
  if(!list.length)return '<div class="mini-empty">No dated deadlines in the next two weeks.</div>';
  return list.map(i=>`<div class="mini-row"><span>${i.url?`<a href="${esc(i.url)}" target="_blank" rel="noopener">${esc(i.title)}</a>`:esc(i.title)}${compact?'':` <span class="mini-sub">${esc(i.org||'')}</span>`}</span><span class="due ${i.deadline_days<=3?'due-soon':''}">${i.deadline_days===0?'today':i.deadline_days+'d'}</span></div>`).join('');
}
function discoverySummary(d){
  const m=d.metrics||{};
  return `<div class="mini-row"><span>${esc(fmtDateTime(d.created_at))}</span><span class="mini-sub">${esc(d.mode||'')}</span></div>
    <div class="mini-kv"><span>Sources successful</span><b>${esc(m.sources_successful??0)} / ${esc(m.sources_attempted??0)}</b></div>
    <div class="mini-kv"><span>Partial · restricted</span><b>${esc(m.sources_partial??0)} · ${esc(m.sources_restricted??0)}</b></div>
    <div class="mini-kv"><span>Unique vacancies</span><b>${esc(m.unique_vacancies??0)}</b></div>
    <div class="mini-kv"><span>New stored</span><b>${esc(m.new_vacancies??0)}</b></div>`;
}

/* ----------------------------------------------------------- sources (v4) */
const RUN_STATE_CLASS={successful:'status-ok',partial:'status-warn',failed:'status-bad',access_restricted:'status-bad',not_attempted:'view-note',disabled:'view-note',backing_off:'status-warn',not_configured:'view-note'};
function viewSources(){
  const d=(state.feed||{}).discovery;
  const reg=state.sources||[];
  const m=(d||{}).metrics||{};
  const run=Object.fromEntries(((d||{}).sources||[]).map(s=>[s.id,s]));
  const cats=Array.from(new Set(reg.map(s=>s.category)));
  const cat=state.filters.sourcesCat||'';
  const rows=reg.filter(s=>!cat||s.category===cat);
  const metric2=(label,v)=>`<div class="mini-kv"><span>${esc(label)}</span><b>${esc(v??0)}</b></div>`;
  return heading('Workspace','Sources & coverage','Every source the discovery engine can use, what it is allowed to do, and what happened the last time it ran. A source counts as working only when it returned records.',
    `<button class="discover-button" data-action="discover">Discover now</button>`)+progressBox()+
    `<div class="grid grid-2 section-space">
      <div class="panel"><div class="panel-head"><h3 class="panel-title">Last discovery</h3><span class="panel-kicker">${d?esc(fmtDateTime(d.created_at))+' · '+esc(d.duration_seconds)+'s':'never'}</span></div>
        ${d?`${metric2('Sources configured',m.sources_configured)}${metric2('Sources attempted',m.sources_attempted)}${metric2('Successful',m.sources_successful)}${metric2('Partially successful',m.sources_partial)}${metric2('Failed or access restricted',m.sources_restricted)}`:'<div class="mini-empty">Run Discover to populate this.</div>'}
      </div>
      <div class="panel"><div class="panel-head"><h3 class="panel-title">What came back</h3><span class="panel-kicker">each line counts a different thing</span></div>
        ${d?`${metric2('Search results (leads, not vacancies)',m.search_results)}${metric2('Career pages discovered',m.career_pages_discovered)}${metric2('ATS boards read',m.ats_boards_read)}${metric2('Raw vacancy records',m.raw_vacancy_records)}${metric2('Unique vacancies after deduplication',m.unique_vacancies)}${metric2('Relevant to your resume',m.relevant_vacancies)}${metric2('Stored this run',m.stored_vacancies)}${metric2('New this run',m.new_vacancies)}${metric2('…verified open on employer systems',m.new_verified_open)}${metric2('…awaiting verification',m.new_awaiting_verification)}${metric2('…closed or expired',m.new_closed_or_expired)}${metric2('Removed from employer boards (closed)',m.board_removals_detected)}`:''}
      </div>
    </div>
    <div class="panel section-space">
      <div class="panel-head"><h3 class="panel-title">Source registry</h3><span class="panel-kicker">${reg.length} sources</span></div>
      <div class="filter-row" style="margin-top:0"><button class="chip ${!cat?'active':''}" data-action="sources-cat" data-value="">All</button>${cats.map(c=>`<button class="chip ${cat===c?'active':''}" data-action="sources-cat" data-value="${esc(c)}">${esc(CATEGORY_LABEL[c]||c.replace(/_/g,' '))}</button>`).join('')}</div>
      <div class="table-wrap"><table class="data-table"><thead><tr><th>Source</th><th>Method</th><th>Last run</th><th class="num">Results</th><th class="num">Reliability</th><th>Last success</th><th>Restrictions · alternative</th><th></th></tr></thead><tbody>
      ${rows.map(s=>{const r=run[s.id]||{};const st=r.state||(s.enabled?'not_attempted':'disabled');return `<tr>
        <td><b>${esc(s.name)}</b><div class="view-note">${esc(s.geography)} · ${esc(s.pagination)}</div></td>
        <td class="view-note">${esc(s.method)}</td>
        <td class="${RUN_STATE_CLASS[st]||''}">${esc(r.state_label||st.replace(/_/g,' '))}${r.reason?`<div class="view-note">${esc(r.reason)}</div>`:''}</td>
        <td class="num">${esc((r.results||0)+(r.listings||0)||'–')}</td>
        <td class="num">${s.reliability!=null?esc(s.reliability)+'%':'–'}</td>
        <td class="view-note">${s.last_success_at?esc(fmtDateTime(s.last_success_at)):'never'}${s.next_attempt_at?`<div class="status-warn">retry after ${esc(fmtDateTime(s.next_attempt_at))}</div>`:''}</td>
        <td class="view-note">${esc(s.access)}${s.alternative?`<div>${esc(s.alternative)}</div>`:''}</td>
        <td><button class="link-button" data-action="source-toggle" data-id="${esc(s.id)}" data-on="${s.enabled?0:1}">${s.enabled?'Disable':'Enable'}</button></td></tr>`;}).join('')}
      </tbody></table></div>
    </div>`;
}

/* ---------------------------------------------------------- command palette */
function paletteItems(q){
  const items=[];const t=q.trim();
  items.push({label:'Discover opportunities',hint:'Run every enabled source',run:()=>startJobRequest('/api/discover',{},'Discovering opportunities')});
  if(t){
    items.push({label:`Search roles: “${t}”`,hint:'Targeted discovery with the same engine',run:()=>startJobRequest('/api/discover',{query:t},'Searching '+t)});
    items.push({label:`Filter feed: “${t}”`,hint:'Narrow what is already stored',run:()=>{(state.filters.feed=state.filters.feed||{}).q=t;setView('home');}});
    items.push({label:`Ask: “${t}”`,hint:'Research with sources',run:()=>{state.askPrefill=t;setView('ask-intelligence');}});
  }
  const lower=t.toLowerCase();
  NAV.forEach(n=>{if(!t||n.label.toLowerCase().includes(lower))items.push({label:'Go to '+n.label,hint:'',run:()=>setView(n.id)});});
  if(t){
    (F().items||[]).filter(i=>`${i.title} ${i.org||''}`.toLowerCase().includes(lower)).slice(0,6).forEach(i=>
      items.push({label:i.title,hint:[i.org,i.state].filter(Boolean).join(' · '),run:()=>{state.expanded['feed-'+i.kind+'-'+i.id]=true;(state.filters.feed=state.filters.feed||{}).q=t;setView('home');}}));
  }else{
    (F().items||[]).filter(i=>['saved','applied','interview'].includes(i.state)).slice(0,5).forEach(i=>
      items.push({label:i.title,hint:i.state,run:()=>{state.expanded['feed-'+i.kind+'-'+i.id]=true;setView('home');}}));
    (F().deadlines||[]).slice(0,3).forEach(i=>items.push({label:`Deadline: ${i.title}`,hint:i.deadline_days+' days',run:()=>{(state.filters.feed=state.filters.feed||{}).section='all';setView('home');}}));
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

/* ------------------------------------------------------------------ events */
document.addEventListener('click',async event=>{
  const viewButton=event.target.closest('[data-view]');
  if(viewButton){event.preventDefault();setView(viewButton.dataset.view);return;}
  const button=event.target.closest('[data-action]');
  if(!button)return;
  const action=button.dataset.action;
  try{
    if(action==='discover'){await startJobRequest('/api/discover',{},'Discovering opportunities');}
    else if(action==='close-drawer'){openDrawer(false);}
    else if(action==='alerts-read'){await api('/api/alerts/read',{method:'POST',headers:{'Content-Type':'application/json'},body:'{}'});await refresh();render();}
    else if(action==='auto-on'){const prefs=JSON.parse(JSON.stringify(D().preferences||{}));prefs.automation={...(prefs.automation||{}),daily_refresh:true};
      await api('/api/preferences',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(prefs)});await refresh();render();toast('Daily discovery is on');}
    else if(action==='feed-section'){const f=state.filters.feed=state.filters.feed||{};f.section=button.dataset.value;state.expanded.feedall=false;render();}
    else if(action==='go'){setView(button.dataset.value);}
    else if(action==='feed-clear'){state.filters.feed={section:'all',q:'',fresh:'',elig:'',source:''};render();}
    else if(action==='follow'){await api(`/api/employers/${button.dataset.id}/follow`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({followed:button.dataset.on==='1'})});
      await refresh();render();toast(button.dataset.on==='1'?'Following this company':'Unfollowed');}
    else if(action==='report'){await api(`/api/listings/${button.dataset.id}/report`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({reason:button.dataset.reason})});
      await refresh();render();toast('Reported — hidden from your feed (kept in the database)');}
    else if(action==='sources-cat'){state.filters.sourcesCat=button.dataset.value;render();}
    else if(action==='source-toggle'){const r=await api(`/api/sources/${encodeURIComponent(button.dataset.id)}/enabled`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({enabled:button.dataset.on==='1'})});
      state.sources=r.sources||state.sources;render();}
    else if(action==='briefing'){await startJobRequest('/api/briefings',{},'Briefing started');}
    else if(action==='scan-all'){await startJobRequest('/api/search/scan-all',{},'Scanning all enabled sections');}
    else if(action==='discover-jobs'){await startJobRequest('/api/intel/search',{category:'jobs',query:state.lastQuery.jobs||'',pool_size:((D().preferences||{}).jobs||{}).pool_size||100},'Discovering jobs');}
    else if(action==='expand'){const k=button.dataset.key;state.expanded[k]=!state.expanded[k];render();}
    else if(action==='set-theme'){await setTheme(button.dataset.theme);render();}
    else if(action==='resume-reprocess'){
      toast('Re-extracting resume locally…');
      await api(`/api/resumes/${button.dataset.id}/reprocess`,{method:'POST',headers:{'Content-Type':'application/json'},body:'{}'});
      await refresh();render();toast('Resume reprocessed; jobs re-ranked');
    }

    else if(action==='cancel-job'){await cancelJob(button.dataset.id);}
    else if(action==='refresh'){await refresh();render();toast('Workspace refreshed');}
    else if(action==='item-state'){
      const next=button.dataset.state;
      await api('/api/items/state',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({kind:button.dataset.kind,id:Number(button.dataset.id),state:next})});
      if(button.dataset.kind==='job'){await refresh();}
      else{
        const map=state.data.item_states=state.data.item_states||{};
        map[button.dataset.kind]=map[button.dataset.kind]||{};
        if(next==='none')delete map[button.dataset.kind][button.dataset.id];else map[button.dataset.kind][button.dataset.id]=next;
      }
      render();toast(next==='none'?'State cleared':next==='applied'?'Marked applied — follow-up task added for next week':'Marked '+next);
    }
    else if(action==='quick-search'){
      const category=button.dataset.category||'jobs';
      const query=button.dataset.query||'';
      state.lastQuery[category]=query;
      const body={category,query,freshness:(state.filters[category]||{}).freshness};
      if(category==='news'){
        body.region=state.filters.news.region||'';
        body.topic=state.filters.news.topic||'';
      }
      await startJobRequest('/api/intel/search',body,'Searching '+CATEGORY_META[category].label);
    }
    else if(action==='market-scan'){
      state.lastQuery.jobs='';
      await startJobRequest('/api/intel/search',{category:'jobs',query:'',scan:true,pool_size:200},'Scanning the job market across your scan roles');
    }
    else if(action==='news-search'){
      const f=state.filters.news;
      await startJobRequest('/api/intel/search',{category:'news',query:state.lastQuery.news||'',freshness:f.freshness,region:f.region&&f.region!=='Global'?f.region:(f.region==='Global'?'Global':''),topic:f.topic||''},'Searching news');
    }
    else if(action==='job-role'){state.filters.jobs.role=button.dataset.value||'';render();}
    else if(action==='job-resume'){state.filters.jobs.resume=button.dataset.value||'';render();}
    else if(action==='job-layout'){state.filters.jobs.layout=button.dataset.value;render();}
    else if(action==='tailor'){
      const id=Number(button.dataset.id);
      if(state.tailor[id]&&!state.tailor[id].loading){delete state.tailor[id];render();return;}
      state.tailor[id]={loading:true};render();
      try{state.tailor[id]=await api('/api/listings/'+id+'/tailor',{method:'POST',headers:{'Content-Type':'application/json'},body:'{}'});}
      catch(err){delete state.tailor[id];toast(err.message,true);}
      render();
    }
    else if(action==='delete-task'){
      await api('/api/tasks/'+button.dataset.id+'/delete',{method:'POST',headers:{'Content-Type':'application/json'},body:'{}'});
      await refresh();render();
    }
    else if(action==='open-note'){
      state.note=await api('/api/notes/'+encodeURIComponent(button.dataset.name));render();
    }
    else if(action==='new-note'){state.note={name:'plan.txt',content:'',isNew:true};render();}
    else if(action==='close-note'){state.note=null;render();}
    else if(action==='interpret-notes'){
      toast('Asking your local model…');
      const data=await api('/api/planning/interpret',{method:'POST',headers:{'Content-Type':'application/json'},body:'{}'});
      state.suggestions={items:data.suggestions||[],source:data.source};render();
    }
    else if(action==='add-suggestion'){
      const s=state.suggestions.items[Number(button.dataset.index)];
      await api('/api/tasks',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(s)});
      state.suggestions.items.splice(Number(button.dataset.index),1);
      await refresh();render();toast('Task added');
    }
    else if(action==='activate-resume'){
      await api(`/api/resumes/${button.dataset.id}/activate`,{method:'POST',headers:{'Content-Type':'application/json'},body:'{}'});
      await refresh();render();toast('Active resume changed; jobs re-ranked');
    }
    else if(action==='resume-default'||action==='resume-delete'||action==='resume-rename'){
      const id=button.dataset.id;let body={};let verb=action.replace('resume-','');
      if(action==='resume-delete'){
        if(state.confirmDelete!==id){state.confirmDelete=id;toast(`Click Delete again to remove “${button.dataset.label}”`);setTimeout(()=>{if(state.confirmDelete===id)state.confirmDelete=null;},5000);return;}
        state.confirmDelete=null;
      }
      if(action==='resume-rename'){
        const input=$('#resume-label');const label=(input&&input.value.trim())||'';
        if(!label){toast('Type the new name in the label box below, then click Rename',true);input&&input.focus();return;}
        body={label};verb='label';
      }
      await api(`/api/resumes/${id}/${verb}`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});
      await refresh();render();toast('Resumes updated');
    }
    else if(action==='resume-edit'){
      const id=Number(button.dataset.id);state.editResume=state.editResume===id?null:id;render();
    }
    else if(action==='resume-replace'){state.replaceResume=Number(button.dataset.id);$('#resume-file')?.click();}
    else if(action==='job-filter'){
      state.filters.jobs.status=button.dataset.value;render();
    }
    else if(action==='job-recency'){
      state.filters.jobs.recency=button.dataset.value;render();
    }
    else if(action==='news-region'){
      state.filters.news.region=button.dataset.value||'';render();
    }
    else if(action==='news-topic'){
      state.filters.news.topic=button.dataset.value||'';render();
    }
    else if(action==='planning-refresh'){
      const data=await api('/api/planning/refresh',{method:'POST',headers:{'Content-Type':'application/json'},body:'{}'});
      await refresh();
      render();
      toast(`Imported ${data.planning.tasks_found} task(s) from ${data.planning.files.length} note file(s)`);
    }
    else if(action==='toggle-task'){
      await api('/api/tasks/'+button.dataset.id+'/toggle',{method:'POST',headers:{'Content-Type':'application/json'},body:'{}'});
      await refresh();render();
    }
    else if(action==='remove-watch'){
      const kind=button.dataset.kind,name=button.dataset.name;
      await api(kind==='exam'?'/api/exams/watchlist':'/api/organizations/watchlist',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({name,remove:true})});
      await refresh();render();toast('Removed from watchlist');
    }
    else if(action==='load-models'){
      const data=await api('/api/models');state.models=data.models||[];render();toast('Installed models reloaded');
    }
    else if(action==='diagnostics'){await startJobRequest('/api/diagnostics/mcp',{},'Running MCP diagnostic');}
    else if(action==='fill-request'){
      const area=document.querySelector('form[data-form="research"] textarea[name="request"]');
      if(area){area.value=button.dataset.text||'';area.focus();}
    }
    else if(action==='resume-pick'){$('#resume-file')?.click();}
    else if(action==='save-profile'){await saveProfile();}
    else if(action==='export'){await exportData();}
    else if(action==='clear-intel'){
      if(!confirm('Clear all discovered jobs, notices, exam events, news, papers, sessions and saved states? Tasks, history, briefings and preferences are kept.'))return;
      await api('/api/data/clear-intel',{method:'POST',headers:{'Content-Type':'application/json'},body:'{}'});
      await refresh();render();toast('Discovered intelligence cleared');
    }
    else if(action==='load-exclusions'){
      const reason=button.dataset.reason,session=button.dataset.session;
      state.exclusions={reason,loading:true};render();
      try{const r=await api(`/api/sources/exclusions?session=${encodeURIComponent(session)}&reason=${encodeURIComponent(reason)}`);
        state.exclusions={reason,items:r.items||[],total:r.total};}
      catch(err){state.exclusions={reason,items:[],total:0};toast(err.message||'Could not load exclusions',true);}
      render();
    }
    else if(action==='rediscover'){await startJobRequest('/api/employers/rediscover',{employer_ids:[Number(button.dataset.id)]},'Re-running career-page discovery');}
    else if(action==='rediscover-due'){await startJobRequest('/api/employers/rediscover',{limit:10},'Career-page discovery for employers that are due');}
    else if(action==='reverify'){await startJobRequest('/api/jobs/reverify',{limit:40},'Re-verifying saved and shortlisted listings');}
    else if(action==='reverify-one'){await startJobRequest('/api/jobs/reverify',{job_ids:[Number(button.dataset.id)]},'Re-verifying listing');}
    else if(action==='job-clear-filters'){
      const f=state.filters.jobs;['role','city','exp','employment','source','life','fresh','eligibility','minMatch','q'].forEach(k=>f[k]='');
      ['startup','tracked','verifiedRecent','intern','fresher','remote'].forEach(k=>f[k]=false);f.recency='all';render();
    }
    else if(action==='app-new'){state.editApp=state.editApp==='new'?null:'new';render();}
    else if(action==='app-edit'){const id=button.dataset.id==='new'?'new':Number(button.dataset.id);state.editApp=state.editApp===id?null:id;render();}
    else if(action==='app-filter'){state.filters.apps.status=button.dataset.value;render();}
    else if(action==='app-delete'){
      const id=button.dataset.id;
      if(state.confirmDelete!=='app'+id){state.confirmDelete='app'+id;toast('Click Delete again to remove this application record');setTimeout(()=>{if(state.confirmDelete==='app'+id)state.confirmDelete=null;},5000);return;}
      state.confirmDelete=null;
      await api(`/api/applications/${id}/delete`,{method:'POST',headers:{'Content-Type':'application/json'},body:'{}'});
      await refresh();render();toast('Application removed');
    }
    else if(action==='startup-signal'){state.filters.startups.signal=button.dataset.value||'';render();}
    else if(action==='startup-kind'){state.filters.startups.kind=button.dataset.value||'';render();}
    else if(action==='startup-all'){state.filters.startups.all=true;render();}
    else if(action==='startup-jobs'){
      const f=state.filters.jobs;['role','city','exp','employment','source','fresh','eligibility','minMatch'].forEach(k=>f[k]='');
      f.q=button.dataset.name||'';f.recency='all';f.undated=true;setView('jobs');
    }
    else if(action==='startup-news'){
      state.filters.news.region='India';state.filters.news.topic='Startup funding';
      await startJobRequest('/api/intel/search',{category:'news',query:'Indian AI startup',freshness:'30d',region:'India',topic:'Startup funding'},'Searching Indian startup news');
    }
  }catch(err){toast(err.message,true);}
});

document.addEventListener('submit',async event=>{
  const form=event.target.closest('form[data-form]');
  if(!form)return;
  event.preventDefault();
  const kind=form.dataset.form;
  const data=new FormData(form);
  try{
    if(kind==='discover'){
      const category=form.dataset.category;
      const query=String(data.get('query')||'').trim();
      const freshness=String(data.get('freshness')||'')||(state.filters[category]||{}).freshness;
      if(state.filters[category]){state.filters[category].freshness=freshness;}
      state.lastQuery[category]=query;
      const body={category,query,freshness};
      if(category==='news'){
        const region=String(data.get('region')||'');
        if(region)state.filters.news.region=region;
        body.region=region||state.filters.news.region||'';
        body.topic=state.filters.news.topic||'';
      }
      await startJobRequest('/api/intel/search',body,'Searching '+CATEGORY_META[category].label);
    }
    else if(kind==='research'){
      const request=String(data.get('request')||'').trim();
      if(!request){toast('Enter a request first',true);return;}
      await startJobRequest('/api/research',{request},'Research started');
    }
    else if(kind==='task'){
      const text=String(data.get('text')||'').trim();
      if(!text){toast('Enter a task',true);return;}
      await api('/api/tasks',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({text,due_date:data.get('due_date')||null})});
      await refresh();render();
    }
    else if(kind==='universal'){
      const request=String(data.get('request')||'').trim();
      if(!request){toast('Type what you are looking for',true);return;}
      await startJobRequest('/api/search/universal',{request},'Searching across sections');
    }
    else if(kind==='employers'){
      const request=String(data.get('request')||'').trim()||'Indian AI startups';
      const topic=String(data.get('topic')||'').trim();
      state.lastQuery.employers=request;state.lastQuery.employerTopic=topic;
      await startJobRequest('/api/employers/discover',{request,topic:topic||null,search_calls:Number(data.get('search_calls')||6)},'Discovering employers');
    }
    else if(kind==='application'){
      const id=form.dataset.id?Number(form.dataset.id):null;
      const interviews=String(data.get('interviews')||'').split('\n').map(l=>l.trim()).filter(Boolean).map(l=>{const [at,...note]=l.split(/\s+/);return {at,note:note.join(' ')||null};});
      const body={id,role:String(data.get('role')||'').trim(),company:String(data.get('company')||'').trim()||null,
        job_url:String(data.get('job_url')||'').trim()||null,resume_id:data.get('resume_id')?Number(data.get('resume_id')):null,
        status:String(data.get('status')||'interested'),applied_at:String(data.get('applied_at')||'')||null,
        follow_up_date:String(data.get('follow_up_date')||'')||null,next_action:String(data.get('next_action')||'').trim()||null,
        recruiter_name:String(data.get('recruiter_name')||'').trim()||null,recruiter_contact:String(data.get('recruiter_contact')||'').trim()||null,
        interview_dates:interviews,notes:String(data.get('notes')||'')};
      if(!body.role){toast('An application needs a role',true);return;}
      await api('/api/applications',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});
      state.editApp=null;await refresh();render();toast('Application saved; reminders updated in Planning');
    }
    else if(kind==='jobsearch'){
      const query=String(data.get('query')||'').trim();
      state.lastQuery.jobs=query;
      await startJobRequest('/api/intel/search',{category:'jobs',query,pool_size:Number(data.get('pool_size')||100)},'Discovering jobs');
    }
    else if(kind==='sources'){
      const prefs=JSON.parse(JSON.stringify(D().preferences||{}));
      const companies=String(data.get('companies')||'').split('\n').map(line=>line.trim()).filter(Boolean).map(line=>{
        const [ats,slug,...name]=line.split(/\s+/);return {ats,slug,name:name.join(' ')||slug};});
      prefs.jobs={...(prefs.jobs||{}),pool_size:Number(data.get('pool_size')||100),companies};
      prefs.scan_all={categories:['jobs','government','exams','news','papers'].filter(c=>data.has('scan:'+c))};
      await api('/api/preferences',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({preferences:prefs})});
      await refresh();render();toast('Search sources saved');
    }
    else if(kind==='note'){
      const name=String(data.get('name')||form.dataset.name||'').trim();
      const res=await api('/api/notes/'+encodeURIComponent(name),{method:'PUT',headers:{'Content-Type':'application/json'},body:JSON.stringify({content:String(data.get('content')||'')})});
      state.note={name:res.name,content:String(data.get('content')||'')};
      await refresh();render();
      toast(`Saved ${res.name}: ${res.planning.tasks_found} task(s) extracted`);
    }
    else if(kind==='automation'){
      const prefs=JSON.parse(JSON.stringify(D().preferences||{}));
      prefs.automation={daily_refresh:data.get('daily_refresh')==='on',refresh_time:String(data.get('refresh_time')||'08:00'),
        categories:['jobs','news','papers','government','exams'].filter(c=>data.has('auto:'+c))};
      await api('/api/preferences',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({preferences:prefs})});
      await refresh();render();toast('Automation saved');
    }
    else if(kind==='watchlist'){
      const name=String(data.get('name')||'').trim();
      if(!name){toast('Enter a name',true);return;}
      const target=form.dataset.kind==='exam'?'/api/exams/watchlist':'/api/organizations/watchlist';
      await api(target,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({name})});
      await refresh();render();toast('Added to watchlist');
    }
    else if(kind==='settings'){
      const payload={
        ollama_model:String(data.get('ollama_model')||''),
        max_search_queries:Number(data.get('max_search_queries')),
        max_fetch_urls:Number(data.get('max_fetch_urls')),
        max_content_chars:Number(data.get('max_content_chars')),
        ollama_timeout:Number(data.get('ollama_timeout')),
        mcp_timeout:Number(data.get('mcp_timeout')),
        notes_dir:String(data.get('notes_dir')||''),
        briefing_preferences:String(data.get('briefing_preferences')||''),
        theme:document.documentElement.dataset.theme||'minimal-light',
        location:(D().settings||{}).location||'',
      };
      await api('/api/settings',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(payload)});
      await refresh();applyTheme();render();toast('Settings saved');
    }
    else if(kind==='preferences'){
      const prefs=JSON.parse(JSON.stringify(D().preferences||{}));
      const jobs=prefs.jobs||{};
      const portals={};
      Object.entries(jobs.portals||{}).forEach(([name,portal])=>{
        portals[name]={domain:portal.domain||'',enabled:data.has('portal:'+name)};
      });
      if(data.has('roles'))prefs.jobs={...jobs,
        roles:splitList(data.get('roles')),experience:String(data.get('experience')||'any'),
        employment_types:splitList(data.get('employment_types')),locations:splitList(data.get('locations')),
        remote:String(data.get('remote')||'any'),salary_min:data.get('salary_min')||null,
        salary_max:data.get('salary_max')||null,ignore_salary:data.get('ignore_salary')==='on',
        skills:splitList(data.get('skills')),freshness:String(data.get('job_freshness')||'30d'),
        scan_roles:data.has('scan_roles')?splitList(data.get('scan_roles')):(jobs.scan_roles||[]),
        match_resume:data.get('match_resume')==='on',portals,custom_sites:splitList(data.get('custom_sites'))};
      if(data.has('disciplines')){prefs.government={...(prefs.government||{}),disciplines:splitList(data.get('disciplines')),
        gate_paper:String(data.get('gate_paper')||''),freshness:String(data.get('gov_freshness')||'90d')};
      prefs.exams={...(prefs.exams||{}),freshness:String(data.get('exam_freshness')||'365d')};
      prefs.news={...(prefs.news||{}),interests:splitList(data.get('news_interests')),
        region:String(data.get('news_region')||'India'),
        freshness:String(data.get('news_freshness')||'7d')};
      prefs.papers={...(prefs.papers||{}),interests:splitList(data.get('paper_interests')),
        freshness:String(data.get('paper_freshness')||'30d')};}
      await api('/api/preferences',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({preferences:prefs})});
      await refresh();render();toast('Preferences saved');
    }
  }catch(err){toast(err.message,true);}
});

let inputTimer=null;
document.addEventListener('input',event=>{
  const target=event.target;const action=target.dataset&&target.dataset.action;
  if(action==='feed-q'){
    clearTimeout(inputTimer);
    inputTimer=setTimeout(()=>{(state.filters.feed=state.filters.feed||{}).q=target.value;const pos=target.selectionStart;render();
      const again=document.querySelector('[data-action="feed-q"]');if(again){again.focus();again.setSelectionRange(pos,pos);}},250);
    return;
  }
  if(action!=='job-q'&&action!=='news-q'&&action!=='startup-q')return;
  clearTimeout(inputTimer);
  inputTimer=setTimeout(()=>{
    ({'job-q':state.filters.jobs,'news-q':state.filters.news,'startup-q':state.filters.startups}[action]).q=target.value;
    const pos=target.selectionStart;render();
    const again=document.querySelector(`[data-action="${action}"]`);if(again){again.focus();again.setSelectionRange(pos,pos);}
  },250);
});
document.addEventListener('change',event=>{
  const target=event.target;
  if(target.dataset.action==='gov-eligibility'){state.filters.government.eligibility=target.value;render();}
  if(target.dataset.action==='gov-doc'){state.filters.government.doc=target.value;render();}
  if(target.dataset.action==='job-sort'){state.filters.jobs.sort=target.value;render();}
  if(target.dataset.action==='job-expired'){state.filters.jobs.showExpired=target.checked;render();}
  if(target.dataset.action==='switch-resume'){
    api(`/api/resumes/${target.value}/activate`,{method:'POST',headers:{'Content-Type':'application/json'},body:'{}'})
      .then(refresh).then(()=>{render();toast('Ranking now uses '+((activeResume()||{}).label||'this resume'));}).catch(err=>toast(err.message,true));
  }
  if(target.dataset.action==='job-undated'){state.filters.jobs.undated=target.checked;render();}
  if(target.dataset.filter){state.filters.jobs[target.dataset.filter]=target.value;render();}
  if(target.dataset.feed){(state.filters.feed=state.filters.feed||{})[target.dataset.feed]=target.value;render();}
  if(target.dataset.filterCheck==='startups-builtin'){state.filters.startups.builtin=target.checked;render();}
  else if(target.dataset.filterCheck){state.filters.jobs[target.dataset.filterCheck]=target.checked;render();}
  if(target.dataset.action==='app-status'){
    api('/api/applications',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({id:Number(target.dataset.id),status:target.value})})
      .then(refresh).then(()=>{render();toast('Status: '+(APP_LABEL[target.value]||target.value));}).catch(err=>toast(err.message,true));
  }
});

async function saveProfile(){
  const root=$('#profile-editor');if(!root)return;
  const profile={};
  ['job_titles','education','skills','languages','frameworks','projects','certifications','keywords'].forEach(field=>{
    const area=root.querySelector(`textarea[name="${field}"]`);
    profile[field]=area?splitList(area.value.replace(/\n/g,',')):[];
  });
  profile.graduation_year=Number(root.querySelector('[name="graduation_year"]')?.value||0)||null;
  profile.experience_years=Number(root.querySelector('[name="experience_years"]')?.value||0)||0;
  const resumeId=root.dataset.resumeId;
  if(resumeId)await api(`/api/resumes/${resumeId}/profile`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({profile})});
  else await api('/api/resume/profile',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({profile})});
  await refresh();render();toast('Profile saved; jobs re-scored');
}
async function exportData(){
  const data=await api('/api/export');
  const blob=new Blob([JSON.stringify(data,null,2)],{type:'application/json'});
  const link=document.createElement('a');
  link.href=URL.createObjectURL(blob);link.download='daily-intelligence-export.json';
  document.body.appendChild(link);link.click();link.remove();
  setTimeout(()=>URL.revokeObjectURL(link.href),1000);
}
function arrayBufferToBase64(buffer){
  let binary='';const bytes=new Uint8Array(buffer);const chunk=0x8000;
  for(let i=0;i<bytes.length;i+=chunk){binary+=String.fromCharCode.apply(null,bytes.subarray(i,i+chunk));}
  return btoa(binary);
}
async function handleResumeFile(event){
  const file=event.target.files&&event.target.files[0];if(!file)return;
  if(file.size>6_000_000){toast('Resume file exceeds 6 MB',true);return;}
  try{
    toast('Extracting resume locally…');
    const buffer=await file.arrayBuffer();
    const label=($('#resume-label')?.value||'').trim();
    const makeDefault=!!$('#resume-default')?.checked;
    const res=await api('/api/resume',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({filename:file.name,content_base64:arrayBufferToBase64(buffer),label,make_default:makeDefault,replace_id:state.replaceResume||null})});
    state.replaceResume=null;
    await refresh();render();toast(`Resume saved; ${res.rescored||0} jobs re-scored`);
  }catch(err){state.replaceResume=null;toast(err.message,true);}
  finally{event.target.value='';}
}
window.handleResumeFile=handleResumeFile;

function applyTheme(){
  const theme=((D().settings||{}).theme)||'minimal-light';
  document.documentElement.dataset.theme=theme;
  try{localStorage.setItem('di-theme',theme);}catch(e){}
}
async function setTheme(theme){
  document.documentElement.dataset.theme=theme;
  try{localStorage.setItem('di-theme',theme);}catch(e){}
  await api('/api/theme',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({theme})});
  if(state.data&&state.data.settings)state.data.settings.theme=theme;
  toast('Theme: '+(THEMES.find(t=>t.id===theme)||{}).label);
}
async function boot(){
  try{
    await refresh();
  }catch(err){
    $('#page-content').innerHTML=`<div class="empty-rich"><h3>Cannot reach local services</h3><p>${esc(err.message)}</p></div>`;
    return;
  }
  applyTheme();
  const tag=$('#version-tag');if(tag&&D().version)tag.textContent='v'+D().version;
  api('/api/visit',{method:'POST',headers:{'Content-Type':'application/json'},body:'{}'}).catch(()=>{});
  const hash=location.hash.replace('#','');
  if(hash&&(NAV.some(item=>item.id===hash)||HIDDEN_VIEWS.includes(hash)))state.view=hash;
  render();
  $('#mobile-menu')?.addEventListener('click',()=>openDrawer(!$('#sidebar')?.classList.contains('open')));
  if(!state.models.length){
    api('/api/models').then(data=>{state.models=data.models||[];if(state.view==='settings')render();}).catch(()=>{});
  }
  const status=D().status;
  if(status&&['queued','running'].includes(status.status)&&status.id){state.activeJob=status;pollJob(status.id);}
  setInterval(()=>{api('/api/heartbeat',{method:'POST',headers:{'Content-Type':'application/json'},body:'{}'}).then(()=>{
    const c=$('#connection');if(c)c.innerHTML='<i></i>Local';}).catch(()=>{const c=$('#connection');if(c)c.textContent='Offline';});},60000);
}
window.addEventListener('hashchange',()=>{
  const hash=location.hash.replace('#','');
  if(hash&&(NAV.some(item=>item.id===hash)||HIDDEN_VIEWS.includes(hash))&&hash!==state.view){state.view=hash;render();}
});
$('#theme-toggle')?.addEventListener('click',async()=>{
  const ids=THEMES.map(t=>t.id);
  const next=ids[(ids.indexOf(document.documentElement.dataset.theme)+1)%ids.length];
  try{await setTheme(next);if(state.view==='settings')render();}catch(err){toast(err.message,true);}
});
$('#quit-app')?.addEventListener('click',async()=>{
  const busy=activeJob();
  if(busy&&state.confirmQuit!==true){state.confirmQuit=true;toast('A search is running. Click Quit again to stop it and exit.');setTimeout(()=>{state.confirmQuit=false;},5000);return;}
  try{
    await api('/api/shutdown',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({force:!!busy})});
    document.body.innerHTML='<div class="empty-rich" style="margin:20vh auto;max-width:460px"><h3>Daily Intelligence has stopped</h3><p>The local server has shut down. You can close this window and start the app again from the application menu.</p></div>';
    setTimeout(()=>{try{window.close();}catch(e){}},800);
  }catch(err){toast(err.message,true);}
});
document.addEventListener('toggle',event=>{const d=event.target;if(d.dataset&&d.dataset.details)state.expanded[d.dataset.details]=d.open;},true);

boot();
