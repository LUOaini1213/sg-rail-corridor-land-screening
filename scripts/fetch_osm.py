"""Download OpenStreetMap building footprints for the study area through the Overpass API.

One query, run once. The response, the query and its SHA-256 are recorded in data/manifest.json
under the key "osm_buildings"; the raw response stays in data/raw/osm_buildings/ (git-ignored).
Only the geometry, the OSM id and the value of the `building` tag are carried into the committed
study-area extract: names, addresses and every other tag are dropped.

OpenStreetMap data (c) OpenStreetMap contributors, Open Database Licence (ODbL) 1.0.
Usage: python scripts/fetch_osm.py   (needs network access)
"""
from __future__ import annotations

import hashlib
import json
import sys
import urllib.parse
import urllib.request
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from corridor import config  # noqa: E402

ENDPOINT = "https://overpass-api.de/api/interpreter"
USER_AGENT = "sg-rail-corridor-land-screening/0.1 (portfolio desk study)"
MANIFEST = ROOT / "data" / "manifest.json"


def query_text() -> str:
    s, w, n, e = config.study_area_wgs84_bbox()
    return (f"[out:json][timeout:120];\n"
            f"(way[\"building\"]({s:.6f},{w:.6f},{n:.6f},{e:.6f});\n"
            f" relation[\"building\"]({s:.6f},{w:.6f},{n:.6f},{e:.6f}););\n"
            f"out tags geom;")


def main() -> int:
    q = query_text()
    req = urllib.request.Request(ENDPOINT, data=urllib.parse.urlencode({"data": q}).encode(),
                                 headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=300) as r:
        body = r.read()
    doc = json.loads(body)
    target = ROOT / "data" / "raw" / "osm_buildings" / "osm_buildings.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(body)
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8")) if MANIFEST.exists() else {}
    manifest["osm_buildings"] = {
        "dataset_name": "OpenStreetMap building footprints (ways and relations tagged building=*)",
        "publisher": "OpenStreetMap contributors, via the Overpass API",
        "page": "https://www.openstreetmap.org/copyright",
        "download_api": ENDPOINT,
        "query": q,
        "osm_base": doc.get("osm3s", {}).get("timestamp_osm_base"),
        "licence": "Open Database Licence (ODbL) 1.0",
        "file": "osm_buildings/osm_buildings.json",
        "bytes": len(body),
        "sha256": hashlib.sha256(body).hexdigest(),
        "accessed": datetime.now().astimezone().isoformat(timespec="seconds"),
    }
    MANIFEST.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n")
    print(f"osm_buildings: {len(body):,} bytes, {len(doc.get('elements', []))} elements")
    return 0


if __name__ == "__main__":
    sys.exit(main())
