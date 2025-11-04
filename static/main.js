async function getJSON(url){ const r = await fetch(url); return r.json(); }

function fillSelect(sel, items, prompt){
  sel.innerHTML = "";
  const o = document.createElement("option");
  o.value=""; o.textContent = prompt;
  sel.appendChild(o);
  for(const it of items){
    const op = document.createElement("option");
    op.value = it; op.textContent = it;
    sel.appendChild(op);
  }
  sel.disabled = items.length === 0;
}

async function setupBreweryDropdowns(){
  const countrySel = document.getElementById("country");
  const stateSel = document.getElementById("state");
  const citySel = document.getElementById("city");
  const venueSel = document.getElementById("venue");

  async function refreshCountries(){
    const countries = await getJSON('/api/countries');
    fillSelect(countrySel, countries, "Country");
    fillSelect(stateSel, [], "State/Province");
    fillSelect(citySel, [], "City");
    fillSelect(venueSel, [], "Venue");
  }
  async function refreshStates(){
    const c = countrySel.value;
    if(!c){ fillSelect(stateSel, [], "State/Province"); return; }
    const states = await getJSON('/api/states?country=' + encodeURIComponent(c));
    fillSelect(stateSel, states, "State/Province");
    fillSelect(citySel, [], "City");
    fillSelect(venueSel, [], "Venue");
  }
  async function refreshCities(){
    const c = countrySel.value, s = stateSel.value;
    if(!c || !s){ fillSelect(citySel, [], "City"); return; }
    const cities = await getJSON(`/api/cities?country=${encodeURIComponent(c)}&state_province=${encodeURIComponent(s)}`);
    fillSelect(citySel, cities, "City");
    fillSelect(venueSel, [], "Venue");
  }
  async function refreshVenues(){
    const c = countrySel.value, s = stateSel.value, ci = citySel.value;
    if(!c || !s || !ci){ fillSelect(venueSel, [], "Venue"); return; }
    const venues = await getJSON(`/api/venues?country=${encodeURIComponent(c)}&state_province=${encodeURIComponent(s)}&city=${encodeURIComponent(ci)}`);
    fillSelect(venueSel, venues, "Venue");
  }

  countrySel.addEventListener('change', refreshStates);
  stateSel.addEventListener('change', refreshCities);
  citySel.addEventListener('change', refreshVenues);

  await refreshCountries();
}
