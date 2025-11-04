# WonderBeerWeb (Portfolio Demo)

A three-step demo:
1) **Upload Profile**: Import your Untappd CSV and generate a tasting profile.
2) **Find Breweries**: Filter by Country → State/Province → City → Venue using `breweries.csv`.
3) **Match Beers**: Pull a venue's Untappd menu and score matches to your profile.
4) **Beer Lookup**: Look up beers via local `beer_cache.json`, or attempt Untappd fetch.

## Run locally
```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
export FLASK_ENV=development
python app.py
# or
gunicorn app:app --bind 0.0.0.0:8000
```

## Required data files
- Place a current **breweries.csv** into `data/breweries.csv`. The app will auto-create `data/breweries_cache.json` on first request.
  Kept columns: name, city, state_province, country, website_url, longitude, latitude
- Optional **beer_cache.json** into `data/beer_cache.json`.
- Uploaded profiles are saved to `data/profiles/<Your_Name>.json`.

## Render
- Uses `render.yaml` with Gunicorn start command.
