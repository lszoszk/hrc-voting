"""Build the client-side full-text search index over harvested resolution texts.

Sources (whatever exists):
  data/ap_mirror/   (mirror_log.csv)  — CHR 1993-2005 .doc + HRC s1-11 .pdf
  data/ods_texts/   (ods_log.csv)     — HRC s12+ .pdf from documents.un.org

Pipeline: extract (textutil / pdftotext -layout, cached in data/text_cache/) → clean
page furniture → re-flow paragraphs → segment into preambular/operative clauses →
tokenize (with term frequency) → emit into dashboard/texts/:
  catalog.json        [[sym,id,year,body,vt,am,subj,title], ...]   (docId = position)
  docs-<year>.json    {sym: [["PP1"|"OP3", clause-text], ...]}     (snippet bundles)
  idx/<c>.json        {token: [[docId, tf], ...]}                  (posting shards)

Zero runtime dependencies: the dashboard fetches shards lazily and intersects
posting lists client-side. Re-run any time; extraction is cached by symbol.
"""
import csv, json, re, subprocess, sys, unicodedata
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CACHE = ROOT / "data" / "text_cache"
CACHE.mkdir(parents=True, exist_ok=True)
OUTDIR = ROOT / "dashboard" / "texts"
(OUTDIR / "idx").mkdir(parents=True, exist_ok=True)

STOP = set("""the of and to in a for on that by with its as at or be is are was were it this
their his her they them from which shall will would should may can could an all any such
other than into upon under between within without also been being have has had do does
not no nor so if but we our us these those there where when who whom whose what how
""".split())

VT = {"ADOPTED WITHOUT VOTE": "C", "RECORDED": "V", "NON-RECORDED": "NR",
      "NON-RECORDED, adopted unanimously": "NRU", "WITHDRAWN": "WD", "NOT CONSIDERED": "NC",
      "NON-RECORDED, no voting information available": "NRX",
      "RECORDED, adopted at a closed meeting": "VC"}

FURNITURE = re.compile(
    r"^(UNITED NATIONS|United Nations|General Assembly|Economic and Social Council|"
    r"Distr\.|GENERAL|LIMITED|RESTRICTED|Original ?:|ORIGINAL ?:|GE\.\d|A/HRC[/ ]|E/CN\.?4|"
    r"page \d+|Page \d+|\d{1,3}\s*$|[A-Z]$|Human Rights Council\s*$|Commission on Human Rights\s*$|"
    r".{0,7}session\s*$|Agenda item|RES/|Dec\.|Resolution \d|Decision \d|Annex\b|"
    r"(?:Human Rights Council|Commission on Human Rights) \S+ session|"   # ODS masthead line
    r"\d{1,2} A/HRC)", re.I)                                              # page-foot footnote ref

BODY_START = re.compile(r"^[\"“]?The (Human Rights Council|Commission on Human Rights|General Assembly)\s*,?\s*", re.I)
DECISION_START = re.compile(r"^[\"“]?At its .{0,60}meeting", re.I)
OP_NUM = re.compile(r"^(\d{1,2})\.\s+(.+)", re.S)          # "1. Decides ..."
SUBITEM = re.compile(r"\s+(?=\([a-z]{1,3}\)\s)")           # split before "(a) ", "(ii) "
# standard UN preambular clause openers (present participles / set phrases)
PSTART = (r"Reaffirm\w*|Recall\w*|Reiterat\w*|Recogni[sz]\w*|Welcom\w*|Consider\w*|"
          r"Bearing in mind|Having (?:regard|considered|examined|reviewed|decided|adopted)|"
          r"Emphasi[sz]\w*|Stress\w*|Underlin\w*|Underscor\w*|Aware|Convinced|Concerned|"
          r"Deeply \w+|Gravely \w+|Seriously \w+|Mindful|Guided \w+|Acknowledg\w*|Affirm\w*|"
          r"Alarmed|Appalled|Believing|Commend\w*|Conscious|Deplor\w*|Determin\w*|Encourag\w*|"
          r"Express\w*|Taking (?:note|into account)|Urg\w*|Desirous|Being \w+|Noting|Observing|"
          r"Fully \w+|Further \w+|Remaining \w+|Cognizant|Anxious|Endorsing")
PSPLIT = re.compile(r"(?<=[,;])\s+(?=(?:" + PSTART + r")\b)")

def is_amendment(title, draft):
    return bool(re.search(r":\s*amendment", title or "", re.I) or
                re.match(r"\s*amendment", draft or "", re.I))

def extract(path: Path) -> str:
    if path.suffix == ".doc":
        r = subprocess.run(["textutil", "-convert", "txt", "-stdout", str(path)],
                           capture_output=True, timeout=60)
        return r.stdout.decode("utf-8", "replace")
    # -layout keeps the indented clause structure of these single-column UN PDFs:
    # blank lines between preambular clauses, and "1. Decides ..." stays on one line
    r = subprocess.run(["pdftotext", "-layout", "-nopgbrk", "-enc", "UTF-8", str(path), "-"],
                       capture_output=True, timeout=60)
    return r.stdout.decode("utf-8", "replace")

def get_text(sym: str, path: Path) -> str:
    # ".L" cache key for the -layout PDF extraction (the .doc cache stays reusable)
    tag = ".L" if path.suffix != ".doc" else ""
    safe = re.sub(r"[^A-Za-z0-9._-]", "_", sym) + tag + ".txt"
    c = CACHE / safe
    if c.exists():
        return c.read_text(encoding="utf-8")
    try:
        t = extract(path)
    except Exception:
        t = ""
    c.write_text(t, encoding="utf-8")
    return t

def paragraphs(raw: str):
    """Group blank-line-separated blocks, re-flowing hard-wrapped lines within each."""
    out, cur = [], []
    for ln in raw.split("\n"):
        s = ln.strip().lstrip("﻿\x0c")
        if not s:
            if cur:
                out.append(" ".join(cur)); cur = []
            continue
        cur.append(s)
    if cur:
        out.append(" ".join(cur))
    res = []
    for p in out:
        p = re.sub(r"\s+", " ", p).strip()
        if len(p) >= 12 and not FURNITURE.match(p):
            res.append(p)
    return res

def split_clauses(p):
    """Split one reflowed paragraph into clauses (used only by the PRST/amendment
    fallback, where there is no opening formula to anchor on)."""
    parts = PSPLIT.split(p) if len(p) > 260 else [p]
    out = []
    for part in parts:
        out.extend(s.strip() for s in SUBITEM.split(part) if len(s.strip()) >= 8)
    return out or [p]

PSTART_RE = re.compile(r"^(?:" + PSTART + r")\b")
OP_LINE = re.compile(r"^(\d{1,2})\.\s+\S")
SUB_LINE = re.compile(r"^\(([a-z]{1,3})\)\s")

def segment(raw):
    """Line-based clause segmentation: split on structural markers (operative 'N.',
    sub-item '(x)', preambular participle openers) rather than on blank lines, which
    are unreliable across the varied UN PDF templates. Continuation lines are joined;
    furniture lines are skipped without breaking a clause across a page boundary.
    Returns ("", clauses) — the catalogue title (MARC 245) is used downstream."""
    clauses, cur, label, in_body, op, pp = [], [], None, False, 0, 0

    def flush():
        nonlocal cur, label
        if cur and label:
            t = re.sub(r"\s+", " ", " ".join(cur)).strip()
            if len(t) >= 8 and not FURNITURE.match(t):
                clauses.append([label, t])
        cur, label = [], None

    for raw_ln in raw.split("\n"):
        s = raw_ln.strip().lstrip("﻿\x0c")
        if not s:
            continue
        if FURNITURE.match(s):
            continue                              # drop furniture; keep clause intact
        if not in_body:
            m = BODY_START.match(s)
            if m:
                in_body = True
                s = s[m.end():].strip(' ,"“')
                if len(s) < 3:
                    continue
            elif DECISION_START.match(s):
                in_body = True; label = "P1"; cur = [s]; continue
            else:
                continue                          # skip masthead / pre-body furniture
        mnum, msub = OP_LINE.match(s), SUB_LINE.match(s)
        if mnum:
            flush(); op = int(mnum.group(1)); label = f"OP{op}"; cur = [s]
        elif msub and op:
            flush(); label = f"OP{op}({msub.group(1)})"; cur = [s]
        elif op == 0 and PSTART_RE.match(s):
            flush(); pp += 1; label = f"PP{pp}"; cur = [s]
        else:
            if label is None:
                pp += 1; label = f"PP{pp}"
            cur.append(s)
    flush()

    if not clauses:                               # PRST / amendments: no opening formula
        def header(x):
            letters = [ch for ch in x if ch.isalpha()]
            return (sum(1 for ch in letters if ch.isupper()) / max(len(letters), 1) > 0.6
                    or re.search(r"session Agenda item", x, re.I))
        body = [x for p in paragraphs(raw) if not header(p) for x in split_clauses(p)]
        clauses = [[f"P{i+1}", x] for i, x in enumerate(body)]
    return "", clauses

def token_counts(text: str):
    t = unicodedata.normalize("NFKD", text.lower())
    from collections import Counter
    return Counter(w for w in re.findall(r"[a-z0-9]{2,}", t) if w not in STOP)

def main():
    meta = {r["symbol"]: r for r in csv.DictReader(
        open(ROOT / "data/csv/resolutions.csv", encoding="utf-8"))}
    sources = []
    for logf, base in [(ROOT / "data/ap_mirror/mirror_log.csv", ROOT / "data/ap_mirror"),
                       (ROOT / "data/ods_texts/ods_log.csv", ROOT / "data/ods_texts")]:
        if logf.exists():
            for r in csv.reader(open(logf, encoding="utf-8")):
                if r and r[1] == "ok" and (base / r[2]).exists():
                    sources.append((r[0], base / r[2]))
    # de-dup (mirror wins), keep only catalogued symbols
    seen, docs = set(), []
    for sym, path in sources:
        if sym in seen or sym not in meta:
            continue
        seen.add(sym); docs.append((sym, path))
    print(f"texts on disk: {len(docs)}")

    catalog, bundles, post = [], defaultdict(dict), defaultdict(dict)
    skipped = 0
    for sym, path in sorted(docs, key=lambda d: (meta[d[0]]["year"], d[0])):
        m = meta[sym]
        raw = get_text(sym, path)
        if len(raw) < 200:
            skipped += 1; continue
        title, clauses = segment(raw)
        title = title or m["title"].split(" : ")[0][:180]
        if not clauses:
            skipped += 1; continue
        year = int(m["year"]) if m["year"].isdigit() else None
        did = len(catalog)
        catalog.append([sym, m["record_id"], year,
                        "HRC" if "Council" in m["body"] else "CHR",
                        VT.get(m["vote_type"], "O"),
                        1 if is_amendment(m["title"], m.get("draft", "")) else 0,
                        m["agenda_subject"].strip(),
                        title])
        bundles[year][sym] = clauses
        for w, n in token_counts(title + " " + " ".join(c[1] for c in clauses)).items():
            post[w][did] = min(n, 30)          # tf capped — enough for idf*log(1+tf)
    print(f"indexed: {len(catalog)} docs · skipped {skipped} (empty/unparsable) · vocabulary {len(post)}")

    (OUTDIR / "catalog.json").write_text(json.dumps(
        {"v": 1, "n": len(catalog), "docs": catalog}, separators=(",", ":"),
        ensure_ascii=False), encoding="utf-8")
    for year, b in bundles.items():
        (OUTDIR / f"docs-{year}.json").write_text(
            json.dumps(b, separators=(",", ":"), ensure_ascii=False), encoding="utf-8")
    shards = defaultdict(dict)
    for w, m in post.items():
        c = w[0] if w[0].isalpha() else "0"
        shards[c][w] = sorted(m.items())       # [[docId, tf], ...]
    for c, d in shards.items():
        (OUTDIR / "idx" / f"{c}.json").write_text(
            json.dumps(d, separators=(",", ":")), encoding="utf-8")
    total = sum(f.stat().st_size for f in OUTDIR.rglob("*.json")) / 1024 / 1024
    print(f"wrote dashboard/texts/: catalog + {len(bundles)} year bundles + {len(shards)} shards = {total:.1f} MB")

if __name__ == "__main__":
    main()
