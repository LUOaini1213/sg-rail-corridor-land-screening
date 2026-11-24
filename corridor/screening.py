"""Corridor screening: which lots each footprint component touches, how much area, what land use,
whether the lot is shown as State land in SLA's open layers, which buildings are involved, and which
lots fall within the railway protection distances of the fact sheet.

All areas are plan areas in square metres (SVY21). The corridor is ILLUSTRATIVE (fictional).
"""
from __future__ import annotations

from dataclasses import dataclass

import geopandas as gpd
import numpy as np
import pandas as pd

from . import components as comp_mod
from . import config

TAKES = ["permanent_surface", "permanent_subterranean", "temporary_surface"]
BANDS = ["first_reserve", "protection_zone", "safety_zone"]
MIN_PIECE_M2 = 1.0         # pieces smaller than this are boundary slivers (lot lines are approximate), counted apart
MIN_BUILDING_M2 = 1.0      # a building counts as involved when at least this much of it lies in the footprint
STATE_LAND_SHARE = 0.5     # a lot is "indicated as State land" when SLA's layers cover at least this share of it


def load_study(path=None) -> dict[str, gpd.GeoDataFrame]:
    path = path or config.STUDY_GPKG
    layers = ["lots", "land_use", "mp_buildings", "osm_buildings", "state_land_vacant", "state_land_agent",
              "state_reserve", "rail_lines", "rail_stations", "station_exits", "airspace_lots", "underground_structures"]
    return {k: gpd.read_file(path, layer=k) for k in layers}


def zone_distances() -> dict[str, float]:
    """Protection distances (m) taken from VERIFIED rows of the fact sheet (inputs/facts.yaml)."""
    return {"first_reserve": float(config.fact_value("F15")), "protection_zone": float(config.fact_value("F13")),
            "safety_zone": float(config.fact_value("F14")), "railway_corridor": float(config.fact_value("F12"))}


def default_subterranean_level_m_shd() -> float:
    """Level (m SHD) down to which surface owners own the subsoil by default, as MinLaw described the 2015 change."""
    return float(config.fact_value("F21"))


def state_land_geometry(study: dict[str, gpd.GeoDataFrame]):
    parts = [study[k].geometry for k in ("state_land_vacant", "state_land_agent", "state_reserve") if len(study[k])]
    if not parts:
        return None
    return gpd.GeoSeries(pd.concat(parts, ignore_index=True), crs=config.SVY21).union_all()


def lot_attributes(lots: gpd.GeoDataFrame, land_use: gpd.GeoDataFrame, state_geom) -> pd.DataFrame:
    """Per lot: area, dominant Master Plan land use (largest share of the lot) and the share shown as State land."""
    pieces = gpd.overlay(lots[["LOT_KEY", "geometry"]], land_use[["LU_DESC", "geometry"]], how="intersection",
                         keep_geom_type=True)
    pieces["a"] = pieces.area
    lu = pieces.groupby(["LOT_KEY", "LU_DESC"])["a"].sum().reset_index()
    lu = lu.sort_values(["LOT_KEY", "a", "LU_DESC"], ascending=[True, False, True])
    top = lu.drop_duplicates("LOT_KEY").set_index("LOT_KEY")
    out = pd.DataFrame({"LOT_KEY": lots["LOT_KEY"].values, "lot_area_m2": lots.area.values}).set_index("LOT_KEY")
    out["land_use"] = top["LU_DESC"]
    out["land_use_share"] = top["a"] / out["lot_area_m2"]
    if state_geom is None:
        out["state_land_share"] = 0.0
    else:
        out["state_land_share"] = [g.intersection(state_geom).area / g.area if g.area > 0 else 0.0
                                   for g in lots.geometry]
    out["state_land_indicated"] = out["state_land_share"] >= STATE_LAND_SHARE
    out["land_use"] = out["land_use"].fillna("NOT IN MASTER PLAN LAYER")
    return out.reset_index()


def overlay_all(lots: gpd.GeoDataFrame, comps: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    """Every piece of each component in each lot, slivers included."""
    pieces = gpd.overlay(comps, lots[["LOT_KEY", "geometry"]], how="intersection", keep_geom_type=True)
    pieces["area_m2"] = pieces.area
    return pieces.reset_index(drop=True)


def overlay(lots: gpd.GeoDataFrame, comps: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    """Pieces of each component in each lot that count as land take (area >= MIN_PIECE_M2)."""
    pieces = overlay_all(lots, comps)
    return pieces[pieces["area_m2"] >= MIN_PIECE_M2].reset_index(drop=True)


def area_accounting(lots: gpd.GeoDataFrame, comps: gpd.GeoDataFrame, all_pieces: gpd.GeoDataFrame) -> pd.DataFrame:
    """For each component: its area = pieces counted + slivers + part in no lot (+ residual, which should be ~0;
    a positive overlap between lots would make the residual negative)."""
    lot_union = lots.geometry.union_all()
    rows = []
    for c in comps.itertuples():
        a = c.geometry.area
        mine = all_pieces.loc[all_pieces["component_id"] == c.component_id, "area_m2"]
        counted = float(mine[mine >= MIN_PIECE_M2].sum())
        sliver = float(mine[mine < MIN_PIECE_M2].sum())
        gap = c.geometry.difference(lot_union).area
        rows.append({"component_id": c.component_id, "component_area_m2": a, "counted_pieces_m2": counted,
                     "sliver_pieces_m2": sliver, "n_slivers": int((mine < MIN_PIECE_M2).sum()),
                     "outside_lots_m2": gap, "residual_m2": a - (counted + sliver + gap)})
    return pd.DataFrame(rows)


def tenure_evidence(state_land: bool, land_use: str) -> str:
    """What the open data say about tenure. Only SLA's layers indicate State land; the rest is unknown."""
    if state_land:
        return "State land (SLA open layer)"
    if land_use == "ROAD":
        return "Unknown: Master Plan road zone"
    if land_use in ("PARK", "OPEN SPACE"):
        return "Unknown: Master Plan park or open space"
    return "Unknown"


def zone_rings(structure, distances: dict[str, float]) -> dict[str, object]:
    """Distance bands measured outward from the outer edge of the railway structure (the structure itself excluded)."""
    d1, d2, d3 = distances["first_reserve"], distances["protection_zone"], distances["safety_zone"]
    b1, b2, b3 = (structure.buffer(d, quad_segs=32) for d in (d1, d2, d3))
    return {"first_reserve": b1.difference(structure), "protection_zone": b2.difference(b1),
            "safety_zone": b3.difference(b2)}


def zone_pieces(lots: gpd.GeoDataFrame, rings: dict[str, object]) -> pd.DataFrame:
    rows = []
    for band, ring in rings.items():
        idx = lots.sindex.query(ring, predicate="intersects")
        for i in idx:
            a = lots.geometry.iloc[i].intersection(ring).area
            if a >= MIN_PIECE_M2:
                rows.append({"LOT_KEY": lots["LOT_KEY"].iloc[i], "band": band, "area_m2": a})
    return pd.DataFrame(rows, columns=["LOT_KEY", "band", "area_m2"])


def buildings_involved(comps: gpd.GeoDataFrame, buildings: gpd.GeoDataFrame, id_col: str,
                       type_col: str | None = None, exclude_types: tuple[str, ...] = ()) -> pd.DataFrame:
    b = buildings
    if type_col and exclude_types:
        b = b[~b[type_col].isin(exclude_types)]
    rows = []
    for c in comps.itertuples():
        idx = b.sindex.query(c.geometry, predicate="intersects")
        for i in idx:
            g = b.geometry.iloc[i]
            a = g.intersection(c.geometry).area
            if a >= MIN_BUILDING_M2:
                rows.append({"component_id": c.component_id, "component_type": c.component_type,
                             "building_id": str(b[id_col].iloc[i]),
                             "building_type": str(b[type_col].iloc[i]) if type_col else "",
                             "area_in_footprint_m2": a, "building_area_m2": g.area})
    return pd.DataFrame(rows, columns=["component_id", "component_type", "building_id", "building_type",
                                       "area_in_footprint_m2", "building_area_m2"])


def buildings_by_lot(pieces: gpd.GeoDataFrame, osm: gpd.GeoDataFrame) -> dict[str, int]:
    """Distinct buildings (OSM, roofs left out) inside the surface take of each lot. A building that two pieces
    of the same lot touch is counted once; one that spans two lots is counted on each."""
    surf = pieces[pieces["take"] != "permanent_subterranean"]
    b = osm[~osm["building"].isin(["roof"])]
    ids: dict[str, set] = {}
    for r in surf.itertuples():
        idx = b.sindex.query(r.geometry, predicate="intersects")
        found = {b["osm_id"].iloc[i] for i in idx if b.geometry.iloc[i].intersection(r.geometry).area >= MIN_BUILDING_M2}
        ids.setdefault(r.LOT_KEY, set()).update(found)
    return {k: len(v) for k, v in ids.items()}


def existing_railway_interfaces(comps: gpd.GeoDataFrame, rail_lines: gpd.GeoDataFrame,
                                stations: gpd.GeoDataFrame, distances: dict[str, float]) -> pd.DataFrame:
    """Distance from each component to the indicative Master Plan rail lines and station outlines.

    The Master Plan lines are indicative centre lines, not structure edges, so the true distance to the
    structure is smaller than reported: membership of a zone here is a lower bound.
    """
    lines = rail_lines.geometry.union_all() if len(rail_lines) else None
    stn = stations.geometry.union_all() if len(stations) else None
    rows = []
    for c in comps.itertuples():
        d_line = float(c.geometry.distance(lines)) if lines is not None else float("inf")
        d_stn = float(c.geometry.distance(stn)) if stn is not None else float("inf")
        d = min(d_line, d_stn)
        if d <= distances["first_reserve"]:
            zone = "first_reserve"
        elif d <= distances["protection_zone"]:
            zone = "protection_zone"
        elif d <= distances["safety_zone"]:
            zone = "safety_zone"
        else:
            zone = "outside"
        rows.append({"component_id": c.component_id, "distance_to_rail_line_m": d_line,
                     "distance_to_station_outline_m": d_stn, "existing_railway_zone": zone})
    return pd.DataFrame(rows)


@dataclass
class Instrument:
    code: str
    text: str
    agency: str


def instrument_for(take: str, state_land: bool, crown_level: float, default_level: float) -> Instrument:
    """Route each interest to the public mechanism the fact sheet describes. Tenure is only *indicated* by
    SLA's open layers, so every route says what has to be confirmed."""
    if take == "permanent_surface":
        if state_land:
            return Instrument("STATE-SURFACE", "Shown as State land: no acquisition under the Land Acquisition Act; "
                              "arrangement with SLA (the process is not described in the public sources used)", "SLA")
        return Instrument("ACQ-SURFACE", "If not State land: acquisition by declaration under s.5 Land Acquisition Act "
                          "(whole or part lot). Confirm tenure with SLA first", "SLA")
    if take == "permanent_subterranean":
        if state_land:
            return Instrument("STATE-STRATUM", "Shown as State land: no acquisition of the stratum", "SLA")
        if crown_level > default_level:
            return Instrument("ACQ-STRATUM", "If not State land: subterranean stratum only, s.5(1A) Land Acquisition Act; "
                              "the tunnel lies above the default ownership depth MinLaw described. Confirm tenure and the "
                              "depth stated in the State title with SLA", "SLA")
        return Instrument("CHECK-TITLE", "The tunnel lies below the default ownership depth MinLaw described: confirm the "
                          "depth in the State title before assuming no acquisition is needed", "SLA")
    if take == "temporary_surface":
        if state_land:
            return Instrument("TOL", "Temporary Occupation Licence over State land (State Lands Rules r.19)", "SLA")
        return Instrument("TEMP-OCC", "If not State land: temporary occupation under s.42 Land Acquisition Act "
                          "(ordinarily up to 3 continuous years); if State land: TOL. Confirm tenure with SLA", "SLA")
    raise ValueError(take)


ZONE_INSTRUMENT = Instrument("RAIL-ZONE", "Within the railway corridor / protection distances of the structure: "
                             "development and works controls administered by LTA (Development & Building Control (Rail))",
                             "LTA")


def lot_schedule(variant: str, pieces: gpd.GeoDataFrame, attrs: pd.DataFrame, zpieces: pd.DataFrame,
                 bld: pd.DataFrame, lot_pieces_bld: dict, crown_level: float, default_level: float) -> pd.DataFrame:
    """One row per lot that has any interest or lies within the safety-zone distance."""
    take_area = pieces.pivot_table(index="LOT_KEY", columns="take", values="area_m2", aggfunc="sum").reindex(columns=TAKES)
    band_area = (zpieces.pivot_table(index="LOT_KEY", columns="band", values="area_m2", aggfunc="sum").reindex(columns=BANDS)
                 if len(zpieces) else pd.DataFrame(columns=BANDS))
    keys = sorted(set(take_area.index) | set(band_area.index))
    df = pd.DataFrame(index=pd.Index(keys, name="LOT_KEY"))
    for t in TAKES:
        df[f"{t}_m2"] = take_area[t].reindex(keys).fillna(0.0) if len(take_area) else 0.0
    for b in BANDS:
        df[f"{b}_m2"] = band_area[b].reindex(keys).fillna(0.0) if b in band_area else 0.0
    a = attrs.set_index("LOT_KEY").reindex(keys)
    df["lot_area_m2"] = a["lot_area_m2"]
    df["land_use"] = a["land_use"]
    df["state_land_indicated"] = a["state_land_indicated"].astype(bool)
    df["tenure_evidence"] = [tenure_evidence(s, lu) for s, lu in zip(df["state_land_indicated"], df["land_use"])]
    df["buildings_in_surface_take"] = [lot_pieces_bld.get(k, 0) for k in keys]
    insts, agencies = [], []
    for k, row in df.iterrows():
        found = []
        for t in TAKES:
            if row[f"{t}_m2"] > 0:
                found.append(instrument_for(t, bool(row["state_land_indicated"]), crown_level, default_level))
        if any(row[f"{b}_m2"] > 0 for b in BANDS):
            found.append(ZONE_INSTRUMENT)
        insts.append(";".join(i.code for i in found))
        agencies.append(";".join(sorted({i.agency for i in found})))
    df["instruments"] = insts
    df["agencies"] = agencies
    df["variant"] = variant
    df["in_scope"] = (df[[f"{t}_m2" for t in TAKES]].sum(axis=1) > 0)
    return df.reset_index()


def screen_variant(key: str, al, comps: gpd.GeoDataFrame, study: dict, attrs: pd.DataFrame) -> dict:
    geo = config.corridor()["geometry"]
    distances = zone_distances()
    crown, invert = comp_mod.tunnel_levels(geo)
    default_level = default_subterranean_level_m_shd()
    lots = study["lots"]
    all_pieces = overlay_all(lots, comps)
    pieces = all_pieces[all_pieces["area_m2"] >= MIN_PIECE_M2].reset_index(drop=True)
    acct = area_accounting(lots, comps, all_pieces)
    structure = comp_mod.railway_structure(comps)
    rings = zone_rings(structure, distances)
    zp = zone_pieces(lots, rings)
    osm = study["osm_buildings"]
    bld = buildings_involved(comps, osm, "osm_id", "building", exclude_types=("roof",))
    roofs = buildings_involved(comps, osm[osm["building"] == "roof"], "osm_id", "building")
    mpb = buildings_involved(comps, study["mp_buildings"], "OBJECTID", "BLDG_TYPE")
    sched = lot_schedule(key, pieces, attrs, zp, bld, buildings_by_lot(pieces, osm), crown, default_level)
    iface = existing_railway_interfaces(comps, study["rail_lines"], study["rail_stations"], distances)
    return {"pieces": pieces, "accounting": acct, "zone_pieces": zp, "rings": rings, "structure": structure,
            "buildings": bld, "roofs": roofs, "mp_buildings": mpb, "schedule": sched, "interfaces": iface,
            "alignment": al, "components": comps}


def summarise(key: str, label: str, res: dict, attrs: pd.DataFrame) -> dict:
    sched = res["schedule"]
    pieces = res["pieces"].merge(attrs[["LOT_KEY", "land_use", "state_land_indicated"]], on="LOT_KEY", how="left")
    by_lu = pieces.pivot_table(index="land_use", columns="take", values="area_m2", aggfunc="sum").reindex(columns=TAKES).fillna(0.0)
    by_state = pieces.pivot_table(index="state_land_indicated", columns="take", values="area_m2", aggfunc="sum").reindex(columns=TAKES).fillna(0.0)
    bld = res["buildings"]
    in_scope = sched[sched["in_scope"]]
    totals = {f"{t}_m2": float(sched[f"{t}_m2"].sum()) for t in TAKES}
    totals.update({
        "lots_in_scope": int(len(in_scope)),
        "lots_permanent_surface": int((sched["permanent_surface_m2"] > 0).sum()),
        "lots_subterranean": int((sched["permanent_subterranean_m2"] > 0).sum()),
        "lots_temporary": int((sched["temporary_surface_m2"] > 0).sum()),
        "lots_state_land_indicated_in_scope": int(in_scope["state_land_indicated"].sum()),
        "subterranean_not_state_m2": float(sched.loc[~sched["state_land_indicated"], "permanent_subterranean_m2"].sum()),
        "permanent_surface_not_state_m2": float(sched.loc[~sched["state_land_indicated"], "permanent_surface_m2"].sum()),
        "temporary_not_state_m2": float(sched.loc[~sched["state_land_indicated"], "temporary_surface_m2"].sum()),
        "permanent_surface_residential_m2": float(sched.loc[sched["land_use"].str.startswith("RESIDENTIAL"), "permanent_surface_m2"].sum()),
    })
    zones = {}
    for b in BANDS:
        lots_b = sched[(sched[f"{b}_m2"] > 0) & (~sched["in_scope"])]
        zones[b] = {"lots_outside_footprint": int(len(lots_b)), "area_m2": float(sched[f"{b}_m2"].sum())}
    zones["within_protection_distance_lots"] = int(((sched["first_reserve_m2"] + sched["protection_zone_m2"]) > 0).sum())
    buildings = {
        "in_station_boxes": int(bld.loc[bld["component_type"] == "station_box", "building_id"].nunique()),
        "in_worksites": int(bld.loc[bld["component_type"] == "worksite", "building_id"].nunique()),
        "above_tunnels": int(bld.loc[bld["component_type"] == "bored_tunnel", "building_id"].nunique()),
        "roof_structures_any": int(res["roofs"]["building_id"].nunique()),
        "mp_hdb_above_tunnels": int(res["mp_buildings"].loc[(res["mp_buildings"]["component_type"] == "bored_tunnel")
                                                          & (res["mp_buildings"]["building_type"].str.strip() == "HDB"), "building_id"].nunique()),
        "mp_any_in_surface_take": int(res["mp_buildings"].loc[res["mp_buildings"]["component_type"] != "bored_tunnel", "building_id"].nunique()),
    }
    buildings["in_surface_take"] = int(bld.loc[bld["component_type"] != "bored_tunnel", "building_id"].nunique())
    inst = {}
    for s in sched.loc[sched["instruments"] != "", "instruments"]:
        for c in s.split(";"):
            inst[c] = inst.get(c, 0) + 1
    acct = res["accounting"]
    comps = {r.component_id: {"type": r.component_type, "take": r.take, "area_m2": float(r.geometry.area)}
             for r in res["components"].itertuples()}
    tenure = in_scope.groupby("tenure_evidence").size().to_dict()
    return {
        "label": label,
        "length_m": float(res["alignment"].length),
        "curves": len(res["alignment"].arcs),
        "components": comps,
        "totals": totals,
        "by_land_use_m2": {lu: {t: float(by_lu.loc[lu, t]) for t in TAKES} for lu in by_lu.index},
        "by_state_land_indication_m2": {("indicated" if bool(k) else "not_indicated"): {t: float(by_state.loc[k, t]) for t in TAKES}
                                        for k in by_state.index},
        "zones": zones,
        "buildings": buildings,
        "instruments_lots": dict(sorted(inst.items())),
        "tenure_evidence_lots": {k: int(v) for k, v in sorted(tenure.items())},
        "existing_railway_interfaces": res["interfaces"].round(1).to_dict(orient="records"),
        "area_accounting_max_residual_m2": float(acct["residual_m2"].abs().max()),
        "area_outside_lots_m2": float(acct["outside_lots_m2"].sum()),
        "slivers": {"count": int(acct["n_slivers"].sum()), "area_m2": float(acct["sliver_pieces_m2"].sum())},
    }


def run(study: dict | None = None) -> tuple[dict, dict, pd.DataFrame]:
    study = study or load_study()
    attrs = lot_attributes(study["lots"], study["land_use"], state_land_geometry(study))
    variants = comp_mod.all_variants()
    labels = {k: v["label"] for k, v in config.corridor()["variants"].items()}
    full, summary = {}, {}
    for k, (al, comps) in variants.items():
        res = screen_variant(k, al, comps, study, attrs)
        full[k] = res
        summary[k] = summarise(k, labels[k], res, attrs)
    return full, summary, attrs


def np_round(x, n=1):
    return float(np.round(x, n))
