"""Transparent multi-criteria comparison of the variants, with weight sensitivity.

Scoring: for each criterion (lower raw value is better) a variant scores
    s = (worst - value) / (worst - best)      in [0, 1], 1 = best of the variants compared,
and a criterion on which all variants tie scores 1 for every variant (it cannot discriminate).
The total is the weighted mean of the scores with the weights renormalised to sum to 1.
"""
from __future__ import annotations

import numpy as np
import pandas as pd


def criteria_table(summary: dict, criteria: list[dict]) -> pd.DataFrame:
    rows = {}
    for v, s in summary.items():
        vals = {}
        for c in criteria:
            k = c["key"]
            if k in s["totals"]:
                vals[k] = s["totals"][k]
            elif k == "length_m":
                vals[k] = s["length_m"]
            elif k in ("buildings_in_surface_take", "buildings_above_tunnels"):
                vals[k] = s["buildings"]["in_surface_take" if k == "buildings_in_surface_take" else "above_tunnels"]
            elif k == "lots_within_protection_distance":
                vals[k] = s["zones"]["within_protection_distance_lots"]
            else:
                raise KeyError(k)
        rows[v] = vals
    return pd.DataFrame(rows).T[[c["key"] for c in criteria]].astype(float)


def normalise(raw: pd.DataFrame) -> pd.DataFrame:
    best, worst = raw.min(axis=0), raw.max(axis=0)
    span = worst - best
    out = (worst - raw) / span.replace(0, np.nan)
    return out.fillna(1.0)


def snap_ties(raw: pd.DataFrame, tol: float) -> pd.DataFrame:
    """Treat values within `tol` (relative) of the best value as equal to the best: min-max scaling
    otherwise turns small, possibly meaningless differences into a full point."""
    best = raw.min(axis=0)
    out = raw.copy()
    for c in raw.columns:
        out.loc[raw[c] <= best[c] * (1.0 + tol) + 1e-12, c] = best[c]
    return out


def weighted(scores: pd.DataFrame, weights: np.ndarray) -> pd.Series:
    w = np.asarray(weights, dtype=float)
    if np.any(w < 0) or w.sum() <= 0:
        raise ValueError("weights must be non-negative and not all zero")
    return scores @ (w / w.sum())


def rank(total: pd.Series) -> list[str]:
    """Variants from best to worst; ties broken by variant key so the order is deterministic."""
    return sorted(total.index, key=lambda v: (-round(float(total[v]), 12), v))


def one_at_a_time(scores: pd.DataFrame, weights: np.ndarray, factors: list[float]) -> list[dict]:
    out = []
    for j, crit in enumerate(scores.columns):
        for f in factors:
            w = np.array(weights, dtype=float)
            w[j] = w[j] * f
            t = weighted(scores, w)
            out.append({"criterion": crit, "factor": f, "winner": rank(t)[0], "ranking": rank(t)})
    return out


def leave_one_out(scores: pd.DataFrame, weights: np.ndarray) -> list[dict]:
    out = []
    for j, crit in enumerate(scores.columns):
        w = np.array(weights, dtype=float)
        w[j] = 0.0
        t = weighted(scores, w)
        out.append({"criterion_removed": crit, "winner": rank(t)[0], "ranking": rank(t)})
    return out


def random_weights(scores: pd.DataFrame, n: int, seed: int) -> dict:
    rng = np.random.default_rng(seed)
    W = rng.dirichlet(np.ones(scores.shape[1]), size=n)
    first = {v: 0 for v in scores.index}
    for w in W:
        first[rank(weighted(scores, w))[0]] += 1
    return {v: first[v] / n for v in scores.index}


def compare(summary: dict, cfg: dict) -> dict:
    crit = cfg["criteria"]
    raw = criteria_table(summary, crit)
    sc = normalise(raw)
    w = np.array([c["weight"] for c in crit], dtype=float)
    total = weighted(sc, w)
    sens = cfg["sensitivity"]
    oat = one_at_a_time(sc, w, sens["one_at_a_time_factor"])
    loo = leave_one_out(sc, w)
    rnd = random_weights(sc, sens["random_weights"]["n"], sens["random_weights"]["seed"])
    eq = weighted(sc, np.ones(len(crit)))
    tol = float(sens.get("tie_tolerance", 0.0))
    tied = weighted(normalise(snap_ties(raw, tol)), w)
    base_winner = rank(total)[0]
    return {
        "criteria": [{"key": c["key"], "label": c["label"], "weight": c["weight"],
                      "discriminates": bool(raw[c["key"]].max() > raw[c["key"]].min())} for c in crit],
        "raw": {v: {k: float(raw.loc[v, k]) for k in raw.columns} for v in raw.index},
        "scores": {v: {k: float(sc.loc[v, k]) for k in sc.columns} for v in sc.index},
        "total": {v: float(total[v]) for v in total.index},
        "ranking": rank(total),
        "equal_weights": {"total": {v: float(eq[v]) for v in eq.index}, "ranking": rank(eq)},
        "ties_within_tolerance": {"tolerance": tol, "total": {v: float(tied[v]) for v in tied.index},
                                  "ranking": rank(tied)},
        "one_at_a_time": oat,
        "one_at_a_time_same_winner": int(sum(1 for r in oat if r["winner"] == base_winner)),
        "one_at_a_time_runs": len(oat),
        "leave_one_out": loo,
        "leave_one_out_same_winner": int(sum(1 for r in loo if r["winner"] == base_winner)),
        "random_weights_first_share": rnd,
        "random_weights_n": sens["random_weights"]["n"],
    }
