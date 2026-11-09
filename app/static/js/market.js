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
        <div class="market-recent-head"><a class="source-title" href="${safeUrl(job.original_url||'#')}" target="_blank" rel="noopener">${esc(job.title||'Untitled role')}</a>${badge(job.status||'unverified')}</div>
        <div class="item-meta">${meta(job.employer||'Employer not stated')}${meta(job.location||'Location not stated')}${job.posted_date?meta('Posted '+ageLabel(job.posted_date)):meta('Date unverified')}${job.source_platform?meta(job.source_platform):''}</div>
      </div>`).join('')}</div>`:emptyRich('No listings to chart yet',
        'Run a market scan. The page reads only stored listings and never invents skills, roles or dates.',
        `<button class="primary-button" data-action="market-scan">Scan the market</button>`)}
    </div>`;
}
