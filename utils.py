import csv, json
from collections import Counter
from typing import Dict, Any, List

def parse_untappd_csv(csv_file, display_name:str) -> Dict[str, Any]:
    reader = csv.DictReader((line.replace('\ufeff','') for line in csv_file))
    needed = {"beer_name","brewery_name","beer_type","beer_abv","beer_ibu","rating_score","global_rating_score"}
    missing = [c for c in needed if c not in reader.fieldnames]
    if missing:
        raise ValueError(f"CSV missing required columns: {missing}. Got: {reader.fieldnames}")

    styles, breweries = Counter(), Counter()
    abv_values: List[float] = []
    ibu_values: List[float] = []
    rating_values: List[float] = []
    deltas: List[float] = []
    samples: List[Dict[str, Any]] = []

    def to_float(x):
        try: return float(x)
        except: return None

    for row in reader:
        style = (row.get("beer_type") or "").strip()
        styles[style] += 1
        breweries[(row.get("brewery_name") or "").strip()] += 1

        abv = to_float(row.get("beer_abv"))
        ibu = to_float(row.get("beer_ibu"))
        rating = to_float(row.get("rating_score"))
        global_rating = to_float(row.get("global_rating_score"))

        if abv is not None: abv_values.append(abv)
        if ibu is not None: ibu_values.append(ibu)
        if rating is not None: rating_values.append(rating)
        if rating is not None and global_rating is not None:
            deltas.append(rating - global_rating)

        if len(samples) < 30:
            samples.append({
                "beer_name": row.get("beer_name",""),
                "brewery_name": row.get("brewery_name",""),
                "beer_type": style,
                "beer_abv": abv,
                "beer_ibu": ibu,
                "rating_score": rating,
                "global_rating_score": global_rating,
            })

    def top_n(counter: Counter, n=5):
        return [{"label": k, "count": int(v)} for k, v in counter.most_common(n)]

    profile = {
        "name": display_name,
        "summary": {
            "total_checkins": sum(styles.values()),
            "avg_abv": round(sum(abv_values)/len(abv_values),2) if abv_values else None,
            "avg_ibu": round(sum(ibu_values)/len(ibu_values),1) if ibu_values else None,
            "avg_rating": round(sum(rating_values)/len(rating_values),2) if rating_values else None,
            "avg_rating_delta": round(sum(deltas)/len(deltas),3) if deltas else None,
        },
        "top_styles": top_n(styles, 5),
        "top_breweries": top_n(breweries, 5),
        "samples": samples,
    }
    return profile

def compute_match_score(profile:Dict[str,Any], beer:Dict[str,Any]) -> float:
    style = (beer.get("beer_type") or "").lower()
    abv = beer.get("beer_abv")
    ibu = beer.get("beer_ibu")

    # Style weight from profile
    style_weight = 0.0
    top_styles = profile.get("top_styles",[])
    if style:
        for i, s in enumerate(top_styles):
            label = (s.get("label") or "").lower()
            if label and label in style:
                style_weight = max(style_weight, (len(top_styles) - i) / len(top_styles))

    avg_abv = (profile.get("summary") or {}).get("avg_abv")
    avg_ibu = (profile.get("summary") or {}).get("avg_ibu")
    abv_score = 0.0
    ibu_score = 0.0
    try:
        if abv is not None and avg_abv is not None:
            abv_score = max(0.0, 1.0 - abs(float(abv) - float(avg_abv)) / 6.0)
    except: pass
    try:
        if ibu is not None and avg_ibu is not None:
            ibu_score = max(0.0, 1.0 - abs(float(ibu) - float(avg_ibu)) / 40.0)
    except: pass

    bias = (profile.get("summary") or {}).get("avg_rating_delta") or 0.0
    bias_norm = max(0.0, min(1.0, 0.5 + bias))

    score = 0.5*style_weight + 0.25*abv_score + 0.2*ibu_score + 0.05*bias_norm
    return round(100*score, 1)
