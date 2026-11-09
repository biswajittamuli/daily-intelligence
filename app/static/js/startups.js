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
          <div class="market-recent-head"><a class="source-title" href="${safeUrl((src[0]||{}).url||s.source_url||'#')}" target="_blank" rel="noopener">${esc(s.title||s.company_name)}</a><span class="dim sig">${esc(SIGNAL_LABEL[s.signal_type]||s.signal_type)}</span></div>
          <div class="item-meta">${meta(s.company_name)}${s.amount?meta(s.amount):''}${meta(s.signal_date?fmtDate(s.signal_date):'date not stated')}${src.length>1?meta(src.length+' articles'):''}</div>
          ${src.length?`<div class="view-note">${src.slice(0,5).map(x=>`<a href="${safeUrl(x.url)}" target="_blank" rel="noopener">${esc(x.publisher||hostOf(x.url))}</a>`).join(' · ')}</div>`:''}
        </div>`;}).join('')}</div>`:'<div class="empty-state">No signals yet. Run “Discover employers”.</div>'}
      </div>
      <div class="panel">
        <div class="panel-head"><h3 class="panel-title">Indian startup news</h3><span class="panel-kicker">funding · hiring · launches</span></div>
        ${news.length?`<div class="source-list">${news.slice(0,12).map(n=>`<div class="source-card"><a class="source-title" href="${safeUrl(n.original_url)}" target="_blank" rel="noopener">${esc(n.title)}</a><div class="item-meta">${meta(n.publisher||'')}${meta(n.topic||'')}${n.published_date?meta(fmtDate(n.published_date)):''}</div></div>`).join('')}</div>`
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
        return `<tr><td><b>${e.website?`<a href="${safeUrl(e.website)}" target="_blank" rel="noopener">${esc(e.name)}</a>`:esc(e.name)}</b>${newSince&&e.first_discovered>newSince?' <span class="badge new">new</span>':''}${e.industry?`<div class="view-note">${esc(e.industry)}</div>`:''}</td>
          <td>${esc(e.classification||'unknown')}${e.country?' · '+esc(e.country):''}</td>
          <td>${e.career_url?`<a href="${safeUrl(e.career_url)}" target="_blank" rel="noopener">career page</a>`:''}${e.ats_provider?`${e.career_url?' · ':''}${esc(e.ats_provider)}${e.ats_slug?' (readable)':''}`:''}<div class="view-note">${esc(e.career_status||'')}</div>${careerDiscoveryCell(e)}</td>
          <td class="num">${jobs.length?`<button class="link-button" data-action="startup-jobs" data-name="${esc(e.name)}">${jobs.length} stored</button>`:''}${e.open_jobs?`<div class="view-note">${esc(e.open_jobs)} on board</div>`:''}${!jobs.length&&!e.open_jobs?'–':''}</td>
          <td>${e.signal_count?esc(e.signal_count):''}${funding?`<div class="view-note">${esc(funding.amount||funding.title||'funding')}</div>`:''}</td>
          <td class="view-note">${esc((e.discovery_sources||[]).filter(s=>!s.startsWith('category:')).slice(0,2).join(', '))}</td>
          <td class="view-note">${esc(fmtDate(e.last_career_check||e.last_discovery))}</td></tr>`;}).join('')}
      </tbody></table></div>${list.length>60&&!f.all?'<button class="link-button section-space" data-action="startup-all">Show all '+list.length+'</button>':''}`
      :emptyRich('No employers discovered yet','Run “Discover employers”. The engine searches startup publications (YourStory, Inc42, Entrackr…), directories and accelerators (Startup India, YC, Techstars…), VC portfolios and job platforms, then resolves each company’s website, career page and job board.','')}
    </div>
    ${last&&(last.career_listings||[]).length?`<div class="panel section-space"><div class="panel-head"><h3 class="panel-title">Vacancy links found on career pages</h3><span class="panel-kicker">last discovery · not yet ranked</span></div>
      <div class="source-list">${last.career_listings.slice(0,30).map(l=>`<div class="source-card"><a class="source-title" href="${safeUrl(l.url)}" target="_blank" rel="noopener">${esc(l.title||l.url)}</a><div class="item-meta">${meta(l.employer)}</div></div>`).join('')}</div>
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
