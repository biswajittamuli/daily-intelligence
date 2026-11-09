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
    appearancePanel() + apiKeysPanel() + `<div class="panel section-space">
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

/* API keys: pasted keys are stored locally (owner-only file), never sent back in full, and used immediately. */
async function loadApiKeys(){
  try{state.apiKeys=await api('/api/keys');}catch(e){state.apiKeys={error:e.message,providers:[]};}
  if(state.view==='settings')render();
}
function apiKeysPanel(){
  if(state.apiKeys===undefined){state.apiKeys=null;loadApiKeys();}
  const data=state.apiKeys;
  const checks=state.keyChecks||{};
  const body=!data?'<div class="view-note">Loading…</div>':data.error?`<div class="view-note">Could not load key status: ${esc(data.error)}</div>`:
    (data.providers||[]).map(p=>{
      const check=checks[p.id];
      const status=p.configured?(p.keys.every(k=>k.source==='environment')?'Set from environment':'Saved'):'Not configured';
      return `<div class="settings-section key-card">
        <div class="panel-head"><h4 class="panel-title">${esc(p.name)}</h4><span class="panel-kicker ${p.configured?'ok':''}">${esc(status)}</span></div>
        <div class="view-note">${esc(p.purpose)}<br>${esc(p.cost)} · Sends: ${esc(p.sends)} · <a href="${safeUrl(p.signup)}" target="_blank" rel="noopener">Get a key ↗</a></div>
        <div class="settings-grid">${p.keys.map(k=>`<div class="field"><label for="key-${esc(k.name)}">${esc(k.label)}${k.hint?` <small>(current: ${esc(k.hint)})</small>`:''}</label>
          <input class="input" id="key-${esc(k.name)}" data-key-name="${esc(k.name)}" data-provider="${esc(p.id)}" type="password" autocomplete="off" spellcheck="false" placeholder="${k.set?'Paste a new value to replace':'Paste here'}"></div>`).join('')}</div>
        <div class="field-actions">
          <button class="primary-button" type="button" data-action="key-save" data-provider="${esc(p.id)}">Save &amp; test</button>
          ${p.configured?`<button class="quiet-button" type="button" data-action="key-test" data-provider="${esc(p.id)}">Test</button>`:''}
          ${p.keys.some(k=>k.source==='saved')?`<button class="danger-button" type="button" data-action="key-remove" data-provider="${esc(p.id)}">Remove</button>`:''}
        </div>
        ${check?`<p class="${check.ok?'key-ok':'key-error'}" role="status">${check.pending?'Testing…':esc(check.message)}</p>`:''}
      </div>`;}).join('');
  return `<div class="panel section-space" id="api-keys">
    <div class="panel-head"><h3 class="panel-title">API keys</h3><span class="panel-kicker">optional · stored only on this computer</span></div>
    <div class="view-note">Each key is tested as soon as you save it and used from the next discovery run, with no restart. Keys are kept in a local file only you can read and are never shown again in full.</div>
    ${body}
  </div>`;
}
async function apiKeyAction(action,provider){
  state.keyChecks=state.keyChecks||{};
  const headers={'Content-Type':'application/json'};
  try{
    if(action==='key-save'){
      const values={};
      document.querySelectorAll(`input[data-provider="${CSS.escape(provider)}"]`).forEach(i=>{if(i.value.trim())values[i.dataset.keyName]=i.value.trim();});
      if(!Object.keys(values).length){toast('Paste the key first',true);return;}
      state.keyChecks[provider]={pending:true};render();
      const r=await api('/api/keys',{method:'POST',headers,body:JSON.stringify({provider,values})});
      state.apiKeys=r;state.keyChecks[provider]=r.check;
      document.querySelectorAll(`input[data-provider="${CSS.escape(provider)}"]`).forEach(i=>{i.value='';});
      toast(r.check.ok?'Key saved and working':r.check.rejected?'Key rejected by the provider — not saved':'Key saved, but the test could not complete',!r.check.ok);
    }else if(action==='key-test'){
      state.keyChecks[provider]={pending:true};render();
      const r=await api('/api/keys/test',{method:'POST',headers,body:JSON.stringify({provider})});
      state.apiKeys=r;state.keyChecks[provider]=r.check;
    }else if(action==='key-remove'){
      if(!confirm('Remove the saved key? Discovery will stop using this source until you add a key again.'))return;
      state.apiKeys=await api('/api/keys/remove',{method:'POST',headers,body:JSON.stringify({provider})});
      delete state.keyChecks[provider];toast('Key removed');
    }
  }catch(e){state.keyChecks[provider]={ok:false,message:e.message};toast(e.message,true);}
  render();
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

