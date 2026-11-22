"""Poster layout and drawing with matplotlib. Bands, coastlines and roads are vectors in the PDF."""
import math

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
from matplotlib import font_manager  # noqa: E402
from matplotlib.collections import LineCollection  # noqa: E402
from matplotlib.colors import to_rgb  # noqa: E402
from matplotlib.patches import PathPatch, Rectangle  # noqa: E402
from matplotlib.path import Path as MPath  # noqa: E402
from scipy import ndimage  # noqa: E402

PALETTES = {
    "ember": ["#fff1b8", "#ffd56e", "#f9ab4a", "#ee7c3b", "#d94f45", "#b5335f", "#872f77", "#5a3682",
              "#363f7f", "#22537a", "#1b6c73", "#24835f"],
    "tide": ["#f2fbbd", "#c3e6a0", "#82cc9e", "#45b0a5", "#2a8fa8", "#2c6da3", "#354e94", "#3b357a", "#3a2360"],
    "heath": ["#fbe8f0", "#f4c0d6", "#ea95bd", "#d76ba5", "#b84d8f", "#90397c", "#683067", "#46264f", "#2b1c36"],
}
INK = "#1d2430"
INK_SOFT = "#5b6573"
PAPER = "#fbfbf8"
WATER = "#dfe6ea"
SHORE = "#a9b7c1"
LAND_IN = "#eeeeea"
LAND_OUT = "#f3f3f0"



def layout(cfg, has_landmarks=False):
    """Inches: figure size, map box (left, bottom, width, height), and block heights."""
    W, H = float(cfg["poster"]["width_in"]), float(cfg["poster"]["height_in"])
    s = min(W, H)
    m = 0.055 * s
    title_h = 0.135 * s
    foot_h = (0.14 if has_landmarks else 0.125) * s
    return {"W": W, "H": H, "m": m, "s": s, "title_h": title_h, "foot_h": foot_h,
            "map": (m, m + foot_h, W - 2 * m, H - 2 * m - title_h - foot_h)}


def fit_frame(bounds, box_w, box_h, margin_m):
    """Grow the focus bounds (projected meters) to the map box's aspect ratio."""
    x0, y0, x1, y1 = bounds
    x0, y0, x1, y1 = x0 - margin_m, y0 - margin_m, x1 + margin_m, y1 + margin_m
    w, h = x1 - x0, y1 - y0
    target = box_w / box_h
    if w / h < target:
        grow = (h * target - w) / 2
        x0, x1 = x0 - grow, x1 + grow
    else:
        grow = (w / target - h) / 2
        y0, y1 = y0 - grow, y1 + grow
    return x0, y0, x1, y1


def setup_fonts(files):
    for f in files:
        try:
            font_manager.fontManager.addfont(str(f))
        except Exception:
            pass
    have = {f.name for f in font_manager.fontManager.ttflist}
    display = "Barlow Condensed" if "Barlow Condensed" in have else "DejaVu Sans"
    body = "Barlow" if "Barlow" in have else "DejaVu Sans"
    plt.rcParams["pdf.fonttype"] = 42  # embed TrueType so text stays editable and sharp
    return display, body


def palette_colors(name, n):
    stops = np.array([to_rgb(c) for c in PALETTES.get(name, PALETTES["ember"])])
    xs = np.linspace(0, 1, len(stops))
    t = np.linspace(0, 1, n) if n > 1 else np.array([0.0])
    return [tuple(np.interp(v, xs, stops[:, k]) for k in range(3)) for v in t]


def rings_path(polys, proj):
    verts, codes = [], []
    for rings, _holes in polys:
        for ring in rings:
            x, y = proj(ring[:, 0], ring[:, 1])
            v = np.column_stack([x, y])
            verts.append(v)
            codes.append(np.r_[MPath.MOVETO, np.full(len(v) - 2, MPath.LINETO), MPath.CLOSEPOLY])
    if not verts:
        return None
    return MPath(np.vstack(verts), np.concatenate(codes).astype(np.uint8))


def smooth_surface(T, sigma, land):
    """Gaussian-soften the finite part of T, then extend it a few cells into the water so the coast clip is crisp."""
    fin = np.isfinite(T)
    Z = np.where(fin, T, 0.0)
    if sigma > 0:
        num = ndimage.gaussian_filter(Z, sigma)
        den = ndimage.gaussian_filter(fin.astype(float), sigma)
        Z = np.where(fin, num / np.maximum(den, 1e-9), 0.0)
    out = np.where(fin, Z, np.nan)
    water = ~land.astype(bool)
    dist, (ri, ci) = ndimage.distance_transform_edt(~fin, return_indices=True)
    near = water & (dist <= 4) & ~fin
    out[near] = Z[ri[near], ci[near]]
    return out


def fmt_duration(sec):
    if not np.isfinite(sec):
        return "out of reach"
    m = int(round(sec / 60))
    if m < 60:
        return f"{m} min"
    return f"{m // 60} h {m % 60:02d}"


def dur_words(sec):
    m = int(round(sec / 60))
    h, mm = divmod(m, 60)
    parts = ([f"{h} hour" + ("s" if h != 1 else "")] if h else []) + \
        ([f"{mm} minute" + ("s" if mm != 1 else "")] if mm else [])
    return " ".join(parts) or "0 minutes"


def fmt_tick(sec, max_s):
    if sec == 0:
        return "start"
    m = int(round(sec / 60))
    if max_s <= 2 * 3600:
        return f"{m} min"
    return f"{m // 60} h" if m % 60 == 0 else f"{m // 60} h {m % 60:02d}"


def render(res, cfg, ctx, out_base):
    P = cfg["poster"]
    L = ctx["layout"]
    display, body = ctx["fonts"]
    proj, grid = ctx["proj"], ctx["grid"]
    x0, y0, x1, y1 = ctx["frame"]
    s = L["s"]
    lw = s / 24

    band_s, min_s, max_s, major_s = ctx["band_s"], ctx["min_s"], ctx["max_s"], ctx["major_s"]
    levels = np.arange(min_s, max_s + band_s / 2, band_s)
    n_bands = len(levels) - 1
    cols = palette_colors(P["palette"], n_bands)

    fig = plt.figure(figsize=(L["W"], L["H"]), facecolor=PAPER)
    mx, my, mw, mh = L["map"]
    ax = fig.add_axes([mx / L["W"], my / L["H"], mw / L["W"], mh / L["H"]])
    ax.set_xlim(x0, x1)
    ax.set_ylim(y0, y1)
    ax.set_aspect("equal")
    ax.axis("off")
    ax.add_patch(Rectangle((x0, y0), x1 - x0, y1 - y0, facecolor=WATER, edgecolor="none", zorder=0))

    focus = ctx["focus_polys"]
    land_path = rings_path(ctx["land_polys"] + ctx["canada_polys"], proj)
    us_path = rings_path(ctx["land_polys"], proj)
    canada_path = rings_path(ctx["canada_polys"], proj)
    focus_path = rings_path(focus, proj) if focus else None
    lake_path = rings_path(ctx["lake_polys"], proj)
    open_path = rings_path(ctx["open_water_polys"], proj)
    county_path = rings_path(ctx["county_polys"], proj) if ctx["county_polys"] else None

    def patch(path, **kw):
        p = PathPatch(path, **kw)
        ax.add_patch(p)
        return p

    land_patch = patch(land_path, facecolor=LAND_OUT if focus else LAND_IN, edgecolor="none", zorder=1) \
        if land_path is not None else None
    focus_patch = patch(focus_path, facecolor=LAND_IN, edgecolor="none", zorder=1.1) if focus_path is not None \
        else None

    Z = smooth_surface(np.where(res["T"] <= max_s, res["T"], np.inf), P["smooth_cells"], ctx["land"])
    Z = np.maximum(Z, min_s)  # anything nearer than the first band (outside the view) takes its color
    xs, ys = grid.centers()
    Zm = np.ma.masked_invalid(Z[::-1])
    yv = ys[::-1]
    maj = [lv for lv in levels[1:] if abs(lv / major_s - round(lv / major_s)) < 1e-6]

    def bands(clip, alpha, z):
        if np.ma.count(Zm) == 0:
            return
        cs = ax.contourf(xs, yv, Zm, levels=levels, colors=cols, alpha=alpha, zorder=z, antialiased=True)
        cs.set_clip_path(clip)
        minor = ax.contour(xs, yv, Zm, levels=levels[1:], colors=[INK], linewidths=0.25 * lw,
                           alpha=0.28 * alpha, zorder=z + 0.1)
        minor.set_clip_path(clip)
        if maj:
            cm = ax.contour(xs, yv, Zm, levels=maj, colors=[INK], linewidths=0.9 * lw, alpha=0.75 * alpha,
                            zorder=z + 0.2)
            cm.set_clip_path(clip)

    if land_patch is not None:
        if focus_patch is not None:
            if P["outside_opacity"] > 0:
                bands(land_patch, P["outside_opacity"], 2)
            bands(focus_patch, 1.0, 3)
        else:
            bands(land_patch, 1.0, 3)

    # water, borders and roads
    if lake_path is not None:
        patch(lake_path, facecolor=WATER, edgecolor=SHORE, linewidth=0.3 * lw, zorder=4)
    if canada_path is not None and open_path is not None:
        canada_clip = PathPatch(canada_path, facecolor="none", edgecolor="none", transform=ax.transData)
        lakes_ca = patch(open_path, facecolor=WATER, edgecolor=SHORE, linewidth=0.3 * lw, zorder=4)
        lakes_ca.set_clip_path(canada_clip)
    if county_path is not None:
        patch(county_path, facecolor="none", edgecolor=INK_SOFT, linewidth=0.3 * lw, alpha=0.45,
              linestyle=(0, (4, 3)), zorder=4.5)
    if us_path is not None:
        patch(us_path, facecolor="none", edgecolor=SHORE, linewidth=0.4 * lw, zorder=5)
    if focus_path is not None:
        patch(focus_path, facecolor="none", edgecolor="#6f8292", linewidth=0.8 * lw, zorder=5.1)

    road_style = {"motorway": (0.6, 0.5), "primary": (0.38, 0.4), "secondary": (0.22, 0.3)}
    for name in ctx["roads"]:
        seg = res["roads"].get(name)
        if seg is None or not len(seg):
            continue
        w_, a_ = road_style[name]
        ax.add_collection(LineCollection(seg.reshape(-1, 2, 2), colors=INK, linewidths=w_ * lw, alpha=a_,
                                         zorder=6, capstyle="round"))

    # markers
    for (sx, sy) in ctx["start_xy"]:
        ax.scatter([sx], [sy], s=(0.42 * s) ** 2, color=PAPER, edgecolors=INK, linewidths=1.6 * lw, zorder=9)
        ax.scatter([sx], [sy], s=(0.18 * s) ** 2, color=INK, linewidths=0, zorder=10)
    for lm in ctx["landmarks"]:
        ax.scatter([lm["xy"][0]], [lm["xy"][1]], marker="D", s=(0.3 * s) ** 2, color=INK, edgecolors=PAPER,
                   linewidths=1.2 * lw, zorder=9)

    # labels: starts first, then landmarks, then towns, each avoiding what is already placed
    fig.canvas.draw()
    renderer = fig.canvas.get_renderer()
    taken = []
    inside = ax.get_window_extent(renderer)

    def fits(bb):
        return (not any(bb.overlaps(o) for o in taken) and inside.contains(bb.x0, bb.y0)
                and inside.contains(bb.x1, bb.y1))

    for (sx, sy), pin in zip(ctx["start_xy"], ctx["pin_names"]):
        tt = ax.text(sx, sy, "   " + pin, fontsize=0.62 * s, fontfamily=display, fontweight="semibold",
                     color=INK, va="center", ha="left", zorder=10)
        taken.append(tt.get_window_extent(renderer).expanded(1.1, 1.4))

    off = 0.32 * s  # points
    spots = [((off, 0), "left", "center"), ((-off, 0), "right", "center"),
             ((0, off * 1.1), "center", "bottom"), ((0, -off * 1.1), "center", "top")]
    for lm in ctx["landmarks"]:
        text = f"{lm['name']}  {fmt_duration(lm['seconds'])}"
        placed = None
        for (dx, dy), ha, va in spots:
            t_ = ax.annotate(text, lm["xy"], xytext=(dx, dy), textcoords="offset points", ha=ha, va=va,
                             fontsize=0.5 * s, fontfamily=body, fontweight="semibold", color=INK, zorder=10)
            bb = t_.get_window_extent(renderer).expanded(1.06, 1.3)
            if fits(bb):
                placed = bb
                break
            t_.remove()
        if placed is None:  # crowded: keep it to the right anyway
            t_ = ax.annotate(text, lm["xy"], xytext=(off, 0), textcoords="offset points", ha="left", va="center",
                             fontsize=0.5 * s, fontfamily=body, fontweight="semibold", color=INK, zorder=10)
            placed = t_.get_window_extent(renderer)
        taken.append(placed)

    towns = []
    for (x, y, name, pop, infocus) in ctx["places"]:
        if (infocus and pop >= ctx["min_pop"]) or pop >= P["context_label_min_population"]:
            towns.append((pop, x, y, name, pop >= 100000))
    towns.sort(key=lambda p: -p[0])
    kept = []
    for (_, x, y, name, big) in towns:
        if not (x0 <= x <= x1 and y0 <= y <= y1):
            continue
        near_pin = any(name.lower() in pin.lower() and np.hypot(x - sx, y - sy) < 0.05 * (x1 - x0)
                       for (sx, sy), pin in zip(ctx["start_xy"], ctx["pin_names"]))
        if near_pin:  # the start label already names it
            continue
        txt = ax.text(x, y, "  " + name, fontsize=0.36 * s * (1.15 if big else 1.0), fontfamily=body,
                      color=INK, va="center", ha="left", zorder=8, fontweight="medium" if big else "normal")
        bb = txt.get_window_extent(renderer).expanded(1.08, 1.25)
        if not fits(bb):
            txt.remove()
            continue
        taken.append(bb)
        kept.append((x, y))
    if kept:
        kx, ky = zip(*kept)
        ax.scatter(kx, ky, s=(0.36 * s * 0.32) ** 2, color=INK, zorder=8, linewidths=0)

    # ---------- title block ----------
    m = L["m"]
    W, H = L["W"], L["H"]
    top = H - m
    fig.text(m / W, top / H, ctx["title"].upper(), fontsize=4.1 * s, fontfamily=display, fontweight="semibold",
             color=INK, va="top", ha="left")
    fig.text(m / W, (top - 0.078 * s) / H, ctx["subtitle"], fontsize=1.25 * s, fontfamily=body,
             color=INK_SOFT, va="top", ha="left")
    lat, lon = ctx["start_ll"][0]
    coord = f"{abs(lat):.4f}° {'N' if lat >= 0 else 'S'}   {abs(lon):.4f}° {'E' if lon >= 0 else 'W'}"
    fig.text((W - m) / W, top / H, coord, fontsize=0.7 * s, fontfamily=body, color=INK_SOFT, va="top", ha="right")

    # ---------- legend ----------
    top_f = m + L["foot_h"] - 0.0125 * s
    leg_w = 0.58 * (W - 2 * m)
    leg_h = 0.022 * s
    bar_top = top_f - 0.016 * s
    fig.text(m / W, top_f / H, "DRIVING TIME", fontsize=0.5 * s, fontfamily=body, fontweight="semibold",
             color=INK, va="top", ha="left")
    lax = fig.add_axes([m / W, (bar_top - leg_h) / H, leg_w / W, leg_h / H])
    lax.set_xlim(min_s, max_s)
    lax.set_ylim(0, 1)
    lax.axis("off")
    for i in range(n_bands):
        lax.add_patch(Rectangle((levels[i], 0), levels[i + 1] - levels[i], 1, facecolor=cols[i], edgecolor="none"))
        lax.plot([levels[i + 1]] * 2, [0, 1], color=PAPER, linewidth=0.4 * lw)
    tick = major_s
    while (max_s - min_s) / tick > 10:
        tick *= 2
    first = math.ceil(min_s / tick - 1e-9) * tick
    for x in sorted({min_s, *np.arange(first, max_s + 1e-6, tick)}):
        if x != min_s and x - min_s < 0.4 * tick:
            continue
        lax.plot([x, x], [-0.25, 0], color=INK, linewidth=0.6 * lw, clip_on=False)
        lax.text(x, -0.45, fmt_tick(x, max_s), fontsize=0.55 * s, fontfamily=body, color=INK, ha="center",
                 va="top", clip_on=False)
    gap = cfg["travel"]["gap_km"]
    notes = (f"Each band is {dur_words(band_s)} of driving; heavier lines every {dur_words(major_s)}.\n"
             f"Uncolored land is more than {gap:g} km from a public road or out of reach.\n"
             "Free-flow speeds: no traffic, weather, stops or ferries.")
    fig.text(m / W, (bar_top - leg_h - 0.03 * s) / H, notes, fontsize=0.45 * s, fontfamily=body,
             color=INK_SOFT, va="top", ha="left", linespacing=1.5)

    # ---------- landmark drive times ----------
    lms = sorted(ctx["landmarks"], key=lambda d: d["seconds"])
    if lms:
        cx0 = m + leg_w + 0.05 * s
        fig.text(cx0 / W, top_f / H, "DRIVE TIMES", fontsize=0.5 * s, fontfamily=body, fontweight="semibold",
                 color=INK, va="top", ha="left")
        fs = 0.5 * s
        line_h = fs / 72 * 1.6
        row_top = top_f - 0.016 * s
        rows = max(1, int((row_top - m * 0.9) / line_h))
        ncol = 1 if len(lms) <= rows else 2
        cap = rows * ncol
        shown = lms if len(lms) <= cap else lms[:cap - 1]
        col_w = (W - m - cx0) / ncol
        for i, lm in enumerate(shown):
            c_, r_ = divmod(i, rows)
            xl = cx0 + c_ * col_w
            yy = row_top - r_ * line_h
            name = lm["name"] if len(lm["name"]) <= 26 else lm["name"][:25] + "…"
            fig.text(xl / W, yy / H, name, fontsize=fs, fontfamily=body, color=INK, va="top", ha="left")
            fig.text((xl + col_w - 0.03 * s) / W, yy / H, fmt_duration(lm["seconds"]), fontsize=fs,
                     fontfamily=body, fontweight="semibold", color=INK, va="top", ha="right")
        if len(shown) < len(lms):
            c_, r_ = divmod(len(shown), rows)
            fig.text((cx0 + c_ * col_w) / W, (row_top - r_ * line_h) / H, f"+ {len(lms) - len(shown)} more",
                     fontsize=fs, fontfamily=body, color=INK_SOFT, va="top", ha="left")

    credit = ("Roads © OpenStreetMap contributors (ODbL)  ·  State and county outlines: U.S. Census Bureau  ·  "
              "Lakes and provinces: Natural Earth")
    fig.text(m / W, m * 0.55 / H, credit, fontsize=0.36 * s, fontfamily=body, color=INK_SOFT, va="bottom",
             ha="left")

    out_base.parent.mkdir(parents=True, exist_ok=True)
    pdf = out_base.with_suffix(".pdf")
    fig.savefig(pdf, facecolor=PAPER)
    png = out_base.with_suffix(".png")
    fig.savefig(png, dpi=P["preview_dpi"], facecolor=PAPER)
    files = [pdf, png]
    if P.get("png_dpi"):
        big = out_base.with_name(out_base.name + f"-{P['png_dpi']}dpi.png")
        fig.savefig(big, dpi=P["png_dpi"], facecolor=PAPER)
        files.append(big)
    plt.close(fig)
    return files
