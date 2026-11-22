"""Settings: defaults, the TOML file, and command-line overrides."""
import copy
import re
import tomllib
from pathlib import Path

DEFAULTS = {
    "start": "Lansing, Michigan",
    "start_label": "",
    "region": {
        "focus": "Michigan",
        "routing": ["michigan", "wisconsin", "illinois", "indiana", "ohio"],
        "margin_km": 20,
    },
    "travel": {
        "band_minutes": 30,
        "major_every_hours": 2,
        "max_hours": "auto",
        "local_speed_kmh": 30,
        "gap_km": 3,
        "ferries": "car",
        "ferry_wait_minutes": 30,
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
        "subtitle": "Every {band} minutes of driving across {focus}",
        "palette": "ember",
        "outside_opacity": 0.35,
        "cell_m": 500,
        "smooth_cells": 1.2,
        "label_min_population": 8000,
        "context_label_min_population": 250000,
        "draw_highways": True,
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
                _merge(cfg, tomllib.load(f))
        elif str(path) != "poster.toml":
            raise SystemExit(f"Settings file not found: {path}")
    return cfg


_COORD = re.compile(r"^\s*(-?\d+(?:\.\d+)?)\s*[, ]\s*(-?\d+(?:\.\d+)?)\s*$")


def parse_starts(value):
    """Return a list of start specs, each either (lat, lon) or a place-name string."""
    def one(v):
        if isinstance(v, (list, tuple)) and len(v) == 2 and all(isinstance(x, (int, float)) for x in v):
            return (float(v[0]), float(v[1]))
        if isinstance(v, str):
            m = _COORD.match(v)
            if m:
                return (float(m.group(1)), float(m.group(2)))
            return v.strip()
        raise SystemExit(f"Can't read start point {v!r}. Use a place name or [latitude, longitude].")

    if isinstance(value, (list, tuple)) and len(value) == 2 and all(isinstance(x, (int, float)) for x in value):
        return [one(value)]
    if isinstance(value, (list, tuple)):
        if not value:
            raise SystemExit("No start point given.")
        return [one(v) for v in value]
    return [one(value)]
