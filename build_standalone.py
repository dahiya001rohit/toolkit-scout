"""Build toolkit-scout.html — the single-file deliverable.

Takes frontend/index.html and inlines everything a reviewer needs:
  - style.css  -> <style> block
  - app.js     -> <script> block
  - data/results.json + data/verification.json -> window.TS_DATA / TS_VERIF

The result opens from disk with no server and no internet (Google Fonts
degrade to system fonts offline; the live-demo box needs the internet to
reach the Render backend, and says so gracefully when it can't).

Usage:  python build_standalone.py
"""

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent
OUT = ROOT / "toolkit-scout.html"

html = (ROOT / "frontend" / "index.html").read_text()
css = (ROOT / "frontend" / "style.css").read_text()
js = (ROOT / "frontend" / "app.js").read_text()
results = json.loads((ROOT / "data" / "results.json").read_text())
verification = json.loads((ROOT / "data" / "verification.json").read_text())

# 1. stylesheet link -> inline <style>
link_tag = '<link rel="stylesheet" href="style.css">'
assert link_tag in html, "stylesheet link not found"
html = html.replace(link_tag, f"<style>\n{css}\n</style>")

# 2. app.js script tag -> embedded data + inline script
script_tag = '<script src="app.js"></script>'
assert script_tag in html, "app.js script tag not found"
embed = (
    "<script>\n"
    "/* embedded at build time so this file works offline from disk */\n"
    f"window.TS_DATA = {json.dumps(results, separators=(',', ':'))};\n"
    f"window.TS_VERIF = {json.dumps(verification, separators=(',', ':'))};\n"
    "</script>\n"
    f"<script>\n{js}\n</script>"
)
html = html.replace(script_tag, embed)

OUT.write_text(html)
size_kb = OUT.stat().st_size / 1024
print(f"wrote {OUT.name} ({size_kb:.0f} KB, "
      f"{len(results['apps'])} apps + verification embedded)")
