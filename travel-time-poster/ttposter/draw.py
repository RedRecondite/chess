"""Poster layout and drawing with matplotlib. Bands, coastlines and roads are vectors in the PDF."""
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

NUMBER_WORDS = ["Zero", "One", "Two", "Three", "Four", "Five", "Six", "Seven", "Eight", "Nine", "Ten",
                "Eleven", "Twelve"]


def layout(cfg):
    """Inches: figure size, map box (left, bottom, width, height), and block heights."""
    W, H = float(cfg["poster"]["width_in"]), float(cfg["poster"]["height_in"])
    s = min(W, H)
    m = 0.055 * s
    title_h = 0.135 * s
    foot_h = 0.125 * s
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


def render(res, cfg, ctx, out_base):
    P = cfg["poster"]
    tr = cfg["travel"]
    L = ctx["layout"]
    display, body = ctx["fonts"]
    proj, grid = ctx["proj"], ctx["grid"]
    x0, y0, x1, y1 = ctx["frame"]
    s = L["s"]

    band_s = tr["band_minutes"] * 60
    max_s = ctx["max_s"]
    levels = np.arange(0, max_s + band_s / 2, band_s)
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

    focus_path = rings_path(ctx["focus_polys"], proj)
    canada_path = rings_path(ctx["canada_polys"], proj)
    other_path = rings_path(ctx["other_polys"] + ctx["canada_polys"], proj)
    lake_path = rings_path(ctx["lake_polys"], proj)
    open_path = rings_path(ctx["open_water_polys"], proj)

    def patch(path, **kw):
        p = PathPatch(path, **kw)
        ax.add_patch(p)
        return p

    if other_path is not None:
        other_patch = patch(other_path, facecolor=LAND_OUT, edgecolor="none", zorder=1)
    focus_patch = patch(focus_path, facecolor=LAND_IN, edgecolor="none", zorder=1)

    Z = smooth_surface(np.where(res["T"] <= max_s, res["T"], np.inf), P["smooth_cells"], ctx["land"])
    xs, ys = grid.centers()
    Zm = np.ma.masked_invalid(Z[::-1])
    yv = ys[::-1]

    def bands(clip, alpha, z):
        cs = ax.contourf(xs, yv, Zm, levels=levels, colors=cols, alpha=alpha, zorder=z, antialiased=True)
        cs.set_clip_path(clip)
        minor = ax.contour(xs, yv, Zm, levels=levels[1:], colors=[INK], linewidths=0.25 * s / 24,
                           alpha=0.28 * alpha, zorder=z + 0.1)
        minor.set_clip_path(clip)
        major_s = tr["major_every_hours"] * 3600
        maj = [lv for lv in levels[1:] if abs(lv / major_s - round(lv / major_s)) < 1e-6]
        if maj:
            cm = ax.contour(xs, yv, Zm, levels=maj, colors=[INK], linewidths=0.9 * s / 24, alpha=0.75 * alpha,
                            zorder=z + 0.2)
            cm.set_clip_path(clip)

    if other_path is not None and P["outside_opacity"] > 0:
        bands(other_patch, P["outside_opacity"], 2)
    bands(focus_patch, 1.0, 3)

    lw = s / 24
    if lake_path is not None:
        patch(lake_path, facecolor=WATER, edgecolor=SHORE, linewidth=0.3 * lw, zorder=4)
    if canada_path is not None:
        if open_path is not None:
            canada_clip = PathPatch(canada_path, facecolor="none", edgecolor="none", transform=ax.transData)
            lakes_ca = patch(open_path, facecolor=WATER, edgecolor=SHORE, linewidth=0.3 * lw, zorder=4)
            lakes_ca.set_clip_path(canada_clip)
    us_other = rings_path(ctx["other_polys"], proj)
    if us_other is not None:
        patch(us_other, facecolor="none", edgecolor=SHORE, linewidth=0.35 * lw, zorder=5)
    patch(focus_path, facecolor="none", edgecolor="#7d8f9c", linewidth=0.7 * lw, zorder=5)

    if P["draw_highways"] and len(res["highways"]):
        h = res["highways"]
        ax.add_collection(LineCollection(h.reshape(-1, 2, 2), colors=INK, linewidths=0.55 * lw, alpha=0.5,
                                         zorder=6, capstyle="round"))
    if len(res["ferries"]):
        f = res["ferries"]
        ax.add_collection(LineCollection(f.reshape(-1, 2, 2), colors=INK_SOFT, linewidths=0.6 * lw,
                                         linestyles=(0, (3, 3)), alpha=0.8, zorder=6))

    # start point(s)
    for (sx, sy) in ctx["start_xy"]:
        ax.scatter([sx], [sy], s=(0.42 * s) ** 2, color=PAPER, edgecolors=INK, linewidths=1.6 * lw, zorder=9)
        ax.scatter([sx], [sy], s=(0.18 * s) ** 2, color=INK, linewidths=0, zorder=10)

    # labels
    fig.canvas.draw()
    renderer = fig.canvas.get_renderer()
    taken = []
    for (sx, sy), pin in zip(ctx["start_xy"], ctx["pin_names"]):
        tt = ax.text(sx, sy, "   " + pin, fontsize=0.62 * s, fontfamily=display, fontweight="semibold",
                     color=INK, va="center", ha="left", zorder=10)
        taken.append(tt.get_window_extent(renderer).expanded(1.1, 1.4))
    places = []
    for (x, y, name, pop, infocus) in ctx["places"]:
        if (infocus and pop >= P["label_min_population"]) or pop >= P["context_label_min_population"]:
            places.append((pop, x, y, name, pop >= 100000))
    places.sort(key=lambda p: -p[0])
    # towns, biggest first, skipping any that would collide with a label already placed
    kept = []
    for (_, x, y, name, big) in places:
        txt = ax.text(x, y, "  " + name, fontsize=0.36 * s * (1.15 if big else 1.0), fontfamily=body,
                      color=INK, va="center", ha="left", zorder=8, fontweight="medium" if big else "normal")
        bb = txt.get_window_extent(renderer).expanded(1.08, 1.25)
        if (any(bb.overlaps(o) for o in taken) or not ax.bbox.contains(bb.x0, bb.y0)
                or not ax.bbox.contains(bb.x1, bb.y1)):
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
    fmt = {"start": ctx["label"], "focus": cfg["region"]["focus"], "band": tr["band_minutes"]}
    title = P["title"].format(**fmt)
    subtitle = P["subtitle"].format(**fmt)
    top = H - m
    fig.text(m / W, top / H, title.upper(), fontsize=4.1 * s, fontfamily=display, fontweight="semibold",
             color=INK, va="top", ha="left")
    fig.text(m / W, (top - 0.078 * s) / H, subtitle, fontsize=1.25 * s, fontfamily=body, color=INK_SOFT,
             va="top", ha="left")
    lat, lon = ctx["start_ll"][0]
    coord = f"{abs(lat):.4f}° {'N' if lat >= 0 else 'S'}   {abs(lon):.4f}° {'E' if lon >= 0 else 'W'}"
    fig.text((W - m) / W, top / H, coord, fontsize=0.7 * s, fontfamily=body, color=INK_SOFT, va="top", ha="right")

    # ---------- legend ----------
    leg_w = 0.62 * (W - 2 * m)
    leg_h = 0.022 * s
    leg_y = m + 0.042 * s
    lax = fig.add_axes([m / W, leg_y / H, leg_w / W, leg_h / H])
    lax.set_xlim(0, max_s)
    lax.set_ylim(0, 1)
    lax.axis("off")
    for i in range(n_bands):
        lax.add_patch(Rectangle((levels[i], 0), levels[i + 1] - levels[i], 1, facecolor=cols[i], edgecolor="none"))
        lax.plot([levels[i + 1]] * 2, [0, 1], color=PAPER, linewidth=0.4 * lw)
    hrs = max_s / 3600
    step_h = 1 if hrs <= 8 else 2
    for hh in np.arange(0, hrs + 1e-6, step_h):
        x = hh * 3600
        lax.plot([x, x], [-0.25, 0], color=INK, linewidth=0.6 * lw, clip_on=False)
        lax.text(x, -0.45, f"{int(hh)} h" if hh else "start", fontsize=0.55 * s, fontfamily=body, color=INK,
                 ha="center", va="top", clip_on=False)
    fig.text(m / W, (leg_y + leg_h + 0.014 * s) / H, "DRIVING TIME", fontsize=0.5 * s, fontfamily=body,
             fontweight="semibold", color=INK, va="bottom", ha="left")

    gap = tr["gap_km"]
    notes = (f"Each band is {tr['band_minutes']} minutes of driving; heavier lines every "
             f"{tr['major_every_hours']} hours.\nUncolored land is more than {gap:g} km from a public road "
             f"or out of reach.\nFree-flow speeds: no traffic, weather or stops.")
    fig.text((m + leg_w + 0.05 * s) / W, (leg_y + leg_h + 0.03 * s) / H, notes, fontsize=0.48 * s,
             fontfamily=body, color=INK_SOFT, va="top", ha="left", linespacing=1.5)
    credit = ("Roads © OpenStreetMap contributors (ODbL)  ·  State outlines: U.S. Census Bureau  ·  "
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
