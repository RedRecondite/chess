"""Downloads (road extracts, boundaries, lakes, fonts) and place-name lookup, all cached under the data folder."""
import json
import shutil
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

UA = "travel-time-poster/1.0 (personal map project)"

GEOFABRIK = "https://download.geofabrik.de/"
REGION_PATHS = {
    "michigan": "north-america/us/michigan", "wisconsin": "north-america/us/wisconsin",
    "illinois": "north-america/us/illinois", "indiana": "north-america/us/indiana",
    "ohio": "north-america/us/ohio", "minnesota": "north-america/us/minnesota",
    "pennsylvania": "north-america/us/pennsylvania", "new-york": "north-america/us/new-york",
    "ontario": "north-america/canada/ontario",
}
CENSUS_STATES = "https://www2.census.gov/geo/tiger/GENZ2023/shp/cb_2023_us_state_500k.zip"
NE = "https://naciscdn.org/naturalearth/10m/"
NE_LAKES = [NE + "physical/ne_10m_lakes.zip", NE + "physical/ne_10m_lakes_north_america.zip"]
NE_ADMIN1 = NE + "cultural/ne_10m_admin_1_states_provinces.zip"
FONT_BASE = "https://raw.githubusercontent.com/google/fonts/main/ofl/"
FONTS = {
    "BarlowCondensed-SemiBold.ttf": "barlowcondensed/BarlowCondensed-SemiBold.ttf",
    "BarlowCondensed-Medium.ttf": "barlowcondensed/BarlowCondensed-Medium.ttf",
    "Barlow-Regular.ttf": "barlow/Barlow-Regular.ttf",
    "Barlow-Medium.ttf": "barlow/Barlow-Medium.ttf",
    "Barlow-SemiBold.ttf": "barlow/Barlow-SemiBold.ttf",
}


def log(msg):
    print(msg, flush=True)


def download(url, dest, quiet=False):
    dest = Path(dest)
    if dest.exists() and dest.stat().st_size > 0:
        return dest
    dest.parent.mkdir(parents=True, exist_ok=True)
    part = dest.with_suffix(dest.suffix + ".part")
    if not quiet:
        log(f"Downloading {url}")
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=120) as r, open(part, "wb") as f:
        total = int(r.headers.get("Content-Length") or 0)
        got, last, shown = 0, 0.0, False
        while True:
            chunk = r.read(1 << 20)
            if not chunk:
                break
            f.write(chunk)
            got += len(chunk)
            if not quiet and time.time() - last > 2:
                last = time.time()
                pct = f" ({got * 100 // total}%)" if total else ""
                sys.stdout.write(f"\r  {got / 1e6:,.0f} MB{pct}   ")
                sys.stdout.flush()
                shown = True
    if shown:
        sys.stdout.write("\n")
    shutil.move(part, dest)
    return dest


def region_pbf(name, data_dir):
    """A Geofabrik region name, a Geofabrik path like 'north-america/us/ohio', or a local file."""
    p = Path(name).expanduser()
    if p.suffix in (".pbf", ".osm") or name.endswith(".osm.pbf"):
        if not p.exists():
            raise SystemExit(f"Road file not found: {p}")
        return p
    key = name.lower().strip()
    path = REGION_PATHS.get(key, key if "/" in key else None)
    if not path:
        raise SystemExit(f"Unknown region {name!r}. Use one of {', '.join(REGION_PATHS)}, "
                         "a Geofabrik path such as 'north-america/us/kentucky', or a local .osm.pbf file.")
    fname = path.split("/")[-1] + "-latest.osm.pbf"
    return download(GEOFABRIK + path + "-latest.osm.pbf", Path(data_dir) / "osm" / fname)


def boundary_files(data_dir):
    d = Path(data_dir) / "boundaries"
    return {
        "states": download(CENSUS_STATES, d / Path(CENSUS_STATES).name),
        "lakes": [download(u, d / Path(u).name) for u in NE_LAKES],
        "admin1": download(NE_ADMIN1, d / Path(NE_ADMIN1).name),
    }


def fonts(data_dir):
    """Fetch the poster typefaces. Returns a list of font files (empty if offline)."""
    d = Path(data_dir) / "fonts"
    files = []
    for name, rel in FONTS.items():
        try:
            files.append(download(FONT_BASE + rel, d / name, quiet=True))
        except Exception as e:  # the poster still renders with the default font
            log(f"  (font {name} unavailable: {e})")
    return files


def geocode(query, data_dir):
    cache_f = Path(data_dir) / "places.json"
    cache = json.loads(cache_f.read_text()) if cache_f.exists() else {}
    if query in cache:
        return cache[query]
    url = "https://nominatim.openstreetmap.org/search?" + urllib.parse.urlencode(
        {"q": query, "format": "jsonv2", "limit": 1})
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=30) as r:
        res = json.load(r)
    time.sleep(1.1)  # Nominatim allows one request per second
    if not res:
        raise SystemExit(f"No place found for {query!r}. Try adding the state, or give [latitude, longitude].")
    hit = {"lat": float(res[0]["lat"]), "lon": float(res[0]["lon"]), "name": res[0].get("display_name", query)}
    cache[query] = hit
    cache_f.parent.mkdir(parents=True, exist_ok=True)
    cache_f.write_text(json.dumps(cache, indent=1))
    return hit


def resolve_starts(specs, label, data_dir):
    """Turn start specs into [(lat, lon)], the poster label, and a name for each start pin."""
    pts, names = [], []
    for s in specs:
        if isinstance(s, tuple):
            pts.append(s)
            names.append(f"{abs(s[0]):.3f}°{'N' if s[0] >= 0 else 'S'} {abs(s[1]):.3f}°{'E' if s[1] >= 0 else 'W'}")
        else:
            hit = geocode(s, data_dir)
            pts.append((hit["lat"], hit["lon"]))
            names.append(s.split(",")[0].strip())
    if not label:
        label = " & ".join(names) if len(names) <= 3 else f"{len(names)} Places"
    if len(pts) == 1:
        names = [label]
    return pts, label, names
