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
        <span class="slot-title">${item.url?`<a href="${safeUrl(item.url)}" target="_blank" rel="noopener">${esc(item.title)}</a>`:esc(item.title)}${item.overdue?' <span class="badge expired">overdue</span>':''}${item.recurrence?` <span class="view-note">↻ ${esc(recurrenceLabel(item.recurrence))}</span>`:''}</span>
        <span>${item.task_id?`<button class="link-button" data-action="toggle-task" data-id="${item.task_id}">${item.done?'Undo':'Done'}</button>`:catBadge(item.category)}</span>
      </div>`).join('')}</div>`:'<div class="empty-state">Nothing scheduled for today. Write tasks in your notes, e.g. “walk my dog every evening”.</div>'}
    </div>
    <div class="panel">
      <div class="panel-head"><h3 class="panel-title">Suggested next steps</h3><span class="panel-kicker">from your jobs & skills</span></div>
      ${suggestions.length?suggestions.map(s=>`<div class="suggestion"><span class="suggestion-icon ${esc(s.kind)}">${s.kind==='learn'?'✎':s.kind==='follow_up'?'↻':'➚'}</span><div><b>${s.url?`<a href="${safeUrl(s.url)}" target="_blank" rel="noopener">${esc(s.title)}</a>`:esc(s.title)}</b><div class="view-note">${esc(s.detail||'')}</div></div></div>`).join(''):'<div class="empty-state">Run a market scan and upload a resume to get job and learning suggestions.</div>'}
      ${!compact&&(plan.deadlines||[]).length?`<div class="section-title section-space">Upcoming deadlines (14 days)</div><div class="timeline">${plan.deadlines.map(d=>`<div class="timeline-row"><div class="timeline-date">${esc(fmtDate(d.date))}</div><div class="timeline-body">${d.url?`<a href="${safeUrl(d.url)}" target="_blank" rel="noopener"><b>${esc(d.title)}</b></a>`:`<b>${esc(d.title)}</b>`}<br>${esc(d.kind)}</div></div>`).join('')}</div>`:''}
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
