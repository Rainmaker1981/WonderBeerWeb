from flask import (
    Flask, render_template, request, redirect, url_for,
    flash, send_from_directory, jsonify
)
import os, math, json, requests
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

def uniq(seq):
    seen, out = set(), []
    for s in seq:
        s = str(s)
        if s not in seen:
            seen.add(s)
            out.append(s)
    return out

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
        "city": "city",
    }
    for src, dst in rename.items():
        if src in df.columns and dst not in df.columns:
            df.rename(columns={src: dst}, inplace=True)

    for col in ["brewery_id", "name", "brewery_type", "city", "state"]:
        if col not in df.columns:
            df[col] = ""
        df[col] = df[col].astype(str).fillna("")

    return df

def load_breweries_df():
    """Load OpenBreweryDB CSV, cached API, or fallback."""
    cache_path = os.path.join(DATA_DIR, "breweries_cache.csv")

    # 1) Local CSV
    if os.path.exists(BREWERIES_CSV):
        try:
            df = pd.read_csv(BREWERIES_CSV)
            if not df.empty:
                return normalize_breweries_df(df)
        except Exception:
            pass

    # 2) Cached API CSV
    if os.path.exists(cache_path):
        try:
            df = pd.read_csv(cache_path)
            if not df.empty:
                return normalize_breweries_df(df)
        except Exception:
            pass

    # 3) Fresh API page (small page to avoid long cold-starts)
    try:
        resp = requests.get("https://api.openbrewerydb.org/breweries?per_page=200", timeout=15)
        resp.raise_for_status()
        data = resp.json()
        df = pd.json_normalize(data)
        # light rename for consistency
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

    # 4) Fallback (still normalized)
    return normalize_breweries_df(read_csv_safe(BREWERIES_CSV))

def load_menu_df():
    """Load beer list from JSON cache (beer_cache.json) or fallback CSV. Always ensure `name`/`style` exist."""
    path = os.path.join(DATA_DIR, "beer_cache.json")
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                raw = json.load(f)
            items = raw.get("beers", raw) if isinstance(raw, dict) else raw
            mdf = pd.json_normalize(items)

            # normalize common variants
            rename = {
                "beer_name": "name",
                "beer_type": "style",
                "beer_style": "style",
                "beer_abv": "abv",
                "beer_ibu": "ibu",
                "rating_score": "global_rating",
                "brewery.brewery_id": "brewery_id",
            }
            for k, v in rename.items():
                if k in mdf.columns and v not in mdf.columns:
                    mdf.rename(columns={k: v}, inplace=True)

            for col in ["name", "style", "brewery_name", "abv", "ibu", "global_rating", "brewery_id"]:
                if col not in mdf.columns:
                    mdf[col] = ""

            for c in ["abv", "ibu", "global_rating"]:
                mdf[c] = pd.to_numeric(mdf[c], errors="coerce")

            return mdf
        except Exception:
            return pd.DataFrame()

    # fallback CSV
    mdf = read_csv_safe(MENU_CSV)
    if "name" not in mdf.columns:
        mdf["name"] = ""
    if "style" not in mdf.columns:
        mdf["style"] = ""
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
        listing = []
        if os.path.isdir(root):
            for name in sorted(os.listdir(root)):
                p = os.path.join(root, name)
                try:
                    listing.append({
                        "name": name,
                        "is_dir": os.path.isdir(p),
                        "size": os.path.getsize(p) if os.path.isfile(p) else None
                    })
                except Exception:
                    listing.append({"name": name, "is_dir": os.path.isdir(p), "size": None})
        out[root] = listing
    return jsonify(out)

@app.get("/debug/breweries")
def debug_breweries():
    try:
        df = load_breweries_df()
        return jsonify({
            "exists": os.path.exists(BREWERIES_CSV),
            "rows": int(len(df)),
            "columns": list(df.columns),
            "sample": df.head(5).to_dict(orient="records")
        })
    except Exception as e:
        return jsonify({"error": str(e)})

# ------------------------------
# Suggest / Autocomplete
# ------------------------------
@app.get("/api/suggest")
def suggest():
    q = (request.args.get("q") or "").strip()
    typ = (request.args.get("type") or "").strip().lower()
    if not q or len(q) < 2:
        return jsonify({"suggestions": []})

    bdf = load_breweries_df()
    mdf = load_menu_df()
    ql = q.lower()
    suggestions = []

    # Brewery autocomplete
    if typ == "brewery" and not bdf.empty:
        bdf = bdf.dropna(subset=["name"]).copy()
        bdf["_match"] = bdf["name"].astype(str).str.lower()
        exact = bdf[bdf["_match"] == ql]
        starts = bdf[bdf["_match"].str.startswith(ql) & ~bdf.index.isin(exact.index)]
        contains = bdf[bdf["_match"].str.contains(ql) & ~bdf.index.isin(exact.index) & ~bdf.index.isin(starts.index)]

        subset_cols = [c for c in ["name", "city", "state"] if c in bdf.columns]
        if not subset_cols:
            subset_cols = ["name"]

        comb = pd.concat([exact, starts, contains], ignore_index=True)\
                 .drop_duplicates(subset=subset_cols, keep="first")

        def fmt_row(r):
            city = str(r.get("city", "") or "").strip()
            state = str(r.get("state", "") or "").strip()
            tail = ", ".join([x for x in [city, state] if x])
            return f"{r['name']} — {tail}" if tail else str(r["name"])

        suggestions = uniq([fmt_row(r) for _, r in comb.iterrows()])[:12]

    # Beer autocomplete
    elif typ == "beer" and not mdf.empty and "name" in mdf.columns:
        names = mdf["name"].dropna().astype(str)
        exact = [n for n in names if n.lower() == ql]
        starts = [n for n in names if n.lower().startswith(ql) and n not in exact]
        contains = [n for n in names if ql in n.lower() and n not in exact and n not in starts]
        suggestions = uniq(exact + starts + contains)[:12]

    # Style autocomplete
    elif typ == "style":
        pool = []
        if not mdf.empty and "style" in mdf.columns:
            pool += mdf["style"].dropna().astype(str).tolist()
        pdf = load_profile()
        if not pdf.empty and "style" in pdf.columns:
            pool += pdf["style"].dropna().astype(str).tolist()

        uniq_styles = pd.Series(pool).dropna().astype(str).unique().tolist()
        exact = [s for s in uniq_styles if s.lower() == ql]
        starts = [s for s in uniq_styles if s.lower().startswith(ql) and s not in exact]
        contains = [s for s in uniq_styles if ql in s.lower() and s not in exact and s not in starts]
        suggestions = uniq(exact + starts + contains)[:12]

    return jsonify({"suggestions": suggestions})

# ------------------------------
# Profile normalization
# ------------------------------
def normalize_untappd_to_profile(df_raw: pd.DataFrame) -> pd.DataFrame:
    cols = {c.lower(): c for c in df_raw.columns}

    def pick(*names):
        for n in names:
            if n in cols:
                return df_raw[cols[n]]
        return pd.Series([None] * len(df_raw))

    style_series = pick("beer_type", "style", "beer_style")
    user_rating = pd.to_numeric(pick("rating_score", "my_rating", "user_rating"), errors="coerce")
    global_rating = pd.to_numeric(pick("global_rating", "rating_global"), errors="coerce")

    def scale(v):
        if v.dropna().empty:
            return v
        mx = v.max(skipna=True)
        if mx and mx > 10:
            return v / 20.0
        if mx and 5 < mx <= 10:
            return v / 2.0
        return v

    user_rating = scale(user_rating)
    global_rating = scale(global_rating)

    df = pd.DataFrame({
        "style": style_series.astype(str).str.strip(),
        "user_rating": user_rating,
        "global_rating": global_rating,
    }).dropna(subset=["style"])

    agg = df.groupby(df["style"].str.lower().str.strip()).agg({
        "user_rating": "mean",
        "global_rating": "mean"
    }).reset_index().rename(columns={"style": "style_norm"})

    agg["style"] = agg["style_norm"].str.replace(r"\s+", " ", regex=True).str.title()
    agg["user_weight"] = 1.0
    agg["global_weight"] = 0.6
    return agg[["style", "user_rating", "global_rating", "user_weight", "global_weight"]]

# ------------------------------
# Basic pages
# ------------------------------
@app.route("/")
def index():
    return render_template("index.html")

@app.route("/profile")
def profile():
    df = load_profile()
    preview = df.head(10).fillna("").to_dict(orient="records") if not df.empty else []
    return render_template("profile.html", profile_exists=not df.empty, profile_preview=preview)

@app.post("/profile/upload")
def upload_profile():
    f = request.files.get("file")
    if not f:
        flash("No file received.")
        return redirect(url_for("profile"))
    try:
        df = pd.read_csv(f)
        cols_lower = {c.lower() for c in df.columns}
        required = {"style", "user_rating", "global_rating", "user_weight", "global_weight"}
        if required.issubset(cols_lower) or required.issubset(set(df.columns)):
            norm = df[["style", "user_rating", "global_rating", "user_weight", "global_weight"]].copy()
        else:
            norm = normalize_untappd_to_profile(df)
            if norm.empty:
                flash("Could not infer styles/ratings from this CSV. Expect Untappd export with beer_type and rating_score, or our 5-column format.")
                return redirect(url_for("profile"))
        os.makedirs(UPLOAD_DIR, exist_ok=True)
        norm.to_csv(PROFILE_CSV, index=False)
        flash("Profile uploaded.")
    except Exception as e:
        flash(f"Upload failed: {e}")
    return redirect(url_for("profile"))

@app.get("/profile/sample")
def sample_profile():
    return send_from_directory(DATA_DIR, "sample_profile.csv", as_attachment=True)

# ------------------------------
# Breweries page
# ------------------------------
@app.route("/breweries")
def breweries():
    q = (request.args.get("q") or "").strip().lower()
    t = (request.args.get("type") or "").strip().lower()
    bdf = normalize_breweries_df(load_breweries_df())

    if bdf.empty:
        return render_template("breweries.html", items=[], types=[])

    if q:
        mask = (
            bdf["name"].str.lower().str.contains(q, na=False) |
            bdf["city"].str.lower().str.contains(q, na=False) |
            bdf["state"].str.lower().str.contains(q, na=False)
        )
        bdf = bdf[mask]

    if t:
        bdf = bdf[bdf["brewery_type"].str.lower() == t]

    if q:
        bdf = bdf.copy()
        bdf["brewery_score"] = (
            bdf["name"].apply(lambda n: _fuzzy_bonus(n, q)) +
            bdf["city"].apply(lambda n: _fuzzy_bonus(n, q)) * 0.25 +
            bdf["state"].apply(lambda n: _fuzzy_bonus(n, q)) * 0.15
        )
        bdf = bdf.sort_values(by=["brewery_score", "name"], ascending=[False, True])

    items = bdf.to_dict(orient="records")
    types = sorted(bdf["brewery_type"].dropna().unique().tolist())
    return render_template("breweries.html", items=items, types=types)

# ------------------------------
# Beer matching
# ------------------------------
def score_beers(menu_df, profile_df):
    if menu_df.empty:
        return menu_df
    if profile_df.empty:
        profile_df = pd.DataFrame(columns=["style", "user_rating", "global_rating", "user_weight", "global_weight"])

    p = profile_df.copy()
    for col in ["user_rating", "global_rating", "user_weight", "global_weight"]:
        p[col] = pd.to_numeric(p[col], errors="coerce").fillna(0)
    p["style_norm"] = p["style"].astype(str).str.lower()

    style_pref = p.groupby("style_norm").apply(
        lambda df: (df["user_rating"] * df["user_weight"]).mean()
    ).to_dict()
    global_w = float(p["global_weight"].mean()) if not p.empty else 0.5
    user_w = float(p["user_weight"].mean()) if not p.empty else 1.0

    m = menu_df.copy()
    if "style" not in m.columns:
        m["style"] = ""
    if "name" not in m.columns:
        m["name"] = ""

    m["style_norm"] = m["style"].astype(str).str.lower()
    m["user_pref"] = m["style_norm"].map(style_pref).fillna(0.0)

    if "global_rating" in m.columns:
        gr = pd.to_numeric(m["global_rating"], errors="coerce")
        if gr.max(skipna=True) and gr.max(skipna=True) <= 5.0:
            gr = gr / 5.0
        m["gr_norm"] = gr.fillna(0.0)
    else:
        m["gr_norm"] = 0.0

    m["score"] = m["user_pref"] * user_w + m["gr_norm"] * global_w
    return m

@app.route("/match")
def match():
    brewery_id  = request.args.get("brewery_id")
    style_filter= (request.args.get("style") or "").strip().lower()
    name_query  = (request.args.get("q") or "").strip()
    order       = request.args.get("order", "score")

    bdf = normalize_breweries_df(load_breweries_df())
    b = None
    if brewery_id and not bdf.empty:
        pick = bdf[bdf["brewery_id"].astype(str) == str(brewery_id)]
        b = pick.to_dict(orient="records")[0] if not pick.empty else None

    mdf = load_menu_df()
    if "style" not in mdf.columns:
        mdf["style"] = ""
    if "name" not in mdf.columns:
        mdf["name"] = ""

    if brewery_id and not mdf.empty and "brewery_id" in mdf.columns:
        mdf = mdf[mdf["brewery_id"].astype(str) == str(brewery_id)]
    elif b is not None and "brewery_name" in mdf.columns:
        mdf = mdf[mdf["brewery_name"].astype(str).str.lower() == b["name"].lower()]

    if style_filter and not mdf.empty:
        mdf = mdf[mdf["style"].astype(str).str.lower().str.contains(style_filter, na=False)]

    pdf = load_profile()
    scored = score_beers(mdf, pdf)

    if not scored.empty and name_query:
        scored["search_bonus"] = scored["name"].apply(lambda n: _fuzzy_bonus(n, name_query))
        scored["score"] = scored["score"].fillna(0.0) + scored["search_bonus"].fillna(0.0)

    if not scored.empty:
        if order in scored.columns:
            scored = scored.sort_values(by=order, ascending=False)
        else:
            scored = scored.sort_values(by="score", ascending=False)

    rows = scored.to_dict(orient="records") if not scored.empty else []
    return render_template("match.html", brewery=b, menu=not mdf.empty, rows=rows)

# ------------------------------
# Admin utility (optional)
# ------------------------------
@app.get("/admin/reload_breweries")
def reload_breweries():
    """Manually refresh cache from OpenBreweryDB."""
    try:
        resp = requests.get("https://api.openbrewerydb.org/breweries?per_page=200", timeout=20)
        resp.raise_for_status()
        data = resp.json()
        df = pd.json_normalize(data)
        rename = {"id": "brewery_id", "name": "name", "brewery_type": "brewery_type", "city": "city", "state": "state", "country": "country"}
        for k, v in rename.items():
            if k in df.columns:
                df.rename(columns={k: v}, inplace=True)
        cache_path = os.path.join(DATA_DIR, "breweries_cache.csv")
        df.to_csv(cache_path, index=False)
        flash(f"Reloaded {len(df)} breweries from OpenBreweryDB.")
    except Exception as e:
        flash(f"Reload failed: {e}")
    return redirect(url_for("breweries"))

# ------------------------------
# Run
# ------------------------------
if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=5000)
