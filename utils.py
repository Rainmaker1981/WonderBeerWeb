import csv
import json
from collections import Counter, defaultdict
from statistics import mean
from typing import Dict, Any, List, Optional

def parse_untappd_csv(file_obj, display_name: str) -> Dict[str, Any]:
    file_obj.seek(0)
    reader = csv.DictReader((line.decode("utf-8") if isinstance(line, bytes) else line for line in file_obj))
    styles = Counter(); abvs=[]; ibus=[]; breweries=Counter(); ratings=[]; global_ratings=[]
    for row in reader:
        bt = (row.get("beer_type") or "").strip()
        if bt: styles[bt]+=1
        try:
            abv = float(row.get("beer_abv") or 0); 
            if abv>0: abvs.append(abv)
        except: pass
        try:
            ibu = float(row.get("beer_ibu") or 0); 
            if ibu>0: ibus.append(ibu)
        except: pass
        bname = (row.get("brewery_name") or "").strip()
        if bname: breweries[bname]+=1
        try:
            r = float(row.get("rating_score") or 0); 
            if r>0: ratings.append(r)
        except: pass
        try:
            gr = float(row.get("global_rating_score") or 0); 
            if gr>0: global_ratings.append(gr)
        except: pass
    top_styles = [{"style": s, "count": c} for s,c in styles.most_common(5)]
    top_breweries = [{"brewery": b, "count": c} for b,c in breweries.most_common(5)]
    return {
        "name": display_name,
        "styles": {ts["style"]: ts["count"] for ts in top_styles},
        "stats": {
            "abv_mean": round(mean(abvs),2) if abvs else None,
            "ibu_mean": round(mean(ibus),1) if ibus else None,
            "user_rating_mean": round(mean(ratings),2) if ratings else None,
            "global_rating_mean": round(mean(global_ratings),2) if global_ratings else None,
        },
        "top_breweries": top_breweries
    }

def compute_match_score(profile: Dict[str, Any], beer: Dict[str, Any], beer_cache_lookup: Optional[Dict[str, Any]] = None) -> float:
    score=0.0
    styles = profile.get("styles", {})
    stats = profile.get("stats", {})
    style = (beer.get("style") or "").strip()
    abv = beer.get("abv"); ibu = beer.get("ibu")
    global_rating=None
    if beer_cache_lookup:
        bname = (beer.get("name") or "").strip().lower()
        cache = beer_cache_lookup.get(bname)
        if isinstance(cache, dict):
            gr = cache.get("global_rating") or cache.get("global_rating_score")
            try: global_rating=float(gr)
            except: pass
    if style and style in styles:
        score += 10.0 + styles[style]
    if isinstance(abv,(int,float)) and stats.get("abv_mean"):
        score += max(0, 5.0 - abs(abv - stats["abv_mean"]))
    if isinstance(ibu,(int,float)) and stats.get("ibu_mean"):
        score += max(0, 5.0 - abs(ibu - stats["ibu_mean"])/5.0)
    if global_rating and global_rating>=3.5:
        score += (global_rating - 3.5)*2.0
    return round(score,2)

def build_breweries_cache(rows: List[Dict[str, str]]) -> Dict[str, Any]:
    from collections import defaultdict
    tree = defaultdict(lambda: defaultdict(lambda: defaultdict(list)))
    for r in rows:
        country = (r.get("country") or "").strip() or "Unknown"
        state = (r.get("state_province") or "").strip()
        city = (r.get("city") or "").strip()
        name = (r.get("name") or "").strip()
        website = (r.get("website_url") or "").strip()
        lon = r.get("longitude"); lat = r.get("latitude")
        try: lon = float(lon) if lon not in (None,"","null") else None
        except: lon=None
        try: lat = float(lat) if lat not in (None,"","null") else None
        except: lat=None
        if not (name and city and country): 
            continue
        tree[country][state][city].append({"name":name,"website_url":website or None,"longitude":lon,"latitude":lat})
    return tree
