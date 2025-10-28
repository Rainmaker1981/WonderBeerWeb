from flask import Flask, render_template, request, redirect, url_for, flash, send_from_directory
import os, math
import pandas as pd

APP_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(APP_DIR, "data")
UPLOAD_DIR = os.path.join(APP_DIR, "uploads")

BREWERIES_CSV = os.path.join(DATA_DIR, "breweries_sample.csv")
MENU_CSV = os.path.join(DATA_DIR, "sample_menu.csv")
PROFILE_CSV = os.path.join(UPLOAD_DIR, "profile.csv")
SAMPLE_PROFILE_CSV = os.path.join(DATA_DIR, "sample_profile.csv")

app = Flask(__name__)
app.secret_key = "wonderbeer-demo"

from flask import jsonify

@app.get("/api/suggest")
def suggest():
    q = (request.args.get("q") or "").strip()
    typ = (request.args.get("type") or "").strip().lower()
    if not q or len(q) < 2:
        return jsonify({"suggestions": []})
    # Load sources
    bdf = load_breweries_df()
    mdf = load_menu_df()

    def uniq(seq):
        seen=set(); out=[]
        for s in seq:
            s = str(s)
            if s not in seen:
                seen.add(s); out.append(s)
        return out

    ql = q.lower()
    suggestions = []
    if typ == "brewery" and not bdf.empty:
        bdf = bdf.dropna(subset=["name"]).copy()
        bdf["_match"] = bdf["name"].str.lower()
        exact    = bdf[bdf["_match"] == ql]
        starts   = bdf[bdf["_match"].str.startswith(ql) & ~bdf.index.isin(exact.index)]
        contains = bdf[bdf["_match"].str.contains(ql) & ~bdf.index.isin(exact.index) & ~bdf.index.isin(starts.index)]

    comb = pd.concat([exact, starts, contains]).drop_duplicates(subset=["name","city","state"], keep="first")
    comb["display"] = comb.apply(lambda r: f"{r['name']} — {r.get('city','')}, {r.get('state','')}".strip().strip(', '), axis=1)
    suggestions = [s for s in comb["display"].tolist() if s][:12]


    elif typ == "beer" and not mdf.empty:
        names = mdf["name"].dropna().astype(str)
        exact = [n for n in names if n.lower() == ql]
        starts = [n for n in names if n.lower().startswith(ql) and n not in exact]
        contains = [n for n in names if ql in n.lower() and n not in exact and n not in starts]
        suggestions = uniq(exact + starts + contains)[:12]

    elif typ == "style":
        src = []
        if not mdf.empty:
            src += mdf["style"].dropna().astype(str).tolist()
        # If user uploaded a profile, include styles from it
        pdf = read_csv_safe(PROFILE_CSV)
        if not pdf.empty and "style" in pdf.columns:
            src += pdf["style"].dropna().astype(str).tolist()
        if src:
            names = pd.Series(src).dropna().astype(str).unique().tolist()
            exact = [n for n in names if n.lower() == ql]
            starts = [n for n in names if n.lower().startswith(ql) and n not in exact]
            contains = [n for n in names if ql in n.lower() and n not in exact and n not in starts]
            suggestions = uniq(exact + starts + contains)[:12]

    return jsonify({"suggestions": suggestions})


def _norm(s):
    return (s or "").strip().lower()

def _fuzzy_bonus(target, query):
    # Returns a numeric bonus for how well `target` matches `query`.
    # Priority: exact > startswith > contains > fuzzy ratio.
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

def load_profile():
    return read_csv_safe(PROFILE_CSV)

import requests, json

def normalize_untappd_to_profile(df_raw: pd.DataFrame) -> pd.DataFrame:
    """Accept an Untappd export (beer_name, brewery_name, beer_type, beer_abv, rating_score, ...)
    and produce the 5-column profile: style, user_rating, global_rating, user_weight, global_weight.
    Aggregates multiple rows per style into mean ratings.
    """
    cols = {c.lower(): c for c in df_raw.columns}

    def pick(*names):
        for n in names:
            if n in cols:
                return df_raw[cols[n]]
        return pd.Series([None] * len(df_raw))

    style_series  = pick('beer_type','style','beer_style')
    user_rating   = pd.to_numeric(pick('rating_score','my_rating','user_rating'), errors='coerce')
    global_rating = pd.to_numeric(pick('global_rating','global_rating_score','rating_global'), errors='coerce')

    # If ratings look like 0..100 or 0..10, scale toward 0..5
    def scale(v):
        if v.dropna().empty:
            return v
        mx = v.max(skipna=True)
        if mx and mx > 10:   # 0..100 → 0..5
            return v / 20.0
        if mx and 5 < mx <= 10:  # 0..10 → 0..5
            return v / 2.0
        return v

    user_rating   = scale(user_rating)
    global_rating = scale(global_rating)

    style = style_series.astype(str).str.strip()
    style = style.replace({'nan': None, 'None': None}).where(style != '', None)

    df = pd.DataFrame({
        'style': style,
        'user_rating': user_rating,
        'global_rating': global_rating
    }).dropna(subset=['style'])

    # Aggregate preferences by style (case-insensitive key)
    agg = df.groupby(df['style'].str.lower().str.strip()).agg({
        'user_rating': 'mean',
        'global_rating': 'mean'
    }).reset_index().rename(columns={'style': 'style_norm'})

    # Pretty style name
    agg['style'] = agg['style_norm'].str.replace(r'\s+', ' ', regex=True).str.title()
    agg['user_weight'] = 1.0
    agg['global_weight'] = 0.6
    return agg[['style','user_rating','global_rating','user_weight','global_weight']]

def load_breweries_df():
    """Prefer data/breweries.csv (OpenBreweryDB). Fall back to cached API, then sample."""
    BREWERIES_FALLBACK = os.path.join(DATA_DIR, "breweries_sample.csv")
    cache_path = os.path.join(DATA_DIR, "breweries_cache.csv")

    # 1) Prefer your local OpenBreweryDB CSV
    if os.path.exists(BREWERIES_CSV):
        try:
            df = pd.read_csv(BREWERIES_CSV)
            if not df.empty:
                return df
        except Exception:
            pass

    # 2) Use cached API CSV if present
    if os.path.exists(cache_path):
        try:
            df = pd.read_csv(cache_path)
            if not df.empty:
                return df
        except Exception:
            pass

    # 3) Fetch a fresh page from API and cache
    try:
        resp = requests.get("https://api.openbrewerydb.org/breweries?per_page=200", timeout=20)
        resp.raise_for_status()
        data = resp.json()
        df = pd.json_normalize(data)
        rename = {"id":"brewery_id","name":"name","brewery_type":"brewery_type","city":"city","state":"state","country":"country"}
        for k,v in rename.items():
            if k in df.columns:
                df.rename(columns={k:v}, inplace=True)
        df.to_csv(cache_path, index=False)
        return df
    except Exception:
        pass

    # 4) Fallback sample
    return read_csv_safe(BREWERIES_FALLBACK)

def load_menu_df():
    """Load beer list from data/beer_cache.json; fall back to sample_menu.csv."""
    path = os.path.join(DATA_DIR, "beer_cache.json")
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                raw = json.load(f)
            items = raw.get("beers", raw) if isinstance(raw, dict) else raw
            mdf = pd.json_normalize(items)

            # Normalize columns from typical sources
            rename = {
                "name":"name","beer_name":"name",
                "style":"style","beer_type":"style",
                "abv":"abv","beer_abv":"abv",
                "ibu":"ibu","beer_ibu":"ibu",
                "global_rating":"global_rating","rating_score":"global_rating",
                "brewery_id":"brewery_id","brewery.brewery_id":"brewery_id",
                "brewery_name":"brewery_name"
            }
            for k,v in rename.items():
                if k in mdf.columns and v not in mdf.columns:
                    mdf.rename(columns={k:v}, inplace=True)

            for c in ["abv","ibu","global_rating","brewery_id"]:
                if c in mdf.columns:
                    mdf[c] = pd.to_numeric(mdf[c], errors="coerce")
            for c in ["name","style","brewery_name"]:
                if c in mdf.columns:
                    mdf[c] = mdf[c].astype(str)

            return mdf
        except Exception:
            return pd.DataFrame()

    return read_csv_safe(MENU_CSV)

@app.get("/admin/reload_breweries")
def reload_breweries():
    """Manually refresh cache from OpenBreweryDB."""
    try:
        resp = requests.get("https://api.openbrewerydb.org/breweries?per_page=200", timeout=20)
        resp.raise_for_status()
        data = resp.json()
        df = pd.json_normalize(data)
        rename = {"id":"brewery_id","name":"name","brewery_type":"brewery_type","city":"city","state":"state","country":"country"}
        for k,v in rename.items():
            if k in df.columns:
                df.rename(columns={k:v}, inplace=True)
        cache_path = os.path.join(DATA_DIR, "breweries_cache.csv")
        df.to_csv(cache_path, index=False)
        flash(f"Reloaded {len(df)} breweries from OpenBreweryDB.")
    except Exception as e:
        flash(f"Reload failed: {e}")
    return redirect(url_for("breweries"))


def get_profile_preview(df, n=10):
    if df.empty: return []
    cols = ["style","user_rating","global_rating","user_weight","global_weight"]
    for c in cols:
        if c not in df.columns: df[c] = None
    preview = df[cols].head(n).fillna("")
    return preview.to_dict(orient="records")

@app.route("/")
def index():
    return render_template("index.html")

@app.route("/profile")
def profile():
    df = load_profile()
    return render_template("profile.html",
        profile_exists=not df.empty,
        profile_preview=get_profile_preview(df))

@app.route("/profile/upload", methods=["POST"])
def upload_profile():
    f = request.files.get("file")
    if not f:
        flash("No file received.")
        return redirect(url_for("profile"))
    try:
        df = pd.read_csv(f)
        cols_lower = {c.lower() for c in df.columns}
        required = {"style","user_rating","global_rating","user_weight","global_weight"}
        if required.issubset(cols_lower) or required.issubset(set(df.columns)):
            norm = df[['style','user_rating','global_rating','user_weight','global_weight']].copy()
        else:
            norm = normalize_untappd_to_profile(df)
            if norm.empty:
                flash("Could not infer styles/ratings from this CSV. Expect Untappd export with beer_type and rating_score, or our 5-column format.")
                return redirect(url_for("profile"))
        os.makedirs(UPLOAD_DIR, exist_ok=True)
        norm.to_csv(PROFILE_CSV, index=False)
        flash("Uploaded Untappd CSV normalized into profile preferences." if 'beer_type' in [c.lower() for c in df.columns] else "Profile uploaded and set active.")
    except Exception as e:
        flash(f"Upload failed: {e}")
    return redirect(url_for("profile"))


@app.get("/profile/sample")
def download_sample_profile():
    return send_from_directory(DATA_DIR, "sample_profile.csv", as_attachment=True)

@app.route("/breweries")
def breweries():
    q = (request.args.get("q") or "").strip().lower()
    t = (request.args.get("type") or "").strip().lower()
    bdf = read_csv_safe(BREWERIES_CSV)
    if bdf.empty:
        items = []
        types = []
    else:
        if q:
            mask = (
                bdf["name"].str.lower().str.contains(q, na=False) |
                bdf["city"].str.lower().str.contains(q, na=False) |
                bdf["state"].str.lower().str.contains(q, na=False)
            )
            bdf = bdf[mask]
        if t:
            bdf = bdf[bdf["brewery_type"].str.lower()==t]
        # Fuzzy priority sort
        if q:
            bdf = bdf.copy()
            bdf["brewery_score"] = bdf["name"].apply(lambda n: _fuzzy_bonus(n, q)) \
                                   + bdf["city"].apply(lambda n: _fuzzy_bonus(n, q)) * 0.25 \
                                   + bdf["state"].apply(lambda n: _fuzzy_bonus(n, q)) * 0.15
            bdf = bdf.sort_values(by=["brewery_score","name"], ascending=[False, True])
        items = bdf.to_dict(orient="records")
        types = sorted([x for x in bdf["brewery_type"].dropna().unique()])
    return render_template("breweries.html", items=items, types=types)

def score_beers(menu_df, profile_df):
    if menu_df.empty:
        return menu_df
    # Normalize style match using user profile
    if profile_df.empty:
        profile_df = pd.DataFrame(columns=["style","user_rating","global_rating","user_weight","global_weight"])
    # Prepare lookup by style (case-insensitive)
    p = profile_df.copy()
    for col in ["user_rating","global_rating","user_weight","global_weight"]:
        if col in p.columns:
            p[col] = pd.to_numeric(p[col], errors="coerce")
        else:
            p[col] = 0.0
    p["style_norm"] = p["style"].str.strip().str.lower()
    # Build style -> pref score
    # user_pref = user_rating * user_weight
    # global component = global_rating * global_weight (if present on beer)
    style_pref = p.groupby("style_norm").apply(lambda df: (df["user_rating"]*df["user_weight"]).mean()).to_dict()
    global_w = p["global_weight"].mean() if not p.empty else 0.5
    user_w = p["user_weight"].mean() if not p.empty else 1.0

    m = menu_df.copy()
    m["style_norm"] = m["style"].str.strip().str.lower()
    m["user_pref"] = m["style_norm"].map(style_pref).fillna(0.0)
    # Normalize global ratings to 0..1 if they look like 0..5 scale
    if "global_rating" in m.columns:
        gr = pd.to_numeric(m["global_rating"], errors="coerce")
        if gr.max(skipna=True) and gr.max(skipna=True) <= 5.0:
            gr = gr / 5.0
        m["gr_norm"] = gr.fillna(0.0)
    else:
        m["gr_norm"] = 0.0

    # Final score: weighted combination
    # Score = user_pref * user_w + gr_norm * global_w
    m["score"] = m["user_pref"].fillna(0.0) * (user_w if not math.isnan(user_w) else 1.0) + m["gr_norm"].fillna(0.0) * (global_w if not math.isnan(global_w) else 0.5)
    return m

@app.route("/match")
def match():
    brewery_id = request.args.get("brewery_id")
    order = request.args.get("order", "score")
    style_filter = (request.args.get("style") or "").strip().lower()
    name_query = (request.args.get("q") or "").strip()

    bdf = read_csv_safe(BREWERIES_CSV)
    b = None
    if brewery_id and not bdf.empty:
        pick = bdf[bdf["brewery_id"].astype(str)==str(brewery_id)]
        b = pick.to_dict(orient="records")[0] if not pick.empty else None

    mdf = read_csv_safe(MENU_CSV)
    if brewery_id and not mdf.empty:
        mdf = mdf[mdf["brewery_id"].astype(str)==str(brewery_id)]
    if style_filter and not mdf.empty:
        mdf = mdf[mdf["style"].str.lower().str.contains(style_filter, na=False)]

    pdf = load_profile()
    scored = score_beers(mdf, pdf)
    if not scored.empty:
        if name_query:
            scored = scored.copy()
            scored["search_bonus"] = scored["name"].apply(lambda n: _fuzzy_bonus(n, name_query))
            # Boost the existing score so exact name matches bubble to the top
            scored["score"] = scored["score"].fillna(0.0) + scored["search_bonus"].fillna(0.0)
        # Sort
        if order in {"score","abv","ibu"} and order in scored.columns:
            scored = scored.sort_values(by=order, ascending=False)
        else:
            scored = scored.sort_values(by="score", ascending=False)

    rows = scored.to_dict(orient="records") if not scored.empty else []
    return render_template("match.html",
        brewery=b,
        menu=not mdf.empty,
        rows=rows)

if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=5000)
