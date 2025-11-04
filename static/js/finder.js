async function loadIndex() {
  const res = await fetch("/api/breweries_index");
  if (!res.ok) { console.error("Failed to load index"); return; }
  return await res.json();
}

function fillSelect(sel, options, placeholder="-- choose --") {
  sel.innerHTML = "";
  const ph = document.createElement("option");
  ph.value = "";
  ph.textContent = placeholder;
  sel.appendChild(ph);
  for (const opt of options) {
    const o = document.createElement("option");
    o.value = opt;
    o.textContent = opt;
    sel.appendChild(o);
  }
}

document.addEventListener("DOMContentLoaded", async () => {
  const stateSel = document.getElementById("stateSel");
  const citySel = document.getElementById("citySel");
  const venueSel = document.getElementById("venueSel");
  const selection = document.getElementById("selection");
  const continueBtn = document.getElementById("continueBtn");

  const idx = await loadIndex();
  fillSelect(stateSel, idx.states, "-- choose state --");

  stateSel.addEventListener("change", () => {
    const st = stateSel.value;
    selection.textContent = "";
    venueSel.disabled = true;
    fillSelect(venueSel, [], "-- choose venue --");

    if (!st) {
      citySel.disabled = true;
      fillSelect(citySel, [], "-- choose city --");
      continueBtn.disabled = true;
      return;
    }
    const cities = idx.cities[st] || [];
    citySel.disabled = false;
    fillSelect(citySel, cities, "-- choose city --");
    continueBtn.disabled = true;
  });

  citySel.addEventListener("change", () => {
    const st = stateSel.value;
    const city = citySel.value;
    selection.textContent = "";
    if (!city) {
      venueSel.disabled = true;
      fillSelect(venueSel, [], "-- choose venue --");
      continueBtn.disabled = true;
      return;
    }
    const key = `${st}||${city}`;
    const venues = idx.venues[key] || [];
    venueSel.disabled = false;
    fillSelect(venueSel, venues, "-- choose venue --");
    continueBtn.disabled = true;
  });

  venueSel.addEventListener("change", () => {
    const st = stateSel.value;
    const city = citySel.value;
    const venue = venueSel.value;
    if (venue) {
      selection.innerHTML = `<p><strong>Selected:</strong> ${venue} — ${city}, ${st}</p>`;
      continueBtn.disabled = false;
    } else {
      selection.textContent = "";
      continueBtn.disabled = true;
    }
  });

  continueBtn.addEventListener("click", () => {
    const st = stateSel.value;
    const city = citySel.value;
    const venue = venueSel.value;
    alert(`Proceeding to match beers for ${venue} — ${city}, ${st}.\n(Connect this button to /match?state=${encodeURIComponent(st)}&city=${encodeURIComponent(city)}&venue=${encodeURIComponent(venue)})`);
  });
});
