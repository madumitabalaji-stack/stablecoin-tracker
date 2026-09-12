#!/usr/bin/env python3
"""
Rebuild the downloadable dataset PDF (data/state-stablecoin-atlas.pdf) from data/states.json.

The CSV and JSON exports are generated live in the browser, so they are always current.
The PDF is a committed snapshot, so re-run this whenever the data changes:

    python3 scripts/build-dataset-pdf.py

It renders with headless Chrome/Chromium/Edge (whichever is installed). If none is found,
it writes the print-ready HTML next to the PDF and tells you to open it and "Save as PDF".
"""
import json, html, os, sys, subprocess, shutil, tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(ROOT, "data", "states.json")
OUT = os.path.join(ROOT, "data", "state-stablecoin-atlas.pdf")
HTML_FALLBACK = os.path.join(ROOT, "data", "state-stablecoin-atlas.print.html")

STATUS_COLOR = {"live": "#17935a", "pending": "#d68207", "guidance": "#2f6bd6", "excluded": "#7a8394"}

CHROME_CANDIDATES = [
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
    "/Applications/Chromium.app/Contents/MacOS/Chromium",
    "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge",
    "/Applications/Brave Browser.app/Contents/MacOS/Brave Browser",
    "google-chrome", "chromium", "chromium-browser", "microsoft-edge",
]


def build_html():
    d = json.load(open(DATA, encoding="utf-8"))
    states = d.get("states", [])
    last = d.get("lastUpdated", "")
    rows = ""
    for s in sorted(states, key=lambda x: x["name"]):
        c = STATUS_COLOR.get(s.get("status"), "#2f6bd6")
        rows += (
            "<tr>"
            f'<td class="st">{html.escape(s["name"])}</td>'
            f'<td><span class="dot" style="background:{c}"></span>{html.escape(s.get("statusLabel", ""))}</td>'
            f'<td>{html.escape(s.get("regulator", ""))}</td>'
            f'<td class="fw">{html.escape(s.get("framework", ""))}</td>'
            "</tr>"
        )
    return f"""<!DOCTYPE html><html><head><meta charset="utf-8"><style>
@page {{ size: A4; margin: 14mm 12mm; }}
* {{ box-sizing: border-box; }}
body {{ font-family: Arial, Helvetica, sans-serif; color: #10131c; margin: 0; }}
h1 {{ font-family: Georgia, 'Times New Roman', serif; font-size: 22px; margin: 0 0 3px; }}
.eyebrow {{ font-size: 9px; letter-spacing: 2px; text-transform: uppercase; color: #6d4bf6; font-weight: bold; }}
.sub {{ font-size: 10px; color: #4a5163; margin: 4px 0 2px; max-width: 150mm; line-height: 1.4; }}
.meta {{ font-size: 8.5px; color: #8a91a2; margin-bottom: 12px; }}
table {{ width: 100%; border-collapse: collapse; font-size: 8.3px; }}
th {{ text-align: left; text-transform: uppercase; letter-spacing: .4px; font-size: 7.5px; color: #8a91a2; border-bottom: 1.2px solid #10131c; padding: 6px; }}
td {{ vertical-align: top; padding: 6px; border-bottom: .5px solid #e6e8ef; line-height: 1.35; }}
td.st {{ font-weight: bold; white-space: nowrap; }}
td.fw {{ color: #4a5163; }}
.dot {{ display: inline-block; width: 6px; height: 6px; border-radius: 50%; margin-right: 5px; vertical-align: middle; }}
.foot {{ margin-top: 12px; font-size: 8px; color: #8a91a2; line-height: 1.5; }}
</style></head><body>
<div class="eyebrow">State Regulation &middot; Data Export</div>
<h1>State Stablecoin Atlas</h1>
<div class="sub">How U.S. state money-transmission and digital-asset licensing regimes interact with the federal GENIUS Act framework, verified jurisdiction by jurisdiction against primary sources.</div>
<div class="meta">Compiled by Madumita Mira Balaji &middot; statestablecoinatlas.com &middot; Last updated {html.escape(last)}</div>
<table><thead><tr><th style="width:26mm">State</th><th style="width:34mm">Status</th><th style="width:52mm">Regulator</th><th>Framework</th></tr></thead>
<tbody>{rows}</tbody></table>
<div class="foot">Independent research project for informational purposes only; not legal advice. Full analysis, effective dates, and primary-source links at statestablecoinatlas.com. Machine-readable CSV and JSON exports also available on the site.</div>
</body></html>"""


def find_chrome():
    for c in CHROME_CANDIDATES:
        if os.path.isfile(c):
            return c
        found = shutil.which(c)
        if found:
            return found
    return None


def main():
    doc = build_html()
    chrome = find_chrome()
    if not chrome:
        open(HTML_FALLBACK, "w", encoding="utf-8").write(doc)
        print("No Chrome/Chromium/Edge found for PDF rendering.")
        print(f"Wrote print-ready HTML to: {HTML_FALLBACK}")
        print("Open it in a browser and use File > Print > Save as PDF, saving over:")
        print(f"  {OUT}")
        sys.exit(1)

    with tempfile.NamedTemporaryFile("w", suffix=".html", delete=False, encoding="utf-8") as tf:
        tf.write(doc)
        tmp_html = tf.name
    try:
        subprocess.run([
            chrome, "--headless=new", "--disable-gpu", "--no-pdf-header-footer",
            f"--print-to-pdf={OUT}", "file://" + tmp_html,
        ], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        # older Chrome uses --headless (not --headless=new); retry if needed
        if not os.path.isfile(OUT) or os.path.getsize(OUT) == 0:
            subprocess.run([
                chrome, "--headless", "--disable-gpu", "--no-pdf-header-footer",
                f"--print-to-pdf={OUT}", "file://" + tmp_html,
            ], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    finally:
        os.unlink(tmp_html)

    if os.path.isfile(OUT) and os.path.getsize(OUT) > 0:
        kb = os.path.getsize(OUT) / 1024
        print(f"Rebuilt {os.path.relpath(OUT, ROOT)} ({kb:.0f} KB) from {len(json.load(open(DATA))['states'])} jurisdictions.")
    else:
        print("PDF render failed. Try opening the HTML fallback and printing to PDF manually.")
        sys.exit(1)


if __name__ == "__main__":
    main()
