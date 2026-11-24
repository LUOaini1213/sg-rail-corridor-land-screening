"""Run the whole screening from the committed study-area extract and write results/.

python -m corridor.pipeline        (offline; about a minute)
"""
from __future__ import annotations

import json
import sys

import geopandas as gpd
import numpy as np
import pandas as pd
from shapely.ops import substring

from . import components as comp_mod
from . import config, landdb, options, quality, screening


def _round(obj, nd=6):
    if isinstance(obj, float):
        return round(obj, nd)
    if isinstance(obj, dict):
        return {k: _round(v, nd) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_round(v, nd) for v in obj]
    return obj


def write_json(name: str, obj) -> None:
    config.RESULTS.mkdir(parents=True, exist_ok=True)
    (config.RESULTS / f"{name}.json").write_text(json.dumps(_round(obj), indent=2, sort_keys=True, ensure_ascii=False) + "\n",
                                                 encoding="utf-8", newline="\n")


def data_quality(study: dict) -> dict:
    lots, lu = study["lots"], study["land_use"]
    ov = quality.overlaps(lots, "LOT_KEY")
    lu_ov = quality.overlaps(lu, "OBJECTID")
    box = config.study_area_box()
    xs = np.array([[box[0], box[1]], [box[2], box[3]], [(box[0] + box[2]) / 2, (box[1] + box[3]) / 2]])
    mp = study["mp_buildings"]
    osm = study["osm_buildings"]
    return {
        "study_area_svy21": list(box),
        "study_area_km2": (box[2] - box[0]) * (box[3] - box[1]) / 1e6,
        "lots": {"count": int(len(lots)), "invalid": quality.invalid_geometries(lots),
                 "duplicate_keys": len(quality.duplicate_keys(lots, "LOT_KEY")),
                 "overlapping_pairs": len(ov), "overlap_max_m2": max([o[2] for o in ov], default=0.0),
                 "coverage": quality.coverage(lots, box)},
        "land_use": {"count": int(len(lu)), "overlapping_pairs": len(lu_ov), "coverage": quality.coverage(lu, box),
                     "classes": int(lu["LU_DESC"].nunique())},
        "mp_buildings": {"count": int(len(mp)), "by_type": {str(k).strip(): int(v) for k, v in
                                                            mp["BLDG_TYPE"].str.strip().value_counts().items()},
                         "types": sorted(mp["BLDG_TYPE"].str.strip().unique().tolist()),
                         "type_with_stray_spaces": int((mp["BLDG_TYPE"] != mp["BLDG_TYPE"].str.strip()).sum())},
        "osm_buildings": {"count": int(len(osm)), "roof_structures": int((osm["building"] == "roof").sum()),
                          "top_tags": {str(k): int(v) for k, v in osm["building"].value_counts().head(6).items()}},
        "building_cross_check": quality.building_cross_check(mp, osm),
        "state_land_layers": {k: int(len(study[k])) for k in ("state_land_vacant", "state_land_agent", "state_reserve")},
        "airspace_lots": int(len(study["airspace_lots"])),
        "underground_structures": int(len(study["underground_structures"])),
        "rail_lines": int(len(study["rail_lines"])),
        "crs_round_trip_max_error_m": quality.crs_round_trip_error_m(xs),
    }


def corridor_check(variants: dict, study: dict, end_trim_m: float = 300.0) -> dict:
    """Clearance between the middle of each fictional alignment and every rail line in the Master Plan 2025
    layer (as amended), and whether the extract is large enough for that check to be complete."""
    lines = study["rail_lines"].geometry.union_all()
    stations = study["rail_stations"]
    box = config.study_area_box()
    from shapely.geometry import box as sbox
    edge = sbox(*box).exterior
    out = {}
    interchange_max = float(config.corridor()["geometry"]["interchange_max_distance_m"])
    names = config.corridor()["end_stations"]
    for k, (al, comps) in variants.items():
        mid = substring(al.line, end_trim_m, al.line.length - end_trim_m)
        clear = float(mid.distance(lines))
        to_edge = float(mid.distance(edge))
        bs = comps.loc[comps["component_id"] == f"{k}-BOX-S", "geometry"].iloc[0]
        bn = comps.loc[comps["component_id"] == f"{k}-BOX-N", "geometry"].iloc[0]
        d_s = float(bs.distance(stations.loc[stations["NAME"] == names[0]].geometry.union_all()))
        d_n = float(bn.distance(stations.loc[stations["NAME"] == names[1]].geometry.union_all()))
        out[k] = {"clearance_middle_to_mp_rail_m": clear, "middle_to_extract_edge_m": to_edge,
                  "extract_sufficient": bool(to_edge > clear), "end_trim_m": end_trim_m,
                  "box_s_to_station_m": d_s, "box_n_to_station_m": d_n,
                  "interchange_ok": bool(d_s <= interchange_max and d_n <= interchange_max)}
    return out


def build_landdb(full: dict, attrs: pd.DataFrame, study: dict) -> tuple[landdb.LandDB, dict]:
    cfg = config.corridor()
    db = landdb.LandDB(landdb.parcels_table(study["lots"], attrs))
    for k, v in cfg["variants"].items():
        db.add_version(f"{k}-v1", k, v["label"], v["pis"], full[k], attrs, status="baseline" if k == "A" else "option")
    rev = cfg["revision_demo"]
    base = cfg["variants"][rev["base_variant"]]
    spec = dict(base, pis=rev["revised_pis"])
    al2, comps2 = comp_mod.build_variant(rev["base_variant"], spec, cfg["geometry"])
    res2 = screening.screen_variant(rev["base_variant"], al2, comps2, study, attrs)
    # SYNTHETIC progress on the baseline before the alignment changes: step 1 done and step 2 under way on the
    # first two acquisition interests that continue after the revision, and on the first one the revision drops,
    # so that both behaviours of the update (carry over; flag for review) show in the demo
    ints = db.interests[db.interests["version_id"] == "A-v1"]
    acq = ints[ints["instrument_code"].isin(["ACQ-SURFACE", "ACQ-STRATUM"])].sort_values("interest_id")
    kept = set(zip(res2["pieces"]["LOT_KEY"], res2["pieces"]["take"]))
    cont = [r.interest_id for r in acq.itertuples() if (r.lot_key, r.interest_type) in kept][:2]
    gone = [r.interest_id for r in acq.itertuples() if (r.lot_key, r.interest_type) not in kept][:1]
    for iid in cont + gone:
        db.set_step(f"{iid}:1", "done", "2026-11-20", "SYNTHETIC demo progress")
        db.set_step(f"{iid}:2", "in_progress", "2026-11-22", "SYNTHETIC demo progress")
    upd = db.revise("A-v1", "A-v2", rev["base_variant"], rev["revised_label"], rev["revised_pis"], res2, attrs)
    return db, upd


def run(write_outputs: bool = True) -> dict:
    study = screening.load_study()
    dq = data_quality(study)
    full, summary, attrs = screening.run(study)
    variants = {k: (full[k]["alignment"], full[k]["components"]) for k in full}
    check = corridor_check(variants, study)
    cmp = options.compare(summary, config.scoring())
    geo = config.corridor()["geometry"]
    crown, invert = comp_mod.tunnel_levels(geo)
    params = {"zone_distances_m": screening.zone_distances(), "default_subterranean_level_m_shd": screening.default_subterranean_level_m_shd(),
              "tunnel_crown_level_m_shd": crown, "tunnel_invert_level_m_shd": invert,
              "tunnel_outer_width_m": float(geo["bored_tunnel"]["tube_centre_spacing_m"] + geo["bored_tunnel"]["tube_outer_diameter_m"]),
              "station_box": geo["station_box"], "worksite": geo["worksite"], "curve_radius_m": geo["curve_radius_m"],
              "min_piece_m2": screening.MIN_PIECE_M2, "min_building_m2": screening.MIN_BUILDING_M2,
              "state_land_share": screening.STATE_LAND_SHARE}
    write_json("data_quality", dq)
    write_json("screening", {"parameters": params, "variants": summary, "corridor_check": check})
    write_json("options", cmp)
    sched = pd.concat([full[k]["schedule"] for k in full], ignore_index=True)
    sched.round(2).to_csv(config.RESULTS / "schedule.csv", index=False, lineterminator="\n")
    db, upd = build_landdb(full, attrs, study)
    val = db.validate()
    config.OUTPUTS.mkdir(parents=True, exist_ok=True)
    db.write(config.OUTPUTS / "land_db.gpkg")
    write_json("landdb", {
        "tables": {"parcels": len(db.parcels), "alignment_versions": len(db.versions), "affected_areas": len(db.affected),
                   "interests": len(db.interests), "steps": len(db.steps), "documents": len(db.documents),
                   "change_log": len(db.changes)},
        "interests_by_version": {k: int(v) for k, v in db.interests.groupby("version_id").size().items()},
        "validation": {k: len(v) for k, v in val.items()},
        "validation_failures": int(sum(len(v) for v in val.values())),
        "n_rules": len(landdb.VALIDATION_RULES),
        "update_demo": {"base_version": upd["base_version"], "new_version": upd["new_version"],
                        "revised_label": config.corridor()["revision_demo"]["revised_label"],
                        "out_of_scope": upd["out_of_scope"], "new_in_scope": upd["new_in_scope"],
                        "out_lots": [f"{r['lot_key']} ({r['interest_type'].replace('_', ' ')})" for r in upd["out_of_scope"]] or ["none"],
                        "new_lots": [f"{r['lot_key']} ({r['interest_type'].replace('_', ' ')})" for r in upd["new_in_scope"]] or ["none"],
                        "n_out": len(upd["out_of_scope"]), "n_new": len(upd["new_in_scope"]),
                        "n_changed": len(upd["changed"]), "changed": upd["changed"],
                        "steps_to_review": upd["steps_to_review"], "n_steps_to_review": len(upd["steps_to_review"])},
    })
    if write_outputs:
        from .outputs import run_all as outputs_run
        outputs_run(full, summary, cmp, attrs, study, check)
    return {"summary": summary, "options": cmp, "landdb_validation": val}


if __name__ == "__main__":
    run()
    sys.exit(0)
