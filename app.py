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
    bdf = read_csv_safe(BREWERIES_CSV)
    mdf = read_csv_safe(MENU_CSV)

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
        names = bdf["name"].dropna().astype(str)
        exact = [n for n in names if n.lower() == ql]
        starts = [n for n in names if n.lower().startswith(ql) and n not in exact]
        contains = [n for n in names if ql in n.lower() and n not in exact and n not in starts]
        suggestions = uniq(exact + starts + contains)[:12]

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
        required = {"style","user_rating","global_rating","user_weight","global_weight"}
        if not required.issubset(set(df.columns)):
            flash("CSV missing required columns: " + ", ".join(sorted(required)))
            return redirect(url_for("profile"))
        os.makedirs(UPLOAD_DIR, exist_ok=True)
        df.to_csv(PROFILE_CSV, index=False)
        flash("Profile uploaded and set active.")
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
