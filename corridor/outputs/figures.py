"""Static figures (PNG). Colour encodes only the take type, everywhere; variants are told apart by line
style and labels. Palette: first three slots of the validated reference palette (checked with the
dataviz validator, all pairs, light surface); the aqua slot is below 3:1 contrast, so every figure carries
a labelled legend and the numbers are also in tables (README, Excel schedule)."""
from __future__ import annotations

from pathlib import Path

import geopandas as gpd
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.lines import Line2D  # noqa: E402
from matplotlib.patches import Patch  # noqa: E402

from .. import config  # noqa: E402
from . import rel  # noqa: E402

TAKE_COLOURS = {"permanent_surface": "#2a78d6", "permanent_subterranean": "#eb6834", "temporary_surface": "#1baf7a"}
TAKE_LABELS = {"permanent_surface": "Permanent surface take (station boxes)",
               "permanent_subterranean": "Tunnel stratum (bored tunnels)",
               "temporary_surface": "Temporary occupation (worksites)"}
INK, INK2, MUTED, AXIS, SURFACE = "#0b0b0b", "#52514e", "#898781", "#c3c2b7", "#fcfcfb"
ROAD, LOTLINE, BUILDING = "#ecebe6", "#d5d4cd", "#c9c8c0"
STYLES = {"A": "-", "B": "--", "C": ":"}
BANNER = "ILLUSTRATIVE: fictional corridor, not a planned line; no real property is proposed for acquisition"


def _extent(full, pad=120.0):
    b = gpd.GeoSeries([r["components"].geometry.union_all() for r in full.values()], crs=config.SVY21).total_bounds
    return b[0] - pad, b[1] - pad, b[2] + pad, b[3] + pad


def _background(ax, study, ext, label_stations: bool = True):
    from shapely.geometry import box
    area = box(*ext)
    lu = study["land_use"]
    lu[lu["LU_DESC"] == "ROAD"].clip(area).plot(ax=ax, color=ROAD, linewidth=0)
    study["lots"].clip(area).boundary.plot(ax=ax, color=LOTLINE, linewidth=0.35)
    study["osm_buildings"].clip(area).plot(ax=ax, color=BUILDING, linewidth=0)
    study["rail_lines"].clip(area).plot(ax=ax, color=INK2, linewidth=1.1)
    st = study["rail_stations"]
    st.plot(ax=ax, facecolor="#e8e7e1", edgecolor=INK2, linewidth=0.8)
    if label_stations:
        for r in st.itertuples():
            b = r.geometry.bounds
            north = (b[1] + b[3]) / 2 > (ext[1] + ext[3]) / 2
            # label on the far side of the station from the corridor
            ax.annotate(f"{r.NAME.title()} station (existing)", ((b[0] + b[2]) / 2, b[3] if north else b[1]),
                        xytext=(0, 4 if north else -4), textcoords="offset points", ha="center",
                        va="bottom" if north else "top", fontsize=7.5, color=INK)


def _frame(ax, ext, scale_m=200):
    ax.set_xlim(ext[0], ext[2])
    ax.set_ylim(ext[1], ext[3])
    ax.set_aspect("equal")
    ax.set_xticks([])
    ax.set_yticks([])
    ax.set_xlabel("")
    ax.set_ylabel("")
    for s in ax.spines.values():
        s.set_color(AXIS)
        s.set_linewidth(0.6)
    x1, y0 = ext[2] - 30, ext[1] + 30
    ax.plot([x1 - scale_m, x1], [y0, y0], color=INK, linewidth=1.5, solid_capstyle="butt")
    ax.text(x1 - scale_m / 2, y0 + 12, f"{scale_m} m", ha="center", fontsize=7, color=INK)
    ax.annotate("N", xy=(ext[0] + 40, ext[3] - 40), xytext=(ext[0] + 40, ext[3] - 110), ha="center", fontsize=8,
                color=INK, arrowprops=dict(arrowstyle="-|>", color=INK, linewidth=0.8))


def overview(full, summary, study, path: Path) -> dict:
    ext = _extent(full)
    fig, ax = plt.subplots(figsize=(7.2, 9.6), facecolor=SURFACE)
    ax.set_facecolor(SURFACE)
    _background(ax, study, ext)
    handles = []
    for k, r in full.items():
        al = r["alignment"]
        xs, ys = al.line.xy
        ax.plot(xs, ys, linestyle=STYLES[k], color=INK, linewidth=1.6)
        boxes = r["components"][r["components"]["component_type"] == "station_box"]
        boxes.boundary.plot(ax=ax, color=INK, linewidth=0.8)
        mid = al.line.interpolate(0.55, normalized=True)
        ax.annotate(k, (mid.x, mid.y), xytext=(7, 0), textcoords="offset points", fontsize=10, fontweight="bold", color=INK)
        handles.append(Line2D([], [], color=INK, linestyle=STYLES[k], linewidth=1.6,
                              label=f"{k}: {summary[k]['label']} ({summary[k]['length_m']:,.0f} m)"))
    handles += [Line2D([], [], color=INK2, linewidth=1.1, label="Existing railway (Master Plan 2025, indicative)"),
                Patch(facecolor=BUILDING, label="Buildings (OpenStreetMap)"), Patch(facecolor=ROAD, label="Road zone (Master Plan 2025)"),
                Patch(facecolor=SURFACE, edgecolor=INK, label="Station boxes (150 m x 24 m)")]
    ax.legend(handles=handles, loc="upper center", bbox_to_anchor=(0.5, -0.01), ncol=2, fontsize=7, frameon=False)
    _frame(ax, ext)
    ax.set_title("Fictional link IL-1: three horizontal variants", fontsize=11, color=INK, loc="left")
    fig.text(0.01, 0.028, BANNER + ".", fontsize=6.5, color=INK2)
    fig.text(0.01, 0.01, "SVY21 / EPSG:3414. Data: URA, SLA, LTA via data.gov.sg (Singapore Open Data Licence v1.0); "
             "buildings (c) OpenStreetMap contributors (ODbL).", fontsize=6.5, color=INK2)
    fig.tight_layout(rect=(0, 0.045, 1, 1))
    fig.savefig(path, dpi=150, facecolor=SURFACE)
    plt.close(fig)
    return {"path": rel(path)}


def takes(full, summary, study, path: Path) -> dict:
    ext = _extent(full)
    fig, axs = plt.subplots(1, 3, figsize=(12.5, 6.4), facecolor=SURFACE)
    for ax, (k, r) in zip(axs, full.items()):
        ax.set_facecolor(SURFACE)
        _background(ax, study, ext, label_stations=False)
        sched = r["schedule"]
        lots = study["lots"][study["lots"]["LOT_KEY"].isin(sched.loc[sched["in_scope"], "LOT_KEY"])]
        p = r["pieces"]
        for take, col in TAKE_COLOURS.items():
            sub = p[p["take"] == take]
            if len(sub):
                sub.plot(ax=ax, color=col, edgecolor=SURFACE, linewidth=0.6)
        lots.boundary.plot(ax=ax, color=INK2, linewidth=0.5)
        for d, ring_key in ((6, "first_reserve"), (40, "protection_zone"), (60, "safety_zone")):
            outer = r["structure"].buffer(d, quad_segs=16).exterior
            ax.plot(*outer.xy, color=MUTED, linewidth=0.6, linestyle=(0, (3, 2)))
        s = summary[k]
        ax.set_title(f"{k}: {s['label']}\n{s['totals']['lots_in_scope']} lots with an interest, "
                     f"{s['zones']['within_protection_distance_lots']} lots within 40 m", fontsize=8.5, color=INK, loc="left")
        _frame(ax, ext)
    handles = [Patch(facecolor=c, label=TAKE_LABELS[t]) for t, c in TAKE_COLOURS.items()]
    handles += [Line2D([], [], color=INK2, linewidth=0.5, label="Lot with an interest (SLA cadastral, approximate)"),
                Line2D([], [], color=MUTED, linewidth=0.6, linestyle=(0, (3, 2)), label="6, 40 and 60 m from the structure"),
                Patch(facecolor="#e8e7e1", edgecolor=INK2, label="Existing stations: Bedok (south), Bedok Reservoir (north)")]
    fig.legend(handles=handles, loc="lower center", bbox_to_anchor=(0.5, 0.03), ncol=3, fontsize=7.5, frameon=False)
    fig.text(0.01, 0.005, BANNER + ".", fontsize=6, color=INK2)
    fig.tight_layout(rect=(0, 0.12, 1, 1))
    fig.savefig(path, dpi=150, facecolor=SURFACE)
    plt.close(fig)
    return {"path": rel(path)}


def comparison(summary, cmp, path: Path) -> dict:
    keys = list(summary)
    fig, (a1, a2) = plt.subplots(1, 2, figsize=(10.5, 3.4), facecolor=SURFACE, gridspec_kw={"width_ratios": [1.5, 1]})
    for ax in (a1, a2):
        ax.set_facecolor(SURFACE)
        for s in ("top", "right"):
            ax.spines[s].set_visible(False)
        for s in ("left", "bottom"):
            ax.spines[s].set_color(AXIS)
        ax.tick_params(colors=INK2, labelsize=8)
    y = range(len(keys))[::-1]
    left = [0.0] * len(keys)
    for take, col in TAKE_COLOURS.items():
        vals = [summary[k]["totals"][f"{take}_m2"] / 1000.0 for k in keys]
        a1.barh(list(y), vals, left=left, color=col, edgecolor=SURFACE, linewidth=1.0, height=0.55, label=TAKE_LABELS[take])
        left = [l + v for l, v in zip(left, vals)]
    for yy, tot in zip(y, left):
        a1.text(tot + 0.4, yy, f"{tot:,.1f}", va="center", fontsize=8, color=INK)
    a1.set_yticks(list(y), [f"{k}: {summary[k]['label']}" for k in keys], fontsize=8, color=INK)
    a1.set_xlabel("Land interest by type (thousand square metres, plan area)", fontsize=8, color=INK2)
    a1.legend(fontsize=7, frameon=False, loc="lower right", bbox_to_anchor=(1.0, 1.0), ncol=1)
    a1.xaxis.grid(True, color="#e1e0d9", linewidth=0.5)
    a1.set_axisbelow(True)
    tot = [cmp["total"][k] for k in keys]
    a2.barh(list(y), tot, color=INK2, height=0.55)
    share = cmp["random_weights_first_share"]
    for yy, k, t in zip(y, keys, tot):
        a2.text(t + 0.02, yy, f"{t:.2f}  (ranked first under {100 * share[k]:.1f}%\nof {cmp['random_weights_n']:,} random weightings)",
                va="center", fontsize=7, color=INK)
    a2.set_yticks(list(y), keys, fontsize=8, color=INK)
    a2.set_xlim(0, 2.0)
    a2.set_xticks([0, 0.5, 1.0])
    a2.set_xlabel("Weighted score (author's weights; 1 = best)", fontsize=8, color=INK2)
    fig.text(0.01, 0.01, BANNER + ".", fontsize=6, color=INK2)
    fig.tight_layout(rect=(0, 0.04, 1, 1))
    fig.savefig(path, dpi=150, facecolor=SURFACE)
    plt.close(fig)
    return {"path": rel(path)}


def make_all(full, summary, cmp, study, fig_dir: Path) -> dict:
    return {"overview": overview(full, summary, study, fig_dir / "overview.png"),
            "takes": takes(full, summary, study, fig_dir / "takes_by_variant.png"),
            "comparison": comparison(summary, cmp, fig_dir / "comparison.png")}
