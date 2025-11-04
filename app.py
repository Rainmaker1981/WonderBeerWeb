
import os, csv, json
from pathlib import Path
from flask import Flask, render_template, request, jsonify, send_from_directory
from werkzeug.utils import secure_filename

try:
    import pandas as pd
except Exception:
    pd = None

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "dev")

APP_ROOT = Path(__file__).parent.resolve()
DATA_DIR = APP_ROOT / "data"
PROFILES_DIR = DATA_DIR / "profiles"
PRIMARY_BREWERIES = DATA_DIR / "breweries.csv"
FALLBACK_BREWERIES = DATA_DIR / "breweries_sample.csv"

def get_breweries_path():
    return PRIMARY_BREWERIES if PRIMARY_BREWERIES.exists() else FALLBACK_BREWERIES

def load_breweries_rows():
    path = get_breweries_path()
    rows = []
    if not path.exists():
        return rows
    with open(path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for r in reader:
            row = {k.strip().lower(): (v.strip() if isinstance(v, str) else v) for k, v in r.items()}
            name = row.get("name") or row.get("brewery_name") or row.get("venue_name")
            city = row.get("city") or row.get("brewery_city") or row.get("venue_city")
            state = row.get("state_province") or row.get("state") or row.get("province") or row.get("region") or row.get("brewery_state") or row.get("venue_state")
            country = row.get("country") or row.get("brewery_country") or row.get("venue_country")
            url = row.get("url") or row.get("website") or row.get("brewery_url")
            if name and city and (state or country):
                rows.append({
                    "name": name, "city": city,
                    "state_province": state or "", "country": country or "", "url": url or ""
                })
    return rows

def list_profiles():
    items = []
    PROFILES_DIR.mkdir(parents=True, exist_ok=True)
    for p in PROFILES_DIR.glob("*.json"):
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
            display = data.get("name") or p.stem
        except Exception:
            display = p.stem
        items.append({"file": p.name, "display_name": display, "type": "json"})
    return sorted(items, key=lambda x: x["display_name"].lower())

@app.route("/")
def index():
    return render_template("index.html", profiles=list_profiles())

@app.route("/profiles")
def profiles_page():
    return render_template("profiles.html", profiles=list_profiles())

@app.route("/analytics")
def analytics():
    return render_template("analytics.html", profiles=list_profiles())

# --- Locations APIs ---
@app.get("/api/locations/countries")
def api_countries():
    rows = load_breweries_rows()
    countries = sorted({r["country"] or "United States" for r in rows if (r.get("country") or "").strip()})
    if "United States" in countries:
        countries.remove("United States")
        countries = ["United States"] + countries
    return jsonify(countries)

@app.get("/api/locations/states")
def api_states():
    country = request.args.get("country", "").strip()
    rows = load_breweries_rows()
    states = sorted({r["state_province"] for r in rows if (not country or r["country"] == country) and r["state_province"]})
    return jsonify(states)

@app.get("/api/locations/cities")
def api_cities():
    country = request.args.get("country", "").strip()
    state = request.args.get("state", "").strip()
    rows = load_breweries_rows()
    cities = sorted({r["city"] for r in rows if (not country or r["country"] == country) and (not state or r["state_province"] == state)})
    return jsonify(cities)

@app.get("/api/locations/venues")
def api_venues():
    country = request.args.get("country", "").strip()
    state = request.args.get("state", "").strip()
    city = request.args.get("city", "").strip()
    rows = load_breweries_rows()
    venues = [r for r in rows if (not country or r["country"] == country) and (not state or r["state_province"] == state) and (not city or r["city"] == city)]
    venues = sorted(venues, key=lambda v: v["name"].lower())
    return jsonify(venues)

# --- Profiles APIs ---
@app.get("/api/profiles")
def api_profiles():
    return jsonify(list_profiles())

@app.get("/api/profiles/<filename>")
def api_profile_detail(filename):
    path = PROFILES_DIR / filename
    if not path.exists() or path.suffix.lower() != ".json":
        return jsonify({"error": "Profile not found"}), 404
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    return jsonify(data)

@app.post("/api/profiles/upload")
def api_profile_upload():
    if "file" not in request.files:
        return jsonify({"error": "No file uploaded"}), 400
    file = request.files["file"]
    display_name = request.form.get("display_name", "").strip() or "Unnamed"
    safe_basename = secure_filename(display_name.replace(" ", "_"))
    out_json = PROFILES_DIR / f"{safe_basename}.json"
    PROFILES_DIR.mkdir(parents=True, exist_ok=True)

    if pd is None:
        return jsonify({"error": "Pandas not available"}), 500
    try:
        df = pd.read_csv(file, sep=",", engine="python")
    except Exception as e:
        return jsonify({"error": f"CSV parse failed: {e}"}), 400

    def col(name):
        return df[name] if name in df.columns else None

    # styles
    styles = {}
    if col("beer_type") is not None:
        styles = (df["beer_type"].dropna().astype(str).str.strip().value_counts().head(5)).to_dict()

    # flavors
    flavors = {}
    if col("flavor_profiles") is not None:
        for s in df["flavor_profiles"].dropna().astype(str):
            for tok in [t.strip() for t in s.split(",") if t.strip()]:
                flavors[tok] = flavors.get(tok, 0) + 1
        flavors = dict(sorted(flavors.items(), key=lambda kv: kv[1], reverse=True)[:5])

    # helpers
    def to_float(x):
        try: return float(x)
        except: return None

    abv_points, ibu_points = [], []
    for _, r in df.iterrows():
        abv = to_float(r.get("beer_abv"))
        ibu = to_float(r.get("beer_ibu"))
        rating = to_float(r.get("rating_score"))
        entry = {"beer": str(r.get("beer_name") or "")[:80], "style": str(r.get("beer_type") or ""), "rating": rating}
        if abv is not None: abv_points.append({**entry, "abv": abv})
        if ibu is not None: ibu_points.append({**entry, "ibu": ibu})

    # breweries top 5
    for colname in ["brewery_name", "brewery_city", "brewery_state", "brewery_url"]:
        if colname not in df.columns:
            df[colname] = None
    g = (df.groupby(["brewery_name","brewery_city","brewery_state","brewery_url"], dropna=False)
           .size().reset_index(name="count").sort_values("count", ascending=False).head(5))
    breweries_top = []
    for _, r in g.iterrows():
        breweries_top.append({
            "name": r["brewery_name"] or "",
            "city": r["brewery_city"] or "",
            "state": r["brewery_state"] or "",
            "count": int(r["count"]),
            "url": r["brewery_url"] or ""
        })

    import numpy as np
    rating_mean = float(np.nanmean(pd.to_numeric(df.get("rating_score", []), errors="coerce"))) if "rating_score" in df else None
    global_mean = float(np.nanmean(pd.to_numeric(df.get("global_rating_score", []), errors="coerce"))) if "global_rating_score" in df else None

    result = {
        "name": display_name,
        "styles": styles,
        "flavors": flavors,
        "abv": abv_points,
        "ibu": ibu_points,
        "breweries": breweries_top,
        "ratings": {
            "mean_rating": round(rating_mean,3) if rating_mean==rating_mean else None,
            "mean_global": round(global_mean,3) if global_mean==global_mean else None,
            "n": int(len(df))
        }
    }
    out_json.write_text(json.dumps(result, indent=2), encoding="utf-8")
    return jsonify({"ok": True, "file": out_json.name, "profile": result})

@app.route("/static/<path:filename>")
def static_files(filename):
    return send_from_directory((Path(__file__).parent / "static"), filename)

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)), debug=True)
