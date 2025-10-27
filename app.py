from flask import Flask, render_template, request, redirect, url_for, session, flash
import os, json
import pandas as pd
from difflib import get_close_matches
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "dev-key")

ROOT = os.path.dirname(__file__)
DATA = os.path.join(ROOT, "Data")
os.makedirs(DATA, exist_ok=True)

def data_path(*parts): 
    return os.path.join(DATA, *parts)

def load_profiles():
    p = data_path("profiles.json")
    if os.path.exists(p):
        with open(p, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}

def save_profiles(obj):
    with open(data_path("profiles.json"), "w", encoding="utf-8") as f:
        json.dump(obj, f, indent=2)

@app.route("/", methods=["GET","POST"])
def home():
    profs = load_profiles()
    if request.method == "POST":
        mode = request.form.get("mode")
        if mode == "create":
            first = (request.form.get("first") or "").strip().capitalize()
            last  = (request.form.get("last")  or "").strip().capitalize()
            if not first or not last:
                flash("Enter first and last name.", "error")
                return redirect(url_for("home"))
            display = f"{first} {last}"
            fname   = f"{first}_{last}_Beer_Data.csv"
            csvp = data_path(fname)
            if not os.path.exists(csvp):
                with open(csvp, "w", encoding="utf-8") as f:
                    f.write("beer_name,brewery_name,beer_type,beer_abv,beer_ibu,rating_score\n")
            profs[fname] = display
            save_profiles(profs)
            session["profile_file"] = fname
            session["profile_name"] = display
            return redirect(url_for("menu"))
        else:
            sel = request.form.get("profile_file")
            if sel and sel in profs:
                session["profile_file"] = sel
                session["profile_name"] = profs[sel]
                return redirect(url_for("menu"))
            flash("Select a profile.", "error")
    return render_template("home.html", profiles=load_profiles())

@app.route("/menu")
def menu():
    if "profile_file" not in session:
        return redirect(url_for("home"))
    return render_template("menu.html", profile_name=session["profile_name"])

@app.route("/add-beer", methods=["GET","POST"])
def add_beer():
    if "profile_file" not in session: 
        return redirect(url_for("home"))
    if request.method == "POST":
        row = {k:(request.form.get(k) or "").strip() for k in
               ["beer_name","brewery_name","beer_type","beer_abv","beer_ibu","rating_score"]}
        if not row["beer_name"] or not row["brewery_name"]:
            flash("Beer name and brewery required.", "error")
        else:
            csvp = data_path(session["profile_file"])
            need_header = not os.path.exists(csvp) or os.path.getsize(csvp)==0
            with open(csvp, "a", encoding="utf-8") as f:
                if need_header:
                    f.write("beer_name,brewery_name,beer_type,beer_abv,beer_ibu,rating_score\n")
                f.write(",".join([row["beer_name"],row["brewery_name"],row["beer_type"],
                                  row["beer_abv"],row["beer_ibu"],row["rating_score"]])+"\n")
            flash("Beer added.", "ok")
            return redirect(url_for("add_beer"))
    return render_template("add_beer.html")

@app.route("/breweries", methods=["GET","POST"])
def breweries():
    if "profile_file" not in session: 
        return redirect(url_for("home"))
    results, form = None, {"city":"", "state":""}
    if request.method == "POST":
        form["city"] = (request.form.get("city") or "").strip()
        abbr = (request.form.get("state") or "").strip().upper()
        states = {"NE":"Nebraska","CO":"Colorado","CA":"California","NY":"New York","TX":"Texas"}  # add more or use the longer dict
        state = states.get(abbr, "")
        if not form["city"] or not state:
            flash("Enter a city and valid 2-letter state.", "error")
        else:
            try:
                df = pd.read_csv(data_path("breweries.csv"), dtype=str, low_memory=False)
                m = (df["city"].str.lower()==form["city"].lower()) & (df["state_province"].str.lower()==state.lower())
                take = df.loc[m, ["name","brewery_type","website_url","address_1","postal_code"]].fillna("")
                results = take.to_dict(orient="records")
            except Exception as e:
                flash(f"Could not read breweries.csv: {e}", "error")
    return render_template("breweries.html", results=results, form=form)

@app.route("/beer-search", methods=["GET","POST"])
def beer_search():
    if "profile_file" not in session: 
        return redirect(url_for("home"))
    matches, term = [], ""
    if request.method == "POST":
        term = (request.form.get("term") or "").strip()
        try:
            with open(data_path("beer_cache.json"), "r", encoding="utf-8") as f:
                beer_list = json.load(f)
            names = [(b.get("nameDisplay") or b.get("name") or "") for b in beer_list]
            from difflib import get_close_matches
            close = set(get_close_matches(term, names, n=20, cutoff=0.5))
            for b in beer_list:
                nm = b.get("nameDisplay") or b.get("name") or ""
                if nm in close:
                    matches.append({
                        "name": nm,
                        "style": (b.get("style") or {}).get("name","") if isinstance(b.get("style"), dict) else "",
                        "abv": b.get("abv",""),
                        "ibu": b.get("ibu",""),
                        "desc": (b.get("description") or "")[:300]
                    })
        except Exception as e:
            flash(f"beer_cache.json missing or unreadable: {e}", "error")
    return render_template("beer_search.html", matches=matches, term=term)

@app.route("/analytics")
def analytics():
    if "profile_file" not in session: 
        return redirect(url_for("home"))
    csv_candidates = [data_path("user.csv"), data_path(session["profile_file"])]
    csvp = next((p for p in csv_candidates if os.path.exists(p)), None)
    if not csvp:
        flash("No CSV found. Add beers first.", "error")
        return redirect(url_for("menu"))
    try:
        df = pd.read_csv(csvp)
    except Exception as e:
        flash(f"Could not read CSV: {e}", "error")
        return redirect(url_for("menu"))
    want = ["beer_name","brewery_name","beer_type","beer_abv","beer_ibu","rating_score"]
    mapping = {}
    for c in df.columns:
        key = c.replace(" ", "").lower()
        if key in want:
            mapping[c] = key
    df = df.rename(columns=mapping)
    for col in ["beer_abv","beer_ibu","rating_score"]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")
    kpis = {
        "total": len(df),
        "avg_abv": float(df["beer_abv"].mean()) if "beer_abv" in df.columns else None,
        "avg_ibu": float(df["beer_ibu"].mean()) if "beer_ibu" in df.columns else None,
        "avg_rating": float(df["rating_score"].mean()) if "rating_score" in df.columns else None,
    }
    outdir = os.path.join(ROOT, "static", "analytics")
    os.makedirs(outdir, exist_ok=True)
    charts = []
    def save_fig(fig, name):
        p = os.path.join(outdir, name)
        fig.savefig(p, bbox_inches="tight")
        plt.close(fig)
        return f"analytics/{name}"
    if "rating_score" in df.columns and df["rating_score"].notna().any():
        fig = plt.figure()
        df["rating_score"].dropna().plot(kind="hist", bins=10, title="Ratings Distribution")
        plt.xlabel("Rating"); plt.ylabel("Count")
        charts.append(("Ratings Distribution", save_fig(fig, "ratings_hist.png")))
    if "beer_abv" in df.columns and df["beer_abv"].notna().any():
        fig = plt.figure()
        df["beer_abv"].dropna().plot(kind="hist", bins=12, title="ABV Distribution")
        plt.xlabel("ABV %"); plt.ylabel("Count")
        charts.append(("ABV Distribution", save_fig(fig, "abv_hist.png")))
    if "beer_type" in df.columns and df["beer_type"].notna().any():
        ts = df["beer_type"].dropna().value_counts().head(10).sort_values(ascending=True)
        if not ts.empty:
            fig = plt.figure()
            ts.plot(kind="barh", title="Top Styles")
            plt.xlabel("Count"); plt.ylabel("Style")
            charts.append(("Top Styles", save_fig(fig, "styles_top.png")))
    if all(c in df.columns for c in ["beer_ibu","rating_score"]) and df[["beer_ibu","rating_score"]].dropna().shape[0] > 0:
        fig = plt.figure()
        tmp = df[["beer_ibu","rating_score"]].dropna()
        plt.scatter(tmp["beer_ibu"], tmp["rating_score"])
        plt.title("IBU vs Rating"); plt.xlabel("IBU"); plt.ylabel("Rating")
        charts.append(("IBU vs Rating", save_fig(fig, "ibu_vs_rating.png")))
    if all(c in df.columns for c in ["beer_abv","rating_score"]) and df[["beer_abv","rating_score"]].dropna().shape[0] > 0:
        fig = plt.figure()
        tmp = df[["beer_abv","rating_score"]].dropna()
        plt.scatter(tmp["beer_abv"], tmp["rating_score"])
        plt.title("ABV vs Rating"); plt.xlabel("ABV %"); plt.ylabel("Rating")
        charts.append(("ABV vs Rating", save_fig(fig, "abv_vs_rating.png")))
    return render_template("analytics.html", charts=charts, kpis=kpis, csv=os.path.basename(csvp))

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
