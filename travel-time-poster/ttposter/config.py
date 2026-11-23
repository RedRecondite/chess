"""Settings: defaults, the TOML file, and command-line overrides."""
import copy
import re
try:
    import tomllib  # Python 3.11+
except ModuleNotFoundError:  # Python 3.9/3.10
    import tomli as tomllib
from pathlib import Path

DEFAULTS = {
    "start": "Lansing, Michigan",
    "start_label": "",
    "landmarks": [],
    "view": {
        "area": "Michigan",
        "margin_km": "auto",
    },
    "routing": {
        "regions": "auto",
        "include_canada": False,
    },
    "travel": {
        "band_minutes": "auto",
        "major_every_minutes": "auto",
        "max_hours": "auto",
        "local_speed_kmh": 30,
        "gap_km": 3,
        "route_classes": ["motorway", "motorway_link", "trunk", "trunk_link", "primary", "primary_link",
                          "secondary", "secondary_link", "tertiary", "tertiary_link", "unclassified",
                          "residential", "road"],
        "gap_classes": ["motorway", "trunk", "primary", "secondary", "tertiary", "unclassified",
                        "residential", "living_street", "road"],
    },
    "poster": {
        "width_in": 24,
        "height_in": 36,
        "title": "Drive Time from {start}",
        "subtitle": "auto",
        "palette": "ember",
        "outside_opacity": 0.35,
        "cell_m": "auto",
        "smooth_cells": 1.2,
        "label_min_population": "auto",
        "context_label_min_population": 250000,
        "draw_roads": "auto",
        "landmark_scale": 1.0,
        "preview_dpi": 60,
        "png_dpi": 0,
    },
    "paths": {"data": "data", "out": "out"},
}


def _merge(base, extra):
    for k, v in extra.items():
        if isinstance(v, dict) and isinstance(base.get(k), dict):
            _merge(base[k], v)
        else:
            base[k] = v
    return base


def load(path=None):
    cfg = copy.deepcopy(DEFAULTS)
    if path:
        p = Path(path)
        if p.exists():
            with open(p, "rb") as f:
                user = tomllib.load(f)
            # settings files from the first version used [region] focus/routing
            old = user.pop("region", None)
            if old:
                if "focus" in old:
                    user.setdefault("view", {}).setdefault("area", old["focus"])
                if "margin_km" in old:
                    user.setdefault("view", {}).setdefault("margin_km", old["margin_km"])
                if "routing" in old:
                    user.setdefault("routing", {}).setdefault("regions", old["routing"])
            tr = user.get("travel", {})
            if "major_every_hours" in tr and "major_every_minutes" not in tr:
                tr["major_every_minutes"] = tr.pop("major_every_hours") * 60
            for k in ("ferries", "ferry_wait_minutes"):
                tr.pop(k, None)
            _merge(cfg, user)
        elif str(path) != "poster.toml":
            raise SystemExit(f"Settings file not found: {path}")
    return cfg


_COORD = re.compile(r"^\s*(-?\d+(?:\.\d+)?)\s*[, ]\s*(-?\d+(?:\.\d+)?)\s*$")


def parse_place(v):
    """A place: (lat, lon) tuple, or a place-name string to look up."""
    if isinstance(v, (list, tuple)) and len(v) == 2 and all(isinstance(x, (int, float)) for x in v):
        return (float(v[0]), float(v[1]))
    if isinstance(v, str):
        m = _COORD.match(v)
        if m:
            return (float(m.group(1)), float(m.group(2)))
        if v.strip():
            return v.strip()
    raise SystemExit(f"Can't read the place {v!r}. Use a place name or [latitude, longitude].")


def parse_starts(value):
    """Return a list of start specs, each either (lat, lon) or a place-name string."""
    if isinstance(value, (list, tuple)) and len(value) == 2 and all(isinstance(x, (int, float)) for x in value):
        return [parse_place(value)]
    if isinstance(value, (list, tuple)):
        if not value:
            raise SystemExit("No start point given.")
        return [parse_place(v) for v in value]
    return [parse_place(value)]


def parse_landmarks(items, cli=None):
    """Landmarks from [[landmarks]] tables ({name, at}) and --landmark "Name=place" flags."""
    out = []
    for i, it in enumerate(items or []):
        if isinstance(it, dict):
            at = it.get("at", it.get("place", it.get("coords")))
            if at is None:
                raise SystemExit(f"Landmark {i + 1} needs an 'at' (place name or [latitude, longitude]).")
            spec = parse_place(at)
            name = it.get("name") or (spec if isinstance(spec, str) else f"Landmark {i + 1}")
        else:
            spec = parse_place(it)
            name = spec if isinstance(spec, str) else f"Landmark {i + 1}"
        out.append({"name": str(name).split(",")[0] if not isinstance(it, dict) else str(name), "spec": spec})
    for raw in cli or []:
        name, sep, place = raw.partition("=")
        if not sep:
            place, name = raw, ""
        spec = parse_place(place)
        if not name:
            name = spec.split(",")[0] if isinstance(spec, str) else f"Landmark {len(out) + 1}"
        out.append({"name": name.strip(), "spec": spec})
    return out
