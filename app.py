import os, json, csv
from pathlib import Path
from flask import Flask, request, render_template, redirect, url_for, jsonify, flash

from utils import build_breweries_cache, parse_untappd_csv, compute_match_score

APP_ROOT = Path(__file__).parent.resolve()
DATA_DIR = APP_ROOT / "data"
PROFILES_DIR = DATA_DIR / "profiles"
BREWERIES_CSV = DATA_DIR / "breweries.csv"
BREWERIES_CACHE = DATA_DIR / "breweries_cache.json"
BEER_CACHE_JSON = DATA_DIR / "beer_cache.json"

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "dev-secret")

def ensure_breweries_cache():
    if not BREWERIES_CSV.exists():
        return False
    if (not BREWERIES_CACHE.exists()) or (BREWERIES_CSV.stat().st_mtime > BREWERIES_CACHE.stat().st_mtime):
        rows=[]
        with open(BREWERIES_CSV, newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for r in reader:
                rows.append({
                    "name": r.get("name"),
                    "city": r.get("city"),
                    "state_province": r.get("state_province"),
                    "country": r.get("country"),
                    "website_url": r.get("website_url"),
                    "longitude": r.get("longitude"),
                    "latitude": r.get("latitude"),
                })
        tree = build_breweries_cache(rows)
        BREWERIES_CACHE.write_text(json.dumps(tree, ensure_ascii=False, indent=2), encoding="utf-8")
    return True

def load_breweries_cache():
    if ensure_breweries_cache() and BREWERIES_CACHE.exists():
        return json.loads(BREWERIES_CACHE.read_text(encoding="utf-8"))
    return {}

def load_beer_cache():
    if BEER_CACHE_JSON.exists():
        try: return json.loads(BEER_CACHE_JSON.read_text(encoding="utf-8"))
        except: return {}
    return {}

@app.get("/")
def index():
    return render_template("index.html")

@app.get("/profile")
def profile_page():
    PROFILES_DIR.mkdir(parents=True, exist_ok=True)
    profiles=[]
    for p in PROFILES_DIR.glob("*.json"):
        try:
            data=json.loads(p.read_text(encoding="utf-8"))
            profiles.append({"file": p.name, "name": data.get("name")})
        except: pass
    return render_template("profile.html", profiles=profiles)

@app.post("/profile/upload")
def profile_upload():
    file = request.files.get("csv_file")
    display_name = request.form.get("display_name","").strip() or "Unnamed"
    if not file or file.filename=="":
        flash("Please choose a CSV file to upload.")
        return redirect(url_for("profile_page"))
    profile = parse_untappd_csv(file.stream, display_name)
    PROFILES_DIR.mkdir(parents=True, exist_ok=True)
    out_path = PROFILES_DIR / f"{display_name.replace(' ','_')}.json"
    out_path.write_text(json.dumps(profile, ensure_ascii=False, indent=2), encoding="utf-8")
    flash(f"Profile saved: {out_path.name}")
    return redirect(url_for("profile_page"))

@app.get("/breweries")
def breweries_page():
    return render_template("breweries.html")

@app.get("/api/breweries")
def api_breweries():
    return jsonify(load_breweries_cache())

@app.get("/match")
def match_page():
    country = request.args.get("country","")
    state = request.args.get("state","")
    city = request.args.get("city","")
    venue = request.args.get("venue","")
    profile_file = request.args.get("profile","")
    return render_template("match.html", country=country, state=state, city=city, venue=venue, profile_file=profile_file)

@app.post("/match/run")
def match_run():
    payload = request.get_json(force=True)
    country = payload.get("country","")
    state = payload.get("state","")
    city = payload.get("city","")
    venue = payload.get("venue","")
    profile_file = payload.get("profile_file","")

    profile={}
    if profile_file:
        p = PROFILES_DIR / profile_file
        if p.exists():
            try: profile = json.loads(p.read_text(encoding="utf-8"))
            except: profile = {}

    from untappd_scraper import fetch_venue_menu
    menu = fetch_venue_menu(venue, city, state, country)

    beer_cache = load_beer_cache()

    for b in menu:
        b["match_score"] = compute_match_score(profile, b, beer_cache_lookup=beer_cache)

    menu.sort(key=lambda x: x.get("match_score", 0), reverse=True)
    return jsonify({"results": menu, "profile": profile})

@app.get("/lookup")
def lookup_page():
    return render_template("lookup.html")

@app.get("/api/beer_cache")
def api_beer_cache():
    return jsonify(load_beer_cache())

@app.get("/map")
def map_redirect():
    lat = request.args.get("lat"); lon = request.args.get("lon"); q = request.args.get("q","Brewery")
    if lat and lon:
        from flask import redirect
        return redirect(f"https://www.google.com/maps/search/?api=1&query={lat}%2C{lon}")
    from flask import redirect
    return redirect(f"https://www.google.com/maps/search/{q}")

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT","5000")), debug=True)
