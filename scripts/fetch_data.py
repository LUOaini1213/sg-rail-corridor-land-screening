"""Download the open datasets this study uses into data/raw/ (git-ignored).

Every dataset is published on data.gov.sg under the Singapore Open Data Licence v1.0.
Each download lands in its own directory, data/raw/<key>/, and is recorded in
data/manifest.json with the dataset page, the download API used, the access time, the
file size, its SHA-256 and the dataset's own lastUpdatedAt. The pre-signed file URL that
the download API hands out is NOT recorded: it carries a temporary signature.

Usage: python scripts/fetch_data.py [--only KEY ...] [--raw-dir DIR]
Needs network access. Requests are spaced out and retried with back-off on HTTP 429/5xx.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from corridor.sources import DATASETS  # noqa: E402

USER_AGENT = "sg-rail-corridor-land-screening/0.1 (portfolio desk study)"
DGS_META = "https://api-production.data.gov.sg/v2/public/api/datasets/{id}/metadata"
DGS_INIT = "https://api-open.data.gov.sg/v1/public/api/datasets/{id}/initiate-download"
DGS_POLL = "https://api-open.data.gov.sg/v1/public/api/datasets/{id}/poll-download"
MANIFEST = ROOT / "data" / "manifest.json"


def get(url: str, timeout: float = 300.0, attempts: int = 6) -> bytes:
    for attempt in range(1, attempts + 1):
        req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return r.read()
        except urllib.error.HTTPError as e:
            if (e.code != 429 and e.code < 500) or attempt == attempts:
                raise
            wait = 20.0 * attempt
            print(f"  HTTP {e.code}; retrying in {wait:.0f}s", flush=True)
            time.sleep(wait)
    raise RuntimeError("unreachable")


def signed_file_url(dataset_id: str) -> str:
    data = json.loads(get(DGS_INIT.format(id=dataset_id)))["data"]
    if data.get("url"):
        return data["url"]
    for _ in range(30):
        time.sleep(4)
        data = json.loads(get(DGS_POLL.format(id=dataset_id)))["data"]
        if data.get("status") == "DOWNLOAD_SUCCESS" and data.get("url"):
            return data["url"]
    raise RuntimeError(f"{dataset_id}: download not ready after polling")


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", nargs="*", default=None)
    ap.add_argument("--raw-dir", type=Path, default=ROOT / "data" / "raw")
    args = ap.parse_args(argv)
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8")) if MANIFEST.exists() else {}
    for key, spec in DATASETS.items():
        if args.only and key not in args.only:
            continue
        meta = json.loads(get(DGS_META.format(id=spec["id"])))["data"]
        body = get(signed_file_url(spec["id"]))
        target = args.raw_dir / key / spec["file"]
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(body)
        manifest[key] = {
            "dataset_id": spec["id"],
            "dataset_name": meta.get("name"),
            "publisher": meta.get("managedBy"),
            "dataset_last_updated": meta.get("lastUpdatedAt"),
            "page": f"https://data.gov.sg/datasets/{spec['id']}/view",
            "download_api": DGS_INIT.format(id=spec["id"]),
            "licence": "Singapore Open Data Licence v1.0",
            "file": f"{key}/{spec['file']}",
            "bytes": len(body),
            "sha256": hashlib.sha256(body).hexdigest(),
            "accessed": datetime.now().astimezone().isoformat(timespec="seconds"),
        }
        MANIFEST.parent.mkdir(parents=True, exist_ok=True)
        MANIFEST.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n")
        print(f"{key}: {len(body):,} bytes", flush=True)
        time.sleep(10)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
