from __future__ import annotations
import csv, json, statistics, re
from pathlib import Path
from typing import Dict, Any, List

# Columns expected from Untappd export (header names may vary slightly; normalize below)
EXPECTED = {
    'beer_name':'beer_name',
    'brewery_name':'brewery_name',
    'beer_type':'beer_type',
    'beer_abv':'beer_abv',
    'beer_ibu':'beer_ibu',
    'rating_score':'rating_score',
    'global_rating_score':'global_rating_score'
}

def _norm_header(h: str) -> str:
    return re.sub(r'\s+', '_', h.strip().lower())

def load_untappd_csv(fp: Path) -> List[Dict[str,str]]:
    txt = fp.read_text(encoding='utf-8', errors='replace')
    # Handle both comma and semicolon CSV by sniffing
    dialect = csv.Sniffer().sniff(txt.splitlines()[0])
    reader = csv.DictReader(txt.splitlines(), dialect=dialect)
    rows = []
    for r in reader:
        rr = {_norm_header(k): v for k,v in r.items()}
        rows.append(rr)
    return rows

def build_profile(rows: List[Dict[str,str]], display_name: str) -> Dict[str,Any]:
    styles = {}
    breweries = {}
    abvs = []
    ibus = []
    deltas = []  # rating - global_rating

    for r in rows:
        bt = r.get('beer_type') or r.get('beer_style') or ''
        bname = r.get('brewery_name','')
        g = r.get('global_rating_score') or r.get('global_weighted_rating_score') or ''
        rs = r.get('rating_score') or ''
        abv = r.get('beer_abv') or ''
        ibu = r.get('beer_ibu') or ''

        if bt:
            styles.setdefault(bt, {'count':0, 'ratings':[]})
            styles[bt]['count'] += 1
            try:
                styles[bt]['ratings'].append(float(rs))
            except: pass

        if bname:
            breweries[bname] = breweries.get(bname, 0) + 1

        try:
            abvs.append(float(abv))
        except: pass
        try:
            ibus.append(float(ibu))
        except: pass
        try:
            deltas.append(float(rs) - float(g))
        except: pass

    # Top-5 styles by count
    top_styles = sorted(
        [{'style':k, 'count':v['count'], 'avg_rating': (sum(v['ratings'])/len(v['ratings'])) if v['ratings'] else None} for k,v in styles.items()],
        key=lambda x: x['count'], reverse=True
    )[:5]

    top_breweries = sorted(breweries.items(), key=lambda kv: kv[1], reverse=True)[:5]

    profile = {
        'name': display_name,
        'summary': {
            'total_checkins': len(rows),
            'abv_median': statistics.median(abvs) if abvs else None,
            'ibu_median': statistics.median(ibus) if ibus else None,
            'rating_minus_global_avg': (sum(deltas)/len(deltas)) if deltas else None
        },
        'top_styles': top_styles,
        'top_breweries': [{'brewery': k, 'count': v} for k,v in top_breweries]
    }
    return profile

def score_beer(beer: Dict[str,Any], profile: Dict[str,Any]) -> float:
    """Return a 0..1 score combining style affinity and ABV/IBU proximity to medians."""
    style = (beer.get('style') or '').strip()
    abv = beer.get('abv')
    ibu = beer.get('ibu')
    s = 0.0
    # Style weight
    tops = [t['style'] for t in profile.get('top_styles',[])]
    if style:
        # partial contains match
        if any(style.lower() in t.lower() or t.lower() in style.lower() for t in tops):
            s += 0.6
    # ABV/IBU closeness
    abv_med = profile.get('summary',{}).get('abv_median')
    ibu_med = profile.get('summary',{}).get('ibu_median')
    if isinstance(abv, (int,float)) and isinstance(abv_med, (int,float)):
        # within 1.5% is good, fall off to 0 at 6%
        diff = abs(abv - abv_med)
        s += max(0.0, 0.25 * (1 - min(diff/6.0, 1.0)))
    if isinstance(ibu, (int,float)) and isinstance(ibu_med, (int,float)):
        diff = abs(ibu - ibu_med)
        s += max(0.0, 0.15 * (1 - min(diff/30.0, 1.0)))
    return min(1.0, s)
