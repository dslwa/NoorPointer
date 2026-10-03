'use strict';
const $ = id => document.getElementById(id);
const escapeHtml = value => String(value ?? '').replace(/[&<>"']/g, char => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[char]));
const formatNumber = value => new Intl.NumberFormat('en-US', {maximumFractionDigits: 2}).format(value);
const money = value => new Intl.NumberFormat('en-US', {style:'currency', currency:'USD', maximumFractionDigits:4}).format(value);
const labels = {pii_regex:'Personal data (PII)',secrets:'Secrets and API keys',prompt_injection:'Prompt injection',content_safety:'Content safety',attack_signatures:'Attack signatures',agent_loops:'Agent loops',mcp_tools:'MCP tools'};
let token = sessionStorage.getItem('noorpointer-token');
let view = 'overview', page = 0, dashboard, editorInitialized = false, signaturesInitialized = false;
let toastTimer;

function toast(message, error = false) {
  $('toast').textContent = message;
  $('toast').className = error ? 'error-toast' : '';
  $('toast').hidden = false;
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => { $('toast').hidden = true; }, error ? 8500 : 4500);
}

async function api(path, options = {}) {
  const response = await fetch('/api' + path, {
    ...options,
    headers: {'Authorization':'Bearer ' + token, ...(options.body ? {'Content-Type':'application/json'} : {}), ...options.headers}
  });
  if (!response.ok) {
    const error = await response.json().catch(() => ({}));
    throw new Error(error.message || (response.status === 401 ? 'Invalid API token.' : 'API error: ' + response.status));
  }
  return options.download ? response.blob() : response.json();
}

async function job(button, action) {
  button.disabled = true;
  try { await action(); } catch (error) { toast(error.message, true); }
  finally { button.disabled = false; }
}

async function loadDashboard() {
  dashboard = await api('/dashboard');
  const summary = dashboard.summary, revision = dashboard.active_policy.revision;
  if (!editorInitialized) { setEditor(revision.document); editorInitialized = true; }
  $('connection').textContent = 'API connected'; $('connection').className = 'connection online';
  $('policy-name').textContent = `Active policy: ${revision.name} · v${revision.version}`;
  $('policy-status').textContent = `${dashboard.controls_enabled} of ${dashboard.controls_total} controls enabled · ${revision.document.defaults.mode} mode · configuration available to the gateway`;
  $('stat-requests').textContent = formatNumber(summary.requests);
  $('stat-blocked').textContent = formatNumber(summary.blocked);
  $('stat-tokens').textContent = formatNumber(summary.tokens);
  $('stat-cost').textContent = money(summary.cost_usd);
  $('block-rate').textContent = summary.requests ? `${formatNumber(summary.blocked / summary.requests * 100)}% of decisions blocked` : 'No decisions reported';
  $('control-coverage').textContent = `${dashboard.controls_enabled} / ${dashboard.controls_total} controls enabled in the policy`;
  $('demo').hidden = !dashboard.demo_enabled;
  const maximum = Math.max(...summary.trend.map(day => day.requests), 1);
  $('trend').innerHTML = summary.trend.map(day => `<div class="chart-day" title="${escapeHtml(day.date)}: ${day.requests} decisions, ${day.blocked} blocked"><span class="chart-count">${day.requests}</span><div class="chart-bars"><i class="chart-bar" style="height:${day.requests / maximum * 100}%"></i><i class="chart-bar blocked" style="height:${day.blocked / maximum * 100}%"></i></div><small>${day.date.slice(5,7)}/${day.date.slice(8)}</small></div>`).join('');
  const categories = Object.entries(summary.categories).sort((a,b) => b[1]-a[1]);
  $('categories').className = 'categories' + (categories.length ? '' : ' empty');
  $('categories').innerHTML = categories.length ? categories.map(([category,count]) => `<div class="category-row"><div><span>${escapeHtml(category)}</span><strong>${count}</strong></div><div class="progress"><i style="width:${count / summary.blocked * 100}%"></i></div></div>`).join('') : 'No blocks yet. Connect the gateway or load demo events.';
  const metrics = {monthly_usd:'Monthly cost · USD',daily_tokens:'Daily tokens',gpu_seconds_per_hour:'GPU seconds · last hour'};
  $('budgets').innerHTML = dashboard.budgets.length ? dashboard.budgets.map(budget => {
    const percent = budget.limit > 0 ? Math.min(budget.used / budget.limit * 100,100) : budget.used > 0 ? 100 : 0;
    return `<div class="budget-row"><strong>${escapeHtml(budget.subject)}</strong><div class="budget-numbers"><span>${metrics[budget.metric]}</span><span>${formatNumber(budget.used)} / ${formatNumber(budget.limit)}</span></div><div class="progress ${budget.used >= budget.limit ? 'over':''}"><i style="width:${percent}%"></i></div><small>When exceeded: ${escapeHtml(budget.on_exceed)}</small></div>`;
  }).join('') : '<div class="empty">No budgets are configured in the active policy.</div>';
}

function editorDocument() { return JSON.parse($('policy-document').value); }
function setEditor(document) {
  $('policy-document').value = JSON.stringify(document, null, 2);
  $('validation-result').textContent = 'Each save creates a separate, immutable version.';
  renderControls();
}
function renderControls() {
  let document;
  try { document = editorDocument(); }
  catch { $('quick-controls').innerHTML = '<p class="help">For YAML, use the full editor below. Quick settings are available for JSON.</p>'; return; }
  $('quick-controls').innerHTML = Object.entries(document.controls || {}).map(([key,control]) => `<div class="quick-row"><input type="checkbox" data-control="${escapeHtml(key)}" aria-label="Enable ${escapeHtml(labels[key] || key)}" ${control.enabled ? 'checked':''}><strong>${escapeHtml(labels[key] || key)}</strong>${key === 'prompt_injection' ? `<label>Threshold <input type="number" id="injection-threshold" min="0" max="1" step="0.05" value="${escapeHtml(control.threshold)}"></label>` : ''}<select data-action="${escapeHtml(key)}" aria-label="Action ${escapeHtml(labels[key] || key)}">${['block','redact','monitor'].map(action => `<option ${action === control.action ? 'selected':''}>${action}</option>`).join('')}</select></div>`).join('');
}

async function loadPolicies() {
  const revisions = await api('/policies');
  const active = dashboard.active_policy.revision.version;
  $('revision-list').innerHTML = revisions.slice(0,9).map(revision => `<article class="revision ${revision.version === active ? 'current':''}"><div><span class="label">VERSION ${revision.version}</span>${revision.version === active ? '<span class="badge allow">ACTIVE</span>':''}</div><h3>${escapeHtml(revision.name)}</h3><p>${escapeHtml(new Date(revision.created_at).toLocaleString('en-US'))}</p><div><button class="button ghost small" data-edit="${revision.version}">Create copy</button><button class="button ${revision.version === active ? 'secondary':'primary'} small" data-publish="${revision.version}" ${revision.version === active ? 'disabled':''}>Publish</button></div></article>`).join('');
}

function eventQuery() {
  const query = new URLSearchParams();
  for (const [field,id] of [['action','filter-action'],['agent','filter-agent'],['category','filter-category']]) {
    const value = $(id).value.trim(); if (value) query.set(field,value);
  }
  return query;
}
async function loadEvents() {
  const query = eventQuery(); query.set('page',page); query.set('size',20);
  const result = await api('/events?' + query);
  $('event-rows').innerHTML = result.items.length ? result.items.map(event => `<tr class="event-row" data-event="${escapeHtml(event.id)}"><td>${escapeHtml(new Date(event.occurred_at).toLocaleString('en-US'))}${event.context.demo ? '<span class="demo-label">DEMO</span>':''}<small>${escapeHtml(event.kind)}</small></td><td><strong>${escapeHtml(event.agent_id)}</strong><small>${escapeHtml(event.model)}</small></td><td>${escapeHtml(labels[event.control] || event.control)}</td><td>${escapeHtml(event.category)}</td><td><span class="badge ${escapeHtml(event.action)}">${escapeHtml(event.action)}</span></td><td><button class="button ghost small" aria-label="Event details ${escapeHtml(event.id)}">↗</button></td></tr>`).join('') : '<tr><td colspan="6" class="empty">No events match these filters. Load demo events or connect the gateway.</td></tr>';
  $('event-count').textContent = result.total ? `${page * 20 + 1}–${Math.min((page+1)*20,result.total)} of ${result.total} events` : 'No events';
  $('previous-page').disabled = page === 0;
  $('next-page').disabled = (page+1)*20 >= result.total;
}

const exampleFeed = {signatures:[{id:'DEMO-INJECTION-001',name:'Example prompt injection rule',source:'https://owasp.org/www-project-top-10-for-large-language-model-applications/',category:'LLM01:2025',action:'block',target:'prompt',match:{type:'literal',value:'ignore all previous instructions'},description:'Demonstration rule; does not provide comprehensive prompt injection detection.',enabled:true}]};
async function loadSignatures() {
  const feed = await api('/signatures');
  $('signature-count').textContent = `${feed.signatures.length} RULES`;
  $('signature-list').innerHTML = feed.signatures.length ? feed.signatures.map(signature => `<div class="signature-row"><div><strong>${escapeHtml(signature.name)}</strong><p>${escapeHtml(signature.id)} · ${escapeHtml(signature.category)} · ${escapeHtml(signature.target)}</p><a href="${escapeHtml(signature.source)}" target="_blank" rel="noopener noreferrer">Source ↗</a></div><span class="badge ${escapeHtml(signature.action)}">${escapeHtml(signature.action)}</span></div>`).join('') : '<p class="help">The feed is empty. An example document is ready to import below.</p>';
  if (!signaturesInitialized) { $('signature-document').value = JSON.stringify(feed.signatures.length ? feed : exampleFeed,null,2); signaturesInitialized = true; }
}

async function refresh() {
  await loadDashboard();
  if(view === 'policies') await loadPolicies();
  if(view === 'events') await loadEvents();
  if(view === 'signatures') await loadSignatures();
}
async function showView(name) {
  view = name;
  for(const section of document.querySelectorAll('.view')) section.hidden = section.id !== name;
  for(const item of document.querySelectorAll('.nav-item')) item.classList.toggle('active',item.dataset.view === name);
  const names = {overview:['Overview','Security in one place.','Policies, events and usage across your AI agents.'],policies:['Policies','Your policies, under control.','Edit configurations and publish new versions for the gateway.'],events:['Events','See what happened.','Browse decisions and usage reports received from the gateway.'],signatures:['Signatures','Simple rules. One shared feed.','Import signatures and make them available to the gateway.']};
  $('breadcrumb').textContent = names[name][0]; $('page-title').textContent = names[name][1]; $('page-description').textContent = names[name][2];
  if(token) try { await refresh(); } catch(error) { toast(error.message,true); }
}

for(const item of document.querySelectorAll('.nav-item')) item.addEventListener('click',() => showView(item.dataset.view));
$('open-policies').addEventListener('click',() => showView('policies'));
$('refresh').addEventListener('click',event => job(event.currentTarget,async () => {await refresh();toast('Data refreshed.');}));
$('demo').addEventListener('click',event => job(event.currentTarget,async () => {const result=await api('/demo/events',{method:'POST'});await refresh();toast(`Added ${result.created} sample events, marked DEMO.`);}));
$('credentials').addEventListener('click',() => {$('login-error').textContent='';$('login-dialog').showModal();});
$('login-dialog').addEventListener('cancel',event => {if(!token)event.preventDefault();});
$('login-form').addEventListener('submit',async event => {
  event.preventDefault();
  const previousToken = token; token=$('api-token').value.trim();
  const button=event.currentTarget.querySelector('button[type=submit]');button.disabled=true;
  try {await refresh();sessionStorage.setItem('noorpointer-token',token);$('login-dialog').close();$('login-error').textContent='';}
  catch(error){token=previousToken;$('login-error').textContent=error.message;}
  finally{button.disabled=false;}
});
$('profile').addEventListener('change',event => {
  if(event.target.value) job(event.target,async () => {setEditor(await api('/profiles/'+event.target.value));$('draft-name').value=event.target.value+'-custom';});
});
$('policy-document').addEventListener('input',renderControls);
$('quick-controls').addEventListener('change',event => {
  try {
    const document=editorDocument(),target=event.target;
    if(target.dataset.control) document.controls[target.dataset.control].enabled=target.checked;
    if(target.dataset.action) document.controls[target.dataset.action].action=target.value;
    if(target.id==='injection-threshold') document.controls.prompt_injection.threshold=Number(target.value);
    $('policy-document').value=JSON.stringify(document,null,2);$('validation-result').textContent='Configuration changed — save a new version.';
  }catch(error){toast(error.message,true);}
});
$('validate-policy').addEventListener('click',event => job(event.currentTarget,async () => {
  await api('/policies/validate',{method:'POST',body:JSON.stringify({document:$('policy-document').value})});
  $('validation-result').textContent='Configuration is valid.';toast('Configuration passed validation.');
}));
$('save-policy').addEventListener('click',event => job(event.currentTarget,async () => {
  const name=$('draft-name').value.trim();if(!name)throw new Error('Enter a version name.');
  const revision=await api('/policies',{method:'POST',body:JSON.stringify({name,description:'Created from dashboard',document:$('policy-document').value})});
  await loadPolicies();toast(`Saved version ${revision.version}. Click Publish to activate it.`);
}));
$('revision-list').addEventListener('click',event => {
  const button=event.target.closest('button');if(!button)return;
  job(button,async () => {
    if(button.dataset.edit){const revision=await api('/policies/'+button.dataset.edit);setEditor(revision.document);$('draft-name').value=revision.name+'-copy';$('draft-name').focus();}
    if(button.dataset.publish){await api('/policies/'+button.dataset.publish+'/publish',{method:'POST'});await refresh();toast(`Published version ${button.dataset.publish}. The gateway can fetch the updated configuration.`);}
  });
});
$('event-filters').addEventListener('submit',event => {event.preventDefault();page=0;loadEvents().catch(error=>toast(error.message,true));});
$('event-filters').addEventListener('reset',() => {page=0;setTimeout(()=>loadEvents().catch(error=>toast(error.message,true)),0);});
$('previous-page').addEventListener('click',() => {page--;loadEvents().catch(error=>toast(error.message,true));});
$('next-page').addEventListener('click',() => {page++;loadEvents().catch(error=>toast(error.message,true));});
$('event-rows').addEventListener('click',async event => {
  const row=event.target.closest('[data-event]');if(!row)return;
  try {const detail=await api('/events/'+encodeURIComponent(row.dataset.event));$('event-detail').textContent=JSON.stringify(detail,null,2);$('detail-dialog').showModal();}
  catch(error){toast(error.message,true);}
});
$('close-detail').addEventListener('click',()=>$('detail-dialog').close());
for(const button of document.querySelectorAll('[data-export]')) button.addEventListener('click',() => job(button,async () => {
  const query=eventQuery();query.set('format',button.dataset.export);
  const blob=await api('/events/export?'+query,{download:true});
  const url=URL.createObjectURL(blob),link=document.createElement('a');link.href=url;link.download='noorpointer-events.'+button.dataset.export;link.click();setTimeout(()=>URL.revokeObjectURL(url),1000);
}));
$('import-signatures').addEventListener('click',event => job(event.currentTarget,async () => {
  const result=await api('/signatures/import',{method:'POST',body:JSON.stringify({document:$('signature-document').value})});
  await loadSignatures();toast(`Feed replaced. Imported ${result.imported} rules.`);
}));
setInterval(async () => {
  if(!token || $('login-dialog').open || document.hidden || !['overview','events'].includes(view))return;
  try {await refresh();} catch {$('connection').textContent='Disconnected';$('connection').className='connection';}
},15000);
if(token) refresh().catch(error=>{toast(error.message,true);$('login-dialog').showModal();});
else $('login-dialog').showModal();
