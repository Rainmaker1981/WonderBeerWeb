# WonderBEER (Flask demo)

A local Flask demo for your WonderBEER web app vision. It supports:
- Uploading a taste profile CSV (user + global preferences with weights)
- Searching sample breweries (local CSV)
- Viewing a sample menu for a brewery
- Matching beers using a weighted score: `score = user_pref * mean(user_weight) + (global_rating_norm) * mean(global_weight)`

## Quickstart

```bash
cd wonderbeer_web
python -m venv .venv
# Windows:
.venv\Scripts\activate
# macOS/Linux:
source .venv/bin/activate

pip install -r requirements.txt
python app.py
```

Then open http://127.0.0.1:5000

## Files

- `app.py` — Flask server and routes
- `templates/` — Jinja templates (base, index, profile, breweries, match)
- `static/styles.css` — Light, modern UI
- `data/breweries_sample.csv` — Local fallback list of breweries
- `data/sample_menu.csv` — Sample beer menus keyed by `brewery_id`
- `data/sample_profile.csv` — Example profile for testing
- `uploads/profile.csv` — Your active profile after upload

## Your Profile CSV

Expected columns:
- `style` — e.g., "American IPA", "Pilsner"
- `user_rating` — your taste (0–5)
- `global_rating` — optional average rating (0–5)
- `user_weight` — weight to apply to your rating (e.g., 1.0)
- `global_weight` — weight to apply to global rating (e.g., 0.6)

You can download the sample from **Profile → Download Sample** in the app.

## Extend Next

- Replace sample data with real brewery sources (OpenBreweryDB CSV) and real menus.
- Add scraping/parsing module for brewery menus (Untappd or on‑site pages) — store beers by `brewery_id`.
- Persist user sessions and multiple profiles.
- Add geosearch for "near me" using city/state/ZIP.
- Improve scoring (include ABV/IBU ranges, seasonal preference, time‑of‑day mood sliders).
- Export results as CSV or shareable link.
