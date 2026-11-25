/* ------------------------------------------------------------------ events */
/* View registry: built here, in the last script, because it names functions from every view file
   (function hoisting does not cross <script> files). */
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
    else if(action==='feed-section'){const f=feedState();f.lens='all';f.section=button.dataset.value;state.expanded.feedmore=0;render();}
    else if(action==='feed-lens'){const f=feedState();f.lens=button.dataset.value;f.section='';state.expanded.feedmore=0;render();}
    else if(action==='feed-more'){state.expanded.feedmore=(state.expanded.feedmore||10)+10;render();}
    else if(action==='go'){setView(button.dataset.value);}
    else if(action==='feed-clear'){state.filters.feed={lens:(state.filters.feed||{}).lens||'foryou',section:'',q:'',fresh:'',elig:'',source:''};state.expanded.refine=false;render();}
    else if(action==='follow'){await api(`/api/employers/${button.dataset.id}/follow`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({followed:button.dataset.on==='1'})});
      await refresh();render();toast(button.dataset.on==='1'?'Following this company':'Unfollowed');}
    else if(action==='report'){await api(`/api/listings/${button.dataset.id}/report`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({reason:button.dataset.reason})});
      await refresh();render();toast('Reported — hidden from your feed (kept in the database)');}
    else if(action==='sources-cat'){state.filters.sourcesCat=button.dataset.value;render();}
    else if(action==='source-toggle'){const r=await api(`/api/sources/${encodeURIComponent(button.dataset.id)}/enabled`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({enabled:button.dataset.on==='1'})});
      state.sources=r.sources||state.sources;render();}
    else if(action==='monitor-run'){
      const r=await api('/api/monitoring/run',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({kind:button.dataset.kind||'auto'})});
      toast(r.queued?`Monitoring batch queued (${r.kind})`:'Nothing is due right now');
      setTimeout(async()=>{await refresh();render();},1800);
    }
    else if(action==='company-follow'){
      const r=await api(`/api/companies/${button.dataset.id}/update`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({followed:button.dataset.on==='1'})});
      await refresh();render();toast(button.dataset.on==='1'?'Following this company':'Unfollowed');
    }
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
    else if(action==='key-save'||action==='key-test'||action==='key-remove'){await apiKeyAction(action,button.dataset.provider);}
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
    else if(kind==='eligibility'){
      const value=key=>String(data.get(key)||'').trim();
      const number=key=>{const raw=value(key);return raw===''?null:Number(raw);};
      const profile={
        date_of_birth:value('date_of_birth')||null,age:number('age'),age_as_of:value('age_as_of')||null,
        category:value('category')||null,gender:value('gender')||null,pwd:data.has('pwd'),
        ex_serviceman:data.has('ex_serviceman'),nationality:value('nationality')||null,
        domicile_state:value('domicile_state')||null,
        education:{degree:value('degree'),branch:value('branch'),university:value('university'),
          graduation_year:number('graduation_year'),final_year:data.has('final_year'),
          percentage:number('percentage'),cgpa:number('cgpa'),cgpa_scale:number('cgpa_scale'),backlogs:number('backlogs')},
        experience:{full_time_months:number('full_time_months'),internship_months:number('internship_months')},
        gate:{appeared:data.has('gate_appeared'),paper:value('gate_paper')||null,year:number('gate_year'),
          score:number('gate_score'),rank:number('gate_rank'),valid_until:value('gate_valid_until')||null},
        preferences:{sectors:['psu','government','private'].filter(s=>data.has('sector:'+s)),
          locations:splitList(value('locations')),min_salary:number('min_salary'),
          employment_types:splitList(value('employment_types'))},
      };
      const result=await api('/api/eligibility',{method:'POST',headers:{'Content-Type':'application/json'},
        body:JSON.stringify({profile})});
      await refresh();render();
      toast(`Eligibility profile saved; ${result.reevaluated?.notices??0} notice(s) and ${result.reevaluated?.exams??0} exam(s) re-evaluated`);
    }
    else if(kind==='missed'){
      const url=String(data.get('url')||'').trim();
      const title=String(data.get('title')||'').trim();
      if(!url&&!title){toast('Give the link or title of the missed opportunity',true);return;}
      await api('/api/missed',{method:'POST',headers:{'Content-Type':'application/json'},
        body:JSON.stringify({url:url||null,title:title||null,kind:'missed',
          reason:String(data.get('reason')||'').trim()||null,note:String(data.get('note')||'').trim()||null})});
      await refresh();render();toast('Reported. It is stored locally for source and rule fixes.');
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
  if(target.dataset.action==='exam-eligibility'){state.filters.exams.eligibility=target.value;render();}
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
    const c=$('#connection');if(c){c.textContent='';c.classList.remove('offline');}}).catch(()=>{const c=$('#connection');if(c){c.textContent='Offline';c.classList.add('offline');}});},60000);
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
