from flask import Flask, render_template, request, redirect, url_for, flash, send_from_directory, jsonify
import os, math, requests, json, pandas as pd

# ------------------------------
# Core paths and setup
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
# Utility helpers
# ------------------------------

def normalize_breweries_df(df: pd.DataFrame) -> pd.DataFrame:
    """Standardize brewery DataFrame columns for consistency."""
    if df is None or df.empty:
        return pd.DataFrame(columns=["brewery_id", "name", "brewery_type", "city", "state"])
    df = df.copy()

    rename = {
        "id": "brewery_id",
        "brewerytype": "brewery_type",
        "brewery_type": "brewery_type",
        "city": "city",
        "state_province": "state",
        "state": "state",
        "name": "name",
    }
    for src, dst in rename.items():
        if src in df.columns and dst not in df.columns:
            df.rename(columns={src: dst}, inplace=True)

    for col in ["brewery_id", "name", "brewery_type", "city", "state"]:
        if col not in df.columns:
            df[col] = ""
        df[col] = df[col].astype(str).fillna("")

    return df


def read_csv_safe(path):
    """Safe CSV reader that never throws."""
    if not os.path.exists(path):
        return pd.DataFrame()
    try:
        return pd.read_csv(path)
    except Exception:
        return pd.DataFrame()


def _norm(s): return (s or "").strip().lower()


def _fuzzy_bonus(target, query):
    """Scoring helper for fuzzy matching."""
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


# ------------------------------
# Data loaders
# ------------------------------

def load_breweries_df():
    """Load brewery data from local file, cache, or API."""
    BREWERIES_FALLBACK = os.path.join(DATA_DIR, "breweries.csv")
    cache_path = os.path.join(DATA_DIR, "breweries_cache.csv")

    if os.path.exists(BREWERIES_CSV):
        try:
            df = pd.read_csv(BREWERIES_CSV)
            if not df.empty:
                return normalize_breweries_df(df)
        except Exception:
            pass

    if os.path.exists(cache_path):
        try:
            df = pd.read_csv(cache_path)
            if not df.empty:
                return normalize_breweries_df(df)
        except Exception:
            pass

    try:
        resp = requests.get("https://api.openbrewerydb.org/breweries?per_page=200", timeout=20)
        resp.raise_for_status()
        data = resp.json()
        df = pd.json_normalize(data)
        rename = {"id": "brewery_id", "name": "name", "brewery_typ
