"""Build dashboard/OHCHR_voting_dashboard.html — the single-file offline/e-mail copy.

index.html loads world.js and data.js with <script src>, which a file:// recipient
cannot rely on once the page is detached from its folder. This inlines both, so the
one file is self-contained.

Previously this was a manual copy step described in the audit notes, which is why the
single-file build drifted behind index.html. Run it after any rebuild:

    python scripts/build_dashboard_data.py && python scripts/build_single_file.py

The Texts and Language tabs fetch their shards over HTTP and stay inert here by
design; both already show an offline notice.
"""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DASH = ROOT / "dashboard"
OUT = DASH / "OHCHR_voting_dashboard.html"

html = (DASH / "index.html").read_text(encoding="utf-8")

for name in ("world.js", "data.js"):
    tag = f'<script src="{name}"></script>'
    if tag not in html:
        raise SystemExit(f"expected {tag} in index.html — inline step needs updating")
    payload = (DASH / name).read_text(encoding="utf-8").rstrip()
    # </script> inside a string literal would close the tag early
    payload = payload.replace("</script", "<\\/script")
    html = html.replace(tag, "<script>\n" + payload + "\n</script>")

assert "<script src=" not in html, "an external script survived inlining"
OUT.write_text(html, encoding="utf-8")
print(f"{OUT.relative_to(ROOT)}: {OUT.stat().st_size/1024/1024:.1f} MB (self-contained)")
