"""Build the Hugging Face package in huggingface/hrc-voting/ from the repo's own outputs.

    python scripts/prepare_hf_dataset.py

Five configs, because the source is relational and flattening it would either explode
the row count or throw away the resolution-level metadata:

  resolutions  one row per catalogued resolution           (data/csv/resolutions.csv)
  votes        one row per (resolution, country) roll-call (data/csv/votes_long.csv)
  clauses      one row per clause of a harvested text      (dashboard/texts/)
  countries    dimension table, 154 states                 (dashboard/data.js)
  subjects     dimension table, OHCHR's controlled vocab   (dashboard/data.js)

The two dimension tables exist so that caveats which are otherwise only prose become
machine-readable: which states no longer exist, which ISO code spans a change of
representation rather than of state, and which subject tags name a country situation
rather than a theme.

Everything here is derived from files already committed to this repository, so the
package can be rebuilt from a clean checkout without re-harvesting.

Derived columns exist mainly to stop downstream users repeating mistakes this project
already made and fixed (see notes/AUDIT-2026-07.md):

  prevailing_side / adopted   Under the chamber's own rules an abstention is not a vote
                              cast, so the outcome turns on Yes vs No alone. Taking
                              max(Yes, No, Abstain) instead — the obvious-looking move —
                              scores the winning Yes bloc as defeated on 53 adopted
                              resolutions in this corpus.
  rollcall_reconciles         ~9% of recorded votes have a per-country roll-call whose
                              tally does not match the official totals. The flag lets a
                              user filter them rather than discover the discrepancy
                              halfway through an analysis.
  clause_type                 Articles of annexed declarations and protocols are marked
                              `annex`, not `operative`. They are treaty-style text, not
                              commitments of the organ, and conflating them shifts every
                              operative-verb statistic.
"""
import csv
import json
import sys
from pathlib import Path

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

sys.path.insert(0, str(Path(__file__).resolve().parent))
from tag_terms import code_clause                      # noqa: E402
from build_dashboard_data import country_subject_matcher  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
CSVD = ROOT / "data" / "csv"
TX = ROOT / "dashboard" / "texts"
OUT = ROOT / "huggingface" / "hrc-voting"
DATA = OUT / "data"

VOTE_LABEL = {
    "Y": "yes", "N": "no", "A": "abstain",
    ".": "absent or not participating",
    "": "not a member at the time / no position recorded",
}
ADOPTION_MODE = {
    "ADOPTED WITHOUT VOTE": "adopted without a vote",
    "RECORDED": "recorded vote",
    "RECORDED, adopted at a closed meeting": "recorded vote (closed meeting)",
    "NON-RECORDED": "non-recorded vote",
    "NON-RECORDED, adopted unanimously": "non-recorded, adopted unanimously",
    "NON-RECORDED, no voting information available": "non-recorded, no voting information",
    "WITHDRAWN": "withdrawn before a decision",
    "NOT CONSIDERED": "not considered",
}


def load_payload():
    raw = (ROOT / "dashboard" / "data.js").read_text(encoding="utf-8")
    return json.loads(raw[len("window.DATA = "):].rstrip().rstrip(";"))


def as_int(v):
    return int(v) if str(v).strip().isdigit() else None


def is_amendment(title, draft):
    import re
    return bool(re.search(r":\s*amendment", title or "", re.I)
                or re.match(r"\s*amendment", draft or "", re.I))


def build_resolutions(res_rows, tally):
    rows = []
    for r in res_rows:
        y, n, a = as_int(r["yes"]), as_int(r["no"]), as_int(r["abstain"])
        nrc = as_int(r["n_rollcall"]) or 0
        # the side that prevailed: Yes vs No only (abstentions are not votes cast)
        prevailing = None if (y is None or n is None) else ("Y" if y > n else "N" if n > y else None)
        t = tally.get(r["record_id"], {})
        reconciles = None
        if nrc and None not in (y, n, a):
            reconciles = (t.get("Y", 0) == y and t.get("N", 0) == n and t.get("A", 0) == a)
        rows.append({
            "record_id": r["record_id"],
            "symbol": r["symbol"],
            "title": r["title"],
            "date": r["date"] or None,
            "year": as_int(r["year"]),
            "body": "HRC" if "Council" in r["body"] else "CHR",
            "vote_type": r["vote_type"],
            "adoption_mode": ADOPTION_MODE.get(r["vote_type"], "other"),
            "is_amendment": is_amendment(r["title"], r.get("draft", "")),
            "subject": r["agenda_subject"].strip() or None,
            "agenda_item_no": r["agenda_item_no"].strip() or None,
            "agenda_item_title": r["agenda_item_title"].strip().rstrip(" -").strip() or None,
            "main_sponsors": r["main_sponsors"].strip() or None,
            "meeting": r["meeting"].strip() or None,
            "yes": y, "no": n, "abstain": a,
            "nonvoting": as_int(r["nonvoting"]), "total": as_int(r["total"]),
            "n_rollcall": nrc,
            "has_rollcall": nrc > 0,
            "prevailing_side": prevailing,
            "adopted": None if prevailing is None else (prevailing == "Y"),
            "rollcall_reconciles": reconciles,
            "url_resolution": r["url_resolution"] or None,
            "url_draft": r["url_draft"] or None,
            "record_url": r["record_url"] or None,
        })
    return pd.DataFrame(rows)


def build_votes(vote_rows, res_df, groups):
    by_id = res_df.set_index("record_id")
    prevail = by_id["prevailing_side"].to_dict()
    subject = by_id["subject"].to_dict()
    amend = by_id["is_amendment"].to_dict()
    rows = []
    for v in vote_rows:
        rid, code = v["record_id"], v["vote"]
        p = prevail.get(rid)
        rows.append({
            "record_id": rid,
            "symbol": v["symbol"],
            "date": v["date"] or None,
            "year": as_int(v["year"]),
            "body": "HRC" if "Council" in v["body"] else "CHR",
            "iso3": v["iso3"] or None,
            "country": v["country"] or None,
            "un_regional_group": groups.get(v["iso3"]) or None,
            "vote": code or None,
            "vote_label": VOTE_LABEL.get(code, "unknown"),
            "is_cast_vote": code in ("Y", "N", "A"),
            "prevailing_side": p,
            # null when the state cast no vote, or the resolution had no Yes/No outcome
            "with_prevailing_side": (code == p) if (p and code in ("Y", "N", "A")) else None,
            "subject": subject.get(rid),
            "is_amendment": bool(amend.get(rid, False)),
        })
    return pd.DataFrame(rows)


def clause_type(label):
    if label.startswith("AX"):
        return "annex"
    if label.startswith("PP"):
        return "preambular"
    if label.startswith("OP"):
        return "operative_subitem" if "(" in label else "operative"
    return "other"


def build_countries(payload, votes_df):
    """Dimension table. Carries the caveats that are otherwise only prose: which states
    no longer exist, and which ISO code spans a change of representation rather than of
    state (the China seat, 1971)."""
    labels = payload["meta"]["groupLabels"]
    first_last = votes_df.groupby("iso3")["year"].agg(["min", "max"])
    rows = []
    for c in payload["countries"]:
        fl = first_last.loc[c["iso3"]] if c["iso3"] in first_last.index else None
        rb = c.get("repBreak") or {}
        rows.append({
            "iso3": c["iso3"],
            "name": c["name"],
            "un_regional_group": labels.get(c["group"]) or None,
            "un_regional_group_code": c["group"] or None,
            "n_rollcall_cells": c["n"],
            "n_yes": c["y"], "n_no": c["no"], "n_abstain": c["a"],
            "n_absent": c["absent"], "n_no_position": c["blank"],
            "first_vote_year": int(fl["min"]) if fl is not None else None,
            "last_vote_year": int(fl["max"]) if fl is not None else None,
            "is_historical_state": bool(c.get("hist")),
            "representation_break_year": rb.get("year"),
            "representation_break_note": rb.get("note"),
        })
    return pd.DataFrame(rows)


def build_subjects(res_df, is_country_subject):
    """OHCHR's own controlled subject vocabulary (MARC 991$d), with the thematic /
    country-situation split the dashboard uses.

    Covers all 1,033 catalogued subjects, not just the 312 that reach a recorded vote —
    the dashboard only needs the latter, but a null classification on a third of the
    resolutions would be a poor dataset. Uses the dashboard's own matcher, so the two
    can never disagree. The split is a name-matching heuristic against catalogued state
    names plus an explicit list of territories: imperfect at the margins."""
    counts_all = res_df.groupby("subject").size()
    counts_rec = res_df[res_df.has_rollcall].groupby("subject").size()
    rows = [{
        "subject": s,
        "is_country_situation": bool(is_country_subject(s)),
        "n_resolutions_recorded": int(counts_rec.get(s, 0)),
        "n_resolutions_all": int(n),
    } for s, n in counts_all.items()]
    return pd.DataFrame(rows).sort_values("n_resolutions_all", ascending=False)


def build_clauses(res_df):
    cat = json.loads((TX / "catalog.json").read_text())["docs"]
    bundles = {int(f.stem.split("-")[1]): json.loads(f.read_text())
               for f in TX.glob("docs-*.json")}
    meta = res_df.set_index("record_id")[["adoption_mode", "prevailing_side", "adopted"]].to_dict("index")
    rows = []
    for sym, rid, year, body, vt, am, subj, title in cat:
        for i, (label, text) in enumerate(bundles.get(year, {}).get(sym, [])):
            ct = clause_type(label)
            verb = dr = val = dg = None
            if ct == "operative":                      # scoring applies to top-level OP only
                verb, dr, val, dg = code_clause(text)
            m = meta.get(rid, {})
            rows.append({
                "record_id": rid,
                "symbol": sym,
                "year": year,
                "body": body,
                "subject": subj or None,
                "title": title,
                "is_amendment": bool(am),
                "adoption_mode": m.get("adoption_mode"),
                "adopted": m.get("adopted"),
                "clause_index": i,
                "clause_label": label,
                "clause_type": ct,
                "text": text,
                "n_chars": len(text),
                "n_words": len(text.split()),
                "operative_verb": verb,
                "directive_force": dr if (ct == "operative" and dr) else None,
                "sentiment": val if ct == "operative" else None,
                "creates_or_tasks_machinery": dg if ct == "operative" else None,
            })
    return pd.DataFrame(rows)


def main():
    DATA.mkdir(parents=True, exist_ok=True)
    res_rows = list(csv.DictReader(open(CSVD / "resolutions.csv", encoding="utf-8")))
    vote_rows = list(csv.DictReader(open(CSVD / "votes_long.csv", encoding="utf-8")))

    tally = {}
    for v in vote_rows:
        tally.setdefault(v["record_id"], {}).setdefault(v["vote"] or "-", 0)
        tally[v["record_id"]][v["vote"] or "-"] += 1

    payload = load_payload()
    groups = {c["iso3"]: payload["meta"]["groupLabels"].get(c["group"], None)
              for c in payload["countries"]}

    res_df = build_resolutions(res_rows, tally)

    # thematic vs country-situation, using the dashboard's own matcher over the raw
    # catalogued spellings so the two can never drift apart
    raw_names = {}
    for v in vote_rows:
        if v["iso3"]:
            raw_names.setdefault(v["iso3"], set()).add(v["country"].strip().upper())
    is_country_subject = country_subject_matcher(raw_names)
    cs = {s: is_country_subject(s) for s in res_df["subject"].dropna().unique()}

    res_df["subject_is_country_situation"] = res_df["subject"].map(cs)
    votes_df = build_votes(vote_rows, res_df, groups)
    clauses_df = build_clauses(res_df)
    clauses_df["subject_is_country_situation"] = clauses_df["subject"].map(cs)
    countries_df = build_countries(payload, votes_df)
    subjects_df = build_subjects(res_df, is_country_subject)

    for name, df in [("resolutions", res_df), ("votes", votes_df), ("clauses", clauses_df),
                     ("countries", countries_df), ("subjects", subjects_df)]:
        path = DATA / f"{name}-train.parquet"
        # pandas 3 writes object columns as arrow large_string; normalise to string so
        # older `datasets` releases read the files without a type surprise
        table = pa.Table.from_pandas(df, preserve_index=False)
        table = table.cast(pa.schema([
            f.with_type(pa.string()) if pa.types.is_large_string(f.type) else f
            for f in table.schema
        ]))
        pq.write_table(table, path, compression="zstd")
        print(f"  {name:<12} {len(df):>7,} rows  {path.stat().st_size/1024/1024:>6.1f} MB  "
              f"{len(df.columns)} cols")

    stats = {
        "resolutions": len(res_df),
        "votes": len(votes_df),
        "clauses": len(clauses_df),
        "countries": len(countries_df),
        "subjects": len(subjects_df),
        "country_situation_subjects": int(subjects_df["is_country_situation"].sum()),
        "historical_states": int(countries_df["is_historical_state"].sum()),
        "year_min": int(res_df["year"].min()),
        "year_max": int(res_df["year"].max()),
        "n_voting_states": int(votes_df["iso3"].nunique()),
        "with_rollcall": int(res_df["has_rollcall"].sum()),
        "rollcall_mismatch": int((res_df["rollcall_reconciles"] == False).sum()),  # noqa: E712
        "amendments": int(res_df["is_amendment"].sum()),
        "clause_years": [int(clauses_df["year"].min()), int(clauses_df["year"].max())],
        "clause_docs": int(clauses_df["symbol"].nunique()),
        "operative_clauses": int((clauses_df["clause_type"] == "operative").sum()),
    }
    (OUT / "dataset_stats.json").write_text(json.dumps(stats, indent=2) + "\n")
    print("\nstats:", json.dumps(stats))


if __name__ == "__main__":
    main()
