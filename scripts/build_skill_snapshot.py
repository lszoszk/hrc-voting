"""Refresh the data snapshot bundled inside the Claude skill.

    python scripts/build_skill_snapshot.py

The skill in skills/hrc-voting/ has to work where there is no network (a Claude.ai
sandbox, a train), so it carries a gzipped copy of the four CSVs it reads, a small
countries table and meta.json (version, snapshot date, DOI, counts). Run this after a
re-harvest and before a release; scripts/check_figures.py fails if the snapshot's
version or counts fall behind CITATION.cff and the build.
"""
import csv
import gzip
import json
import re
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "skills" / "hrc-voting" / "assets" / "data"
FILES = ["resolutions.csv", "votes_long.csv", "ga_resolutions.csv", "ga_votes_long.csv"]


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    for name in FILES:
        with open(ROOT / "data" / "csv" / name, "rb") as src, gzip.GzipFile(OUT / (name + ".gz"), "wb", compresslevel=9, mtime=0) as dst:
            shutil.copyfileobj(src, dst)
    raw = (ROOT / "dashboard" / "data.js").read_text(encoding="utf-8")
    payload = json.loads(raw[len("window.DATA = "):].rstrip().rstrip(";"))
    groups = payload["meta"]["groupLabels"]
    hist = {"CSK", "DDR", "GER", "SCG", "SUN", "YMD", "YUG"}
    with open(OUT / "countries.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["iso3", "name", "group", "historical"])
        for c in sorted(payload["countries"], key=lambda c: c["iso3"]):
            w.writerow([c["iso3"], c["name"], groups.get(c["group"], ""), int(c["iso3"] in hist)])
    cff = (ROOT / "CITATION.cff").read_text(encoding="utf-8")
    stats = json.loads((ROOT / "huggingface" / "hrc-voting" / "dataset_stats.json").read_text())
    meta = {
        "version": re.search(r'^version:\s*"([^"]+)"', cff, re.M).group(1),
        "snapshot_date": re.search(r'^date-released:\s*"([^"]+)"', cff, re.M).group(1),
        "doi_concept": "10.5281/zenodo.21281232",
        "records": stats["resolutions"],
        "country_votes": stats["votes"],
        "recorded_records": stats["with_rollcall"],
        "amendments": stats["amendments"],
        "ga_resolutions": stats["ga"]["resolutions"],
        "ga_votes": stats["ga"]["votes"],
    }
    (OUT / "meta.json").write_text(json.dumps(meta, indent=1) + "\n", encoding="utf-8")
    size = sum(p.stat().st_size for p in OUT.iterdir())
    print(f"snapshot v{meta['version']} ({meta['snapshot_date']}): {len(list(OUT.iterdir()))} files, {size/1e6:.2f} MB")


if __name__ == "__main__":
    main()
