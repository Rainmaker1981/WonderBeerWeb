from flask import Flask, render_template, request, redirect, url_for, flash, send_from_directory, jsonify
import os, math, time, re, json
import pandas as pd
import requests
from bs4 import BeautifulSoup

# -----------------------------
# Paths & App
# -----------------------------
APP_DIR   = os.path.dirname(os.path.abspath(__file__))
DATA_DIR  = os.path.join(APP_DIR, "data")
UPLOAD_DIR= os.path.join(APP_DIR, "uploads")
os.makedirs(DATA_DIR, exist_ok=True)
os.makedirs(UPLOAD_DIR, exist_ok=True)

# Input files
BREWERIES_CSV        = os.path.join(DATA_DIR, "breweries.csv")          # OpenBreweryDB CSV
MENU_CSV             = os.path.join(DATA_DIR, "sample_menu.csv")
PROFILE_CSV          = os.path.join(UPLOAD_DIR, "profile.csv")
SAMPLE_PROFILE_CSV   = os.path.join(DATA_DIR, "sample_profile.csv")
BEER_CACHE_JSON      = os.path.join(DATA_DIR, "beer_cache.json")        # optional local json
BREWERIES_CACHE_CSV  = os.path.join(DATA_DIR, "breweries_cache.csv")    # fetched API cache
MENUS_CACHE_DIR      = os.path.join(DATA_DIR, "menus_cache")            # scraped venue menu cache
os.makedirs(MENUS_CACHE_DIR, exist_ok=True)

app = Flask(__name__)
app.secret_key = "wonderbeer-demo"

HTTP_TIMEOUT = 20
HEADERS = {
    "User-Agent": "WonderBEER/1.0 (+https://wonderbeer.example; contact: owner)",
    "Accept": "text/html,application/xhtml+xml",
}

# -----------------------------
# Small utils
# -----------------------------
def _norm(s):
    return (s or "").strip().lower()

def _fuzzy_bonus(target, query):
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
    seen = set(); out = []
    for s in seq:
        s = str(s)
        if s not in seen:
            seen.add(s); out.append(s)
    return out

def _slug(s: str) -> str:
    s = (s or "").strip().lower()
    s = re.sub(r"[^a-z0-9]+", "-", s)
    return s.strip("-") or "venue"

# -----------------------------
# Normalizers (columns vary by sources)
# -----------------------------
def normalize_breweries_df(df: pd.DataFrame) -> pd.DataFrame:
    """
    Normalize OpenBreweryDB-like CSV to include:
      brewery_id, name, brewery_type, city, state_province
    (We keep state_province to handle international data. We'll also alias 'state' if present.)
    """
    if df is None or df.empty:
        return pd.DataFrame(columns=["brewery_id","name","brewery_type","city","state_province"])

    df = df.copy()
    # Common aliases
    rename = {
        "id": "brewery_id",
        "brewery_type": "brewery_type",
        "brewerytype": "brewery_type",
        "name": "name",
        "city": "city",
        "state_province": "state_province",
        "state": "state",  # we may alias to state_province next
        "country": "country",
        "website_url": "website_url",
    }
    for src, dst in rename.items():
        if src in df.columns and dst not in df.columns:
            df.rename(columns={src: dst}, inplace=True)

    # prefer state_province, but fill from state if needed
    if "state_province" not in df.columns:
        df["state_province"] = ""
    if "state" in df.columns and df["state_province"].eq("").all():
        df["state_province"] = df["state"]

    # Ensure required
    for col in ["brewery_id","name","brewery_type","city","state_province"]:
        if col not in df.columns:
            df[col] = ""

    # Stringify
    for col in ["brewery_id","name","brewery_type","city","state_province","country","website_url"]:
        if col in df.columns:
            df[col] = df[col].astype(str).fillna("")

    return df

def normalize_menu_df(df: pd.DataFrame) -> pd.DataFrame:
    """
    Normalize menu dataframe columns to include:
      name, style, abv, ibu, global_rating (float)
    Accept alternate names like rating -> global_rating.
    """
    if df is None or df.empty:
        return pd.DataFrame(columns=["name","style","abv","ibu","global_rating"])

    df = df.copy()
    # column mapping (source -> target)
    mapping = {
        "name":"name", "beer_name":"name", "title":"name",
        "style":"style","beer_style":"style","beer_type":"style","type":"style",
        "abv":"abv","beer_abv":"abv",
        "ibu":"ibu","beer_ibu":"ibu",
        "global_rating":"global_rating","rating":"global_rating","rating_score":"global_rating",
        "brewery_id":"brewery_id","brewery.brewery_id":"brewery_id",
        "brewery_name":"brewery_name","image":"image"
    }
    for src, dst in mapping.items():
        if src in df.columns and dst not in df.columns:
            df.rename(columns={src: dst}, inplace=True)

    for c in ["name","style","brewery_name","image"]:
        if c not in df.columns: df[c] = ""
        df[c] = df[c].astype(str)

    for c in ["abv","ibu","global_rating","brewery_id"]:
        if c in df.columns:
            df[c] = pd.to_numeric(df[c], errors="coerce")

    # If ratings on 0..5, keep; if 0..100 or 0..10, they should be pre-scaled by importers
    return df

# -----------------------------
# Data Loaders
# -----------------------------
def load_profile():
    return read_csv_safe(PROFILE_CSV)

def load_breweries_df():
    """
    Prefer local CSV; fallback to cached API; fallback to direct API page.
    Always normalized on return.
    """
    # 1) Local
    df = read_csv_safe(BREWERIES_CSV)
    if not df.empty:
        return normalize_breweries_df(df)

    # 2) Cached API
    df = read_csv_safe(BREWERIES_CACHE_CSV)
    if not df.empty:
        return normalize_breweries_df(df)

    # 3) Live fetch small page and cache
    try:
        resp = requests.get("https://api.openbrewerydb.org/breweries?per_page=200", timeout=HTTP_TIMEOUT)
        resp.raise_for_status()
        data = resp.json()
        df = pd.json_normalize(data)
        df = normalize_breweries_df(df)
        df.to_csv(BREWERIES_CACHE_CSV, index=False)
        return df
    except Exception:
        pass

    return pd.DataFrame(columns=["brewery_id","name","brewery_type","city","state_province"])

def load_menu_df():
    """
    Load from JSON cache if present (data/beer_cache.json), else sample CSV.
    Always normalized on return.
    """
    if os.path.exists(BEER_CACHE_JSON):
        try:
            with open(BEER_CACHE_JSON, "r", encoding="utf-8") as f:
                raw = json.load(f)
            items = raw.get("beers", raw) if isinstance(raw, dict) else raw
            df = pd.json_normalize(items)
            return normalize_menu_df(df)
        except Exception:
            pass

    df = read_csv_safe(MENU_CSV)
    return normalize_menu_df(df)

# -----------------------------
# Profile preview helper
# -----------------------------
def get_profile_preview(df, n=10):
    if df.empty: return []
    cols = ["style","user_rating","global_rating","user_weight","global_weight"]
    for c in cols:
        if c not in df.columns: df[c] = None
    preview = df[cols].head(n).fillna("")
    return preview.to_dict(orient="records")

# -----------------------------
# Untappd scraping helpers (venue page -> menu JSON)
# -----------------------------
def _get(url: str):
    try:
        resp = requests.get(url, headers=HEADERS, timeout=HTTP_TIMEOUT)
        if resp.status_code == 200:
            return resp
    except Exception:
        return None
    return None

def _parse_abv_ibu(text: str):
    # e.g. "7.5% ABV • 12 IBU"
    abv, ibu = None, None
    if not text:
        return abv, ibu
    m_abv = re.search(r"(\d+(?:\.\d+)?)\s*%\s*ABV", text, re.I)
    if m_abv:
        try: abv = float(m_abv.group(1))
        except: pass
    m_ibu = re.search(r"(\d+(?:\.\d+)?)\s*IBU", text, re.I)
    if m_ibu:
        try: ibu = float(m_ibu.group(1))
        except: pass
    return abv, ibu

def scrape_untappd_venue_menu(venue_url: str):
    resp = _get(venue_url)
    if not resp:
        return {"ok": False, "reason": "fetch_failed", "source": "untappd", "source_url": venue_url}

    soup = BeautifulSoup(resp.text, "html.parser")
    beers = []

    for li in soup.select("li.menu-item#beer"):
        # image
        img = li.select_one(".beer-label img")
        image = img["src"].strip() if img and img.has_attr("src") else ""

        # name & style
        title = li.select_one(".beer-details h5")
        name, style = "", ""
        if title:
            a = title.select_one("a")
            em = title.select_one("em")
            name = (a.get_text(strip=True) if a else title.get_text(strip=True)) or ""
            style = (em.get_text(strip=True) if em else "")

        # ABV / IBU / rating (in h6)
        h6 = li.select_one(".beer-details h6")
        abv, ibu, rating = None, None, None
        brewery_name = ""
        if h6:
            span_text = " ".join([t.get_text(" ", strip=True) for t in h6.select("span")])
            abv, ibu = _parse_abv_ibu(span_text)

            rate_div = h6.select_one("div.caps.small")
            if rate_div and rate_div.has_attr("data-rating"):
                try: rating = float(rate_div["data-rating"])
                except: rating = None

            b = h6.select_one("a[data-track='menu'][data-href=':brewery']")
            if b:
                brewery_name = b.get_text(strip=True)

        if name:
            beers.append({
                "name": name,
                "style": style,
                "abv": abv,
                "ibu": ibu,
                "global_rating": rating,   # align with our scoring
                "image": image,
                "brewery_name": brewery_name,
            })

    return {
        "ok": True,
        "source": "untappd",
        "source_url": venue_url,
        "count": len(beers),
        "beers": beers,
    }

def cached_menu_path(key: str) -> str:
    return os.path.join(MENUS_CACHE_DIR, f"{_slug(key)}.json")

def cache_menu_json(key: str, payload: dict):
    path = cached_menu_path(key)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    return path

def load_cached_menu(key: str):
    path = cached_menu_path(key)
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return None
    return None

def scrape_and_cache_untappd(venue_url: str, cache_key: str):
    cached = load_cached_menu(cache_key)
    if cached and isinstance(cached, dict) and cached.get("ok") and cached.get("count", 0) > 0:
        return {"from": "cache", "key": cache_key, **cached}
    time.sleep(0.8)  # be gentle
    data = scrape_untappd_venue_menu(venue_url)
    cache_menu_json(cache_key, data)
    return {"from": "live", "key": cache_key, **data}

# -----------------------------
# Scoring
# -----------------------------
def score_beers(menu_df, profile_df):
    if menu_df.empty:
        return menu_df

    if profile_df.empty:
        profile_df = pd.DataFrame(columns=["style","user_rating","global_rating","user_weight","global_weight"])

    p = profile_df.copy()
    for col in ["user_rating","global_rating","user_weight","global_weight"]:
        if col in p.columns:
            p[col] = pd.to_numeric(p[col], errors="coerce")
        else:
            p[col] = 0.0
    p["style_norm"] = p["style"].astype(str).str.strip().str.lower()

    style_pref = p.groupby("style_norm").apply(lambda df: (df["user_rating"]*df["user_weight"]).mean()).to_dict()
    global_w = p["global_weight"].mean() if not p.empty else 0.5
    user_w   = p["user_weight"].mean()   if not p.empty else 1.0

    m = menu_df.copy()
    if "style" not in m.columns: m["style"] = ""
    if "name" not in m.columns:  m["name"]  = ""
    m["style_norm"] = m["style"].astype(str).str.strip().str.lower()
    m["user_pref"]  = m["style_norm"].map(style_pref).fillna(0.0)

    # normalize ratings if 0..5 → 0..1
    gr = pd.to_numeric(m.get("global_rating", pd.Series([0]*len(m))), errors="coerce").fillna(0.0)
    if gr.max(skipna=True) and gr.max(skipna=True) <= 5.0:
        gr = gr / 5.0
    m["gr_norm"] = gr

    m["score"] = m["user_pref"].fillna(0.0) * (user_w if not math.isnan(user_w) else 1.0) \
               + m["gr_norm"].fillna(0.0)   * (global_w if not math.isnan(global_w) else 0.5)
    return m

# -----------------------------
# Views
# -----------------------------
@app.route("/")
def index():
    return render_template("index.html")

@app.route("/profile")
def profile():
    df = load_profile()
    preview = get_profile_preview(df)
    return render_template("profile.html",
        profile_exists=not df.empty,
        profile_preview=preview)

@app.post("/profile/upload")
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
            # Untappd export → normalize
            norm = normalize_untappd_to_profile(df)
            if norm.empty:
                flash("Could not infer styles/ratings from this CSV. Expect Untappd export with beer_type and rating_score, or our 5-column format.")
                return redirect(url_for("profile"))
        os.makedirs(UPLOAD_DIR, exist_ok=True)
        norm.to_csv(PROFILE_CSV, index=False)
        flash("Profile uploaded and set active." if required.issubset(cols_lower) else "Uploaded Untappd CSV normalized into profile preferences.")
    except Exception as e:
        flash(f"Upload failed: {e}")
    return redirect(url_for("profile"))

@app.get("/profile/sample")
def download_sample_profile():
    # Keep this endpoint name to match your template reference.
    return send_from_directory(DATA_DIR, "sample_profile.csv", as_attachment=True)

@app.get("/breweries")
def breweries():
    q = (request.args.get("q") or "").strip().lower()
    t = (request.args.get("type") or "").strip().lower()

    bdf = load_breweries_df()  # normalized with state_province
    if bdf.empty:
        return render_template("breweries.html", items=[], types=[])

    df = bdf.copy()
    if q:
        # search across name, city, state_province
        mask = (
            df["name"].str.lower().str.contains(q, na=False) |
            df["city"].str.lower().str.contains(q, na=False) |
            df["state_province"].str.lower().str.contains(q, na=False)
        )
        df = df[mask]

    if t:
        df = df[df["brewery_type"].str.lower() == t]

    if q:
        df = df.copy()
        df["brewery_score"] = (
            df["name"].apply(lambda n: _fuzzy_bonus(n, q))
            + df["city"].apply(lambda n: _fuzzy_bonus(n, q)) * 0.25
            + df["state_province"].apply(lambda n: _fuzzy_bonus(n, q)) * 0.15
        )
        df = df.sort_values(by=["brewery_score","name"], ascending=[False, True])

    items = df.to_dict(orient="records")
    types = sorted([x for x in df["brewery_type"].dropna().unique()])
    return render_template("breweries.html", items=items, types=types)

@app.get("/api/suggest")
def suggest():
    q   = (request.args.get("q") or "").strip()
    typ = (request.args.get("type") or "").strip().lower()
    if not q or len(q) < 2:
        return jsonify({"suggestions": []})

    # breweries
    if typ == "brewery":
        bdf = load_breweries_df()
        if bdf.empty:
            return jsonify({"suggestions": []})
        b = bdf.dropna(subset=["name"]).copy()
        b["_match"] = b["name"].astype(str).str.lower()
        ql = q.lower()

        exact    = b[b["_match"] == ql]
        starts   = b[b["_match"].str.startswith(ql) & ~b.index.isin(exact.index)]
        contains = b[b["_match"].str.contains(ql) & ~b.index.isin(exact.index) & ~b.index.isin(starts.index)]
        comb = pd.concat([exact, starts, contains], ignore_index=True)\
                 .drop_duplicates(subset=[c for c in ["name","city","state_province"] if c in b.columns], keep="first")

        def line(r):
            city = (r.get("city") or "").strip()
            st   = (r.get("state_province") or "").strip()
            tail = ", ".join([x for x in [city, st] if x])
            return f"{r['name']} — {tail}" if tail else str(r["name"])

        suggestions = uniq([line(r) for r in comb.to_dict(orient="records")])[:12]
        return jsonify({"suggestions": suggestions})

    # beer names
    if typ == "beer":
        mdf = load_menu_df()
        if mdf.empty or "name" not in mdf.columns:
            return jsonify({"suggestions": []})
        names = mdf["name"].dropna().astype(str)
        ql = q.lower()
        exact    = [n for n in names if n.lower() == ql]
        starts   = [n for n in names if n.lower().startswith(ql) and n not in exact]
        contains = [n for n in names if ql in n.lower() and n not in exact and n not in starts]
        return jsonify({"suggestions": uniq(exact + starts + contains)[:12]})

    # style
    if typ == "style":
        pool = []
        mdf = load_menu_df()
        if not mdf.empty and "style" in mdf.columns:
            pool += mdf["style"].dropna().astype(str).tolist()
        try:
            pdf = load_profile()
            if not pdf.empty and "style" in pdf.columns:
                pool += pdf["style"].dropna().astype(str).tolist()
        except Exception:
            pass
        if not pool:
            return jsonify({"suggestions": []})
        uniq_styles = pd.Series(pool).dropna().astype(str).unique().tolist()
        ql = q.lower()
        exact    = [s for s in uniq_styles if s.lower() == ql]
        starts   = [s for s in uniq_styles if s.lower().startswith(ql) and s not in exact]
        contains = [s for s in uniq_styles if ql in s.lower() and s not in exact and s not in starts]
        return jsonify({"suggestions": uniq(exact + starts + contains)[:12]})

    return jsonify({"suggestions": []})

# -----------------------------
# Admin: scrape a venue page once & cache
# -----------------------------
@app.get("/admin/scrape_untappd")
def admin_scrape_untappd():
    venue_url = (request.args.get("venue_url") or "").strip()
    venue     = (request.args.get("venue") or "").strip()
    city      = (request.args.get("city") or "").strip()
    state     = (request.args.get("state") or "").strip()

    if not venue_url:
        flash("Missing ?venue_url= param.")
        return redirect(url_for("index"))

    key = "--".join([p for p in [_slug(venue), _slug(city), _slug(state)] if p]) or "untappd-venue"
    result = scrape_and_cache_untappd(venue_url, key)
    flash(f"Untappd scrape: {result.get('count',0)} beers ({result.get('from')}).")
    # Jump to match using venue strings (match() will load cached file)
    return redirect(url_for("match", venue=venue, city=city, state=state))

# -----------------------------
# Match view (menu -> score -> sorted list)
# Supports: brewery_id OR (venue, city, state) cached menu
# -----------------------------
@app.get("/match")
def match():
    brewery_id   = request.args.get("brewery_id")
    order        = request.args.get("order", "score")
    style_filter = (request.args.get("style") or "").strip().lower()
    name_query   = (request.args.get("q") or "").strip()

    # Venue-based cached menu first (if venue, city, or state provided)
    venue = (request.args.get("venue") or "").strip()
    city  = (request.args.get("city") or "").strip()
    state = (request.args.get("state") or "").strip()

    mdf = pd.DataFrame()
    if venue or city or state:
        key = "--".join([p for p in [_slug(venue), _slug(city), _slug(state)] if p]) or None
        if key:
            cached = load_cached_menu(key)
            if cached and cached.get("ok"):
                mdf = pd.json_normalize(cached.get("beers", []))
                mdf = normalize_menu_df(mdf)

    # Brewery object (for display) if we have an id
    b = None
    bdf = load_breweries_df()
    if brewery_id and not bdf.empty and "brewery_id" in bdf.columns:
        pick = bdf[bdf["brewery_id"].astype(str) == str(brewery_id)]
        b = pick.to_dict(orient="records")[0] if not pick.empty else None

    # If no venue cache, fallback to general menu data
    if mdf.empty:
        mdf = load_menu_df()

        # If brewery_id is provided, try to filter by it when column exists
        if brewery_id and "brewery_id" in mdf.columns:
            mdf = mdf[mdf["brewery_id"].astype(str) == str(brewery_id)]

    # Style filter
    if style_filter and not mdf.empty and "style" in mdf.columns:
        mdf = mdf[mdf["style"].str.lower().str.contains(style_filter, na=False)]

    # Ensure required columns
    if "global_rating" not in mdf.columns and "rating" in mdf.columns:
        mdf["global_rating"] = pd.to_numeric(mdf["rating"], errors="coerce")

    for col in ("name","style"):
        if col not in mdf.columns:
            mdf[col] = ""

    # Score using user profile
    pdf = load_profile()
    scored = score_beers(mdf, pdf)

    # Bonus by beer name search
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
    return render_template("match.html", brewery=b, menu=not mdf.empty, rows=rows)

# -----------------------------
# Untappd → profile normalizer (for CSV uploads)
# -----------------------------
def normalize_untappd_to_profile(df_raw: pd.DataFrame) -> pd.DataFrame:
    """
    Accept an Untappd export (beer_name, brewery_name, beer_type, beer_abv, rating_score, ...)
    Produce 5 columns: style, user_rating, global_rating, user_weight, global_weight
    Aggregates by style.
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

    agg = df.groupby(df['style'].str.lower().str.strip()).agg({
        'user_rating': 'mean',
        'global_rating': 'mean'
    }).reset_index().rename(columns={'style': 'style_norm'})

    agg['style'] = agg['style_norm'].str.replace(r'\s+', ' ', regex=True).str.title()
    agg['user_weight'] = 1.0
    agg['global_weight'] = 0.6
    return agg[['style','user_rating','global_rating','user_weight','global_weight']]

# -----------------------------
# Debug routes
# -----------------------------
@app.get("/debug/tree")
def debug_tree():
    roots = [DATA_DIR, APP_DIR]
    out = {}
    for r in roots:
        items = []
        if os.path.isdir(r):
            for name in sorted(os.listdir(r)):
                p = os.path.join(r, name)
                try:
                    items.append({
                        "name": name,
                        "is_dir": os.path.isdir(p),
                        "size": os.path.getsize(p) if os.path.isfile(p) else None
                    })
                except Exception:
                    items.append({"name": name, "is_dir": os.path.isdir(p), "size": None})
        out[r] = items
    return jsonify(out)

@app.get("/debug/breweries")
def debug_breweries():
    try:
        df = load_breweries_df()
        return jsonify({
            "path": BREWERIES_CSV,
            "exists": os.path.exists(BREWERIES_CSV),
            "rows": int(len(df)),
            "columns": list(df.columns),
            "head": df.head(3).to_dict(orient="records")
        })
    except Exception as e:
        return jsonify({"error": str(e)})

# -----------------------------
# Entrypoint
# -----------------------------
if __name__ == "__main__":
    # For local debug
    app.run(debug=True, host="0.0.0.0", port=5000)
