"""Cut the study-area extract out of the raw downloads (needs data/raw/, see scripts/fetch_data.py).

Usage: python scripts/build_study_area.py
Writes data/study_area/study_area.gpkg and data/study_area/study_area.meta.json (both committed).
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from corridor import study_area  # noqa: E402

if __name__ == "__main__":
    counts = study_area.build()
    for k, v in counts.items():
        print(f"{k}: {v}")
