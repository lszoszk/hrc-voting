"""
Parse harvested MARCXML (data/raw/page_*.xml) into dashboard-ready CSVs:

  data/csv/resolutions.csv  - one row per voting record (metadata + vote totals)
  data/csv/votes_long.csv   - one row per (record, country) roll-call vote

Dedupes records by MARC 001 (control number).
"""
import collections
import csv
import difflib
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


def repair_iso(seen):
    """Repair 967$b codes that contradict the country name in 967$e.

    Two catalogued rows carry another state's ISO code (record 21028 has NORWAY as
    'PER', record 30508 has BRAZIL as 'BEN'). Left alone they move a vote from one
    country's profile to another's and make the same state appear twice on one
    resolution. The name is authoritative: build name -> iso3 from the corpus
    majority, then correct rows that disagree.  Returns the list of repairs.
    """
    tally = collections.defaultdict(collections.Counter)
    for _, votes in seen.values():
        for v in votes:
            if v["iso3"] and v["country"]:
                tally[v["country"].strip().upper()][v["iso3"]] += 1
    canon = {n: c.most_common(1)[0][0] for n, c in tally.items()
             if c.most_common(1)[0][1] >= 3}          # needs corroboration
    fixed = []
    for rid, (row, votes) in seen.items():
        for v in votes:
            want = canon.get(v["country"].strip().upper())
            if want and v["iso3"] and want != v["iso3"]:
                fixed.append((rid, row["symbol"], v["country"], v["iso3"], want))
                v["iso3"] = want
    return fixed


HRC_L = r"A/HRC/(?:S-)?\d+/L\.\d+(?:/Rev\.\d+)?"


def _base(sym):
    """A/HRC/52/L.7/Rev.1 -> A/HRC/52/L.7: an amendment names the draft as it stood when
    it was tabled, the resolution record the revision that was adopted."""
    return re.sub(r"/REV\.\d+$", "", re.sub(r"\s+", "", sym).upper().rstrip("."))


def _session(sym):
    m = re.search(r"A/HRC/(?:RES/|DEC/|PRST/)?((?:S-)?\d+)/", sym)
    return m.group(1) if m else ""


def link_amendments(rows):
    """Amendments only ever carry their own L. symbol (they are never re-issued as a
    resolution), so each one gets the draft it amended (`amends_draft`, from the 993
    note) and the final text that draft became (`final_symbol`: the A/HRC/RES, DEC or
    PRST record whose 993/856 names that draft). Empty when the draft was not adopted
    or the note does not name one.

    The 993 note of an amendment is sometimes wrong (A/HRC/37/L.51-57 on prevention of
    genocide say "to draft resolution L.1", the Eastern Ghouta text). So a link stands
    only when the two titles agree; otherwise the final text is looked up by title
    among the same session's texts, and left empty when none matches.
    Returns (linked, amendments, linked by title)."""
    finals = collections.defaultdict(set)
    by_sym, by_session = {}, collections.defaultdict(list)
    for r in rows:
        if re.search(r"A/HRC/(RES|DEC|PRST)/", r["symbol"]):
            drafts = re.findall(HRC_L, r["draft"] + " " + r["url_draft"])
            same = [d for d in drafts if _session(d) == _session(r["symbol"])]
            for d in same or drafts:     # RES/53/5's note says 52/L.7, its link 53/L.7
                finals[_base(d)].add(r["symbol"])
            by_sym[r["symbol"]] = (r, (same or drafts or [""])[0])
            by_session[_session(r["symbol"])].append(r["symbol"])

    def tt(t):
        return re.sub(r"\s*:\s*(draft\s+)?(resolution|decision|amendment|presidential statement)s?"
                      r"\s*/.*$", "", t, flags=re.I).strip().lower()

    def sim(a, b):
        return difflib.SequenceMatcher(None, tt(a), tt(b)).ratio()

    linked = n = by_title = 0
    for r in rows:
        r["amends_draft"] = r["final_symbol"] = ""
        is_am = (re.search(r":\s*amendment", r["title"], re.I)
                 or re.match(r"\s*amendment", r["draft"], re.I))
        if not (is_am and "/L." in r["symbol"]):
            continue
        n += 1
        d, own, sess = r["draft"], _base(r["symbol"]), _session(r["symbol"])
        m = (re.search(r"\bto\s+(?:the\s+)?(?:draft\s+(?:resolution|decision|text)s?\s+)?("
                       + HRC_L + ")", d, re.I))
        parent = m.group(1) if m else ""
        if not parent:          # "to draft resolution L.41"
            m = re.search(r"\bto\s+(?:the\s+)?draft\s+(?:resolution|decision)s?\s+"
                          r"(L\.\d+(?:/Rev\.\d+)?)", d, re.I)
            parent = f"A/HRC/{sess}/{m.group(1)}" if m and sess else ""
        if not parent:          # "Amendment to A/HRC/39/L.20 A/HRC/39/L.26 ..."
            parent = next((s for s in re.findall(HRC_L, d) if _base(s) != own), "")
        cand = finals.get(_base(parent), set()) if parent else set()
        fin = next(iter(cand)) if len(cand) == 1 else ""
        if fin and sim(r["title"], by_sym[fin][0]["title"]) < 0.5:
            fin = parent = ""            # the note names a draft on another subject
        if not fin:
            scored = sorted(((sim(r["title"], by_sym[f][0]["title"]), f)
                             for f in by_session.get(sess, [])), reverse=True)
            if scored and scored[0][0] >= 0.8 and (len(scored) == 1 or scored[1][0] < scored[0][0]):
                fin = scored[0][1]
                parent = parent or by_sym[fin][1]
                by_title += 1
        r["amends_draft"], r["final_symbol"] = parent, fin
        linked += bool(fin)
    return linked, n, by_title


SESSION_PAGES = ROOT / "data" / "ohchr_session_pages" / "hrc_adoption_dates.txt"


def load_session_page_dates(path=SESSION_PAGES, window_days=45):
    """symbol -> adoption date from OHCHR's per-session tables (sessions 12-63).

    A date is kept only when it falls within `window_days` of the session's median date
    (the pages carry typos such as 37/19 dated 2019) and the page gives the text a single
    date. Day-and-month-only entries ("????") take the session's year."""
    import datetime as dt
    import statistics
    out = {}
    if not path.exists():
        return out
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip() or line.startswith("#"):
            continue
        sess, rest = line.split("|", 1)
        groups = [g.split(":", 1) for g in rest.split(";") if ":" in g]
        full = [d for d, _ in groups if re.fullmatch(r"\d{4}-\d\d-\d\d", d)]
        if not full:
            continue
        year = collections.Counter(d[:4] for d in full).most_common(1)[0][0]
        mid = dt.date.fromordinal(int(statistics.median(dt.date.fromisoformat(d).toordinal() for d in full)))
        seen = collections.defaultdict(set)
        for d, texts in groups:
            if d.startswith("????"):
                d = year + d[4:]
            if not re.fullmatch(r"\d{4}-\d\d-\d\d", d):
                continue
            try:
                if abs((dt.date.fromisoformat(d) - mid).days) > window_days:
                    continue
            except ValueError:
                continue
            for t in texts.split(","):
                kind, num = t[:1], t[1:]
                sym = {"R": f"A/HRC/RES/{sess}/{num}", "D": f"A/HRC/DEC/{sess}/{num}",
                       "P": f"A/HRC/PRST/{sess}/{num}", "L": f"A/HRC/{sess}/L.{num}"}.get(kind)
                if sym and re.fullmatch(r"[\w./-]+", num):
                    seen[sym].add(d)
        out.update({k: next(iter(v)) for k, v in seen.items() if len(v) == 1})
    return out


def apply_adoption_dates(rows, page_dates):
    """OHCHR's catalogue sometimes dates a Council text by its draft, not its adoption
    (A/HRC/RES/63/2: catalogued 24 Sep 2026, adopted 5 Oct 2026). Use the session page's
    adoption date where it has one; give records voted at the same meeting (amendments,
    rejected and withdrawn drafts) that meeting's date when it is unambiguous. Keeps the
    catalogue's date in `catalogue_date` and says where `date` came from in `date_source`.
    Returns a Counter of what was done."""
    stats = collections.Counter()
    by_meeting = collections.defaultdict(set)
    for r in rows:
        r["catalogue_date"], r["date_source"] = r["date"], "catalogue"
        if not r["body"].startswith("Human Rights Council"):
            continue
        d = page_dates.get(re.sub(r"\s+", "", r["symbol"]))
        if d:
            stats["changed" if d != r["date"] else "confirmed"] += 1
            r["date"], r["date_source"] = d, "OHCHR session page"
        mt = re.search(r"(\d+)(?:st|nd|rd|th) meeting", r["meeting"])
        if d and mt:
            by_meeting[(_session(r["symbol"]), mt.group(1))].add(d)
    for r in rows:
        if r["date_source"] != "catalogue" or not r["body"].startswith("Human Rights Council"):
            continue
        mt = re.search(r"(\d+)(?:st|nd|rd|th) meeting", r["meeting"])
        ds = by_meeting.get((_session(r["symbol"]), mt.group(1))) if mt else None
        if ds and len(ds) == 1:
            d = next(iter(ds))
            stats["meeting, changed" if d != r["date"] else "meeting, confirmed"] += 1
            r["date"], r["date_source"] = d, "OHCHR session page (same meeting)"
    for r in rows:
        if r["date"][:4].isdigit():
            r["year"] = r["date"][:4]
    return stats


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

    for rid, sym, name, was, now in repair_iso(seen):
        print(f"iso3 repaired: rec {rid} {sym} — {name} was '{was}', now '{now}'")

    linked, n_am, by_title = link_amendments([seen[r][0] for r in order])
    st = apply_adoption_dates([seen[r][0] for r in order], load_session_page_dates())
    print("HRC dates from OHCHR session pages:", dict(st))
    print(f"amendments linked to the final text of the draft they amended: {linked} of {n_am} "
          f"({by_title} by title, where the catalogue note names no or another draft)")

    res_cols = ["record_id", "symbol", "title", "statement", "date", "year",
                "body", "collection", "vote_type", "meeting", "meeting_type",
                "agenda_item_no", "agenda_item_title", "agenda_symbol",
                "agenda_subject", "main_sponsors", "draft",
                "yes", "no", "abstain", "nonvoting", "total", "n_rollcall",
                "url_resolution", "url_draft", "record_url",
                "amends_draft", "final_symbol", "catalogue_date", "date_source"]
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
