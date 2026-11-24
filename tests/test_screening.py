"""Screening checked on a hand-made 2 x 2 grid of lots (see conftest.grid_study)."""
import math

import geopandas as gpd
import pandas as pd
import pytest
from shapely.geometry import LineString, box

from corridor import config, screening


def comps_gdf(rows):
    return gpd.GeoDataFrame(rows, geometry="geometry", crs=config.SVY21)


def one(cid, ctype, take, geom, variant="T"):
    return {"variant": variant, "component_id": cid, "component_type": ctype, "take": take, "geometry": geom}


def test_overlay_splits_a_component_by_lot(grid_study):
    c = comps_gdf([one("T-BOX", "station_box", "permanent_surface", box(50, 50, 150, 150))])
    p = screening.overlay(grid_study["lots"], c)
    got = dict(zip(p["LOT_KEY"], p["area_m2"]))
    assert got == pytest.approx({"L1": 2500.0, "L2": 2500.0, "L3": 2500.0, "L4": 2500.0})


def test_area_is_conserved_with_part_outside_the_lots(grid_study):
    c = comps_gdf([one("T-WS", "worksite", "temporary_surface", box(150, 50, 250, 150))])
    allp = screening.overlay_all(grid_study["lots"], c)
    acct = screening.area_accounting(grid_study["lots"], c, allp).iloc[0]
    assert acct["component_area_m2"] == pytest.approx(10000.0)
    assert acct["counted_pieces_m2"] == pytest.approx(5000.0)
    assert acct["outside_lots_m2"] == pytest.approx(5000.0)
    assert acct["residual_m2"] == pytest.approx(0.0, abs=1e-6)


def test_slivers_are_kept_out_of_the_take_but_in_the_accounting(grid_study):
    # 0.05 m x 10 m = 0.5 m2 in L1 is below the 1 m2 threshold; 50 m x 10 m in L2 is take
    c = comps_gdf([one("T-BOX", "station_box", "permanent_surface", box(99.95, 0, 150, 10))])
    p = screening.overlay(grid_study["lots"], c)
    assert p["LOT_KEY"].tolist() == ["L2"]
    acct = screening.area_accounting(grid_study["lots"], c, screening.overlay_all(grid_study["lots"], c)).iloc[0]
    assert acct["n_slivers"] == 1 and acct["sliver_pieces_m2"] == pytest.approx(0.5)
    assert acct["residual_m2"] == pytest.approx(0.0, abs=1e-6)


def test_lot_attributes_dominant_use_and_state_land(grid_study):
    lu = grid_study["land_use"].copy()
    # make L1 60 % RESIDENTIAL, 40 % PARK
    lu = pd.concat([lu, comps_gdf([{"OBJECTID": 3, "LU_DESC": "PARK", "GPR": None, "geometry": box(60, 0, 100, 100)}])],
                   ignore_index=True)
    lu.loc[0, "geometry"] = box(0, 0, 60, 100).union(box(0, 100, 100, 200))
    lu = gpd.GeoDataFrame(lu, geometry="geometry", crs=config.SVY21)
    a = screening.lot_attributes(grid_study["lots"], lu, screening.state_land_geometry(grid_study)).set_index("LOT_KEY")
    assert a.loc["L1", "land_use"] == "RESIDENTIAL" and a.loc["L1", "land_use_share"] == pytest.approx(0.6)
    assert a.loc["L2", "land_use"] == "ROAD"
    assert a.loc["L4", "state_land_share"] == pytest.approx(1.0) and bool(a.loc["L4", "state_land_indicated"])
    assert not bool(a.loc["L2", "state_land_indicated"])


def test_zone_rings_have_the_hand_computed_areas():
    # 100 m square; buffers with round corners: area(d) = 10000 + 400 d + pi d^2
    sq = box(0, 0, 100, 100)
    rings = screening.zone_rings(sq, {"first_reserve": 6.0, "protection_zone": 40.0, "safety_zone": 60.0})
    a = lambda d: 10000 + 400 * d + math.pi * d * d
    assert rings["first_reserve"].area == pytest.approx(a(6) - 10000, rel=1e-3)
    assert rings["protection_zone"].area == pytest.approx(a(40) - a(6), rel=1e-3)
    assert rings["safety_zone"].area == pytest.approx(a(60) - a(40), rel=1e-3)
    assert rings["first_reserve"].intersection(sq).area == pytest.approx(0.0, abs=1e-6)
    assert rings["first_reserve"].intersection(rings["protection_zone"]).area == pytest.approx(0.0, abs=1e-6)


def test_zone_distances_are_the_verified_fact_values():
    d = screening.zone_distances()
    assert d == {"first_reserve": 6.0, "protection_zone": 40.0, "safety_zone": 60.0, "railway_corridor": 40.0}
    rows = {r["id"]: r for r in config.facts()["facts"]}
    assert rows["F15"]["value"] == 6 and rows["F13"]["value"] == 40 and rows["F14"]["value"] == 60
    assert screening.default_subterranean_level_m_shd() == pytest.approx(-30.0)


def test_unverified_facts_cannot_feed_a_calculation():
    with pytest.raises(ValueError):
        config.fact_value("F22")


@pytest.mark.parametrize("take,state,crown,code", [
    ("permanent_surface", True, -5.0, "STATE-SURFACE"),
    ("permanent_surface", False, -5.0, "ACQ-SURFACE"),
    ("permanent_subterranean", True, -5.0, "STATE-STRATUM"),
    ("permanent_subterranean", False, -5.0, "ACQ-STRATUM"),
    ("permanent_subterranean", False, -29.9, "ACQ-STRATUM"),
    ("permanent_subterranean", False, -30.0, "CHECK-TITLE"),
    ("permanent_subterranean", False, -35.0, "CHECK-TITLE"),
    ("temporary_surface", True, -5.0, "TOL"),
    ("temporary_surface", False, -5.0, "TEMP-OCC"),
])
def test_instrument_routing(take, state, crown, code):
    assert screening.instrument_for(take, state, crown, -30.0).code == code


def test_buildings_need_a_square_metre_inside_and_roofs_can_be_left_out(grid_study):
    c = comps_gdf([one("T-BOX", "station_box", "permanent_surface", box(59.5, 0, 200, 200))])
    b = screening.buildings_involved(c, grid_study["osm_buildings"], "osm_id", "building")
    assert set(b["building_id"]) == {"way/1", "way/2"}  # way/1: a 0.5 m x 20 m strip = 10 m2 inside
    assert b.set_index("building_id").loc["way/1", "area_in_footprint_m2"] == pytest.approx(10.0)
    c2 = comps_gdf([one("T-BOX", "station_box", "permanent_surface", box(59.96, 0, 200, 200))])
    b2 = screening.buildings_involved(c2, grid_study["osm_buildings"], "osm_id", "building", exclude_types=("roof",))
    assert b2.empty                                    # 0.04 m x 20 m = 0.8 m2 < 1 m2, and the roof is excluded


def test_existing_railway_zone_classification(grid_study):
    line = grid_study["rail_lines"]                     # y = -100
    rows = [one(f"T-{d}", "worksite", "temporary_surface", box(0, -100 + d, 10, -100 + d + 10)) for d in (5, 30, 50, 70)]
    iface = screening.existing_railway_interfaces(comps_gdf(rows), line, grid_study["rail_stations"],
                                                  {"first_reserve": 6, "protection_zone": 40, "safety_zone": 60})
    assert iface["existing_railway_zone"].tolist() == ["first_reserve", "protection_zone", "safety_zone", "outside"]


def test_tenure_evidence_labels():
    assert screening.tenure_evidence(True, "ROAD") == "State land (SLA open layer)"
    assert screening.tenure_evidence(False, "ROAD") == "Unknown: Master Plan road zone"
    assert screening.tenure_evidence(False, "PARK") == "Unknown: Master Plan park or open space"
    assert screening.tenure_evidence(False, "RESIDENTIAL") == "Unknown"


def test_lot_schedule_on_the_grid(grid_study):
    al = None
    c = comps_gdf([
        one("T-BOX-S", "station_box", "permanent_surface", box(10, 10, 90, 30)),       # L1 only, 1600 m2
        one("T-TUN", "bored_tunnel", "permanent_subterranean", box(10, 30, 90, 190)),   # L1 5600, L3 7200
        one("T-WS-S", "worksite", "temporary_surface", box(110, 110, 190, 130)),        # L4 (State land) 1600
    ])
    attrs = screening.lot_attributes(grid_study["lots"], grid_study["land_use"], screening.state_land_geometry(grid_study))
    pieces = screening.overlay(grid_study["lots"], c)
    structure = c[c["take"] != "temporary_surface"].geometry.union_all()
    rings = screening.zone_rings(structure, screening.zone_distances())
    zp = screening.zone_pieces(grid_study["lots"], rings)
    s = screening.lot_schedule("T", pieces, attrs, zp, None, {}, -5.0, -30.0).set_index("LOT_KEY")
    assert s.loc["L1", "permanent_surface_m2"] == pytest.approx(1600.0)
    assert s.loc["L1", "permanent_subterranean_m2"] == pytest.approx(5600.0)
    assert s.loc["L3", "permanent_subterranean_m2"] == pytest.approx(7200.0)
    assert s.loc["L4", "temporary_surface_m2"] == pytest.approx(1600.0)
    assert s.loc["L1", "instruments"].split(";")[:2] == ["ACQ-SURFACE", "ACQ-STRATUM"]
    assert s.loc["L4", "instruments"].startswith("TOL")
    assert bool(s.loc["L4", "in_scope"]) and s.loc["L4", "agencies"] == "LTA;SLA"
    # L2 holds no take but lies within 40 m of the structure (x = 90 -> lot starts at 100)
    assert not bool(s.loc["L2", "in_scope"]) and s.loc["L2", "instruments"] == "RAIL-ZONE"
    assert s.loc["L2", "first_reserve_m2"] == pytest.approx(0.0)
    assert s.loc["L2", "protection_zone_m2"] > 0
