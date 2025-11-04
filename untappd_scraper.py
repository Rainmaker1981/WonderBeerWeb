from typing import List, Dict, Any
import requests
from bs4 import BeautifulSoup
import re

def fetch_untappd_menu(venue_url:str) -> List[Dict[str,Any]]:
    try:
        r = requests.get(venue_url, timeout=15)
        r.raise_for_status()
    except Exception:
        return []

    soup = BeautifulSoup(r.text, "html.parser")
    beers = []
    for li in soup.select("li.menu-item"):
        name = (li.select_one(".name") or li.select_one(".beer-name") or li.find("h3"))
        style = (li.select_one(".style") or li.select_one(".beer-style"))
        abv = (li.select_one(".abv") or li.find(string=lambda x: x and "ABV" in x))
        ibu = (li.select_one(".ibu") or li.find(string=lambda x: x and "IBU" in x))

        rec = {
            "beer_name": name.get_text(strip=True) if name else None,
            "beer_type": style.get_text(strip=True) if style else None,
            "beer_abv": None,
            "beer_ibu": None,
        }
        if abv:
            m = re.search(r"(\d+(?:\.\d+)?)\s*%\s*ABV", str(abv))
            if m: rec["beer_abv"] = float(m.group(1))
        if ibu:
            m = re.search(r"(\d+)\s*IBU", str(ibu))
            if m: rec["beer_ibu"] = float(m.group(1))
        if rec["beer_name"]:
            beers.append(rec)
    return beers
