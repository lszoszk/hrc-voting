"""Tag every clause-segmented resolution with UNITAR "Terms Used in Resolutions"
operative verbs and preambular openers, and report statistics + newly-used terms.

Reads dashboard/texts/{catalog.json, docs-*.json} (built by build_text_index.py).
Writes dashboard/texts/terms.json (per-doc verb tags + corpus aggregates) and prints
a stats report.  UNITAR reference: JG-1/02/10.
"""
import json, re, collections
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TX = ROOT / "dashboard" / "texts"

# ---- UNITAR controlled vocabulary (canonical heads) ----
OPERATIVE = [
    "Accepts", "Acknowledges", "Adopts", "Affirms", "Agrees", "Appeals", "Appoints",
    "Approves", "Authorizes", "Believes", "Calls the attention", "Calls attention",
    "Calls upon", "Commends", "Compliments", "Concurs", "Condemns", "Confirms",
    "Congratulates", "Considers", "Decides", "Declares", "Demands", "Denounces",
    "Deplores", "Designates", "Determines", "Dissolves", "Draws the attention", "Elects",
    "Emphasizes", "Empowers", "Endorses", "Entrusts", "Envisages", "Establishes",
    "Exhorts", "Expresses", "Extends", "Firmly supports", "Insists", "Instructs",
    "Invites the attention", "Invites", "Is of the opinion", "Looks forward",
    "Makes an urgent appeal", "Mandates", "Notes", "Pays tribute", "Proclaims",
    "Proposes", "Reaffirms", "Realizes", "Reasserts", "Recalls", "Recognizes",
    "Recommends", "Refers", "Regrets", "Reiterates", "Rejects", "Reminds", "Renews",
    "Requests", "Resolves", "Solemnly adopts", "Stresses", "Suggests", "Supports",
    "Takes note", "Transmits", "Trusts", "Underlines", "Urgently requests", "Urges",
    "Welcomes",
]
PREAMBLE = [
    "Acknowledging", "Acting", "Adhering", "Affirming", "Agreeing", "Alarmed",
    "Appreciating", "Aware", "Bearing in mind", "Believing", "Cognizant", "Concerned",
    "Concurring", "Condemning", "Conscious", "Considering", "Convinced", "Deploring",
    "Desirous", "Emphasizing", "Encouraged", "Expressing", "Faithful", "Fearing",
    "Fully aware", "Guided by", "Having considered", "Hopeful", "Indignant", "Inspired",
    "Keeping in mind", "Mindful", "Noting", "Persuaded", "Reaffirming", "Recalling",
    "Recognizing", "Regretting", "Reiterating", "Sharing the concern", "Stressing",
    "Striving", "Taking into account", "Taking into consideration", "Taking note",
    "Underlining", "Viewing with concern", "Welcoming", "Wishing",
]
# generic intensifiers/adverbs that precede a verb but are not part of a UNITAR entry
INTENS = ["strongly", "deeply", "gravely", "seriously", "vigorously", "categorically",
          "unequivocally", "emphatically", "resolutely", "also", "further", "again",
          "once again", "in this regard", "in particular"]

# ---- two-axis coding scheme (grounded: Abbott/Keohane/Moravcsik/Slaughter/Snidal 2000
# "Legalization" IO 54(3); Benson & Tucker 2022 JCR level-of-action + sentiment; Lebovic
# & Voeten 2006 ISQ shaming; Legal Response Intl verb gloss; UPR-Info action ladder).
# Axis 1 DIRECTIVE FORCE (dir 5..1, 0 = non-directive). Axis 2 VALENCE (val -2..+2, or
# None for pure directives). Within-tier order is author synthesis, not authoritative.
DIR = {5: ["Decides", "Demands", "Resolves", "Declares", "Determines", "Adopts",
           "Solemnly adopts", "Establishes", "Authorizes", "Elects", "Appoints",
           "Dissolves", "Designates", "Empowers", "Entrusts", "Proclaims", "Mandates",
           "Renews", "Extends"],
       4: ["Urges", "Calls upon", "Exhorts", "Appeals", "Calls for", "Insists",
           "Instructs", "Urgently requests", "Makes an urgent appeal", "Demands"],
       3: ["Requests", "Recommends"],
       2: ["Invites", "Encourages", "Suggests", "Proposes", "Envisages"]}
VAL = {2:  ["Commends", "Compliments", "Congratulates", "Pays tribute"],
       1:  ["Welcomes", "Appreciates", "Applauds", "Thanks", "Endorses", "Approves",
            "Accepts", "Supports", "Firmly supports", "Confirms"],
       0:  ["Notes", "Takes note", "Recalls", "Reaffirms", "Reasserts", "Reiterates",
            "Acknowledges", "Recognizes", "Affirms", "Stresses", "Emphasizes",
            "Underlines", "Underscores", "Highlights", "Considers", "Believes", "Agrees",
            "Concurs", "Trusts", "Is of the opinion", "Looks forward", "Transmits",
            "Refers", "Realizes", "Observes"],
       -1: ["Regrets", "Deplores", "Rejects", "Denounces"],
       -2: ["Condemns"]}
DIR_OF = {v: t for t, vs in DIR.items() for v in vs}
VAL_OF = {v: t for t, vs in VAL.items() for v in vs}
# "Expresses X" and "Notes with X" carry valence in the object, resolved per clause:
NEG_OBJ = re.compile(r"\b(concern|regret|indignation|dismay|alarm|disappoint|condemn)", re.I)
POS_OBJ = re.compile(r"\b(appreciation|satisfaction|solidarity|gratitude|confidence|support|hope)", re.I)
DELEG = re.compile(r"\b(secretary-general|high commissioner|ohchr|special rapporteur|"
                   r"independent expert|working group|commission of inquiry|fact-finding|"
                   r"to (?:report|submit|present|prepare|convene|establish|appoint)|"
                   r"the mandate|a panel|a report)", re.I)

def _byword(terms):
    # longest-first so "Calls upon" wins over a bare "Calls"
    return sorted((t.lower() for t in terms), key=lambda s: -len(s))

OP_L, PP_L = _byword(OPERATIVE), _byword(PREAMBLE)
CANON = {t.lower(): t for t in OPERATIVE} | {t.lower(): t for t in PREAMBLE}

def match(head, terms):
    """Longest controlled term that `head` (lowercased clause opening) begins with."""
    for t in terms:
        if head == t or head.startswith(t + " "):
            return t
    return None

def op_head(text):
    """Leading operative phrase of an OP clause: drop the 'N.' and any label prefix."""
    s = re.sub(r"^\(?[a-z0-9]{1,4}\)?[.)]\s*", "", text.strip(), flags=re.I)  # "1." / "(a)"
    return " ".join(re.findall(r"[A-Za-z']+", s)[:5]).lower()

def tag_operative(head):
    m = match(head, OP_L)
    if m:
        return CANON[m], None
    # try stripping one generic intensifier ("Strongly condemns", "Also requests")
    for a in sorted(INTENS, key=lambda s: -len(s)):
        if head.startswith(a + " "):
            m = match(head[len(a) + 1:], OP_L)
            if m:
                return CANON[m], a
    return None, None   # unrecognized

def tag_preamble(head):
    m = match(head, PP_L)
    return CANON[m] if m else None

NEWCANON = {"calls for": "Calls for", "encourages": "Encourages", "underscores": "Underscores",
            "appreciates": "Appreciates", "applauds": "Applauds", "thanks": "Thanks",
            "highlights": "Highlights", "observes": "Observes", "deplores": "Deplores",
            "regrets": "Regrets", "rejects": "Rejects", "denounces": "Denounces", "condemns": "Condemns"}
# extended operative vocabulary = UNITAR + the codeable "new" verbs (finding: Encourages)
OP_EXT = _byword(OPERATIVE + ["Encourages", "Calls for", "Underscores", "Appreciates",
                              "Applauds", "Thanks", "Highlights", "Observes", "Deplores",
                              "Regrets", "Rejects", "Denounces", "Condemns"])

def code_clause(text):
    """(verb, dir, val, deleg) for one operative clause under the two-axis scheme."""
    head = op_head(text)
    verb = match(head, OP_EXT)
    if not verb:
        for a in sorted(INTENS, key=lambda s: -len(s)):
            if head.startswith(a + " "):
                verb = match(head[len(a) + 1:], OP_EXT)
                if verb:
                    break
    if not verb:
        return None, 0, None, bool(DELEG.search(text))
    v = CANON.get(verb) or NEWCANON.get(verb) or verb.title()
    d = DIR_OF.get(v, 0)
    if v in ("Expresses", "Notes", "Takes note", "Recognizes"):
        val = -1 if NEG_OBJ.search(text) else (1 if POS_OBJ.search(text) else 0)
    else:
        val = None if d else VAL_OF.get(v, 0)
    return v, d, val, bool(DELEG.search(text))

def build_lang(cat, bundles):
    import statistics
    new_heads = collections.Counter(); intens = collections.Counter()
    UNITAR_L = set(OP_L)
    def track_new(text):
        head = op_head(text)
        if match(head, OP_L):
            return
        for a in sorted(INTENS, key=lambda s: -len(s)):
            if head.startswith(a + " "):
                m = match(head[len(a) + 1:], OP_L)
                if m:
                    intens[(CANON[m], a)] += 1; return
        w = head.split(" ")[0] if head else ""
        NEW_OK = {"encourages", "calls", "underscores", "appreciates", "applauds",
                  "thanks", "highlights", "continues", "remains", "deprecates"}
        if w in NEW_OK:
            new_heads["Calls for" if head.startswith("calls for") else w.title()] += 1
    yr = collections.defaultdict(lambda: {"body": "", "nres": 0, "nop": 0, "dirSum": 0,
        "dirN": 0, "valSum": 0, "valN": 0, "tier": collections.Counter(),
        "enc": 0, "cond": 0, "deleg": 0})
    subj = collections.defaultdict(lambda: {"n": 0, "dir": [], "val": [], "deleg": 0,
        "verbs": collections.Counter()})
    per_doc = []
    for d in cat:
        sym, rid, year, body, vt, am, subject, title = d
        if am or not year:
            continue                       # amendments are edit-instructions, not operative
        cls = bundles.get(year, {}).get(sym, [])
        dv, vv, ndeleg, nop = [], [], 0, 0
        y = yr[year]; y["body"] = body; y["nres"] += 1
        for label, text in cls:
            if not (label.startswith("OP") and "(" not in label):
                continue
            verb, dr, val, dg = code_clause(text); track_new(text)
            nop += 1; y["nop"] += 1
            if dr:
                dv.append(dr); y["dirSum"] += dr; y["dirN"] += 1; y["tier"][dr] += 1
                if verb in ("Encourages", "Invites", "Suggests", "Proposes"): y["enc"] += 1
            if val is not None:
                vv.append(val); y["valSum"] += val; y["valN"] += 1
                if val <= -2: y["cond"] += 1
            if dg: ndeleg += 1; y["deleg"] += 1
            if verb: subj[subject]["verbs"][verb] += 1
        if subject:
            s = subj[subject]; s["n"] += 1
            if dv: s["dir"].append(statistics.mean(dv))
            if vv: s["val"].append(statistics.mean(vv))
            s["deleg"] += (ndeleg / nop if nop else 0)
        if nop:
            per_doc.append([sym, year, round(statistics.mean(dv), 2) if dv else None,
                            round(statistics.mean(vv), 2) if vv else None,
                            round(ndeleg / nop, 2)])
    byYear = []
    for y in sorted(yr):
        o = yr[y]
        if o["nop"] < 5:
            continue
        byYear.append({"y": y, "body": o["body"], "nres": o["nres"], "nop": o["nop"],
            "dir": round(o["dirSum"] / o["dirN"], 3) if o["dirN"] else None,
            "val": round(o["valSum"] / o["valN"], 3) if o["valN"] else None,
            "encShare": round(o["enc"] / o["nop"], 3), "condShare": round(o["cond"] / o["nop"], 3),
            "delegShare": round(o["deleg"] / o["nop"], 3)})
    bySubj = []
    for s, o in subj.items():
        if o["n"] >= 6 and o["dir"]:
            top = o["verbs"].most_common(1)[0][0] if o["verbs"] else ""
            bySubj.append([s, o["n"], round(statistics.mean(o["dir"]), 2),
                           round(statistics.mean(o["val"]), 2) if o["val"] else 0,
                           round(o["deleg"] / o["n"], 2), top])
    bySubj.sort(key=lambda r: -r[2])
    # verb table with axis coordinates for the scheme visualisation
    op_freq = collections.Counter()
    for d in cat:
        if d[5] or not d[2]:
            continue
        for label, text in bundles.get(d[2], {}).get(d[0], []):
            if label.startswith("OP") and "(" not in label:
                verb, dr, val, dg = code_clause(text)
                if verb:
                    op_freq[verb] += 1
    verbs = [[v, c, DIR_OF.get(v, 0), VAL_OF.get(v, 0 if v not in ("Expresses",) else 0)]
             for v, c in op_freq.most_common()]
    (TX / "lang.json").write_text(json.dumps({
        "scheme": {"dir": DIR, "val": {str(k): v for k, v in VAL.items()}},
        "byYear": byYear, "bySubject": bySubj, "verbs": verbs, "perDoc": per_doc,
        "newVerbs": new_heads.most_common(10),
        "intensified": [[f"{a.title()} {v.lower()}", c] for (v, a), c in intens.most_common(10)],
    }, separators=(",", ":"), ensure_ascii=False), encoding="utf-8")
    return byYear, verbs

def main():
    cat = json.loads((TX / "catalog.json").read_text())["docs"]
    bundles = {}
    for f in TX.glob("docs-*.json"):
        bundles[int(f.stem.split("-")[1])] = json.loads(f.read_text())

    op_freq = collections.Counter()          # operative verb -> clause count
    op_docs = collections.defaultdict(set)    # operative verb -> docIds
    pp_freq = collections.Counter()
    intens_freq = collections.Counter()       # (verb, intensifier) -> count
    new_heads = collections.Counter()         # unrecognized operative head -> count
    op_by_year = collections.defaultdict(collections.Counter)   # year -> verb counts
    per_doc = {}                              # docId -> {verbs:[...], strengthN...}
    n_op_clauses = n_pp_clauses = 0

    for did, d in enumerate(cat):
        sym, rid, year, body, vt, am, subj, title = d
        cls = bundles.get(year, {}).get(sym, [])
        verbs, preambles = [], []
        for label, text in cls:
            if label.startswith("OP") and "(" not in label:   # top-level operative only
                n_op_clauses += 1
                head = op_head(text)
                verb, intens = tag_operative(head)
                if verb:
                    op_freq[verb] += 1; op_docs[verb].add(did); verbs.append(verb)
                    op_by_year[year][verb] += 1
                    if intens: intens_freq[(verb, intens)] += 1
                else:
                    first = head.split(" ")[0] if head else ""
                    if len(first) > 2: new_heads[first] += 1
            elif label.startswith("PP"):
                n_pp_clauses += 1
                p = tag_preamble(op_head(text) if False else " ".join(
                    re.findall(r"[A-Za-z']+", text)[:5]).lower())
                if p:
                    pp_freq[p] += 1; preambles.append(p)
        per_doc[sym] = {"verbs": verbs, "preambles": preambles}

    ndocs = len(cat)
    print(f"corpus: {ndocs} resolutions · {n_op_clauses} operative clauses · {n_pp_clauses} preambular clauses\n")

    print("== TOP OPERATIVE VERBS (UNITAR) — by clause frequency ==")
    for v, c in op_freq.most_common(30):
        print(f"  {c:>6}  {len(op_docs[v]):>5} docs  {v}")
    matched = sum(op_freq.values())
    print(f"  operative clauses matched to UNITAR: {matched}/{n_op_clauses} "
          f"({matched/max(n_op_clauses,1)*100:.1f}%)")

    print("\n== TOP PREAMBULAR OPENERS (UNITAR) ==")
    for v, c in pp_freq.most_common(20):
        print(f"  {c:>6}  {v}")
    pm = sum(pp_freq.values())
    print(f"  preambular clauses matched: {pm}/{n_pp_clauses} ({pm/max(n_pp_clauses,1)*100:.1f}%)")

    print("\n== INTENSIFIED operative verbs (verb + adverb not in UNITAR) ==")
    for (v, a), c in intens_freq.most_common(15):
        print(f"  {c:>5}  {a.title()} {v.lower()}")

    print("\n== 'NEW' / unrecognized operative heads (not in UNITAR 2010 list) ==")
    for h, c in new_heads.most_common(25):
        print(f"  {c:>5}  {h}")

    by, verbs = build_lang(cat, bundles)
    print("\n== two-axis aggregates (lang.json) ==")
    print("  directive intensity (mean D, 1-5) — first/last decade:")
    for o in by[:3]+by[-3:]:
        print(f"    {o['y']} ({o['body']}): dir {o['dir']} · val {o['val']} · encourage {o['encShare']*100:.0f}% · condemn {o['condShare']*100:.0f}% · delegation {o['delegShare']*100:.0f}%")
    (TX / "terms.json").write_text(json.dumps({
        "unitar": {"operative": OPERATIVE, "preamble": PREAMBLE},
        "opFreq": op_freq.most_common(), "ppFreq": pp_freq.most_common(),
        "opByYear": {y: dict(c) for y, c in sorted(op_by_year.items())},
        "intensified": [[f"{a} {v}", c] for (v, a), c in intens_freq.most_common()],
        "newHeads": new_heads.most_common(40),
        "perDoc": per_doc,
    }, separators=(",", ":"), ensure_ascii=False), encoding="utf-8")
    print(f"\nwrote dashboard/texts/terms.json ({(TX/'terms.json').stat().st_size/1024/1024:.1f} MB)")

if __name__ == "__main__":
    main()
