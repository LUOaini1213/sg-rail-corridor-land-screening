"""Tests added after the first mutation run: each closes a gap that a surviving mutant exposed
(see results/mutation.json, key "first")."""
import geopandas as gpd
import numpy as np
import pandas as pd
import pytest
from shapely.geometry import box

from corridor import components, config, docs, landdb, options, screening


def two_criteria():
    # A is best on a, B is best on b, C is worst on both
    raw = pd.DataFrame({"a": [1.0, 2.0, 3.0], "b": [2.0, 1.0, 3.0]}, index=["A", "B", "C"])
    return options.normalise(raw)


def test_railway_structure_is_the_permanent_components_only():
    rows = [("X-BOX-S", "station_box", "permanent_surface", box(0, 0, 10, 10)),
            ("X-TUN", "bored_tunnel", "permanent_subterranean", box(10, 0, 30, 10)),
            ("X-WS-S", "worksite", "temporary_surface", box(0, 10, 10, 50))]
    g = gpd.GeoDataFrame([{"component_id": c, "component_type": t, "take": k, "geometry": geom} for c, t, k, geom in rows],
                         geometry="geometry", crs=config.SVY21)
    s = components.railway_structure(g)
    assert s.area == pytest.approx(300.0)                 # boxes and tunnel; the worksite is not railway
    assert s.intersection(box(0, 10, 10, 50)).area == pytest.approx(0.0)


def test_one_at_a_time_scales_the_weight():
    sc = two_criteria()
    oat = options.one_at_a_time(sc, np.array([0.6, 0.4, ]), [0.5])
    by = {r["criterion"]: r for r in oat}
    assert by["a"]["winner"] == "B"        # 0.3 x a against 0.4 x b: B wins
    assert by["b"]["winner"] == "A"        # 0.6 x a against 0.2 x b: A wins


def test_leave_one_out_drops_the_criterion():
    loo = {r["criterion_removed"]: r["winner"] for r in options.leave_one_out(two_criteria(), np.array([0.6, 0.4]))}
    assert loo == {"a": "B", "b": "A"}


def test_random_weights_count_the_winner():
    share = options.random_weights(two_criteria(), 2000, 11)
    assert share["C"] == 0.0               # C is never best
    assert 0.4 < share["A"] < 0.6 and 0.4 < share["B"] < 0.6   # weights uniform on the simplex: a coin toss


def test_interest_area_sums_its_pieces_in_one_lot(grid_study):
    attrs = screening.lot_attributes(grid_study["lots"], grid_study["land_use"], screening.state_land_geometry(grid_study))
    comps = gpd.GeoDataFrame([
        {"variant": "T", "component_id": "T-BOX-S", "component_type": "station_box", "take": "permanent_surface", "geometry": box(10, 10, 30, 30)},
        {"variant": "T", "component_id": "T-BOX-N", "component_type": "station_box", "take": "permanent_surface", "geometry": box(50, 50, 90, 60)},
    ], geometry="geometry", crs=config.SVY21)
    res = {"pieces": screening.overlay(grid_study["lots"], comps), "zone_pieces": pd.DataFrame(columns=["LOT_KEY", "band", "area_m2"])}
    ints, aff = landdb.interests_from_screening("T-v1", res, attrs, -5.0, -11.6, -30.0)
    row = ints.set_index("interest_id").loc["T-v1:L1:ACQ-SURFACE"]
    assert row["area_m2"] == pytest.approx(400.0 + 400.0)
    assert len(aff) == 2


def test_revision_reports_a_change_of_instrument(grid_study, monkeypatch):
    attrs = screening.lot_attributes(grid_study["lots"], grid_study["land_use"], screening.state_land_geometry(grid_study))
    comps = gpd.GeoDataFrame([{"variant": "T", "component_id": "T-TUN", "component_type": "bored_tunnel",
                               "take": "permanent_subterranean", "geometry": box(10, 30, 90, 90)}], geometry="geometry", crs=config.SVY21)
    res = {"pieces": screening.overlay(grid_study["lots"], comps), "zone_pieces": pd.DataFrame(columns=["LOT_KEY", "band", "area_m2"])}
    db = landdb.LandDB(landdb.parcels_table(grid_study["lots"], attrs))
    db.add_version("T-v1", "T", "shallow", [(50, 30), (50, 90)], res, attrs)
    # the revision lowers the tunnel below the default ownership depth: same lot, same area, new instrument
    monkeypatch.setattr(components, "tunnel_levels", lambda geo: (-35.0, -41.6))
    upd = db.revise("T-v1", "T-v2", "T", "deep", [(50, 30), (50, 90)], res, attrs)
    ch = {(c["lot_key"], c["interest_type"]): c for c in upd["changed"]}
    assert ch[("L1", "permanent_subterranean")]["old_instrument"] == "ACQ-STRATUM"
    assert ch[("L1", "permanent_subterranean")]["new_instrument"] == "CHECK-TITLE"


def test_number_formats_used_by_the_documents():
    assert docs.fmt(0.996, "pct1") == "99.6%"
    assert docs.fmt(0.5, "pct") == "50%"
    assert docs.fmt(1234.6, ",.0f") == "1,235"
    assert docs.fmt(["a", "b"], "join") == "a, b"
    assert docs.render("{{x.y:.1f}} and {{x.z.0}}", {"x": {"y": 2.25, "z": [7]}}) == "2.2 and 7"


def test_readme_sentences_about_the_ranking_still_hold():
    import json
    o = json.loads((config.RESULTS / "options.json").read_text(encoding="utf-8"))
    best = o["ranking"][0]
    assert o["equal_weights"]["ranking"][0] == best          # README: "ranks first ... under equal weights"
    assert o["one_at_a_time_same_winner"] == o["one_at_a_time_runs"]
    assert o["leave_one_out_same_winner"] == len(o["leave_one_out"])


def test_buildings_by_lot_counts_each_building_once_per_lot(grid_study):
    osm = grid_study["osm_buildings"]
    extra = gpd.GeoDataFrame([{"osm_id": "way/3", "building": "yes", "geometry": box(5, 80, 15, 95)}],
                             geometry="geometry", crs=config.SVY21)
    osm = gpd.GeoDataFrame(pd.concat([osm, extra], ignore_index=True), geometry="geometry", crs=config.SVY21)
    comps = gpd.GeoDataFrame([
        # two pieces in L1 both cover part of way/1 (40..60); only the first covers way/3
        {"variant": "T", "component_id": "T-BOX-S", "component_type": "station_box", "take": "permanent_surface", "geometry": box(0, 45, 45, 99)},
        {"variant": "T", "component_id": "T-WS-S", "component_type": "worksite", "take": "temporary_surface", "geometry": box(45, 30, 70, 50)},
    ], geometry="geometry", crs=config.SVY21)
    pieces = screening.overlay(grid_study["lots"], comps)
    assert screening.buildings_by_lot(pieces, osm) == {"L1": 2}
