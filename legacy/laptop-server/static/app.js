/* Coach — single-page app. No framework, no build step. */
const $ = (s, el = document) => el.querySelector(s);
const view = $('#view');
const S = { status: null, planWeek: null, logTab: 'lifts', liftSel: null, metricSel: null };

const TYPES = ['run', 'strength', 'bike', 'swim', 'mobility', 'walk', 'rest', 'other'];
const TYPE_COLORS = { run: '#4fa3ff', strength: '#ff6b3d', bike: '#b38cff', swim: '#2ed3c6', walk: '#8fb36b', mobility: '#f39bd0', other: '#7d8696' };
const SPARK = '<svg class="spark" viewBox="0 0 24 24" fill="currentColor"><path d="M12 2l1.8 6.2L20 10l-6.2 1.8L12 18l-1.8-6.2L4 10l6.2-1.8z"/><path d="M19 15l.8 2.2L22 18l-2.2.8L19 21l-.8-2.2L16 18l2.2-.8z"/></svg>';
const GEAR = '<svg viewBox="0 0 24 24"><circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.7 1.7 0 0 0 .3 1.8l.1.1a2 2 0 1 1-2.8 2.8l-.1-.1a1.7 1.7 0 0 0-1.8-.3 1.7 1.7 0 0 0-1 1.5V21a2 2 0 1 1-4 0v-.1a1.7 1.7 0 0 0-1.1-1.5 1.7 1.7 0 0 0-1.8.3l-.1.1a2 2 0 1 1-2.8-2.8l.1-.1a1.7 1.7 0 0 0 .3-1.8 1.7 1.7 0 0 0-1.5-1H3a2 2 0 1 1 0-4h.1a1.7 1.7 0 0 0 1.5-1.1 1.7 1.7 0 0 0-.3-1.8l-.1-.1a2 2 0 1 1 2.8-2.8l.1.1a1.7 1.7 0 0 0 1.8.3H9a1.7 1.7 0 0 0 1-1.5V3a2 2 0 1 1 4 0v.1a1.7 1.7 0 0 0 1 1.5 1.7 1.7 0 0 0 1.8-.3l.1-.1a2 2 0 1 1 2.8 2.8l-.1.1a1.7 1.7 0 0 0-.3 1.8V9a1.7 1.7 0 0 0 1.5 1H21a2 2 0 1 1 0 4h-.1a1.7 1.7 0 0 0-1.5 1z"/></svg>';

/* ---------- utils ---------- */
const esc = s => String(s ?? '').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
const iso = d => { const x = new Date(d); x.setMinutes(x.getMinutes() - x.getTimezoneOffset()); return x.toISOString().slice(0, 10); };
const todayIso = () => iso(new Date());
const addDays = (s, n) => { const d = new Date(s + 'T12:00'); d.setDate(d.getDate() + n); return iso(d); };
const monday = s => { const d = new Date((s || todayIso()) + 'T12:00'); d.setDate(d.getDate() - ((d.getDay() + 6) % 7)); return iso(d); };
const dname = (s, o = { weekday: 'short' }) => new Date(s + 'T12:00').toLocaleDateString(undefined, o);
const mins = m => !m ? '' : m < 60 ? `${Math.round(m)} min` : `${Math.floor(m / 60)}h ${String(Math.round(m % 60)).padStart(2, '0')}`;
const km = m => m ? (m / 1000).toFixed(m >= 10000 ? 1 : 2) + ' km' : '';
const num = v => v == null ? '–' : (Math.round(v * 10) / 10).toString();
const typeOf = t => { t = (t || 'other').toLowerCase(); for (const k of ['run', 'strength', 'bike', 'swim', 'walk', 'mobility', 'rest']) if (t.includes(k)) return k; if (t.includes('cycl')) return 'bike'; if (t.includes('weight')) return 'strength'; return 'other'; };

async function api(method, path, body) {
  const r = await fetch(path, {
    method, headers: { 'Content-Type': 'application/json', 'X-Passcode': localStorage.getItem('pc') || '' },
    body: body ? JSON.stringify(body) : undefined,
  });
  if (r.status === 401) { askPasscode(); throw new Error('Passcode required'); }
  const data = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(data.error || `HTTP ${r.status}`);
  return data;
}

function toast(msg, err) {
  const t = $('#toast');
  t.textContent = msg; t.className = 'toast on' + (err ? ' err' : '');
  clearTimeout(t._h); t._h = setTimeout(() => t.className = 'toast', err ? 4500 : 2200);
}

function openSheet(html, onMount) {
  const sh = $('#sheet');
  sh.innerHTML = '<div class="grab"></div>' + html;
  $('#backdrop').classList.add('on'); sh.classList.add('on');
  onMount && onMount(sh);
}
function closeSheet() { $('#sheet').classList.remove('on'); $('#backdrop').classList.remove('on'); }
$('#backdrop').onclick = closeSheet;

function formData(root) {
  const o = {};
  root.querySelectorAll('[name]').forEach(el => {
    let v = el.value;
    if (el.type === 'number') v = v === '' ? null : Number(v);
    else if (v === '' && el.dataset.nullable !== undefined) v = null;
    o[el.name] = v;
  });
  return o;
}

async function busy(btn, fn) {
  const html = btn.innerHTML; btn.disabled = true; btn.innerHTML = '<span class="loading"></span>';
  try { return await fn(); } catch (e) { toast(e.message, true); } finally { btn.disabled = false; btn.innerHTML = html; }
}

function md(text) {
  return esc(text).split('\n').map(l => {
    if (/^#{1,4}\s/.test(l)) return `<h4>${l.replace(/^#+\s/, '')}</h4>`;
    return l.replace(/\*\*(.+?)\*\*/g, '<b>$1</b>');
  }).join('\n').replace(/<\/h4>\n/g, '</h4>');
}

function askPasscode() {
  openSheet(`<h3>Enter passcode</h3><label class="f"><input id="pc" type="password" inputmode="numeric" autocomplete="current-password"></label>
    <button class="btn primary block" id="pcgo">Unlock</button>`, sh => {
    $('#pcgo', sh).onclick = () => { localStorage.setItem('pc', $('#pc', sh).value); closeSheet(); render(); };
  });
}

/* ---------- router ---------- */
const VIEWS = { today: renderToday, plan: renderPlan, log: renderLog, trends: renderTrends, goals: renderGoals };
async function render() {
  const tab = (location.hash || '#today').slice(1);
  document.querySelectorAll('.tabbar a').forEach(a => a.classList.toggle('on', a.dataset.tab === tab));
  try { await (VIEWS[tab] || renderToday)(); } catch (e) { if (e.message !== 'Passcode required') view.innerHTML = `<div class="card">${esc(e.message)}</div>`; }
}
window.addEventListener('hashchange', () => { closeSheet(); window.scrollTo(0, 0); render(); });

function header(title, sub, right = '') {
  return `<header class="top"><div><div class="sub">${esc(sub)}</div><h1>${esc(title)}</h1></div>${right}</header>`;
}

/* ---------- workout rendering ---------- */
function woHtml(w, opts = {}) {
  const t = typeOf(w.type);
  const meta = [mins(w.duration_min), w.intensity, opts.showDate ? dname(w.date, { weekday: 'short', day: 'numeric' }) : ''].filter(Boolean).join(' · ');
  return `<div class="wo ${w.status}" data-wo="${w.id}">
    <div class="bar t-${t}"></div>
    <div class="grow">
      <div class="row between"><span class="t">${esc(w.title)}</span>
        <span class="row" style="gap:5px">${w.source === 'ai' ? '<span class="tag ai">AI</span>' : ''}${w.status === 'done' ? `<span class="tag done">Done${w.rpe ? ' · RPE ' + w.rpe : ''}</span>` : w.status === 'skipped' ? '<span class="tag">Skipped</span>' : ''}</span></div>
      ${meta ? `<div class="meta">${esc(meta)}</div>` : ''}
      ${w.details && opts.details !== false ? `<div class="det">${esc(w.details)}</div>` : ''}
      ${opts.actions && w.status === 'planned' && t !== 'rest' ? `<div class="btn-row" style="margin-top:10px"><button class="btn sm primary" data-complete="${w.id}">Mark done</button><button class="btn sm ghost" data-skip="${w.id}">Skip</button></div>` : ''}
    </div></div>`;
}

function bindWorkouts(root, items, reload) {
  root.querySelectorAll('[data-wo]').forEach(el => el.onclick = e => {
    if (e.target.closest('button')) return;
    const w = items.find(x => x.id == el.dataset.wo); if (w) workoutSheet(w, reload);
  });
  root.querySelectorAll('[data-complete]').forEach(b => b.onclick = () => completeSheet(items.find(x => x.id == b.dataset.complete), reload));
  root.querySelectorAll('[data-skip]').forEach(b => b.onclick = async () => { await api('PUT', '/api/planned/' + b.dataset.skip, { status: 'skipped' }); reload(); });
}

function completeSheet(w, reload) {
  openSheet(`<h3>Nice. How did it feel?</h3>
    <p class="muted small" style="margin-top:-8px">${esc(w.title)}</p>
    <label class="f"><span>Effort (RPE 1–10)</span><input name="rpe" type="number" min="1" max="10" inputmode="numeric" placeholder="7"></label>
    <label class="f"><span>Notes (energy, pain, what changed)</span><textarea name="feel_notes" placeholder="Legs heavy, cut last set…"></textarea></label>
    <p class="hint">Lifted? Log your sets in the Log tab so they count toward PRs.</p>
    <button class="btn primary block" id="ok">Save</button>`, sh => {
    $('#ok', sh).onclick = async () => { await api('PUT', '/api/planned/' + w.id, { ...formData(sh), status: 'done' }); closeSheet(); toast('Logged'); reload(); };
  });
}

function workoutSheet(w, reload) {
  const isNew = !w.id;
  openSheet(`<h3>${isNew ? 'Add workout' : 'Edit workout'}</h3>
    <div class="grid2"><label class="f"><span>Date</span><input name="date" type="date" value="${w.date || todayIso()}"></label>
    <label class="f"><span>Type</span><select name="type">${TYPES.map(t => `<option ${typeOf(w.type) === t ? 'selected' : ''}>${t}</option>`).join('')}</select></label></div>
    <label class="f"><span>Title</span><input name="title" value="${esc(w.title || '')}" placeholder="Lower body A / Tempo run"></label>
    <div class="grid2"><label class="f"><span>Duration (min)</span><input name="duration_min" type="number" inputmode="numeric" value="${w.duration_min ?? ''}"></label>
    <label class="f"><span>Intensity</span><select name="intensity">${['', 'easy', 'moderate', 'hard'].map(t => `<option ${w.intensity === t ? 'selected' : ''}>${t}</option>`).join('')}</select></label></div>
    <label class="f"><span>Details</span><textarea name="details" placeholder="Squat 5x5 @ 100kg, RDL 3x8…">${esc(w.details || '')}</textarea></label>
    ${isNew ? '' : `<div class="grid2"><label class="f"><span>Status</span><select name="status">${['planned', 'done', 'skipped'].map(t => `<option ${w.status === t ? 'selected' : ''}>${t}</option>`).join('')}</select></label>
    <label class="f"><span>RPE</span><input name="rpe" type="number" min="1" max="10" value="${w.rpe ?? ''}"></label></div>
    <label class="f"><span>How it felt</span><input name="feel_notes" value="${esc(w.feel_notes || '')}"></label>`}
    <div class="btn-row">${isNew ? '' : '<button class="btn ghost" id="del">Delete</button>'}<button class="btn primary" id="save">Save</button></div>`, sh => {
    $('#save', sh).onclick = async () => {
      const d = formData(sh); if (!d.title) return toast('Add a title', true);
      if (isNew) await api('POST', '/api/planned', { ...d, source: 'me' }); else await api('PUT', '/api/planned/' + w.id, d);
      closeSheet(); reload();
    };
    if (!isNew) $('#del', sh).onclick = async () => { await api('DELETE', '/api/planned/' + w.id); closeSheet(); reload(); };
  });
}

/* ---------- TODAY ---------- */
async function renderToday() {
  const [d, st] = await Promise.all([api('GET', '/api/today'), api('GET', '/api/status')]);
  S.status = st;
  const t = d.date;
  const todays = d.week.filter(w => w.date === t);
  const setup = !st.keys.garmin_api_key.set || !st.keys.anthropic_api_key.set || !st.counts.goals;
  const r = d.readiness;
  const ws = monday(t);

  let h = header('Today', dname(t, { weekday: 'long', month: 'short', day: 'numeric' }), `<button class="icon-btn" id="gear" aria-label="Settings">${GEAR}</button>`);

  if (setup) h += `<div class="card hero"><h2>Get set up</h2>
    <div class="item"><span class="grow">1. Connect Garmin (Personal API key)</span>${st.keys.garmin_api_key.set ? '<span class="tag done">Done</span>' : '<button class="btn sm" data-open="settings">Add</button>'}</div>
    <div class="item"><span class="grow">2. Add a Claude API key for the coach</span>${st.keys.anthropic_api_key.set ? '<span class="tag done">Done</span>' : '<button class="btn sm" data-open="settings">Add</button>'}</div>
    <div class="item"><span class="grow">3. Set a long-term and short-term goal</span>${st.counts.goals ? '<span class="tag done">Done</span>' : '<a class="btn sm" href="#goals">Add</a>'}</div></div>`;

  h += `<div class="card"><div class="ready-head"><span class="pill ${r.level}">${{ good: 'Ready', ok: 'Caution', low: 'Recover', unknown: 'No data' }[r.level]}</span><span class="small muted grow">${esc(r.summary)}</span></div>
    ${r.signals.length ? `<div class="signals">${r.signals.map(s => `<div class="signal ${s.state}"><div class="k">${esc(s.name)}</div><div class="v">${esc(s.value)}</div><div class="d">${esc(s.vs)}</div></div>`).join('')}</div>` : ''}
    ${d.last_sync ? `<div class="hint" style="margin-top:10px">Garmin synced ${esc(d.last_sync.replace('T', ' '))} · <a href="#" id="sync" style="color:var(--accent)">Sync now</a></div>` : ''}</div>`;

  h += `<div class="card" id="todaywo"><h2>Today's training <button data-add="${t}">+ Add</button></h2>
    ${todays.length ? todays.map(w => woHtml(w, { actions: true })).join('') : '<div class="empty">Nothing planned. <b>Rest</b>, or add something. The coach can plan your week from the Plan tab.</div>'}</div>`;

  h += `<div class="card"><h2>This week <a href="#plan">Plan</a></h2><div class="week">` +
    [...Array(7)].map((_, i) => {
      const day = addDays(ws, i), ws_ = d.week.filter(w => w.date === day && typeOf(w.type) !== 'rest');
      return `<div class="day ${day === t ? 'today' : ''}">${dname(day).slice(0, 2)}<b>${+day.slice(8)}</b><div class="dots">${ws_.map(w => `<i class="t-${typeOf(w.type)} ${w.status === 'done' ? 'done' : ''}" style="${w.status === 'skipped' ? 'opacity:.3' : ''}"></i>`).join('')}</div></div>`;
    }).join('') + `</div>${d.adherence.pct != null ? `<div class="hint" style="margin-top:10px">Last 4 weeks: ${d.adherence.done}/${d.adherence.planned} planned sessions done (${d.adherence.pct}%)</div>` : ''}</div>`;

  const sg = d.goals.filter(g => g.horizon === 'short').slice(0, 3);
  if (sg.length) h += `<div class="card"><h2>Short-term goals <a href="#goals">All</a></h2>${sg.map(goalRow).join('')}</div>`;

  if (d.recent_prs.length) h += `<div class="card"><h2>New PRs · last 2 weeks</h2>${d.recent_prs.map(p => `<div class="item">🏆 <span class="grow">${esc(p)}</span></div>`).join('')}</div>`;

  if (d.recent_activities.length) h += `<div class="card"><h2>From your watch</h2>${d.recent_activities.map(a => `<div class="item">
      <div class="wo" style="padding:0;border:0"><div class="bar t-${typeOf(a.type)}"></div></div>
      <div class="grow"><div style="font-weight:600">${esc(a.name || a.type)}</div><div class="small muted">${dname(a.date, { weekday: 'short', day: 'numeric', month: 'short' })}</div></div>
      <div class="r small">${[mins((a.duration_s || 0) / 60), km(a.distance_m)].filter(Boolean).join(' · ')}<div class="faint">${a.avg_hr ? Math.round(a.avg_hr) + ' bpm' : ''}${a.training_load ? ' · load ' + Math.round(a.training_load) : ''}</div></div></div>`).join('')}</div>`;

  h += `<button class="btn primary fab" id="askfab">${SPARK} Ask coach</button>`;
  view.innerHTML = h;

  $('#gear').onclick = openSettings;
  view.querySelectorAll('[data-open="settings"]').forEach(b => b.onclick = openSettings);
  $('#askfab').onclick = openCoach;
  const sync = $('#sync'); if (sync) sync.onclick = e => { e.preventDefault(); doSync(); };
  view.querySelectorAll('[data-add]').forEach(b => b.onclick = () => workoutSheet({ date: b.dataset.add, type: 'strength' }, renderToday));
  bindWorkouts(view, d.week, renderToday);
  bindGoals(view, d.goals);
}

async function doSync(days) {
  toast('Syncing Garmin…');
  try {
    const r = await api('POST', '/api/garmin/sync', days ? { days } : {});
    toast(`Synced: ${r.log.join(', ')}` + (r.errors.length ? ` · ${r.errors.length} source(s) failed` : ''), r.errors.length > 0);
    if (r.errors.length) console.warn(r.errors);
    render();
    return r;
  } catch (e) { toast(e.message, true); }
}

/* ---------- PLAN ---------- */
async function renderPlan() {
  S.planWeek = S.planWeek || monday();
  const ws = S.planWeek, we = addDays(ws, 6);
  const [p, lp] = await Promise.all([api('GET', `/api/planned?from=${ws}&to=${we}`), api('GET', '/api/coach/latest-plan')]);
  const items = p.items;
  const label = `${dname(ws, { month: 'short', day: 'numeric' })} – ${dname(we, { month: 'short', day: 'numeric' })}`;
  const isThis = ws === monday();

  let h = header('Plan', isThis ? 'This week' : ws < monday() ? 'Past week' : 'Upcoming week');
  h += `<div class="weeknav"><button class="icon-btn" id="prev">‹</button><b>${label}</b><button class="icon-btn" id="next">›</button></div>`;

  h += `<div class="card ai-card"><h2>AI coach</h2>
    <p class="small muted" style="margin:-4px 0 10px">Builds this week around your goals, your planned sessions, recovery data and recent numbers. Your own workouts are kept unless there's a reason to change them.</p>
    <label class="f"><textarea id="note" placeholder="Optional: 'only 4 days this week', 'knee is sore', 'race on Sunday'…" style="min-height:60px"></textarea></label>
    <button class="btn primary block" id="gen">${SPARK} Plan this week</button></div>`;

  if (lp.plan && lp.week_start === ws) h += aiPlanHtml(lp);

  for (let i = 0; i < 7; i++) {
    const day = addDays(ws, i), its = items.filter(w => w.date === day);
    h += `<div class="daygroup"><div class="dh ${day === todayIso() ? 'today' : ''}"><b>${dname(day, { weekday: 'long', day: 'numeric' })}</b><button class="add" data-add="${day}">+</button></div>
      <div class="card" style="margin-bottom:6px;padding:${its.length ? '12px 16px' : '10px 16px'}">${its.length ? its.map(w => woHtml(w, { actions: day <= todayIso() })).join('') : '<div class="empty faint">Rest / nothing planned</div>'}</div></div>`;
  }
  view.innerHTML = h;

  $('#prev').onclick = () => { S.planWeek = addDays(ws, -7); renderPlan(); };
  $('#next').onclick = () => { S.planWeek = addDays(ws, 7); renderPlan(); };
  view.querySelectorAll('[data-add]').forEach(b => b.onclick = () => workoutSheet({ date: b.dataset.add, type: 'strength' }, renderPlan));
  bindWorkouts(view, items, renderPlan);
  $('#gen').onclick = e => busy(e.currentTarget, async () => {
    toast('Coach is thinking… (20–60s)');
    await api('POST', '/api/coach/plan', { week_start: ws, note: $('#note').value });
    await renderPlan();
    $('.ai-plan')?.scrollIntoView({ behavior: 'smooth' });
  });
  view.querySelectorAll('[data-apply]').forEach(b => b.onclick = e => busy(e.currentTarget, async () => {
    await api('POST', '/api/coach/apply', { plan_id: +b.dataset.apply, replace_mine: b.dataset.replace === '1' });
    toast('Added to your week'); renderPlan();
  }));
}

function aiPlanHtml(lp) {
  const p = lp.plan, list = a => (a && a.length) ? `<ul>${a.map(x => `<li>${esc(x)}</li>`).join('')}</ul>` : '';
  return `<div class="card ai-card ai-plan"><h2>Suggested week ${lp.applied ? '<span class="tag done">Applied</span>' : ''}</h2>
    <p style="margin:0 0 8px">${esc(p.summary)}</p>
    ${p.readiness_take ? `<p class="small muted" style="margin:0 0 8px">${esc(p.readiness_take)}</p>` : ''}
    ${(p.changes_to_my_plan || []).length ? `<div class="small" style="margin-top:8px"><b>Changes to your plan</b>${list(p.changes_to_my_plan)}</div>` : ''}
    ${(p.watch_outs || []).length ? `<div class="small" style="margin-top:8px"><b>Watch outs</b>${list(p.watch_outs)}</div>` : ''}
    <div style="margin-top:10px">${(p.days || []).map(d => `<div class="ai-day"><div class="row between"><b>${dname(d.date, { weekday: 'short', day: 'numeric' })} · ${esc(d.title)}</b><span class="small muted">${[mins(d.duration_min), d.intensity].filter(Boolean).join(' · ')}</span></div>
      ${d.details ? `<div class="small" style="color:#c3c9d4;white-space:pre-wrap;margin-top:3px">${esc(d.details)}</div>` : ''}
      ${d.why ? `<div class="why">${d.keeps_my_plan ? '✓ Your session · ' : ''}${esc(d.why)}</div>` : ''}</div>`).join('')}</div>
    <div class="btn-row" style="margin-top:12px"><button class="btn primary" data-apply="${lp.id}">Add to my week</button><button class="btn ghost" data-apply="${lp.id}" data-replace="1">Replace my plan</button></div>
    <p class="hint">"Add" fills in the AI sessions and keeps yours. "Replace" swaps out your planned (not completed) sessions for this week.</p></div>`;
}

/* ---------- LOG ---------- */
async function renderLog() {
  const st = S.status || (S.status = await api('GET', '/api/status'));
  const unit = st.units || 'kg';
  let h = header('Log', 'History, numbers & PRs');
  h += `<div class="seg">${[['lifts', 'Lifts'], ['metrics', 'Numbers'], ['prs', 'PRs']].map(([k, l]) => `<button data-seg="${k}" class="${S.logTab === k ? 'on' : ''}">${l}</button>`).join('')}</div><div id="logbody"></div>`;
  view.innerHTML = h;
  view.querySelectorAll('[data-seg]').forEach(b => b.onclick = () => { S.logTab = b.dataset.seg; renderLog(); });
  const body = $('#logbody');
  const names = (await api('GET', '/api/goals')).names;

  if (S.logTab === 'lifts') {
    const { items } = await api('GET', '/api/lifts?limit=150');
    body.innerHTML = `<div class="card"><h2>Log a lift</h2>
      <datalist id="exlist">${names.exercises.map(e => `<option value="${esc(e)}">`).join('')}</datalist>
      <div class="grid2"><label class="f"><span>Exercise</span><input name="exercise" list="exlist" placeholder="Back squat" autocapitalize="words" value="${esc(S.lastEx || '')}"></label>
      <label class="f"><span>Date</span><input name="date" type="date" value="${todayIso()}"></label></div>
      <div class="grid4"><label class="f"><span>Sets</span><input name="sets" type="number" inputmode="numeric" value="${S.lastSets || 3}"></label>
      <label class="f"><span>Reps</span><input name="reps" type="number" inputmode="numeric" value="${S.lastReps || ''}"></label>
      <label class="f"><span>${unit}</span><input name="weight" type="number" inputmode="decimal" step="0.5" value="${S.lastW || ''}"></label>
      <label class="f"><span>RPE</span><input name="rpe" type="number" inputmode="decimal" step="0.5" min="1" max="10"></label></div>
      <input type="hidden" name="unit" value="${unit}">
      <button class="btn primary block" id="addlift">Add</button>
      <p class="hint">One line per set scheme (e.g. 3 × 5 @ 100). Top sets ≤12 reps count toward estimated 1RM.</p></div>`;
    body.innerHTML += groupByDate(items, l => `<div class="item"><div class="grow"><b style="font-weight:600">${esc(l.exercise)}</b>${l.rpe ? ` <span class="faint small">RPE ${l.rpe}</span>` : ''}</div>
      <div class="r">${l.sets} × ${l.reps} @ ${num(l.weight)} ${esc(l.unit)}</div><button class="x" data-del-lift="${l.id}">×</button></div>`);
    $('#addlift').onclick = async () => {
      const d = formData(body.querySelector('.card'));
      if (!d.exercise || !d.reps || d.weight == null) return toast('Exercise, reps and weight please', true);
      Object.assign(S, { lastEx: d.exercise, lastSets: d.sets, lastReps: d.reps, lastW: d.weight });
      await api('POST', '/api/lifts', d); toast('Logged'); renderLog();
    };
    body.querySelectorAll('[data-del-lift]').forEach(b => b.onclick = async () => { await api('DELETE', '/api/lifts/' + b.dataset.delLift); renderLog(); });
  }

  if (S.logTab === 'metrics') {
    const { items } = await api('GET', '/api/metrics?limit=150');
    body.innerHTML = `<div class="card"><h2>Log a number</h2>
      <datalist id="mlist">${names.metrics.map(e => `<option value="${esc(e)}">`).join('')}</datalist>
      <label class="f"><span>What</span><input name="metric" list="mlist" placeholder="5k time, Bodyweight, Max pull-ups…" autocapitalize="sentences"></label>
      <div class="grid3"><label class="f"><span>Value</span><input name="value" type="number" inputmode="decimal" step="any"></label>
      <label class="f"><span>Unit</span><input name="unit" placeholder="min, kg, reps"></label>
      <label class="f"><span>Better</span><select name="better"><option value="higher">higher</option><option value="lower">lower</option></select></label></div>
      <div class="grid2"><label class="f"><span>Date</span><input name="date" type="date" value="${todayIso()}"></label>
      <label class="f"><span>Note</span><input name="notes" data-nullable></label></div>
      <button class="btn primary block" id="addm">Add</button>
      <p class="hint">Times: enter minutes as decimals (24:30 → 24.5) and set "Better" to lower.</p></div>`;
    body.innerHTML += groupByDate(items, m => `<div class="item"><div class="grow">${esc(m.metric)}${m.notes ? `<div class="small faint">${esc(m.notes)}</div>` : ''}</div>
      <div class="r"><b>${num(m.value)}</b> ${esc(m.unit || '')}</div><button class="x" data-del-m="${m.id}">×</button></div>`);
    const mi = $('[name=metric]', body);
    mi.onchange = () => { const last = items.find(x => x.metric.toLowerCase() === mi.value.toLowerCase()); if (last) { $('[name=unit]', body).value = last.unit || ''; $('[name=better]', body).value = last.better; } };
    $('#addm').onclick = async () => {
      const d = formData(body.querySelector('.card'));
      if (!d.metric || d.value == null) return toast('Name and value please', true);
      await api('POST', '/api/metrics', d); toast('Logged'); renderLog();
    };
    body.querySelectorAll('[data-del-m]').forEach(b => b.onclick = async () => { await api('DELETE', '/api/metrics/' + b.dataset.delM); renderLog(); });
  }

  if (S.logTab === 'prs') {
    const p = await api('GET', '/api/prs');
    body.innerHTML = `<div class="card"><h2>Lifts · best estimated 1RM</h2>${p.lifts.length ? p.lifts.map(l => `<div class="item"><div class="grow"><b style="font-weight:600">${esc(l.exercise)}</b>
        <div class="small muted">${l.best_e1rm ? `${num(l.best_e1rm.weight)}×${l.best_e1rm.reps} on ${l.best_e1rm.date}` : ''}${l.best_weight ? ` · heaviest ${num(l.best_weight.value)}${esc(l.unit)}` : ''}</div></div>
        <div class="r"><b style="font-size:18px">${l.best_e1rm ? num(l.best_e1rm.value) : '–'}</b> <span class="small muted">${esc(l.unit)}</span></div></div>`).join('') : '<div class="empty">Log lifts to see PRs.</div>'}</div>
      <div class="card"><h2>Other numbers · best</h2>${p.metrics.length ? p.metrics.map(m => `<div class="item"><div class="grow"><b style="font-weight:600">${esc(m.metric)}</b><div class="small muted">best on ${m.best.date} · latest ${num(m.latest.value)}</div></div>
        <div class="r"><b style="font-size:18px">${num(m.best.value)}</b> <span class="small muted">${esc(m.unit || '')}</span></div></div>`).join('') : '<div class="empty">Log numbers to see bests.</div>'}</div>`;
  }
}

function groupByDate(items, rowFn) {
  if (!items.length) return '';
  const groups = {};
  items.forEach(i => (groups[i.date] = groups[i.date] || []).push(i));
  return Object.keys(groups).sort().reverse().map(d => `<div class="section-title">${dname(d, { weekday: 'short', month: 'short', day: 'numeric' })}</div><div class="card">${groups[d].map(rowFn).join('')}</div>`).join('');
}

/* ---------- TRENDS ---------- */
async function renderTrends() {
  const t = await api('GET', '/api/trends?weeks=12&days=90');
  const w = t.weekly, dly = t.daily;
  const wl = x => dname(x.week, { month: 'numeric', day: 'numeric' });
  const avgMin = Math.round(w.slice(-4).reduce((a, x) => a + x.minutes, 0) / 4);
  const lr = t.load_ratio.ratio;

  let h = header('Trends', 'Last 12 weeks');
  h += `<div class="stats" style="margin-bottom:12px">
    <div class="stat"><b>${t.adherence.pct ?? '–'}${t.adherence.pct != null ? '%' : ''}</b><span>Plan done (8 wk)</span></div>
    <div class="stat"><b style="color:${lr == null ? 'inherit' : lr > 1.5 ? 'var(--low)' : lr > 1.3 || lr < .8 ? 'var(--ok)' : 'var(--good)'}">${lr ?? '–'}</b><span>Load ratio 7d:28d</span></div>
    <div class="stat"><b>${mins(avgMin) || '–'}</b><span>Avg / week (4 wk)</span></div></div>`;

  h += `<div class="card"><h2>Training time per week</h2>${barChart(w.map(x => ({ label: wl(x), parts: x.minutes_by_type })), TYPE_COLORS, { highlightLast: true })}</div>`;
  h += `<div class="card"><h2>Training load per week</h2>${barChart(w.map(x => ({ label: wl(x), parts: { load: x.load } })), { load: '#ff6b3d' }, { highlightLast: true })}
    <div class="hint">Garmin training load where available, otherwise minutes. Ratio 0.8–1.3 is the usual sweet spot; above 1.5 is a spike.</div></div>`;
  if (w.some(x => x.run_km)) h += `<div class="card"><h2>Running distance (km)</h2>${barChart(w.map(x => ({ label: wl(x), parts: { run: x.run_km } })), { run: TYPE_COLORS.run })}</div>`;
  if (w.some(x => x.tonnage)) h += `<div class="card"><h2>Lifting volume (sets × reps × weight)</h2>${barChart(w.map(x => ({ label: wl(x), parts: { strength: x.tonnage } })), { strength: TYPE_COLORS.strength })}</div>`;

  const ser = (f, scale = 1) => dly.map(r => ({ date: r.date, value: r[f] != null ? r[f] * scale : null }));
  const avg7 = arr => arr.map((p, i) => { const win = arr.slice(Math.max(0, i - 6), i + 1).filter(x => x.value != null); return { date: p.date, value: win.length ? win.reduce((a, x) => a + x.value, 0) / win.length : null }; });
  if (dly.length) {
    const hrv = ser('hrv_last_night');
    h += `<div class="section-title">Recovery · 90 days</div>`;
    h += `<div class="card"><h2>HRV (ms)</h2>${lineChart([{ name: 'Nightly', color: '#2ed3c6', points: hrv }, { name: '7-day avg', color: '#eef1f5', points: avg7(hrv), dashed: true }])}</div>`;
    h += `<div class="card"><h2>Resting heart rate (bpm)</h2>${lineChart([{ name: 'RHR', color: '#ff5c6c', points: ser('resting_hr') }])}</div>`;
    h += `<div class="card"><h2>Sleep (hours)</h2>${lineChart([{ name: 'Sleep', color: '#b38cff', points: ser('sleep_hours') }], { band: [7, 9] })}<div class="hint">Shaded band = 7–9 h.</div></div>`;
    if (dly.some(r => r.body_battery_high)) h += `<div class="card"><h2>Body Battery peak</h2>${lineChart([{ name: 'Peak', color: '#3ddc84', points: ser('body_battery_high') }])}</div>`;
  } else {
    h += `<div class="card"><div class="empty">No watch data yet. Add your Garmin key in Settings and sync.</div></div>`;
  }

  h += `<div class="section-title">Strength · estimated 1RM</div><div class="card" id="liftc">${t.names.exercises.length ? `<div class="chips">${t.names.exercises.map(e => `<button class="chip" data-lift="${esc(e)}">${esc(e)}</button>`).join('')}</div><div id="liftchart"></div>` : '<div class="empty">Log lifts to see strength trends.</div>'}</div>`;
  h += `<div class="section-title">Your numbers</div><div class="card" id="metc">${t.names.metrics.length ? `<div class="chips">${t.names.metrics.map(e => `<button class="chip" data-met="${esc(e)}">${esc(e)}</button>`).join('')}</div><div id="metchart"></div>` : '<div class="empty">Log numbers (5k time, bodyweight…) to see trends.</div>'}</div>`;
  view.innerHTML = h;

  const pickChip = async (attr, kind, target, key) => {
    const chips = view.querySelectorAll(`[data-${attr}]`); if (!chips.length) return;
    const sel = S[key] && [...chips].some(c => c.dataset[attr] === S[key]) ? S[key] : chips[0].dataset[attr];
    S[key] = sel;
    chips.forEach(c => c.classList.toggle('on', c.dataset[attr] === sel));
    const r = await api('GET', `/api/series?kind=${kind}&name=${encodeURIComponent(sel)}`);
    $(target).innerHTML = lineChart([{ name: sel, color: kind === 'lift' ? '#ff6b3d' : '#4fa3ff', points: r.points }], { dots: true });
    chips.forEach(c => c.onclick = () => { S[key] = c.dataset[attr]; pickChip(attr, kind, target, key); });
  };
  pickChip('lift', 'lift', '#liftchart', 'liftSel');
  pickChip('met', 'metric', '#metchart', 'metricSel');
}

/* ---------- GOALS ---------- */
function goalRow(g) {
  const p = g.progress;
  const target = g.target_value != null ? `${num(g.target_value)} ${esc(g.unit || '')}` : '';
  return `<div class="goal" data-goal="${g.id}"><div class="row between"><span class="t">${esc(g.title)}</span>
      ${g.status !== 'active' ? `<span class="tag ${g.status === 'achieved' ? 'done' : ''}">${g.status}</span>` : p?.days_left != null ? `<span class="small muted">${p.days_left >= 0 ? p.days_left + ' days left' : 'overdue'}</span>` : ''}</div>
    ${p?.pct != null ? `<div class="prog"><i style="width:${p.pct}%"></i></div>` : ''}
    <div class="small muted">${p ? `Now ${num(p.current)} ${esc(g.unit || '')}${target ? ' → ' + target : ''}${p.pct != null ? ` · ${p.pct}%` : ''}` : g.metric ? `Tracking "${esc(g.metric)}": log it to see progress` : target ? 'Target ' + target : ''}</div></div>`;
}
function bindGoals(root, goals) {
  root.querySelectorAll('[data-goal]').forEach(el => el.onclick = () => goalSheet(goals.find(g => g.id == el.dataset.goal)));
}

async function renderGoals() {
  const { goals, names } = await api('GET', '/api/goals');
  S.names = names;
  const longs = goals.filter(g => g.horizon === 'long'), shorts = goals.filter(g => g.horizon === 'short');
  let h = header('Goals', 'Long-term direction, short-term steps');
  h += `<div class="section-title">Long-term</div>`;
  h += longs.length ? longs.map(g => `<div class="card goal-long" data-goal="${g.id}" style="cursor:pointer">
      <div class="row between"><b style="font-size:19px">${esc(g.title)}</b>${g.target_date ? `<span class="small muted">by ${dname(g.target_date, { month: 'short', year: 'numeric' })}</span>` : ''}</div>
      ${g.notes ? `<p class="small muted" style="margin:6px 0 0">${esc(g.notes)}</p>` : ''}
      ${g.progress ? `<div class="prog"><i style="width:${g.progress.pct || 0}%"></i></div><div class="small muted">Now ${num(g.progress.current)} ${esc(g.unit || '')} → ${num(g.target_value)} ${esc(g.unit || '')}</div>` : ''}
      <div class="small faint" style="margin-top:8px">${shorts.filter(s => s.parent_id === g.id).length} short-term goal(s) linked</div></div>`).join('')
    : `<div class="card"><div class="empty">Where do you want to be in 6–12 months? e.g. <b>Run a sub-45 10k</b>, <b>Squat 1.75× bodyweight</b>, <b>Finish a half Ironman</b>.</div></div>`;
  h += `<button class="btn ghost block" data-new="long" style="margin-bottom:8px">+ Long-term goal</button>`;
  h += `<div class="section-title">Short-term (4–12 weeks)</div><div class="card">${shorts.length ? shorts.map(goalRow).join('') : '<div class="empty">Break the long-term goal into measurable steps, e.g. <b>Bench e1RM 100 kg by Jan 31</b>.</div>'}</div>`;
  h += `<button class="btn ghost block" data-new="short">+ Short-term goal</button>`;
  h += `<p class="hint" style="margin:14px 4px">Tip: set "Track with" to an exercise name (uses your best e1RM) or a number you log (5k time, bodyweight) and progress updates automatically.</p>`;
  view.innerHTML = h;
  bindGoals(view, goals);
  view.querySelectorAll('[data-new]').forEach(b => b.onclick = () => goalSheet({ horizon: b.dataset.new, better: 'higher' }, longs));
  S.longGoals = longs;
}

function goalSheet(g, longs) {
  longs = longs || S.longGoals || [];
  const names = S.names || { exercises: [], metrics: [] };
  const isNew = !g.id;
  openSheet(`<h3>${isNew ? 'New' : 'Edit'} ${g.horizon === 'long' ? 'long-term' : 'short-term'} goal</h3>
    <input type="hidden" name="horizon" value="${g.horizon}">
    <label class="f"><span>Goal</span><input name="title" value="${esc(g.title || '')}" placeholder="${g.horizon === 'long' ? 'Run a sub-45 10k' : 'Squat 140 kg × 1'}"></label>
    <label class="f"><span>Track with (exercise or logged number)</span><input name="metric" list="glist" value="${esc(g.metric || '')}" placeholder="Back squat / 10k time" data-nullable>
      <datalist id="glist">${[...names.exercises, ...names.metrics].map(e => `<option value="${esc(e)}">`).join('')}</datalist></label>
    <div class="grid3"><label class="f"><span>Start</span><input name="baseline_value" type="number" step="any" value="${g.baseline_value ?? ''}"></label>
    <label class="f"><span>Target</span><input name="target_value" type="number" step="any" value="${g.target_value ?? ''}"></label>
    <label class="f"><span>Unit</span><input name="unit" value="${esc(g.unit || '')}" placeholder="kg / min" data-nullable></label></div>
    <div class="grid2"><label class="f"><span>Better is</span><select name="better"><option ${g.better !== 'lower' ? 'selected' : ''}>higher</option><option ${g.better === 'lower' ? 'selected' : ''}>lower</option></select></label>
    <label class="f"><span>By</span><input name="target_date" type="date" value="${g.target_date || ''}" data-nullable></label></div>
    ${g.horizon === 'short' && longs.length ? `<label class="f"><span>Supports long-term goal</span><select name="parent_id"><option value="">—</option>${longs.map(l => `<option value="${l.id}" ${g.parent_id === l.id ? 'selected' : ''}>${esc(l.title)}</option>`).join('')}</select></label>` : ''}
    <label class="f"><span>Why it matters / notes</span><textarea name="notes" data-nullable placeholder="Context the coach should know">${esc(g.notes || '')}</textarea></label>
    ${isNew ? '' : `<label class="f"><span>Status</span><select name="status">${['active', 'achieved', 'dropped'].map(s => `<option ${g.status === s ? 'selected' : ''}>${s}</option>`).join('')}</select></label>`}
    <div class="btn-row">${isNew ? '' : '<button class="btn ghost" id="del">Delete</button>'}<button class="btn primary" id="save">Save</button></div>`, sh => {
    $('#save', sh).onclick = async () => {
      const d = formData(sh); if (!d.title) return toast('Name your goal', true);
      if ('parent_id' in d) d.parent_id = d.parent_id ? +d.parent_id : null;
      if (isNew) await api('POST', '/api/goals', d); else await api('PUT', '/api/goals/' + g.id, d);
      closeSheet(); render();
    };
    if (!isNew) $('#del', sh).onclick = async () => { await api('DELETE', '/api/goals/' + g.id); closeSheet(); render(); };
  });
}

/* ---------- COACH CHAT ---------- */
async function openCoach() {
  const { items } = await api('GET', '/api/coach/messages');
  const msgs = items.map(m => `<div class="msg ${m.role}">${m.role === 'assistant' ? md(m.content) : esc(m.content)}</div>`).join('');
  openSheet(`<h3 class="row between">Coach <button class="btn sm ghost" id="clr">Clear</button></h3>
    <div class="chat" id="chat">${msgs || '<div class="empty">Ask anything about your training. The coach sees your goals, plan, logs and watch data.</div>'}</div>
    <div class="chips"><button class="chip" data-q="weekly_review">Weekly review</button>
      <button class="chip" data-txt="Should I train hard today or back off?">Hard or easy today?</button>
      <button class="chip" data-txt="Am I on track for my short-term goals? What's the biggest limiter?">On track?</button>
      <button class="chip" data-txt="Suggest how to progress my main lifts next week based on my recent sets.">Progress my lifts</button></div>
    <div class="row"><input id="q" placeholder="Ask your coach…" class="grow"><button class="btn primary" id="send">Send</button></div>`, sh => {
    const chat = $('#chat', sh); chat.scrollTop = chat.scrollHeight;
    const send = async (payload, label) => {
      chat.querySelector('.empty')?.remove();
      chat.insertAdjacentHTML('beforeend', `<div class="msg user">${esc(label)}</div><div class="msg assistant" id="pending"><span class="loading"></span></div>`);
      chat.scrollTop = chat.scrollHeight;
      try { const r = await api('POST', '/api/coach/ask', payload); $('#pending').outerHTML = `<div class="msg assistant">${md(r.answer)}</div>`; }
      catch (e) { $('#pending').outerHTML = `<div class="msg assistant" style="color:var(--low)">${esc(e.message)}</div>`; }
      chat.scrollTop = chat.scrollHeight;
    };
    $('#send', sh).onclick = () => { const v = $('#q', sh).value.trim(); if (v) { $('#q', sh).value = ''; send({ question: v }, v); } };
    $('#q', sh).onkeydown = e => { if (e.key === 'Enter') $('#send', sh).click(); };
    sh.querySelectorAll('[data-q]').forEach(c => c.onclick = () => send({ preset: c.dataset.q }, c.textContent));
    sh.querySelectorAll('[data-txt]').forEach(c => c.onclick = () => send({ question: c.dataset.txt }, c.dataset.txt));
    $('#clr', sh).onclick = async () => { await api('DELETE', '/api/coach/messages'); closeSheet(); };
  });
}

/* ---------- SETTINGS ---------- */
async function openSettings() {
  const st = await api('GET', '/api/status');
  const p = st.profile || {};
  const k = st.keys;
  const pf = (name, label, ph = '', type = 'text') => `<label class="f"><span>${label}</span><input data-p="${name}" type="${type}" value="${esc(p[name] ?? '')}" placeholder="${ph}"></label>`;
  openSheet(`<h3>Settings</h3>
    <div class="section-title" style="margin-top:0">Garmin</div>
    <label class="f"><span>Personal API key ${k.garmin_api_key.set ? `<span class="tag done">${esc(k.garmin_api_key.hint)}</span>` : ''}</span><input id="gk" type="password" placeholder="${k.garmin_api_key.set ? 'Saved. Paste a new one to replace' : 'Paste key from Garmin Connect'}" autocomplete="off"></label>
    <p class="hint" style="margin-top:-6px">Garmin Connect (web) → Personal API Key → Create Key. Pick 1 year. Keys can't be viewed again, so paste it here straight away.</p>
    <div class="btn-row" style="margin:8px 0 6px"><button class="btn sm" id="sync">Sync now</button><button class="btn sm ghost" id="sync365">Re-sync 1 year</button></div>
    <p class="hint">${st.last_sync ? 'Last sync ' + esc(st.last_sync.replace('T', ' ')) : 'Not synced yet'} · ${st.counts.garmin_activities} activities, ${st.counts.garmin_daily} days stored</p>

    <div class="section-title">AI coach (Claude)</div>
    <label class="f"><span>Claude API key ${k.anthropic_api_key.set ? `<span class="tag done">${esc(k.anthropic_api_key.hint)}</span>` : ''}</span><input id="ak" type="password" placeholder="${k.anthropic_api_key.set ? 'Saved. Paste a new one to replace' : 'sk-ant-…'}" autocomplete="off"></label>
    <p class="hint" style="margin-top:-6px">From console.anthropic.com. Billed per use, separate from a Claude subscription. A weekly plan costs a few cents.</p>
    <label class="f"><span>Model</span><input id="model" value="${esc(st.ai_model)}"></label>

    <div class="section-title">About you (the coach uses this)</div>
    <div class="grid2">${pf('age', 'Age', '29', 'number')}${pf('bodyweight', 'Bodyweight', '78')}</div>
    <div class="grid2">${pf('days_per_week', 'Training days / week', '5')}${pf('session_minutes', 'Usual session length (min)', '60')}</div>
    ${pf('sports', 'Sports / focus', 'Strength + running, hybrid')}
    ${pf('experience', 'Experience', '4 yrs lifting, 1 yr running')}
    ${pf('equipment', 'Equipment', 'Full gym; no pool')}
    ${pf('schedule', 'Schedule constraints', 'Long run Sat only; no training Fri')}
    ${pf('injuries', 'Injuries / limits', 'Left knee: avoid deep lunges')}
    <label class="f"><span>Units</span><select id="units"><option ${st.units === 'kg' ? 'selected' : ''}>kg</option><option ${st.units === 'lb' ? 'selected' : ''}>lb</option></select></label>

    <div class="section-title">Security & data</div>
    <label class="f"><span>App passcode ${k.passcode.set ? '<span class="tag done">On</span>' : ''}</span><input id="pcset" type="password" inputmode="numeric" placeholder="${k.passcode.set ? 'Set. Type a new one, or a single space to remove' : 'Recommended'}"></label>
    <a class="btn ghost block" href="/api/export" id="exp" download="coach-export.json" style="margin-bottom:12px">Export my data (JSON)</a>
    <button class="btn primary block" id="save">Save</button>`, sh => {
    const save = async () => {
      const profile = { ...p }; sh.querySelectorAll('[data-p]').forEach(i => { profile[i.dataset.p] = i.value || null; });
      const body = { profile, units: $('#units', sh).value, ai_model: $('#model', sh).value.trim() };
      if ($('#gk', sh).value) body.garmin_api_key = $('#gk', sh).value;
      if ($('#ak', sh).value) body.anthropic_api_key = $('#ak', sh).value;
      const pcv = $('#pcset', sh).value;
      if (pcv) body.passcode = pcv.trim();
      S.status = await api('POST', '/api/settings', body);
      if (pcv) localStorage.setItem('pc', pcv.trim());
    };
    $('#save', sh).onclick = e => busy(e.currentTarget, async () => { await save(); closeSheet(); toast('Saved'); render(); });
    $('#sync', sh).onclick = e => busy(e.currentTarget, async () => { await save(); if (await doSync()) closeSheet(); });
    $('#sync365', sh).onclick = e => busy(e.currentTarget, async () => { await save(); if (await doSync(365)) closeSheet(); });
    $('#exp', sh).onclick = async e => {
      e.preventDefault();
      const data = await api('GET', '/api/export');
      const a = document.createElement('a'); a.href = URL.createObjectURL(new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' }));
      a.download = `coach-export-${todayIso()}.json`; a.click();
    };
  });
}

/* ---------- boot ---------- */
if ('serviceWorker' in navigator && location.protocol === 'https:') navigator.serviceWorker.register('/sw.js').catch(() => {});
render();
