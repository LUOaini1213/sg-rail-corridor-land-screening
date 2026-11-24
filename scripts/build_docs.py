"""Render the generated documents from inputs/ and results/.

Usage: python scripts/build_docs.py [--check]
  --check   do not write; exit 1 if any generated document differs from what is committed
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from corridor import config, docs  # noqa: E402


def documents() -> dict[Path, str]:
    results = docs.load_results()
    out = {config.DOCS / "fact_sheet.md": docs.render_fact_sheet(),
           config.DOCS / "data_sources.md": docs.render_data_sources(results),
           config.DOCS / "schema.md": docs.render_schema(results)}
    from corridor.outputs import briefing
    out[config.DOCS / "briefing_note.md"] = briefing.render_markdown()
    readme_t = config.DOCS / "templates" / "README.md"
    if readme_t.exists():
        out[config.ROOT / "README.md"] = docs.render(readme_t.read_text(encoding="utf-8"), results)
    return out


def main(argv: list[str]) -> int:
    check = "--check" in argv
    stale = []
    for path, text in documents().items():
        if check:
            if not path.exists() or path.read_text(encoding="utf-8") != text:
                stale.append(path.relative_to(config.ROOT).as_posix())
        else:
            if docs.write_if_changed(path, text):
                print("wrote", path.relative_to(config.ROOT).as_posix())
    if stale:
        print("stale:", ", ".join(stale))
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
