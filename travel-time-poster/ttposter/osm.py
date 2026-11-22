"""Read roads, ferries and towns from an .osm.pbf file into compact numpy arrays, cached next to the data."""
from array import array
from pathlib import Path
import re
import time

import numpy as np

PARSE_VERSION = 3

CLASSES = ["motorway", "motorway_link", "trunk", "trunk_link", "primary", "primary_link",
           "secondary", "secondary_link", "tertiary", "tertiary_link", "unclassified", "residential",
           "living_street", "service", "track", "road", "ferry"]
CLS = {c: i for i, c in enumerate(CLASSES)}

# way flags
F_FLAT = 1         # bridge or tunnel: you can't leave the road partway across
F_CAR_FERRY = 2
F_PASSENGER_FERRY = 4

_SPEED = re.compile(r"^\s*(\d+(?:\.\d+)?)\s*(mph)?")


def parse_speed(s):
    if not s:
        return 0.0
    if s == "none":
        return 130.0
    m = _SPEED.match(s)
    if not m:
        return 0.0
    return float(m.group(1)) * (1.609 if m.group(2) else 1.0)


def _yes(v):
    return v in ("yes", "designated", "permissive", "destination")


def parse(pbf, cache_dir, log=print):
    import osmium

    pbf = Path(pbf)
    cache = Path(cache_dir) / (pbf.name.split(".")[0] + ".npz")
    if cache.exists() and cache.stat().st_mtime >= pbf.stat().st_mtime:
        with np.load(cache) as z:
            if int(z["version"]) == PARSE_VERSION:
                return cache
    cache.parent.mkdir(parents=True, exist_ok=True)
    log(f"Reading roads from {pbf.name} (a few minutes for a whole state)…")
    t0 = time.time()

    refs, lats, lons = array("q"), array("f"), array("f")
    off, cls, spd, ow, flags = array("q", [0]), array("b"), array("f"), array("b"), array("B")
    p_name, p_lat, p_lon, p_pop, p_kind = [], [], [], [], []
    n_ways = 0

    fp = osmium.FileProcessor(str(pbf)).with_locations().with_filter(osmium.filter.KeyFilter("highway", "route", "place"))
    for o in fp:
        if o.is_node():
            t = o.tags
            kind = t.get("place")
            if kind in ("city", "town") and "name" in t:
                pop = parse_speed(t.get("population", "").replace(",", ""))
                p_name.append(t.get("name"))
                p_lat.append(o.location.lat)
                p_lon.append(o.location.lon)
                p_pop.append(pop)
                p_kind.append(0 if kind == "city" else 1)
            continue
        if not o.is_way():
            continue
        t = o.tags
        fl = 0
        if t.get("route") == "ferry":
            c = CLS["ferry"]
            mv = t.get("motor_vehicle") or t.get("motorcar") or t.get("hgv")
            fl |= F_CAR_FERRY if _yes(mv) else F_PASSENGER_FERRY
        else:
            h = t.get("highway")
            c = CLS.get(h)
            if c is None or t.get("area") == "yes":
                continue
            if t.get("motor_vehicle") == "no" or t.get("motorcar") == "no":
                continue
            if t.get("access") in ("no", "private") and not (_yes(t.get("motor_vehicle")) or _yes(t.get("motorcar"))):
                continue
            b, tu = t.get("bridge"), t.get("tunnel")
            if (b and b != "no") or (tu and tu not in ("no", "building_passage")):
                fl |= F_FLAT
        nodes = o.nodes
        if len(nodes) < 2:
            continue
        cnt = 0
        for n in nodes:
            loc = n.location
            if not loc.valid():
                continue
            refs.append(n.ref)
            lats.append(loc.lat)
            lons.append(loc.lon)
            cnt += 1
        if cnt < 2:
            del refs[len(refs) - cnt:], lats[len(lats) - cnt:], lons[len(lons) - cnt:]
            continue
        off.append(len(refs))
        cls.append(c)
        spd.append(parse_speed(t.get("maxspeed")))
        o_ = t.get("oneway")
        if o_ in ("yes", "1", "true"):
            ow.append(1)
        elif o_ in ("-1", "reverse"):
            ow.append(-1)
        elif o_ == "no":
            ow.append(0)
        else:
            implied = CLASSES[c] in ("motorway", "motorway_link") or t.get("junction") in ("roundabout", "circular")
            ow.append(1 if implied else 0)
        flags.append(fl)
        n_ways += 1
        if n_ways % 250000 == 0:
            log(f"  {n_ways:,} roads…")

    np.savez(cache, version=PARSE_VERSION,
             refs=np.frombuffer(refs, dtype=np.int64), lat=np.frombuffer(lats, dtype=np.float32),
             lon=np.frombuffer(lons, dtype=np.float32), off=np.frombuffer(off, dtype=np.int64),
             cls=np.frombuffer(cls, dtype=np.int8), maxspeed=np.frombuffer(spd, dtype=np.float32),
             oneway=np.frombuffer(ow, dtype=np.int8), flags=np.frombuffer(flags, dtype=np.uint8),
             p_name=np.array(p_name, dtype=str), p_lat=np.array(p_lat), p_lon=np.array(p_lon),
             p_pop=np.array(p_pop), p_kind=np.array(p_kind, dtype=np.int8))
    log(f"  {n_ways:,} roads and {len(p_name):,} towns in {time.time() - t0:.0f} s")
    return cache


def load_all(caches):
    """Concatenate several parsed regions."""
    parts = [dict(np.load(c)) for c in caches]
    out = {}
    shift = 0
    offs = []
    for p in parts:
        o = p["off"]
        offs.append(o[:-1] + shift)
        shift += o[-1]
    out["off"] = np.concatenate(offs + [np.array([shift], dtype=np.int64)])
    for k in ("refs", "lat", "lon", "cls", "maxspeed", "oneway", "flags",
              "p_name", "p_lat", "p_lon", "p_pop", "p_kind"):
        out[k] = np.concatenate([p[k] for p in parts])
    return out
