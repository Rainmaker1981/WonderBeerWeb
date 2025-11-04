import csv, json, os, threading
from pathlib import Path
from flask import Flask, jsonify, request, render_template, redirect, url_for, abort
from utils import parse_untappd_csv, compute_match_score
from untappd_scraper import fetch_untappd_menu

app = Flask(__name__)

DATA_DIR = Path(os.environ.get("DATA_DIR", "data"))
CSV_PATH = DATA_DIR / "breweries.csv"
INDEX_PATH = Path(os.environ.get("BREWERIES_INDEX_PATH", "/tmp/breweries_index.json"))
PROFILES_DIR = DATA_DIR / "profiles"

_init_lock = threading.Lock()
_initialized = False
_index_mem = {}

def build_breweries_index(csv_path: Path, out_path: Path) -> dict:
    wanted = {"name","city","state_province","country","website_url","longitude","latitude"}
    venues = []
    countries = {}
    if not csv_path.exists():
        index = {"venues": [], "index": {}}
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps(index), encoding="utf-8")
        return index

    with csv_path.open(newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            rec = {k: (row.get(k) or "").strip() for k in wanted}
            for coord in ("longitude","latitude"):
                v = rec.get(coord, "")
                try:
                    rec[coord] = float(v) if v not in ("", None) else None
                except ValueError:
                    rec[coord] = None
            venues.append(rec)
            country = rec["country"] or "Unknown"
            state = rec["state_province"] or "Unknown"
            city = rec["city"] or "Unknown"
            name = rec["name"] or "Unknown"
            countries.setdefault(country, {}).setdefault(state, {}).setdefault(city, []).append(name)
    index = {"venues": venues, "index": countries}
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(index, ensure_ascii=False), encoding="utf-8")
    return index

def _load_or_build_index():
    if INDEX_PATH.exists():
        return json.loads(INDEX_PATH.read_text(encoding="utf-8"))
    return build_breweries_index(CSV_PATH, INDEX_PATH)

def init_once():
    global _initialized, _index_mem
    if _initialized: return
    with _init_lock:
        if _initialized: return
        PROFILES_DIR.mkdir(parents=True, exist_ok=True)
        _index_mem = _load_or_build_index()
        _initialized = True

@app.before_request
def _ensure():
    init_once()

@app.get("/")
def landing():
    return render_template("home.html")

@app.get("/profile")
def profile():
    return render_template("profile.html")

# app.py (inside the POST handler for profile upload)
from utils import build_profile_from_untappd, save_profile_json
import os

@app.post("/profile/upload")
def profile_upload():
    from utils import parse_untappd_csv
    display_name = request.form.get("display_name", "").strip() or "Profile"
    file = request.files.get("file")
    if not file:
        return ("No CSV file uploaded.", 400)
    try:
        # the parser now reads bytes safely
        profile = parse_untappd_csv(file, display_name)
    except Exception as e:
        return (f"CSV parse error: {e}", 400)

    safe_name = display_name.replace(" ", "_")
    out_path = PROFILES_DIR / f"{safe_name}.json"
    out_path.write_text(json.dumps(profile, ensure_ascii=False, indent=2), encoding="utf-8")
    return redirect(url_for("profile_view", name=safe_name))


@app.get("/profile/<name>")
def profile_view(name):
    p = PROFILES_DIR / f"{name}.json"
    if not p.exists():
        abort(404)
    return render_template("profile_view.html", profile_json=p.read_text(encoding="utf-8"))

@app.get("/breweries")
def breweries():
    return render_template("breweries.html")

@app.get("/api/countries")
def api_countries():
    return jsonify(sorted(list(_index_mem.get("index", {}).keys())))

@app.get("/api/states")
def api_states():
    country = request.args.get("country","")
    return jsonify(sorted(list(_index_mem.get("index",{}).get(country,{ }).keys())))

@app.get("/api/cities")
def api_cities():
    country = request.args.get("country","")
    state = request.args.get("state_province","")
    return jsonify(sorted(list(_index_mem.get("index",{}).get(country,{}).get(state,{}).keys())))

@app.get("/api/venues")
def api_venues():
    country = request.args.get("country","")
    state = request.args.get("state_province","")
    city = request.args.get("city","")
    venues = _index_mem.get("index",{}).get(country,{}).get(state,{}).get(city,[])
    return jsonify(sorted(venues))

@app.get("/api/venue_detail")
def api_venue_detail():
    country = request.args.get("country","")
    state = request.args.get("state_province","")
    city = request.args.get("city","")
    name = request.args.get("name","")
    for v in _index_mem.get("venues", []):
        if v.get("country")==country and v.get("state_province")==state and v.get("city")==city and v.get("name")==name:
            return jsonify(v)
    return jsonify({"error":"not found"}), 404

@app.get("/match")
def match_page():
    return render_template("match.html")

@app.post("/match/run")
def match_run():
    profile_slug = request.form.get("profile_slug","").strip()
    venue_url = request.form.get("venue_url","").strip()
    if not profile_slug or not venue_url:
        return abort(400, "profile and venue_url are required.")
    p = PROFILES_DIR / f"{profile_slug}.json"
    if not p.exists():
        return abort(400, "Profile JSON not found.")
    profile = json.loads(p.read_text(encoding="utf-8"))
    menu = fetch_untappd_menu(venue_url)
    results = []
    for beer in menu:
        score = compute_match_score(profile, beer)
        out = beer.copy()
        out["match"] = score
        results.append(out)
    results.sort(key=lambda x: x.get("match",0.0), reverse=True)
    return render_template("match_results.html", profile_name=profile.get("name","Profile"), venue_url=venue_url, results=results)

@app.get("/lookup")
def lookup_page():
    return render_template("lookup.html")

@app.get("/api/health")
def api_health():
    return jsonify({
        "ok": True,
        "initialized": _initialized,
        "csv_exists": CSV_PATH.exists(),
        "venues_count": len(_index_mem.get("venues",[])),
        "profiles": sorted([p.name for p in PROFILES_DIR.glob("*.json")])
    })

if __name__ == "__main__":
    init_once()
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", "5000")))
