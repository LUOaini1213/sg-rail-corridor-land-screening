"""Topology and data-quality checks on the inputs and on the overlay results."""
from __future__ import annotations

import geopandas as gpd
import numpy as np
from shapely.geometry import box

from . import config


def invalid_geometries(gdf: gpd.GeoDataFrame) -> int:
    return int((~gdf.geometry.is_valid).sum() + gdf.geometry.is_empty.sum())


def duplicate_keys(gdf: gpd.GeoDataFrame, key: str) -> list[str]:
    d = gdf[key][gdf[key].duplicated(keep=False)]
    return sorted(set(d.astype(str)))


def overlaps(gdf: gpd.GeoDataFrame, key: str, tol_m2: float = 0.01) -> list[tuple[str, str, float]]:
    """Pairs of polygons whose interiors overlap by more than tol_m2 (each pair once)."""
    out = []
    geoms = gdf.geometry.values
    keys = gdf[key].astype(str).values
    left, right = gdf.sindex.query(geoms, predicate="intersects")
    for i, j in zip(left, right):
        if i >= j:
            continue
        a = geoms[i].intersection(geoms[j]).area
        if a > tol_m2:
            out.append((keys[i], keys[j], float(a)))
    return out


def coverage(gdf: gpd.GeoDataFrame, area_box: tuple[float, float, float, float]) -> dict:
    """Share of a box covered by the union of the polygons, and the uncovered (gap) area."""
    b = box(*area_box)
    covered = gdf.geometry.union_all().intersection(b).area
    return {"box_m2": float(b.area), "covered_m2": float(covered), "gap_m2": float(b.area - covered),
            "covered_share": float(covered / b.area)}


def crs_round_trip_error_m(points_xy: np.ndarray) -> float:
    """Largest distance (m) after SVY21 -> WGS84 -> SVY21 for the given SVY21 points."""
    fwd, inv = config.to_wgs84(), config.to_svy21()
    lon, lat = fwd.transform(points_xy[:, 0], points_xy[:, 1])
    x, y = inv.transform(lon, lat)
    return float(np.max(np.hypot(np.asarray(x) - points_xy[:, 0], np.asarray(y) - points_xy[:, 1])))


def building_cross_check(mp: gpd.GeoDataFrame, osm: gpd.GeoDataFrame, min_share: float = 0.5) -> dict:
    """How many URA Master Plan building footprints are matched by OpenStreetMap footprints.

    A Master Plan footprint counts as matched when OSM footprints cover at least min_share of its area.
    """
    osm_union = osm.geometry.union_all() if len(osm) else None
    matched = 0
    for g in mp.geometry:
        if osm_union is not None and g.area > 0 and g.intersection(osm_union).area / g.area >= min_share:
            matched += 1
    return {"mp_buildings": int(len(mp)), "matched_by_osm": int(matched),
            "share": float(matched / len(mp)) if len(mp) else float("nan"), "min_share": min_share}


def area_conservation(component_area: float, pieces: list[float], gap: float, tol: float = 0.01) -> bool:
    """Area of a component equals the sum of its pieces in each lot plus the part that lies in no lot."""
    return abs(component_area - (sum(pieces) + gap)) <= tol
