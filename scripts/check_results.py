"""Rebuild everything from the committed extract and compare with what is committed.

Usage: python scripts/check_results.py
JSON and CSV results are compared number by number with a small tolerance (floating-point results can differ
in the last digits between platforms); the generated Markdown documents must match exactly. Binary outputs
(GeoPackage, workbook, PDF, PNG) carry timestamps and are only checked to exist. Exit status 1 on a mismatch.
"""
from __future__ import annotations

import csv
import io
import json
import math
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REL, ABS = 1e-7, 1e-4


def close(a, b, path="") -> list[str]:
    if isinstance(a, dict) and isinstance(b, dict):
        if set(a) != set(b):
            return [f"{path}: keys differ {sorted(set(a) ^ set(b))[:5]}"]
        return [m for k in a for m in close(a[k], b[k], f"{path}.{k}")]
    if isinstance(a, list) and isinstance(b, list):
        if len(a) != len(b):
            return [f"{path}: length {len(a)} != {len(b)}"]
        return [m for i, (x, y) in enumerate(zip(a, b)) for m in close(x, y, f"{path}[{i}]")]
    if isinstance(a, bool) or isinstance(b, bool) or not isinstance(a, (int, float)) or not isinstance(b, (int, float)):
        return [] if a == b else [f"{path}: {a!r} != {b!r}"]
    return [] if math.isclose(a, b, rel_tol=REL, abs_tol=ABS) else [f"{path}: {a} != {b}"]


def committed(rel: str) -> str:
    return subprocess.run(["git", "show", f"HEAD:{rel}"], cwd=ROOT, capture_output=True, text=True,
                          encoding="utf-8", check=True).stdout


def csv_rows(text: str) -> list[list]:
    out = []
    for row in csv.reader(io.StringIO(text)):
        conv = []
        for v in row:
            try:
                conv.append(float(v))
            except ValueError:
                conv.append(v)
        out.append(conv)
    return out


def main() -> int:
    for cmd in ([sys.executable, "-m", "corridor.pipeline"], [sys.executable, "scripts/build_docs.py"]):
        subprocess.run(cmd, cwd=ROOT, check=True)
    problems = []
    for p in sorted((ROOT / "results").glob("*.json")):
        rel = p.relative_to(ROOT).as_posix()
        if p.name in ("mutation.json", "raw_survey.json", "verification.json", "quote_check.json"):
            continue                      # written by other scripts, not by the pipeline
        problems += close(json.loads(p.read_text(encoding="utf-8")), json.loads(committed(rel)), rel)
    problems += close(csv_rows((ROOT / "results" / "schedule.csv").read_text(encoding="utf-8")),
                      csv_rows(committed("results/schedule.csv")), "results/schedule.csv")
    docs = ["README.md", "docs/fact_sheet.md", "docs/data_sources.md", "docs/schema.md", "docs/briefing_note.md"]
    docs += [p.relative_to(ROOT).as_posix() for p in sorted((ROOT / "results" / "tables").glob("*.md"))]
    for rel in docs:
        if (ROOT / rel).read_text(encoding="utf-8") != committed(rel):
            problems.append(f"{rel}: differs from the committed version")
    for rel in ("outputs/land_db.gpkg", "outputs/land_schedule.xlsx", "outputs/briefing_note.pdf",
                "outputs/webmap.html", "outputs/corridor_variants.dxf"):
        if not (ROOT / rel).exists():
            problems.append(f"{rel}: missing")
    for m in problems[:50]:
        print(m)
    print("results match the committed versions" if not problems else f"{len(problems)} differences")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
