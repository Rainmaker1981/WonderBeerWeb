async function fetchJSON(url){
  const res = await fetch(url);
  if(!res.ok) throw new Error(await res.text());
  return res.json();
}

function el(id){ return document.getElementById(id); }

async function loadCountries(){
  try{
    const data = await fetchJSON('/api/locations/countries');
    const select = el('country');
    select.innerHTML = '';
    for(const c of data.countries){
      const opt = document.createElement('option');
      opt.value = c; opt.textContent = c;
      select.appendChild(opt);
    }
    await loadStates();
  }catch(e){
    console.error(e);
  }
}

async function loadStates(){
  const country = el('country').value;
  try{
    const data = await fetchJSON('/api/locations/states?country='+encodeURIComponent(country));
    const select = el('state');
    select.innerHTML = '';
    for(const s of data.states){
      const opt = document.createElement('option');
      opt.value = s; opt.textContent = s;
      select.appendChild(opt);
    }
    await loadCities();
  }catch(e){
    console.error(e);
  }
}

async function loadCities(){
  const country = el('country').value;
  const state = el('state').value || '';
  try{
    const data = await fetchJSON('/api/locations/cities?country='+encodeURIComponent(country)+'&state='+encodeURIComponent(state));
    const select = el('city');
    select.innerHTML = '';
    for(const c of data.cities){
      const opt = document.createElement('option');
      opt.value = c; opt.textContent = c;
      select.appendChild(opt);
    }
    await loadBreweries();
  }catch(e){
    console.error(e);
  }
}

async function loadBreweries(){
  const country = el('country').value;
  const state = el('state').value || '';
  const city = el('city').value || '';
  try{
    const data = await fetchJSON('/api/locations/breweries?country='+encodeURIComponent(country)+'&state='+encodeURIComponent(state)+'&city='+encodeURIComponent(city));
    const select = el('brewery');
    select.innerHTML = '';
    for(const b of data.breweries){
      const opt = document.createElement('option');
      opt.value = b; opt.textContent = b;
      select.appendChild(opt);
    }
  }catch(e){
    console.error(e);
  }
}

async function uploadProfile(){
  const file = el('untappd_csv').files[0];
  const display = el('display_name').value.trim();
  const status = el('upload_status');
  const preview = el('profile_preview');
  if(!file){
    status.textContent = 'Please select a CSV.';
    return;
  }
  status.textContent = 'Parsing…';
  const form = new FormData();
  form.append('file', file);
  form.append('display_name', display || '');
  try{
    const res = await fetch('/api/profiles/upload', { method: 'POST', body: form });
    const data = await res.json();
    if(!res.ok){ throw new Error(data.error || 'Upload failed'); }
    status.textContent = 'Profile saved.';
    preview.classList.remove('muted','error');
    preview.classList.add('success');
    preview.innerHTML = renderProfilePreview(data);
  }catch(e){
    status.textContent = 'Error parsing file.';
    preview.classList.remove('success');
    preview.classList.add('error');
    preview.textContent = e.message;
  }
}

function renderKV(kv){
  return Object.entries(kv).map(([k,v])=>`<span class="pill">${k}: ${v}</span>`).join('');
}

function renderBreweries(list){
  return list.map(b=>{
    const link = b.url ? `<a href="${b.url}" target="_blank" rel="noopener">${b.name}</a>` : b.name;
    const loc = [b.city, b.state].filter(Boolean).join(', ');
    return `<div class="pill">${link} — ${loc} (${b.count})</div>`;
  }).join('');
}

function renderProfilePreview(p){
  const ratings = p.ratings || {};
  return `
    <div><strong>${p.name}</strong></div>
    <div class="muted" style="margin:6px 0 10px;">Your computed stats:</div>
    <div><strong>Top styles</strong><br>${renderKV(p.styles || {})}</div>
    <div style="margin-top:8px;"><strong>Top breweries</strong><br>${renderBreweries(p.breweries || [])}</div>
    <div style="margin-top:8px;"><strong>Top flavors</strong><br>${renderKV(p.flavors || {})}</div>
    <div style="margin-top:8px;"><strong>Ratings</strong><br>
      avg_user: ${ratings.avg_user ?? '—'} |
      avg_global: ${ratings.avg_global ?? '—'} |
      avg_delta: ${ratings.avg_delta ?? '—'}
    </div>
    <div class="muted" style="margin-top:8px;">Saved to <code>data/profiles/${(p.name||'').replace(/[^a-z0-9_-]/gi,'_')}.json</code></div>
  `;
}

document.addEventListener('DOMContentLoaded', ()=>{
  loadCountries();
  el('country').addEventListener('change', loadStates);
  el('state').addEventListener('change', loadCities);
  el('city').addEventListener('change', loadBreweries);
  el('btn_create').addEventListener('click', uploadProfile);
});
