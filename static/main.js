
async function fetchJSON(url){ const r = await fetch(url); if(!r.ok) throw new Error(await r.text()); return r.json(); }

async function setupHome(){
  const countrySel=document.getElementById("countrySelect");
  const stateSel=document.getElementById("stateSelect");
  const citySel=document.getElementById("citySelect");
  const venueSel=document.getElementById("venueSelect");
  const venueMeta=document.getElementById("venueMeta");
  const goAnalytics=document.getElementById("goAnalytics");
  const profileSelect=document.getElementById("profileSelect");
  if(goAnalytics&&profileSelect){ goAnalytics.addEventListener("click",()=>{ window.location.href=`/analytics?profile=${encodeURIComponent(profileSelect.value)}`; }); }
  if(!countrySel) return;

  const countries = await fetchJSON("/api/locations/countries");
  countrySel.innerHTML = countries.map(c=>`<option value="${c}">${c}</option>`).join("");
  if(countries.includes("United States")) countrySel.value="United States";

  async function refreshStates(){
    const states = await fetchJSON(`/api/locations/states?country=${encodeURIComponent(countrySel.value)}`);
    stateSel.innerHTML = `<option value="">(Select)</option>` + states.map(s=>`<option value="${s}">${s}</option>`).join("");
    citySel.innerHTML = ""; venueSel.innerHTML = ""; venueMeta.textContent="";
  }
  async function refreshCities(){
    const cities = await fetchJSON(`/api/locations/cities?country=${encodeURIComponent(countrySel.value)}&state=${encodeURIComponent(stateSel.value)}`);
    citySel.innerHTML = `<option value="">(Select)</option>` + cities.map(c=>`<option value="${c}">${c}</option>`).join("");
    venueSel.innerHTML = ""; venueMeta.textContent="";
  }
  async function refreshVenues(){
    const venues = await fetchJSON(`/api/locations/venues?country=${encodeURIComponent(countrySel.value)}&state=${encodeURIComponent(stateSel.value)}&city=${encodeURIComponent(citySel.value)}`);
    venueSel.innerHTML = `<option value="">(Select)</option>` + venues.map(v=>`<option value="${v.name}">${v.name}</option>`).join("");
    venueSel._venues = venues; venueMeta.textContent = venues.length?`Found ${venues.length} venues`:"No venues found";
  }
  function updateVenueMeta(){
    const items = venueSel._venues||[]; const v = items.find(x=>x.name===venueSel.value);
    if(!v){ venueMeta.textContent=""; return; }
    let loc=[v.city,v.state_province].filter(Boolean).join(", ");
    venueMeta.innerHTML = `${v.name} — ${loc} ${v.url?`• <a href="${v.url}" target="_blank">website</a>`:""}`;
  }

  await refreshStates();
  countrySel.addEventListener("change", refreshStates);
  stateSel.addEventListener("change", refreshCities);
  citySel.addEventListener("change", refreshVenues);
  venueSel.addEventListener("change", updateVenueMeta);
}

async function setupProfiles(){
  const form=document.getElementById("uploadForm"); const out=document.getElementById("uploadResult"); if(!form) return;
  form.addEventListener("submit", async (e)=>{
    e.preventDefault();
    const fd=new FormData(form); out.textContent="Uploading and processing...";
    try{
      const r=await fetch("/api/profiles/upload",{method:"POST", body:fd}); const j=await r.json(); if(!r.ok) throw new Error(j.error||"Upload failed");
      out.textContent = JSON.stringify(j.profile, null, 2);
      const list = await fetchJSON("/api/profiles"); const ul=document.getElementById("profileList");
      ul.innerHTML = list.map(p=>`<li><a href="/analytics?profile=${encodeURIComponent(p.file)}">${p.display_name}</a> <small class="muted">(${p.file})</small></li>`).join("");
    }catch(err){ out.textContent="Error: "+err.message; }
  });
}

function renderBar(canvasId, labels, data, title){
  const ctx=document.getElementById(canvasId); if(!ctx) return; if(ctx._chart) ctx._chart.destroy();
  ctx._chart = new Chart(ctx, {type:"bar", data:{labels, datasets:[{label:title, data}]}, options:{responsive:true, plugins:{legend:{display:false}, title:{display:true, text:title}}}});
}
function renderScatter(canvasId, points, title){
  const ctx=document.getElementById(canvasId); if(!ctx) return; if(ctx._chart) ctx._chart.destroy();
  ctx._chart = new Chart(ctx, {type:"scatter", data:{datasets:[{label:title, data:points}]},
    options:{responsive:true, plugins:{title:{display:true, text:title}}, scales:{x:{title:{display:true, text:title.includes("ABV")?"ABV %":"IBU"}}, y:{title:{display:true, text:"Rating"}, min:0, max:5}}}});
}

async function setupAnalytics(){
  const sel=document.getElementById("profileSelect"); if(!sel) return;
  const params=new URLSearchParams(window.location.search); const q=params.get("profile"); if(q) sel.value=q;
  async function loadProfile(){
    if(!sel.value) return;
    const j = await fetchJSON(`/api/profiles/${encodeURIComponent(sel.value)}`);
    renderBar("stylesChart", Object.keys(j.styles||{}), Object.values(j.styles||{}), "Styles (Top 5)");
    renderBar("flavorsChart", Object.keys(j.flavors||{}), Object.values(j.flavors||{}), "Flavors (Top 5)");
    renderScatter("abvChart", (j.abv||[]).map(p=>({x:p.abv,y:p.rating,label:p.beer})), "ABV vs Rating");
    renderScatter("ibuChart", (j.ibu||[]).map(p=>({x:p.ibu,y:p.rating,label:p.beer})), "IBU vs Rating");
    renderBar("breweriesChart", (j.breweries||[]).map(b=>`${b.name} (${b.city})`), (j.breweries||[]).map(b=>b.count), "Top Breweries");
    const rs=j.ratings||{}; const delta=(rs.mean_rating!=null && rs.mean_global!=null)?(rs.mean_rating-rs.mean_global).toFixed(3):"n/a";
    document.getElementById("ratingSummary").innerHTML = `<strong>Ratings:</strong><br>Mine: ${rs.mean_rating ?? "n/a"}<br>Global: ${rs.mean_global ?? "n/a"}<br>Delta: ${delta}<br>N=${rs.n ?? 0}`;
  }
  sel.addEventListener("change", loadProfile);
  await loadProfile();
}

document.addEventListener("DOMContentLoaded", ()=>{ setupHome(); setupProfiles(); setupAnalytics(); });
