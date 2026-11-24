"""Land schedule workbook (openpyxl): one sheet per variant with a totals row (SUM formulas), a summary,
a read-me and the sources."""
from __future__ import annotations

from pathlib import Path

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

from .. import config
from . import rel
from .figures import BANNER

COLUMNS = [  # (header, schedule column, number format)
    ("Lot key (SLA)", "LOT_KEY", None),
    ("Master Plan 2025 zone (largest share)", "land_use", None),
    ("Tenure evidence (open data)", "tenure_evidence", None),
    ("Permanent surface take (m2)", "permanent_surface_m2", "#,##0.0"),
    ("Tunnel stratum (m2)", "permanent_subterranean_m2", "#,##0.0"),
    ("Temporary occupation (m2)", "temporary_surface_m2", "#,##0.0"),
    ("Within 6 m of structure (m2)", "first_reserve_m2", "#,##0.0"),
    ("6 to 40 m from structure (m2)", "protection_zone_m2", "#,##0.0"),
    ("40 to 60 m from structure (m2)", "safety_zone_m2", "#,##0.0"),
    ("Buildings in surface take", "buildings_in_surface_take", "0"),
    ("Mechanisms (codes, see Read me)", "instruments", None),
    ("Agencies", "agencies", None),
]
SUM_COLS = [c for c in COLUMNS if c[2] is not None]
HEADER_ROW = 4
BOLD = Font(bold=True)
HEAD_FILL = PatternFill("solid", fgColor="E1E0D9")


def _sheet(ws, title_lines):
    for i, t in enumerate(title_lines, start=1):
        ws.cell(row=i, column=1, value=t).font = Font(bold=(i == 1))


def make(full, summary, attrs, path: Path) -> dict:
    wb = Workbook()
    rd = wb.active
    rd.title = "Read me"
    lines = [
        "Land schedule: fictional corridor IL-1 (ILLUSTRATIVE)",
        BANNER + ".",
        "Personal portfolio desk study on public data, built with AI assistance. Not affiliated with or endorsed by LTA, SLA or URA. Not legal advice.",
        "Lots: SLA Cadastral Land Parcel (data.gov.sg); lot lines are approximate. Zones: URA Master Plan 2025 (as amended). Areas are plan areas in SVY21.",
        "Tenure evidence: only SLA's open layers of vacant State land, State land managed by agents and State reserves indicate State land; 'Unknown' means not shown there.",
        "Mechanism codes: ACQ-SURFACE = acquisition under s.5 Land Acquisition Act if not State land; ACQ-STRATUM = subterranean stratum only, s.5(1A);",
        "TEMP-OCC = temporary occupation under s.42 if not State land (TOL if it is); TOL = Temporary Occupation Licence; STATE-SURFACE / STATE-STRATUM = shown as State land;",
        "RAIL-ZONE = within the 40 m railway corridor / protection distances (LTA controls). Facts and sources: docs/fact_sheet.md.",
        "Money is not shown: there is no public unit rate for compensation (see README).",
    ]
    _sheet(rd, lines)
    rd.column_dimensions["A"].width = 160
    sm = wb.create_sheet("Summary")
    sm.append(["Summary by variant (plan areas, square metres)"])
    sm["A1"].font = BOLD
    head = ["Variant", "Label", "Length (m)", "Lots with an interest", "Permanent surface (m2)", "Tunnel stratum (m2)",
            "Temporary (m2)", "Lots within 40 m", "Buildings in surface take", "Buildings above tunnels"]
    sm.append([])
    sm.append(head)
    for c in sm[3]:
        c.font, c.fill = BOLD, HEAD_FILL
    for k, s in summary.items():
        t = s["totals"]
        sm.append([k, s["label"], round(s["length_m"], 1), t["lots_in_scope"], round(t["permanent_surface_m2"], 1),
                   round(t["permanent_subterranean_m2"], 1), round(t["temporary_surface_m2"], 1),
                   s["zones"]["within_protection_distance_lots"], s["buildings"]["in_surface_take"], s["buildings"]["above_tunnels"]])
    for i in range(1, len(head) + 1):
        sm.column_dimensions[get_column_letter(i)].width = 18 if i > 2 else (10 if i == 1 else 34)
    written = {}
    for k, r in full.items():
        ws = wb.create_sheet(f"Schedule {k}")
        _sheet(ws, [f"Variant {k}: {summary[k]['label']}", BANNER + "."])
        for j, (h, _, _) in enumerate(COLUMNS, start=1):
            c = ws.cell(row=HEADER_ROW, column=j, value=h)
            c.font, c.fill = BOLD, HEAD_FILL
            c.alignment = Alignment(wrap_text=True, vertical="top")
        rows = r["schedule"].sort_values(["in_scope", "LOT_KEY"], ascending=[False, True])
        first = HEADER_ROW + 1
        for i, row in enumerate(rows.itertuples(index=False), start=first):
            d = row._asdict()
            for j, (_, col, fmt) in enumerate(COLUMNS, start=1):
                v = d[col]
                v = round(float(v), 2) if fmt and fmt != "0" else (int(v) if fmt == "0" else v)
                c = ws.cell(row=i, column=j, value=v)
                if fmt:
                    c.number_format = fmt
        last = first + len(rows) - 1
        tot = last + 1
        ws.cell(row=tot, column=1, value="Total").font = BOLD
        for j, (_, col, fmt) in enumerate(COLUMNS, start=1):
            # no total for buildings: one building can stand on two lots, so the column does not add up
            if fmt and col != "buildings_in_surface_take":
                L = get_column_letter(j)
                c = ws.cell(row=tot, column=j, value=f"=SUM({L}{first}:{L}{last})")
                c.font, c.number_format = BOLD, fmt
        ws.freeze_panes = ws.cell(row=first, column=2)
        ws.auto_filter.ref = f"A{HEADER_ROW}:{get_column_letter(len(COLUMNS))}{last}"
        for j in range(1, len(COLUMNS) + 1):
            ws.column_dimensions[get_column_letter(j)].width = 16 if j > 3 else 24
        ws.column_dimensions[get_column_letter(len(COLUMNS) - 1)].width = 44
        written[k] = {"rows": int(len(rows)), "first_row": first, "last_row": last, "total_row": tot}
    so = wb.create_sheet("Sources")
    so.append(["Source", "Licence or status"])
    for a, b in [("Datasets: see docs/data_sources.md (data.gov.sg, OpenStreetMap)", "SODL v1.0; ODbL 1.0"),
                 ("Legal and regulatory facts: docs/fact_sheet.md", "VERIFIED / UNVERIFIED per row"),
                 ("Corridor geometry: inputs/corridor.yaml", "ILLUSTRATIVE (fictional)")]:
        so.append([a, b])
    so.column_dimensions["A"].width = 70
    so.column_dimensions["B"].width = 36
    wb.properties.creator = "sg-rail-corridor-land-screening"
    wb.properties.title = "Fictional corridor IL-1 land schedule"
    wb.save(path)
    return {"path": rel(path), "sheets": wb.sheetnames, "schedules": written}
