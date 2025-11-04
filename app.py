import os, io, csv, json, math, re
from collections import Counter, defaultdict
from urllib.parse import urlparse
import requests
from bs4 import BeautifulSoup
import pandas as pd
from flask import Flask, render_template, request, jsonify

APP_ROOT = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(APP_ROOT, "data")
PROFILES_DIR = os.path.join(DATA_DIR, "profiles")

app = Flask(__name__)

# ------------- helpers -------------
def breweries_path():
    return os.path.join(DATA_DIR, "breweries.csv")

def beer_cache_path():
    return os.path.join(DATA_DIR, "beer_cache.json")

def list_profiles():
    mapping_path = os.path.join(PROFILES_DIR, "profiles.json")
    mapping = {}
    if os.path.exists(mapping_path):
        with open(mapping_path, encoding="utf-8") as f:
            mapping = json.load(f)
    # Include actual jsons found as well
    for fn in os.listdir(PROFILES_DIR):
        if fn.endswith(".json"):
            mapping.setdefault(fn, os.path.splitext(fn)[0].replace("_"," "))
    return mapping

def save_profile_mapping(filename, display_name):
    mapping_path = os.path.join(PROFILES_DIR, "profiles.json")
    mapping = {}
    if os.path.exists(mapping_path):
        with open(mapping_path, encoding="utf-8") as f:
            mapping = json.load(f)
    mapping[filename] = display_name
    with open(mapping_path, "w", encoding="utf-8") as f:
        json.dump(mapping, f, indent=2)

def parse_untappd_csv(file_bytes):
    text = file_bytes.decode("utf-8", errors="ignore")
    # Sniff delimiter (commas typical for Untappd export)
    sniffer = csv.Sniffer()
    dialect = sniffer.sniff(text.splitlines()[0] + "\n" + text.splitlines()[1])
    reader = csv.DictReader(io.StringIO(text), dialect=dialect)
    rows = list(reader)
    # Normalize headers
    def norm(s): return s.strip().lower().replace(' ', '_')
    rows_norm = [{norm(k):v for k,v in r.items()} for r in rows]
    return rows_norm

def build_profile_summary(rows):
    # Expected keys (normalized): beer_name, brewery_name, beer_type, beer_abv, beer_ibu, rating_score, global_rating_score
    styles = Counter()
    abvs, ibus, ratings, globals_ = [], [], [], []
    points_abv_ibu = []
    for r in rows:
        bt = r.get("beer_type") or r.get("style") or ""
        if bt:
            styles[bt] += 1
        # numeric fields
        def to_float(x):
            try: 
                if x is None or x == "": 
                    return None
                return float(str(x).strip())
            except: 
                return None
        abv = to_float(r.get("beer_abv"))
        ibu = to_float(r.get("beer_ibu"))
        rate = to_float(r.get("rating_score"))
        gr = to_float(r.get("global_rating_score") or r.get("global_weighted_rating_score"))
        if abv is not None: abvs.append(abv)
        if ibu is not None: ibus.append(ibu)
        if rate is not None: ratings.append(rate)
        if gr is not None: globals_.append(gr)
        if abv is not None and ibu is not None:
            points_abv_ibu.append({"x":abv,"y":ibu})
    summary = {
        "styles": dict(styles),
        "abv_mean": sum(abvs)/len(abvs) if abvs else 0.0,
        "ibu_mean": sum(ibus)/len(ibus) if ibus else 0.0,
        "rating_mean": sum(ratings)/len(ratings) if ratings else 0.0,
        "global_rating_mean": sum(globals_)/len(globals_) if globals_ else 0.0,
        "points_abv_ibu": points_abv_ibu,
        "top_styles": sorted(styles.items(), key=lambda kv: kv[1], reverse=True)[:5],
    }
    return summary

def write_profile_json(display_name, rows):
    safe = re.sub(r"\W+", "_", display_name).strip("_")
    filename = f"{safe}.json"
    path = os.path.join(PROFILES_DIR, filename)
    summary = build_profile_summary(rows)
    payload = {"name": display_name, **summary}
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2)
    save_profile_mapping(filename, display_name)
    return filename, payload

def load_breweries_df():
    path = breweries_path()
    df = pd.read_csv(path)
    for col in ["country","state_province","city","name","untappd_venue_url"]:
        if col not in df.columns:
            df[col] = ""
    return df

def compute_match(beer, prof):
    # simple distance from profile means for ABV/IBU, plus style presence bonus
    abv, ibu, style = beer.get("abv"), beer.get("ibu"), (beer.get("style") or "").strip()
    abv_m = prof.get("abv_mean") or 0.0
    ibu_m = prof.get("ibu_mean") or 0.0
    # normalize distances
    d_abv = abs((abv or abv_m) - abv_m) / 10.0  # 10% abv window
    d_ibu = abs((ibu or ibu_m) - ibu_m) / 60.0  # 60 ibu window
    dist = (d_abv + d_ibu)/2.0
    base = max(0.0, 1.0 - dist)
    style_bonus = 0.1 if style in (prof.get("styles") or {}) else 0.0
    return min(1.0, base + style_bonus)

def try_fetch_untappd_menu(url):
    if not url: 
        return None
    try:
        resp = requests.get(url, timeout=10, headers={"User-Agent":"Mozilla/5.0"})
        if resp.status_code != 200:
            return None
        soup = BeautifulSoup(resp.text, "lxml")
        # Heuristic parsing: look for menu items
        beers = []
        for li in soup.select("li.menu-item, div.beer-item, div.menu-item"):
            name = (li.select_one(".name,.beer-name,h3,h4") or li).get_text(" ", strip=True)
            style = (li.select_one(".style,.beer-style,.beer-style-name") or None)
            style = style.get_text(" ", strip=True) if style else None
            abv = None; ibu = None
            # ABV/IBU tokens
            text = li.get_text(" ", strip=True)
            m = re.search(r"(\d+(?:\.\d+)?)\s*%\s*ABV", text, re.I)
            if m: abv = float(m.group(1))
            m = re.search(r"(\d+)\s*IBU", text, re.I)
            if m: ibu = float(m.group(1))
            beers.append({"name": name, "style": style, "abv": abv, "ibu": ibu})
        return beers if beers else None
    except Exception:
        return None

def load_fallback_menu(venue_name):
    # simple mapping for demo
    if "Thunderhead" in (venue_name or ""):
        path = os.path.join(DATA_DIR, "menus", "thunderhead_sample.json")
        with open(path, encoding="utf-8") as f:
            d = json.load(f)
        return d.get("beers", [])
    return []

# ------------- routes -------------
@app.route("/")
def home():
    return render_template("home.html")

@app.route("/profile", methods=["GET","POST"])
def profile():
    if request.method == "POST":
        name = request.form.get("name","").strip()
        file = request.files.get("csvfile")
        if not name or not file:
            return render_template("profile.html", summary=None)
        data = file.read()
        try:
            rows = parse_untappd_csv(data)
        except Exception as e:
            # fallback to comma dialect
            text = data.decode("utf-8", errors="ignore")
            reader = csv.DictReader(io.StringIO(text))
            rows = list(reader)
            rows = [{k.strip().lower().replace(' ','_'):v for k,v in r.items()} for r in rows]
        filename, payload = write_profile_json(name, rows)
        payload["filename"] = filename
        return render_template("profile.html", summary=payload)
    return render_template("profile.html", summary=None)

@app.route("/finder")
def finder():
    profiles = list_profiles().items()
    return render_template("finder.html", profiles=profiles)

@app.get("/api/countries")
def api_countries():
    df = load_breweries_df()
    countries = sorted([c for c in df["country"].dropna().unique().tolist() if str(c).strip()])
    return jsonify(countries)

@app.get("/api/states")
def api_states():
    country = request.args.get("country","")
    df = load_breweries_df()
    subset = df[df["country"]==country] if country else df
    states = sorted([s for s in subset["state_province"].dropna().unique().tolist() if str(s).strip()])
    return jsonify(states)

@app.get("/api/cities")
def api_cities():
    country = request.args.get("country","")
    state = request.args.get("state","")
    df = load_breweries_df()
    if country:
        df = df[df["country"]==country]
    if state:
        df = df[df["state_province"]==state]
    cities = sorted([c for c in df["city"].dropna().unique().tolist() if str(c).strip()])
    return jsonify(cities)

@app.get("/api/venues")
def api_venues():
    country = request.args.get("country","")
    state = request.args.get("state","")
    city = request.args.get("city","")
    df = load_breweries_df()
    if country:
        df = df[df["country"]==country]
    if state:
        df = df[df["state_province"]==state]
    if city:
        df = df[df["city"]==city]
    venues = df[["name","city","state_province","untappd_venue_url"]].to_dict(orient="records")
    return jsonify(venues)

@app.route("/match")
def match():
    venue = request.args.get("venue","")
    profile_json = request.args.get("profile_json","")
    profile_obj = None
    if profile_json:
        ppath = os.path.join(PROFILES_DIR, profile_json)
        if os.path.exists(ppath):
            with open(ppath, encoding="utf-8") as f:
                profile_obj = json.load(f)
    # find URL for venue
    df = load_breweries_df()
    row = None
    if venue:
        sub = df[df["name"]==venue]
        if not sub.empty:
            row = sub.iloc[0].to_dict()
    url = (row or {}).get("untappd_venue_url")
    beers = try_fetch_untappd_menu(url) or load_fallback_menu(venue)
    # compute matches
    if profile_obj:
        for b in beers:
            b["match"] = compute_match(b, profile_obj)
    else:
        for b in beers:
            b["match"] = 0.0
    return render_template("match.html", venue_name=venue, profile_name=(profile_obj or {}).get("name"), beers=beers)

@app.route("/lookup")
def lookup():
    q = request.args.get("q","").strip()
    result = None
    result_name = q
    if q:
        with open(beer_cache_path(), encoding="utf-8") as f:
            cache = json.load(f)
        # try exact, then case-insensitive
        if q in cache:
            result = cache[q]
            result_name = q
        else:
            # ci scan
            for k,v in cache.items():
                if k.lower() == q.lower():
                    result = v
                    result_name = k
                    break
    return render_template("lookup.html", result=result, result_name=result_name)
    
if __name__ == "__main__":
    app.run(debug=True)
