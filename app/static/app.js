const NAV=[
  {id:'daily-briefing',label:'Daily Briefing',icon:'◷',group:'main'},
  {id:'ask-intelligence',label:'Ask Intelligence',icon:'✳',group:'main'},
  {id:'research',label:'Research',icon:'⌕',group:'main'},
  {id:'jobs',label:'Jobs',icon:'▤',group:'intel'},
  {id:'job-market',label:'Skills Market',icon:'◫',group:'intel'},
  {id:'tracker',label:'Applications',icon:'✓',group:'intel'},
  {id:'government',label:'Government & PSU',icon:'⌂',group:'intel'},
  {id:'exams',label:'Exams',icon:'▧',group:'intel'},
  {id:'ai-news',label:'AI News',icon:'◈',group:'intel'},
  {id:'papers',label:'Research Papers',icon:'▱',group:'intel'},
  {id:'planning',label:'Planning',icon:'☷',group:'personal'},
  {id:'history',label:'History',icon:'↺',group:'personal'},
  {id:'settings',label:'Settings',icon:'⚙',group:'personal'},
];
const CATEGORY_META={
  jobs:{label:'Jobs',endpoint:'jobs'},
  government:{label:'Government & PSU',endpoint:'government'},
  exams:{label:'Exams',endpoint:'exams'},
  news:{label:'AI News',endpoint:'news'},
  papers:{label:'Research Papers',endpoint:'papers'},
};
const state={
  data:null,view:'daily-briefing',activeJob:null,pollTimer:null,toastTimer:null,
  models:[],lastJob:null,tailor:{},note:null,suggestions:null,editResume:null,replaceResume:null,confirmDelete:null,
  lastQuery:{jobs:'',government:'',exams:'',news:'',papers:''},
  filters:{
    jobs:{status:'all',q:'',freshness:'30d',recency:'month',role:'',resume:'',sort:'newest',layout:'cards',undated:true},
    government:{eligibility:'all',doc:'all',q:'',freshness:'90d'},
    exams:{q:'',freshness:'365d'},
    news:{q:'',freshness:'7d',region:'',topic:''},
    papers:{q:'',freshness:'30d'},
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
function progressBox(){
  const job=activeJob();if(!job)return '';
  return `<div class="progress-box visible">
    <div class="progress-top"><span>${esc(job.message||'Working')} <span class="view-note">${esc(job.kind||'')}</span></span><span>${job.elapsed_seconds!=null?esc(job.elapsed_seconds)+'s':''}</span></div>
    <div class="progress-track"><span></span></div>
    <div class="item-actions"><button class="link-button danger" data-action="cancel-job" data-id="${esc(job.id)}">Cancel</button></div>
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
  state.data=await api('/api/bootstrap');
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
    return sep+`<button class="nav-item ${state.view===n.id?'active':''}" data-view="${n.id}"><span class="nav-icon">${n.icon}</span><span>${n.label}</span>${count?`<span class="nav-count" title="New since your last visit">${count}</span>`:''}</button>`;
  }).join('');
}
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
function statCard(label,value,icon){
  return `<div class="panel stat-card"><div class="stat-icon">${icon}</div><div><div class="stat-value">${esc(value)}</div><div class="stat-label">${esc(label)}</div></div></div>`;
}
function emptyRich(title,text,actions){
  return `<div class="empty-rich"><h3>${esc(title)}</h3><p>${esc(text)}</p><div class="item-actions" style="justify-content:center">${actions||''}</div></div>`;
}
function render(){
  renderNav();
  const meta=NAV.find(n=>n.id===state.view)||NAV[0];
  const crumb=$('#page-crumb');if(crumb)crumb.textContent=meta.label;
  const content=$('#page-content');if(!content)return;
  if(!state.data){content.innerHTML='<div class="empty-state"><strong>Loading workspace</strong>Connecting to local services…</div>';return;}
  const view=VIEWS[state.view]||VIEWS['daily-briefing'];
  content.innerHTML=view();
}
function setView(view){
  if(!NAV.some(n=>n.id===view))view='daily-briefing';
  state.view=view;
  if(location.hash!=='#'+view)history.replaceState(null,'','#'+view);
  $('#sidebar')?.classList.remove('open');
  render();
  window.scrollTo({top:0,behavior:'smooth'});
}

/* --------------------------------------------------------------- dashboard */
function viewBriefing(){
  const d=D(),briefing=(d.briefings||[])[0];
  const c=counts();
  const content=briefing?briefing.content||{}:{};
  return heading('Workspace','Daily briefing',
    `Personalized intelligence for ${esc(d.date||'today')}. Stored findings are assembled locally; live search runs only when no intelligence exists.`,
    `<button class="primary-button" data-action="briefing">Generate briefing</button>`) +
    progressBox() +
    `<div class="grid grid-3 section-space">
      ${statCard('Fresh job listings',d.fresh_job_count??c.jobs,'▤')}
      ${statCard('Recruitment notices',c.notices,'⌂')}
      ${statCard('Exam events',c.exams,'▧')}
      ${statCard('AI news items',c.news,'◈')}
      ${statCard('Papers & resources',c.papers,'▱')}
      ${statCard('Saved / tracked',Object.values(d.item_states||{}).reduce((n,m)=>n+Object.keys(m).length,0),'✓')}
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
  return days+' days ago';
}
function filteredJobs(){
  const jobs=D().jobs||[];
  const f=state.filters.jobs;
  const days={'week':7,'month':30,'quarter':90,'all':null}[f.recency||'month'];
  const q=(f.q||'').toLowerCase();
  const listings=[],searchPages=[];
  for(const job of jobs){
    if(SEARCH_KINDS.has(job.source_kind)){searchPages.push(job);continue;}
    if(days!=null){
      const age=daysAgo(job.posted_date);
      if(age==null){if(!f.undated)continue;}
      else if(age>days)continue;
    }
    if(f.status!=='all'&&job.status!==f.status)continue;
    if(f.status==='all'&&!f.showExpired&&['expired','closed'].includes(job.status))continue;
    if(f.role&&job.role_family!==f.role)continue;
    if(f.resume&&job.best_resume_label!==f.resume)continue;
    if(q&&!`${job.title} ${job.employer||''} ${job.location||''} ${(job.skills||[]).join(' ')}`.toLowerCase().includes(q))continue;
    listings.push(job);
  }
  const sorters={
    newest:(a,b)=>String(b.posted_date||'').localeCompare(String(a.posted_date||''))||String(b.first_seen||'').localeCompare(String(a.first_seen||'')),
    match:(a,b)=>(b.match_score??-1)-(a.match_score??-1),
  };
  listings.sort(sorters[f.sort||'newest']);
  return {listings,searchPages};
}
function viewJobs(){
  const jobs=D().jobs||[];
  const f=state.filters.jobs;
  const {listings,searchPages}=filteredJobs();
  const families=Array.from(new Set(jobs.filter(j=>!SEARCH_KINDS.has(j.source_kind)).map(j=>j.role_family).filter(Boolean))).sort();
  const resumes=Array.from(new Set(jobs.map(j=>j.best_resume_label).filter(Boolean)));
  const tabs=[['all','All'],['open','Open'],['unverified','Unverified'],['expired','Expired']];
  const recency=[['week','This week'],['month','30 days'],['quarter','90 days'],['all','Any date']];
  const fresh=D().fresh_job_count??listings.length;
  const roles=D().scan_roles||[];
  return heading('Intelligence','Jobs',
    `Individual listings from job boards and company career pages, newest first. Index pages are expanded into the roles they list; ${esc(fresh)} listings are fresh (seen in the last 3 weeks, not expired).`,
    `<button class="primary-button" data-action="market-scan">Scan ${esc(roles.length)} roles</button><a class="quiet-button" href="/api/export/jobs.csv?fresh=1">Export CSV</a>`) +
    progressBox() +
    `<div class="toolbar"><form data-form="discover" data-category="jobs">
      <input class="input" name="query" placeholder="Search a specific role, e.g. “Data Engineer Pune” — blank searches your configured roles" value="${esc(state.lastQuery.jobs||'')}">
      <select class="select" name="freshness">${freshnessOptions(f.freshness)}</select>
      <button class="quiet-button" type="submit">Search one role</button>
    </form>
    <div class="view-note" style="margin-top:8px">Market scan roles: ${roles.map(r=>`<span class="meta">${esc(r)}</span>`).join(' ')} <a href="#settings" data-view="settings">edit</a></div></div>
    <div class="sticky-filters"><div class="filter-row">
      ${tabs.map(([value,label])=>`<button class="chip ${f.status===value?'active':''}" data-action="job-filter" data-value="${value}">${label}</button>`).join('')}
      <span class="filter-gap"></span>
      ${recency.map(([value,label])=>`<button class="chip ${(f.recency||'month')===value?'active':''}" data-action="job-recency" data-value="${value}">${label}</button>`).join('')}
      <label class="chip"><input type="checkbox" data-action="job-undated" ${f.undated?'checked':''}> undated</label>
    </div>
    <div class="filter-row">
      <span class="filter-label">Role</span>
      <button class="chip ${!f.role?'active':''}" data-action="job-role" data-value="">All</button>
      ${families.map(name=>`<button class="chip ${f.role===name?'active':''}" data-action="job-role" data-value="${esc(name)}">${esc(name)}</button>`).join('')}
    </div>
    <div class="filter-row">
      ${resumes.length?`<span class="filter-label">Best resume</span><button class="chip ${!f.resume?'active':''}" data-action="job-resume" data-value="">Any</button>${resumes.map(name=>`<button class="chip ${f.resume===name?'active':''}" data-action="job-resume" data-value="${esc(name)}">${esc(name)}</button>`).join('')}`:''}
      <span class="filter-gap"></span>
      <input class="input" style="width:200px" data-action="job-q" placeholder="Filter…" value="${esc(f.q||'')}">
      <select class="select" style="width:auto" data-action="job-sort"><option value="newest" ${f.sort!=='match'?'selected':''}>Newest</option><option value="match" ${f.sort==='match'?'selected':''}>Best match</option></select>
      <button class="chip ${f.layout==='table'?'active':''}" data-action="job-layout" data-value="${f.layout==='table'?'cards':'table'}">${f.layout==='table'?'Cards':'Table'}</button>
    </div></div>
    <div class="banner">${listings.length} listing${listings.length===1?'':'s'} shown${isNewCount(listings)?` · <b>${isNewCount(listings)} new since your last visit</b>`:''}</div>` +
    (listings.length
      ?(f.layout==='table'?jobsTable(listings):`<div class="list-grid section-space">${listings.map(jobCard).join('')}</div>`)
      :emptyRich('No listings match these filters',
        'Widen the date range, include undated listings, or run a market scan. The scan searches each role family on job boards and company career pages, then expands index pages into individual listings.',
        `<button class="primary-button" data-action="market-scan">Scan the market</button>`)) +
    (searchPages.length?`<details class="collapsible"><summary>Search pages to check <span class="badge unverified">${searchPages.length}</span></summary>
      <div class="view-note">These are search/index pages that could not be expanded into individual listings. Open them to browse manually.</div>
      <div class="source-list section-space">${searchPages.slice(0,40).map(job=>`<div class="source-card"><a class="source-title" href="${esc(job.original_url)}" target="_blank" rel="noopener">${esc(job.title)}</a><div class="item-meta">${meta(job.source_platform||'')}${job.posted_date?meta(fmtDate(job.posted_date)):''}</div></div>`).join('')}</div>
    </details>`:'');
}
function isNewCount(items){return items.filter(isNew).length;}
function resumeLine(job){
  const scores=(job.resume_scores||[]).filter(s=>s&&s.score!=null);
  if(!job.best_resume_label)return '';
  const others=scores.filter(s=>s.label!==job.best_resume_label).slice(0,3)
    .map(s=>`${esc(s.label)} ${esc(s.score)}%`).join(' · ');
  const best=scores.find(s=>s.label===job.best_resume_label)||{};
  return `<div class="resume-line"><span class="resume-pill">Best resume: ${esc(job.best_resume_label)}${best.score!=null?' · '+esc(best.score)+'%':''}</span>${others?`<span class="view-note">${others}</span>`:''}</div>
    ${(best.matched||[]).length||(best.missing||[]).length?`<div class="item-meta">${(best.matched||[]).slice(0,6).map(s=>`<span class="meta skill-have">✓ ${esc(s)}</span>`).join('')}${(best.missing||[]).slice(0,5).map(s=>`<span class="meta skill-miss">+ ${esc(s)}</span>`).join('')}</div>`:''}`;
}
function jobCard(job){
  const current=stateOf('job',job.id);
  const age=daysAgo(job.posted_date);
  const tailor=state.tailor[job.id];
  const match=job.match_score!=null
    ?`<div class="match"><span class="match-score">${esc(job.match_score)}% match</span><span>${esc(job.match_reason||'')}</span></div>`
    :`<div class="match"><span>${esc(job.match_reason||'Needs review — insufficient evidence to score.')}</span></div>`;
  return `<article class="item-card ${isNew(job)?'is-new':''}">
    <div class="item-head">
      <div><h3 class="item-title"><a href="${esc(job.original_url||'#')}" target="_blank" rel="noopener">${esc(job.title||'Untitled role')}</a></h3>
        <div class="item-sub">${esc(job.employer||'Employer not stated')} · ${esc(job.location||'Location not stated')}${job.remote?' · '+esc(job.remote):''}</div></div>
      <div class="chips">${isNew(job)?'<span class="badge new">new</span>':''}${age!=null&&age<=7?'<span class="badge open">this week</span>':''}${badge(job.status||'unverified')}${job.source_kind==='harvested'?'<span class="badge harvested">from index</span>':''}</div>
    </div>
    ${match}
    ${resumeLine(job)}
    <div class="item-meta">
      ${job.role_family?meta(job.role_family):''}
      ${job.employment_type?meta(job.employment_type):''}
      ${job.experience?meta('Experience: '+job.experience):''}
      ${job.salary?meta(job.salary):''}
      ${job.posted_date?meta('Posted '+fmtDate(job.posted_date)+' ('+ageLabel(job.posted_date)+')'):meta('Posting date not stated')}
      ${job.deadline?meta('Deadline '+fmtDate(job.deadline)):''}
      ${job.source_platform?meta(job.source_platform):''}
    </div>
    ${(job.skills||[]).length&&!((job.resume_scores||[]).find(s=>s.label===job.best_resume_label)||{}).matched?.length&&!((job.resume_scores||[]).find(s=>s.label===job.best_resume_label)||{}).missing?.length?`<div class="item-meta">${job.skills.slice(0,10).map(skill=>meta(skill)).join('')}</div>`:''}
    ${evidence(job)}
    ${tailor?tailorBox(tailor):''}
    <div class="item-actions">
      <a class="link-button primary" href="${esc(job.original_url||'#')}" target="_blank" rel="noopener">Open listing</a>
      ${trackButtons(job.id,current)}
      ${(D().resumes||[]).length?`<button class="link-button" data-action="tailor" data-id="${job.id}">Tailoring hints</button>`:''}
    </div>
  </article>`;
}
function tailorBox(t){
  if(t.loading)return '<div class="reason">Preparing tailoring hints with the local model…</div>';
  return `<div class="reason"><b>Tailor your “${esc(t.resume)}” resume</b> (fit ${esc(t.fit??'—')}%)
    ${(t.missing||[]).length?`<div>Not evidenced in this resume: ${t.missing.map(esc).join(', ')} — add them only if you genuinely have them.</div>`:''}
    ${(t.matched||[]).length?`<div>Emphasise: ${t.matched.map(esc).join(', ')}</div>`:''}
    ${(t.bullets||[]).length?`<ul>${t.bullets.map(b=>`<li>${esc(b)}</li>`).join('')}</ul>`:''}
    <div class="view-note">${t.source==='local_model'?'Bullet suggestions from your local model; review before use.':'Deterministic hints (local model unavailable).'}</div></div>`;
}
const TRACK_STATES=[['saved','Save'],['applied','Applied'],['interview','Interview'],['offer','Offer'],['rejected','Rejected'],['dismissed','Hide']];
function trackButtons(id,current){
  const visible=current&&current!=='saved'&&current!=='dismissed'
    ?TRACK_STATES.filter(([v])=>['applied','interview','offer','rejected'].includes(v))
    :TRACK_STATES.filter(([v])=>['saved','applied','dismissed'].includes(v));
  return visible.map(([value,label])=>
    `<button class="link-button ${current===value?'active':''}" data-action="item-state" data-kind="job" data-id="${id}" data-state="${current===value?'none':value}">${current===value?'✓ ':''}${label}</button>`).join('');
}
function jobsTable(listings){
  return `<div class="table-wrap section-space"><table class="data-table">
    <thead><tr><th>Role</th><th>Employer</th><th>Location</th><th>Posted</th><th class="num">Match</th><th>Best resume</th><th>Status</th><th>Source</th></tr></thead>
    <tbody>${listings.map(job=>`<tr>
      <td><a href="${esc(job.original_url||'#')}" target="_blank" rel="noopener"><b>${esc(job.title)}</b></a>${isNew(job)?' <span class="badge new">new</span>':''}<div class="view-note">${esc(job.role_family||'')}</div></td>
      <td>${esc(job.employer||'—')}</td><td>${esc(job.location||'—')}</td>
      <td>${job.posted_date?esc(ageLabel(job.posted_date)):'—'}</td>
      <td class="num">${job.match_score!=null?esc(job.match_score)+'%':'—'}</td>
      <td>${esc(job.best_resume_label||'—')}</td><td>${badge(job.status||'unverified')}</td>
      <td>${esc(job.source_platform||'')}</td></tr>`).join('')}</tbody></table></div>`;
}

/* ------------------------------------------------------------- tracker */
function viewTracker(){
  const items=D().tracker||[];
  const cols=[['saved','Saved'],['applied','Applied'],['interview','Interview'],['offer','Offer'],['rejected','Rejected']];
  return heading('Intelligence','Applications',
    'Your application pipeline. Marking a job “Applied” records the date and adds a follow-up task to Planning seven days later.',
    `<a class="quiet-button" href="/api/export/jobs.csv">Export all jobs (CSV)</a>`) +
    (items.length?`<div class="kanban">${cols.map(([key,label])=>{
      const list=items.filter(item=>item.state===key);
      return `<div class="kanban-col"><h3>${label}<span class="panel-kicker">${list.length}</span></h3>
        ${list.map(item=>`<div class="kanban-card">
          <b><a href="${esc(item.original_url||'#')}" target="_blank" rel="noopener">${esc(item.title)}</a></b>
          <small>${esc(item.employer||'Employer not stated')}${item.location?' · '+esc(item.location):''}</small>
          ${item.applied_at?`<small>Applied ${esc(fmtDate(item.applied_at))} (${esc(ageLabel(item.applied_at))})</small>`:''}
          ${item.best_resume_label?`<small>Resume: ${esc(item.best_resume_label)}${item.match_score!=null?' · '+esc(item.match_score)+'%':''}</small>`:''}
          <div class="item-actions">${cols.filter(([k])=>k!==key).map(([k,l])=>`<button class="link-button" data-action="item-state" data-kind="job" data-id="${item.id}" data-state="${k}">→ ${l}</button>`).join('')}<button class="link-button danger" data-action="item-state" data-kind="job" data-id="${item.id}" data-state="none">Remove</button></div>
        </div>`).join('')||'<div class="view-note">Nothing here yet.</div>'}
      </div>`;}).join('')}</div>`
      :emptyRich('No applications tracked yet','Use “Save” or “Applied” on any job card to start your pipeline.',
        `<button class="primary-button" data-view="jobs">Browse jobs</button>`));
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
  if(!(fit||[]).length)return '<div class="empty-state">Upload resumes in Settings to compare how each fits each role family.</div>';
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
    'Which skills and roles are in demand right now, computed only from fresh stored listings across job boards and company career pages. Counts are per listing. Run a market scan to widen coverage.',
    `<button class="primary-button" data-action="market-scan">Scan the market</button>`) +
    progressBox() +
    `<div class="market-hero">
      ${statCard('Fresh listings analysed',totals.listings??0,'▤')}
      ${statCard('Posted in 30 days',totals.recent_30d??0,'◷')}
      ${statCard('Boards & career sites',totals.portals??0,'◫')}
      ${statCard('Role families',totals.roles??0,'◧')}
      ${statCard('Distinct skills',totals.skills??0,'✳')}
    </div>
    <div class="market-grid section-space">
      <div class="panel">
        <div class="panel-head"><h3 class="panel-title">Most-requested skills</h3><span class="panel-kicker">listings mentioning</span></div>
        ${barList(market.skills,{empty:'No skills extracted from listings yet.'})}
      </div>
      <div class="panel">
        <div class="panel-head"><h3 class="panel-title">Your skill gap</h3><span class="panel-kicker">in demand · not on your resumes</span></div>
        ${hasResumes?barList(market.skill_gap,{empty:'Your resumes already cover the most-requested skills.',series:2}):'<div class="empty-state">Upload a resume in Settings to see which in-demand skills it is missing.</div>'}
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
        <textarea class="textarea" name="request" placeholder="e.g. Find current entry-level AI engineer jobs in India. Check Wellfound, Naukri, Indeed, LinkedIn and YC Work at a Startup."></textarea>
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
    `<div class="panel">
      <div class="panel-head"><h3 class="panel-title">Local model & resources</h3><span class="panel-kicker">Ollama</span></div>
      <form data-form="settings">
        <div class="settings-grid">
          <div class="field"><label>Installed Ollama model</label><select class="select" name="ollama_model">${modelOptions()}</select><small>Only installed models are accepted. Nothing is pulled automatically.</small></div>
          <div class="field"><label>Theme</label><select class="select" name="theme"><option value="light" ${settings.theme!=='dark'?'selected':''}>Light (cream)</option><option value="dark" ${settings.theme==='dark'?'selected':''}>Dark (walnut)</option></select></div>
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

    ${resumesPanel()}

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
function resumesPanel(){
  const resumes=D().resumes||[];
  const editing=resumes.find(r=>r.id===state.editResume)||null;
  return `<div class="panel section-space" id="resumes">
      <div class="panel-head"><h3 class="panel-title">Resumes</h3><span class="panel-kicker">${resumes.length} stored · local only</span></div>
      <div class="view-note">Upload one resume per target direction (e.g. “SDE”, “AI/ML”, “Backend”). Every job is scored against all of them and shows the best fit, with the skills it covers and misses. Resume text never leaves this machine.</div>
      <div class="resume-list section-space">${resumes.length?resumes.map(r=>{
        const skills=(r.profile||{}).skills||[];
        return `<div class="resume-card ${r.is_default?'default':''}">
          <div><b>${esc(r.label)}</b> ${r.is_default?'<span class="badge open">default</span>':''}
            <div class="view-note">${esc(r.filename||'manual')} · updated ${esc(fmtDateTime(r.updated_at))} · ${skills.length} skills</div>
            <div class="item-meta">${skills.slice(0,10).map(s=>meta(s)).join('')}</div></div>
          <div class="item-actions" style="margin-top:0">
            ${r.is_default?'':`<button class="link-button" data-action="resume-default" data-id="${r.id}">Make default</button>`}
            <button class="link-button" data-action="resume-rename" data-id="${r.id}" data-label="${esc(r.label)}">Rename</button>
            <button class="link-button" data-action="resume-edit" data-id="${r.id}">${editing&&editing.id===r.id?'Close editor':'Edit profile'}</button>
            <button class="link-button" data-action="resume-replace" data-id="${r.id}">Replace file</button>
            <button class="link-button danger" data-action="resume-delete" data-id="${r.id}" data-label="${esc(r.label)}">Delete</button>
          </div></div>`;}).join(''):'<div class="empty-state">No resume uploaded yet. Jobs are matched against your preferences only.</div>'}</div>
      <div class="upload-box section-space">
        <div class="inline-form" style="width:min(520px,100%)"><input class="input" id="resume-label" placeholder="Label, e.g. AI/ML or Backend SDE"><label class="check-row"><input type="checkbox" id="resume-default"> make default</label></div>
        <div class="item-actions" style="justify-content:center"><button class="primary-button" type="button" data-action="resume-pick">Upload PDF / DOCX</button><input id="resume-file" type="file" accept=".pdf,.docx,.txt,.md" onchange="handleResumeFile(event)"></div>
        <div class="view-note">After upload, all stored jobs are re-scored automatically.</div>
      </div>
      ${editing?`<div class="settings-section"><h3>Edit “${esc(editing.label)}”</h3>${profileEditor(editing)}</div>`:''}
    </div>`;
}

function profileEditor(profile){
  const prof=profile?profile.profile||{}:{};
  const fields=['education','skills','languages','frameworks','projects','certifications','keywords'];
  return `<div class="profile-editor section-space" id="profile-editor" data-resume-id="${esc(profile&&profile.id||'')}">
    <div class="field-grid">
      <div class="field"><label>Graduation year</label><input class="input" name="graduation_year" type="number" min="1980" max="2100" value="${esc(prof.graduation_year??'')}"></div>
      <div class="field"><label>Experience years</label><input class="input" name="experience_years" type="number" min="0" max="60" value="${esc(prof.experience_years??0)}"></div>
    </div>
    ${fields.map(field=>`<div class="field"><label>${field}</label><textarea class="textarea" name="${field}" placeholder="One item per line">${esc((prof[field]||[]).join('\n'))}</textarea></div>`).join('')}
    <div class="item-actions"><button class="quiet-button" type="button" data-action="save-profile">Save reviewed profile</button></div>
  </div>`;
}

const VIEWS={
  'daily-briefing':viewBriefing,
  'ask-intelligence':viewAsk,
  research:viewResearch,
  jobs:viewJobs,
  'job-market':viewMarket,
  tracker:viewTracker,
  government:viewGovernment,
  exams:viewExams,
  'ai-news':viewNews,
  papers:viewPapers,
  planning:viewPlanning,
  history:viewHistory,
  settings:viewSettings,
};

/* ------------------------------------------------------------------ events */
document.addEventListener('click',async event=>{
  const viewButton=event.target.closest('[data-view]');
  if(viewButton){event.preventDefault();setView(viewButton.dataset.view);return;}
  const button=event.target.closest('[data-action]');
  if(!button)return;
  const action=button.dataset.action;
  try{
    if(action==='briefing'){await startJobRequest('/api/briefings',{},'Briefing started');}
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
      await startJobRequest('/api/intel/search',{category:'jobs',query:'',scan:true,freshness:(state.filters.jobs||{}).freshness},'Scanning the job market role by role');
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
        theme:String(data.get('theme')||'light'),
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
  if(action!=='job-q'&&action!=='news-q')return;
  clearTimeout(inputTimer);
  inputTimer=setTimeout(()=>{
    (action==='job-q'?state.filters.jobs:state.filters.news).q=target.value;
    const pos=target.selectionStart;render();
    const again=document.querySelector(`[data-action="${action}"]`);if(again){again.focus();again.setSelectionRange(pos,pos);}
  },250);
});
document.addEventListener('change',event=>{
  const target=event.target;
  if(target.dataset.action==='gov-eligibility'){state.filters.government.eligibility=target.value;render();}
  if(target.dataset.action==='gov-doc'){state.filters.government.doc=target.value;render();}
  if(target.dataset.action==='job-sort'){state.filters.jobs.sort=target.value;render();}
  if(target.dataset.action==='job-undated'){state.filters.jobs.undated=target.checked;render();}
});

async function saveProfile(){
  const root=$('#profile-editor');if(!root)return;
  const profile={};
  ['education','skills','languages','frameworks','projects','certifications','keywords'].forEach(field=>{
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
  const theme=((D().settings||{}).theme)||'light';
  document.documentElement.dataset.theme=theme;
}
async function boot(){
  try{
    await refresh();
  }catch(err){
    $('#page-content').innerHTML=`<div class="empty-rich"><h3>Cannot reach local services</h3><p>${esc(err.message)}</p></div>`;
    return;
  }
  applyTheme();
  const tag=$('#version-tag');if(tag&&D().version)tag.textContent='Version '+D().version;
  api('/api/visit',{method:'POST',headers:{'Content-Type':'application/json'},body:'{}'}).catch(()=>{});
  const hash=location.hash.replace('#','');
  if(hash&&NAV.some(item=>item.id===hash))state.view=hash;
  render();
  if(!state.models.length){
    api('/api/models').then(data=>{
      state.models=data.models||[];
      if(state.view==='settings')render();
    }).catch(()=>{});
  }
  const status=D().status;
  if(status&&['queued','running'].includes(status.status)&&status.id){state.activeJob=status;pollJob(status.id);}
}
window.addEventListener('hashchange',()=>{
  const hash=location.hash.replace('#','');
  if(hash&&NAV.some(item=>item.id===hash)&&hash!==state.view){state.view=hash;render();}
});
$('#theme-toggle')?.addEventListener('click',async()=>{
  const next=document.documentElement.dataset.theme==='light'?'dark':'light';
  document.documentElement.dataset.theme=next;
  try{await api('/api/settings',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({theme:next})});state.data.settings.theme=next;}
  catch(err){toast(err.message,true);}
});
$('#mobile-menu')?.addEventListener('click',()=>$('#sidebar')?.classList.toggle('open'));

boot();
