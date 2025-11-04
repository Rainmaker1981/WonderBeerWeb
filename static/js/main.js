// Breweries cascading selectors
async function loadBreweriesTree() {
  const res = await fetch('/api/breweries');
  const tree = await res.json();
  const $country = document.getElementById('country');
  const $state = document.getElementById('state');
  const $city = document.getElementById('city');
  const $venue = document.getElementById('venue');

  if (!$country || !$state || !$city || !$venue) return;

  $country.innerHTML = '<option value="">Select Country</option>';
  Object.keys(tree).sort().forEach(c => {
    const opt = document.createElement('option');
    opt.value = c; opt.textContent = c;
    $country.appendChild(opt);
  });

  function resetSelect(el, label) { el.innerHTML = `<option value="">Select ${label}</option>`; }
  resetSelect($state, 'State/Province'); resetSelect($city, 'City'); resetSelect($venue, 'Venue');

  $country.addEventListener('change', () => {
    resetSelect($state,'State/Province'); resetSelect($city,'City'); resetSelect($venue,'Venue');
    const c = $country.value;
    if (!c) return;
    const states = tree[c];
    const stateKeys = Object.keys(states).sort((a,b)=> (a||'').localeCompare(b||''));
    stateKeys.forEach(s => {
      const opt = document.createElement('option');
      opt.value = s; opt.textContent = s || '(no state)';
      $state.appendChild(opt);
    });
  });

  $state.addEventListener('change', () => {
    resetSelect($city,'City'); resetSelect($venue,'Venue');
    const c = $country.value; const s = $state.value;
    if (!c) return;
    const cities = (tree[c]||{})[s] || {};
    Object.keys(cities).sort().forEach(city => {
      const opt = document.createElement('option');
      opt.value = city; opt.textContent = city;
      $city.appendChild(opt);
    });
  });

  $city.addEventListener('change', () => {
    resetSelect($venue,'Venue');
    const c = $country.value; const s = $state.value; const ci = $city.value;
    const venues = (((tree[c]||{})[s]||{})[ci]) || [];
    venues.sort((a,b)=> a.name.localeCompare(b.name)).forEach(v => {
      const opt = document.createElement('option');
      opt.value = v.name; opt.textContent = v.name;
      opt.dataset.lat = v.latitude; opt.dataset.lon = v.longitude; opt.dataset.website = v.website_url || '';
      $venue.appendChild(opt);
    });
  });

  const go = document.getElementById('goMatch');
  if (go) {
    go.addEventListener('click', () => {
      const c = $country.value, s = $state.value, ci = $city.value, v = $venue.value;
      const pf = (document.getElementById('profile_file') || {}).value || '';
      if (!c || !ci || !v) { alert('Please pick Country, City, and Venue.'); return; }
      const params = new URLSearchParams({country:c, state:s, city:ci, venue:v, profile:pf});
      window.location.href = '/match?' + params.toString();
    });
  }
}

async function matchPageInit() {
  if (typeof args === 'undefined') return;
  const btn = document.getElementById('runMatch');
  const out = document.getElementById('matchResults');
  btn?.addEventListener('click', async () => {
    out.textContent = 'Fetching menu…';
    const res = await fetch('/match/run', {
      method: 'POST',
      headers: {'Content-Type':'application/json'},
      body: JSON.stringify(args)
    });
    const data = await res.json();
    const list = data.results || [];
    if (!list.length) { out.textContent = 'No menu found.'; return; }
    const rows = list.map(b => {
      const abv = (b.abv != null) ? b.abv + '%' : '';
      const ibu = (b.ibu != null) ? b.ibu : '';
      return `<tr>
        <td>${b.name||''}</td>
        <td>${b.style||''}</td>
        <td>${abv}</td>
        <td>${ibu}</td>
        <td><strong>${b.match_score||0}</strong></td>
      </tr>`
    }).join('');
    out.innerHTML = `<table class="table">
      <thead><tr><th>Beer</th><th>Style</th><th>ABV</th><th>IBU</th><th>Match</th></tr></thead>
      <tbody>${rows}</tbody>
    </table>`;
  });
}

async function lookupInit() {
  const btn = document.getElementById('loadCache');
  const out = document.getElementById('cacheOut');
  btn?.addEventListener('click', async () => {
    const res = await fetch('/api/beer_cache');
    const data = await res.json();
    out.textContent = JSON.stringify(data, null, 2);
  });
}

document.addEventListener('DOMContentLoaded', () => {
  loadBreweriesTree();
  matchPageInit();
  lookupInit();
});
