/* ------------------------------------------------------------- briefing v2 */
function actionableBriefing(a){
  const sections=(a.sections||[]);
  const total=a.total_new||0;
  return `<div class="banner section-space">${total?`${esc(total)} new item${total===1?'':'s'} since the previous briefing`:'Nothing new since the previous briefing'}${a.since?` (${esc(fmtDateTime(a.since))})`:''}. Older items that are still relevant are counted, not repeated. Closed and expired listings are never suggested.</div>
  <div class="briefing-grid section-space">${sections.map(s=>`<div class="panel brief-${esc(s.key)}">
    <div class="panel-head"><h3 class="panel-title">${esc(s.title)}</h3><span class="panel-kicker">${s.new_count?`<span class="badge new">${esc(s.new_count)} new</span>`:''}${s.still_relevant?` +${esc(s.still_relevant)} earlier`:''}</span></div>
    ${s.note?`<div class="view-note">${esc(s.note)}</div>`:''}
    ${(s.items||[]).length?`<div class="brief-list">${s.items.map(i=>`<div class="brief-item">${i.url?`<a href="${safeUrl(i.url)}" target="_blank" rel="noopener">${esc(i.title||'item')}</a>`:`<b>${esc(i.title||'item')}</b>`}${i.detail?`<div class="view-note">${esc(i.detail)}</div>`:''}</div>`).join('')}</div>`:'<div class="empty-state">Nothing new.</div>'}
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
