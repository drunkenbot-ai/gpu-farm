const $ = id => document.getElementById(id);
async function refresh() {
  const [health, workers, jobs, telemetry] = await Promise.all(['/health','/workers','/jobs','/monitoring/history?limit=8'].map(x=>fetch(x).then(r=>r.json())));
  $('summary').innerHTML = [['Mode',health.farm_mode],['Workers',health.workers],['Jobs',health.jobs]].map(([k,v])=>`<div class="card">${k}<div class="number">${v}</div></div>`).join('');
  $('workers').innerHTML = workers.workers.map(w=>`<tr><td>${w.worker_id}</td><td>${w.status}</td><td>${w.backend}</td><td>${w.hostname||''}</td></tr>`).join('');
  $('jobs').innerHTML = jobs.jobs.map(j=>`<tr><td>${j.spec.job_id}</td><td>${j.spec.status}</td><td>${j.assigned_worker_id||''}</td><td>${j.result?.artifact_bundle_url||''}</td><td><button onclick="controlJob('${j.spec.job_id}','pause')">Pause</button> <button onclick="controlJob('${j.spec.job_id}','resume')">Resume</button> <button onclick="controlJob('${j.spec.job_id}','cancel')">Cancel</button> <button onclick="controlJob('${j.spec.job_id}','restart')">Restart</button></td></tr>`).join('');
  $('telemetry').textContent = JSON.stringify(telemetry.samples, null, 2);
}
function live() { const proto=location.protocol==='https:'?'wss':'ws'; const ws=new WebSocket(`${proto}://${location.host}/ws`); ws.onopen=()=>{$('connection').textContent='Live';}; ws.onmessage=refresh; ws.onclose=()=>{$('connection').textContent='Reconnecting…';setTimeout(live,2000)}; }
refresh(); live(); setInterval(refresh,15000);
async function controlJob(id, action) { const response = await fetch(`/jobs/${id}/${action}`, {method:'POST'}); if (!response.ok) alert(await response.text()); refresh(); }
