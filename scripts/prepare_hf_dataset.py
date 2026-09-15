"""Build the Hugging Face package in huggingface/hrc-voting/ from the repo's own outputs.

    python scripts/prepare_hf_dataset.py

Nine configs, because the source is relational and flattening it would either explode
the row count or throw away the resolution-level metadata:

  resolutions  one row per catalogued resolution           (data/csv/resolutions.csv)
  votes        one row per (resolution, country) roll-call (data/csv/votes_long.csv)
  clauses      one row per clause of a harvested text      (dashboard/texts/)
  countries    dimension table, 200 states (154 CHR/HRC)   (dashboard/data.js)
  subjects     dimension table, OHCHR's controlled vocab   (dashboard/data.js)

  General Assembly — Third Committee (added September 2026; scripts/ga/):
  ga_resolutions      one row per GA resolution adopted by recorded vote  (data/csv/ga_resolutions.csv)
  ga_votes            one row per (GA resolution, State) plenary vote      (data/csv/ga_votes_long.csv)
  ga_committee_events one row per recorded vote in the Third Committee    (data/csv/ga_committee_events.csv)
  ga_committee_votes  one row per (committee vote, State)                 (data/csv/ga_committee_votes.csv)
  ga_clauses          one row per clause of an Assembly text, 1993–       (dashboard/texts/)

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


# "One row is …" for each config, as shown in Methodology 13. A config with no entry
# here fails the build rather than reaching the dashboard undescribed.
HF_DESC = {
    "resolutions": "a catalogued resolution, decision or amendment (1946–2026)",
    "votes": "one state's position on one resolution (1947–2026)",
    "clauses": "one preambular / operative / annex clause — the Texts corpus, 1993–2026",
    "countries": "a state that cast at least one roll-call vote in any of the three organs (154 in the CHR/HRC tables)",
    "subjects": "one OHCHR controlled subject heading",
    "ga_resolutions": "a GA resolution adopted by recorded vote on a Third Committee text (1970–2025)",
    "ga_votes": "one state's plenary vote on one GA resolution (1970–2025)",
    "ga_committee_events": "one recorded vote in the Third Committee — draft, amendment, paragraph or motion (2000–2024)",
    "ga_committee_votes": "one state's vote in one committee-stage roll-call (2000–2024)",
    "ga_clauses": "one clause of an Assembly text, same columns as clauses (1993–2025)",
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


def build_clauses(res_df, bodies=("CHR", "HRC")):
    """Clause rows for the catalogued texts of the given organs. The `clauses` config stays
    a Commission/Council table; the Assembly's texts go to `ga_clauses` (same shape)."""
    cat = json.loads((TX / "catalog.json").read_text())["docs"]
    bundles = {int(f.stem.split("-")[1]): json.loads(f.read_text())
               for f in TX.glob("docs-*.json")}
    cols = [c for c in ("adoption_mode", "prevailing_side", "adopted") if c in res_df.columns]
    meta = res_df.set_index("record_id")[cols].to_dict("index")
    rows = []
    for sym, rid, year, body, vt, am, subj, title in cat:
        if body not in bodies:
            continue
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
                "adoption_mode": m.get("adoption_mode", "recorded" if body == "GA" else None),
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


def base_symbol(sym):
    """A/C.3/63/L.22/Rev.1 → A/C.3/63/L.22 (first symbol of a joined list, Add./Rev. dropped)."""
    import re
    s = (sym or "").split("|")[0].strip().upper()
    return re.sub(r"/(ADD|REV)\.\d+$", "", s)


def build_ga(groups, payload):
    """The four General Assembly configs; None if the GA CSVs are not present."""
    import re
    if not (CSVD / "ga_resolutions.csv").exists():
        return None
    res_rows = list(csv.DictReader(open(CSVD / "ga_resolutions.csv", encoding="utf-8")))
    ev_rows = list(csv.DictReader(open(CSVD / "ga_committee_events.csv", encoding="utf-8"))) \
        if (CSVD / "ga_committee_events.csv").exists() else []
    cv_rows = list(csv.DictReader(open(CSVD / "ga_committee_votes.csv", encoding="utf-8"))) \
        if (CSVD / "ga_committee_votes.csv").exists() else []
    # committee draft vote per base draft symbol (a later re-vote replaces an earlier one),
    # following the same trust rule as the dashboard build
    draft_ev = {}
    for e in ev_rows:
        if e["kind"] != "draft" or not e["draft_symbol"]:
            continue
        if e.get("symbol_source") == "context" and "draft resolution" not in e["subject"].lower():
            continue
        draft_ev[base_symbol(e["draft_symbol"])] = e
    # cross-organ bridge from the dashboard payload: GA record → CHR/HRC symbols
    idx = {i: r for i, r in enumerate(payload["res"])}
    related = {}
    for r in payload["res"]:
        if r.get("body") == "GA" and r.get("rel"):
            related[r["id"]] = "|".join(idx[j]["sym"] for j in r["rel"] if j in idx and idx[j].get("sym"))
    rid_by_draft = {}
    rows = []
    for r in res_rows:
        rid = "ga" + r["undl_id"]
        y, n, a = as_int(r["yes"]), as_int(r["no"]), as_int(r["abstain"])
        prevailing = None if (y is None or n is None) else ("Y" if y > n else "N" if n > y else None)
        b = base_symbol(r["draft"]) if r["draft"].startswith("A/C.3/") else ""
        e = draft_ev.get(b) if b else None
        if b:
            rid_by_draft.setdefault(b, rid)
        rows.append({
            "record_id": rid, "undl_id": as_int(r["undl_id"]), "symbol": r["symbol"], "title": r["title"],
            "session": as_int(r["session"]), "date": r["date"] or None, "year": as_int(r["year"]),
            "body": "GA", "draft": r["draft"] or None, "committee_report": r["committee_report"] or None,
            "meeting": r["meeting"] or None, "agenda_title": r["agenda_title"] or None,
            "subjects": r["subjects"] or None, "vote_note": r["vote_note"] or None,
            "third_committee_attribution": "draft symbol" if r["c3_source"] == "draft" else "agenda item",
            "yes": y, "no": n, "abstain": a, "nonvoting": as_int(r["nonvoting"]), "total": as_int(r["total"]),
            "n_rollcall": as_int(r["n_rollcall"]) or 0,
            "prevailing_side": prevailing, "adopted": None if prevailing is None else prevailing == "Y",
            "committee_event_id": e["event_id"] if e else None,
            "committee_sr_symbol": e["sr_symbol"] if e else None,
            "committee_date": e["meeting_date"] if e else None,
            "committee_yes": as_int(e["n_yes"]) if e else None,
            "committee_no": as_int(e["n_no"]) if e else None,
            "committee_abstain": as_int(e["n_abstain"]) if e else None,
            "committee_totals_match": (e["totals_match"] == "1") if e and e["stated_yes"] != "" else None,
            "related_chr_hrc_symbols": related.get(rid) or None,
            "url_resolution": f"https://docs.un.org/en/{r['symbol']}" if r["symbol"] else None,
            "record_url": r["record_url"] or None,
        })
    res_df = pd.DataFrame(rows)
    prevail = res_df.set_index("record_id")["prevailing_side"].to_dict()
    vrows = []
    for v in csv.DictReader(open(CSVD / "ga_votes_long.csv", encoding="utf-8")):
        rid, code = "ga" + v["undl_id"], v["vote"]
        pside = prevail.get(rid)
        vrows.append({
            "record_id": rid, "symbol": v["symbol"], "date": v["date"] or None, "year": as_int(v["year"]),
            "body": "GA", "iso3": v["iso3"] or None, "country": v["country"] or None,
            "un_regional_group": groups.get(v["iso3"]) or None,
            "vote": code or None, "vote_label": VOTE_LABEL.get(code, "unknown"),
            "is_cast_vote": code in ("Y", "N", "A"), "prevailing_side": pside,
            "with_prevailing_side": (code == pside) if (pside and code in ("Y", "N", "A")) else None,
        })
    votes_df = pd.DataFrame(vrows)
    erows = []
    for e in ev_rows:
        erows.append({
            "event_id": e["event_id"], "session": as_int(e["session"]), "sr_symbol": e["sr_symbol"],
            "meeting_no": as_int(e["meeting_no"]), "meeting_date": e["meeting_date"] or None,
            "kind": e["kind"], "draft_symbol": e["draft_symbol"] or None, "symbol_source": e["symbol_source"] or None,
            "as_amended": e["as_amended"] == "1", "subject": e["subject"] or None, "result": e["result"] or None,
            "stated_yes": as_int(e["stated_yes"]), "stated_no": as_int(e["stated_no"]), "stated_abstain": as_int(e["stated_abstain"]),
            "n_yes": as_int(e["n_yes"]), "n_no": as_int(e["n_no"]), "n_abstain": as_int(e["n_abstain"]),
            "totals_match": (e["totals_match"] == "1") if e["stated_yes"] != "" else None,
            "resolution_record_id": rid_by_draft.get(base_symbol(e["draft_symbol"])) if e["kind"] == "draft" else None,
        })
    events_df = pd.DataFrame(erows)
    ev_by_id = events_df.set_index("event_id")
    crows = []
    for v in cv_rows:
        crows.append({
            "event_id": v["event_id"], "session": as_int(v["session"]), "draft_symbol": v["draft_symbol"] or None,
            "kind": ev_by_id["kind"].get(v["event_id"]),
            "resolution_record_id": ev_by_id["resolution_record_id"].get(v["event_id"]),
            "iso3": v["iso3"] or None, "country": v["country"] or None,
            "un_regional_group": groups.get(v["iso3"]) or None,
            "vote": v["vote"] or None, "vote_label": VOTE_LABEL.get(v["vote"], "unknown"),
        })
    cvotes_df = pd.DataFrame(crows)
    return {"ga_resolutions": res_df, "ga_votes": votes_df,
            "ga_committee_events": events_df, "ga_committee_votes": cvotes_df}


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

    tables = [("resolutions", res_df), ("votes", votes_df), ("clauses", clauses_df),
              ("countries", countries_df), ("subjects", subjects_df)]
    ga = build_ga(groups, payload)
    if ga:
        ga_clauses = build_clauses(ga["ga_resolutions"], bodies=("GA",))
        cs_ga = {s: is_country_subject(s) for s in ga_clauses["subject"].dropna().unique()}
        ga_clauses["subject_is_country_situation"] = ga_clauses["subject"].map(cs_ga)
        ga["ga_clauses"] = ga_clauses
        tables += list(ga.items())
    for name, df in tables:
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

    # Methodology 13 renders its config table from this file, so the dashboard can never
    # again list five configs and 154 countries while the package has ten and 200 —
    # the drift that happened at v1.1.0. One description per config, kept here with
    # the row counts so a new config cannot reach the Hub without reaching the table.
    undescribed = [name for name, _ in tables if name not in HF_DESC]
    if undescribed:
        raise SystemExit(f"no HF_DESC entry for {undescribed} — add one before shipping, "
                         "or Methodology 13 lists a config it cannot describe")
    hf_stats = {"configs": [{"name": name, "rows": len(df), "desc": HF_DESC[name]}
                            for name, df in tables]}
    (ROOT / "dashboard" / "hf_stats.js").write_text(
        "window.HF_STATS = " + json.dumps(hf_stats, ensure_ascii=False) + ";\n",
        encoding="utf-8")
    print(f"  dashboard/hf_stats.js: {len(tables)} configs")

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
    if ga:
        g = ga["ga_resolutions"]
        stats["ga"] = {
            "resolutions": len(g), "votes": len(ga["ga_votes"]),
            "session_min": int(g["session"].min()), "session_max": int(g["session"].max()),
            "year_min": int(g["year"].min()), "year_max": int(g["year"].max()),
            "by_draft_symbol": int((g["third_committee_attribution"] == "draft symbol").sum()),
            "by_agenda_item": int((g["third_committee_attribution"] == "agenda item").sum()),
            "with_committee_rollcall": int(g["committee_event_id"].notna().sum()),
            "related_to_chr_hrc": int(g["related_chr_hrc_symbols"].notna().sum()),
            "committee_events": len(ga["ga_committee_events"]),
            "committee_votes": len(ga["ga_committee_votes"]),
            "committee_events_by_kind": {k: int(v) for k, v in ga["ga_committee_events"]["kind"].value_counts().items()},
            "clauses": len(ga["ga_clauses"]), "clause_docs": int(ga["ga_clauses"]["symbol"].nunique()),
            "clause_years": [int(ga["ga_clauses"]["year"].min()), int(ga["ga_clauses"]["year"].max())],
        }
    (OUT / "dataset_stats.json").write_text(json.dumps(stats, indent=2) + "\n")
    print("\nstats:", json.dumps(stats))


if __name__ == "__main__":
    main()
