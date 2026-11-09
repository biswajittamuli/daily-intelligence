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
        return item.original_url?`<a class="meta" href="${safeUrl(item.original_url)}" target="_blank" rel="noopener">${esc(label).slice(0,80)}</a>`:meta(label);
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
      ${(changes.new_items||[]).length?`<div class="source-list">${changes.new_items.slice(0,10).map(item=>`<div class="source-card"><a class="source-title" href="${safeUrl(item.url)}" target="_blank" rel="noopener">${esc(item.title||'item')}</a></div>`).join('')}</div>`:'<div class="empty-state">No new items compared with the previous briefing.</div>'}
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
      <div class="item-title"><a href="${safeUrl(job.original_url||'#')}" target="_blank" rel="noopener">${esc(job.title||'Untitled role')}</a> ${isNew(job)?'<span class="badge new">new</span>':''}</div>
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
      <a class="link-button" href="${safeUrl(job.original_url||'#')}" target="_blank" rel="noopener">Original listing</a>
      ${job.application_url?`<a class="link-button primary" href="${safeUrl(job.application_url)}" target="_blank" rel="noopener">Official application page</a>`:''}
      ${job.employer_url?`<a class="link-button" href="${safeUrl(job.employer_url)}" target="_blank" rel="noopener">Employer site</a>`:''}
      ${(job.sources||[]).filter(s=>s.url!==job.original_url).map(s=>`<a class="link-button" href="${safeUrl(s.url)}" target="_blank" rel="noopener">Also on ${esc(s.via||s.platform||'source')}</a>`).join('')}
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
      ${sources.map(s=>`<tr><td><a href="${safeUrl(s.url)}" target="_blank" rel="noopener">${esc(s.portal||s.platform||hostOf(s.url))}</a>${s.url===job.original_url?' <span class="view-note">(canonical)</span>':''}</td><td>${esc(s.via||s.kind||'')}</td><td class="view-note">${esc(s.method||'')}</td><td class="view-note">${esc(s.policy==='search_results_only'?'search results only — not fetched':s.policy==='provider_fetch'?'fetched only via search provider':'')}</td><td class="view-note">${esc(s.retrieved_at?fmtDate(s.retrieved_at):'')}</td></tr>`).join('')}
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
        ${ex?`<div class="table-wrap section-space exclusion-scroll"><table class="data-table"><thead><tr><th>Result</th><th>Source</th><th>Detail</th></tr></thead><tbody>${ex.loading?'<tr><td colspan="3">Loading…</td></tr>':(ex.items||[]).map(e=>`<tr><td>${e.url?`<a href="${safeUrl(e.url)}" target="_blank" rel="noopener">${esc(e.title||e.url)}</a>`:esc(e.title||'')}${e.employer?`<div class="view-note">${esc(e.employer)}</div>`:''}</td><td class="view-note">${esc(e.source||'')}</td><td class="view-note">${esc(e.detail||e.stage||'')}</td></tr>`).join('')}</tbody></table></div><div class="view-note">${esc(ex.total??0)} result(s) for “${esc(ex.reason)}”${(ex.items||[]).length<(ex.total||0)?` — showing first ${esc(ex.items.length)}`:''}.</div>`:''}
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
      <div class="item-title">${item.job_url?`<a href="${safeUrl(item.job_url)}" target="_blank" rel="noopener">${esc(item.role)}</a>`:esc(item.role)}</div>
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
