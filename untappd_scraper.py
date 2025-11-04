import re
import time
from typing import List, Dict, Optional
import requests
from bs4 import BeautifulSoup

UA = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36 WonderBeerDemo/1.0'

def _clean_text(s: Optional[str]) -> Optional[str]:
    if s is None: return None
    return re.sub(r'\s+', ' ', s).strip()

def parse_abv(text: str) -> Optional[float]:
    if not text: return None
    m = re.search(r'(\d+(?:\.\d+)?)\s*%\s*ABV', text, re.I)
    if m: return float(m.group(1))
    m2 = re.search(r'(\d+(?:\.\d+)?)\s*%', text)
    if m2: return float(m2.group(1))
    return None

def parse_ibu(text: str) -> Optional[int]:
    if not text: return None
    m = re.search(r'(\d+)\s*IBU', text, re.I)
    if m: return int(m.group(1))
    return None

def fetch_venue_menu(venue_url: str, timeout: int = 20) -> List[Dict]:
    """Fetch Untappd *venue* page and parse the on-site menu into a list of beers.
    Each item: {name, style, abv, ibu}
    """
    headers = {'User-Agent': UA, 'Accept-Language': 'en-US,en;q=0.9'}
    r = requests.get(venue_url, headers=headers, timeout=timeout)
    r.raise_for_status()
    soup = BeautifulSoup(r.text, 'lxml')

    results = []
    # Known structure: sections with ul.menu-section-list > li.menu-item
    for li in soup.select('ul.menu-section-list li.menu-item'):
        name = None; style = None; abv = None; ibu = None

        # Try common areas
        name_el = li.select_one('.beer-details .name, .beer-info .name, .beer-title, .beer-name, .name a')
        if name_el:
            name = _clean_text(name_el.get_text())

        # Style often nearby
        style_el = li.select_one('.beer-details .style, .beer-info .style, .style')
        if style_el:
            style = _clean_text(style_el.get_text())

        # ABV/IBU line often in the same block
        meta_el = li.select_one('.beer-details, .beer-info, .beer-meta')
        meta_txt = _clean_text(meta_el.get_text(' ')) if meta_el else ''
        abv = parse_abv(meta_txt)
        ibu = parse_ibu(meta_txt)

        # Fallback: scan whole li text
        if abv is None or ibu is None:
            li_txt = _clean_text(li.get_text(' '))
            if abv is None: abv = parse_abv(li_txt or '')
            if ibu is None: ibu = parse_ibu(li_txt or '')

        if name:
            results.append({
                'name': name,
                'style': style,
                'abv': abv,
                'ibu': ibu
            })
    return results
