from flask import Flask, render_template, request, redirect, url_for, flash, send_from_directory, jsonify
import os, math, json
from functools import lru_cache
import pandas as pd
import requests

# --------------------------------------------------------------------------------------
# Paths & App
# --------------------------------------------------------------------------------------

APP_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(APP_DIR, "data")
UPLOAD_DIR = os.path.join(APP_DIR, "uploads")

# Local data files (you already have these in /data)
BREWERIES_CSV       = os.path.join(DATA_DIR, "breweries.csv")
MENU_CSV_FALLBACK   = os.path.join(DATA_DIR, "sample_menu.csv")
PROFILE_CSV_ACTIVE  = os.path.join(UPLOAD_DIR, "profile.csv")
SAMPLE_PROFILE_CSV  = os.path.join(DATA_DIR, "sample_profile.csv")
BEER_CACHE_JSON     = os.path.join(DATA_DIR, "beer_cache.json")
BREWERIES_CACHE_CSV = os.path.join(DATA_DIR, "breweries_cache.csv")

app = Flask(__name__)
app.secret_key = "wonderbeer-demo"

# --------------------------------------------------------------------------------------
# Utilities
# --------------------------------------------------------------------------------------

def _norm(s):
    return (str(s) if s is not None else "").strip().lower()

def _fuzzy_bonus(target, query):
    """Numeric bonus for how well `target` matches `query` (exact > startswith > contains > fuzzy)."""
    t = _norm(target)
    q = _norm(query)
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
        ratio = SequenceMatcher(None, t, q).ratio()  # 0..1
        return ratio * 10.0
    except Exception:
        return 0.0

def read_csv_safe(path):
    if not os.path.exists(path):
        return pd.DataFrame()
    try:
        return pd.read_csv(path)
    except Exception:
        return pd.DataFrame()

def ensure_dir(path):
    os.makedirs(path, exist_ok=True)

# --------------------------------------------------------------------------------------
# Data Normalization
# --------------------------------------------------------------------------------------

def normalize_breweries_df(df: pd.DataFrame) -> pd.DataFrame:
    """
    Always return a copy with canonical columns:
      brewery_id, name, brewery_type, city, state_province
    Accepts sources that may use 'state' or 'state_province' and maps both into state_province.
    """
    if df is None or df.empty:
        return pd.DataFrame(columns=["brewery_id", "name", "brewery_type", "city", "state_province"])

    df = df.copy()

    # Map known variants to canonical names
    rename = {
        "id": "brewery_id",
        "brewerytype": "brewery_type",
        "brewery_type": "brewery_type",
        "name": "name",
        "city": "city",
        "state": "state_province",
        "state_province": "state_province",
    }
    for src, dst in rename.items():
        if src in df.columns and dst not in df.columns:
            df.rename(columns={src: dst}, inplace=True)

    # Ensure required columns exist
    for col in ["brewery_id", "name", "brewery_type", "city", "state_province"]:
        if col not in df.columns:
            df[col] = ""

    # Coerce to string
    for col in ["brewery_id", "name", "brewery_type", "city", "state_province"]:
        df[col] = df[col].astype(str).fillna("")

    return df

def normalize_menu_df(mdf: pd.DataFrame) -> pd.DataFrame:
    """
    Normalize menu/beer list DataFrame to contain at least:
      name (str), style (str), brewery_id (num/str optional), brewery_name (str optional),
      abv (float), ibu (float), global_rating (float)
    """
    if mdf is None or mdf.empty:
        return pd.DataFrame(columns=["name", "style", "brewery_id", "brewery_name", "abv", "ibu", "global_rating"])

    mdf = mdf.copy()

    # Column alias map
    rename = {
        "beer_name": "name",
        "title": "name",

        "beer_style": "style",
        "beer_type": "style",
        "type": "style",

        "beer_abv": "abv",

        "beer_ibu": "ibu",

        "rating_score": "global_rating",
        "rating_global": "global_rating",

        "brewery.brewery_id": "brewery_id",
        "breweryId": "brewery_id",
        "brewery": "brewery_name",
    }
    for src, dst in rename.items():
        if src in mdf.columns and dst not in mdf.columns:
            mdf.rename(columns={src: dst}, inplace=True)

    # Guarantee required columns
    for col in ["name", "style", "brewery_id", "brewery_name"]:
        if col not in mdf.columns:
            mdf[col] = ""

    # Types
    for col in ["name", "style", "brewery_name"]:
        mdf[col] = mdf[col].astype(str)

    for col in ["abv", "ibu", "global_rating", "brewery_id"]:
        if col in mdf.columns:
            mdf[col] = pd.to_numeric(mdf[col], errors="coerce")

    return mdf

# --------------------------------------------------------------------------------------
# Data Loading (with caching for breweries)
# --------------------------------------------------------------------------------------

def _fetch_openbrewerydb_first_page() -> pd.DataFrame:
    """Try to fetch a first page of breweries from the public API as a cache source."""
    try:
        resp = requests.get("https://api.openbrewerydb.org/breweries?per_page=200", timeout=20)
        resp.raise_for_status()
        data = resp.json()
        df = pd.json_normalize(data)
        # Bring into our expected columns
        if "id" in df.columns and "brewery_id" not in df.columns:
            df.rename(columns={"id": "brewery_id"}, inplace=True)
        return df
    except Exception:
        return pd.DataFrame()

def load_breweries_df_uncached() -> pd.DataFrame:
    """
    Load breweries from:
      1) Local CSV (data/breweries.csv)
      2) Cache CSV (data/breweries_cache.csv)
      3) API first page -> cache to data/breweries_cache.csv
      4) Empty DF (last resort)
    Always normalize to canonical columns.
    """
    # 1) Local CSV
    if os.path.exists(BREWERIES_CSV):
        df = read_csv_safe(BREWERIES_CSV)
        if not df.empty:
            return normalize_breweries_df(df)

    # 2) Cached CSV
    if os.path.exists(BREWERIES_CACHE_CSV):
        df = read_csv_safe(BREWERIES_CACHE_CSV)
        if not df.empty:
            return normalize_breweries_df(df)

    # 3) Fetch & cache
    df = _fetch_openbrewerydb_first_page()
    if not df.empty:
        try:
            df.to_csv(BREWERIES_CACHE_CSV, index=False)
        except Exception:
            pass
        return normalize_breweries_df(df)

    # 4) Empty
    return normalize_breweries_df(pd.DataFrame())

@lru_cache(maxsize=1)
def breweries_df_cached() -> pd.DataFrame:
    df = load_breweries_df_uncached()
    # add lowercased helper columns for fast filters
    for c in ("name", "city", "state_province"):
        df[f"_{c}"] = df[c].str.strip().str.lower()
    return df

def clear_brewery_cache():
    breweries_df_cached.cache_clear()

def load_menu_df() -> pd.DataFrame:
    """
    Load beer list from data/beer_cache.json if available; otherwise fallback to sample_menu.csv.
    Normalize columns before returning.
    """
    # JSON cache
    if os.path.exists(BEER_CACHE_JSON):
        try:
            with open(BEER_CACHE_JSON, "r", encoding="utf-8") as f:
                raw = json.load(f)
            items = raw.get("beers", raw) if isinstance(raw, dict) else raw
            mdf = pd.json_normalize(items)
            return normalize_menu_df(mdf)
        except Exception:
            pass

    # CSV fallback
    return normalize_menu_df(read_csv_safe(MENU_CSV_FALLBACK))

def load_profile_df() -> pd.DataFrame:
    return read_csv_safe(PROFILE_CSV_ACTIVE)

# --------------------------------------------------------------------------------------
# Untappd → Profile normalization
# --------------------------------------------------------------------------------------

def normalize_untappd_to_profile(df_raw: pd.DataFrame) -> pd.DataFrame:
    """
    Accept an Untappd export (beer_name, brewery_name, beer_type, beer_abv, rating_score, ...)
    and produce the 5-column profile CSV:
      style, user_rating, global_rating, user_weight, global_weight
    Aggregates multiple rows per style into mean ratings.
    """
    if df_raw is None or df_raw.empty:
        return pd.DataFrame(columns=["style","user_rating","global_rating","user_weight","global_weight"])

    cols = {c.lower(): c for c in df_raw.columns}

    def pick(*names):
        for n in names:
            if n in cols:
                return df_raw[cols[n]]
        return pd.Series([None] * len(df_raw))

    style_series  = pick("beer_type","style","beer_style")
    user_rating   = pd.to_numeric(pick("rating_score","my_rating","user_rating"), errors="coerce")
    global_rating = pd.to_numeric(pick("global_rating","global_rating_score","rating_global"), errors="coerce")

    def scale(v):
        if v.dropna().empty:
            return v
        mx = v.max(skipna=True)
        if pd.notna(mx) and mx > 10:          # 0..100 → 0..5
            return v / 20.0
        if pd.notna(mx) and 5 < mx <= 10:     # 0..10 → 0..5
            return v / 2.0
        return v

    user_rating   = scale(user_rating)
    global_rating = scale(global_rating)

    style = style_series.astype(str).str.strip()
    style = style.replace({"nan": None, "None": None}).where(style != "", None)

    df = pd.DataFrame({
        "style": style,
        "user_rating": user_rating,
        "global_rating": global_rating
    }).dropna(subset=["style"])

    # Aggregate preferences by style (case-insensitive)
    agg = df.groupby(df["style"].str.lower().str.strip()).agg({
        "user_rating": "mean",
        "global_rating": "mean"
    }).reset_index().rename(columns={"style": "style_norm"})

    # Pretty style name
    agg["style"] = agg["style_norm"].str.replace(r"\s+", " ", regex=True).str.title()
    agg["user_weight"] = 1.0
    agg["global_weight"] = 0.6
    return agg[["style","user_rating","global_rating","user_weight","global_weight"]]

# --------------------------------------------------------------------------------------
# Debug helpers (optional)
# --------------------------------------------------------------------------------------

@app.get("/debug/tree")
def debug_tree():
    roots = [APP_DIR, DATA_DIR]
    out = {}
    for root in roots:
        items = []
        try:
            if os.path.isdir(root):
                for name in sorted(os.listdir(root)):
                    p = os.path.join(root, name)
                    try:
                        items.append({
                            "name": name,
                            "is_dir": os.path.isdir(p),
                            "size": os.path.getsize(p) if os.path.isfile(p) else None
                        })
                    except Exception:
                        items.append({"name": name, "is_dir": os.path.isdir(p), "size": None})
        except Exception:
            pass
        out[root] = items
    return jsonify(out)

@app.get("/debug/breweries")
def debug_breweries():
    df = breweries_df_cached()
    return jsonify({
        "path": BREWERIES_CSV,
        "exists": os.path.exists(BREWERIES_CSV),
        "rows": int(len(df)),
        "columns": list(df.columns),
        "head": df.head(3).to_dict(orient="records")
    })

# --------------------------------------------------------------------------------------
# API: Typeahead & Fast Filtering
# --------------------------------------------------------------------------------------

@app.get("/api/suggest")
def suggest():
    q   = (request.args.get("q") or "").strip()
    typ = (request.args.get("type") or "").strip().lower()
    if not q or len(q) < 2:
        return jsonify({"suggestions": []})

    ql = q.lower()
    suggestions = []

    # Brewery suggest ("Name — City, Region")
    if typ == "brewery":
        bdf = breweries_df_cached()
        if not bdf.empty:
            exact    = bdf[bdf["_name"] == ql]
            starts   = bdf[bdf["_name"].str.startswith(ql) & ~bdf.index.isin(exact.index)]
            contains = bdf[bdf["_name"].str.contains(ql) & ~bdf.index.isin(exact.index) & ~bdf.index.isin(starts.index)]
            comb = pd.concat([exact, starts, contains], ignore_index=True)

            # Dedup by name + city + state_province
            subset_cols = [c for c in ["name","city","state_province"] if c in comb.columns]
            if not subset_cols:
                subset_cols = ["name"]
            comb = comb.drop_duplicates(subset=subset_cols, keep="first")

            def display_row(row):
                city  = (row.get("city") or "").strip()
                reg   = (row.get("state_province") or "").strip()
                tail  = ", ".join([x for x in [city, reg] if x])
                return f"{row['name']} — {tail}" if tail else str(row["name"])

            comb["display"] = comb.apply(display_row, axis=1)
            suggestions = [s for s in comb["display"].tolist() if s][:12]

    # Beer name suggest
    elif typ == "beer":
        mdf = load_menu_df()
        if not mdf.empty and "name" in mdf.columns:
            names = mdf["name"].dropna().astype(str)
            exact    = [n for n in names if n.lower() == ql]
            starts   = [n for n in names if n.lower().startswith(ql) and n not in exact]
            contains = [n for n in names if ql in n.lower() and n not in exact and n not in starts]
            seen, out = set(), []
            for s in (exact + starts + contains):
                if s not in seen:
                    seen.add(s); out.append(s)
            suggestions = out[:12]

    # Style suggest (menu + profile pool)
    elif typ == "style":
        pool = []
        mdf = load_menu_df()
        if not mdf.empty and "style" in mdf.columns:
            pool += mdf["style"].dropna().astype(str).tolist()
        pdf = load_profile_df()
        if not pdf.empty and "style" in pdf.columns:
            pool += pdf["style"].dropna().astype(str).tolist()

        if pool:
            uniq_styles = pd.Series(pool).dropna().astype(str).unique().tolist()
            exact    = [s for s in uniq_styles if s.lower() == ql]
            starts   = [s for s in uniq_styles if s.lower().startswith(ql) and s not in exact]
            contains = [s for s in uniq_styles if ql in s.lower() and s not in exact and s not in starts]
            seen, out = set(), []
            for s in (exact + starts + contains):
                if s not in seen:
                    seen.add(s); out.append(s)
            suggestions = out[:12]

    return jsonify({"suggestions": suggestions})

@app.get("/api/states")
def api_states():
    df = breweries_df_cached()
    vals = sorted([s for s in df["state_province"].unique() if str(s).strip()])
    return jsonify({"states": vals})

@app.get("/api/cities")
def api_cities():
    state_province = (request.args.get("state") or "").strip().lower()
    df = breweries_df_cached()
    if state_province:
        df = df[df["_state_province"] == state_province]
    cities = sorted([c for c in df["city"].unique() if str(c).strip()])
    return jsonify({"cities": cities})

@app.get("/api/breweries/search")
def api_breweries_search():
    state_province = (request.args.get("state") or "").strip().lower()
    city  = (request.args.get("city")  or "").strip().lower()
    q     = (request.args.get("q")     or "").strip().lower()
    limit = int(request.args.get("limit", 200))

    df = breweries_df_cached()
    if state_province:
        df = df[df["_state_province"] == state_province]
    if city:
        df = df[df["_city"] == city]
    if q:
        exact    = df[df["_name"] == q]
        starts   = df[df["_name"].str.startswith(q) & ~df.index.isin(exact.index)]
        contains = df[df["_name"].str.contains(q) & ~df.index.isin(exact.index) & ~df.index.isin(starts.index)]
        df = pd.concat([exact, starts, contains], ignore_index=True)
    else:
        df = df.sort_values(["_name"]).copy()

    cols = ["brewery_id","name","brewery_type","city","state_province"]
    for c in cols:
        if c not in df.columns:
            df[c] = ""
    out = df[cols].head(limit).to_dict(orient="records")
    return jsonify({"items": out, "count": len(out)})

# --------------------------------------------------------------------------------------
# Views
# --------------------------------------------------------------------------------------

@app.route("/")
def index():
    return render_template("index.html")

def get_profile_preview(df, n=10):
    if df.empty: 
        return []
    cols = ["style","user_rating","global_rating","user_weight","global_weight"]
    for c in cols:
        if c not in df.columns:
            df[c] = None
    preview = df[cols].head(n).fillna("")
    return preview.to_dict(orient="records")

@app.route("/profile")
def profile():
    df = load_profile_df()
    preview = get_profile_preview(df)
    return render_template(
        "profile.html",
        profile_exists=not df.empty,
        profile_preview=preview
    )

@app.post("/profile/upload")
def upload_profile():
    f = request.files.get("file")
    if not f:
        flash("No file received.")
        return redirect(url_for("profile"))
    try:
        df = pd.read_csv(f)
        # Accept either our 5-column profile or Untappd export
        cols_lower = {c.lower() for c in df.columns}
        required = {"style","user_rating","global_rating","user_weight","global_weight"}
        if required.issubset(cols_lower) or required.issubset(set(df.columns)):
            # Already normalized
            norm = df[["style","user_rating","global_rating","user_weight","global_weight"]].copy()
        else:
            # Try to normalize Untappd → profile
            norm = normalize_untappd_to_profile(df)
            if norm.empty:
                flash("Could not infer styles/ratings from this CSV. Expect Untappd export with beer_type and rating_score, or our 5-column format.")
                return redirect(url_for("profile"))

        ensure_dir(UPLOAD_DIR)
        norm.to_csv(PROFILE_CSV_ACTIVE, index=False)
        flash("Profile uploaded and set active.")
    except Exception as e:
        flash(f"Upload failed: {e}")
    return redirect(url_for("profile"))

@app.get("/profile/sample")
def download_sample_profile():
    # Template should call url_for('download_sample_profile')
    return send_from_directory(DATA_DIR, "sample_profile.csv", as_attachment=True)

@app.route("/breweries")
def breweries():
    # Server-side render of list; client can also call /api/* for fast filters
    q = (request.args.get("q") or "").strip().lower()
    t = (request.args.get("type") or "").strip().lower()

    bdf = breweries_df_cached()
    if bdf.empty:
        items, types = [], []
    else:
        filtered = bdf
        if q:
            mask = (
                filtered["_name"].str.contains(q, na=False) |
                filtered["_city"].str.contains(q, na=False) |
                filtered["_state_province"].str.contains(q, na=False)
            )
            filtered = filtered[mask]
        if t:
            filtered = filtered[filtered["brewery_type"].str.strip().str.lower() == t]

        if q:
            filtered = filtered.copy()
            filtered["brewery_score"] = (
                filtered["name"].apply(lambda n: _fuzzy_bonus(n, q))
                + filtered["city"].apply(lambda n: _fuzzy_bonus(n, q)) * 0.25
                + filtered["state_province"].apply(lambda n: _fuzzy_bonus(n, q)) * 0.15
            )
            filtered = filtered.sort_values(by=["brewery_score","name"], ascending=[False, True])

        items = filtered[["brewery_id","name","brewery_type","city","state_province"]].to_dict(orient="records")
        types = sorted([x for x in bdf["brewery_type"].dropna().unique()])

    return render_template("breweries.html", items=items, types=types)

def score_beers(menu_df: pd.DataFrame, profile_df: pd.DataFrame) -> pd.DataFrame:
    if menu_df.empty:
        return menu_df

    # Ensure required columns
    m = menu_df.copy()
    for col in ["name","style"]:
        if col not in m.columns:
            m[col] = ""

    # Profile default
    p = profile_df.copy() if not profile_df.empty else pd.DataFrame(columns=["style","user_rating","global_rating","user_weight","global_weight"])

    # Make numeric
    for col in ["user_rating","global_rating","user_weight","global_weight"]:
        if col in p.columns:
            p[col] = pd.to_numeric(p[col], errors="coerce")
        else:
            p[col] = 0.0

    p["style_norm"] = p["style"].astype(str).str.strip().str.lower()

    # user_pref = average of (user_rating * user_weight) by style
    style_pref = p.groupby("style_norm").apply(lambda df: (df["user_rating"] * df["user_weight"]).mean()).to_dict()
    global_w = p["global_weight"].mean() if not p.empty else 0.5
    user_w   = p["user_weight"].mean() if not p.empty else 1.0

    m["style_norm"] = m["style"].astype(str).strip().str.lower()
    m["user_pref"]  = m["style_norm"].map(style_pref).fillna(0.0)

    # Normalize global rating to 0..1 if on 0..5 scale
    if "global_rating" in m.columns:
        gr = pd.to_numeric(m["global_rating"], errors="coerce")
        if pd.notna(gr.max()) and gr.max() <= 5.0:
            gr = gr / 5.0
        m["gr_norm"] = gr.fillna(0.0)
    else:
        m["gr_norm"] = 0.0

    # final score
    m["score"] = m["user_pref"].fillna(0.0) * (user_w if not math.isnan(user_w) else 1.0) \
               + m["gr_norm"].fillna(0.0)   * (global_w if not math.isnan(global_w) else 0.5)
    return m

@app.route("/match")
def match():
    brewery_id   = request.args.get("brewery_id")
    order        = request.args.get("order", "score")
    style_filter = (request.args.get("style") or "").strip().lower()
    name_query   = (request.args.get("q") or "").strip()

    # Load breweries & (if needed) normalize id
    bdf = breweries_df_cached()
    b = None
    if brewery_id and not bdf.empty:
        pick = bdf[bdf["brewery_id"].astype(str) == str(brewery_id)]
        b = pick.to_dict(orient="records")[0] if not pick.empty else None

    # Load menu and attempt to match by brewery
    mdf = load_menu_df()

    # Ensure minimal columns for scoring/search
    if "style" not in mdf.columns: mdf["style"] = ""
    if "name"  not in mdf.columns: mdf["name"]  = ""

    # Try match by brewery_id if present
    if brewery_id and "brewery_id" in mdf.columns:
        mdf = mdf[mdf["brewery_id"].astype(str) == str(brewery_id)]

    # Fallback to match by brewery_name if no ID match and we know the brewery name
    if (mdf.empty or "brewery_id" not in mdf.columns) and b and "name" in b and "brewery_name" in mdf.columns:
        target_name = (b["name"] or "").strip().lower()
        mdf = mdf[mdf["brewery_name"].astype(str).str.strip().str.lower() == target_name]

    # Optional style filter
    if style_filter and not mdf.empty and "style" in mdf.columns:
        mdf = mdf[mdf["style"].str.lower().str.contains(style_filter, na=False)]

    # Score with profile
    pdf = load_profile_df()
    scored = score_beers(mdf, pdf)

    # Name search bonus
    if not scored.empty and name_query:
        scored = scored.copy()
        scored["search_bonus"] = scored["name"].apply(lambda n: _fuzzy_bonus(n, name_query))
        scored["score"] = scored["score"].fillna(0.0) + scored["search_bonus"].fillna(0.0)

    # Sort
    if not scored.empty:
        if order in {"score","abv","ibu"} and order in scored.columns:
            scored = scored.sort_values(by=order, ascending=False)
        else:
            scored = scored.sort_values(by="score", ascending=False)

    rows = scored.to_dict(orient="records") if not scored.empty else []
    return render_template("match.html",
                           brewery=b,
                           menu=not mdf.empty,
                           rows=rows)

# --------------------------------------------------------------------------------------
# Admin refresh (optional)
# --------------------------------------------------------------------------------------

@app.get("/admin/reload_breweries")
def reload_breweries():
    try:
        df = _fetch_openbrewerydb_first_page()
        if df.empty:
            flash("OpenBreweryDB returned no data.")
        else:
            df.to_csv(BREWERIES_CACHE_CSV, index=False)
            clear_brewery_cache()
            flash(f"Reloaded {len(df)} breweries from OpenBreweryDB.")
    except Exception as e:
        flash(f"Reload failed: {e}")
    return redirect(url_for("breweries"))

# --------------------------------------------------------------------------------------
# Main
# --------------------------------------------------------------------------------------

if __name__ == "__main__":
    # Local dev
    app.run(debug=True, host="0.0.0.0", port=5000)
