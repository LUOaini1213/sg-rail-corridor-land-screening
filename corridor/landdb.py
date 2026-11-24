"""A small land database in a GeoPackage: parcels, alignment versions, affected areas, interests, the status
of each acquisition or occupation step, documents, a change log and the validation rules.

Statuses, dates and documents in the demo are SYNTHETIC: they show how the database behaves, not the state
of any real case. Step lists follow the public sources in the fact sheet where one exists (marked with the
fact ID); the rest are the author's checklist (marked ILLUSTRATIVE).
"""
from __future__ import annotations

import hashlib
import json
import sqlite3
from datetime import date
from pathlib import Path

import geopandas as gpd
import pandas as pd


from . import components as comp_mod
from . import config, screening

SCHEMA_VERSION = "1.0"
AS_OF = "2026-11-24"   # fixed date stamped on records so that rebuilding the database is reproducible
TEMP_START, TEMP_END = date(2028, 1, 1), date(2030, 12, 31)   # SYNTHETIC occupation period for the demo

STEP_TEMPLATES: dict[str, list[tuple[str, str, bool]]] = {
    # (step name, source, mandatory)
    "ACQ-SURFACE": [("Confirm tenure and title particulars (lot search)", "ILLUSTRATIVE", True),
                    ("Notice of acquisition", "F06", True), ("Collector's inquiry", "F06", True),
                    ("Collector's award", "F06", True), ("Payment of compensation and site possession", "F06", True),
                    ("Appeal to the Appeals Board (if lodged)", "F06", False)],
    "ACQ-STRATUM": [("Confirm tenure and the depth stated in the State title", "ILLUSTRATIVE", True),
                    ("Define the stratum (plan and levels)", "ILLUSTRATIVE", True),
                    ("Notice of acquisition", "F06", True), ("Collector's inquiry", "F06", True),
                    ("Collector's award", "F06", True), ("Payment of compensation and site possession", "F06", True),
                    ("Appeal to the Appeals Board (if lodged)", "F06", False)],
    "TEMP-OCC": [("Confirm the land is not State land", "ILLUSTRATIVE", True),
                 ("Notice to interested persons and occupiers (at least one month)", "F10", True),
                 ("Temporary possession", "F10", True), ("Return of the land at the end of the term", "ILLUSTRATIVE", True),
                 ("Compensation claims settled", "ILLUSTRATIVE", False)],
    "TOL": [("Confirm the land is State land", "ILLUSTRATIVE", True), ("Apply for a Temporary Occupation Licence", "F09", True),
            ("Licence issued", "F08", True), ("Licence ends and site handed back", "ILLUSTRATIVE", True)],
    "STATE-SURFACE": [("Confirm State land and agree the arrangement with SLA", "ILLUSTRATIVE", True)],
    "STATE-STRATUM": [("Confirm State land and agree the arrangement with SLA", "ILLUSTRATIVE", True)],
    "CHECK-TITLE": [("Confirm the depth stated in the State title", "ILLUSTRATIVE", True)],
    "RAIL-ZONE": [("Record the lot as within the protection distances", "ILLUSTRATIVE", True),
                  ("Track the gazette of the railway area", "F16", False)],
}
STEP_STATUSES = ("not_started", "in_progress", "done", "not_applicable", "withdrawn")

# Attribute tables: (column, SQL type and constraint, meaning). Spatial layers are described in SPATIAL.
SPATIAL = {
    "parcels": {"description": "Cadastral lots in the study area with land use and the State-land indicator", "columns": [
        ("lot_key", "TEXT, unique", "SLA lot key (mukim or town subdivision, lot number); identifier only"),
        ("lot_area_m2", "REAL", "Plan area of the lot polygon (SVY21), not the title area"),
        ("land_use", "TEXT", "Master Plan 2025 zone covering the largest share of the lot"),
        ("land_use_share", "REAL", "Share of the lot under that zone"),
        ("state_land_share", "REAL", "Share of the lot covered by SLA's open State-land layers"),
        ("state_land_indicated", "INTEGER 0/1", "1 when that share is at least one half"),
        ("tenure_evidence", "TEXT", "What the open data say about tenure"),
        ("source", "TEXT", "Origin of the geometry"),
        ("geometry", "POLYGON / MULTIPOLYGON, EPSG:3414", "Lot boundary as published (approximate)")]},
    "affected_areas": {"description": "Pieces of each footprint component in each lot, per alignment version", "columns": [
        ("area_id", "TEXT, unique", "version:component:lot:n"),
        ("version_id", "TEXT", "Alignment version"), ("component_id", "TEXT", "Box, tunnel or worksite"),
        ("component_type", "TEXT", "station_box, bored_tunnel or worksite"),
        ("take", "TEXT", "permanent_surface, permanent_subterranean or temporary_surface"),
        ("lot_key", "TEXT", "Lot"), ("area_m2", "REAL", "Plan area of the piece"),
        ("geometry", "POLYGON / MULTIPOLYGON, EPSG:3414", "The piece")]},
}

SCHEMA: dict[str, dict] = {
    "alignment_versions": {"description": "Each alignment variant or revision the database has seen", "columns": [
        ("version_id", "TEXT NOT NULL UNIQUE", "e.g. A-v1"), ("variant", "TEXT NOT NULL", "Variant key"),
        ("label", "TEXT", "Description"), ("pis_json", "TEXT NOT NULL", "Points of intersection, SVY21"),
        ("geometry_sha", "TEXT NOT NULL", "Hash of the PIs"), ("status", "TEXT NOT NULL", "baseline, option, revision or superseded"),
        ("created", "TEXT", "Date stamped on the record")]},
    "interests": {"description": "Land interest needed in a lot for one alignment version", "columns": [
        ("interest_id", "TEXT NOT NULL UNIQUE", "version:lot:instrument"),
        ("version_id", "TEXT NOT NULL REFERENCES alignment_versions(version_id)", "Alignment version"),
        ("lot_key", "TEXT NOT NULL REFERENCES parcels(lot_key)", "Lot"),
        ("interest_type", "TEXT NOT NULL", "permanent_surface, permanent_subterranean, temporary_surface or zone"),
        ("instrument_code", "TEXT NOT NULL", "Mechanism code (see README)"), ("instrument_text", "TEXT", "Mechanism in words"),
        ("agency", "TEXT", "Agency to liaise with, per the public sources"), ("area_m2", "REAL NOT NULL", "Plan area"),
        ("stratum_top_m_shd", "REAL", "Top of a subterranean stratum, m SHD"),
        ("stratum_bottom_m_shd", "REAL", "Bottom of a subterranean stratum, m SHD"),
        ("status", "TEXT NOT NULL", "proposed, superseded or withdrawn"),
        ("start_date", "TEXT", "Start of temporary occupation (SYNTHETIC)"), ("end_date", "TEXT", "End of temporary occupation (SYNTHETIC)"),
        ("created", "TEXT", "Date stamped on the record"), ("updated", "TEXT", "Date of the last change")]},
    "steps": {"description": "Status of each acquisition or occupation step of an interest", "columns": [
        ("step_id", "TEXT NOT NULL UNIQUE", "interest:seq"),
        ("interest_id", "TEXT NOT NULL REFERENCES interests(interest_id)", "Interest"),
        ("seq", "INTEGER NOT NULL", "Order"), ("step_name", "TEXT NOT NULL", "Step"),
        ("source", "TEXT NOT NULL", "Fact-sheet row the step comes from, or ILLUSTRATIVE"),
        ("mandatory", "INTEGER NOT NULL", "1 if the step cannot be skipped"),
        ("status", "TEXT NOT NULL", "not_started, in_progress, done, not_applicable or withdrawn"),
        ("date", "TEXT", "Date of the status (SYNTHETIC)"), ("note", "TEXT", "Note")]},
    "documents": {"description": "Documents to obtain or held for an interest (SYNTHETIC placeholders)", "columns": [
        ("doc_id", "TEXT NOT NULL UNIQUE", "Identifier"),
        ("interest_id", "TEXT REFERENCES interests(interest_id)", "Interest"),
        ("lot_key", "TEXT REFERENCES parcels(lot_key)", "Lot"), ("doc_type", "TEXT NOT NULL", "Kind of document"),
        ("title", "TEXT", "Title"), ("status", "TEXT NOT NULL", "to_obtain, received or not_applicable"),
        ("reference", "TEXT", "Reference"), ("date", "TEXT", "Date"), ("note", "TEXT", "Note")]},
    "change_log": {"description": "Every change made after the first load, with the reason", "columns": [
        ("change_id", "INTEGER NOT NULL UNIQUE", "Sequence"), ("timestamp", "TEXT NOT NULL", "Date stamped on the change"),
        ("version_id", "TEXT", "Alignment version that caused it"), ("table_name", "TEXT NOT NULL", "Table"),
        ("record_id", "TEXT NOT NULL", "Record"), ("field", "TEXT NOT NULL", "Field"),
        ("old_value", "TEXT", "Before"), ("new_value", "TEXT", "After"), ("reason", "TEXT", "Why")]},
    "validation_rules": {"description": "Rules checked by corridor.landdb.LandDB.validate()", "columns": [
        ("rule_id", "TEXT NOT NULL UNIQUE", "Rule"), ("description", "TEXT NOT NULL", "What is checked"),
        ("severity", "TEXT NOT NULL", "error or warning")]},
    "metadata": {"description": "Schema version, CRS and disclaimer", "columns": [
        ("key", "TEXT NOT NULL UNIQUE", "Key"), ("value", "TEXT", "Value")]},
}
for _t in SCHEMA.values():
    _t["columns"] = [c if len(c) == 3 else (c[0], c[1], "") for c in _t["columns"]]

VALIDATION_RULES = [
    ("V01", "Primary keys are unique in every table", "error"),
    ("V02", "Every interest and affected area refers to an existing parcel", "error"),
    ("V03", "Every interest and affected area refers to an existing alignment version", "error"),
    ("V04", "Interest area is positive and not larger than the parcel", "error"),
    ("V05", "Surface take (permanent plus temporary) on a lot does not exceed the lot area in any version", "error"),
    ("V06", "Temporary occupation under s.42 runs no longer than the fact-sheet limit; TOLs under 10 years", "error"),
    ("V07", "Instrument agrees with the tenure indicator (TOL only on land shown as State land; s.42 only on land not shown as State land)", "error"),
    ("V08", "A stratum has its top above its bottom", "error"),
    ("V09", "Steps: a mandatory step is not done while an earlier mandatory step is not done; withdrawn interests have no step in progress", "error"),
    ("V10", "Documents refer to an existing interest or parcel", "error"),
    ("V11", "Geometries are valid, not empty and in EPSG:3414", "error"),
    ("V12", "Interest area equals the sum of its affected-area pieces", "error"),
]


def geometry_hash(pis) -> str:
    return hashlib.sha256(json.dumps([[float(x), float(y)] for x, y in pis]).encode()).hexdigest()[:16]


def interests_from_screening(version_id: str, res: dict, attrs: pd.DataFrame, crown: float, invert: float,
                             default_level: float) -> tuple[pd.DataFrame, gpd.GeoDataFrame]:
    """Interests (one per lot and take, plus one zone interest per lot in the protection distances) and the
    affected-area pieces behind them."""
    pieces = res["pieces"].copy()
    pieces["version_id"] = version_id
    pieces["area_id"] = [f"{version_id}:{c}:{k}:{i}" for i, (c, k) in enumerate(zip(pieces["component_id"], pieces["LOT_KEY"]))]
    aff = gpd.GeoDataFrame(pieces.rename(columns={"LOT_KEY": "lot_key"})[
        ["area_id", "version_id", "component_id", "component_type", "take", "lot_key", "area_m2", "geometry"]],
        geometry="geometry", crs=config.SVY21)
    state = attrs.set_index("LOT_KEY")["state_land_indicated"]
    rows = []
    for (lot, take), g in pieces.groupby(["LOT_KEY", "take"]):
        inst = screening.instrument_for(take, bool(state[lot]), crown, default_level)
        is_temp = take == "temporary_surface"
        is_sub = take == "permanent_subterranean"
        rows.append({"interest_id": f"{version_id}:{lot}:{inst.code}", "version_id": version_id, "lot_key": lot,
                     "interest_type": take, "instrument_code": inst.code, "instrument_text": inst.text,
                     "agency": inst.agency, "area_m2": float(g["area_m2"].sum()),
                     "stratum_top_m_shd": crown if is_sub else None, "stratum_bottom_m_shd": invert if is_sub else None,
                     "status": "proposed", "start_date": TEMP_START.isoformat() if is_temp else None,
                     "end_date": TEMP_END.isoformat() if is_temp else None, "created": AS_OF, "updated": AS_OF})
    zp = res["zone_pieces"]
    if len(zp):
        for lot, g in zp.groupby("LOT_KEY"):
            rows.append({"interest_id": f"{version_id}:{lot}:RAIL-ZONE", "version_id": version_id, "lot_key": lot,
                         "interest_type": "zone", "instrument_code": "RAIL-ZONE",
                         "instrument_text": screening.ZONE_INSTRUMENT.text, "agency": "LTA",
                         "area_m2": float(g["area_m2"].sum()), "stratum_top_m_shd": None, "stratum_bottom_m_shd": None,
                         "status": "proposed", "start_date": None, "end_date": None, "created": AS_OF, "updated": AS_OF})
    return pd.DataFrame(rows), aff


def steps_for(interests: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for r in interests.itertuples():
        for seq, (name, src, mandatory) in enumerate(STEP_TEMPLATES[r.instrument_code], start=1):
            rows.append({"step_id": f"{r.interest_id}:{seq}", "interest_id": r.interest_id, "seq": seq,
                         "step_name": name, "source": src, "mandatory": int(mandatory), "status": "not_started",
                         "date": None, "note": None})
    return pd.DataFrame(rows)


def documents_for(interests: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for r in interests.itertuples():
        if r.instrument_code == "RAIL-ZONE":
            continue
        rows.append({"doc_id": f"DOC:{r.interest_id}:LOT", "interest_id": r.interest_id, "lot_key": r.lot_key,
                     "doc_type": "lot particulars search", "title": f"Lot particulars for {r.lot_key}",
                     "status": "to_obtain", "reference": None, "date": None, "note": "SYNTHETIC placeholder"})
        if r.instrument_code == "ACQ-STRATUM":
            rows.append({"doc_id": f"DOC:{r.interest_id}:STRATUM", "interest_id": r.interest_id, "lot_key": r.lot_key,
                         "doc_type": "stratum plan", "title": f"Plan and levels of the stratum under {r.lot_key}",
                         "status": "to_obtain", "reference": None, "date": None, "note": "SYNTHETIC placeholder"})
    return pd.DataFrame(rows)


def parcels_table(lots: gpd.GeoDataFrame, attrs: pd.DataFrame) -> gpd.GeoDataFrame:
    a = attrs.set_index("LOT_KEY")
    p = lots[["LOT_KEY", "geometry"]].rename(columns={"LOT_KEY": "lot_key"}).copy()
    p["lot_area_m2"] = p.geometry.area
    p["land_use"] = a.loc[p["lot_key"], "land_use"].values
    p["land_use_share"] = a.loc[p["lot_key"], "land_use_share"].values
    p["state_land_share"] = a.loc[p["lot_key"], "state_land_share"].values
    p["state_land_indicated"] = a.loc[p["lot_key"], "state_land_indicated"].astype(int).values
    p["tenure_evidence"] = [screening.tenure_evidence(bool(s), lu) for s, lu in zip(p["state_land_indicated"], p["land_use"])]
    p["source"] = "SLA Cadastral Land Parcel (data.gov.sg), lot lines approximate"
    return gpd.GeoDataFrame(p, geometry="geometry", crs=config.SVY21)


class LandDB:
    """In-memory tables plus write/read to a GeoPackage."""

    def __init__(self, parcels: gpd.GeoDataFrame):
        self.parcels = parcels
        self.versions = pd.DataFrame(columns=["version_id", "variant", "label", "pis_json", "geometry_sha", "status", "created"])
        self.affected = gpd.GeoDataFrame(columns=["area_id", "version_id", "component_id", "component_type", "take",
                                                  "lot_key", "area_m2", "geometry"], geometry="geometry", crs=config.SVY21)
        self.interests = pd.DataFrame()
        self.steps = pd.DataFrame()
        self.documents = pd.DataFrame()
        self.changes: list[dict] = []

    # -- building ------------------------------------------------------------------------------------
    def add_version(self, version_id: str, variant: str, label: str, pis, res: dict, attrs: pd.DataFrame,
                    status: str = "baseline") -> None:
        geo = config.corridor()["geometry"]
        crown, invert = comp_mod.tunnel_levels(geo)
        ints, aff = interests_from_screening(version_id, res, attrs, crown, invert,
                                             screening.default_subterranean_level_m_shd())
        self.versions = pd.concat([self.versions, pd.DataFrame([{
            "version_id": version_id, "variant": variant, "label": label,
            "pis_json": json.dumps([[float(x), float(y)] for x, y in pis]), "geometry_sha": geometry_hash(pis),
            "status": status, "created": AS_OF}])], ignore_index=True)
        self.affected = gpd.GeoDataFrame(pd.concat([self.affected, aff], ignore_index=True), geometry="geometry", crs=config.SVY21)
        self.interests = pd.concat([self.interests, ints], ignore_index=True)
        self.steps = pd.concat([self.steps, steps_for(ints)], ignore_index=True)
        self.documents = pd.concat([self.documents, documents_for(ints)], ignore_index=True)

    def log(self, version_id: str, table: str, record: str, field: str, old, new, reason: str) -> None:
        self.changes.append({"change_id": len(self.changes) + 1, "timestamp": AS_OF, "version_id": version_id,
                             "table_name": table, "record_id": record, "field": field,
                             "old_value": None if old is None else str(old), "new_value": None if new is None else str(new),
                             "reason": reason})

    def set_step(self, step_id: str, status: str, when: str, note: str) -> None:
        if status not in STEP_STATUSES:
            raise ValueError(status)
        i = self.steps.index[self.steps["step_id"] == step_id]
        if len(i) != 1:
            raise KeyError(step_id)
        old = self.steps.at[i[0], "status"]
        self.steps.loc[i[0], ["status", "date", "note"]] = [status, when, note]
        vid = self.interests.loc[self.interests["interest_id"] == self.steps.at[i[0], "interest_id"], "version_id"].iloc[0]
        self.log(vid, "steps", step_id, "status", old, status, note)

    # -- alignment change ----------------------------------------------------------------------------
    def revise(self, base_version: str, new_version: str, variant: str, label: str, pis, res: dict,
               attrs: pd.DataFrame, area_tol_m2: float = 1.0) -> dict:
        """Add a revised alignment and reconcile its interests with the base version.

        Lots only in the base: their interests are withdrawn (steps not done become 'withdrawn'; steps
        already done are kept and flagged for review). Lots only in the new version: new interests. Lots in
        both: the area change and any change of instrument are logged.
        """
        self.add_version(new_version, variant, label, pis, res, attrs, status="revision")
        self.versions.loc[self.versions["version_id"] == base_version, "status"] = "superseded"
        self.log(new_version, "alignment_versions", base_version, "status", "baseline", "superseded", f"replaced by {new_version}")
        old = self.interests[self.interests["version_id"] == base_version]
        new = self.interests[self.interests["version_id"] == new_version]
        key = lambda d: {(r.lot_key, r.interest_type): r for r in d.itertuples()}
        ko, kn = key(old), key(new)
        out_keys, in_keys = sorted(set(ko) - set(kn)), sorted(set(kn) - set(ko))
        both = sorted(set(ko) & set(kn))
        review = []
        for k in out_keys:
            r = ko[k]
            idx = self.interests.index[self.interests["interest_id"] == r.interest_id][0]
            self.interests.loc[idx, ["status", "updated"]] = ["withdrawn", AS_OF]
            self.log(new_version, "interests", r.interest_id, "status", "proposed", "withdrawn",
                     f"lot out of scope after {new_version}")
            for s in self.steps[self.steps["interest_id"] == r.interest_id].itertuples():
                if s.status == "done":
                    review.append(s.step_id)
                    self.log(new_version, "steps", s.step_id, "note", s.note, "completed before revision: review",
                             "interest withdrawn after the step was completed")
                    self.steps.loc[self.steps["step_id"] == s.step_id, "note"] = "completed before revision: review"
                else:
                    self.steps.loc[self.steps["step_id"] == s.step_id, "status"] = "withdrawn"
        for k in in_keys:
            r = kn[k]
            self.log(new_version, "interests", r.interest_id, "status", None, "proposed", f"lot newly in scope in {new_version}")
        changed = []
        for k in both:
            a, b = ko[k], kn[k]
            if abs(a.area_m2 - b.area_m2) > area_tol_m2 or a.instrument_code != b.instrument_code:
                changed.append({"lot_key": k[0], "interest_type": k[1], "old_area_m2": float(a.area_m2),
                                "new_area_m2": float(b.area_m2), "old_instrument": a.instrument_code,
                                "new_instrument": b.instrument_code})
                self.log(new_version, "interests", b.interest_id, "area_m2", round(a.area_m2, 1), round(b.area_m2, 1),
                         f"area changed from {a.interest_id}")
            # carry progress of continuing interests over to the new version
            for s in self.steps[self.steps["interest_id"] == a.interest_id].itertuples():
                if s.status in ("done", "in_progress") and a.instrument_code == b.instrument_code:
                    tgt = f"{b.interest_id}:{s.seq}"
                    self.steps.loc[self.steps["step_id"] == tgt, ["status", "date", "note"]] = [s.status, s.date, "carried over from " + a.interest_id]
                    self.log(new_version, "steps", tgt, "status", "not_started", s.status, "carried over from the base version")
            if a.instrument_code == b.instrument_code:
                idx = self.interests.index[self.interests["interest_id"] == a.interest_id][0]
                self.interests.loc[idx, ["status", "updated"]] = ["superseded", AS_OF]
        return {
            "base_version": base_version, "new_version": new_version,
            "out_of_scope": [{"lot_key": k[0], "interest_type": k[1]} for k in out_keys],
            "new_in_scope": [{"lot_key": k[0], "interest_type": k[1]} for k in in_keys],
            "changed": changed, "steps_to_review": review,
        }

    # -- validation ----------------------------------------------------------------------------------
    def validate(self) -> dict[str, list[str]]:
        v: dict[str, list[str]] = {r[0]: [] for r in VALIDATION_RULES}
        for name, df, k in [("parcels", self.parcels, "lot_key"), ("interests", self.interests, "interest_id"),
                            ("steps", self.steps, "step_id"), ("documents", self.documents, "doc_id"),
                            ("affected_areas", self.affected, "area_id"), ("alignment_versions", self.versions, "version_id")]:
            if len(df) and df[k].duplicated().any():
                v["V01"] += [f"{name}:{x}" for x in df.loc[df[k].duplicated(), k]]
        lots = set(self.parcels["lot_key"])
        vers = set(self.versions["version_id"])
        for name, df in [("interests", self.interests), ("affected_areas", self.affected)]:
            if len(df):
                v["V02"] += [f"{name}:{x}" for x in df.loc[~df["lot_key"].isin(lots), "lot_key"]]
                v["V03"] += [f"{name}:{x}" for x in df.loc[~df["version_id"].isin(vers), "version_id"]]
        parea = self.parcels.set_index("lot_key")["lot_area_m2"]
        live = self.interests[self.interests["status"] != "withdrawn"] if len(self.interests) else self.interests
        for r in self.interests.itertuples():
            pa = parea.get(r.lot_key)
            if pa is not None and (r.area_m2 <= 0 or (r.interest_type != "zone" and r.area_m2 > pa + 0.01)):
                v["V04"].append(r.interest_id)
        if len(live):
            surf = live[live["interest_type"].isin(["permanent_surface", "temporary_surface"])]
            for (ver, lot), g in surf.groupby(["version_id", "lot_key"]):
                if g["area_m2"].sum() > parea.get(lot, float("inf")) + 0.01:
                    v["V05"].append(f"{ver}:{lot}")
        max_years = float(config.fact_value("F10"))
        state = self.parcels.set_index("lot_key")["state_land_indicated"].astype(bool)
        for r in self.interests.itertuples():
            if r.instrument_code in ("TEMP-OCC", "TOL"):
                if not r.start_date or not r.end_date:
                    v["V06"].append(f"{r.interest_id}: no dates")
                else:
                    years = (date.fromisoformat(r.end_date) - date.fromisoformat(r.start_date)).days / 365.25
                    limit = max_years if r.instrument_code == "TEMP-OCC" else 10.0
                    if years > limit or years < 0:
                        v["V06"].append(f"{r.interest_id}: {years:.2f} years")
            if r.instrument_code == "TOL" and not state.get(r.lot_key, False):
                v["V07"].append(r.interest_id)
            if r.instrument_code == "TEMP-OCC" and state.get(r.lot_key, False):
                v["V07"].append(r.interest_id)
            if r.interest_type == "permanent_subterranean":
                if r.stratum_top_m_shd is None or r.stratum_bottom_m_shd is None or not r.stratum_top_m_shd > r.stratum_bottom_m_shd:
                    v["V08"].append(r.interest_id)
        if len(self.steps):
            st = self.steps.merge(self.interests[["interest_id", "status"]].rename(columns={"status": "interest_status"}),
                                  on="interest_id", how="left")
            for iid, g in st.groupby("interest_id"):
                g = g.sort_values("seq")
                seen_open = False
                for s in g.itertuples():
                    if s.mandatory and s.status == "done" and seen_open:
                        v["V09"].append(s.step_id)
                    if s.mandatory and s.status not in ("done", "not_applicable"):
                        seen_open = True
                    if s.interest_status == "withdrawn" and s.status == "in_progress":
                        v["V09"].append(s.step_id)
        if len(self.documents):
            iids = set(self.interests["interest_id"])
            for d in self.documents.itertuples():
                if (d.interest_id is not None and d.interest_id not in iids) or (d.lot_key is not None and d.lot_key not in lots):
                    v["V10"].append(d.doc_id)
        for name, g in [("parcels", self.parcels), ("affected_areas", self.affected)]:
            if len(g):
                bad = (~g.geometry.is_valid) | g.geometry.is_empty
                v["V11"] += [f"{name}:{i}" for i in g.index[bad]]
                if g.crs is None or g.crs.to_epsg() != 3414:
                    v["V11"].append(f"{name}: CRS is not EPSG:3414")
        if len(self.affected) and len(self.interests):
            sums = self.affected.groupby(["version_id", "lot_key", "take"])["area_m2"].sum()
            for r in self.interests[self.interests["interest_type"] != "zone"].itertuples():
                s = sums.get((r.version_id, r.lot_key, r.interest_type), 0.0)
                if abs(s - r.area_m2) > 0.01:
                    v["V12"].append(r.interest_id)
        return v

    # -- persistence ---------------------------------------------------------------------------------
    def write(self, path: Path) -> None:
        """Spatial layers through GDAL; attribute tables with explicit types, keys and foreign keys."""
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.exists():
            path.unlink()
        self.parcels.to_file(path, layer="parcels", driver="GPKG")
        self.affected.to_file(path, layer="affected_areas", driver="GPKG")
        meta = pd.DataFrame([
            {"key": "schema_version", "value": SCHEMA_VERSION},
            {"key": "crs", "value": config.SVY21},
            {"key": "as_of", "value": AS_OF},
            {"key": "disclaimer", "value": "ILLUSTRATIVE fictional corridor; statuses, dates and documents are SYNTHETIC; not legal advice"},
        ])
        tables = {"alignment_versions": self.versions, "interests": self.interests, "steps": self.steps,
                  "documents": self.documents, "change_log": pd.DataFrame(self.changes, columns=[c[0] for c in SCHEMA["change_log"]["columns"]]),
                  "validation_rules": pd.DataFrame(VALIDATION_RULES, columns=["rule_id", "description", "severity"]),
                  "metadata": meta}
        con = sqlite3.connect(path)
        try:
            con.execute("PRAGMA foreign_keys = ON")
            con.execute("CREATE UNIQUE INDEX parcels_lot_key ON parcels(lot_key)")
            con.execute("CREATE UNIQUE INDEX affected_areas_area_id ON affected_areas(area_id)")
            for name, df in tables.items():
                spec = SCHEMA[name]
                cols = spec["columns"]
                defs = ["fid INTEGER PRIMARY KEY AUTOINCREMENT"] + [f'"{c}" {t}' for c, t, _ in cols] + spec.get("constraints", [])
                con.execute(f'CREATE TABLE "{name}" ({", ".join(defs)})')
                names = [c for c, _, _ in cols]
                rows = [tuple(None if (isinstance(v, float) and v != v) else v for v in r)
                        for r in (df[names].astype(object).where(df[names].notna(), None).itertuples(index=False, name=None)
                                  if len(df) else [])]
                con.executemany(f'INSERT INTO "{name}" ({", ".join(chr(34) + n + chr(34) for n in names)}) '
                                f'VALUES ({", ".join("?" for _ in names)})', rows)
                con.execute("INSERT INTO gpkg_contents (table_name, data_type, identifier, description, last_change) "
                            "VALUES (?, 'attributes', ?, ?, ?)", (name, name, spec["description"], AS_OF + "T00:00:00.000Z"))
            con.commit()
            bad = con.execute("PRAGMA foreign_key_check").fetchall()
            if bad:
                raise ValueError(f"foreign key violations: {bad[:5]}")
        finally:
            con.close()

    @staticmethod
    def read_table(path: Path, name: str) -> pd.DataFrame:
        con = sqlite3.connect(path)
        try:
            return pd.read_sql_query(f'SELECT * FROM "{name}"', con)
        finally:
            con.close()
