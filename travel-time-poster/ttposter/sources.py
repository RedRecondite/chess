"""Downloads (road extracts, boundaries, lakes, fonts) and place-name lookup, all cached under the data folder."""
import json
import re
import shutil
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

UA = "travel-time-poster/1.0 (personal map project)"

GEOFABRIK = "https://download.geofabrik.de/"
US_STATES = ["alabama", "alaska", "arizona", "arkansas", "california", "colorado", "connecticut", "delaware",
             "district-of-columbia", "florida", "georgia", "hawaii", "idaho", "illinois", "indiana", "iowa", "kansas",
             "kentucky", "louisiana", "maine", "maryland", "massachusetts", "michigan", "minnesota", "mississippi",
             "missouri", "montana", "nebraska", "nevada", "new-hampshire", "new-jersey", "new-mexico", "new-york",
             "north-carolina", "north-dakota", "ohio", "oklahoma", "oregon", "pennsylvania", "puerto-rico",
             "rhode-island", "south-carolina", "south-dakota", "tennessee", "texas", "utah", "vermont", "virginia",
             "washington", "west-virginia", "wisconsin", "wyoming"]
CA_PROVINCES = ["alberta", "british-columbia", "manitoba", "new-brunswick", "newfoundland-and-labrador",
                "northwest-territories", "nova-scotia", "nunavut", "ontario", "prince-edward-island", "quebec",
                "saskatchewan", "yukon"]


def region_key(name):
    return re.sub(r"[^a-z]+", "-", name.lower()).strip("-")


def region_path(name):
    key = region_key(name)
    if key in US_STATES:
        return "north-america/us/" + key
    if key in CA_PROVINCES:
        return "north-america/canada/" + key
    return None


CENSUS_STATES = "https://www2.census.gov/geo/tiger/GENZ2023/shp/cb_2023_us_state_500k.zip"
CENSUS_COUNTIES = "https://www2.census.gov/geo/tiger/GENZ2023/shp/cb_2023_us_county_500k.zip"
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
    """A state or province name, a Geofabrik path like 'north-america/us/ohio', or a local .osm.pbf file."""
    p = Path(name).expanduser()
    if p.suffix in (".pbf", ".osm") or name.endswith(".osm.pbf"):
        if not p.exists():
            raise SystemExit(f"Road file not found: {p}")
        return p
    path = region_path(name) or (name.strip().lower() if "/" in name else None)
    if not path:
        raise SystemExit(f"Unknown region {name!r}. Use a U.S. state or Canadian province name, "
                         "a Geofabrik path such as 'europe/germany/bayern', or a local .osm.pbf file.")
    fname = path.split("/")[-1] + "-latest.osm.pbf"
    return download(GEOFABRIK + path + "-latest.osm.pbf", Path(data_dir) / "osm" / fname)


def boundary_files(data_dir):
    d = Path(data_dir) / "boundaries"
    return {
        "states": download(CENSUS_STATES, d / Path(CENSUS_STATES).name),
        "lakes": [download(u, d / Path(u).name) for u in NE_LAKES],
        "admin1": download(NE_ADMIN1, d / Path(NE_ADMIN1).name),
    }


def county_file(data_dir):
    return download(CENSUS_COUNTIES, Path(data_dir) / "boundaries" / Path(CENSUS_COUNTIES).name)


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


def geocode(query, data_dir, need_bbox=False):
    """Look a place up on Nominatim (once; results are cached). Returns lat, lon, name and bounding box."""
    cache_f = Path(data_dir) / "places.json"
    cache = json.loads(cache_f.read_text()) if cache_f.exists() else {}
    if query in cache and (not need_bbox or "bbox" in cache[query]):
        return cache[query]
    url = "https://nominatim.openstreetmap.org/search?" + urllib.parse.urlencode(
        {"q": query, "format": "jsonv2", "limit": 1})
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    res = None
    for attempt in range(3):
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                res = json.load(r)
            break
        except (urllib.error.URLError, TimeoutError) as e:
            if attempt == 2:
                raise SystemExit(f"Couldn't look up {query!r} on OpenStreetMap Nominatim ({e}). "
                                 "Wait a minute and retry, or give the place as [latitude, longitude].")
            time.sleep(3 * (attempt + 1))
    time.sleep(1.1)  # Nominatim allows one request per second
    if not res:
        raise SystemExit(f"No place found for {query!r}. Try adding the state, or give [latitude, longitude].")
    s_, n_, w_, e_ = (float(v) for v in res[0]["boundingbox"])
    hit = {"lat": float(res[0]["lat"]), "lon": float(res[0]["lon"]), "name": res[0].get("display_name", query),
           "bbox": [s_, w_, n_, e_]}
    cache[query] = hit
    cache_f.parent.mkdir(parents=True, exist_ok=True)
    cache_f.write_text(json.dumps(cache, indent=1))
    return hit


def coord_name(lat, lon):
    return f"{abs(lat):.3f}°{'N' if lat >= 0 else 'S'} {abs(lon):.3f}°{'E' if lon >= 0 else 'W'}"


def resolve_place(spec, data_dir):
    """(lat, lon) or a place name -> (lat, lon, short name)."""
    if isinstance(spec, tuple):
        return spec[0], spec[1], coord_name(*spec)
    hit = geocode(spec, data_dir)
    return hit["lat"], hit["lon"], spec.split(",")[0].strip()


def resolve_starts(specs, label, data_dir):
    """Turn start specs into [(lat, lon)], the poster label, and a name for each start pin."""
    pts, names = [], []
    for s in specs:
        lat, lon, name = resolve_place(s, data_dir)
        pts.append((lat, lon))
        names.append(name)
    if not label:
        label = " & ".join(names) if len(names) <= 3 else f"{len(names)} Places"
    if len(pts) == 1:
        names = [label]
    return pts, label, names


def resolve_landmarks(items, data_dir):
    out = []
    for it in items:
        lat, lon, _ = resolve_place(it["spec"], data_dir)
        out.append({"name": it["name"], "lat": lat, "lon": lon})
    return out
