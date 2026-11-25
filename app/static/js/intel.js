/* -------------------------------------------------------------- government */
function viewGovernment(){
  const notices=D().notices||[];
  const f=state.filters.government;
  const filtered=notices.filter(notice=>{
    if(f.eligibility!=='all'&&(notice.eligibility_bucket||'undecided')!==f.eligibility)return false;
    if(f.doc!=='all'&&(notice.document_type||'')!==f.doc)return false;
    return true;
  });
  const eligibility=[['all','All eligibility'],['eligible','Eligible for me'],['likely','Likely eligible'],
    ['needs_fact','Needs one fact'],['uncertain','Uncertain'],['not_eligible','Not eligible'],['undecided','Not evaluated']];
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
  const verdict=notice.eligibility||{};
  const bucket=notice.eligibility_bucket||'undecided';
  const missing=(verdict.missing_facts||[]).slice(0,3);
  return `<article class="item-card">
    <div class="item-head">
      <div><h3 class="item-title">${notice.notification_url?`<a href="${safeUrl(notice.notification_url)}" target="_blank" rel="noopener">${esc(notice.post_name||notice.organization||'Recruitment notice')}</a>`:esc(notice.post_name||notice.organization||'Recruitment notice')}</h3>
        <div class="item-sub">${esc(notice.organization||'Organisation not stated')}${notice.discipline?' · '+esc(notice.discipline):''}${notice.advertisement_number?' · Adv. '+esc(notice.advertisement_number):''}</div></div>
      <div class="chips">${badge(notice.status||'unverified')}${badge(bucket,(verdict.status_label||'Not evaluated'))}${notice.lead?badge('unverified','Discovery lead'):''}</div>
    </div>
    ${verdict.summary?`<div class="reason">${esc(verdict.summary)}</div>`:''}
    ${missing.length?`<div class="reason status-warn">Missing fact${missing.length>1?'s':''}: ${missing.map(esc).join(' · ')}</div>`:''}
    ${(verdict.failed_rules||[]).length?`<div class="reason status-bad">${esc(verdict.failed_rules[0])}</div>`:''}
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
      ${kv('Official source',notice.source_name)}
    </div>
    ${evidence(notice)}
    <div class="item-actions">
      ${notice.document_url?`<a class="link-button" href="${safeUrl(notice.document_url)}" target="_blank" rel="noopener">Official notification</a>`:''}
      ${notice.notification_url?`<a class="link-button" href="${safeUrl(notice.notification_url)}" target="_blank" rel="noopener">Notice page</a>`:''}
      ${notice.application_url&&notice.application_url!==notice.notification_url?`<a class="link-button primary" href="${safeUrl(notice.application_url)}" target="_blank" rel="noopener">Apply / portal</a>`:''}
      ${stateButtons('notice',notice.id,current)}
    </div>
  </article>`;
}

/* ------------------------------------------------------------------ exams */
function viewExams(){
  const events=D().exams||[];
  const f=state.filters.exams;
  const watch=(D().watchlists||{}).exam||[];
  const filtered=events.filter(event=>!f.eligibility||f.eligibility==='all'||
    (event.eligibility_bucket||'undecided')===f.eligibility);
  const buckets=[['all','All eligibility'],['eligible','Eligible for me'],['likely','Likely eligible'],
    ['needs_fact','Needs one fact'],['uncertain','Uncertain'],['not_eligible','Not eligible']];
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
    </form>
    <select class="select" data-action="exam-eligibility" style="width:auto">${buckets.map(([v,l])=>`<option value="${v}" ${(f.eligibility||'all')===v?'selected':''}>${l}</option>`).join('')}</select></div>` +
    (filtered.length?`<div class="list-grid">${filtered.map(examCard).join('')}</div>`:emptyRich('No examination events stored',
      'Add examinations to your watchlist, then run a search. Events are extracted only when an official source states a date; missing dates are never generated from model knowledge.',
      `<button class="primary-button" data-action="quick-search" data-category="exams" data-query="">Search exams</button>`));
}
function examCard(event){
  const current=stateOf('exam',event.id);
  const verdict=event.eligibility||{};
  const bucket=event.eligibility_bucket||'undecided';
  return `<article class="item-card">
    <div class="item-head">
      <div><h3 class="item-title">${event.notification_url?`<a href="${safeUrl(event.notification_url)}" target="_blank" rel="noopener">${esc(event.exam_name||'Examination')}</a>`:esc(event.exam_name||'Examination')}</h3>
        <div class="item-sub">${esc(event.organization||'Conducting organisation not stated')} · ${esc(event.event_type||'event')}</div></div>
      <div class="chips">${badge(event.date_status||'unverified')}${verdict.status?badge(bucket,verdict.status_label):''}</div>
    </div>
    ${verdict.summary?`<div class="reason">${esc(verdict.summary)}</div>`:''}
    ${(verdict.missing_facts||[]).length?`<div class="reason status-warn">Missing fact: ${verdict.missing_facts.slice(0,3).map(esc).join(' · ')}</div>`:''}
    <div class="item-meta">${event.event_date?meta(fmtDate(event.event_date)):meta('Date unavailable')}${event.event_date?meta(event.event_date):''}</div>
    ${evidence(event)}
    <div class="item-actions">
      ${event.notification_url?`<a class="link-button" href="${safeUrl(event.notification_url)}" target="_blank" rel="noopener">Official source</a>`:''}
      ${event.application_url&&event.application_url!==event.notification_url?`<a class="link-button primary" href="${safeUrl(event.application_url)}" target="_blank" rel="noopener">Application portal</a>`:''}
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
      <div><h3 class="item-title"><a href="${safeUrl(item.original_url||'#')}" target="_blank" rel="noopener">${esc(item.title||'Untitled')}</a></h3>
        <div class="item-sub">${esc(item.publisher||'Publisher not stated')}${item.authors?' · '+esc(item.authors):''}${item.published_date?' · '+esc(fmtDate(item.published_date)):''}</div></div>
      <div class="chips">${badge(item.freshness||'date_unavailable')}${kind==='paper'?badge(item.peer_reviewed||'not_verified'):''}</div>
    </div>
    ${item.summary?`<div class="item-body">${esc(plain(item.summary).slice(0,520))}</div>`:''}
    ${item.why_it_matters?`<div class="reason"><b>Why it matters:</b> ${esc(item.why_it_matters)}</div>`:''}
    <div class="item-meta">
      ${item.region?meta('Region: '+item.region):''}
      ${item.topic?meta('Topic: '+item.topic):''}
      ${item.code_url?`<a class="meta" href="${safeUrl(item.code_url)}" target="_blank" rel="noopener">Code</a>`:''}
      ${item.dataset_url?`<a class="meta" href="${safeUrl(item.dataset_url)}" target="_blank" rel="noopener">Dataset</a>`:''}
    </div>
    ${evidence(item)}
    <div class="item-actions">
      <a class="link-button primary" href="${safeUrl(item.original_url||'#')}" target="_blank" rel="noopener">Open source</a>
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
