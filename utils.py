# utils.py
import io, csv, json, statistics

UNTAPPD_FIELDS = {
    "beer_name","brewery_name","beer_type","beer_abv","beer_ibu",
    "rating_score","global_rating_score","brewery_city","brewery_state"
}

def _text_from_filestorage(fs) -> str:
    """Return text from a Flask FileStorage or file-like/path."""
    # 1) get raw bytes
    if hasattr(fs, "read"):            # FileStorage or file-like
        data = fs.read()
    elif hasattr(fs, "stream"):        # sometimes .stream exists
        data = fs.stream.read()
    elif isinstance(fs, (bytes, bytearray)):
        data = bytes(fs)
    elif isinstance(fs, str):
        # path on disk
        with open(fs, "rb") as f:
            data = f.read()
    else:
        raise TypeError("Unsupported file object")

    # If we were given text already, convert to bytes first
    if isinstance(data, str):
        data = data.encode("utf-8", "ignore")

    # 2) decode to text (handle BOM + fallbacks)
    try:
        return data.decode("utf-8-sig")
    except UnicodeDecodeError:
        return data.decode("latin-1", errors="ignore")

def iter_untappd_rows(file_obj):
    """Yield DictReader rows from Untappd export regardless of upload mode."""
    text = _text_from_filestorage(file_obj)
    sio = io.StringIO(text, newline="")  # csv needs text stream
    reader = csv.DictReader(sio)
    yield from reader

def build_profile_from_untappd(file_obj, display_name: str) -> dict:
    # Parse rows
    rows = list(iter_untappd_rows(file_obj))

    # Extract analytics
    import collections
    styles = collections.Counter()
    breweries = collections.Counter()
    abvs, ibus, ratings, global_ratings = [], [], [], []

    for r in rows:
        bt = (r.get("beer_type") or "").strip()
        if bt: styles[bt] += 1

        bn = (r.get("brewery_name") or "").strip()
        if bn: breweries[bn] += 1

        # numeric fields
        def f(x):
            try: return float(str(x).strip())
            except: return None

        a = f(r.get("beer_abv"))
        i = f(r.get("beer_ibu"))
        rs = f(r.get("rating_score"))
        gr = f(r.get("global_rating_score"))

        if a is not None: abvs.append(a)
        if i is not None: ibus.append(i)
        if rs is not None: ratings.append(rs)
        if gr is not None: global_ratings.append(gr)

    def avg(lst): 
        return round(statistics.fmean(lst), 2) if lst else None

    profile = {
        "name": display_name.strip() or "Unnamed",
        "summary": {
            "avg_abv": avg(abvs),
            "avg_ibu": avg(ibus),
            "avg_rating": avg(ratings),
            "avg_global_rating": avg(global_ratings),
            "top_styles": styles.most_common(5),
            "top_breweries": breweries.most_common(5),
            "total_checkins": len(rows),
        },
    }
    return profile

def save_profile_json(profile: dict, path: str):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(profile, f, ensure_ascii=False, indent=2)
