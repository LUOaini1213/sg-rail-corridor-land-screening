"""Record how many tests the suite has (results/verification.json), for the README.

Usage: python scripts/count_tests.py
tests/test_repo.py checks the recorded number against the collected tests whenever the whole suite runs.
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def count() -> int:
    out = subprocess.run([sys.executable, "-m", "pytest", "--collect-only", "-q", "-p", "no:cacheprovider"],
                         cwd=ROOT, capture_output=True, text=True).stdout
    m = re.search(r"(\d+) tests? collected", out)
    if not m:
        raise RuntimeError(out[-2000:])
    return int(m.group(1))


if __name__ == "__main__":
    n = count()
    (ROOT / "results" / "verification.json").write_text(json.dumps({"tests": n}, indent=2) + "\n", encoding="utf-8",
                                                        newline="\n")
    print(n, "tests")
