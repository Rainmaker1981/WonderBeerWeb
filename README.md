# WonderBeerDemo

A portfolio-friendly Flask demo that:
1) Ingests your Untappd CSV and builds a profile JSON used for analytics.
2) Lets you find breweries via Country → State/Province → City → Venue dropdowns.
3) Fetches a brewery menu (from Untappd when available, with a local fallback) and computes “match %” vs your profile.
4) Looks up beers from a local `beer_cache.json`, and if missing, attempts a live fetch.

## Quickstart (local)

```bash
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -r requirements.txt
export FLASK_APP=app.py    # Windows PowerShell: $env:FLASK_APP="app.py"
flask run
```

Open http://127.0.0.1:5000/

## Deploy (Render)
- Set **Start Command**: `gunicorn app:app --bind 0.0.0.0:$PORT`
- Ensure build has Python 3.12+ and installs `requirements.txt`.
- Make sure `data/` is committed so the app has CSVs/JSONs at boot.

## Data
- `data/breweries.csv` — sample cascading dataset with Country/State/City/Venue (Name).
- `data/beer_cache.json` — sample beer info cache by beer name.
- `data/profiles/` — holds generated profile JSONs (from Untappd CSV uploads).

## Pages
- **/** Home: guided flow.
- **/profile**: upload Untappd CSV, enter your name → builds `<name>.json`.
- **/finder**: country/state/city/venue dropdowns (prefilled from `breweries.csv`).
- **/match**: uses selected venue & chosen profile to compute matches from a live Untappd menu (with fallback sample).
- **/lookup**: shows details for a beer from `beer_cache.json` (with optional live fetch).

## Notes
- Live Untappd fetching is best-effort HTML parsing and may change if their markup changes.
- If a venue has no Untappd menu URL, the demo uses a local sample menu in `data/menus/`.
