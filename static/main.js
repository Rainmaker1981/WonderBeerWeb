window.WB = (function(){
  async function fetchJSON(url){ const r = await fetch(url); if(!r.ok) throw new Error(await r.text()); return await r.json(); }
  async function initDiscover(){
    const $country = document.getElementById('country');
    const $state = document.getElementById('state');
    const $city = document.getElementById('city');
    const $venue = document.getElementById('venue');
    const $list = document.getElementById('venueList');
    const $toMatch = document.getElementById('toMatch');

    function fill(sel, items){
      sel.innerHTML = "";
      items.forEach(v => {
        const o = document.createElement('option');
        o.value = v; o.textContent = v;
        sel.appendChild(o);
      });
    }

    const countries = await fetchJSON('/api/countries');
    fill($country, countries);
    $country.value = 'United States';

    async function loadStates(){
      const states = await fetchJSON(`/api/states?country=${encodeURIComponent($country.value)}`);
      fill($state, states);
      await loadCities();
    }
    async function loadCities(){
      const cities = await fetchJSON(`/api/cities?country=${encodeURIComponent($country.value)}&state=${encodeURIComponent($state.value)}`);
      fill($city, cities);
      await loadVenues();
    }
    async function loadVenues(){
      const venues = await fetchJSON(`/api/breweries?country=${encodeURIComponent($country.value)}&state=${encodeURIComponent($state.value)}&city=${encodeURIComponent($city.value)}`);
      fill($venue, venues.map(v => v.name));
      $list.innerHTML = venues.map(v => `<li>${v.name} — ${v.city}, ${v.state_province} (${v.country})</li>`).join('');
    }

    $country.addEventListener('change', loadStates);
    $state.addEventListener('change', loadCities);
    $city.addEventListener('change', loadVenues);
    await loadStates();

    $toMatch.addEventListener('click', () => {
      window.location.href = '/match';
    });
  }
  return { initDiscover };
})();
