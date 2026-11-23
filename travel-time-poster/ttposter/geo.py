"""Projection, distances and polygon reading."""
import numpy as np
import shapefile  # pyshp

R_EARTH = 6371008.8


class Albers:
    """Spherical Albers equal-area conic, fitted to a latitude range. Units: meters."""

    def __init__(self, lat_min, lat_max, lon0):
        span = lat_max - lat_min
        p1, p2 = np.radians(lat_min + span / 6), np.radians(lat_max - span / 6)
        self.lat0 = np.radians((lat_min + lat_max) / 2)
        self.lon0 = np.radians(lon0)
        self.n = (np.sin(p1) + np.sin(p2)) / 2
        self.C = np.cos(p1) ** 2 + 2 * self.n * np.sin(p1)
        self.rho0 = R_EARTH * np.sqrt(self.C - 2 * self.n * np.sin(self.lat0)) / self.n

    def __call__(self, lon, lat):
        lon = np.radians(np.asarray(lon, dtype=np.float64))
        lat = np.radians(np.asarray(lat, dtype=np.float64))
        rho = R_EARTH * np.sqrt(self.C - 2 * self.n * np.sin(lat)) / self.n
        th = self.n * (lon - self.lon0)
        return rho * np.sin(th), self.rho0 - rho * np.cos(th)


def haversine(lat1, lon1, lat2, lon2):
    p1, p2 = np.radians(lat1), np.radians(lat2)
    dp, dl = p2 - p1, np.radians(lon2 - lon1)
    a = np.sin(dp / 2) ** 2 + np.cos(p1) * np.cos(p2) * np.sin(dl / 2) ** 2
    return 2 * R_EARTH * np.arcsin(np.sqrt(np.minimum(1.0, a)))


def ring_area(lon, lat):
    return 0.5 * np.sum(lon[:-1] * lat[1:] - lon[1:] * lat[:-1])


def read_polygons(path, keep=None):
    """Read a polygon shapefile (zip ok). Returns [(record_dict, [ring arrays (N,2) lon/lat], [is_hole])]."""
    out = []
    with shapefile.Reader(str(path)) as r:
        fields = [f[0] for f in r.fields[1:]]
        for sr in r.iterShapeRecords():
            rec = dict(zip(fields, sr.record))
            if keep and not keep(rec):
                continue
            shp = sr.shape
            if not shp.points:
                continue
            pts = np.asarray(shp.points, dtype=np.float64)
            parts = list(shp.parts) + [len(pts)]
            rings, holes = [], []
            for a, b in zip(parts[:-1], parts[1:]):
                ring = pts[a:b]
                if len(ring) < 4:
                    continue
                rings.append(ring)
                holes.append(ring_area(ring[:, 0], ring[:, 1]) > 0)  # shapefile outer rings run clockwise
            out.append((rec, rings, holes))
    return out


def bbox_of(rings):
    allp = np.vstack(rings)
    return allp[:, 0].min(), allp[:, 1].min(), allp[:, 0].max(), allp[:, 1].max()
