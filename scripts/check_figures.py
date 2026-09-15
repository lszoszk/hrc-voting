"""Fail if a figure, version or title stated in prose has drifted from the build.

    python scripts/check_figures.py

Numbers that live in two places drift. This project has watched it happen four
times: the UNITAR vocabulary size (103/56 quoted against 77/49 implemented), the
citation version, Methodology 13's config table (five configs quoted against ten
shipped) and the README's coverage figures, which went on describing a two-organ
corpus after the Assembly landed.

Methodology 13 was fixed by deriving it — it reads dashboard/hf_stats.js at runtime.
README.md cannot do that; it is markdown, read as-is. So it gets the other half of
the pattern: the figures stay hand-written, and this asserts they still match what
the pipeline actually produced. Run it after any rebuild, before pushing.

Sources of truth:
  huggingface/hrc-voting/dataset_stats.json   row counts, written by prepare_hf_dataset.py
  dashboard/data.js                            coverage totals, written by build_dashboard_data.py
  CITATION.cff                                 version and title
"""
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def load():
    stats = json.loads((ROOT / "huggingface" / "hrc-voting" / "dataset_stats.json").read_text())
    raw = (ROOT / "dashboard" / "data.js").read_text(encoding="utf-8")
    payload = json.loads(raw[len("window.DATA = "):].rstrip().rstrip(";"))
    hf_raw = (ROOT / "dashboard" / "hf_stats.js").read_text(encoding="utf-8")
    hf = json.loads(hf_raw[len("window.HF_STATS = "):].rstrip().rstrip(";"))
    return stats, payload, hf


def main():
    stats, payload, hf = load()
    cov = payload["meta"]["coverage"]
    ga = stats.get("ga", {})
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    fails = []

    def want(label, value, text=None, where="README.md"):
        """The formatted value must appear verbatim in `text`."""
        s = f"{value:,}" if isinstance(value, int) else str(value)
        if s not in (text if text is not None else readme):
            fails.append(f"{where}: {label} should read {s} — not found")

    # --- coverage figures, in the order the README states them ---
    want("total records across three organs", cov["totalResolutions"])
    want("CHR/HRC catalogue", len(payload["resAll"]))
    want("CHR/HRC with a roll-call",
         sum(1 for r in payload["res"] if r["body"] in ("CHR", "HRC")))
    want("CHR/HRC per-country votes", stats["votes"])
    want("records with a per-country breakdown", cov["recordedResolutions"])
    want("GA resolutions", ga.get("resolutions"))
    want("GA plenary votes", ga.get("votes"))
    want("GA committee votes", ga.get("committee_votes"))
    want("harvested text corpus", stats["clause_docs"] + ga.get("clause_docs", 0))

    # --- the Hugging Face package: config count, stated in two prose spots ---
    n = len(hf["configs"])
    n_ga = sum(1 for c in hf["configs"] if c["name"].startswith("ga_"))
    if f"{n} parquet configs ({n - n_ga} CHR/HRC + {n_ga} GA)" not in readme:
        fails.append(f"README.md: layout should say "
                     f"'{n} parquet configs ({n - n_ga} CHR/HRC + {n_ga} GA)'")
    if not re.search(rf"\b{n}\b configs", readme.replace("Ten", "10")) \
            and f"{n} configs" not in readme.lower().replace("ten configs", "10 configs"):
        fails.append(f"README.md: the Hugging Face section should say {n} configs")

    # --- version and title, which must agree across five files ---
    cff = (ROOT / "CITATION.cff").read_text(encoding="utf-8")
    version = re.search(r'^version:\s*"([^"]+)"', cff, re.M).group(1)
    title = re.search(r'^title:\s*"([^"]+)"', cff, re.M).group(1)
    index = (ROOT / "dashboard" / "index.html").read_text(encoding="utf-8")
    # Extract each file's own title and compare for EQUALITY. A substring test looks
    # equivalent and is not: a title that loses its tail ("… — CHR · HRC") is still a
    # prefix of the full one, so `in` waves it through — which is how the Assembly
    # dropped out of CITATION.cff unnoticed in the first place.
    titles = {
        ".zenodo.json": (r'"title":\s*"([^"]+)"', (ROOT / ".zenodo.json")),
        "codemeta.json": (r'"name":\s*"([^"]+)"', (ROOT / "codemeta.json")),
        "huggingface/hrc-voting/CITATION.cff":
            (r'^title:\s*"([^"]+)"', ROOT / "huggingface" / "hrc-voting" / "CITATION.cff"),
        "dashboard/index.html": (r"<title>([^<]+)</title>", ROOT / "dashboard" / "index.html"),
        "README.md": (r"^# (.+)$", ROOT / "README.md"),
    }
    for path, (pattern, f) in titles.items():
        text = f.read_text(encoding="utf-8")
        m = re.search(pattern, text, re.M)
        if not m:
            fails.append(f"{path}: no title found (pattern {pattern!r})")
        elif m.group(1).strip() != title:
            fails.append(f"{path}: title is {m.group(1).strip()!r}, "
                         f"CITATION.cff says {title!r}")
        if version not in text:
            fails.append(f"{path}: version should be {version} (from CITATION.cff)")

    # CITE_ACADEMIC is stamped on every export and shown by the footer's Cite button
    cite = re.search(r"const CITE_ACADEMIC='([^']+)'", index)
    if not cite:
        fails.append("dashboard/index.html: CITE_ACADEMIC not found")
    elif title not in cite.group(1) or f"v{version}" not in cite.group(1):
        fails.append(f"dashboard/index.html: CITE_ACADEMIC should carry {title!r} and v{version}")

    if fails:
        print(f"FIGURES: {len(fails)} drifted\n")
        for f in fails:
            print("  ✗", f)
        print("\nRebuild first (build_dashboard_data.py, prepare_hf_dataset.py), then "
              "update the prose to match.")
        sys.exit(1)
    print(f"FIGURES: OK — coverage, {n} configs, title and v{version} agree "
          "across README, metadata and the dashboard")


if __name__ == "__main__":
    main()
