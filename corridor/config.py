"""Paths, coordinate reference systems and the YAML inputs."""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path

import yaml
from pyproj import Transformer

ROOT = Path(__file__).resolve().parents[1]
INPUTS = ROOT / "inputs"
DATA = ROOT / "data"
RAW = DATA / "raw"
STUDY_GPKG = DATA / "study_area" / "study_area.gpkg"
RESULTS = ROOT / "results"
OUTPUTS = ROOT / "outputs"
DOCS = ROOT / "docs"

SVY21 = "EPSG:3414"   # SVY21 / Singapore TM, metres
WGS84 = "EPSG:4326"


@lru_cache(maxsize=None)
def corridor() -> dict:
    with open(INPUTS / "corridor.yaml", encoding="utf-8") as f:
        return yaml.safe_load(f)


@lru_cache(maxsize=None)
def scoring() -> dict:
    with open(INPUTS / "scoring.yaml", encoding="utf-8") as f:
        return yaml.safe_load(f)


@lru_cache(maxsize=None)
def facts() -> dict:
    with open(INPUTS / "facts.yaml", encoding="utf-8") as f:
        return yaml.safe_load(f)


def fact_value(fact_id: str, key: str = "value"):
    """Numeric value of a fact used in a calculation. Only VERIFIED facts may feed a calculation."""
    rows = {r["id"]: r for r in facts()["facts"]}
    row = rows[fact_id]
    if row["status"] != "VERIFIED":
        raise ValueError(f"fact {fact_id} is {row['status']}; only VERIFIED facts may be used in a calculation")
    return row[key]


def study_area_box() -> tuple[float, float, float, float]:
    x0, y0, x1, y1 = corridor()["study_area"]
    return float(x0), float(y0), float(x1), float(y1)


def to_wgs84() -> Transformer:
    return Transformer.from_crs(SVY21, WGS84, always_xy=True)


def to_svy21() -> Transformer:
    return Transformer.from_crs(WGS84, SVY21, always_xy=True)


def study_area_wgs84_bbox() -> tuple[float, float, float, float]:
    """(south, west, north, east) in degrees, enclosing the SVY21 study box (corners transformed)."""
    x0, y0, x1, y1 = study_area_box()
    t = to_wgs84()
    lons, lats = zip(*(t.transform(x, y) for x, y in [(x0, y0), (x0, y1), (x1, y0), (x1, y1)]))
    return min(lats), min(lons), max(lats), max(lons)
