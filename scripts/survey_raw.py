"""Island-wide facts that need the full downloads (data/raw/, see scripts/fetch_data.py); writes
results/raw_survey.json, which the documents quote. Not part of the offline pipeline.

1. How the two end stations of the fictional link were chosen. Pairs of operating MRT stations (those with
   exits in LTA's MRT Station Exit layer) 1.4-3.6 km apart are kept when the middle of the straight line
   between them (400 m trimmed at each end) stays at least 250 m from every line in URA's Master Plan 2025
   rail line layer (as amended), which also shows lines not yet built. Whether the chosen pair lies away from
   the areas LTA has named for rail feasibility studies was checked by reading LTA's 2025 and 2026 news
   releases, not computed here.
2. What the island-wide layers contain (building types, lot counts).
"""
from __future__ import annotations

import itertools
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import geopandas as gpd  # noqa: E402
import pyogrio  # noqa: E402
from shapely.geometry import LineString  # noqa: E402

from corridor import config  # noqa: E402

MIN_D, MAX_D, TRIM, MIN_CLEAR = 1400.0, 3600.0, 400.0, 250.0


def corridor_selection(raw: Path) -> dict:
    exits = gpd.read_file(raw / "lta_station_exit" / "lta_mrt_station_exit.geojson").to_crs(config.SVY21)
    stns = gpd.read_file(raw / "mp25_rail_station" / "mp25_rail_station_amended.geojson").to_crs(config.SVY21)
    lines = gpd.read_file(raw / "mp25_rail_line" / "mp25_rail_line_amended.geojson").to_crs(config.SVY21)
    exit_names = set(exits["STATION_NA"].str.upper().str.replace(r"\s+(MRT|LRT)\s+STATION.*$", "", regex=True).str.strip())
    stns["name"] = stns["NAME"].str.upper().str.strip()
    stns["operating"] = stns["name"].isin(exit_names)
    op = stns[stns["operating"] & (stns["RAIL_TYPE"] == "MRT")].dissolve(by="name").reset_index()
    pts = {r.name: r.geometry.centroid for r in op.itertuples()}
    rail = lines.geometry.union_all()
    cands = []
    for a, b in itertools.combinations(sorted(pts), 2):
        d = pts[a].distance(pts[b])
        if not MIN_D <= d <= MAX_D:
            continue
        seg = LineString([pts[a], pts[b]])
        mid = LineString([seg.interpolate(TRIM), seg.interpolate(d - TRIM)])
        clear = mid.distance(rail)
        if clear >= MIN_CLEAR:
            cands.append({"a": a, "b": b, "distance_m": round(d, 1), "clearance_m": round(clear, 1)})
    cands.sort(key=lambda r: -r["clearance_m"])
    chosen = config.corridor()["end_stations"]
    pick = [c for c in cands if {c["a"], c["b"]} == set(chosen)]
    return {"rules": {"distance_m": [MIN_D, MAX_D], "trim_m": TRIM, "min_clearance_m": MIN_CLEAR},
            "stations_in_master_plan_layer": int(len(stns)),
            "stations_with_exits_matched": int(stns["operating"].sum()),
            "exit_station_names_not_matched": len(exit_names - set(stns["name"])),
            "operating_mrt_stations_used": len(pts), "candidate_pairs": len(cands),
            "top_candidates": cands[:10], "chosen": chosen,
            "chosen_rank": (cands.index(pick[0]) + 1) if pick else None, "chosen_pair": pick[0] if pick else None}


def layers(raw: Path) -> dict:
    b = pyogrio.read_dataframe(raw / "mp25_building" / "mp25_building.geojson", columns=["BLDG_TYPE"], read_geometry=False)
    lots = pyogrio.read_info(raw / "sla_cadastral" / "sla_cadastral_land_parcel.geojson")["features"]
    lu = pyogrio.read_info(raw / "mp25_land_use" / "mp25_land_use_amended.geojson")["features"]
    return {"mp_building_types": {k: int(v) for k, v in b["BLDG_TYPE"].str.strip().value_counts().items()},
            "mp_buildings": int(len(b)), "cadastral_lots": int(lots), "land_use_polygons": int(lu)}


def main() -> int:
    raw = config.RAW
    out = {"corridor_selection": corridor_selection(raw), "layers": layers(raw)}
    (config.RESULTS / "raw_survey.json").write_text(json.dumps(out, indent=2, sort_keys=True) + "\n",
                                                   encoding="utf-8", newline="\n")
    cs = out["corridor_selection"]
    print(json.dumps({"candidate_pairs": cs["candidate_pairs"], "chosen_rank": cs["chosen_rank"],
                      "layers": out["layers"]}, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
