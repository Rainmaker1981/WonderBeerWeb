# app.py
import csv
import json
import os
import threading
from pathlib import Path
from flask import Flask, jsonify, render_template_string, request

app = Flask(__name__)

# --- Paths & globals ---
DATA_DIR = Path(os.environ.get("DATA_DIR", "data"))
CSV_PATH = DATA_DIR / "breweries.csv"
INDEX_PATH = Path(os.environ.get("BREWERIES_INDEX_PATH", "/tmp/breweries_index.json"))

_init_lock = threading.Lock()
_initialized = False
_index_mem = {}  # in-memory copy to serve quickly


def build_breweries_index(csv_path: Path, out_path: Path) -> dict:
    """
    Read the master breweries.csv and emit a compact JSON index with only:
    name, city, state_province, country, website_url, longitude, latitude.
    Also builds nested maps for dropdowns: countries -> states -> cities -> venues.
    """
    wanted = {
        "name",
        "city",
        "state_province",
        "country",
        "website_url",
        "longitude",
        "latitude",
    }

    venues = []  # flat list of dicts with just the wanted keys
    countries = {}

    with csv_path.open(newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            rec = {k: (row.get(k) or "").strip() for k in wanted}

            # Normalize lon/lat to float when possible
            for coord in ("longitude", "latitude"):
                v = rec.get(coord, "")
                try:
                    rec[coord] = float(v) if v not in ("", None) else None
                except ValueError:
                    rec[coord] = None

            venues.append(rec)

            # Build hierarchical index
            country = rec["country"] or "Unknown"
            state = rec["state_province"] or "Unknown"
            city = rec["city"] or "Unknown"
            name = rec["name"] or "Unknown"

            countries.setdefault(country, {})
            countries[country].setdefault(state, {})
            countries[country][state].setdefault(city, [])
            countries[country][state][city].append(name)

    index = {"venues": venues, "index": countries}

    # Persist to disk (useful on Render for cold starts)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", encoding="utf-8") as f:
        json.dump(index, f, ensure_ascii=False)

    return index


def _load_or_build_index():
    """
    Load from disk cache if present; otherwise build from CSV.
    """
    if INDEX_PATH.exists():
        with INDEX_PATH.open(encoding="utf-8") as f:
            return json.load(f)

    if not CSV_PATH.exists():
        # No CSV yet—return empty shape so UI can handle it gracefully.
        empty = {"venues": [], "index": {}}
        INDEX_PATH.parent.mkdir(parents=True, exist_ok=True)
        with INDEX_PATH.open("w", encoding="utf-8") as f:
            json.dump(empty, f)
        return empty

    return build_breweries_index(CSV_PATH, INDEX_PATH)


def init_once():
    """
    Safe to call on every request; runs the heavy init exactly once.
    """
    global _initialized, _index_mem
    if _initialized:
        return

    with _init_lock:
        if _initialized:
            return
        _index_mem = _load_or_build_index()
        _initialized = True


@app.before_request
def _ensure_initialized():
    init_once()


# ------------------- API -------------------

@app.get("/api/health")
def api_health():
    csv_exists = CSV_PATH.exists()
    count = len(_index_mem.get("venues", [])) if _initialized else 0
    return jsonify(
        {
            "ok": True,
            "csv_exists": csv_exists,
            "csv_path": str(CSV_PATH),
            "index_path": str(INDEX_PATH),
            "count": count,
            "initialized": _initialized,
        }
    )


@app.get("/api/index")
def api_index():
    # Return the whole hierarchy (countries -> states -> cities -> venue names)
    return jsonify(_index_mem.get("index", {}))


@app.get("/api/countries")
def api_countries():
    return jsonify(sorted(list(_index_mem.get("index", {}).keys())))


@app.get("/api/states")
def api_states():
    country = request.args.get("country", "")
    states = sorted(list(_index_mem.get("index", {}).get(country, {}).keys()))
    return jsonify(states)


@app.get("/api/cities")
def api_cities():
    country = request.args.get("country", "")
    state = request.args.get("state_province", "")
    cities = sorted(
        list(_index_mem.get("index", {}).get(country, {}).get(state, {}).keys())
    )
    return jsonify(cities)


@app.get("/api/venues")
def api_venues():
    country = request.args.get("country", "")
    state = request.args.get("state_province", "")
    city = request.args.get("city", "")
    venues = _index_mem.get("index", {}).get(country, {}).get(state, {}).get(city, [])
    return jsonify(sorted(venues))


@app.get("/api/venue_detail")
def api_venue_detail():
    """
    Given country, state_province, city, name -> return the full record
    including website_url and coordinates for 'Get Directions'.
    """
    country = request.args.get("country", "")
    state = request.args.get("state_province", "")
    city = request.args.get("city", "")
    name = request.args.get("name", "")

    # simple linear scan over venues list (could be indexed by tuple if needed)
    for v in _index_mem.get("venues", []):
        if (
            (v.get("country") == country)
            and (v.get("state_province") == state)
            and (v.get("city") == city)
            and (v.get("name") == name)
        ):
            return jsonify(v)

    return jsonify({"error": "not found"}), 404


# ------------------- Minimal UI (optional) -------------------

_INDEX_HTML = """
<!doctype html>
<html>
  <head>
    <meta charset="utf-8" />
    <title>WonderBEER – Brewery Finder</title>
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <style>
      body { font-family: system-ui, -apple-system, Segoe UI, Roboto, Arial, sans-serif; margin: 24px; }
      .row { display: grid; gap: 12px; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); margin-bottom: 16px; }
      select, button, a { padding: 10px; font-size: 16px; }
      .card { border: 1px solid #ddd; border-radius: 12px; padding: 16px; box-shadow: 0 2px 10px rgba(0,0,0,0.05); }
      .muted { color: #555; font-size: 14px; }
      .actions a { margin-right: 12px; }
    </style>
  </head>
  <body>
    <h1>WonderBEER — Find a Venue</h1>
    <p class="muted">Start at the left and work across: Country → State/Province → City → Venue.</p>

    <div class="row">
      <select id="country"></select>
      <select id="state"></select>
      <select id="city"></select>
      <select id="venue"></select>
    </div>

    <div class="card">
      <div id="chosen" class="muted">No venue selected.</div>
      <div class="actions" id="links" style="margin-top:10px;"></div>
    </div>

    <script>
      const qs = (s)=>document.querySelector(s);
      const countrySel = qs('#country');
      const stateSel = qs('#state');
      const citySel = qs('#city');
      const venueSel = qs('#venue');
      const chosen = qs('#chosen');
      const links = qs('#links');

      async function getJSON(url){ const r = await fetch(url); return r.json(); }

      function fill(sel, arr, prompt){
        sel.innerHTML = '';
        const opt = document.createElement('option');
        opt.value = ''; opt.textContent = prompt;
        sel.appendChild(opt);
        for(const v of arr){
          const o = document.createElement('option');
          o.value = v; o.textContent = v; sel.appendChild(o);
        }
        sel.disabled = arr.length === 0;
      }

      async function refreshCountries(){
        const countries = await getJSON('/api/countries');
        fill(countrySel, countries, 'Select Country');
        fill(stateSel, [], 'Select State/Province');
        fill(citySel, [], 'Select City');
        fill(venueSel, [], 'Select Venue');
      }

      async function refreshStates(){
        const c = countrySel.value;
        if(!c){ fill(stateSel, [], 'Select State/Province'); return; }
        const states = await getJSON(`/api/states?country=${encodeURIComponent(c)}`);
        fill(stateSel, states, 'Select State/Province');
        fill(citySel, [], 'Select City');
        fill(venueSel, [], 'Select Venue');
      }

      async function refreshCities(){
        const c = countrySel.value, s = stateSel.value;
        if(!c || !s){ fill(citySel, [], 'Select City'); return; }
        const cities = await getJSON(`/api/cities?country=${encodeURIComponent(c)}&state_province=${encodeURIComponent(s)}`);
        fill(citySel, cities, 'Select City');
        fill(venueSel, [], 'Select Venue');
      }

      async function refreshVenues(){
        const c = countrySel.value, s = stateSel.value, ci = citySel.value;
        if(!c || !s || !ci){ fill(venueSel, [], 'Select Venue'); return; }
        const venues = await getJSON(`/api/venues?country=${encodeURIComponent(c)}&state_province=${encodeURIComponent(s)}&city=${encodeURIComponent(ci)}`);
        fill(venueSel, venues, 'Select Venue');
      }

      async function showVenue(){
        links.innerHTML = '';
        const c = countrySel.value, s = stateSel.value, ci = citySel.value, n = venueSel.value;
        if(!c || !s || !ci || !n){ chosen.textContent = 'No venue selected.'; return; }

        const v = await getJSON(`/api/venue_detail?country=${encodeURIComponent(c)}&state_province=${encodeURIComponent(s)}&city=${encodeURIComponent(ci)}&name=${encodeURIComponent(n)}`);
        if(v.error){ chosen.textContent = 'Not found'; return; }

        chosen.textContent = `${v.name} — ${v.city}, ${v.state_province} (${v.country})`;

        // Visit Website
        if(v.website_url){
          const a = document.createElement('a');
          a.href = v.website_url; a.target = '_blank'; a.rel='noopener';
          a.textContent = 'Visit Website';
          links.appendChild(a);
        }

        // Get Directions
        const g = document.createElement('a');
        if(v.latitude != null && v.longitude != null){
          g.href = `https://www.google.com/maps/dir/?api=1&destination=${encodeURIComponent(v.latitude + ',' + v.longitude)}`;
        } else {
          g.href = `https://www.google.com/maps/search/?api=1&query=${encodeURIComponent(v.name + ' ' + v.city + ' ' + v.state_province)}`;
        }
        g.target = '_blank'; g.rel='noopener';
        g.textContent = 'Get Directions';
        links.appendChild(g);
      }

      countrySel.addEventListener('change', refreshStates);
      stateSel.addEventListener('change', refreshCities);
      citySel.addEventListener('change', refreshVenues);
      venueSel.addEventListener('change', showVenue);

      refreshCountries();
    </script>
  </body>
</html>
"""

@app.get("/")
def home():
    return render_template_string(_INDEX_HTML)


# ------------------- Entry -------------------
if __name__ == "__main__":
    # Local dev: ensure initialization before first request
    init_once()
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", "5000")))
