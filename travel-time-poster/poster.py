#!/usr/bin/env python3
"""Make a drive-time poster.

    python poster.py                                   settings from poster.toml
    python poster.py --start "Marquette, Michigan"     a different start point
    python poster.py --start 46.5436,-87.3954 --label "Home"
    python poster.py --view "Kent County, Michigan"    a different map area
    python poster.py --view landmarks --landmark "Grandma=Holland, MI" --landmark "Cabin=44.95,-85.2"
    python poster.py --prepare-only                    just download and read the map data
"""
import argparse
import math
import re
import sys
import time
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
from ttposter import config, draw, geo, network, osm, sources, view as views  # noqa: E402

log = sources.log


def slug(text):
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-") or "poster"


def duration_text(minutes):
    if minutes % 60 == 0:
        h = minutes // 60
        return f"{h} hour" + ("s" if h != 1 else "")
    return f"{minutes:g} minutes"


def pick_band(far_s, setting):
    if isinstance(setting, (int, float)):
        return float(setting)
    for m in (1, 2, 5, 10, 15, 20, 30, 60, 120):
        if far_s / (m * 60) <= 26:
            return float(m)
    return 180.0


def pick_major(band_min, setting):
    if isinstance(setting, (int, float)):
        return float(setting)
    for m in (5, 10, 15, 30, 60, 120, 180, 240, 360, 480):
        if m >= 4 * band_min - 1e-9 and abs(m / band_min - round(m / band_min)) < 1e-9:
            return float(m)
    return band_min * 4


def main(argv=None):
    ap = argparse.ArgumentParser(description="Drive-time poster from OpenStreetMap roads.")
    ap.add_argument("--config", default="poster.toml", help="settings file (default: poster.toml)")
    ap.add_argument("--start", action="append",
                    help='place name or "lat,lon"; repeat for several start points')
    ap.add_argument("--label", help="name printed on the poster for the start point")
    ap.add_argument("--view", help='map area: a state, "Kent County, Michigan", a place name, or "landmarks"')
    ap.add_argument("--landmark", action="append", default=[],
                    help='"Name=place or lat,lon" to mark on the map; repeatable (adds to poster.toml)')
    ap.add_argument("--no-landmarks", action="store_true", help="ignore landmarks in the settings file")
    ap.add_argument("--title", help="poster title; {start}, {view} and {band} are filled in")
    ap.add_argument("--out", help="output file name without extension (default: out/<start>-<view>)")
    ap.add_argument("--png-dpi", type=int, help="also write a PNG at this resolution, e.g. 300")
    ap.add_argument("--prepare-only", action="store_true", help="download and read map data, then stop")
    args = ap.parse_args(argv)

    here = Path(__file__).resolve().parent
    cfg_path = Path(args.config)
    if not cfg_path.is_absolute() and not cfg_path.exists() and (here / cfg_path).exists():
        cfg_path = here / cfg_path
    cfg = config.load(cfg_path)
    if args.start:
        cfg["start"] = args.start if len(args.start) > 1 else args.start[0]
        if not args.label:
            cfg["start_label"] = ""
    if args.label:
        cfg["start_label"] = args.label
    if args.view:
        cfg["view"]["area"] = args.view
    if args.title:
        cfg["poster"]["title"] = args.title
    if args.png_dpi is not None:
        cfg["poster"]["png_dpi"] = args.png_dpi
    if args.no_landmarks:
        cfg["landmarks"] = []
    P, tr = cfg["poster"], cfg["travel"]

    base = cfg_path.resolve().parent
    data_dir = (base / cfg["paths"]["data"]).resolve()
    out_dir = (base / cfg["paths"]["out"]).resolve()
    t0 = time.time()

    # 1. outlines, start points, landmarks and the map view
    bfiles = sources.boundary_files(data_dir)
    states = geo.read_polygons(bfiles["states"])
    canada_all = geo.read_polygons(bfiles["admin1"], keep=lambda rec: rec.get("admin") == "Canada")
    starts, label, pin_names = sources.resolve_starts(config.parse_starts(cfg["start"]), cfg["start_label"], data_dir)
    landmarks = sources.resolve_landmarks(config.parse_landmarks(cfg["landmarks"], args.landmark), data_dir)
    log(f"Start: {label} " + "; ".join(f"({a:.4f}, {b:.4f})" for a, b in starts))
    if landmarks:
        log(f"Landmarks: {', '.join(lm['name'] for lm in landmarks)}")
    view = views.resolve(cfg["view"]["area"], states, data_dir,
                         list(starts) + [(lm["lat"], lm["lon"]) for lm in landmarks])
    lon0, lat0, lon1, lat1 = view.bbox
    proj = geo.Albers(lat0, lat1, (lon0 + lon1) / 2)
    if view.focus:
        pts = np.vstack([r for rings, _ in view.focus for r in rings])
    else:
        t = np.linspace(0, 1, 30)
        pts = np.vstack([np.column_stack([lon0 + (lon1 - lon0) * t, np.full_like(t, lat0)]),
                         np.column_stack([lon0 + (lon1 - lon0) * t, np.full_like(t, lat1)]),
                         np.column_stack([np.full_like(t, lon0), lat0 + (lat1 - lat0) * t]),
                         np.column_stack([np.full_like(t, lon1), lat0 + (lat1 - lat0) * t])])
    px, py = proj(pts[:, 0], pts[:, 1])
    vb = (px.min(), py.min(), px.max(), py.max())
    L = draw.layout(cfg, has_landmarks=bool(landmarks))
    margin = view.margin_m(cfg["view"]["margin_km"], vb[2] - vb[0], vb[3] - vb[1])
    frame = draw.fit_frame(vb, L["map"][2], L["map"][3], margin)
    fw, fh = frame[2] - frame[0], frame[3] - frame[1]
    cell = P["cell_m"] if isinstance(P["cell_m"], (int, float)) else \
        min(1000.0, max(25.0, round(max(fw, fh) / 1600 / 5) * 5))
    grid = network.Grid(*frame, cell)
    area_km2 = fw * fh / 1e6
    log(f"View: {view.name or view.kind}, {fw / 1000:.0f} × {fh / 1000:.0f} km, {cell:g} m grid")

    # 2. road data (downloaded and read once, then cached)
    regions = cfg["routing"]["regions"]
    if regions == "auto":
        regions = views.auto_regions(view, proj, states, canada_all,
                                     list(starts) + [(lm["lat"], lm["lon"]) for lm in landmarks],
                                     cfg["routing"]["include_canada"])
        log(f"Road data for: {', '.join(regions)}")
    pbfs = [sources.region_pbf(r, data_dir) for r in regions]
    caches = [osm.parse(p, data_dir / "cache", log) for p in pbfs]
    if args.prepare_only:
        log("Map data is ready.")
        return

    # 3. land, water and the focus area on the grid
    def in_frame(rings):
        for ring in rings:
            x, y = proj(ring[:, 0], ring[:, 1])
            if x.max() >= frame[0] and x.min() <= frame[2] and y.max() >= frame[1] and y.min() <= frame[3]:
                return True
        return False

    us = [(r, h) for rec, r, h in states if in_frame(r)]
    # Natural Earth's provinces include their share of the Great Lakes, so their lake parts are masked below
    canada = [(r, h) for rec, r, h in canada_all if in_frame(r)]
    us_land = grid.rasterize(us, proj).astype(bool) if us else np.zeros((grid.rows, grid.cols), bool)
    inland, open_water = [], []
    for lf in bfiles["lakes"]:
        for rec, r, h in geo.read_polygons(lf):
            if not in_frame(r):
                continue
            outer = r[0]
            cx, cy = proj(outer[:, 0].mean(), outer[:, 1].mean())
            rr, cc, ok = grid.cell_of(np.array([cx]), np.array([cy]))
            (inland if ok[0] and us_land[rr[0], cc[0]] else open_water).append((r, h))
    zeros = np.zeros_like(us_land)
    ca_land = grid.rasterize(canada, proj).astype(bool) if canada else zeros
    if canada and open_water:
        ca_land &= ~grid.rasterize(open_water, proj).astype(bool)
    lake_r = grid.rasterize(inland, proj).astype(bool) if inland else zeros
    land = (us_land | ca_land) & ~lake_r
    focus_mask = (grid.rasterize(view.focus, proj).astype(bool) & ~lake_r) if view.focus else land
    counties = []
    if view.kind == "county" or area_km2 < 60000:
        counties = [(r, h) for rec, r, h in geo.read_polygons(sources.county_file(data_dir)) if in_frame(r)]

    # 4. drive times
    R = osm.load_all(caches)
    res = network.compute(R, cfg, proj, grid, land, focus_mask, starts,
                          probes=[(lm["lat"], lm["lon"]) for lm in landmarks], log=log)
    for lm, ts in zip(landmarks, res["probe_s"]):
        lm["seconds"] = ts
    lm_far = max([lm["seconds"] for lm in landmarks if math.isfinite(lm["seconds"])], default=0.0)
    far = max(res["far_s"], lm_far)
    # when the start is outside the view, begin the colors at the nearest time actually on the map
    Tf = res["T"][focus_mask & np.isfinite(res["T"])]
    near = min([float(Tf.min()) if Tf.size else 0.0] +
               [lm["seconds"] for lm in landmarks if math.isfinite(lm["seconds"])])
    band_min = pick_band(far - near, tr["band_minutes"])
    band_s = band_min * 60
    min_s = math.floor(near / band_s) * band_s
    if isinstance(tr["max_hours"], (int, float)):
        max_s = float(tr["max_hours"]) * 3600
    else:
        max_s = max(min_s + band_s, math.ceil(far / band_s - 1e-9) * band_s)
    major_min = pick_major(band_min, tr["major_every_minutes"])
    log(f"Times on the map: {near / 3600:.2f}–{far / 3600:.2f} h; {band_min:g}-minute bands from "
        f"{min_s / 3600:g} to {max_s / 3600:g} h")

    # 5. towns
    tx, ty = proj(R["p_lon"], R["p_lat"])
    rr, cc, ok = grid.cell_of(tx, ty)
    seen, places = set(), []
    for i in np.nonzero(ok)[0]:
        key = (R["p_name"][i], round(float(tx[i]) / 2000), round(float(ty[i]) / 2000))
        if key in seen:
            continue
        seen.add(key)
        places.append((float(tx[i]), float(ty[i]), str(R["p_name"][i]), float(R["p_pop"][i]),
                       bool(focus_mask[rr[i], cc[i]])))
    min_pop = P["label_min_population"]
    if not isinstance(min_pop, (int, float)):
        min_pop = min(20000.0, area_km2 / 60)
    roads = P["draw_roads"]
    if roads == "auto":
        roads = ["motorway"] if area_km2 > 150000 else ["motorway", "primary"] if area_km2 > 15000 \
            else ["motorway", "primary", "secondary"]
    elif roads is True:
        roads = ["motorway"]
    elif not roads:
        roads = []

    # 6. draw
    fmt = {"start": label, "view": view.name, "focus": view.name, "band": f"{band_min:g}"}
    subtitle = P["subtitle"]
    if subtitle == "auto":
        subtitle = f"Every {duration_text(band_min)} of driving" + (f" across {view.name}" if view.name else "")
    ctx = {
        "layout": L, "fonts": draw.setup_fonts(sources.fonts(data_dir)), "proj": proj, "grid": grid,
        "frame": frame, "focus_polys": view.focus, "land_polys": us, "canada_polys": canada,
        "county_polys": counties, "lake_polys": inland, "open_water_polys": open_water, "land": land,
        "min_s": min_s, "max_s": max_s, "band_s": band_s, "major_s": major_min * 60, "label": label, "pin_names": pin_names,
        "start_ll": starts, "places": places, "min_pop": min_pop, "roads": roads,
        "title": P["title"].format(**fmt), "subtitle": subtitle.format(**fmt),
        "start_xy": [tuple(float(v) for v in proj(lon, lat)) for lat, lon in starts],
        "landmarks": [dict(lm, xy=tuple(float(v) for v in proj(lm["lon"], lm["lat"]))) for lm in landmarks],
    }
    out_base = Path(args.out).resolve() if args.out else \
        out_dir / f"{slug(label)}-{slug(view.name) if view.name else view.kind}"
    files = draw.render(res, cfg, ctx, out_base)
    log(f"Done in {time.time() - t0:.0f} s:")
    for f in files:
        log(f"  {f}")


if __name__ == "__main__":
    main()
