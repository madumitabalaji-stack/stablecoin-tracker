#!/usr/bin/env python3
"""
Weekly source checker for the stablecoin tracker.

Fetches each state's primary source URL, extracts text, and compares
a SHA-256 hash against the stored baseline in data/source-hashes.json.

Exit codes:
  0  all sources unchanged (or first-run baseline recorded)
  1  one or more previously-hashed sources changed -> triggers GitHub Issue
  2  dependency or config error
"""

import hashlib
import io
import json
import re
import sys
from datetime import date
from pathlib import Path

try:
    import requests
    from bs4 import BeautifulSoup
    import pypdf
except ImportError as e:
    print(f"Missing dependency: {e}\nRun: pip install requests beautifulsoup4 pypdf")
    sys.exit(2)

ROOT = Path(__file__).parent.parent
STATES_FILE  = ROOT / "data" / "states.json"
HASHES_FILE  = ROOT / "data" / "source-hashes.json"
REPORT_FILE  = ROOT / "change-report.json"

HEADERS = {"User-Agent": "StablecoinTracker/1.0 (+https://github.com)"}
TIMEOUT = 30


def fetch_text(url: str) -> str | None:
    try:
        resp = requests.get(url, headers=HEADERS, timeout=TIMEOUT, allow_redirects=True)
        resp.raise_for_status()
    except Exception as e:
        print(f"  SKIP  could not fetch: {e}")
        return None

    content_type = resp.headers.get("content-type", "")

    if "pdf" in content_type or url.lower().split("?")[0].endswith(".pdf"):
        try:
            reader = pypdf.PdfReader(io.BytesIO(resp.content))
            text = "\n".join(page.extract_text() or "" for page in reader.pages)
        except Exception as e:
            print(f"  SKIP  PDF parse error: {e}")
            return None
    else:
        soup = BeautifulSoup(resp.text, "html.parser")
        for tag in soup(["script", "style", "nav", "header", "footer"]):
            tag.decompose()
        text = soup.get_text(separator=" ")

    return re.sub(r"\s+", " ", text).strip()


def sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def main():
    if not STATES_FILE.exists():
        print(f"ERROR: {STATES_FILE} not found")
        sys.exit(2)

    states_data = json.loads(STATES_FILE.read_text())
    hashes = json.loads(HASHES_FILE.read_text()) if HASHES_FILE.exists() else {}

    today = date.today().isoformat()
    changed = []
    first_runs = []

    for state in states_data["states"]:
        slug = state["slug"]
        url  = state["sourceUrl"]
        name = state["name"]

        print(f"\n[{name}]")
        print(f"  URL: {url}")

        text = fetch_text(url)
        if text is None:
            print("  -> skipped (fetch error)")
            continue

        new_hash  = sha256(text)
        stored    = hashes.get(slug, {})
        old_hash  = stored.get("hash")

        if old_hash is None:
            print(f"  -> baseline recorded ({new_hash[:12]}...)")
            first_runs.append(name)
        elif old_hash != new_hash:
            print(f"  -> CHANGED  was={old_hash[:12]}  now={new_hash[:12]}")
            changed.append({"name": name, "slug": slug, "url": url})
        else:
            print(f"  -> unchanged ({new_hash[:12]}...)")

        hashes[slug] = {"url": url, "hash": new_hash, "lastChecked": today}

    # Always write updated hashes (captures lastChecked and any new baselines)
    HASHES_FILE.write_text(json.dumps(hashes, indent=2) + "\n")
    print(f"\n{'='*60}")

    if first_runs:
        print(f"Baselines recorded for: {', '.join(first_runs)}")

    if changed:
        print(f"\nCHANGES DETECTED ({len(changed)} source(s)):")
        for c in changed:
            print(f"  * {c['name']}: {c['url']}")
        REPORT_FILE.write_text(json.dumps({"date": today, "changed": changed}, indent=2) + "\n")
        sys.exit(1)
    else:
        print("All checked sources unchanged.")
        if REPORT_FILE.exists():
            REPORT_FILE.unlink()
        sys.exit(0)


if __name__ == "__main__":
    main()
