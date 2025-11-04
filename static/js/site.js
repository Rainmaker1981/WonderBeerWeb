// Chart.js helper loader (CDN injected per template when needed)

async function api(path, opts={}){
  const res = await fetch(path, {headers:{'X-Requested-With':'fetch'}, ...opts});
  if(!res.ok) throw new Error('API error '+res.status);
  return await res.json();
}

// Cascading dropdowns on /finder
async function initFinder(){
  const cSel = document.getElementById('country');
  const sSel = document.getElementById('state');
  const citySel = document.getElementById('city');
  const vSel = document.getElementById('venue');
  const listBox = document.getElementById('venueList');

  const countries = await api('/api/countries');
  cSel.innerHTML = '<option value="">Select Country</option>' + countries.map(c=>`<option>${c}</option>`).join('');

  cSel.onchange = async ()=>{
    sSel.innerHTML = '<option value="">Select State/Province</option>';
    citySel.innerHTML = '<option value="">Select City</option>';
    vSel.innerHTML = '<option value="">Select Venue</option>';
    listBox.innerHTML = '';
    if(!cSel.value) return;
    const states = await api('/api/states?country=' + encodeURIComponent(cSel.value));
    sSel.innerHTML = '<option value="">Select State/Province</option>' + states.map(s=>`<option>${s}</option>`).join('');
  };

  sSel.onchange = async ()=>{
    citySel.innerHTML = '<option value="">Select City</option>';
    vSel.innerHTML = '<option value="">Select Venue</option>';
    listBox.innerHTML = '';
    if(!sSel.value) return;
    const cities = await api(`/api/cities?country=${encodeURIComponent(cSel.value)}&state=${encodeURIComponent(sSel.value)}`);
    citySel.innerHTML = '<option value="">Select City</option>' + cities.map(c=>`<option>${c}</option>`).join('');
  };

  citySel.onchange = async ()=>{
    vSel.innerHTML = '<option value="">Select Venue</option>';
    listBox.innerHTML = '';
    if(!citySel.value) return;
    const venues = await api(`/api/venues?country=${encodeURIComponent(cSel.value)}&state=${encodeURIComponent(sSel.value)}&city=${encodeURIComponent(citySel.value)}`);
    vSel.innerHTML = '<option value="">Select Venue</option>' + venues.map(v=>`<option>${v.name}</option>`).join('');
    listBox.innerHTML = venues.map(v=>`<li>${v.name} <span class="small">${v.city}, ${v.state_province}</span> ${v.untappd_venue_url?`<a class="badge" href="${v.untappd_venue_url}" target="_blank">Untappd</a>`:''}</li>`).join('');
  };
}

// Profile charts
function renderProfileCharts(summary){
  if(!window.Chart) return;
  const ctx1 = document.getElementById('chartAbvIbu');
  const ctx2 = document.getElementById('chartRatings');
  if(ctx1){
    new Chart(ctx1, {
      type: 'scatter',
      data: {
        datasets: [{
          label: 'ABV vs IBU',
          data: summary.points_abv_ibu || [],
        }]
      },
      options: {scales:{x:{title:{display:true,text:'ABV %'}},y:{title:{display:true,text:'IBU'}}}}
    });
  }
  if(ctx2){
    new Chart(ctx2, {
      type: 'bar',
      data: {
        labels: ['Your Avg', 'Global Avg'],
        datasets: [{
          label: 'Rating',
          data: [summary.rating_mean || 0, summary.global_rating_mean || 0],
        }]
      },
      options: {scales:{y:{min:0,max:5}}}
    });
  }
}
