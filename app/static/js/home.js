/* ------------------------------------------------------------------ home (v4) */
const FEED_LENSES=[['foryou','For you'],['new','New'],['saved','Saved'],['public','Government & exams'],['all','All']];
const FEED_SECTIONS=[['internship','Internships'],['fresher','Fresher roles'],['remote','Remote'],['startup','Startups'],['product','Product companies'],['followed','Companies you follow'],['stretch','Stretch roles']];
function greeting(d=new Date()){const h=d.getHours();return h<5?'Good evening':h<12?'Good morning':h<17?'Good afternoon':'Good evening';}
function longDate(d=new Date()){return d.toLocaleDateString(undefined,{weekday:'long',day:'numeric',month:'long'});}
function F(){return state.feed||{items:[],summary:{},deadlines:[],news:[]};}
function homeStatus(f,picks){
  if(!(f.items||[]).length)return 'Nothing here yet. When you’re ready, run Discover and the feed will fill in.';
  if(!picks.length)return 'You’re all caught up. Nothing new needs your attention right now.';
  return picks.length===1?'One opportunity is worth your attention today.':`${picks.length} opportunities are worth your attention today.`;
}
function feedState(){return state.filters.feed=state.filters.feed||{lens:'foryou',section:'',q:'',fresh:'',elig:'',source:''};}
function feedFilter(){
  const f=feedState();
  const q=(f.q||'').toLowerCase();
  const lens=f.lens||'foryou';
  return (F().items||[]).filter(i=>{
    if(lens==='foryou'&&!(i.kind==='job'&&['strong','possible'].includes(i.tier)))return false;
    if(lens==='new'&&!(i.sections||[]).includes('new'))return false;
    if(lens==='saved'&&!['saved','applied','interview','offer'].includes(i.state))return false;
    if(lens==='public'&&i.kind==='job')return false;
    if(f.section&&!(i.sections||[]).includes(f.section))return false;
    if(!f.section&&lens!=='all'&&i.tier==='ineligible')return false;
    if(f.fresh&&((i.freshness||{}).key||'')!==f.fresh&&!(f.fresh==='week'&&['new_today','new_24h','new_3d','new_7d'].includes((i.freshness||{}).key)))return false;
    if(f.elig&&i.eligibility!==f.elig)return false;
    if(f.source&&i.source_type!==f.source)return false;
    if(q&&!`${i.title} ${i.org||''} ${i.location||''} ${(i.matched||[]).join(' ')}`.toLowerCase().includes(q))return false;
    return true;
  });
}
function todaysPicks(){
  // At most three: new strong matches first, then other strong, then fresh eligible good matches. Never stretch or saved.
  const items=(F().items||[]).filter(i=>i.kind==='job'&&!i.state&&['strong','possible'].includes(i.tier)&&!['not_eligible','uncertain'].includes(i.eligibility));
  const fresh=i=>['new_today','new_24h','new_3d'].includes((i.freshness||{}).key);
  const rank=i=>(i.tier==='strong'?2:0)+(fresh(i)?1:0);
  return items.filter(i=>i.tier==='strong'||fresh(i)).sort((a,b)=>rank(b)-rank(a)||b.priority-a.priority).slice(0,3);
}
function rowMeta(i){
  const fresh=(i.freshness||{}).label;
  const parts=[i.org,i.kind==='job'?(i.location||'').split(',')[0]:null,i.kind==='exam'?(i.event||'').replace(/_/g,' '):null,
    fresh&&!/date unknown/i.test(fresh)?fresh.replace(/^New /,'').replace(/^First seen /,'seen '):null].filter(Boolean);
  return parts.map(esc).join(' · ');
}
function rowNote(i){
  if(i.deadline_days!=null&&i.deadline_days<=7)return `<span class="note-due">${i.deadline_days===0?'Closes today':`Closes in ${i.deadline_days} day${i.deadline_days===1?'':'s'}`}</span>`;
  if(i.state&&i.state!=='dismissed')return `<span class="note-state">${esc(i.state)}</span>`;
  return '';
}
function feedRow(i){
  const key='feed-'+i.kind+'-'+i.id;
  const open=state.expanded[key];
  const score=i.kind==='job'?(i.match??''):(i.kind==='exam'?'exam':'gov');
  return `<article class="calm-row${open?' open':''}">
    <button class="calm-head" data-action="expand" data-key="${key}" aria-expanded="${!!open}">
      <span class="calm-text"><span class="calm-title">${esc(i.title||'Untitled')}</span><span class="calm-meta">${rowMeta(i)}</span></span>
      <span class="calm-side">${rowNote(i)}<span class="calm-score ${esc(i.tier||'')}" title="${i.kind==='job'?'Match with your resume':''}">${esc(score)}</span></span>
    </button>
    ${open?feedDetail(i):''}
  </article>`;
}
function pickCard(i){
  const key='feed-'+i.kind+'-'+i.id;
  const open=state.expanded[key];
  const reason=(i.matched||[]).length?`Matches ${(i.matched||[]).slice(0,3).join(', ')}`:(i.why||'').split('.')[0];
  return `<article class="pick${open?' open':''}">
    <button class="pick-head" data-action="expand" data-key="${key}" aria-expanded="${!!open}">
      <span class="pick-score">${esc(i.match??'')}</span>
      <span class="pick-title">${esc(i.title)}</span>
      <span class="calm-meta">${rowMeta(i)}</span>
      ${reason?`<span class="pick-reason">${esc(reason)}</span>`:''}
    </button>
    ${open?feedDetail(i):''}
  </article>`;
}
function feedDetail(i){
  const link=i.application_url||i.url;
  if(i.kind!=='job')return `<div class="calm-detail">${i.eligibility_label?`<p class="why">Eligibility: ${esc(i.eligibility_label)}</p>`:''}<div class="calm-actions">${link?`<a class="open-link" href="${safeUrl(link)}" target="_blank" rel="noopener">Open notice ↗</a>`:''}</div></div>`;
  const current=stateOf('job',i.id);
  const reporting=state.expanded['report-'+i.id];
  const followed=(i.sections||[]).includes('followed');
  const quiet=(action,label,extra='')=>`<button class="quiet-action" data-action="${action}" ${extra}>${label}</button>`;
  return `<div class="calm-detail">
    <p class="why">${esc(i.why||'No explanation stored yet.')}</p>
    ${(i.matched||[]).length||(i.missing||[]).length?`<p class="skills-line">${(i.matched||[]).length?`<span class="have">You have</span> ${(i.matched||[]).slice(0,6).map(esc).join(', ')}`:''}${(i.missing||[]).length?`${(i.matched||[]).length?'<br>':''}<span class="miss">Missing</span> ${(i.missing||[]).slice(0,4).map(esc).join(', ')}`:''}</p>`:''}
    <p class="facts">${[(i.lifecycle||{}).label,i.eligibility_label,i.arrangement,i.posted?'posted '+fmtDate(i.posted):null,i.sources>1?i.sources+' sources':null].filter(Boolean).map(esc).join(' · ')}</p>
    <div class="calm-actions">
      ${link?`<a class="open-link" href="${safeUrl(link)}" target="_blank" rel="noopener">${i.application_url?'Apply':'Open listing'} ↗</a>`:''}
      ${quiet('item-state',current==='saved'?'Saved ✓':'Save',`data-kind="job" data-id="${i.id}" data-state="${current==='saved'?'none':'saved'}"`)}
      ${quiet('item-state',current==='applied'?'Applied ✓':'Mark applied',`data-kind="job" data-id="${i.id}" data-state="${current==='applied'?'none':'applied'}"`)}
      ${quiet('item-state','Not for me',`data-kind="job" data-id="${i.id}" data-state="dismissed"`)}
      <details class="more-actions"><summary>More</summary><div>
        ${i.employer_id!=null?quiet('follow',followed?'Unfollow company':'Follow company',`data-id="${i.employer_id}" data-on="${followed?0:1}"`):''}
        ${quiet('expand','Report inaccurate',`data-key="report-${i.id}"`)}
        <a class="quiet-action" href="#jobs" data-view="jobs">Full breakdown</a>
        ${i.url&&i.application_url&&i.url!==i.application_url?`<a class="quiet-action" href="${safeUrl(i.url)}" target="_blank" rel="noopener">Original listing ↗</a>`:''}
      </div></details>
    </div>
    ${reporting?`<div class="report-row">${[['closed','No longer open'],['wrong_location','Wrong location'],['wrong_details','Wrong details'],['duplicate','Duplicate'],['not_a_job','Not a job'],['scam','Looks like a scam']].map(([v,l])=>`<button class="chip" data-action="report" data-id="${i.id}" data-reason="${v}">${l}</button>`).join('')}</div>`:''}
  </div>`;
}
function viewHome(){
  const f=F(),s=f.summary||{};
  const ff=feedState();
  const picks=todaysPicks();
  const pickIds=new Set(picks.map(i=>i.kind+i.id));
  const items=feedFilter().filter(i=>ff.lens!=='foryou'||!pickIds.has(i.kind+i.id));
  const limit=state.expanded.feedmore||10;
  const plan=(f.today_plan||D().today_plan||{});
  const coming=[...(f.deadlines||[]).map(d=>({title:d.title,url:d.url,when:d.deadline_days===0?'today':d.deadline_days+'d'})),
    ...(plan.schedule||[]).map(t=>({title:t.title,url:t.url,when:t.time||'today'}))].slice(0,4);
  const alerts=(f.alerts||[]).length;
  const refining=state.expanded.refine||ff.section||ff.fresh||ff.elig||ff.source||ff.q;
  const disc=f.discovery;
  const m=(disc||{}).metrics||{};
  const facts=[s.strong_matches?`<button class="fact" data-action="feed-lens" data-value="foryou">${s.strong_matches} strong</button>`:'',
    s.new_opportunities?`<button class="fact" data-action="feed-lens" data-value="new">${s.new_opportunities} new</button>`:'',
    s.deadlines_14d?`<span class="fact">${s.deadlines_14d} deadline${s.deadlines_14d===1?'':'s'} soon</span>`:''].filter(Boolean).join('<span class="dot">·</span>');
  return `<section class="calm-head-block">
      <p class="calm-date">${esc(longDate())}</p>
      <h1>${esc(greeting())}.</h1>
      <p class="calm-status">${esc(homeStatus(f,picks))}</p>
      ${facts?`<p class="calm-facts">${facts}</p>`:''}
      ${alerts?`<p class="calm-alert">${alerts} new match alert${alerts===1?'':'s'} since you last looked. <button class="quiet-action" data-action="alerts-read">Dismiss</button></p>`:''}
    </section>
    ${progressBox()}
    <div class="calm-grid">
      <div class="calm-main">
        ${picks.length?`<section class="picks" aria-label="Today's picks"><h2 class="calm-h2">Today’s picks</h2>${picks.map(pickCard).join('')}</section>`:''}
        <section aria-label="Opportunities">
          <div class="lens-bar">
            <h2 class="calm-h2">${picks.length&&ff.lens==='foryou'?'More for you':'Opportunities'}</h2>
            <div class="lenses" role="tablist">${FEED_LENSES.map(([k,l])=>`<button class="lens ${ff.lens===k?'active':''}" data-action="feed-lens" data-value="${k}" role="tab" aria-selected="${ff.lens===k}">${l}</button>`).join('')}</div>
            <button class="quiet-action" data-action="expand" data-key="refine" aria-expanded="${!!refining}">${refining?'Hide filters':'Refine'}</button>
          </div>
          ${refining?`<div class="refine">
            <input class="input" data-action="feed-q" placeholder="Role, skill, company or city" value="${esc(ff.q||'')}">
            <select class="select" data-feed="section">${optionList(FEED_SECTIONS,ff.section||'','Any kind')}</select>
            <select class="select" data-feed="fresh">${optionList([['week','Last 7 days'],['new_today','Today'],['older_open','Older, still open'],['date_unknown','Date unknown']],ff.fresh||'','Any time')}</select>
            <select class="select" data-feed="elig">${optionList([['eligible','Eligible'],['likely_eligible','Likely eligible'],['uncertain','Uncertain']],ff.elig||'','Any eligibility')}</select>
            <select class="select" data-feed="source">${optionList([['ats','Employer job board'],['career','Career page'],['feed','Public feed'],['portal','Job portal'],['web','Web search']],ff.source||'','Any source')}</select>
            <button class="quiet-action" data-action="feed-clear">Clear</button>
          </div>`:''}
          ${items.length?`<div class="calm-list">${items.slice(0,limit).map(feedRow).join('')}</div>
            ${items.length>limit?`<button class="quiet-action more" data-action="feed-more">Show ${Math.min(10,items.length-limit)} more</button>`:''}`
          :`<p class="calm-empty">${(f.items||[]).length?'Nothing here with these filters.':'Your feed is empty.'} ${(f.items||[]).length?'<button class="quiet-action" data-action="feed-clear">Clear filters</button>':'<button class="quiet-action" data-action="discover">Run Discover</button>'}</p>`}
        </section>
      </div>
      <aside class="calm-side-col">
        <section><h2 class="calm-h2">Coming up</h2>${coming.length?coming.map(c=>`<div class="side-row"><span>${c.url?`<a href="${safeUrl(c.url)}" target="_blank" rel="noopener">${esc(c.title)}</a>`:esc(c.title)}</span><span class="side-when">${esc(c.when)}</span></div>`).join(''):'<p class="calm-empty small">A quiet two weeks — no deadlines.</p>'}</section>
        ${(f.news||[]).length?`<section><h2 class="calm-h2">Worth knowing</h2>${(f.news||[]).slice(0,2).map(n=>`<div class="side-row"><span><a href="${safeUrl(n.url)}" target="_blank" rel="noopener">${esc(n.title)}</a></span></div>`).join('')}<a class="quiet-action" href="#ai-news" data-view="ai-news">More news</a></section>`:''}
        <p class="side-foot">${disc?`Updated ${esc(fmtDateTime(disc.created_at))} · ${esc(m.sources_successful??0)} of ${esc(m.sources_attempted??0)} sources answered`:'Not updated yet'}
          · <a href="#sources" data-view="sources">Coverage</a><br>
          ${(f.automation||{}).daily_refresh?`Refreshes daily at ${esc((f.automation||{}).refresh_time||'08:00')}`:`Daily refresh is off · <button class="quiet-action inline" data-action="auto-on">Turn on</button>`}</p>
      </aside>
    </div>`;
}
function deadlineList(list,compact){
  if(!list.length)return '<div class="mini-empty">No dated deadlines in the next two weeks.</div>';
  return list.map(i=>`<div class="mini-row"><span>${i.url?`<a href="${safeUrl(i.url)}" target="_blank" rel="noopener">${esc(i.title)}</a>`:esc(i.title)}${compact?'':` <span class="mini-sub">${esc(i.org||'')}</span>`}</span><span class="due ${i.deadline_days<=3?'due-soon':''}">${i.deadline_days===0?'today':i.deadline_days+'d'}</span></div>`).join('');
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
const RUN_STATE_CLASS={no_results:'status-warn',successful:'status-ok',partial:'status-warn',failed:'status-bad',access_restricted:'status-bad',not_attempted:'view-note',disabled:'view-note',backing_off:'status-warn',not_configured:'view-note'};
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
        ${d?`${metric2('Sources configured',m.sources_configured)}${metric2('Sources attempted',m.sources_attempted)}${metric2('Successful',m.sources_successful)}${metric2('Partially successful',m.sources_partial)}${metric2('Searched, no results',m.sources_no_results)}${metric2('Failed or access restricted',m.sources_restricted)}`:'<div class="mini-empty">Run Discover to populate this.</div>'}
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
