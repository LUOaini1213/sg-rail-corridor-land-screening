"""Reader outputs: workbook totals against Python, DXF read-back, web map content, two-page briefing."""
import json

import ezdxf
import pytest
from openpyxl import load_workbook
from pypdf import PdfReader

from corridor import config, screening
from corridor.outputs import briefing, dxf_export, schedule_xlsx, webmap

TAKE_COLS = {"D": "permanent_surface_m2", "E": "permanent_subterranean_m2", "F": "temporary_surface_m2"}


@pytest.fixture(scope="module")
def run():
    study = screening.load_study()
    full, summary, attrs = screening.run(study)
    return study, full, summary, attrs


def check_workbook(path, summary, info):
    wb = load_workbook(path)          # formulas come back as text: the test sums the cells itself
    for k, s in summary.items():
        ws = wb[f"Schedule {k}"]
        meta = info["schedules"][k]
        first, last, tot = meta["first_row"], meta["last_row"], meta["total_row"]
        for col, key in TAKE_COLS.items():
            cells = [ws[f"{col}{r}"].value or 0.0 for r in range(first, last + 1)]
            assert sum(cells) == pytest.approx(s["totals"][key], abs=0.01 * len(cells)), (k, key)
            assert ws[f"{col}{tot}"].value == f"=SUM({col}{first}:{col}{last})"
        keys = [ws[f"A{r}"].value for r in range(first, last + 1)]
        assert len(keys) == len(set(keys)) and ws[f"A{tot}"].value == "Total"
        in_scope = sum(1 for r in range(first, last + 1) if any((ws[f"{c}{r}"].value or 0) > 0 for c in TAKE_COLS))
        assert in_scope == s["totals"]["lots_in_scope"], k
        assert "fictional" in ws["A2"].value
    assert "fictional" in wb["Read me"]["A2"].value


def test_workbook_written_now_matches_python(run, tmp_path):
    _, full, summary, attrs = run
    info = schedule_xlsx.make(full, summary, attrs, tmp_path / "s.xlsx")
    check_workbook(tmp_path / "s.xlsx", summary, info)


def test_committed_workbook_matches_the_committed_results():
    summary = json.loads((config.RESULTS / "screening.json").read_text(encoding="utf-8"))["variants"]
    info = json.loads((config.RESULTS / "outputs.json").read_text(encoding="utf-8"))["schedule_xlsx"]
    check_workbook(config.OUTPUTS / "land_schedule.xlsx", summary, info)


def test_dxf_reads_back_with_the_alignment_vertices(run, tmp_path):
    study, full, _, _ = run
    info = dxf_export.make(full, study, tmp_path / "c.dxf")
    assert info["audit_errors"] == 0 and info["opened_in_cad_software"] is False
    doc = ezdxf.readfile(tmp_path / "c.dxf")
    assert doc.header["$INSUNITS"] == 6
    msp = doc.modelspace()
    for k, r in full.items():
        lines = [e for e in msp.query("LWPOLYLINE") if e.dxf.layer == dxf_export.layer_name(k, "ALIGNMENT")]
        assert len(lines) == 1
        pts = [(p[0], p[1]) for p in lines[0].get_points()]
        ref = list(r["alignment"].line.coords)
        assert len(pts) == len(ref)
        assert max(abs(a[0] - b[0]) + abs(a[1] - b[1]) for a, b in zip(pts, ref)) < 1e-6
        boxes = [e for e in msp.query("LWPOLYLINE") if e.dxf.layer == dxf_export.layer_name(k, "BOX")]
        assert len(boxes) == 2 and all(e.closed for e in boxes)
    texts = {e.dxf.text for e in msp.query("TEXT") if e.dxf.layer == "LOT_KEYS"}
    in_scope = set().union(*[set(r["schedule"].loc[r["schedule"]["in_scope"], "LOT_KEY"]) for r in full.values()])
    assert texts == in_scope
    notes = " ".join(e.dxf.text for e in msp.query("TEXT") if e.dxf.layer == "NOTES")
    assert "ILLUSTRATIVE" in notes and "not opened in AutoCAD" in notes


def test_web_map_has_the_layers_and_the_banner(run, tmp_path):
    study, full, summary, attrs = run
    p = tmp_path / "m.html"
    info = webmap.make(full, summary, attrs, study, p)
    html = p.read_text(encoding="utf-8")
    assert "fictional corridor, not a planned line" in html and "not legal advice" in html
    assert "OpenStreetMap" in html and "onemap" not in html.lower()
    names = webmap.layer_names(p)
    for k in full:
        assert any(n.startswith(f"Variant {k}:") for n in names), names
    for k in full:
        assert info["layers"][k]["lots"] == summary[k]["totals"]["lots_in_scope"]


def test_briefing_note_is_two_pages_and_carries_the_disclaimer(tmp_path):
    info = briefing.make(tmp_path / "b.pdf")
    assert info["pages"] == 2
    text = " ".join(pg.extract_text() for pg in PdfReader(tmp_path / "b.pdf").pages)
    assert "fictional" in text and "not legal advice" in text


def test_committed_outputs_exist_and_are_recorded():
    info = json.loads((config.RESULTS / "outputs.json").read_text(encoding="utf-8"))
    for key in ("schedule_xlsx", "dxf", "webmap", "briefing"):
        assert (config.ROOT / info[key]["path"]).exists(), key
    assert info["briefing"]["pages"] == 2
    for f in info["figures"].values():
        assert (config.ROOT / f["path"]).exists()
