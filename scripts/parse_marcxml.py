"""
Parse harvested MARCXML (data/raw/page_*.xml) into dashboard-ready CSVs:

  data/csv/resolutions.csv  - one row per voting record (metadata + vote totals)
  data/csv/votes_long.csv   - one row per (record, country) roll-call vote

Dedupes records by MARC 001 (control number).
"""
import csv
import glob
import re
from pathlib import Path
from xml.etree import ElementTree as ET

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "data" / "raw"
OUT = ROOT / "data" / "csv"
OUT.mkdir(parents=True, exist_ok=True)
NS = {"m": "http://www.loc.gov/MARC21/slim"}


def isodate(s):
    """YYYYMMDD -> YYYY-MM-DD; tolerate year-only / junk."""
    if not s:
        return ""
    s = s.strip()
    if re.fullmatch(r"\d{8}", s):
        return f"{s[:4]}-{s[4:6]}-{s[6:8]}"
    if re.fullmatch(r"\d{4}", s):
        return s
    return s


def parse_record(rec):
    # control fields
    ctrl = {cf.get("tag"): (cf.text or "").strip()
            for cf in rec.findall("m:controlfield", NS)}
    # datafields: tag -> list of {code: value} (first value per code kept, plus
    # 'a_all' style not needed here); we keep per-occurrence dicts
    dfs = {}
    for df in rec.findall("m:datafield", NS):
        tag = df.get("tag")
        d = {}
        for sf in df.findall("m:subfield", NS):
            code = sf.get("code")
            d.setdefault(code, (sf.text or "").strip())
        dfs.setdefault(tag, []).append(d)

    def first(tag, code, default=""):
        for occ in dfs.get(tag, []):
            if code in occ:
                return occ[code]
        return default

    def all_sub(tag, code):
        return [occ[code] for occ in dfs.get(tag, []) if code in occ]

    rid = ctrl.get("001", "")

    # title 245
    t = dfs.get("245", [{}])[0]
    title = " ".join(x for x in [t.get("a", ""), t.get("b", "")] if x).strip()
    statement = t.get("c", "")

    # date: prefer 269$a, fall back to 992$a
    date_raw = first("269", "a") or first("992", "a")
    date = isodate(date_raw)
    year = date[:4] if len(date) >= 4 else ""

    # sponsors from 500 notes
    notes = all_sub("500", "a")
    sponsors = ""
    for n in notes:
        mm = re.match(r"\s*Main sponsors?\s*:\s*(.+)", n, re.I)
        if mm:
            sponsors = mm.group(1).strip()
            break

    # links 856 by label
    url_res = url_draft = ""
    for occ in dfs.get("856", []):
        y = (occ.get("y", "") or "").lower()
        u = occ.get("u", "")
        if "resolution" in y and "draft" not in y and not url_res:
            url_res = u
        elif "draft" in y and not url_draft:
            url_draft = u
    # totals 996
    tot = dfs.get("996", [{}])[0]

    # roll-call votes 967
    votes = []
    for occ in dfs.get("967", []):
        code = occ.get("d", "")
        # Normalize the one unambiguous typo ('y' -> 'Y'); leave '.'/'' as-is.
        code = code.upper() if code in ("y",) else code
        iso = occ.get("b", "")
        name = occ.get("e", "")
        # Repair rare malformed subfield where '$e<name>' leaked into $b
        # (e.g. rec 31144: b="VEN$eVENEZUELA (...)"), recovering iso3 + name.
        if "$" in iso or len(iso) > 3:
            emb = re.search(r"\$e(.+)$", iso)
            if emb and not name:
                name = emb.group(1)
            lead = re.match(r"([A-Za-z]{2,3})", iso)
            iso = lead.group(1).upper() if lead else iso[:3]
        votes.append({
            "seq": occ.get("a", ""),
            "iso3": iso,
            "vote": code,
            "country": name,
        })

    row = {
        "record_id": rid,
        "symbol": first("791", "a"),
        "title": title,
        "statement": statement,
        "date": date,
        "year": year,
        "body": first("981", "a"),
        "collection": first("980", "a"),
        "vote_type": first("591", "a"),
        "meeting": first("952", "a"),
        "meeting_type": first("793", "v"),
        "agenda_item_no": first("991", "b"),
        "agenda_item_title": first("991", "c"),
        "agenda_symbol": first("991", "a"),
        "agenda_subject": first("991", "d"),
        "main_sponsors": sponsors,
        "draft": first("993", "a") or first("991", "a"),
        "yes": tot.get("b", ""),
        "no": tot.get("c", ""),
        "abstain": tot.get("d", ""),
        "nonvoting": tot.get("e", ""),
        "total": tot.get("f", ""),
        "n_rollcall": len(votes),
        "url_resolution": url_res,
        "url_draft": url_draft,
        "record_url": f"https://searchlibrary.ohchr.org/record/{rid}" if rid else "",
    }
    return row, votes


def main():
    seen = {}
    order = []
    for fp in sorted(glob.glob(str(RAW / "*.xml"))):
        tree = ET.parse(fp)
        for rec in tree.getroot().findall("m:record", NS):
            row, votes = parse_record(rec)
            rid = row["record_id"]
            if not rid or rid in seen:
                continue
            seen[rid] = (row, votes)
            order.append(rid)

    res_cols = ["record_id", "symbol", "title", "statement", "date", "year",
                "body", "collection", "vote_type", "meeting", "meeting_type",
                "agenda_item_no", "agenda_item_title", "agenda_symbol",
                "agenda_subject", "main_sponsors", "draft",
                "yes", "no", "abstain", "nonvoting", "total", "n_rollcall",
                "url_resolution", "url_draft", "record_url"]
    vote_cols = ["record_id", "symbol", "date", "year", "body", "vote_type",
                 "seq", "iso3", "country", "vote"]

    with open(OUT / "resolutions.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=res_cols)
        w.writeheader()
        for rid in order:
            w.writerow(seen[rid][0])

    nvotes = 0
    with open(OUT / "votes_long.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=vote_cols)
        w.writeheader()
        for rid in order:
            row, votes = seen[rid]
            for v in votes:
                w.writerow({"record_id": rid, "symbol": row["symbol"],
                            "date": row["date"], "year": row["year"],
                            "body": row["body"], "vote_type": row["vote_type"],
                            **v})
                nvotes += 1

    print(f"Unique records: {len(order)}")
    print(f"resolutions.csv rows: {len(order)}")
    print(f"votes_long.csv rows: {nvotes}")

    # quick sanity summary
    from collections import Counter
    rows = [seen[r][0] for r in order]
    by_body = Counter(r["body"] for r in rows)
    by_type = Counter(r["vote_type"] for r in rows)
    yrs = [int(r["year"]) for r in rows if r["year"].isdigit()]
    print("\nBy body:", dict(by_body))
    print("By vote_type:", dict(by_type.most_common()))
    if yrs:
        print(f"Year range: {min(yrs)}-{max(yrs)}")
    print("Records with 0 roll-call rows:",
          sum(1 for r in rows if r["n_rollcall"] == 0))


if __name__ == "__main__":
    main()
