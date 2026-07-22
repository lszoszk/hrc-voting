"""Build the client-side full-text search index over harvested resolution texts.

Sources (whatever exists):
  data/ap_mirror/   (mirror_log.csv)  — CHR 1993-2005 .doc + HRC s1-11 .pdf
  data/ods_texts/   (ods_log.csv)     — HRC s12+ .pdf from documents.un.org

Pipeline: extract (textutil / pdftotext, cached in data/text_cache/) → clean page
furniture → re-flow paragraphs → segment into preambular/operative clauses →
tokenize → emit into dashboard/texts/:
  catalog.json        [[sym,id,year,body,vt,am,subj,title], ...]   (docId = position)
  docs-<year>.json    {sym: [["PP1"|"OP3", clause-text], ...]}     (snippet bundles)
  idx/<c>.json        {token: [docId, ...]}                        (posting shards, c = first char)

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
    r"Distr\.|GENERAL|LIMITED|RESTRICTED|Original ?:|ORIGINAL ?:|GE\.[\d-]|A/HRC/|E/CN\.4/|"
    r"page \d+|Page \d+|\d{1,3}|[A-Z]$|Human Rights Council$|Commission on Human Rights$|"
    r".{0,4}session$|Agenda item|RES/|Dec\.|POINT)")

BODY_START = re.compile(r"^\s*(\"?The (Human Rights Council|Commission on Human Rights|General Assembly))[ ,]*$", re.I)
OP_NUM = re.compile(r"^\s*(\d{1,2})\.\s+\S")

def is_amendment(title, draft):
    return bool(re.search(r":\s*amendment", title or "", re.I) or
                re.match(r"\s*amendment", draft or "", re.I))

def extract(path: Path) -> str:
    if path.suffix == ".doc":
        r = subprocess.run(["textutil", "-convert", "txt", "-stdout", str(path)],
                           capture_output=True, timeout=60)
        return r.stdout.decode("utf-8", "replace")
    r = subprocess.run(["pdftotext", "-enc", "UTF-8", str(path), "-"],
                       capture_output=True, timeout=60)
    return r.stdout.decode("utf-8", "replace")

def get_text(sym: str, path: Path) -> str:
    safe = re.sub(r"[^A-Za-z0-9._-]", "_", sym) + ".txt"
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
    """Re-flow hard-wrapped lines into paragraphs; drop page furniture."""
    out, cur = [], []
    for ln in raw.split("\n"):
        s = ln.strip().lstrip("﻿\x0c")
        if not s:
            if cur:
                out.append(" ".join(cur)); cur = []
            continue
        if FURNITURE.match(s) and not cur:
            continue
        # a new numbered operative para starts its own block even without a blank line
        if cur and OP_NUM.match(s):
            out.append(" ".join(cur)); cur = []
        cur.append(s)
    if cur:
        out.append(" ".join(cur))
    return [re.sub(r"\s+", " ", p).strip() for p in out if len(p.strip()) >= 25]

def segment(paras):
    """Return (title, clauses[[label,text]]) — split at the body-opening formula."""
    title, clauses, in_body, pp, op = "", [], False, 0, 0
    for p in paras:
        if not in_body and BODY_START.match(p):
            in_body = True
            continue
        if not in_body and re.match(r'^[\"\u201c]?At its .{0,60}meeting', p):
            in_body = True          # decision style: "At its Nth meeting, ... decided ..."
        elif not in_body:
            if not title and not p.isupper() and 20 < len(p) < 220:
                title = p
            # the opening formula is often glued to the first clause
            m = re.match(r"^\"?The (?:Human Rights Council|Commission on Human Rights)\s*,\s*(.+)$", p)
            if m:
                in_body = True
                p = m.group(1).strip()
                if len(p) < 25:
                    continue
            else:
                continue
        m = OP_NUM.match(p)
        if m:
            op = int(m.group(1))
            clauses.append([f"OP{op}", p])
        else:
            pp += 1
            clauses.append([f"PP{pp}", p])
    if not clauses:
        # fallback (amendments/PRST etc. carry no opening formula): index the
        # paragraphs themselves, minus obvious session-header blocks
        def header(x):
            letters = [c for c in x if c.isalpha()]
            up = sum(1 for c in letters if c.isupper()) / max(len(letters), 1)
            return up > 0.6 or re.search(r"session Agenda item", x, re.I)
        body = [x for x in paras if not header(x)]
        clauses = [[f"P{i+1}", x] for i, x in enumerate(body)]
        if not title:
            title = next((x for x in body if 20 < len(x) < 220), "")
    return title, clauses

def tokens(text: str):
    t = unicodedata.normalize("NFKD", text.lower())
    return {w for w in re.findall(r"[a-z0-9]{2,}", t) if w not in STOP}

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

    catalog, bundles, post = [], defaultdict(dict), defaultdict(set)
    skipped = 0
    for sym, path in sorted(docs, key=lambda d: (meta[d[0]]["year"], d[0])):
        m = meta[sym]
        raw = get_text(sym, path)
        if len(raw) < 200:
            skipped += 1; continue
        title, clauses = segment(paragraphs(raw))
        if not clauses:
            skipped += 1; continue
        year = int(m["year"]) if m["year"].isdigit() else None
        did = len(catalog)
        catalog.append([sym, m["record_id"], year,
                        "HRC" if "Council" in m["body"] else "CHR",
                        VT.get(m["vote_type"], "O"),
                        1 if is_amendment(m["title"], m.get("draft", "")) else 0,
                        m["agenda_subject"].strip(),
                        title or m["title"].split(" : ")[0][:180]])
        bundles[year][sym] = clauses
        toks = tokens(title + " " + " ".join(c[1] for c in clauses))
        for w in toks:
            post[w].add(did)
    print(f"indexed: {len(catalog)} docs · skipped {skipped} (empty/unparsable) · vocabulary {len(post)}")

    (OUTDIR / "catalog.json").write_text(json.dumps(
        {"v": 1, "n": len(catalog), "docs": catalog}, separators=(",", ":"),
        ensure_ascii=False), encoding="utf-8")
    for year, b in bundles.items():
        (OUTDIR / f"docs-{year}.json").write_text(
            json.dumps(b, separators=(",", ":"), ensure_ascii=False), encoding="utf-8")
    shards = defaultdict(dict)
    for w, ids in post.items():
        c = w[0] if w[0].isalpha() else "0"
        shards[c][w] = sorted(ids)
    for c, d in shards.items():
        (OUTDIR / "idx" / f"{c}.json").write_text(
            json.dumps(d, separators=(",", ":")), encoding="utf-8")
    total = sum(f.stat().st_size for f in OUTDIR.rglob("*.json")) / 1024 / 1024
    print(f"wrote dashboard/texts/: catalog + {len(bundles)} year bundles + {len(shards)} shards = {total:.1f} MB")

if __name__ == "__main__":
    main()
