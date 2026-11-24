"""Markdown tables written to results/tables/ by the pipeline and quoted by the README and briefing note."""
from __future__ import annotations

from . import config


def _n(x, nd=0):
    return f"{x:,.{nd}f}"


def variant_summary(summary: dict) -> str:
    ks = list(summary)
    rows = [
        ("Route length (m)", lambda s: _n(s["length_m"])),
        ("Curves (radius 300 m)", lambda s: str(s["curves"])),
        ("Lots with a land interest", lambda s: str(s["totals"]["lots_in_scope"])),
        ("- of which shown as State land in SLA's open layers", lambda s: str(s["totals"]["lots_state_land_indicated_in_scope"])),
        ("Permanent surface take, station boxes (m2)", lambda s: _n(s["totals"]["permanent_surface_m2"])),
        ("Tunnel stratum (m2)", lambda s: _n(s["totals"]["permanent_subterranean_m2"])),
        ("- under lots not shown as State land (m2)", lambda s: _n(s["totals"]["subterranean_not_state_m2"])),
        ("Temporary occupation, worksites (m2)", lambda s: _n(s["totals"]["temporary_surface_m2"])),
        ("Buildings inside boxes or worksites (OSM)", lambda s: str(s["buildings"]["in_surface_take"])),
        ("Buildings above the tunnels (OSM)", lambda s: str(s["buildings"]["above_tunnels"])),
        ("- of which URA-listed HDB blocks", lambda s: str(s["buildings"]["mp_hdb_above_tunnels"])),
        ("Lots within 40 m of the structure (any part)", lambda s: str(s["zones"]["within_protection_distance_lots"])),
        ("Other lots 40 to 60 m from the structure", lambda s: str(s["zones"]["safety_zone"]["lots_outside_footprint"])),
    ]
    head = "| | " + " | ".join(f"{k}: {summary[k]['label']}" for k in ks) + " |"
    out = [head, "|---|" + "---|" * len(ks)]
    for label, f in rows:
        out.append(f"| {label} | " + " | ".join(f(summary[k]) for k in ks) + " |")
    return "\n".join(out)


def land_use_by_take(summary: dict) -> str:
    ks = list(summary)
    uses = sorted({u for k in ks for u in summary[k]["by_land_use_m2"]})
    takes = [("permanent_surface", "surface"), ("permanent_subterranean", "stratum"), ("temporary_surface", "temporary")]
    head = "| Master Plan zone | " + " | ".join(f"{k} {t}" for k in ks for _, t in takes) + " |"
    out = [head, "|---|" + "---|" * (len(ks) * len(takes))]
    for u in uses:
        cells = []
        for k in ks:
            d = summary[k]["by_land_use_m2"].get(u, {})
            cells += [_n(d.get(t, 0.0)) if d.get(t, 0.0) else "-" for t, _ in takes]
        out.append(f"| {u.capitalize()} | " + " | ".join(cells) + " |")
    return "\n".join(out)


def instruments(summary: dict) -> str:
    ks = list(summary)
    codes = sorted({c for k in ks for c in summary[k]["instruments_lots"]})
    out = ["| Mechanism code | " + " | ".join(ks) + " |", "|---|" + "---|" * len(ks)]
    for c in codes:
        out.append(f"| `{c}` | " + " | ".join(str(summary[k]["instruments_lots"].get(c, 0)) for k in ks) + " |")
    return "\n".join(out)


def tenure(summary: dict) -> str:
    ks = list(summary)
    labels = sorted({t for k in ks for t in summary[k]["tenure_evidence_lots"]})
    out = ["| Tenure evidence (lots with an interest) | " + " | ".join(ks) + " |", "|---|" + "---|" * len(ks)]
    for t in labels:
        out.append(f"| {t} | " + " | ".join(str(summary[k]["tenure_evidence_lots"].get(t, 0)) for k in ks) + " |")
    return "\n".join(out)


def interfaces(summary: dict) -> str:
    names = {"first_reserve": "within 6 m", "protection_zone": "6 to 40 m", "safety_zone": "40 to 60 m", "outside": "beyond 60 m"}
    out = ["| Component | Distance to the indicative line (m) | Distance to the station outline (m) | Band |", "|---|---|---|---|"]
    for k in summary:
        for r in summary[k]["existing_railway_interfaces"]:
            out.append(f"| {r['component_id']} | {_n(r['distance_to_rail_line_m'], 1)} | {_n(r['distance_to_station_outline_m'], 1)} | "
                       f"{names[r['existing_railway_zone']]} |")
    return "\n".join(out)


def mca(cmp: dict, summary: dict) -> str:
    ks = list(summary)
    out = ["| Criterion (lower is better) | Weight | " + " | ".join(ks) + " |", "|---|---|" + "---|" * len(ks)]
    for c in cmp["criteria"]:
        nd = 0
        cells = [f"{_n(cmp['raw'][k][c['key']], nd)} ({cmp['scores'][k][c['key']]:.2f})" for k in ks]
        out.append(f"| {c['label']} | {c['weight']:.2f} | " + " | ".join(cells) + " |")
    out.append("| **Weighted score** | 1.00 | " + " | ".join(f"**{cmp['total'][k]:.2f}**" for k in ks) + " |")
    return "\n".join(out)


def sensitivity(cmp: dict) -> str:
    ks = list(cmp["total"])
    rows = [("Author's weights", cmp["ranking"]), ("Equal weights", cmp["equal_weights"]["ranking"]),
            (f"Values within {100 * cmp['ties_within_tolerance']['tolerance']:.0f}% of the best treated as ties",
             cmp["ties_within_tolerance"]["ranking"])]
    out = ["| Weighting | Ranking |", "|---|---|"]
    out += [f"| {a} | {' > '.join(b)} |" for a, b in rows]
    out.append(f"| Each weight x0.5 or x1.5 in turn ({cmp['one_at_a_time_runs']} runs) | same winner in "
               f"{cmp['one_at_a_time_same_winner']} of {cmp['one_at_a_time_runs']} |")
    out.append(f"| Each criterion left out in turn ({len(cmp['leave_one_out'])} runs) | same winner in "
               f"{cmp['leave_one_out_same_winner']} of {len(cmp['leave_one_out'])} |")
    shares = ", ".join(f"{k} {100 * cmp['random_weights_first_share'][k]:.1f}%" for k in ks)
    out.append(f"| {cmp['random_weights_n']:,} random weightings: share ranked first | {shares} |")
    return "\n".join(out)


def write_all(summary: dict, cmp: dict) -> dict:
    d = config.RESULTS / "tables"
    d.mkdir(parents=True, exist_ok=True)
    tables = {"variant_summary": variant_summary(summary), "land_use_by_take": land_use_by_take(summary),
              "instruments": instruments(summary), "tenure": tenure(summary), "interfaces": interfaces(summary),
              "mca": mca(cmp, summary), "sensitivity": sensitivity(cmp)}
    for k, v in tables.items():
        (d / f"{k}.md").write_text(v + "\n", encoding="utf-8", newline="\n")
    return tables
