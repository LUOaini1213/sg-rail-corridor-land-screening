"""Check that every VERIFIED quote in inputs/facts.yaml appears in its source (needs network).

Each source with a URL is downloaded once (Singapore Statutes Online is skipped: it refused automated access),
its text extracted (PDF with pypdf, HTML with the standard-library parser), and each quote is searched for
after removing whitespace and folding quotes and case, because PDF text extraction drops or adds spaces.
The SHA-256 of what was downloaded is compared with the one recorded in facts.yaml (a changed page is
reported, not treated as a failure). Copies are kept in data/raw/sources/ (git-ignored), never committed.
Writes results/quote_check.json.

Usage: python scripts/check_quotes.py
"""
from __future__ import annotations

import hashlib
import io
import json
import sys
import time
import urllib.request
from html.parser import HTMLParser
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from corridor import config  # noqa: E402

USER_AGENT = "sg-rail-corridor-land-screening/0.1 (portfolio desk study)"
SKIP_HOSTS = ("sso.agc.gov.sg",)


class _Text(HTMLParser):
    def __init__(self):
        super().__init__()
        self.parts, self.skip = [], 0

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style", "noscript"):
            self.skip += 1

    def handle_endtag(self, tag):
        if tag in ("script", "style", "noscript") and self.skip:
            self.skip -= 1

    def handle_data(self, data):
        if not self.skip:
            self.parts.append(data)


def text_of(body: bytes, url: str) -> str:
    if body[:4] == b"%PDF":
        from pypdf import PdfReader
        return " ".join((p.extract_text() or "") for p in PdfReader(io.BytesIO(body)).pages)
    p = _Text()
    p.feed(body.decode("utf-8", errors="replace"))
    return " ".join(p.parts)


def norm(s: str) -> str:
    s = s.replace("’", "'").replace("‘", "'").replace("“", '"').replace("”", '"').replace("—", "-")
    return "".join(s.split()).lower()


def main() -> int:
    f = config.facts()
    cache = config.RAW / "sources"
    cache.mkdir(parents=True, exist_ok=True)
    texts, report = {}, {"sources": {}, "facts": {}}
    for sid, s in f["sources"].items():
        url = s["url"]
        if any(h in url for h in SKIP_HOSTS) or not any(r["source"] == sid and r["status"] == "VERIFIED" for r in f["facts"]):
            continue
        req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
        try:
            with urllib.request.urlopen(req, timeout=120) as r:
                body = r.read()
        except Exception as e:  # noqa: BLE001
            report["sources"][sid] = {"error": str(e)}
            continue
        (cache / f"{sid}.bin").write_bytes(body)
        sha = hashlib.sha256(body).hexdigest()
        report["sources"][sid] = {"bytes": len(body), "sha256_matches_recorded": sha == s.get("sha256")}
        texts[sid] = norm(text_of(body, url))
        time.sleep(3)
    for r in f["facts"]:
        if r["status"] != "VERIFIED":
            continue
        t = texts.get(r["source"])
        report["facts"][r["id"]] = None if t is None else (norm(r["quote"]) in t)
    found = sum(1 for v in report["facts"].values() if v)
    checked = sum(1 for v in report["facts"].values() if v is not None)
    report["summary"] = {"verified_rows": sum(r["status"] == "VERIFIED" for r in f["facts"]), "checked": checked, "found": found,
                         "not_found": [k for k, v in report["facts"].items() if v is False]}
    (config.RESULTS / "quote_check.json").write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n")
    print(json.dumps(report["summary"], indent=1))
    return 0 if not report["summary"]["not_found"] else 1


if __name__ == "__main__":
    sys.exit(main())
