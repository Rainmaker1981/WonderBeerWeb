# wonderBEER web (v2) — guided flow + profiles + analytics + 3-dropdown finder
import os
from pathlib import Path
from flask import Flask, render_template, request, jsonify, redirect, url_for, flash, send_from_directory
import csv, json

def create_app():
    app = Flask(__name__)
    app.secret_key = os.getenv("SECRET_KEY", "dev-secret")

    BASE_DIR = Path(__file__).resolve().parent
    DATA_DIR = BASE_DIR / "data"
    PROFILES_DIR = DATA_DIR / "profiles"

    BREWERIES_CSV = Path(os.getenv("BREWERIES_CSV", str(DATA_DIR / "breweries.csv")))

    _breweries_index = None

    def load_breweries_index():
        nonlocal _breweries_index
        if _breweries_index is not None:
            return _breweries_index

        states = []
        cities = {}
        venues = {}

        if not BREWERIES_CSV.exists():
            app.logger.warning(f"breweries.csv not found at {BREWERIES_CSV}")
            _breweries_index = {"states": [], "cities": {}, "venues": {}}
            return _breweries_index

        with BREWERIES_CSV.open(newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                name = (row.get("Name") or "").strip()
                city = (row.get("City") or "").strip()
                state = (row.get("State_province") or "").strip()
                if not (name and city and state):
                    continue
                if state not in states:
                    states.append(state)
                cities.setdefault(state, set()).add(city)
                venues.setdefault((state, city), []).append(name)

        states.sort()
        cities_sorted = {st: sorted(list(cset)) for st, cset in cities.items()}
        venues_sorted = {f"{st}||{cty}": sorted(list(set(vlist))) for (st, cty), vlist in venues.items()}
        _breweries_index = {"states": states, "cities": cities_sorted, "venues": venues_sorted}
        return _breweries_index

    @app.route("/")
    def index():
        return render_template("index.html")

    @app.route("/profiles", methods=["GET", "POST"])
    def profiles():
        PROFILES_DIR.mkdir(parents=True, exist_ok=True)
        if request.method == "POST":
            file = request.files.get("profile")
            if not file or file.filename == "":
                flash("No profile file selected.", "error")
                return redirect(url_for("profiles"))
            try:
                data = json.load(file.stream)
                name = (data.get("name") or "profile").strip()
                safe = "".join(c for c in name if c.isalnum() or c in ("_", "-", "."))
                if not safe:
                    safe = "profile"
                out = PROFILES_DIR / f"{safe}.json"
                with out.open("w", encoding="utf-8") as fp:
                    json.dump(data, fp, ensure_ascii=False, indent=2)
                flash(f"Uploaded {out.name}", "ok")
            except Exception as e:
                app.logger.exception("Profile upload failed")
                flash(f"Upload failed: {e}", "error")
            return redirect(url_for("profiles"))

        existing = sorted([p.name for p in PROFILES_DIR.glob("*.json")])
        if (DATA_DIR / "sample_profile.json").exists():
            existing = ["sample_profile.json"] + existing
        return render_template("profiles.html", files=existing)

    @app.route("/profiles/download/<name>")
    def download_profile(name):
        path = (PROFILES_DIR / name) if not name.startswith("sample_") else (DATA_DIR / name)
        if not path.exists():
            flash("Profile not found.", "error")
            return redirect(url_for("profiles"))
        return send_from_directory(path.parent, path.name, as_attachment=True)

    @app.route("/finder")
    def finder():
        return render_template("select_venue.html")

    @app.route("/api/breweries_index")
    def api_breweries_index():
        idx = load_breweries_index()
        return jsonify(idx)

    @app.route("/analytics")
    def analytics():
        profile_name = request.args.get("profile", "sample_profile.json")
        path = (PROFILES_DIR / profile_name) if not profile_name.startswith("sample_") else (DATA_DIR / profile_name)
        if not path.exists():
            path = DATA_DIR / "sample_profile.json"
        try:
            with path.open(encoding="utf-8") as f:
                prof = json.load(f)
        except Exception:
            prof = {"name":"Sample","styles":{"IPA":3,"Stout":2,"Lager":4},"flavors":{"Hoppy":4,"Roasty":2,"Crisp":3}}
        return render_template("analytics.html", profile=prof, profile_name=path.name)

    return app

app = create_app()
