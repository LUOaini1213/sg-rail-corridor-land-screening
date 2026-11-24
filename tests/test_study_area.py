"""Checks on the committed study-area extract and on the screening of the three variants."""
import json

import pyogrio
import pytest

from corridor import components, config, pipeline, screening

ALLOWED_COLUMNS = {
    "lots": {"LOT_KEY"}, "airspace_lots": {"LOT_KEY"}, "land_use": {"OBJECTID", "LU_DESC", "GPR"},
    "mp_buildings": {"OBJECTID", "BLDG_TYPE"}, "osm_buildings": {"osm_id", "building"},
    "state_land_vacant": {"OBJECTID", "CATEGORY"}, "state_land_agent": {"OBJECTID"}, "state_reserve": {"OBJECTID", "LOT_KEY"},
    "rail_lines": {"OBJECTID", "GRND_LEVEL", "RAIL_TYPE"}, "rail_stations": {"OBJECTID", "NAME", "GRND_LEVEL", "RAIL_TYPE"},
    "station_exits": {"OBJECTID", "STATION_NA", "EXIT_CODE"}, "underground_structures": {"OBJECTID"},
}


@pytest.fixture(scope="module")
def study():
    return screening.load_study()


@pytest.fixture(scope="module")
def run(study):
    return screening.run(study)


def test_extract_keeps_only_the_allowed_attributes():
    layers = {name for name, _ in pyogrio.list_layers(config.STUDY_GPKG)}
    assert layers == set(ALLOWED_COLUMNS)
    for layer, cols in ALLOWED_COLUMNS.items():
        info = pyogrio.read_info(config.STUDY_GPKG, layer=layer)
        assert set(info["fields"]) == cols, layer
        assert info["crs"] == "EPSG:3414", layer


def test_station_names_are_only_the_two_existing_end_stations(study):
    assert set(study["rail_stations"]["NAME"]) == set(config.corridor()["end_stations"])
    exits = set(study["station_exits"]["STATION_NA"].str.upper())
    for name in config.corridor()["end_stations"]:
        assert any(e.startswith(name + " MRT STATION") for e in exits), name   # the station is in operation


def test_lots_tile_the_study_box(study):
    lots = study["lots"]
    assert lots["LOT_KEY"].is_unique and lots.geometry.is_valid.all()
    dq = pipeline.data_quality(study)
    assert dq["lots"]["coverage"]["covered_share"] > 0.9999
    assert dq["lots"]["overlap_max_m2"] < 1.0


def test_area_is_conserved_for_every_component_of_every_variant(run):
    full, summary, _ = run
    for k, res in full.items():
        acct = res["accounting"]
        assert acct["residual_m2"].abs().max() < 0.01, k
        assert acct["outside_lots_m2"].max() < 0.01, k      # the box lies inside the cadastre everywhere
        # the take per take-type in the summary equals the component areas minus slivers
        for take in screening.TAKES:
            comp_area = res["components"].loc[res["components"]["take"] == take].area.sum()
            ids = res["components"].loc[res["components"]["take"] == take, "component_id"]
            sliver = acct.loc[acct["component_id"].isin(ids), "sliver_pieces_m2"].sum()
            assert summary[k]["totals"][f"{take}_m2"] == pytest.approx(comp_area - sliver, abs=0.01)


def test_schedule_rows_add_up_to_the_totals(run):
    full, summary, _ = run
    for k, res in full.items():
        s = res["schedule"]
        for take in screening.TAKES:
            assert s[f"{take}_m2"].sum() == pytest.approx(summary[k]["totals"][f"{take}_m2"])
        assert summary[k]["totals"]["lots_in_scope"] == int(s["in_scope"].sum())


def test_fictional_alignments_follow_no_master_plan_rail_line(run, study):
    full, _, _ = run
    check = pipeline.corridor_check({k: (r["alignment"], r["components"]) for k, r in full.items()}, study)
    for k, c in check.items():
        assert c["clearance_middle_to_mp_rail_m"] >= 250.0, k
        assert c["extract_sufficient"], k
        assert c["interchange_ok"], k


@pytest.mark.golden
def test_committed_screening_results_match_a_fresh_run(run):
    import sys
    sys.path.insert(0, str(config.ROOT / "scripts"))
    from check_results import close        # numbers compared with a small tolerance (platform differences)
    _, summary, _ = run
    committed = json.loads((config.RESULTS / "screening.json").read_text(encoding="utf-8"))["variants"]
    fresh = json.loads(json.dumps(pipeline._round(summary), sort_keys=True))
    assert close(fresh, committed) == []
