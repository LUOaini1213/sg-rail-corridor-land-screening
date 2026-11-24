"""Build the committed study-area extract (data/study_area/study_area.gpkg) from the raw downloads.

Only the attributes the screening needs are kept. Fields that carry names or addresses (SLA managing-agent
names, State-land asset descriptions, block numbers, street names, postal codes) are dropped here and never
reach the repository. Cadastral lots, airspace lots and building footprints are kept whole (so their areas
stay true); the other layers are clipped to the study box.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import geopandas as gpd
from shapely.geometry import box

from . import config

# layer name -> (raw key, file, columns kept, clip to box?)
LAYERS = {
    "lots": ("sla_cadastral", "sla_cadastral_land_parcel.geojson", ["LOT_KEY"], False),
    "airspace_lots": ("sla_airspace", "sla_cadastral_airspace_parcel.geojson", ["LOT_KEY"], False),
    "land_use": ("mp25_land_use", "mp25_land_use_amended.geojson", ["OBJECTID", "LU_DESC", "GPR"], True),
    "mp_buildings": ("mp25_building", "mp25_building.geojson", ["OBJECTID", "BLDG_TYPE"], False),
    "state_land_vacant": ("sla_vacant_state_land", "sla_vacant_state_land.geojson", ["OBJECTID", "CATEGORY"], True),
    "state_land_agent": ("sla_managing_agent", "sla_managing_agent.geojson", ["OBJECTID"], True),
    "state_reserve": ("sla_state_reserve", "sla_state_reserve.geojson", ["OBJECTID", "LOT_KEY"], True),
    "rail_lines": ("mp25_rail_line", "mp25_rail_line_amended.geojson", ["OBJECTID", "GRND_LEVEL", "RAIL_TYPE"], True),
    "rail_stations": ("mp25_rail_station", "mp25_rail_station_amended.geojson", ["OBJECTID", "NAME", "GRND_LEVEL", "RAIL_TYPE"], False),
    "station_exits": ("lta_station_exit", "lta_mrt_station_exit.geojson", ["OBJECTID", "STATION_NA", "EXIT_CODE"], True),
    "underground_structures": ("mp25_underground", "mp25_underground_structure.geojson", ["OBJECTID"], True),
}


def _read(raw: Path, key: str, fname: str, cols: list[str], clip: bool) -> gpd.GeoDataFrame:
    s, w, n, e = config.study_area_wgs84_bbox()
    pad = 0.002  # degrees; the SVY21 box is clipped exactly below
    gdf = gpd.read_file(raw / key / fname, bbox=(w - pad, s - pad, e + pad, n + pad), columns=cols)
    gdf = gdf.to_crs(config.SVY21)
    area = box(*config.study_area_box())
    gdf = gdf[gdf.intersects(area)].copy()
    if clip:
        gdf["geometry"] = gdf.geometry.intersection(area)
        gdf = gdf[~gdf.geometry.is_empty]
    return gdf[cols + ["geometry"]].reset_index(drop=True)


def _osm_buildings(raw: Path) -> gpd.GeoDataFrame:
    """Polygons from the Overpass 'out geom' response: closed ways, and outer rings of multipolygon relations."""
    from shapely.geometry import MultiPolygon, Polygon
    from shapely.ops import unary_union
    doc = json.loads((raw / "osm_buildings" / "osm_buildings.json").read_text(encoding="utf-8"))
    rows = []
    for el in doc["elements"]:
        tags = el.get("tags", {})
        if el["type"] == "way" and el.get("geometry"):
            pts = [(p["lon"], p["lat"]) for p in el["geometry"]]
            if len(pts) >= 4 and pts[0] == pts[-1]:
                rows.append({"osm_id": f"way/{el['id']}", "building": tags.get("building", "yes"), "geometry": Polygon(pts)})
        elif el["type"] == "relation":
            outers, inners = [], []
            for m in el.get("members", []):
                if m.get("type") != "way" or not m.get("geometry"):
                    continue
                pts = [(p["lon"], p["lat"]) for p in m["geometry"]]
                if len(pts) >= 4 and pts[0] == pts[-1]:
                    (outers if m.get("role") == "outer" else inners).append(Polygon(pts))
            if outers:
                geom = unary_union(outers)
                if inners:
                    geom = geom.difference(unary_union(inners))
                rows.append({"osm_id": f"relation/{el['id']}", "building": tags.get("building", "yes"), "geometry": geom})
    gdf = gpd.GeoDataFrame(rows, geometry="geometry", crs=config.WGS84).to_crs(config.SVY21)
    gdf["geometry"] = gdf.geometry.make_valid()
    gdf = gdf[gdf.intersects(box(*config.study_area_box()))]
    return gdf.reset_index(drop=True)


def build(raw: Path = config.RAW, out: Path = config.STUDY_GPKG) -> dict:
    out.parent.mkdir(parents=True, exist_ok=True)
    if out.exists():
        out.unlink()
    counts = {}
    for layer, (key, fname, cols, clip) in LAYERS.items():
        gdf = _read(raw, key, fname, cols, clip)
        if layer == "rail_stations":
            gdf["NAME"] = gdf["NAME"].str.strip().str.upper()
        gdf.to_file(out, layer=layer, driver="GPKG")
        counts[layer] = len(gdf)
    osm = _osm_buildings(raw)
    osm.to_file(out, layer="osm_buildings", driver="GPKG")
    counts["osm_buildings"] = len(osm)
    manifest = json.loads((config.DATA / "manifest.json").read_text(encoding="utf-8"))
    meta = {"study_area_svy21": list(config.study_area_box()), "layers": counts,
            "sources": {k: {"sha256": v["sha256"], "accessed": v["accessed"], "dataset_last_updated": v.get("dataset_last_updated"),
                            "osm_base": v.get("osm_base")} for k, v in manifest.items()}}
    (out.parent / "study_area.meta.json").write_text(json.dumps(meta, indent=2, sort_keys=True) + "\n",
                                                     encoding="utf-8", newline="\n")
    return counts


def sha256(path: Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()
