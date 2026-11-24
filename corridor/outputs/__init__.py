"""Reader outputs: figures, interactive map, Excel land schedule, DXF, briefing note."""
from __future__ import annotations

import json
from pathlib import Path

from .. import config


def rel(path) -> str:
    """Path relative to the repository when inside it (as recorded in results/), else as given."""
    try:
        return Path(path).resolve().relative_to(config.ROOT.resolve()).as_posix()
    except ValueError:
        return Path(path).as_posix()


def run_all(full, summary, cmp, attrs, study, check) -> dict:
    from . import briefing, dxf_export, figures, schedule_xlsx, webmap
    out_dir = config.OUTPUTS
    out_dir.mkdir(parents=True, exist_ok=True)
    fig_dir = config.ROOT / "figures"
    fig_dir.mkdir(parents=True, exist_ok=True)
    res = {}
    res["figures"] = figures.make_all(full, summary, cmp, study, fig_dir)
    res["webmap"] = webmap.make(full, summary, attrs, study, out_dir / "webmap.html")
    res["schedule_xlsx"] = schedule_xlsx.make(full, summary, attrs, out_dir / "land_schedule.xlsx")
    res["dxf"] = dxf_export.make(full, study, out_dir / "corridor_variants.dxf")
    from ..pipeline import write_json
    write_json("outputs", res)
    # the briefing note quotes results/*.json, so it is rendered after they are written
    res["briefing"] = briefing.make(out_dir / "briefing_note.pdf")
    write_json("outputs", res)
    return res


def load() -> dict:
    p = config.RESULTS / "outputs.json"
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}
