"""General Assembly (Third Committee) resolutions with a recorded plenary vote.

Reads the UN Digital Library "General Assembly voting data" CSV
(data/raw/ga/<version>_ga_voting.csv, one row per Member State vote) and writes
the same two-file shape the CHR/HRC pipeline uses:

  data/csv/ga_resolutions.csv   one row per resolution (metadata + official totals)
  data/csv/ga_votes_long.csv    one row per (resolution, Member State) plenary vote

A resolution is "Third Committee" when its draft symbol is A/C.3/… (explicit,
from session 55 on). Earlier sessions carry no draft symbol in the dataset;
they are left out here and handled separately once an agenda-based rule is
validated (see notes/GA_THIRD_COMMITTEE_PLAN.md).

Usage: python3 scripts/ga/parse_undl.py [--csv data/raw/ga/2026_02_06_ga_voting.csv]
"""
import argparse
import collections
import csv
import glob
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
OUT = ROOT / "data" / "csv"
csv.field_size_limit(10 ** 9)

RES_COLS = ["undl_id", "symbol", "session", "date", "year", "body", "draft", "committee_report",
            "meeting", "title", "agenda_title", "subjects", "vote_note",
            "yes", "no", "abstain", "nonvoting", "total", "n_rollcall", "c3_source", "record_url"]
VOTE_COLS = ["undl_id", "symbol", "date", "year", "body", "vote_type", "seq", "iso3", "country", "vote"]
VOTE_CODE = {"Y": "Y", "N": "N", "A": "A", "X": "."}   # X = non-voting → "." as in the CHR/HRC file


def num(x):
    """Totals arrive as '106.0'; keep them as plain integers."""
    try:
        return int(float(x))
    except ValueError:
        return 0


# Before session 55 the dataset carries no draft symbol, so a resolution is
# attributed to the Third Committee by its agenda item. The list is the set of
# agenda titles that carry A/C.3 drafts from session 55 on, plus the items the
# Committee handled earlier under other names. Items that sound like human rights
# but belonged to other committees are deliberately absent: apartheid policies,
# UNRWA and the Special Committee on Israeli practices (Special Political
# Committee), foreign economic interests in colonial territories (Fourth
# Committee). Validation against sessions 55–80 is printed at the end.
C3_AGENDA = re.compile(r"""^(?:
  human\ rights\ questions|
  human\ rights\ situations\ and\ reports|
  right\ of\ peoples\ to\ self-determination|
  importance\ of\ the\ universal\ realization\ of\ the\ right\ of\ peoples\ to\ self-determination|
  elimination\ of\ (?:all\ forms\ of\ )?rac|
  comprehensive\ implementation\ of\ an?d?\ follow-up\ to\ the\ durban|
  implementation\ of\ the\ programme\ for\ the\ decade\ for\ action\ to\ combat\ racism|
  (?:second\ |third\ )?decade\ (?:for\ action\ )?to\ combat\ racism|
  international\ covenants\ on\ human\ rights|
  implementation\ of\ human\ rights\ instruments|
  status\ of\ the\ international\ convention|
  human\ rights\ and\ scientific|
  alternative\ approaches\ and\ ways\ and\ means|
  adverse\ consequences\ for\ the\ enjoyment\ of\ human\ rights|
  torture\ and\ other\ cruel|
  report\ of\ the\ (?:united\ nations\ )?high\ commissioner\ for\ refugees|
  report\ of\ the\ human\ rights\ council|
  promotion\ and\ protection\ of\ the\ rights\ of\ children|
  rights\ of\ (?:the\ child|indigenous)|
  advancement\ of\ women|
  implementation\ of\ the\ outcome\ of\ the\ (?:4th|fourth)\ world\ conference\ on\ women|
  social\ development|
  implementation\ of\ the\ outcome\ of\ the\ world\ summit\ for\ social\ development|
  crime\ prevention\ and\ criminal\ justice|
  international\ drug\ control|
  countering\ the\ use\ of\ information\ and\ communications\ technologies\ for\ criminal|
  world\ social\ situation|
  policies\ and\ programmes\ (?:relating\ to|involving)\ youth|
  international\ year\ of\ the\ family|
  question\ of\ ag(?:e)?ing|
  strengthening\ of\ united\ nations\ action\ in\ the\ (?:human\ rights|field\ of\ human\ rights)|
  office\ of\ the\ united\ nations\ high\ commissioner\ for\ human\ rights|
  united\ nations\ decade\ for\ human\ rights\ education|
  human\ rights\ education|
  the\ right\ to\ development|
  respect\ for\ the\ right\ to\ universal\ freedom\ of\ travel|
  protection\ of\ migrants|
  the\ girl\ child|
  violence\ against\ women|
  traffic(?:king)?\ in\ women|
  measures\ to\ be\ taken\ against\ nazi|
  (?:the\ )?situation\ of\ human\ rights\ in
)""", re.I | re.X)


def agenda_c3(agenda_title):
    """True when every '|'-separated agenda title matches the Third Committee list."""
    parts = [a.strip() for a in agenda_title.split("|") if a.strip()]
    return bool(parts) and all(C3_AGENDA.search(a) for a in parts)


def main():
    ap = argparse.ArgumentParser()
    default = sorted(glob.glob(str(ROOT / "data" / "raw" / "ga" / "*_ga_voting.csv")))
    ap.add_argument("--csv", default=default[-1] if default else None)
    args = ap.parse_args()
    if not args.csv:
        raise SystemExit("no data/raw/ga/*_ga_voting.csv found")

    res = {}
    votes = collections.defaultdict(list)
    validation = {}   # resolutions NOT selected, for the agenda-rule check below
    with open(args.csv, newline="", encoding="utf-8-sig") as fh:
        for row in csv.DictReader(fh):
            explicit = row["draft"].startswith("A/C.3/")
            pre55 = not row["session"].isdigit() or int(row["session"]) < 55
            if not explicit and not (pre55 and not row["draft"] and agenda_c3(row["agenda_title"])):
                validation.setdefault(row["undl_id"], (row["session"], row["draft"], row["agenda_title"]))
                continue
            rid = row["undl_id"]
            if rid not in res:
                res[rid] = {
                    "undl_id": rid, "symbol": row["resolution"], "session": row["session"],
                    "date": row["date"], "year": row["date"][:4], "body": "General Assembly",
                    "draft": row["draft"], "committee_report": row["committee_report"],
                    "meeting": row["meeting"], "title": row["title"], "agenda_title": row["agenda_title"],
                    "subjects": row["subjects"], "vote_note": row["vote_note"],
                    "yes": num(row["total_yes"]), "no": num(row["total_no"]), "abstain": num(row["total_abstentions"]),
                    "nonvoting": num(row["total_non_voting"]), "total": num(row["total_ms"]),
                    "n_rollcall": 0, "c3_source": "draft" if explicit else "agenda", "record_url": row["undl_link"],
                }
            votes[rid].append({
                "undl_id": rid, "symbol": row["resolution"], "date": row["date"], "year": row["date"][:4],
                "body": "General Assembly", "vote_type": "RECORDED", "seq": len(votes[rid]) + 1,
                "iso3": row["ms_code"], "country": row["ms_name"], "vote": VOTE_CODE.get(row["ms_vote"], row["ms_vote"]),
            })
    for rid, rows in votes.items():
        res[rid]["n_rollcall"] = len(rows)

    OUT.mkdir(parents=True, exist_ok=True)
    ordered = sorted(res.values(), key=lambda r: (int(r["session"]) if r["session"].isdigit() else 0, r["date"], r["symbol"]))
    with open(OUT / "ga_resolutions.csv", "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=RES_COLS); w.writeheader(); w.writerows(ordered)
    with open(OUT / "ga_votes_long.csv", "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=VOTE_COLS); w.writeheader()
        for r in ordered:
            w.writerows(votes[r["undl_id"]])

    # reconciliation: roll-call tally vs official totals
    ok = bad = 0
    for r in ordered:
        t = collections.Counter(v["vote"] for v in votes[r["undl_id"]])
        if (t["Y"], t["N"], t["A"]) == (r["yes"], r["no"], r["abstain"]):
            ok += 1
        else:
            bad += 1
    per_session = collections.Counter(r["session"] for r in ordered)
    print(f"[ga] {len(ordered)} Third Committee resolutions with a recorded plenary vote, "
          f"{sum(len(v) for v in votes.values())} votes, sessions {min(per_session, key=int)}–{max(per_session, key=int)}")
    print(f"[ga] totals reconciled: {ok} match, {bad} mismatch")
    print("[ga] per session:", " ".join(f"{s}:{n}" for s, n in sorted(per_session.items(), key=lambda x: int(x[0]))))
    by_source = collections.Counter(r["c3_source"] for r in ordered)
    print(f"[ga] attribution: {by_source['draft']} by draft symbol, {by_source['agenda']} by agenda item (sessions < 55)")
    # Validate the agenda rule where the truth is known (session >= 55, draft present):
    # recall = explicit C.3 resolutions the rule would catch; false positives = other
    # committees' resolutions the rule would wrongly catch.
    caught = sum(1 for r in ordered if r["c3_source"] == "draft" and agenda_c3(r["agenda_title"]))
    fp = [(s, d, a[:70]) for s, d, a in validation.values() if s.isdigit() and int(s) >= 55 and d and agenda_c3(a)]
    print(f"[ga] agenda rule on sessions 55–80: recall {caught}/{by_source['draft']}, false positives {len(fp)}")
    for x in fp[:12]:
        print("      fp:", x)


if __name__ == "__main__":
    main()
