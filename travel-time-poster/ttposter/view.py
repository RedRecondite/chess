"""What the map shows (a state, a county, a place, a box, or the landmarks) and which road extracts it needs."""
import re
from dataclasses import dataclass

import numpy as np
from matplotlib.path import Path as MPath
from scipy.spatial import cKDTree

from . import geo, sources

COUNTY_WORDS = r"county|parish|borough|census area|city and borough|municipality"


@dataclass
class View:
    kind: str            # state, county, place, box, landmarks
    name: str            # shown in the subtitle; "" when there is no natural name
    focus: list | None   # [(rings, holes)] drawn at full strength, or None for "everything in the frame"
    bbox: tuple          # lon0, lat0, lon1, lat1

    def margin_m(self, setting, w, h):
        if isinstance(setting, (int, float)):
            return setting * 1000.0
        frac = {"state": 0.04, "county": 0.08, "place": 0.04, "box": 0.0, "landmarks": 0.12}[self.kind]
        floor = {"landmarks": 3000.0, "box": 0.0}.get(self.kind, 1500.0)
        return max(floor, frac * max(w, h))


def _expand(lat0, lon0, lat1, lon1, min_km):
    """Make sure a lat/lon box is at least min_km across in both directions."""
    clat = (lat0 + lat1) / 2
    need_lat = min_km / 111.32
    need_lon = min_km / (111.32 * np.cos(np.radians(clat)))
    if lat1 - lat0 < need_lat:
        lat0, lat1 = clat - need_lat / 2, clat + need_lat / 2
    if lon1 - lon0 < need_lon:
        c = (lon0 + lon1) / 2
        lon0, lon1 = c - need_lon / 2, c + need_lon / 2
    return lat0, lon0, lat1, lon1


def resolve(area, states, data_dir, points):
    """area: state or county name, any place name, [south, west, north, east], or "landmarks"."""
    if isinstance(area, (list, tuple)):
        if len(area) != 4:
            raise SystemExit("A box view needs four numbers: [south, west, north, east].")
        s, w, n, e = (float(v) for v in area)
        return View("box", "", None, (w, s, e, n))
    a = str(area).strip()
    low = a.lower()
    if low in ("landmarks", "fit", "auto"):
        if not points:
            raise SystemExit("area = \"landmarks\" needs at least one landmark or start point.")
        lats = [p[0] for p in points]
        lons = [p[1] for p in points]
        lat0, lon0, lat1, lon1 = _expand(min(lats), min(lons), max(lats), max(lons), 8.0)
        return View("landmarks", "", None, (lon0, lat0, lon1, lat1))

    for rec, rings, holes in states:
        if str(rec.get("NAME", "")).lower() == low or str(rec.get("STUSPS", "")).lower() == low:
            return View("state", rec["NAME"], [(rings, holes)], geo.bbox_of(rings))

    m = re.match(rf"^(.*?)(?:\s+({COUNTY_WORDS}))?\s*(?:,\s*(.+))?$", a, re.I)
    if m and (m.group(2) or m.group(3)):
        cname, word, st = m.group(1).strip().lower(), m.group(2), (m.group(3) or "").strip().lower()
        counties = geo.read_polygons(sources.county_file(data_dir))
        hits = [(rec, r, h) for rec, r, h in counties
                if str(rec["NAME"]).lower() == cname
                and (not st or st in (str(rec["STATE_NAME"]).lower(), str(rec["STUSPS"]).lower()))]
        if len(hits) > 1 and not st:
            opts = ", ".join(f"{rec['NAMELSAD']}, {rec['STATE_NAME']}" for rec, _, _ in hits[:8])
            raise SystemExit(f"{a!r} matches several counties ({opts}…). Add the state, e.g. \"{a}, Michigan\".")
        if hits:
            rec, rings, holes = hits[0]
            return View("county", rec["NAMELSAD"], [(rings, holes)], geo.bbox_of(rings))
        if word:
            raise SystemExit(f"No county named {a!r} in the Census county outlines.")

    hit = sources.geocode(a, data_dir, need_bbox=True)
    s, w, n, e = hit["bbox"]
    s, w, n, e = _expand(s, w, n, e, 20.0)
    return View("place", a.split(",")[0].strip(), None, (w, s, e, n))


def auto_regions(view, proj, states, canada, points, include_canada):
    """Road extracts to download: every state (and optionally province) near the view, the starts and the
    landmarks, or on the way between them."""
    lon0, lat0, lon1, lat1 = view.bbox
    if view.focus:
        ring_pts = np.vstack([r for rings, _ in view.focus for r in rings])
        step = max(1, len(ring_pts) // 4000)
        tg = ring_pts[::step]
    else:
        # the drawn frame adds margins around boxes and landmark views; cover them too
        dx, dy = 0.15 * (lon1 - lon0), 0.15 * (lat1 - lat0)
        lon0, lon1, lat0, lat1 = lon0 - dx, lon1 + dx, lat0 - dy, lat1 + dy
        t = np.linspace(0, 1, 40)
        tg = np.vstack([np.column_stack([lon0 + (lon1 - lon0) * t, np.full_like(t, lat0)]),
                        np.column_stack([lon0 + (lon1 - lon0) * t, np.full_like(t, lat1)]),
                        np.column_stack([np.full_like(t, lon0), lat0 + (lat1 - lat0) * t]),
                        np.column_stack([np.full_like(t, lon1), lat0 + (lat1 - lat0) * t])])
    cx, cy = (lon0 + lon1) / 2, (lat0 + lat1) / 2
    extra = [[cx, cy]]
    for lat, lon in points:
        extra.append([lon, lat])
        km = geo.haversine(lat, lon, cy, cx) / 1000
        for f in np.linspace(0, 1, max(2, int(km / 20))):
            extra.append([lon + (cx - lon) * f, lat + (cy - lat) * f])
    tg = np.vstack([tg, np.array(extra)])
    tx, ty = proj(tg[:, 0], tg[:, 1])
    tree = cKDTree(np.column_stack([tx, ty]))
    vx, vy = proj(np.array([lon0, lon1]), np.array([lat0, lat1]))
    diag = float(np.hypot(vx[1] - vx[0], vy[1] - vy[0]))
    buffer_m = max(100000.0, 0.15 * diag)

    def near(rings):
        allp = np.vstack(rings)
        step = max(1, len(allp) // 3000)
        px, py = proj(allp[::step, 0], allp[::step, 1])
        if tree.query(np.column_stack([px, py]))[0].min() <= buffer_m:
            return True
        return any(MPath(r).contains_points(tg).any() for r in rings)

    names = []
    for rec, rings, _ in states:
        if sources.region_path(str(rec.get("NAME", ""))) and near(rings):
            names.append(sources.region_key(rec["NAME"]))
    if include_canada:
        for rec, rings, _ in canada:
            nm = str(rec.get("name", ""))
            if sources.region_path(nm) and near(rings):
                names.append(sources.region_key(nm))
    return names
