import requests, re
from typing import List, Dict
from bs4 import BeautifulSoup

def fetch_venue_menu(venue_name: str, city: str, state: str, country: str) -> List[Dict]:
    query = " ".join([venue_name, city, state, country]).strip()
    if not query: return []
    search_url = "https://www.bing.com/search"
    try:
        resp = requests.get(search_url, params={"q": f"site:untappd.com {query}"}, timeout=10)
        resp.raise_for_status()
    except Exception:
        return []
    soup = BeautifulSoup(resp.text, "lxml")
    venue_link=None
    for a in soup.select("a"):
        href = a.get("href","")
        if "untappd.com/v/" in href:
            venue_link = href; break
    if not venue_link:
        return []
    try:
        v = requests.get(venue_link, timeout=12)
        v.raise_for_status()
    except Exception:
        return []
    vsoup = BeautifulSoup(v.text, "lxml")
    beers=[]
    for li in vsoup.select("li.menu-item, li[data-menu-item], div.menu-item"):
        name_el = li.select_one(".beer-name, .name, .beer, h4")
        name = name_el.get_text(strip=True) if name_el else None
        style_el = li.select_one(".style, .beer-style, .caps")
        style = style_el.get_text(strip=True) if style_el else None
        txt = li.get_text(" ", strip=True)
        abv = None; ibu=None
        mabv = re.search(r"(\\d+(?:\\.\\d+)?)\\s*%\\s*ABV", txt, re.I)
        if mabv:
            try: abv=float(mabv.group(1))
            except: pass
        mibu = re.search(r"(\\d+)\\s*IBU", txt, re.I)
        if mibu:
            try: ibu=float(mibu.group(1))
            except: pass
        if name:
            beers.append({"name":name,"style":style,"abv":abv,"ibu":ibu})
    if beers: return beers
    for row in vsoup.select("ul.menu-section-list li, div.beer-info"):
        txt = row.get_text(" ", strip=True)
        name=None
        name_el = row.select_one(".beer-name, .name, h4")
        if name_el: name=name_el.get_text(strip=True)
        else:
            tag=row.find(["strong","b"])
            name = tag.get_text(strip=True) if tag else None
        style=None
        for cls in (".style",".beer-style",".caps"):
            el=row.select_one(cls)
            if el: style = el.get_text(strip=True); break
        abv=None; ibu=None
        mabv = re.search(r"(\\d+(?:\\.\\d+)?)\\s*%\\s*ABV", txt, re.I)
        if mabv:
            try: abv=float(mabv.group(1))
            except: pass
        mibu = re.search(r"(\\d+)\\s*IBU", txt, re.I)
        if mibu:
            try: ibu=float(mibu.group(1))
            except: pass
        if name:
            beers.append({"name":name,"style":style,"abv":abv,"ibu":ibu})
    return beers
