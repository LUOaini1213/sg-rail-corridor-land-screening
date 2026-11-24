"""Repository-wide checks: generated documents are current, numbers come from results, red lines hold."""
import json
import re
import subprocess
import sys
from pathlib import Path

import pytest

from corridor import config, docs

sys.path.insert(0, str(config.ROOT / "scripts"))
import build_docs  # noqa: E402

TEMPLATES = ["README.md", "data_sources.md", "schema.md", "briefing_note.md"]
FUTURE_LINE_NAMES = ["Seletar", "Tengah Line", "Cross Island", "Jurong Region", "West Coast Extension", "Punggol Extension"]


def tracked_files() -> list[Path]:
    try:
        out = subprocess.run(["git", "ls-files"], cwd=config.ROOT, capture_output=True, text=True, check=True).stdout
        return [config.ROOT / p for p in out.splitlines()]
    except (OSError, subprocess.CalledProcessError):      # not a git checkout: fall back to a walk
        skip = {".venv", ".git", "raw", "__pycache__", ".pytest_cache"}
        return [p for p in config.ROOT.rglob("*") if p.is_file() and not skip & set(p.parts)]


TEXT_SUFFIXES = {".md", ".py", ".yaml", ".yml", ".json", ".csv", ".txt", ".toml", ".html", ".cfg", ".ini", ".gitignore"}


def text_files():
    return [p for p in tracked_files() if p.suffix in TEXT_SUFFIXES or p.name in (".gitignore", ".gitattributes", "LICENSE")]


@pytest.mark.golden
def test_generated_documents_are_up_to_date():
    stale = [p.name for p, text in build_docs.documents().items() if not p.exists() or p.read_text(encoding="utf-8") != text]
    assert stale == [], f"run python scripts/build_docs.py: {stale}"


@pytest.mark.parametrize("name", TEMPLATES)
def test_templates_contain_no_typed_numbers(name):
    tmpl = (config.DOCS / "templates" / name).read_text(encoding="utf-8")
    assert docs.typed_numbers(tmpl) == []


def test_typed_number_check_catches_a_number():
    assert docs.typed_numbers("A box of 150 m and {{x.y:.0f}} lots") == ["150"]


def test_readme_opens_with_the_required_note():
    head = (config.ROOT / "README.md").read_text(encoding="utf-8")[:1500]
    assert head.startswith("# sg-rail-corridor-land-screening\n\n> **Read this first.**")
    for phrase in ("Personal portfolio project on public data", "built with AI assistance", "not affiliated with",
                   "non-public information", "**fictional**", "**not legal advice**",
                   "Author: Wenjie Luo (GitHub LUOaini1213)"):
        assert phrase in head, phrase


def test_licence_names_the_author():
    assert "Copyright (c) 2026 Wenjie Luo (LUOaini1213)" in (config.ROOT / "LICENSE").read_text(encoding="utf-8")


PRIVATE = {
    "email": re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.(?:com|sg|org|net|edu|gov)\b"),
    "phone": re.compile(r"(?:\+65[\s-]?)?\b[689]\d{3}[\s-]?\d{4}\b"),
    "local path": re.compile(r"(?i)(?:[a-z]:\\\\?users\\\\?|/users/|/home/|appdata)"),
    "secret": re.compile(r"(?i)(?:api[_-]?key|access[_-]?token|secret|password|bearer)\s*[:=]\s*\S+"),
    "signed url": re.compile(r"(?i)x-amz-(?:signature|credential)"),
}
ALLOWED_PHONE_LIKE = re.compile(r"(?:sha256|[0-9a-f]{12,}|d_[0-9a-f]+|OBJECTID|\d{4}-\d\d-\d\d|\d+\.\d+)")


def test_no_private_data_in_tracked_text():
    found = []
    for p in text_files():
        if p.name == "test_repo.py":
            continue
        text = p.read_text(encoding="utf-8", errors="replace")
        for kind, pat in PRIVATE.items():
            for m in pat.finditer(text):
                s = m.group(0)
                if kind == "phone":
                    ctx = text[max(0, m.start() - 40): m.end() + 40]
                    if ALLOWED_PHONE_LIKE.search(ctx) or re.search(r"[A-Z]{2}\d\d-\d", ctx):
                        continue
                found.append((p.relative_to(config.ROOT).as_posix(), kind, s))
    assert found == []


def test_no_future_line_names_in_readers_material():
    paths = [config.ROOT / "README.md", config.DOCS / "briefing_note.md", config.DOCS / "fact_sheet.md",
             config.DOCS / "data_sources.md", config.OUTPUTS / "webmap.html", config.ROOT / "inputs" / "corridor.yaml"]
    for p in paths:
        text = p.read_text(encoding="utf-8")
        for n in FUTURE_LINE_NAMES:
            assert n not in text, (p.name, n)


def test_no_claim_that_cad_or_gis_packages_were_used():
    for p in [config.ROOT / "README.md", config.DOCS / "data_sources.md", config.DOCS / "briefing_note.md", config.DOCS / "schema.md"]:
        for line in p.read_text(encoding="utf-8").splitlines():
            if re.search(r"AutoCAD|MicroStation|QGIS|ArcGIS", line):
                assert re.search(r"\bnot\b|\bno\b|\bNo\b", line), (p.name, line)


def test_repository_is_under_30_mb():
    total = sum(p.stat().st_size for p in tracked_files() if p.exists())
    assert total < 30 * 1024 * 1024


def test_extract_hashes_match_the_manifest():
    man = json.loads((config.DATA / "manifest.json").read_text(encoding="utf-8"))
    meta = json.loads((config.DATA / "study_area" / "study_area.meta.json").read_text(encoding="utf-8"))
    assert set(meta["sources"]) == set(man)
    for k, v in meta["sources"].items():
        assert v["sha256"] == man[k]["sha256"], k
    for k, v in man.items():
        assert "Signature" not in json.dumps(v) and v["licence"]


def test_recorded_test_count_matches_the_suite(request):
    rec = json.loads((config.RESULTS / "verification.json").read_text(encoding="utf-8"))["tests"]
    files = {item.fspath.basename for item in request.session.items}
    full_run = files >= {p.name for p in (config.ROOT / "tests").glob("test_*.py")} and not request.config.getoption("keyword") \
        and not request.config.getoption("markexpr") and not request.config.getoption("deselect")
    if not full_run:
        pytest.skip("partial run")
    assert len(request.session.items) == rec, "run python scripts/count_tests.py"
