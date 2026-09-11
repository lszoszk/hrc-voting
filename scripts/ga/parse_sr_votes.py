"""Committee-stage recorded votes from Third Committee summary records.

Reads data/raw/ga/sr/<session>/SR.<n>.{docx,doc} (harvest_sr.py), extracts every
"A recorded vote was taken on …" block with its "In favour / Against /
Abstaining" lists and the result sentence, maps State names to ISO3 through the
names in the UN Digital Library voting file, and writes:

  data/csv/ga_committee_events.csv  one row per vote event (draft, amendment,
                                    paragraph, motion) with parsed and stated totals
  data/csv/ga_committee_votes.csv   one row per (event, State) vote

.doc records are converted with macOS textutil (cached as .txt next to the file).
Usage: python3 scripts/ga/parse_sr_votes.py [--sessions 55-80]
"""
import argparse
import collections
import csv
import glob
import re
import subprocess
import unicodedata
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
RAW = ROOT / "data" / "raw" / "ga" / "sr"
OUT = ROOT / "data" / "csv"
csv.field_size_limit(10 ** 9)

NUM_WORDS = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10}
# "A recorded vote was taken on draft resolution X." — or, in older records, just "A recorded vote was taken."
TAKEN_RE = re.compile(r"(?:recorded\s+)?vote\s+(?:was|had\s+been)\s+taken(?:\s+by\s+roll[- ]call)?(?:\s+on\s+(?P<subject>.{0,320}?))?\.?\s*\n", re.S | re.I)
LIST_HEAD_RE = re.compile(r"^\s*(In favour|Against|Abstaining|Abstentions)\s*:\s*(.*)$", re.I)
LIST_END_RE = re.compile(r"^\s*(?:\d+\.\s|Draft resolution|The draft|The amendment|The motion|The proposal|Operative|Paragraph|Mr\.|Ms\.|Mrs\.)", re.I)


def vote_blocks(t):
    """Yield (subject, {Y,N,A: text}, tail) for each recorded vote with roll-call lists.

    The lists are read line by line: a block ends at the next numbered paragraph,
    footnote, or result sentence — so a vote with no "Abstaining:" section cannot
    swallow the following vote's lists.
    """
    for m in TAKEN_RE.finditer(t):
        subject = re.sub(r"\s+", " ", m.group("subject") or "").strip()
        lines = t[m.end():].split("\n")
        lists = {"Y": [], "N": [], "A": []}
        cur, started, tail_at = None, False, len(lines)
        for i, line in enumerate(lines):
            h = LIST_HEAD_RE.match(line)
            if h:
                cur = {"in favour": "Y", "against": "N", "abstaining": "A", "abstentions": "A"}[h.group(1).lower()]
                started = True
                if h.group(2).strip():
                    lists[cur].append(h.group(2))
                continue
            if not line.strip() or (started and re.match(r"^\s*\*\s", line)):
                continue
            if started and (LIST_END_RE.match(line) or re.search(r"recorded\s+vote", line, re.I)):
                tail_at = i
                break
            if cur is not None:
                lists[cur].append(line)
            elif i > 3:
                break
        if not started:
            continue
        tail = "\n".join(lines[tail_at:tail_at + 20])[:2400]
        texts = {k: " ".join(v) for k, v in lists.items()}
        # some records glue the result sentence onto the last list line:
        # "..., Zambia. Draft amendment A/C.3/67/L.66 was rejected by 85 votes to 55"
        for k, v in texts.items():
            glued = re.search(r"\.\s*(?:Abstentions|Abstaining)\s*:\s*", v)
            if glued and k != "A" and not texts["A"]:
                texts[k], texts["A"] = v[:glued.start() + 1], v[glued.end():]
                v = texts[k]
            cut = re.search(r"\.\s+(?=(?:Draft|The|Proposed|Operative|Paragraph)\b)", v)
            if cut:
                texts[k], tail = v[:cut.start() + 1], v[cut.end():] + "\n" + tail
        nxt = re.search(r"recorded\s+vote\s+(?:was|had\s+been)\s+taken", tail, re.I)
        # the draft under discussion, for paragraph/amendment votes whose subject names none
        before = t[max(0, m.start() - 6000):m.start()]
        ctx = SYMBOL_RE.findall(before)
        yield subject, texts, tail[:nxt.start()] if nxt else tail, (ctx[-1] if ctx else "")


RESULT_RE = re.compile(
    r"(?:was|were)\s+(?P<result>adopted|rejected|retained|approved|not\s+adopted)(?:\s+as\s+(?:orally\s+)?(?:amended|revised))?\s+by\s+(?P<y>\d+)\s+(?:votes?\s+)?to\s+(?P<n>\d+|none|one)"
    r"(?:,?\s*with\s+(?P<a>\d+|no|one|two|three|four|five|six|seven|eight|nine|ten)\s+abstentions?)?", re.I)
# "was adopted by 140 votes in favour, 2 against and 1 abstention"
RESULT2_RE = re.compile(
    r"(?:was|were)\s+(?P<result>adopted|rejected|retained|approved|not\s+adopted)\s+by\s+(?P<y>\d+)\s+votes?\s+in\s+favour,?\s+(?P<n>\d+|none)\s+against"
    r"(?:,?\s*(?:and|with)\s+(?P<a>\d+|no|one|two|three|four|five|six|seven|eight|nine|ten)\s+abstentions?)?", re.I)
SYMBOL_RE = re.compile(r"A/C\.3/\d{2,3}/L\.\d+(?:/Rev\.\d+)?", re.I)
HEAD_MEETING_RE = re.compile(r"Summary record of the (\d+)(?:st|nd|rd|th) meeting", re.I)
HEAD_DATE_RE = re.compile(r"on\s+\w+day,\s+(\d{1,2}\s+\w+\s+\d{4})", re.I)


def norm(name):
    # apostrophes and no-break spaces first: the ASCII fold below would drop them
    s = name.replace("’", "'").replace("\u00a0", " ")
    s = unicodedata.normalize("NFD", s).encode("ascii", "ignore").decode().lower()
    s = re.sub(r"[^a-z0-9 ]+", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def build_name_map():
    """Every spelling in the UNDL voting file → ISO3, plus the CHR/HRC file's names."""
    m = {}
    src = sorted(glob.glob(str(ROOT / "data" / "raw" / "ga" / "*_ga_voting.csv")))
    if src:
        seen = set()
        with open(src[-1], newline="", encoding="utf-8-sig") as fh:
            for row in csv.DictReader(fh):
                key = (row["ms_code"], row["ms_name"])
                if key in seen:
                    continue
                seen.add(key)
                m.setdefault(norm(row["ms_name"]), row["ms_code"])
                bare = norm(re.sub(r"\s*\(.*?\)", "", row["ms_name"]))
                m.setdefault(bare, row["ms_code"])
    for row in csv.DictReader(open(ROOT / "data" / "csv" / "votes_long.csv", encoding="utf-8")):
        if row["iso3"] and row["country"]:
            m.setdefault(norm(row["country"]), row["iso3"])
    # spellings the summary records use that the voting file does not
    m.update({
        "turkiye": "TUR", "turkey": "TUR", "czechia": "CZE", "eswatini": "SWZ", "north macedonia": "MKD",
        "cabo verde": "CPV", "cote d ivoire": "CIV", "viet nam": "VNM", "netherlands kingdom of the": "NLD",
        "netherlands": "NLD", "bolivia plurinational state of": "BOL", "iran islamic republic of": "IRN",
        "venezuela bolivarian republic of": "VEN", "micronesia federated states of": "FSM",
        "democratic people s republic of korea": "PRK", "lao people s democratic republic": "LAO",
        "united republic of tanzania": "TZA", "republic of moldova": "MDA", "syrian arab republic": "SYR",
        "united kingdom of great britain and northern ireland": "GBR", "united kingdom": "GBR",
        "united states of america": "USA", "united states": "USA", "russian federation": "RUS",
        "libya": "LBY", "libyan arab jamahiriya": "LBY", "sao tome and principe": "STP", "timor leste": "TLS",
        "brunei darussalam": "BRN", "the former yugoslav republic of macedonia": "MKD", "swaziland": "SWZ",
        "cape verde": "CPV", "serbia and montenegro": "SCG", "yugoslavia": "YUG", "zaire": "ZAR",
        "myanmar": "MMR", "burma": "MMR", "congo": "COG", "democratic republic of the congo": "COD",
        "saint kitts and nevis": "KNA", "saint lucia": "LCA", "saint vincent and the grenadines": "VCT",
        "state of palestine": "PSE", "holy see": "VAT",
        # older records: hyphenated / translated / abbreviated spellings
        "bosnia herzegovina": "BIH", "vietnam": "VNM", "palaos": "PLW", "saint marin": "SMR", "santa lucia": "LCA",
        "islamic republic of iran": "IRN", "st kitts and nevis": "KNA", "st lucia": "LCA", "st vincent and the grenadines": "VCT",
        "former yugoslav republic of macedonia": "MKD", "the former republic of macedonia": "MKD",
        "lao peoples democratic republic": "LAO", "republic of korea": "KOR", "democratic republic of congo": "COD",
        "federated states of micronesia": "FSM", "in dora": "AND", "antigua in barbuda": "ATG", "omar": "OMN",
        "moldova": "MDA", "korea democratic people s republic of": "PRK", "korea republic of": "KOR",
        "tanzania united republic of": "TZA", "macedonia the former yugoslav republic of": "MKD",
        "democratic republic of korea": "PRK", "costa rice": "CRI",
        "bolivarian republic of venezuela": "VEN", "lichtenstein": "LIE",
        "plurinational state of bolivia": "BOL", "guineabissau": "GNB", "timorleste": "TLS", "cyrus": "CYP",
    })
    return m


def text_of(path):
    return clean(raw_text_of(path))


def clean(x):
    # no-break spaces and Unicode line/paragraph separators would hide the list
    # headers ("In\xa0favour:\u2028Andorra, ..."); footnote bodies are glued to the
    # list line after a tab-digit-tab marker, and some .doc conversions leave
    # "-10795-12700" style artefacts.
    x = x.replace("\xa0", " ").replace("\u2028", "\n").replace("\u2029", "\n")
    x = re.sub(r"\t\d{1,2}\t[^\n]*", "", x)
    x = re.sub(r"\s-?\d{3,6}-\d{4,6}\b", "", x)
    return x


def raw_text_of(path):
    if path.suffix == ".docx":
        x = zipfile.ZipFile(path).read("word/document.xml").decode("utf-8", "replace")
        x = re.sub(r"<w:tab/>", "\t", x)
        x = re.sub(r"</w:p>", "\n", x)
        x = re.sub(r"<[^>]+>", "", x)
        return x.replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">")
    cache = path.with_suffix(".txt")
    if not cache.exists():
        subprocess.run(["textutil", "-convert", "txt", "-output", str(cache), str(path)], check=True, capture_output=True)
    return cache.read_text(encoding="utf-8", errors="replace")


def split_names(block, name_map):
    names = []
    for part in re.split(r",\s*", block.replace("\n", " ")):
        part = part.strip(" .;:\t")
        if not part or part.lower() == "none":
            continue
        if name_map.get(norm(part)) or name_map.get(norm(re.sub(r"\s*\(.*?\)", "", part))):
            names.append(part)
            continue
        # "X and Y" (last pair of a list) or a lost comma ("Suriname Swaziland")
        part = re.sub(r"^(?:the|and)\s+", "", part, flags=re.I)
        if name_map.get(norm(part)):
            names.append(part)
            continue
        split_ok = False
        for mm in reversed(list(re.finditer(r"\s+and\s+", part))):
            halves = [part[:mm.start()], part[mm.end():]]
            if all(name_map.get(norm(h)) for h in halves):
                names.extend(halves)
                split_ok = True
                break
        if split_ok:
            continue
        words = part.split()
        for i in range(1, len(words)):
            a, b = " ".join(words[:i]), " ".join(words[i:])
            if name_map.get(norm(a)) and name_map.get(norm(b)):
                names.extend([a, b])
                break
        else:
            names.append(part)
    return names


def classify(subject):
    s = subject.lower()
    if not s:
        return "unknown"
    if "amendment" in s:
        return "amendment"
    if re.search(r"paragraph|operative|preambular|preamble|\bline\b|\bwords?\b|\bphrase\b", s):
        return "paragraph"
    if re.search(r"motion|proposal|no action|no-action|appeal|ruling|adjourn|division|competence|closure", s):
        return "motion"
    return "draft"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--sessions", default="55-80")
    args = ap.parse_args()
    a, b = (int(x) for x in args.sessions.split("-"))
    name_map = build_name_map()
    events, votes, unmapped = [], [], collections.Counter()
    for session in range(a, b + 1):
        for path in sorted((RAW / str(session)).glob("SR.*"), key=lambda p: int(re.search(r"SR\.(\d+)", p.name).group(1))) if (RAW / str(session)).exists() else []:
            if path.suffix not in (".docx", ".doc"):
                continue
            t = text_of(path)
            mno = HEAD_MEETING_RE.search(t)
            mdate = HEAD_DATE_RE.search(t[:3000])
            meeting_no = mno.group(1) if mno else re.search(r"SR\.(\d+)", path.name).group(1)
            sr_symbol = f"A/C.3/{session}/SR.{re.search(r'SR\.(\d+)', path.name).group(1)}"
            for k, (subject, blocks, tail, ctx_symbol) in enumerate(vote_blocks(t), 1):
                lists = {c: split_names(blocks[c], name_map) for c in ("Y", "N", "A")}
                res = RESULT_RE.search(tail) or RESULT2_RE.search(tail)
                if not subject and res:      # bare "A recorded vote was taken.": describe it by the result sentence
                    pre = tail[:res.start()].strip().split("\n")[-1]
                    subject = re.sub(r"^\d+\.\s*", "", pre).strip(" ,")
                sym = SYMBOL_RE.search(subject) or (SYMBOL_RE.search(tail[:res.start()]) if res else None)
                symbol_source = "subject" if sym else ("context" if ctx_symbol else "")
                symbol = sym.group(0) if sym else ctx_symbol
                if symbol and not symbol.startswith(f"A/C.3/{session}/"):
                    symbol = re.sub(r"^A/C\.3/\d+/", f"A/C.3/{session}/", symbol)
                    symbol_source = "corrected"
                stated = {"y": None, "n": None, "a": None, "result": ""}
                if res:
                    abst = res.group("a")
                    y, n = int(res.group("y")), {"none": 0, "one": 1}.get(res.group("n").lower(), None)
                    n = int(res.group("n")) if n is None else n
                    result = re.sub(r"\s+", " ", res.group("result").lower())
                    if result in ("rejected", "not adopted"):      # "rejected by 98 votes to 11": 98 against
                        y, n = n, y
                    stated = {"y": y, "n": n,
                              "a": (int(abst) if abst and abst.isdigit() else NUM_WORDS.get((abst or "").lower(), 0)),
                              "result": result}
                event_id = f"{session}-SR{meeting_no}-{k}"
                counts = {c: len(v) for c, v in lists.items()}
                events.append({
                    "event_id": event_id, "session": session, "sr_symbol": sr_symbol, "meeting_no": meeting_no,
                    "meeting_date": mdate.group(1) if mdate else "", "kind": classify(subject),
                    "draft_symbol": symbol, "symbol_source": symbol_source,
                    "as_amended": int(bool(re.search(r"as (?:orally )?(?:amended|revised)", subject, re.I))),
                    "subject": subject, "result": stated["result"],
                    "stated_yes": stated["y"], "stated_no": stated["n"], "stated_abstain": stated["a"],
                    "n_yes": counts["Y"], "n_no": counts["N"], "n_abstain": counts["A"],
                    "totals_match": int(stated["y"] is not None and (stated["y"], stated["n"], stated["a"]) == (counts["Y"], counts["N"], counts["A"])),
                })
                for code, names in lists.items():
                    for nm in names:
                        iso = name_map.get(norm(nm)) or name_map.get(norm(re.sub(r"\s*\(.*?\)", "", nm)))
                        if not iso:
                            unmapped[nm] += 1
                        votes.append({"event_id": event_id, "session": session, "draft_symbol": symbol,
                                      "iso3": iso or "", "country": nm, "vote": code})
    OUT.mkdir(parents=True, exist_ok=True)
    with open(OUT / "ga_committee_events.csv", "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(events[0].keys()) if events else ["event_id"]); w.writeheader(); w.writerows(events)
    with open(OUT / "ga_committee_votes.csv", "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=["event_id", "session", "draft_symbol", "iso3", "country", "vote"]); w.writeheader(); w.writerows(votes)
    kinds = collections.Counter(e["kind"] for e in events)
    matched = sum(e["totals_match"] for e in events)
    with_result = sum(1 for e in events if e["stated_yes"] is not None)
    print(f"[sr] {len(events)} vote events ({dict(kinds)}), {len(votes)} State votes; "
          f"stated totals present {with_result}, matching parsed lists {matched}; unmapped names {sum(unmapped.values())}")
    for nm, n in unmapped.most_common(15):
        print(f"      unmapped: {nm!r} × {n}")
    per_session = collections.Counter(e["session"] for e in events if e["kind"] == "draft")
    print("[sr] draft-resolution votes per session:", " ".join(f"{s}:{n}" for s, n in sorted(per_session.items())))


if __name__ == "__main__":
    main()
