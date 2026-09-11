"""Per-State votes from the Third Committee voting-sheet PDFs — a cross-check source.

The sheets behind un.org/en/ga/third/<s>/votingsheets.shtml come in two generations:

* sessions 65–73: scanned printouts of the conference-room board, mostly without a
  usable text layer (a partial OCR layer on some; image-only on most);
* sessions 74–78: native e-voting PDFs — four columns of "<Y|N|A> STATE", a
  "Vote Name:" block with the draft symbol and title, printed Yes/No/Abstain totals
  and a "Vote Time:". A few States can be missing from the text layer of a native
  sheet, so only sheets whose parsed counts equal the printed totals are trusted.

The dashboard does not use these votes: the summary records (parse_sr_votes.py)
cover every session and carry the same lists. The sheets serve to validate the
summary-record parser — on the 60 trusted sheets of sessions 75–77 that pair with a
summary-record vote, 10,480 of 10,482 State-votes agree (September 2026). Writes

  data/csv/ga_sheet_events.csv   one row per sheet (session, file, symbol, kind, date, counts, quality flags)
  data/csv/ga_sheet_votes.csv    one row per (sheet, State): Y / N / A, or "." for a State listed without a vote

Usage: python3 scripts/ga/parse_sheets.py [--sessions 65-78]
"""
import argparse
import csv
import difflib
import glob
import re
import subprocess
import unicodedata
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
RAW = ROOT / "data" / "raw" / "ga" / "sheets"
OUT = ROOT / "data" / "csv"
csv.field_size_limit(10 ** 9)

# board abbreviations and OCR-prone spellings → ISO3
ALIASES = {
    "antigua barbuda": "ATG", "bosnia herzeg": "BIH", "bosnia herzegovina": "BIH", "marshall island": "MHL",
    "micronesia fs": "FSM", "micronesia federated": "FSM", "micronesia federated states of": "FSM",
    "saint kitts nev": "KNA", "st kitts nevis": "KNA", "saint kitis nev": "KNA", "saint vincent g": "VCT", "st vincent gren": "VCT",
    "trinidad tobago": "TTO", "sao tome princi": "STP", "sao tome principe": "STP",
    "dem pr korea": "PRK", "oem pr korea": "PRK", "dempr korea": "PRK", "oempr korea": "PRK", "dprk": "PRK",
    "dem rep of cong": "COD", "oem rep of cong": "COD", "dem rep of the congo": "COD", "dem rep congo": "COD", "drc": "COD",
    "lao people s dem rep": "LAO", "lao pdr": "LAO", "lao peoples dem rep": "LAO", "laos": "LAO",
    "uk": "GBR", "united kingdom": "GBR", "usa": "USA", "united states": "USA", "russian fed": "RUS",
    "syrian arab rep": "SYR", "syria": "SYR", "united r tanz": "TZA", "united rep of tanzania": "TZA", "tanzania": "TZA",
    "rep of korea": "KOR", "rep of moldova": "MDA", "iran islamic rep": "IRN", "iran": "IRN",
    "venezuela bolivarian rep": "VEN", "venezuela": "VEN", "bolivia plurinational state": "BOL", "bolivia": "BOL",
    "tfyr macedonia": "MKD", "the former yugoslav republic of macedonia": "MKD", "north macedonia": "MKD", "macedonia": "MKD",
    "central afr rep": "CAF", "central african rep": "CAF", "dominican rep": "DOM", "czech rep": "CZE", "czechia": "CZE",
    "libyan arab jamahiriya": "LBY", "libya": "LBY", "libyan aj": "LBY", "cote divo ire": "CIV", "cote d ivoire": "CIV", "cote divoire": "CIV",
    "cape verde": "CPV", "cabo verde": "CPV", "swaziland": "SWZ", "eswatini": "SWZ", "viet nam": "VNM", "vietnam": "VNM",
    "turkiye": "TUR", "turkey": "TUR", "netherlands kingdom of the": "NLD", "netherlands": "NLD",
    "brunei dar sala": "BRN", "brunei darussalam": "BRN", "brunei": "BRN", "timor leste": "TLS", "papua n guinea": "PNG",
    "united a emi": "ARE", "united arab emi": "ARE", "uae": "ARE", "equat guinea": "GNQ", "saudi arabia": "SAU",
    "guinea bissau": "GNB", "south sudan": "SSD", "solomon islands": "SLB", "sri lanka": "LKA", "burkina faso": "BFA",
}


def norm(s):
    s = s.replace("’", "'").replace("·", "-").replace(" ", " ")
    s = unicodedata.normalize("NFD", s).encode("ascii", "ignore").decode().lower()
    s = re.sub(r"[^a-z ]+", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def build_names():
    names = {}
    src = sorted(glob.glob(str(ROOT / "data" / "raw" / "ga" / "*_ga_voting.csv")))
    seen = set()
    with open(src[-1], newline="", encoding="utf-8-sig") as fh:
        for row in csv.DictReader(fh):
            key = (row["ms_code"], row["ms_name"])
            if key in seen:
                continue
            seen.add(key)
            names.setdefault(norm(row["ms_name"]), row["ms_code"])
            names.setdefault(norm(re.sub(r"\s*\(.*?\)", "", row["ms_name"])), row["ms_code"])
    names.update(ALIASES)
    return names


class Matcher:
    def __init__(self, names):
        self.names = names
        self.keys = list(names)
        self.cache = {}

    def __call__(self, raw):
        n = norm(raw)
        if len(n) < 3:
            return None
        if n in self.cache:
            return self.cache[n]
        iso = self.names.get(n) or self.names.get(norm(re.sub(r"\s*\(.*$", "", raw)))
        if not iso:
            close = difflib.get_close_matches(n, self.keys, n=1, cutoff=0.8)
            iso = self.names[close[0]] if close else None
        self.cache[n] = iso
        return iso


NOISE = re.compile(r"^(?:VOTE|ITEM|DATE|SUBJECT|MEETING|COMMITTEE|YES|NO|ABSTAIN|TOTAL|RECORDED|ADOPTED|REJECTED|MULTIPLE|THIRD|CONFERENCE|ROOM|GA HALL|Y|N|A)\b", re.I)
BUREAU = re.compile(r"\s*(?:\((?:VC|CH|RAPP?|CHAIR)\)|\bVC\b.*|VICE-?CHAIR(?:MAN)?|CHAIR(?:MAN|PERSON)?|RAPPORTEUR)\s*$", re.I)


def cells_of(line):
    """(name_x, code, name) per cell of a layout line; cells are 3+ spaces apart.

    Native sheets put 3 spaces between the vote letter and the name ("Y   ALBANIA"),
    so a lone Y/N/A token is the code of the next token on the line."""
    toks = [(m.start(), m.group(0)) for m in re.finditer(r"\S+(?:\s{1,2}\S+)*", line)]
    out, i = [], 0
    while i < len(toks):
        x, cell = toks[i]
        mm = re.match(r"^([YNAyna])\s+(.+)$", cell)
        if mm:
            out.append((x + len(cell) - len(mm.group(2)), mm.group(1).upper(), mm.group(2)))
        elif re.fullmatch(r"[YNAyna]", cell) and i + 1 < len(toks) and toks[i + 1][0] - x <= 6:
            out.append((toks[i + 1][0], cell.upper(), toks[i + 1][1]))
            i += 1
        else:
            out.append((x, "", cell))
        i += 1
    return out


def clean_name(name):
    name = BUREAU.sub("", name)
    name = re.sub(r"[^A-Za-z' .()\-]+", " ", name).strip(" .-")
    return name


def parse_sheet(path, match):
    txt = subprocess.run(["pdftotext", "-layout", str(path), "-"], capture_output=True, text=True).stdout
    lines = txt.splitlines()
    head = "\n".join(lines[:25])
    m = re.search(r"Vote Name:\s*(.*)\n((?:\s*\S.*\n){0,3})", head)
    vote_name = re.sub(r"\s+", " ", (m.group(1) + " " + m.group(2))).strip() if m else ""
    m = re.search(r"Subject:\s*(.+)", head)
    subject = m.group(1).strip() if m else ""
    date = ""
    m = re.search(r"Vote Time:\s*(\d{1,2})/(\d{1,2})/(\d{4})", head)
    if m:
        date = f"{m.group(3)}-{int(m.group(1)):02d}-{int(m.group(2)):02d}"
    else:
        m = re.search(r"Date\s*-?\s*Time:\s*(\d{1,2}\s+\w+\s+\d{4})", head)
        if m:
            try:
                date = datetime.strptime(m.group(1), "%d %B %Y").strftime("%Y-%m-%d")
            except ValueError:
                date = m.group(1)
    m = re.search(r"Yes\s+No\s+Abstain\s+(\d+)\s+(\d+)\s+(\d+)", txt)
    totals = tuple(int(x) for x in m.groups()) if m else None
    native = bool(re.search(r"Vote Time:", head))
    # column-aware walk: a long name wraps onto the next line in the same column
    # ("DEMOCRATIC PEOPLE'S" / "REPUBLIC OF KOREA"), so an unmatched cell is kept
    # pending per column and joined with the code-less cell below it.
    votes, unmatched, columns, pending = {}, [], [], {}
    for line in lines:
        if not re.search(r"[A-Z]{3}", line):
            continue
        for x, code, name in cells_of(line):
            name = clean_name(name)
            if len(name) < 3 or name.upper() != name or (NOISE.match(name) and not code):
                continue
            col = next((c for c in columns if abs(c - x) <= 6), None)
            if col is None:
                columns.append(x)
                col = x
            if not code and col in pending:
                pcode, pname, n_join = pending.pop(col)
                joined = f"{pname} {name}"
                iso = match(joined)
                if iso:
                    votes.setdefault(iso, (pcode, joined))
                elif n_join < 3:
                    pending[col] = (pcode, joined, n_join + 1)
                else:
                    unmatched.append(joined)
                continue
            if col in pending:
                unmatched.append(pending.pop(col)[1])
            iso = match(name)
            if iso:
                votes.setdefault(iso, (code, name))
            else:
                pending[col] = (code, name, 1)
    unmatched.extend(v[1] for v in pending.values())
    return vote_name, subject, date, totals, votes, native, unmatched


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--sessions", default="65-78")
    args = ap.parse_args()
    a, b = (int(x) for x in args.sessions.split("-"))
    match = Matcher(build_names())
    index = {(r["session"], r["file"]): r for r in csv.DictReader(open(RAW / "index.csv", encoding="utf-8"))}
    events, rows, unmatched = [], [], {}
    for session in range(a, b + 1):
        for path in sorted((RAW / str(session)).glob("*.pdf")) if (RAW / str(session)).exists() else []:
            meta = index.get((str(session), path.name), {})
            vote_name, subject, date, totals, votes, native, miss = parse_sheet(path, match)
            text = " ".join([vote_name, subject, meta.get("link_text", "")])
            sym = re.search(r"A/C\.3[./]\d+/L\.\d+(?:/Rev\.\d+)?", text.replace(" ", ""))
            symbol = re.sub(r"^A/C\.3\.", "A/C.3/", sym.group(0)) if sym else meta.get("symbol_hint", "")
            low = text.lower()
            kind = ("amendment" if "amendment" in low else "paragraph" if re.search(r"\bops?\b|\bpp\b|paragraph", low)
                    else "motion" if re.search(r"\bmotion\b|no[- ]action|adjourn|competence|division", low) else "draft")
            counts = {"Y": 0, "N": 0, "A": 0, "": 0}
            event_id = f"{session}-sheet-{path.stem}"
            for iso, (code, name) in votes.items():
                counts[code] += 1
                rows.append({"event_id": event_id, "session": session, "draft_symbol": symbol, "iso3": iso, "country": name, "vote": code or "."})
            for nm in miss:
                unmatched[nm] = unmatched.get(nm, 0) + 1
            seen = votes
            events.append({"event_id": event_id, "session": session, "file": path.name, "draft_symbol": symbol, "kind": kind,
                           "vote_name": vote_name[:160], "subject": subject[:160], "date": date, "native": int(native),
                           "n_yes": counts["Y"], "n_no": counts["N"], "n_abstain": counts["A"], "n_absent": counts[""],
                           "stated_yes": totals[0] if totals else "", "stated_no": totals[1] if totals else "", "stated_abstain": totals[2] if totals else "",
                           "totals_match": int(bool(totals) and totals == (counts["Y"], counts["N"], counts["A"])),
                           "n_states": len(seen), "n_unmatched": len(miss)})
    OUT.mkdir(parents=True, exist_ok=True)
    with open(OUT / "ga_sheet_events.csv", "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(events[0].keys())); w.writeheader(); w.writerows(events)
    with open(OUT / "ga_sheet_votes.csv", "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=["event_id", "session", "draft_symbol", "iso3", "country", "vote"]); w.writeheader(); w.writerows(rows)
    nat = [e for e in events if e["native"]]
    with_tot = [e for e in events if e["stated_yes"] != ""]
    print(f"[sheets] {len(events)} sheets ({len(nat)} native e-voting, {len(events) - len(nat)} scans), {len(rows)} State cells; "
          f"printed totals on {len(with_tot)}, matching the parsed counts on {sum(e['totals_match'] for e in with_tot)}; unmatched names {sum(unmatched.values())}")
    for nm, n in sorted(unmatched.items(), key=lambda x: -x[1])[:20]:
        print(f"      unmatched: {nm!r} × {n}")
    for s in sorted({e["session"] for e in events}):
        es = [e for e in events if e["session"] == s]
        print(f"      session {s}: {len(es)} sheets, native {sum(e['native'] for e in es)}, States/sheet median {sorted(e['n_states'] for e in es)[len(es)//2]}, "
              f"totals match {sum(e['totals_match'] for e in es)}/{sum(1 for e in es if e['stated_yes'] != '')}")


if __name__ == "__main__":
    main()
