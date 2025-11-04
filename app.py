from flask import Flask, jsonify, request, render_template
import csv, os, json, time
from urllib.parse import quote

app = Flask(__name__)

# --- File locations ---
CSV_PATH   = os.path.join(os.path.dirname(__file__), "data", "breweries.csv")
INDEX_PATH = os.environ.get("BREW_INDEX_PATH", "/tmp/breweries_index.json")

# --- US state long name -> 2-letter code ---
US_STATE_TO_CODE = {
    "alabama":"AL","alaska":"AK","arizona":"AZ","arkansas":"AR","california":"CA","colorado":"CO",
    "connecticut":"CT","delaware":"DE","district of columbia":"DC","florida":"FL","georgia":"GA",
    "hawaii":"HI","idaho":"ID","illinois":"IL","indiana":"IN","iowa":"IA","kansas":"KS","kentucky":"KY",
    "louisiana":"LA","maine":"ME","maryland":"MD","massachusetts":"MA","michigan":"MI","minnesota":"MN",
    "mississippi":"MS","missouri":"MO","montana":"MT","nebraska":"NE","nevada":"NV","new hampshire":"NH",
    "new jersey":"NJ","new mexico":"NM","new york":"NY","north carolina":"NC","north dakota":"ND",
    "ohio":"OH","oklahoma":"OK","oregon":"OR","pennsylvania":"PA","rhode island":"RI","south carolina":"SC",
    "south dakota":"SD","tennessee":"TN","texas":"TX","utah":"UT","vermont":"VT","virginia":"VA",
    "washington":"WA","west virginia":"WV","wisconsin":"WI","wyoming":"WY"
}

def us_state_to_code(state_province: str) -> str:
    if not state_province:
        return ""
    return US_STATE_TO_CODE.get(state_province.strip().lower(), "")

# --- Normalize helper ---
def _norm(s):
    return (s or "").strip()

# --- Read the big breweries.csv and extract only needed columns ---
def _read_csv_rows(csv_path):
    if not os.path.exists(csv_path):
        app.logger.error(f"CSV not found: {csv_path}")
        return []
    with open(csv_path, newline="", encoding="utf-8") as f:
        rdr = csv.DictReader(f)
        return list(rdr)

def _rows_to_minimal(records):
    """Extract only name, city, state_province, country, website_url, longitude, latitude"""
    out = []
    for r in records:
        country = _norm(r.get("country"))
        state_p = _norm(r.get("state_province"))
        city    = _norm(r.get("city"))
        name    = _norm(r.get("name"))
        web     = _norm(r.get("website_url"))
        lat     = r.get("latitude")
        lng     = r.get("longitude")
        try: lat = float(lat) if lat else None
        except: lat = None
        try: lng = float(lng) if lng else None
        except: lng = None

        if not name:
            continue

        out.append({
            "country": country,
            "state_province": state_p,
            "state_code": us_state_to_code(state_p) if country == "United States" else "",
            "city": city,
            "name": name,
            "website_url": web,
            "latitude": lat,
            "longitude": lng
        })
    return out

# --- Build a hierarchical JSON index for fast dropdowns ---
def _build_index(minimal):
    countries = set()
    states, cities, venues = {}, {}, {}
    for it in minimal:
        c, s, ci, v = it["country"], it["state_province"], it["city"], it["name"]
        countries.add(c)
        states.setdefault(c, set()).add(s)
        cities.setdefault((c, s), set()).add(ci)
        venues.setdefault((c, s, ci), []).append(it)

    return {
        "countries": sorted(x for x in countries if x),
        "states": {c: sorted(x for x in vals if x) for c, vals in states.items()},
        "cities": {f"{c}||{s}": sorted(x for x in vals if x) for (c, s), vals in cities.items()},
        "venues": venues,
        "minimal": minimal,
        "count": len(minimal),
        "generated_at": int(time.time())
    }

# --- Index caching ---
def rebuild_index():
    records = _read_csv_rows(CSV_PATH)
    minimal = _rows_to_minimal(records)
    idx = _build_index(minimal)
    os.makedirs(os.path.dirname(INDEX_PATH), exist_ok=True)
    with open(INDEX_PATH, "w", encoding="utf-8") as f:
        json.dump(idx, f, ensure_ascii=False)
    return idx

def load_index():
    if not os.path.exists(INDEX_PATH):
        return rebuild_index()
    try:
        with open(INDEX_PATH, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return rebuild_index()

_index = None

@app.before_first_request
def warm():
    """Build or load the JSON index on first request."""
    global _index
    _index = load_index()

# --------------------------------------------------------------------
#                            ROUTES
# --------------------------------------------------------------------

@app.route("/")
def home():
    return render_template("finder.html")

@app.route("/api/health")
def health():
    return jsonify({
        "ok": True,
        "csv_exists": os.path.exists(CSV_PATH),
        "count": (_index or {}).get("count", 0),
        "index_path": INDEX_PATH
    })

@app.route("/api/breweries/reindex", methods=["POST"])
def reindex():
    """Rebuild the cache manually (if the CSV updates during runtime)."""
    global _index
    _index = rebuild_index()
    return jsonify({"ok": True, "count": _index["count"]})

@app.route("/api/breweries/countries")
def countries():
    return jsonify((_index or {}).get("countries", []))

@app.route("/api/breweries/states")
def states():
    c = _norm(request.args.get("country"))
    return jsonify((_index or {}).get("states", {}).get(c, []))

@app.route("/api/breweries/cities")
def cities():
    c = _norm(request.args.get("country"))
    s = _norm(request.args.get("state"))
    return jsonify((_index or {}).get("cities", {}).get(f"{c}||{s}", []))

@app.route("/api/breweries/venues")
def venues():
    c = _norm(request.args.get("country"))
    s = _norm(request.args.get("state"))
    ci = _norm(request.args.get("city"))
    return jsonify([v["name"] for v in (_index or {}).get("venues", {}).get((c,s,ci), [])])

@app.route("/api/breweries/venue-detail")
def venue_detail():
    c  = _norm(request.args.get("country"))
    s  = _norm(request.args.get("state"))
    ci = _norm(request.args.get("city"))
    res = (_index or {}).get("venues", {}).get((c,s,ci), [])
    return jsonify(res)

@app.route("/api/mapslink")
def mapslink():
    """Return a Google Maps directions URL for given lat/lng or location string."""
    lat = request.args.get("lat")
    lng = request.args.get("lng")
    if lat and lng:
        return jsonify({"url": f"https://www.google.com/maps/dir/?api=1&destination={lat},{lng}"})
    name = _norm(request.args.get("name"))
    city = _norm(request.args.get("city"))
    state_p = _norm(request.args.get("state_province"))
    country = _norm(request.args.get("country"))
    q = quote(", ".join([x for x in [name, city, state_p, country] if x]))
    return jsonify({"url": f"https://www.google.com/maps/dir/?api=1&destination={q}"})

if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=5000)
