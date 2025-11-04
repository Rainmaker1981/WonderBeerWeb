import os
import io
import json
from collections import Counter, defaultdict

from flask import Flask, jsonify, request, render_template, send_from_directory
import pandas as pd

APP_ROOT = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(APP_ROOT, "data")
PROFILES_DIR = os.path.join(DATA_DIR, "profiles")
BREWERIES_CSV = os.path.join(DATA_DIR, "breweries.csv")

app = Flask(__name__)

def autodetect_sep_and_read(file_storage):
    sample = file_storage.stream.read(2048).decode(errors="ignore")
    file_storage.stream.seek(0)
    sep = ";" if sample.count(";") > sample.count(",") else ","
    return pd.read_csv(file_storage, sep=sep, engine="python")

def safe_float(x):
    try:
        return float(x)
    except Exception:
        return None

def top_n_counts(series, n=5):
    c = Counter([s for s in series if pd.notna(s) and str(s).strip() != ""])
    return dict(c.most_common(n))

def ensure_dirs():
    os.makedirs(DATA_DIR, exist_ok=True)
    os.makedirs(PROFILES_DIR, exist_ok=True)

def load_breweries_df():
    if not os.path.exists(BREWERIES_CSV):
        return pd.DataFrame(columns=["Name","City","State_province","Country"])
    try:
        df = pd.read_csv(BREWERIES_CSV)
        cols = {c.lower(): c for c in df.columns}
        def pick(*names):
            for n in names:
                if n in cols:
                    return cols[n]
            return None

        name_col = pick("name")
        city_col = pick("city")
        state_col = pick("state_province","state","province","state/Province","state_prov".lower())
        country_col = pick("country")
        if not all([name_col, city_col, state_col, country_col]):
            df.rename(columns={name_col or "": "Name",
                               city_col or "": "City",
                               state_col or "": "State_province",
                               country_col or "": "Country"}, inplace=True)
        else:
            df = df.rename(columns={name_col: "Name",
                                    city_col: "City",
                                    state_col: "State_province",
                                    country_col: "Country"})
        df = df.dropna(subset=["Name","City","State_province","Country"])
        for c in ["Name","City","State_province","Country"]:
            df[c] = df[c].astype(str).str.strip()
        return df
    except Exception:
        return pd.DataFrame(columns=["Name","City","State_province","Country"])

@app.route("/")
def home():
    return render_template("index.html")

@app.get("/api/health")
def health():
    return jsonify({"ok": True})

@app.get("/api/locations/countries")
def get_countries():
    df = load_breweries_df()
    countries = sorted(df["Country"].dropna().unique().tolist())
    if "United States" in countries:
        countries.remove("United States")
        countries = ["United States"] + countries
    return jsonify({"countries": countries})

@app.get("/api/locations/states")
def get_states():
    country = request.args.get("country", "United States")
    df = load_breweries_df()
    if not df.empty:
        df2 = df[df["Country"].str.lower() == country.lower()]
        states = sorted(df2["State_province"].dropna().unique().tolist())
    else:
        states = []
    return jsonify({"states": states})

@app.get("/api/locations/cities")
def get_cities():
    country = request.args.get("country", "United States")
    state = request.args.get("state", "")
    df = load_breweries_df()
    if not df.empty:
        sel = (df["Country"].str.lower()==country.lower())
        if state:
            sel &= (df["State_province"].str.lower()==state.lower())
        df2 = df[sel]
        cities = sorted(df2["City"].dropna().unique().tolist())
    else:
        cities = []
    return jsonify({"cities": cities})

@app.get("/api/locations/breweries")
def get_breweries():
    country = request.args.get("country", "United States")
    state = request.args.get("state", "")
    city = request.args.get("city", "")
    df = load_breweries_df()
    breweries = []
    if not df.empty:
        sel = (df["Country"].str.lower()==country.lower())
        if state:
            sel &= (df["State_province"].str.lower()==state.lower())
        if city:
            sel &= (df["City"].str.lower()==city.lower())
        df2 = df[sel]
        breweries = sorted(df2["Name"].dropna().unique().tolist())
    return jsonify({"breweries": breweries})

@app.post("/api/profiles/upload")
def upload_untappd():
    ensure_dirs()
    file = request.files.get("file")
    display_name = request.form.get("display_name","").strip() or "Unnamed"
    if not file:
        return jsonify({"error":"No file uploaded"}), 400

    try:
        df = autodetect_sep_and_read(file)
    except Exception as e:
        return jsonify({"error": f"CSV parse failed: {e}"}), 400

    lower_map = {c.lower(): c for c in df.columns}
    def col(*cands):
        for c in cands:
            if c in lower_map:
                return lower_map[c]
        return None

    c_beer_type   = col("beer_type")
    c_brewery     = col("brewery_name")
    c_brew_city   = col("brewery_city")
    c_brew_state  = col("brewery_state","brewery_province","brewery_region")
    c_brew_url    = col("brewery_url")
    c_abv         = col("beer_abv")
    c_ibu         = col("beer_ibu")
    c_rating      = col("rating_score")
    c_global      = col("global_rating_score","global_weighted_rating_score")
    c_flavors     = col("flavor_profiles")

    styles_top5 = top_n_counts(df[c_beer_type]) if c_beer_type else {}

    from collections import Counter
    breweries_counts = Counter()
    brewery_meta = {}
    if c_brewery:
        for _, row in df.iterrows():
            bname = row.get(c_brewery)
            if pd.isna(bname) or str(bname).strip()=="":
                continue
            bname = str(bname).strip()
            breweries_counts[bname] += 1
            if bname not in brewery_meta:
                brewery_meta[bname] = {
                    "name": bname,
                    "city": str(row.get(c_brew_city, "") or ""),
                    "state": str(row.get(c_brew_state, "") or ""),
                    "url": str(row.get(c_brew_url, "") or ""),
                }
    top5_breweries = []
    for name, cnt in breweries_counts.most_common(5):
        meta = brewery_meta.get(name, {"name": name, "city":"", "state":"", "url":""})
        meta["count"] = cnt
        top5_breweries.append(meta)

    abv_values = [v for v in (safe_float(x) for x in (df[c_abv] if c_abv else [])) if v is not None]
    ibu_values = [v for v in (safe_float(x) for x in (df[c_ibu] if c_ibu else [])) if v is not None]

    rating_values = [v for v in (safe_float(x) for x in (df[c_rating] if c_rating else [])) if v is not None]
    global_values = [v for v in (safe_float(x) for x in (df[c_global] if c_global else [])) if v is not None]
    avg_user = round(sum(rating_values)/len(rating_values), 3) if rating_values else None
    avg_global = round(sum(global_values)/len(global_values), 3) if global_values else None

    deltas = []
    if c_rating and c_global:
        for _, row in df.iterrows():
            u = safe_float(row.get(c_rating))
            g = safe_float(row.get(c_global))
            if u is not None and g is not None:
                deltas.append(u - g)
    avg_delta = round(sum(deltas)/len(deltas), 3) if deltas else None

    from collections import Counter
    flavor_counts = Counter()
    if c_flavors:
        for s in df[c_flavors].dropna():
            for token in str(s).split(","):
                t = token.strip()
                if t:
                    flavor_counts[t] += 1
    top5_flavors = dict(flavor_counts.most_common(5))

    result = {
        "name": display_name,
        "styles": styles_top5,
        "breweries": top5_breweries,
        "abv_values": abv_values,
        "ibu_values": ibu_values,
        "ratings": {
            "avg_user": avg_user,
            "avg_global": avg_global,
            "avg_delta": avg_delta
        },
        "flavors": top5_flavors
    }

    safe_filename = "".join([c if c.isalnum() or c in ("-", "_") else "_" for c in display_name]) + ".json"
    out_path = os.path.join(PROFILES_DIR, safe_filename)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    return jsonify(result)

@app.route('/static/<path:filename>')
def static_files(filename):
    return send_from_directory(os.path.join(APP_ROOT, 'static'), filename)

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
