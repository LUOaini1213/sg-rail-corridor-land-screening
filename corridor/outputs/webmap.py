"""Interactive map (Leaflet through folium). Opens in a browser; the base map tiles and the Leaflet library
load from the internet. Colour encodes the take type, as in the figures."""
from __future__ import annotations

import html
import json
from pathlib import Path

import folium
import geopandas as gpd

from .. import config
from . import rel
from .figures import BANNER, INK, INK2, MUTED, TAKE_COLOURS, TAKE_LABELS


def _wgs(g: gpd.GeoDataFrame, tol: float = 0.0) -> gpd.GeoDataFrame:
    g = g.copy()
    if tol:
        g["geometry"] = g.geometry.simplify(tol, preserve_topology=True)
    return g.to_crs(config.WGS84)


def make(full, summary, attrs, study, path: Path) -> dict:
    lots = study["lots"]
    centre = gpd.GeoSeries([lots.geometry.union_all().centroid], crs=config.SVY21).to_crs(config.WGS84).iloc[0]
    m = folium.Map(location=[centre.y, centre.x], zoom_start=16, tiles="OpenStreetMap", control_scale=True)
    lu = study["land_use"][["LU_DESC", "geometry"]]
    folium.GeoJson(_wgs(lu, 0.2).to_json(), name="Master Plan 2025 land use (hover for the zone)", show=False,
                   style_function=lambda f: {"color": MUTED, "weight": 0.5, "fillOpacity": 0.05},
                   tooltip=folium.GeoJsonTooltip(fields=["LU_DESC"], aliases=["Zone"])).add_to(m)
    rail = study["rail_lines"][["GRND_LEVEL", "geometry"]]
    folium.GeoJson(_wgs(rail).to_json(), name="Existing railway (indicative)",
                   style_function=lambda f: {"color": INK2, "weight": 2}).add_to(m)
    st = study["rail_stations"][["NAME", "GRND_LEVEL", "geometry"]]
    folium.GeoJson(_wgs(st).to_json(), name="Existing stations",
                   style_function=lambda f: {"color": INK, "weight": 1, "fillColor": "#e8e7e1", "fillOpacity": 0.7},
                   tooltip=folium.GeoJsonTooltip(fields=["NAME", "GRND_LEVEL"], aliases=["Station", "Level"])).add_to(m)
    counts = {}
    for k, r in full.items():
        grp = folium.FeatureGroup(name=f"Variant {k}: {summary[k]['label']}", show=(k == "A"))
        sched = r["schedule"].copy()
        inscope = sched[sched["in_scope"]].copy()
        lot_g = lots.merge(inscope, on="LOT_KEY")
        cols = ["LOT_KEY", "land_use", "tenure_evidence", "permanent_surface_m2", "permanent_subterranean_m2",
                "temporary_surface_m2", "instruments"]
        lot_g = lot_g[cols + ["geometry"]].copy()
        for c in ("permanent_surface_m2", "permanent_subterranean_m2", "temporary_surface_m2"):
            lot_g[c] = lot_g[c].round(0)
        folium.GeoJson(_wgs(lot_g, 0.2).to_json(),
                       style_function=lambda f: {"color": INK2, "weight": 1, "fillOpacity": 0.0},
                       popup=folium.GeoJsonPopup(fields=cols, aliases=["Lot key", "Master Plan zone", "Tenure evidence",
                                                                       "Permanent surface (m2)", "Tunnel stratum (m2)",
                                                                       "Temporary (m2)", "Mechanisms"])).add_to(grp)
        pcs = r["pieces"][["component_id", "take", "LOT_KEY", "area_m2", "geometry"]].copy()
        pcs["area_m2"] = pcs["area_m2"].round(0)
        pcs["take_label"] = pcs["take"].map(TAKE_LABELS)
        folium.GeoJson(_wgs(pcs).to_json(),
                       style_function=lambda f: {"color": "#fcfcfb", "weight": 0.8,
                                                 "fillColor": TAKE_COLOURS[f["properties"]["take"]], "fillOpacity": 0.75},
                       tooltip=folium.GeoJsonTooltip(fields=["component_id", "take_label", "LOT_KEY", "area_m2"],
                                                     aliases=["Component", "Take", "Lot", "Area (m2)"])).add_to(grp)
        line = gpd.GeoDataFrame({"variant": [k]}, geometry=[r["alignment"].line], crs=config.SVY21)
        folium.GeoJson(_wgs(line).to_json(), style_function=lambda f: {"color": INK, "weight": 2}).add_to(grp)
        rings = gpd.GeoDataFrame({"distance": ["6 m", "40 m", "60 m"]},
                                 geometry=[r["structure"].buffer(d, quad_segs=16).exterior for d in (6, 40, 60)], crs=config.SVY21)
        folium.GeoJson(_wgs(rings).to_json(), style_function=lambda f: {"color": MUTED, "weight": 1, "dashArray": "4 3"},
                       tooltip=folium.GeoJsonTooltip(fields=["distance"], aliases=["From the structure"])).add_to(grp)
        grp.add_to(m)
        counts[k] = {"lots": int(len(lot_g)), "pieces": int(len(pcs))}
    folium.LayerControl(collapsed=False).add_to(m)
    legend = "".join(f'<div><span style="display:inline-block;width:12px;height:12px;background:{c};margin-right:6px"></span>'
                     f"{html.escape(TAKE_LABELS[t])}</div>" for t, c in TAKE_COLOURS.items())
    banner = (f'<div style="position:fixed;top:10px;left:50px;z-index:9999;max-width:520px;background:#fcfcfb;'
              f'border:1px solid #c3c2b7;padding:8px 10px;font:12px system-ui,-apple-system,Segoe UI,sans-serif;color:{INK}">'
              f"<b>{html.escape(BANNER)}.</b><br>Personal portfolio desk study on public data, built with AI assistance; "
              f"not affiliated with or endorsed by LTA, SLA or URA; not legal advice. Lot lines are approximate "
              f"(SLA open cadastral layer). Data: URA, SLA, LTA via data.gov.sg (Singapore Open Data Licence v1.0); "
              f"buildings and base map (c) OpenStreetMap contributors.{legend}</div>")
    m.get_root().html.add_child(folium.Element(banner))
    m.get_root().header.add_child(folium.Element("<title>Fictional corridor IL-1: land screening map</title>"))
    m.save(str(path))
    text = path.read_text(encoding="utf-8")
    path.write_text(text, encoding="utf-8", newline="\n")
    return {"path": rel(path), "layers": counts,
            "geojson_layers": text.count("L.geoJson(")}


def layer_names(path: Path) -> list[str]:
    """Names shown in the layer control (read back for the tests)."""
    text = Path(path).read_text(encoding="utf-8")
    start = text.find("var layer_control_")
    seg = text[start:start + 20000]
    names = []
    for part in seg.split('"')[1::2]:
        if part.startswith("Variant ") or part in ("Existing railway (indicative)", "Existing stations") or part.startswith("Master Plan 2025"):
            names.append(part)
    return names
