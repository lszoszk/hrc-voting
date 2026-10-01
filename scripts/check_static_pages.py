"""Fail if the generated static pages are broken.

    python scripts/check_static_pages.py DIR [--base /hrc-voting]

DIR is the folder the pages were written to; --base is the URL path it is served at
(default /hrc-voting, which is what build_static_pages.py links to).

Run after build_static_pages.py (the Pages workflow does). It checks what a crawler
depends on: every internal link resolves, each page has one h1, a unique title and a
description of snippet length, every JSON-LD block parses, the sitemap lists exactly the
pages on disk, and the page counts have not collapsed.
"""
import collections
import json
import re
import sys
from pathlib import Path

args = sys.argv[1:]
base = "/hrc-voting"
if "--base" in args:
    i = args.index("--base")
    base = "/" + args[i + 1].strip("/")
    del args[i:i + 2]
root = Path(args[0]).resolve()
fails = []
htmls = [p for p in root.rglob("*.html") if p.relative_to(root).parts[0] in ("country", "resolution")]
titles, broken = collections.Counter(), collections.Counter()
for p in htmls:
    t = p.read_text(encoding="utf-8")
    rel = p.relative_to(root)
    if t.count("<h1>") != 1:
        fails.append(f"{rel}: expected one <h1>")
    m = re.search(r"<title>(.*?)</title>", t, re.S)
    titles[m.group(1) if m else ""] += 1
    d = re.search(r'name="description" content="(.*?)"', t)
    if not d or not 60 <= len(d.group(1)) <= 200:
        fails.append(f"{rel}: description missing or not snippet length")
    for blob in re.findall(r'<script type="application/ld\+json">(.*?)</script>', t, re.S):
        try:
            json.loads(blob)
        except ValueError:
            fails.append(f"{rel}: JSON-LD does not parse")
    for h in re.findall(r'href="(' + re.escape(base) + r'/[^"#?]*)"', t):
        if h == base + "/":
            continue                       # the dashboard itself
        tgt = root / h[len(base):].lstrip("/")
        if h.endswith("/"):
            tgt = tgt / "index.html"
        if not tgt.exists():
            broken[h] += 1
dup = [t for t, c in titles.items() if c > 1]
if dup:
    fails.append(f"{len(dup)} duplicate titles, e.g. {dup[0]!r}")
if broken:
    fails.append(f"{len(broken)} broken internal links, e.g. {next(iter(broken))}")
n_c = len(list((root / "country").glob("*/index.html")))
n_r = len(list((root / "resolution").glob("*/index.html")))
if n_c < 140 or n_r < 1200:
    fails.append(f"page counts collapsed: {n_c} countries, {n_r} resolutions")
sm = (root / "sitemap.xml").read_text(encoding="utf-8")
listed = set(re.findall(r"<loc>https://lszoszk\.github\.io" + re.escape(base) + r"/((?:country|resolution)/[^<]*)</loc>", sm))
on_disk = {str(p.relative_to(root).parent).replace("\\", "/") + "/" for p in htmls} | {"country/", "resolution/"}
if listed != on_disk:
    fails.append(f"sitemap and pages differ: {len(listed ^ on_disk)} entries")
if fails:
    print(f"STATIC PAGES: {len(fails)} problem(s)")
    for f in fails[:15]:
        print("  ✗", f)
    sys.exit(1)
print(f"STATIC PAGES: OK — {n_c} countries, {n_r} resolutions, {len(htmls)} pages, {sum(broken.values())} broken links")
