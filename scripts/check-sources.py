#!/usr/bin/env python3
"""
Weekly source checker for the stablecoin tracker.

Fetches each state's primary source URL, extracts text, and compares
a SHA-256 hash against the stored baseline in data/source-hashes.json.

To cut noise (timestamps, bill-status counters, rotating "related links"),
a hash difference is only reported as a CHANGE when the extracted-text
length also moves by a meaningful amount (see MIN_DELTA / PCT_DELTA). Below
that threshold the change is treated as trivial: it is logged but not
flagged, and the stored baseline is kept so slow drift still accumulates
until it crosses the threshold.

Exit codes:
  0  all sources unchanged / only trivial drift (or first-run baseline)
  1  one or more sources changed meaningfully -> triggers GitHub Issue
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

# A hash change only counts as a real change when the extracted-text length
# also moves by at least MIN_DELTA characters OR PCT_DELTA of the baseline,
# whichever is larger. This filters out trivial page churn.
MIN_DELTA = 250
PCT_DELTA = 0.03


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
        new_len   = len(text)
        stored    = hashes.get(slug, {})
        old_hash  = stored.get("hash")
        fresh     = {"url": url, "hash": new_hash, "len": new_len, "lastChecked": today}

        if old_hash is None:
            print(f"  -> baseline recorded ({new_hash[:12]}..., {new_len} chars)")
            first_runs.append(name)
            hashes[slug] = fresh
        elif old_hash == new_hash:
            print(f"  -> unchanged ({new_hash[:12]}...)")
            hashes[slug] = fresh
        elif "len" not in stored:
            # legacy entry with no length baseline: record length now, don't flag
            print(f"  -> re-baselined (legacy entry; recorded {new_len} chars)")
            hashes[slug] = fresh
        else:
            delta     = abs(new_len - stored["len"])
            threshold = max(MIN_DELTA, int(PCT_DELTA * stored["len"]))
            if delta >= threshold:
                print(f"  -> CHANGED  was={old_hash[:12]} now={new_hash[:12]}  "
                      f"len {stored['len']}->{new_len} (delta {delta} >= {threshold})")
                changed.append({"name": name, "slug": slug, "url": url})
                hashes[slug] = fresh  # reset baseline to the new content
            else:
                print(f"  -> trivial drift  len {stored['len']}->{new_len} "
                      f"(delta {delta} < {threshold}); baseline kept")
                # keep old hash/len so slow drift accumulates; refresh lastChecked only
                stored["lastChecked"] = today
                hashes[slug] = stored

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
