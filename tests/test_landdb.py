"""Land database: schema, validation rules (each must catch a planted error), alignment update."""
import sqlite3

import geopandas as gpd
import pandas as pd
import pytest
from shapely.geometry import Polygon, box

from corridor import config, landdb, screening


def comps(rows):
    return gpd.GeoDataFrame([{"variant": "T", "component_id": c, "component_type": t, "take": k, "geometry": g}
                             for c, t, k, g in rows], geometry="geometry", crs=config.SVY21)


def result_for(study, attrs, rows):
    c = comps(rows)
    pieces = screening.overlay(study["lots"], c)
    structure = c[c["take"] != "temporary_surface"].geometry.union_all()
    zp = screening.zone_pieces(study["lots"], screening.zone_rings(structure, screening.zone_distances()))
    return {"pieces": pieces, "zone_pieces": zp}


BASE = [("T-BOX-S", "station_box", "permanent_surface", box(10, 10, 90, 30)),
        ("T-TUN", "bored_tunnel", "permanent_subterranean", box(10, 30, 90, 190)),
        ("T-WS-S", "worksite", "temporary_surface", box(110, 110, 190, 130))]
# revision: the tunnel moves east into L2/L4 and the worksite moves off L4 into L2
REV = [("T-BOX-S", "station_box", "permanent_surface", box(10, 10, 90, 30)),
       ("T-TUN", "bored_tunnel", "permanent_subterranean", box(10, 30, 90, 150)),
       ("T-WS-S", "worksite", "temporary_surface", box(110, 10, 190, 30))]


@pytest.fixture
def db(grid_study):
    attrs = screening.lot_attributes(grid_study["lots"], grid_study["land_use"], screening.state_land_geometry(grid_study))
    d = landdb.LandDB(landdb.parcels_table(grid_study["lots"], attrs))
    d.add_version("T-v1", "T", "test", [(50, 10), (50, 190)], result_for(grid_study, attrs, BASE), attrs)
    d._attrs, d._study = attrs, grid_study
    return d


def test_a_clean_database_passes_every_rule(db):
    v = db.validate()
    assert set(v) == {r[0] for r in landdb.VALIDATION_RULES}
    assert all(len(x) == 0 for x in v.values()), v


def test_interests_and_steps_follow_the_instruments(db):
    i = db.interests.set_index("interest_id")
    assert i.loc["T-v1:L1:ACQ-SURFACE", "area_m2"] == pytest.approx(1600.0)
    assert i.loc["T-v1:L1:ACQ-STRATUM", "area_m2"] == pytest.approx(5600.0)
    assert i.loc["T-v1:L3:ACQ-STRATUM", "area_m2"] == pytest.approx(7200.0)
    assert i.loc["T-v1:L4:TOL", "area_m2"] == pytest.approx(1600.0)
    assert i.loc["T-v1:L1:ACQ-STRATUM", "stratum_top_m_shd"] > i.loc["T-v1:L1:ACQ-STRATUM", "stratum_bottom_m_shd"]
    steps = db.steps[db.steps["interest_id"] == "T-v1:L1:ACQ-SURFACE"].sort_values("seq")
    assert steps["step_name"].tolist()[1:5] == ["Notice of acquisition", "Collector's inquiry", "Collector's award",
                                                "Payment of compensation and site possession"]


def test_every_step_cites_a_verified_fact_or_says_illustrative():
    facts = {r["id"]: r["status"] for r in config.facts()["facts"]}
    for code, steps in landdb.STEP_TEMPLATES.items():
        for name, src, _ in steps:
            assert src == "ILLUSTRATIVE" or facts.get(src) == "VERIFIED", (code, name, src)
    codes = {"ACQ-SURFACE", "ACQ-STRATUM", "TEMP-OCC", "TOL", "STATE-SURFACE", "STATE-STRATUM", "CHECK-TITLE", "RAIL-ZONE"}
    assert codes <= set(landdb.STEP_TEMPLATES)


def _row(df, col, val):
    return df.index[df[col] == val][0]


@pytest.mark.parametrize("rule", [r[0] for r in landdb.VALIDATION_RULES])
def test_each_rule_catches_a_planted_error(db, rule):
    i = db.interests
    if rule == "V01":
        db.interests = pd.concat([i, i.iloc[[0]]], ignore_index=True)
    elif rule == "V02":
        i.loc[_row(i, "interest_id", "T-v1:L4:TOL"), "lot_key"] = "NO-SUCH-LOT"
    elif rule == "V03":
        i.loc[_row(i, "interest_id", "T-v1:L4:TOL"), "version_id"] = "X-v9"
    elif rule == "V04":
        i.loc[_row(i, "interest_id", "T-v1:L1:ACQ-SURFACE"), "area_m2"] = 10001.0
    elif rule == "V05":
        extra = i.loc[i["interest_id"] == "T-v1:L1:ACQ-SURFACE"].copy()
        extra["interest_id"], extra["interest_type"], extra["instrument_code"] = "T-v1:L1:TEMP-OCC", "temporary_surface", "TEMP-OCC"
        extra["area_m2"], extra["start_date"], extra["end_date"] = 9000.0, "2028-01-01", "2029-01-01"
        db.interests = pd.concat([i, extra], ignore_index=True)
    elif rule == "V06":
        i.loc[_row(i, "interest_id", "T-v1:L4:TOL"), "end_date"] = "2039-01-01"      # 11 years
    elif rule == "V07":
        i.loc[_row(i, "interest_id", "T-v1:L4:TOL"), "lot_key"] = "L2"              # L2 is not shown as State land
    elif rule == "V08":
        i.loc[_row(i, "interest_id", "T-v1:L3:ACQ-STRATUM"), "stratum_bottom_m_shd"] = 10.0
    elif rule == "V09":
        db.steps.loc[_row(db.steps, "step_id", "T-v1:L1:ACQ-SURFACE:3"), "status"] = "done"
    elif rule == "V10":
        db.documents.loc[db.documents.index[0], "interest_id"] = "NO-SUCH-INTEREST"
    elif rule == "V11":
        db.parcels.loc[db.parcels.index[0], "geometry"] = Polygon([(0, 0), (10, 10), (10, 0), (0, 10)])
    elif rule == "V12":
        i.loc[_row(i, "interest_id", "T-v1:L3:ACQ-STRATUM"), "area_m2"] = 7100.0
    v = db.validate()
    assert len(v[rule]) >= 1, (rule, v)


def test_temporary_occupation_longer_than_the_fact_sheet_limit_fails(db):
    extra = db.interests[db.interests["interest_id"] == "T-v1:L4:TOL"].copy()
    extra["interest_id"], extra["lot_key"], extra["instrument_code"] = "T-v1:L2:TEMP-OCC", "L2", "TEMP-OCC"
    extra["start_date"], extra["end_date"] = "2028-01-01", "2031-06-30"      # 3.5 years > 3
    db.interests = pd.concat([db.interests, extra], ignore_index=True)
    assert any("T-v1:L2:TEMP-OCC" in s for s in db.validate()["V06"])


def test_revision_reports_what_moved_in_and_out_of_scope(db):
    attrs, study = db._attrs, db._study
    db.set_step("T-v1:L3:ACQ-STRATUM:1", "done", "2026-11-20", "demo")
    db.set_step("T-v1:L1:ACQ-SURFACE:1", "done", "2026-11-20", "demo")
    upd = db.revise("T-v1", "T-v2", "T", "test rev", [(50, 10), (50, 150)], result_for(study, attrs, REV), attrs)
    out = {(r["lot_key"], r["interest_type"]) for r in upd["out_of_scope"]}
    new = {(r["lot_key"], r["interest_type"]) for r in upd["new_in_scope"]}
    assert ("L4", "temporary_surface") in out                    # the worksite left L4
    assert ("L2", "temporary_surface") in new                    # and arrived on L2
    changed = {(c["lot_key"], c["interest_type"]): c for c in upd["changed"]}
    assert changed[("L3", "permanent_subterranean")]["new_area_m2"] == pytest.approx(80 * 50)   # 30..150 -> 100..150
    # the stratum on L3 continues, so its completed step is carried over, not sent for review
    assert db.steps.set_index("step_id").loc["T-v2:L3:ACQ-STRATUM:1", "status"] == "done"
    # the withdrawn TOL on L4 had nothing done: its steps are withdrawn
    st = db.steps[db.steps["interest_id"] == "T-v1:L4:TOL"]
    assert set(st["status"]) == {"withdrawn"}
    assert db.interests.set_index("interest_id").loc["T-v1:L4:TOL", "status"] == "withdrawn"
    assert db.versions.set_index("version_id").loc["T-v1", "status"] == "superseded"
    assert len(db.changes) > 0 and all(c["timestamp"] == landdb.AS_OF for c in db.changes)
    assert all(len(x) == 0 for x in db.validate().values())


def test_done_steps_of_withdrawn_interests_are_flagged_for_review(db):
    attrs, study = db._attrs, db._study
    db.set_step("T-v1:L4:TOL:1", "done", "2026-11-20", "demo")
    upd = db.revise("T-v1", "T-v2", "T", "test rev", [(50, 10), (50, 150)], result_for(study, attrs, REV), attrs)
    assert upd["steps_to_review"] == ["T-v1:L4:TOL:1"]
    assert db.steps.set_index("step_id").loc["T-v1:L4:TOL:1", "status"] == "done"


def test_write_and_read_back(db, tmp_path):
    p = tmp_path / "db.gpkg"
    db.write(p)
    con = sqlite3.connect(p)
    kinds = dict(con.execute("SELECT table_name, data_type FROM gpkg_contents").fetchall())
    con.close()
    assert kinds["parcels"] == "features" and kinds["affected_areas"] == "features"
    for t in ("alignment_versions", "interests", "steps", "documents", "change_log", "validation_rules", "metadata"):
        assert kinds[t] == "attributes", t
    assert len(landdb.LandDB.read_table(p, "interests")) == len(db.interests)
    assert len(landdb.LandDB.read_table(p, "validation_rules")) == len(landdb.VALIDATION_RULES)
    back = gpd.read_file(p, layer="parcels")
    assert back.crs.to_epsg() == 3414 and len(back) == len(db.parcels)
