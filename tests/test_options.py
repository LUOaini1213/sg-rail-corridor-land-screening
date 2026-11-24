"""Multi-criteria comparison checked on small hand-worked examples."""
import numpy as np
import pandas as pd
import pytest

from corridor import config, options


def raw_example():
    # three variants, two criteria (lower is better)
    return pd.DataFrame({"area": [10.0, 20.0, 30.0], "count": [5.0, 5.0, 5.0]}, index=["A", "B", "C"])


def test_min_max_scores_and_non_discriminating_criteria():
    sc = options.normalise(raw_example())
    assert sc["area"].tolist() == pytest.approx([1.0, 0.5, 0.0])
    assert sc["count"].tolist() == [1.0, 1.0, 1.0]       # all tied: cannot discriminate, scores 1


def test_weights_are_renormalised_and_must_be_valid():
    sc = options.normalise(raw_example())
    t = options.weighted(sc, np.array([3.0, 1.0]))
    assert t.tolist() == pytest.approx([1.0, 0.625, 0.25])   # 0.75*s_area + 0.25*1
    with pytest.raises(ValueError):
        options.weighted(sc, np.array([1.0, -1.0]))
    with pytest.raises(ValueError):
        options.weighted(sc, np.array([0.0, 0.0]))


def test_rank_breaks_ties_by_variant_key():
    assert options.rank(pd.Series({"B": 0.5, "A": 0.5, "C": 0.9})) == ["C", "A", "B"]


def test_snap_ties_treats_near_best_values_as_best():
    raw = pd.DataFrame({"x": [100.0, 104.0, 106.0]}, index=["A", "B", "C"])
    snapped = options.snap_ties(raw, 0.05)
    assert snapped["x"].tolist() == [100.0, 100.0, 106.0]
    assert options.normalise(snapped)["x"].tolist() == pytest.approx([1.0, 1.0, 0.0])


def test_one_at_a_time_and_leave_one_out_cover_every_criterion():
    sc = options.normalise(raw_example())
    w = np.array([0.5, 0.5])
    oat = options.one_at_a_time(sc, w, [0.5, 1.5])
    assert len(oat) == 4 and {r["criterion"] for r in oat} == {"area", "count"}
    loo = options.leave_one_out(sc, w)
    assert [r["criterion_removed"] for r in loo] == ["area", "count"]
    # without 'area' all variants tie on 'count' and the key order decides
    assert loo[0]["ranking"] == ["A", "B", "C"]


def test_random_weights_are_reproducible_and_shares_sum_to_one():
    sc = options.normalise(pd.DataFrame({"a": [1.0, 2.0, 3.0], "b": [3.0, 2.0, 1.0]}, index=["A", "B", "C"]))
    r1 = options.random_weights(sc, 500, 7)
    r2 = options.random_weights(sc, 500, 7)
    assert r1 == r2 and sum(r1.values()) == pytest.approx(1.0)
    assert r1["B"] < 0.05          # B is never best on either criterion; it wins only on exact ties


def test_criteria_table_reads_the_right_fields():
    summary = {"A": {"totals": {"lots_in_scope": 3, "permanent_surface_not_state_m2": 10.0, "subterranean_not_state_m2": 1.0},
                     "length_m": 1000.0, "buildings": {"in_surface_take": 2, "above_tunnels": 4},
                     "zones": {"within_protection_distance_lots": 7}}}
    crit = config.scoring()["criteria"]
    t = options.criteria_table(summary, crit)
    assert t.loc["A", "lots_in_scope"] == 3 and t.loc["A", "length_m"] == 1000.0
    assert t.loc["A", "buildings_in_surface_take"] == 2 and t.loc["A", "buildings_above_tunnels"] == 4
    assert t.loc["A", "lots_within_protection_distance"] == 7


def test_weights_in_the_inputs_sum_to_one():
    assert sum(c["weight"] for c in config.scoring()["criteria"]) == pytest.approx(1.0)
