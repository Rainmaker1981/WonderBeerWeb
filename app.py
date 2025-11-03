import csv, re
from collections import defaultdict
from flask import Flask, jsonify, request

app = Flask(__name__)

BREWERIES = []
BY_STATE = defaultdict(list)
BY_STATE_CITY = defaultdict(lambda: defaultdict(list))

def _norm_space(s): return re.sub(r"\s+", " ", (s or "")).strip()

def _norm_city(s):
    s = _norm_space(s)
    return s.title()

def _norm_state_province(s):
    s = _norm_space(s)
    return s if (len(s) <= 3 and s.isupper()) else s.title()

def load_breweries(csv_path="breweries.csv"):
    BREWERIES.clear(); BY_STATE.clear(); BY_STATE_CITY.clear()
    with open(csv_path, newline="", encoding="utf-8") as f:
        r = csv.DictReader(f)
        for row in r:
            name = _norm_space(row.get("Name", ""))
            city = _norm_city(row.get("City", ""))
            statep = _norm_state_province(row.get("State_province", ""))
            if not (name and city and statep):
                continue
            rec = {"Name": name, "City": city, "State_province": statep}
            BREWERIES.append(rec)
            BY_STATE[statep].append(rec)
            BY_STATE_CITY[statep][city].append(rec)

load_breweries()

@app.get("/api/states")
def api_states():
    states = sorted([s for s in BY_STATE.keys() if s])
    return jsonify(states=states)

@app.get("/api/cities")
def api_cities():
    statep = _norm_state_province(request.args.get("state_province", ""))
    if not statep or statep not in BY_STATE_CITY:
        return jsonify(cities=[])
    cities = sorted(BY_STATE_CITY[statep].keys())
    return jsonify(cities=cities)

@app.get("/api/venues")
def api_venues():
    statep = _norm_state_province(request.args.get("state_province", ""))
    city   = _norm_city(request.args.get("city", ""))
    if not statep or statep not in BY_STATE_CITY or not city:
        return jsonify(venues=[])
    items = BY_STATE_CITY[statep].get(city, [])
    venues = [{
        "Name": b["Name"],
        "City": b["City"],
        "State_province": b["State_province"],
    } for b in sorted(items, key=lambda x: x["Name"].lower())]
    return jsonify(venues=venues)
