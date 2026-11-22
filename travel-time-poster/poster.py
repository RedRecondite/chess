#!/usr/bin/env python3
"""Make a drive-time poster.

    python poster.py                                  settings from poster.toml
    python poster.py --start "Marquette, Michigan"    a different start point
    python poster.py --start 46.5436,-87.3954 --label "Home"
    python poster.py --start "Detroit, MI" --start "Grand Rapids, MI"   nearest of several
    python poster.py --prepare-only                   just download and read the map data
"""
import argparse
import re
import sys
import time
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
from ttposter import config, draw, geo, network, osm, sources  # noqa: E402

log = sources.log


def slug(text):
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-") or "poster"


def main(argv=None):
    ap = argparse.ArgumentParser(description="Drive-time poster from OpenStreetMap roads.")
    ap.add_argument("--config", default="poster.toml", help="settings file (default: poster.toml)")
    ap.add_argument("--start", action="append",
                    help='place name or "lat,lon"; repeat for several start points')
    ap.add_argument("--label", help="name printed on the poster for the start point")
    ap.add_argument("--title", help="poster title; {start}, {focus} and {band} are filled in")
    ap.add_argument("--out", help="output file name without extension (default: out/<start>-drive)")
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
    if args.title:
        cfg["poster"]["title"] = args.title
    if args.png_dpi is not None:
        cfg["poster"]["png_dpi"] = args.png_dpi

    base = cfg_path.resolve().parent
    data_dir = (base / cfg["paths"]["data"]).resolve()
    out_dir = (base / cfg["paths"]["out"]).resolve()
    t0 = time.time()

    # 1. road data (downloaded and read once, then cached)
    pbfs = [sources.region_pbf(r, data_dir) for r in cfg["region"]["routing"]]
    caches = [osm.parse(p, data_dir / "cache", log) for p in pbfs]
    bfiles = sources.boundary_files(data_dir)
    if args.prepare_only:
        log("Map data is ready.")
        return

    # 2. where the drive starts
    starts, label, pin_names = sources.resolve_starts(config.parse_starts(cfg["start"]), cfg["start_label"], data_dir)
    log(f"Start: {label} " + "; ".join(f"({a:.4f}, {b:.4f})" for a, b in starts))

    # 3. outlines, projection and the poster frame
    focus_name = cfg["region"]["focus"].strip().lower()
    states = geo.read_polygons(bfiles["states"])
    focus = [(r, h) for rec, r, h in states
             if str(rec.get("NAME", "")).lower() == focus_name or str(rec.get("STUSPS", "")).lower() == focus_name]
    if not focus:
        raise SystemExit(f"No U.S. state named {cfg['region']['focus']!r} in the Census outlines.")
    lon0_, lat0_, lon1_, lat1_ = geo.bbox_of([ring for rings, _ in focus for ring in rings])
    proj = geo.Albers(lat0_, lat1_, (lon0_ + lon1_) / 2)
    fx = [proj(ring[:, 0], ring[:, 1]) for rings, _ in focus for ring in rings]
    fb = (min(x.min() for x, _ in fx), min(y.min() for _, y in fx), max(x.max() for x, _ in fx),
          max(y.max() for _, y in fx))
    L = draw.layout(cfg)
    frame = draw.fit_frame(fb, L["map"][2], L["map"][3], cfg["region"]["margin_km"] * 1000)
    grid = network.Grid(*frame, cfg["poster"]["cell_m"])

    def in_frame(rings):
        for ring in rings:
            x, y = proj(ring[:, 0], ring[:, 1])
            if x.max() >= frame[0] and x.min() <= frame[2] and y.max() >= frame[1] and y.min() <= frame[3]:
                return True
        return False

    others = [(r, h) for rec, r, h in states
              if str(rec.get("NAME", "")).lower() != focus_name and str(rec.get("STUSPS", "")).lower() != focus_name
              and in_frame(r)]
    # Natural Earth's provinces include their share of the Great Lakes, so their lake parts are masked below
    canada = [(r, h) for rec, r, h in geo.read_polygons(bfiles["admin1"], keep=lambda rec: rec.get("admin") == "Canada")
              if in_frame(r)]
    focus_r = grid.rasterize(focus, proj).astype(bool)
    us_land = focus_r | grid.rasterize(others, proj).astype(bool)
    inland, open_water = [], []
    for lf in bfiles["lakes"]:
        for rec, r, h in geo.read_polygons(lf):
            if not in_frame(r):
                continue
            # lakes inside the U.S. outlines are cut out of the land; the rest (Great Lakes, Canadian lakes)
            # only matter where they overlap Canadian provinces
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
    focus_mask = focus_r & ~lake_r
    log(f"Frame {(frame[2] - frame[0]) / 1000:.0f} × {(frame[3] - frame[1]) / 1000:.0f} km, "
        f"{len(others) + len(canada)} neighboring areas, {len(inland)} inland lakes")

    # 4. drive times
    R = osm.load_all(caches)
    res = network.compute(R, cfg, proj, grid, land, focus_mask, starts, log)
    band_s = cfg["travel"]["band_minutes"] * 60
    mh = cfg["travel"]["max_hours"]
    if isinstance(mh, (int, float)):
        max_s = float(mh) * 3600
    else:
        max_s = max(band_s, np.ceil(res["far_s"] / band_s) * band_s)
    log(f"Farthest reachable point in {cfg['region']['focus']}: {res['far_s'] / 3600:.1f} h; "
        f"bands up to {max_s / 3600:g} h")

    # 5. towns
    px, py = proj(R["p_lon"], R["p_lat"])
    rr, cc, ok = grid.cell_of(px, py)
    seen, places = set(), []
    for i in np.nonzero(ok)[0]:
        key = (R["p_name"][i], round(float(px[i]) / 2000), round(float(py[i]) / 2000))
        if key in seen:
            continue
        seen.add(key)
        places.append((float(px[i]), float(py[i]), str(R["p_name"][i]), float(R["p_pop"][i]),
                       bool(focus_mask[rr[i], cc[i]])))

    # 6. draw
    ctx = {
        "layout": L, "fonts": draw.setup_fonts(sources.fonts(data_dir)), "proj": proj, "grid": grid,
        "frame": frame, "focus_polys": focus, "other_polys": others, "canada_polys": canada, "lake_polys": inland,
        "open_water_polys": open_water, "land": land,
        "max_s": max_s, "label": label, "pin_names": pin_names, "start_ll": starts, "places": places,
        "start_xy": [tuple(float(v) for v in proj(lon, lat)) for lat, lon in starts],
    }
    out_base = Path(args.out).resolve() if args.out else out_dir / f"{slug(label)}-drive"
    files = draw.render(res, cfg, ctx, out_base)
    log(f"Done in {time.time() - t0:.0f} s:")
    for f in files:
        log(f"  {f}")


if __name__ == "__main__":
    main()
