"""Turn a variant definition (inputs/corridor.yaml) into footprint components.

Component types and the land take they stand for (ILLUSTRATIVE assumptions, see the README):
  station_box   permanent_surface        cut-and-cover box, needs the surface (and the column below it)
  bored_tunnel  permanent_subterranean   twin tubes under the surface; needs a stratum, not the surface
  worksite      temporary_surface        construction area beside a box, returned after the works
"""
from __future__ import annotations

import geopandas as gpd
import numpy as np

from . import config, geometry

TAKE = {"station_box": "permanent_surface", "bored_tunnel": "permanent_subterranean", "worksite": "temporary_surface"}


def build_variant(key: str, spec: dict, geo: dict) -> tuple[geometry.Alignment, gpd.GeoDataFrame]:
    al = geometry.fillet([tuple(p) for p in spec["pis"]], geo["curve_radius_m"])
    L, W = geo["station_box"]["length_m"], geo["station_box"]["width_m"]
    boxes = geometry.station_boxes(al, L, W)
    tw = geometry.twin_tube_outer_width(geo["bored_tunnel"]["tube_outer_diameter_m"],
                                        geo["bored_tunnel"]["tube_centre_spacing_m"])
    tunnel = geometry.tunnel_footprint(al, L, al.line.length - L, tw)
    b0 = geometry.bearing(al.pis[0], al.pis[1])
    bn = geometry.bearing(al.pis[-2], al.pis[-1])
    ws = geo["worksite"]
    extra_launch = geo.get("launch_worksite_extra_width_m", 0.0)
    ws_s = geometry.worksite(boxes["south"], b0, spec["worksite_side"]["south"], ws["width_m"] + extra_launch,
                             ws["extra_length_m"], L, W)
    ws_n = geometry.worksite(boxes["north"], bn, spec["worksite_side"]["north"], ws["width_m"],
                             ws["extra_length_m"], L, W)
    rows = [
        ("BOX-S", "station_box", boxes["south"]),
        ("BOX-N", "station_box", boxes["north"]),
        ("TUN", "bored_tunnel", tunnel),
        ("WS-S", "worksite", ws_s),
        ("WS-N", "worksite", ws_n),
    ]
    gdf = gpd.GeoDataFrame(
        {"variant": key, "component_id": [f"{key}-{r[0]}" for r in rows], "component_type": [r[1] for r in rows],
         "take": [TAKE[r[1]] for r in rows]},
        geometry=[r[2] for r in rows], crs=config.SVY21)
    return al, gdf


def all_variants(cfg: dict | None = None) -> dict[str, tuple[geometry.Alignment, gpd.GeoDataFrame]]:
    cfg = cfg or config.corridor()
    return {k: build_variant(k, v, cfg["geometry"]) for k, v in cfg["variants"].items()}


def railway_structure(components: gpd.GeoDataFrame):
    """Plan outline of the (fictional) railway: the permanent components (boxes and tunnels)."""
    perm = components[components["take"].isin(["permanent_surface", "permanent_subterranean"])]
    return perm.geometry.union_all()


def tunnel_levels(geo: dict) -> tuple[float, float]:
    """(crown, invert) levels of the tubes in metres SHD."""
    crown = float(geo["tunnel_crown_level_m_shd"])
    return crown, crown - float(geo["bored_tunnel"]["tube_outer_diameter_m"])


def alignment_summary(al: geometry.Alignment) -> dict:
    return {"length_m": al.length, "n_curves": len(al.arcs),
            "deflections_deg": [float(np.degrees(a.deflection)) for a in al.arcs]}
