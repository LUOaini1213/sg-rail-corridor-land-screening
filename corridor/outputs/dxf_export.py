"""DXF export (ezdxf, DXF R2013, metres, SVY21 coordinates). Written and read back with ezdxf only:
the file was not opened in AutoCAD, MicroStation or any other CAD package."""
from __future__ import annotations

from pathlib import Path

import ezdxf
from ezdxf.enums import TextEntityAlignment

from .. import config
from . import rel
from .figures import BANNER

COLOURS = {"ALIGNMENT": 7, "BOX": 5, "TUNNEL": 30, "WORKSITE": 3, "ZONE_06M": 8, "ZONE_40M": 8, "ZONE_60M": 8}


def _rings(geom):
    if geom.geom_type == "Polygon":
        return [geom.exterior]
    return [p.exterior for p in geom.geoms]


def layer_name(variant: str, part: str) -> str:
    return f"IL1_{variant}_{part}"


def make(full, study, path: Path) -> dict:
    doc = ezdxf.new("R2013", setup=True)
    doc.units = ezdxf.units.M
    doc.header["$INSUNITS"] = 6
    msp = doc.modelspace()
    for k, r in full.items():
        for part, colour in COLOURS.items():
            doc.layers.add(layer_name(k, part), color=colour)
        xs, ys = r["alignment"].line.xy
        msp.add_lwpolyline(list(zip(xs, ys)), dxfattribs={"layer": layer_name(k, "ALIGNMENT")})
        for c in r["components"].itertuples():
            part = {"station_box": "BOX", "bored_tunnel": "TUNNEL", "worksite": "WORKSITE"}[c.component_type]
            for ring in _rings(c.geometry):
                msp.add_lwpolyline(list(ring.coords), close=True, dxfattribs={"layer": layer_name(k, part)})
        for d, part in ((6, "ZONE_06M"), (40, "ZONE_40M"), (60, "ZONE_60M")):
            for ring in _rings(r["structure"].buffer(d, quad_segs=16)):
                msp.add_lwpolyline(list(ring.coords), close=True, dxfattribs={"layer": layer_name(k, part)})
    doc.layers.add("LOTS_WITH_INTEREST", color=1)
    doc.layers.add("LOT_KEYS", color=1)
    doc.layers.add("EXISTING_STATIONS", color=8)
    doc.layers.add("NOTES", color=7)
    keys = sorted(set().union(*[set(r["schedule"].loc[r["schedule"]["in_scope"], "LOT_KEY"]) for r in full.values()]))
    lots = study["lots"][study["lots"]["LOT_KEY"].isin(keys)]
    for lot in lots.itertuples():
        for ring in _rings(lot.geometry):
            msp.add_lwpolyline(list(ring.coords), close=True, dxfattribs={"layer": "LOTS_WITH_INTEREST"})
        p = lot.geometry.representative_point()
        msp.add_text(lot.LOT_KEY, height=2.0, dxfattribs={"layer": "LOT_KEYS"}).set_placement(
            (p.x, p.y), align=TextEntityAlignment.MIDDLE_CENTER)
    for s in study["rail_stations"].itertuples():
        for ring in _rings(s.geometry):
            msp.add_lwpolyline(list(ring.coords), close=True, dxfattribs={"layer": "EXISTING_STATIONS"})
    minx, miny, maxx, maxy = lots.total_bounds
    notes = [BANNER + ".", "Personal portfolio desk study; not affiliated with LTA, SLA or URA; not legal advice.",
             "Coordinates: SVY21 / Singapore TM (EPSG:3414), metres. Lot lines: SLA open cadastral layer (approximate).",
             "Written with ezdxf; not opened in AutoCAD, MicroStation or any other CAD package."]
    for i, t in enumerate(notes):
        msp.add_text(t, height=4.0, dxfattribs={"layer": "NOTES"}).set_placement((minx, maxy + 40 - 7 * i))
    doc.saveas(path)
    text = Path(path).read_text(encoding="utf-8", errors="replace")
    Path(path).write_text(text, encoding="utf-8", newline="\n")
    back = ezdxf.readfile(path)
    auditor = back.audit()
    counts = {}
    for e in back.modelspace():
        counts[e.dxf.layer] = counts.get(e.dxf.layer, 0) + 1
    return {"path": rel(path), "entities_by_layer": dict(sorted(counts.items())),
            "audit_errors": len(auditor.errors), "lots_with_interest": len(keys),
            "opened_in_cad_software": False}
