from flask import Flask, render_template, request, redirect, url_for, flash, send_from_directory, jsonify
import os, math, requests, json
import pandas as pd

# ------------------------------
# Core setup
# ------------------------------
APP_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(APP_DIR, "data")
UPLOAD_DIR = os.path.join(APP_DIR, "uploads")

BREWERIES_CSV = os.path.join(DATA_DIR, "breweries.csv")
MENU_CSV = os.path.join(DATA_DIR, "sample_menu.csv")
PROFILE_CSV = os.path.join(UPLOAD_DIR, "profile.csv")
SAMPLE_PROFILE_CSV = os.path.join(DATA_DIR, "sample_profile.csv")

app = Flask(__name__)
app.secret_key = "wonderbeer-demo"

# ------------------------------
# Helpers
# ------------------------------
def _norm(s):
    return (s or "").strip().lower()

def _fuzzy_bonus(target, query):
    t, q = _norm(target), _norm(query)
    if not q or not t:
        return 0.0
    if t == q:
        return 100.0
    if t.startswith(q):
        return 50.0
    if q in t:
        return 15.0
    try:
        from difflib import SequenceMatcher
        return SequenceMatcher(None, t, q).ratio() * 10.0
    except Exception:
        return 0.0

def read_csv_safe(path):
    if not os.path.exists(path):
        return pd.DataFrame()
    try:
        return pd.read_csv(path)
    except Exception:
        return pd.DataFrame()

# ------------------------------
# Data normalization
# ------------------------------
def normalize_breweries_df(df: pd.DataFrame) -> pd.DataFrame:
    """Ensure breweries dataframe has consistent columns."""
    if df is None or df.empty:
        return pd.DataFrame(columns=["brewery_id", "name", "brewery_type", "city", "state"])

    df = df.copy()
    rename = {
        "id": "brewery_id",
        "brewerytype": "brewery_type",
        "brewery_type": "brewery_type",
        "state_province": "state",
        "state": "state",
        "name": "name",
        "city": "city"
    }
    for src, dst in rename.items():
        if src in df.columns and dst not in df.columns:
            df.rename(columns={src: dst}, inplace=True)

    for col in ["brewery_id", "name", "brewery_type", "city", "state"]:
        if col not in df.columns:
            df[col] = ""
        df[col] = df[col].astype(str).fillna("")

    return df

# ------------------------------
# Data loaders
# ------------------------------
def load_breweries_df():
    """Load OpenBreweryDB CSV, cached API, or fallback."""
    cache_path = os.path.join(DATA_DIR, "breweries_cache.csv")

    # 1. local
    if os.path.exists(BREWERIES_CSV):
        try:
            df = pd.read_csv(BREWERIES_CSV)
            if not df.empty:
                return normalize_breweries_df(df)
        except Exception:
            pass

    # 2. cache
    if os.path.exists(cache_path):
        try:
            df = pd.read_csv(cache_path)
            if not df.empty:
                return normalize_breweries_df(df)
        except Exception:
            pass

    # 3. API
    try:
        resp = requests.get("https://api.openbrewerydb.org/breweries?per_page=200", timeout=15)
        resp.raise_for_status()
        data = resp.json()
        df = pd.json_normalize(data)
        rename = {
            "id": "brewery_id", "name": "name", "brewery_type": "brewery_type",
            "city": "city", "state": "state", "country": "country"
        }
        for k, v in rename.items():
            if k in df.columns:
                df.rename(columns={k: v}, inplace=True)
        df.to_csv(cache_path, index=False)
        return normalize_breweries_df(df)
    except Exception:
        pass

    return normalize_breweries_df(read_csv_safe(BREWERIES_CSV))

def load_menu_df():
    """Load beer list from JSON cache or fallback CSV."""
    path = os.path.join(DATA_DIR, "beer_cache.json")
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                raw = json.load(f)
            items = raw.get("beers", raw) if isinstance(raw, dict) else raw
            mdf = pd.json_normalize(items)

            rename = {
                "beer_name": "name", "beer_type": "style", "beer_style": "style",
                "beer_abv": "abv", "beer_ibu": "ibu",
                "rating_score": "global_rating", "brewery.brewery_id": "brewery_id"
            }
            for k, v in rename.items():
                if k in mdf.columns and v not in mdf.columns:
                    mdf.rename(columns={k: v}, inplace=True)

            # Always ensure columns exist
            for col in ["name", "style", "brewery_name", "abv", "ibu", "global_rating", "brewery_id"]:
                if col not in mdf.columns:
                    mdf[col] = ""

            for c in ["abv", "ibu", "global_rating"]:
                mdf[c] = pd.to_numeric(mdf[c], errors="coerce")

            return mdf
        except Exception:
            return pd.DataFrame()

    mdf = read_csv_safe(MENU_CSV)
    if "style" not in mdf.columns:
        mdf["style"] = ""
    if "name" not in mdf.columns:
        mdf["name"] = ""
    return mdf

def load_profile():
    return read_csv_safe(PROFILE_CSV)

# ------------------------------
# Debug routes
# ------------------------------
@app.get("/debug/tree")
def debug_tree():
    out = {}
    for root in [APP_DIR, DATA_DIR]:
        if os.path.isdir(root):
            out[root] = [{
                "name": name,
                "is_dir": os.path.isdir(os.path.join(root, name)),
                "size": os.path.getsize(os.path.join(root, name
