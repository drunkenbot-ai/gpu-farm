const $ = id => document.getElementById(id);
const esc = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const auth = () => { const token = localStorage.getItem('farmAdminToken'); return token ? {'X-Farm-Admin-Token': token} : {}; };
async function api(url, options = {}) { const response = await fetch(url, {...options, headers: {...auth(), ...(options.headers || {})}}); if (!response.ok) throw new Error(await response.text()); return response.json(); }

document.querySelector('main').insertAdjacentHTML('beforeend', '<section><h2>GPU tags</h2><div id="tags">Loading…</div></section><section><h2>CPU telemetry trend</h2><div id="chart" class="chart"></div></section>');

function chart(samples) {
  const values = samples.map(x => Number(x.payload?.cpu_percent)).filter(Number.isFinite);
  if (!values.length) return $('chart').textContent = 'No CPU samples yet.';
  const max = Math.max(100, ...values);
  $('chart').innerHTML = values.map(value => `<i title="${value.toFixed(1)}%" style="height:${Math.max(2, value / max * 100)}%"></i>`).join('');
}
function tags(gpus) {
  $('tags').innerHTML = gpus.map(g => `<article class="pool"><b>${esc(g.worker_id)} / ${esc(g.identifier)}</b> ${esc((g.tags || []).join(', '))}<form onsubmit="saveTags(event,'${esc(g.worker_id)}','${esc(g.identifier)}')"><input value="${esc((g.manual_tags || []).join(', '))}" placeholder="comma-separated tags"><button>Save</button></form></article>`).join('') || 'No joined GPUs.';
}
async function saveTags(event, worker, gpu) { event.preventDefault(); const tags = event.target.querySelector('input').value.split(',').map(x => x.trim()).filter(Boolean); try { await api(`/tags/workers/${encodeURIComponent(worker)}/gpus/${encodeURIComponent(gpu)}`, {method:'PUT',headers:{'Content-Type':'application/json'},body:JSON.stringify({tags})}); refresh(); } catch (error) { alert(error.message); } }

async function refresh() {
  try {
    const [health, workers, jobs, telemetry, pools, inventory] = await Promise.all(['/health','/workers','/jobs','/monitoring/history?limit=16','/pools','/tags'].map(api));
    $('summary').innerHTML = [['Mode',health.farm_mode],['Workers',health.workers],['Jobs',health.jobs]].map(([k,v]) => `<div class="card">${k}<div class="number">${esc(v)}</div></div>`).join('');
    $('workers').innerHTML = workers.workers.map(w => `<tr><td>${esc(w.worker_id)}</td><td>${esc(w.status)}</td><td>${esc(w.backend)}</td><td>${esc(w.hostname)}</td></tr>`).join('');
    $('jobs').innerHTML = jobs.jobs.map(j => { const output=j.result?.artifact_bundle_url; return `<tr><td>${esc(j.spec.job_id)}</td><td>${esc(j.spec.status)}</td><td>${esc(j.assigned_worker_id)}</td><td>${output?`<a href="${encodeURI(output)}">Download</a>`:'—'}</td><td>${['pause','resume','cancel','restart'].map(a=>`<button onclick="job('${esc(j.spec.job_id)}','${a}')">${a}</button>`).join(' ')}</td></tr>`; }).join('');
    $('pools').innerHTML = pools.pools.map(p => `<article class="pool"><b>${esc(p.name)}</b> · ${p.stats.available_gpus}/${p.stats.gpu_count} GPUs <button onclick="poolDelete('${esc(p.id)}')">Delete</button></article>`).join('');
    $('job-pool').innerHTML = '<option value="">Any eligible worker</option>' + pools.pools.filter(p=>p.enabled).map(p=>`<option value="${esc(p.id)}">${esc(p.name)}</option>`).join('');
    $('telemetry').textContent = JSON.stringify(telemetry.samples, null, 2); chart(telemetry.samples); tags(inventory.gpus); cloud(health.farm_mode);
  } catch (error) { $('connection').textContent = 'Request failed'; console.error(error); }
}
async function cloud(mode) { if (mode !== 'cloud') return $('cloud').textContent='Local mode — no licensing service is contacted.'; const key=localStorage.getItem('cloudApiKey'); if (!key) return $('cloud').textContent='Cloud mode: set cloudApiKey in browser local storage.'; try { const result=await api('/cloud/status',{headers:{Authorization:`Bearer ${key}`}}); $('cloud').textContent=`${result.tier}: ${result.gpu_hours_remaining ?? 'unlimited'} GPU-hours remaining`; } catch (error) { $('cloud').textContent=error.message; } }
async function job(id, action) { try { await api(`/jobs/${encodeURIComponent(id)}/${action}`,{method:'POST'}); refresh(); } catch (error) { alert(error.message); } }
async function poolDelete(id) { if (!confirm('Delete pool?')) return; try { await api(`/pools/${id}`,{method:'DELETE'}); refresh(); } catch (error) { alert(error.message); } }
$('pool-form').onsubmit = async event => { event.preventDefault(); try { await api('/pools',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({name:$('pool-name').value})}); $('pool-name').value=''; refresh(); } catch (error) { alert(error.message); } };
$('job-form').onsubmit = async event => { event.preventDefault(); try { const job=JSON.parse($('job-json').value), key=localStorage.getItem('cloudApiKey'); const result=await api('/jobs',{method:'POST',headers:{'Content-Type':'application/json',...(key?{Authorization:`Bearer ${key}`}:{})},body:JSON.stringify({job,resource_pool_id:$('job-pool').value||undefined,estimated_gpu_hours:Number($('job-hours').value)})}); alert(`Queued ${result.job_id}`); refresh(); } catch (error) { alert(`Submission failed: ${error.message}`); } };
function live() { const proto=location.protocol==='https:'?'wss':'ws', socket=new WebSocket(`${proto}://${location.host}/ws`); socket.onopen=()=>{$('connection').textContent='Live';}; socket.onmessage=refresh; socket.onclose=()=>setTimeout(live,2000); }
refresh(); live(); setInterval(refresh,15000);
