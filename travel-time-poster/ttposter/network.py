"""Road graph, shortest drive times, and the off-road grid that turns them into a continuous time surface."""
import time

import numpy as np
from PIL import Image, ImageDraw
from scipy import ndimage
from scipy.sparse import csr_matrix
from scipy.sparse.csgraph import dijkstra
from scipy.spatial import cKDTree

from .geo import haversine
from .osm import CLASSES, CLS, F_FLAT

# Free-flow driving speeds in km/h when a road has no maxspeed tag.
DEFAULT_KMH = {
    "motorway": 110, "motorway_link": 60, "trunk": 90, "trunk_link": 50, "primary": 75, "primary_link": 45,
    "secondary": 65, "secondary_link": 40, "tertiary": 55, "tertiary_link": 35, "unclassified": 50,
    "residential": 40, "living_street": 10, "service": 15, "track": 15, "road": 40, "ferry": 25,
}
JUNCTION_DELAY_S = 4.0


class Grid:
    """A square-celled raster over the poster frame, in projected meters."""

    def __init__(self, x0, y0, x1, y1, cell):
        self.cell = float(cell)
        self.cols = int(np.ceil((x1 - x0) / cell))
        self.rows = int(np.ceil((y1 - y0) / cell))
        self.x0, self.ytop = x0, y0 + self.rows * cell

    def cell_of(self, x, y):
        c = np.floor((x - self.x0) / self.cell).astype(np.int64)
        r = np.floor((self.ytop - y) / self.cell).astype(np.int64)
        ok = (c >= 0) & (r >= 0) & (c < self.cols) & (r < self.rows)
        return r, c, ok

    def centers(self):
        xs = self.x0 + (np.arange(self.cols) + 0.5) * self.cell
        ys = self.ytop - (np.arange(self.rows) + 0.5) * self.cell
        return xs, ys

    def rasterize(self, polys, proj, value=1, base=None):
        """Fill polygons (list of (rings, holes)) into a uint8 raster."""
        img = Image.fromarray(base) if base is not None else Image.new("L", (self.cols, self.rows), 0)
        d = ImageDraw.Draw(img)
        for rings, holes in polys:
            for want_hole in (False, True):
                for ring, hole in zip(rings, holes):
                    if hole != want_hole:
                        continue
                    x, y = proj(ring[:, 0], ring[:, 1])
                    px = (x - self.x0) / self.cell
                    py = (self.ytop - y) / self.cell
                    if px.max() < 0 or py.max() < 0 or px.min() > self.cols or py.min() > self.rows:
                        continue
                    d.polygon(list(zip(px.tolist(), py.tolist())), fill=(0 if hole else value))
        return np.array(img)


def _segments(R):
    """Consecutive node pairs within each way."""
    off = R["off"]
    lens = np.diff(off)
    way_of = np.repeat(np.arange(len(lens)), lens)
    i = np.nonzero(way_of[:-1] == way_of[1:])[0]
    return i, way_of[i]


def compute(R, cfg, proj, grid, land, focus_mask, starts, probes=(), log=print):
    t0 = time.time()
    tr = cfg["travel"]
    local_mps = tr["local_speed_kmh"] / 3.6
    cell = grid.cell

    # ---------- nodes ----------
    uniq, first, inv = np.unique(R["refs"], return_index=True, return_inverse=True)
    N = len(uniq)
    nlat = R["lat"][first].astype(np.float64)
    nlon = R["lon"][first].astype(np.float64)
    nx, ny = proj(nlon, nlat)

    pos, way = _segments(R)
    a, b = inv[pos], inv[pos + 1]
    cls = R["cls"][way]
    flags = R["flags"][way]
    seg_m = haversine(nlat[a], nlon[a], nlat[b], nlon[b])

    route_cls = np.zeros(len(CLASSES), bool)
    for c in tr["route_classes"]:
        if c in CLS:
            route_cls[CLS[c]] = True
    is_ferry = cls == CLS["ferry"]
    routable = route_cls[cls] & ~is_ferry   # ferries are never used: no schedules or waits to guess at
    gap_cls = np.zeros(len(CLASSES), bool)
    for c in tr["gap_classes"]:
        if c in CLS:
            gap_cls[CLS[c]] = True
    gapseg = gap_cls[cls] & ~is_ferry

    # ---------- edge times ----------
    dflt = np.array([DEFAULT_KMH[c] for c in CLASSES])[cls]
    ms = R["maxspeed"][way].astype(np.float64)
    kmh = np.where(ms > 0, np.minimum(ms * 0.9, dflt * 1.4), dflt)
    t = seg_m / (kmh / 3.6)

    sel = routable
    a_r, b_r, t_r = a[sel], b[sel], t[sel]
    ow = R["oneway"][way][sel]
    motorwayish = np.isin(cls[sel], [CLS["motorway"], CLS["motorway_link"]])
    deg = np.bincount(a_r, minlength=N) + np.bincount(b_r, minlength=N)
    delay_b = np.where((deg[b_r] >= 3) & ~motorwayish, JUNCTION_DELAY_S, 0.0)
    delay_a = np.where((deg[a_r] >= 3) & ~motorwayish, JUNCTION_DELAY_S, 0.0)
    fwd, rev = ow != -1, ow != 1
    src = np.concatenate([a_r[fwd], b_r[rev]])
    dst = np.concatenate([b_r[fwd], a_r[rev]])
    w = np.concatenate([t_r[fwd] + delay_b[fwd], t_r[rev] + delay_a[rev]])
    w = np.maximum(w, 0.01)
    # the same road can appear in two neighboring extracts: keep one copy of each edge
    key = src.astype(np.int64) * (N + 1) + dst
    order = np.lexsort((w, key))
    ks = key[order]
    keep = order[np.r_[True, ks[1:] != ks[:-1]]]
    src, dst, w = src[keep], dst[keep], w[keep]

    # where you may leave the road: not motorways, ferries, bridges or tunnels
    exit_seg = sel & ~np.isin(cls, [CLS["motorway"], CLS["motorway_link"], CLS["ferry"]]) & ((flags & F_FLAT) == 0)
    exit_node = np.zeros(N, bool)
    exit_node[a[exit_seg]] = True
    exit_node[b[exit_seg]] = True
    log(f"Road graph: {N:,} nodes, {len(src):,} one-way links ({time.time() - t0:.0f} s)")

    # ---------- connect the start point(s) ----------
    cand = np.nonzero(exit_node)[0]
    tree = cKDTree(np.column_stack([nx[cand], ny[cand]]))
    vs, vd, vw = [], [], []
    for lat, lon in starts:
        sx, sy = proj(lon, lat)
        dd, ii = tree.query([float(sx), float(sy)], k=12, distance_upper_bound=15000)
        ok = np.isfinite(dd)
        if not ok.any():
            raise SystemExit(f"The start point {lat:.4f}, {lon:.4f} is more than 15 km from any road in the data. "
                             "Check the coordinates, or add the region it is in to [region] routing.")
        vs += [N] * int(ok.sum())
        vd += cand[ii[ok]].tolist()
        vw += (dd[ok] / local_mps + 0.01).tolist()
    G = csr_matrix((np.concatenate([w, vw]), (np.concatenate([src, vs]), np.concatenate([dst, vd]))),
                   shape=(N + 1, N + 1))
    dnode = dijkstra(G, directed=True, indices=N)[:N]
    log(f"Drive times to {np.isfinite(dnode).sum():,} road nodes ({time.time() - t0:.0f} s)")

    # drive time to each landmark: best of the nearby road nodes plus the last stretch on foot-ish speed
    probe_s = []
    for lat, lon in probes:
        px_, py_ = proj(lon, lat)
        dd, ii = tree.query([float(px_), float(py_)], k=12, distance_upper_bound=15000)
        ok = np.isfinite(dd)
        best = np.min(dnode[cand[ii[ok]]] + dd[ok] / local_mps) if ok.any() else np.inf
        for slat, slon in starts:  # a landmark right next to a start
            sx2, sy2 = proj(slon, slat)
            best = min(best, float(np.hypot(px_ - sx2, py_ - sy2)) / local_mps)
        probe_s.append(float(best))

    # ---------- distance from any road (for the gaps) ----------
    def sample(seg_mask):
        """Points every half cell along the chosen segments: (segment index, fraction, x, y)."""
        idx = np.nonzero(seg_mask)[0]
        n = np.maximum(1, np.ceil(seg_m[idx] / (cell / 2))).astype(np.int64)
        si = np.repeat(idx, n)
        k = np.arange(len(si)) - np.repeat(np.cumsum(n) - n, n)
        f = (k + 0.5) / np.repeat(n, n)
        x = nx[a[si]] + (nx[b[si]] - nx[a[si]]) * f
        y = ny[a[si]] + (ny[b[si]] - ny[a[si]]) * f
        return si, f, x, y

    road = np.zeros((grid.rows, grid.cols), bool)
    _, _, gx, gy = sample(gapseg)
    r, c, ok = grid.cell_of(gx, gy)
    road[r[ok], c[ok]] = True
    r, c, ok = grid.cell_of(nx[exit_node], ny[exit_node])
    road[r[ok], c[ok]] = True
    road_dist = ndimage.distance_transform_edt(~road) * cell
    valid = land & (road_dist <= tr["gap_km"] * 1000)

    # ---------- seed the grid from the roads ----------
    NC = grid.rows * grid.cols
    seed = np.full(NC, np.inf)
    si, f, sx_, sy_ = sample(exit_seg)
    tt = t[si]
    da, db = dnode[a[si]], dnode[b[si]]
    o = R["oneway"][way[si]]
    ts = np.where(o == 1, da + f * tt, np.where(o == -1, db + (1 - f) * tt, np.minimum(da + f * tt, db + (1 - f) * tt)))
    r, c, ok = grid.cell_of(sx_, sy_)
    np.minimum.at(seed, (r * grid.cols + c)[ok], ts[ok])
    en = np.nonzero(exit_node & np.isfinite(dnode))[0]
    r, c, ok = grid.cell_of(nx[en], ny[en])
    np.minimum.at(seed, (r * grid.cols + c)[ok], dnode[en][ok])
    for lat, lon in starts:  # the start cell itself
        sx, sy = proj(lon, lat)
        r, c, ok = grid.cell_of(np.array([sx]), np.array([sy]))
        if ok[0]:
            seed[r[0] * grid.cols + c[0]] = 0.0

    # ---------- spread over the land between roads ----------
    flat = np.arange(NC).reshape(grid.rows, grid.cols)
    gs, gd, gw = [], [], []
    for dr, dc in ((0, 1), (1, 0), (1, 1), (1, -1)):
        r0, r1 = 0, grid.rows - dr
        c0, c1 = max(0, -dc), grid.cols - max(0, dc)
        A = valid[r0:r1, c0:c1] & valid[r0 + dr:r1 + dr, c0 + dc:c1 + dc]
        s_ = flat[r0:r1, c0:c1][A]
        d_ = flat[r0 + dr:r1 + dr, c0 + dc:c1 + dc][A]
        step = cell * (np.sqrt(2) if dr and dc else 1.0) / local_mps
        gs += [s_, d_]
        gd += [d_, s_]
        gw += [np.full(len(s_), step)] * 2
    vf = valid.ravel()
    sc = np.nonzero(np.isfinite(seed) & vf)[0]
    gs.append(np.full(len(sc), NC))
    gd.append(sc)
    gw.append(seed[sc] + 0.01)
    GG = csr_matrix((np.concatenate(gw), (np.concatenate(gs), np.concatenate(gd))), shape=(NC + 1, NC + 1))
    T = dijkstra(GG, directed=True, indices=NC)[:NC].reshape(grid.rows, grid.cols)
    T[~valid] = np.inf
    log(f"Time surface on a {grid.cols}×{grid.rows} grid ({time.time() - t0:.0f} s)")

    reach = np.isfinite(T) & focus_mask
    far = float(T[reach].max()) if reach.any() else 0.0

    # roads to draw, by weight, limited to the frame
    fx0, fx1 = grid.x0, grid.x0 + grid.cols * cell
    fy0, fy1 = grid.ytop - grid.rows * cell, grid.ytop
    inside = (np.maximum(nx[a], nx[b]) >= fx0) & (np.minimum(nx[a], nx[b]) <= fx1) & \
             (np.maximum(ny[a], ny[b]) >= fy0) & (np.minimum(ny[a], ny[b]) <= fy1)
    roads = {}
    for name, group in (("motorway", ["motorway", "trunk"]), ("primary", ["primary"]),
                        ("secondary", ["secondary", "tertiary"])):
        m = inside & np.isin(cls, [CLS[g] for g in group])
        roads[name] = np.column_stack([nx[a[m]], ny[a[m]], nx[b[m]], ny[b[m]]])
    return {"T": T, "valid": valid, "far_s": far, "roads": roads, "probe_s": probe_s}
