"""Tag every clause-segmented resolution with UNITAR "Terms Used in Resolutions"
operative verbs and preambular openers, and report statistics + newly-used terms.

Reads dashboard/texts/{catalog.json, docs-*.json} (built by build_text_index.py).
Writes dashboard/texts/terms.json (per-doc verb tags + corpus aggregates) and prints
a stats report.  UNITAR reference: JG-1/02/10, cross-checked against UNITAR NYO,
"Guidelines for United Nations Resolutions" (2020), Annex VI-VII:
https://unitar.org/sites/default/files/media/publication/doc/UN%20Resolution%20Guidelines_Handbook_English-7x10-Unitar_1.pdf
"""
import json, re, collections
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TX = ROOT / "dashboard" / "texts"

# ---- UNITAR controlled vocabulary (canonical heads) ----
# Cross-checked term-by-term against UNITAR NYO, "Guidelines for United Nations
# Resolutions" (2020), Annex VII "Resolutions: frequently used terms" — a second,
# publicly downloadable UNITAR source, independent of the JG-1/02/10 glossary this
# module was originally built from. Four operative verbs (Appreciates, Underscores,
# Calls for, Discourages) and twelve preambular openers were attested there but
# missing here, which meant real UNITAR vocabulary was being reported to readers as
# "drafting drift beyond the glossary" on the Language tab. Added below, each tagged
# `# Annex VII` at the point it was added.
OPERATIVE = [
    "Accepts", "Acknowledges", "Adopts", "Affirms", "Agrees", "Appeals", "Appoints",
    "Appreciates",  # Annex VII
    "Approves", "Authorizes", "Believes", "Calls the attention", "Calls attention",
    "Calls for",  # Annex VII
    "Calls upon", "Commends", "Compliments", "Concurs", "Condemns", "Confirms",
    "Congratulates", "Considers", "Decides", "Declares", "Demands", "Denounces",
    "Deplores", "Designates", "Determines",
    "Discourages",  # Annex VII — scored as DIR tier 2, mirroring "Encourages"
    "Dissolves", "Draws the attention", "Elects",
    "Emphasizes", "Empowers", "Endorses", "Entrusts", "Envisages", "Establishes",
    "Exhorts", "Expresses", "Extends", "Firmly supports", "Insists", "Instructs",
    "Invites the attention", "Invites", "Is of the opinion", "Looks forward",
    "Makes an urgent appeal", "Mandates", "Notes", "Pays tribute", "Proclaims",
    "Proposes", "Reaffirms", "Realizes", "Reasserts", "Recalls", "Recognizes",
    "Recommends", "Refers", "Regrets", "Reiterates", "Rejects", "Reminds", "Renews",
    "Requests", "Resolves", "Solemnly adopts", "Stresses", "Suggests", "Supports",
    "Takes note", "Transmits", "Trusts", "Underlines",
    "Underscores",  # Annex VII — same register as "Underlines" ("underlining, underscoring")
    "Urgently requests", "Urges",
    "Welcomes",
]
PREAMBLE = [
    "Acknowledging", "Acting", "Adhering", "Affirming", "Agreeing", "Alarmed",
    "Appreciating", "Aware", "Bearing in mind", "Believing", "Cognizant",
    "Commending",  # Annex VII
    "Concerned", "Concurring", "Condemning", "Conscious", "Considering", "Convinced",
    "Deploring",
    "Desiring", "Desirous",  # Annex VII adds "Desiring"; "Desirous" already present
    "Determined",  # Annex VII
    "Disturbed",  # Annex VII
    "Emphasizing", "Encouraged", "Expressing", "Faithful", "Fearing",
    "Fully aware", "Guided",  # Annex VII (bare "Guided", distinct from "Guided by" below)
    "Guided by", "Having considered",
    "Having received",  # Annex VII
    "Hopeful", "Indignant", "Inspired",
    "Keeping in mind", "Mindful", "Noting", "Persuaded",
    "Realizing",  # Annex VII
    "Reaffirming", "Recalling",
    "Recognizing", "Regretting", "Reiterating",
    "Renewing its commitment",  # Annex VII
    "Sharing the concern", "Stressing",
    "Striving", "Taking into account", "Taking into consideration", "Taking note",
    "Thanking",  # Annex VII
    "Underlining",
    "Underscoring",  # Annex VII
    "Viewing with concern", "Welcoming", "Wishing",
]
# generic intensifiers/adverbs that precede a verb but are not part of a UNITAR entry
INTENS = ["strongly", "deeply", "gravely", "seriously", "vigorously", "categorically",
          "unequivocally", "emphatically", "resolutely", "also", "further", "again",
          "once again", "in this regard", "in particular"]
# A clause-opening word followed by one of these is a subject noun ("States should…",
# "Peasants … have the right"), not an operative verb.
SUBJECT_FOLLOWERS = {"shall", "should", "must", "may", "might", "can", "could", "will",
                     "would", "have", "has", "had", "are", "is", "was", "were", "and",
                     "or", "who", "which", "that"}

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
           "Instructs", "Urgently requests", "Makes an urgent appeal"],
       3: ["Requests", "Recommends"],
       2: ["Invites", "Encourages", "Suggests", "Proposes", "Envisages", "Discourages"]}
assert not (set(DIR[5]) & set(DIR[4])), "a verb may sit in only one directive tier"
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
# Delegation: the clause CREATES or TASKS machinery. A bare mention of a body or a
# report is not delegation ("Expresses its appreciation for the report of the Special
# Rapporteur" creates nothing), so all three conditions must hold:
#   1. the clause is directive at all (dir tier > 0), and either
#   2. it establishes / renews / extends a mechanism, or
#   3. a UN actor is the OBJECT of that directive verb (within DELEG_WIN characters of
#      the clause opening) and is followed by an infinitival task.
DELEG_ACTOR = re.compile(
    r"\b(secretary-general|high commissioner|office of the high commissioner|ohchr|"
    r"centre for human rights|special rapporteur|independent expert|special representative|"
    r"working group|commission of inquiry|advisory committee|sub-commission|"
    r"group of experts|panel of experts|fact-finding mission|special procedures?)\b", re.I)
# "to <verb>", excluding "to the/its/a/…" noun phrases ("to bring X to the attention of")
_NOT_VERB = (r"(?:the|its|his|her|their|our|this|that|these|those|all|any|such|a|an|which|"
             r"whom|it|them|him|and|or|as|in|on|at|for|of|with|from|by|international|human|"
             r"present|above|full|date|end|extent|effect|attention|situation|question|report|"
             r"states?|governments?|members?)")
DELEG_TASK = re.compile(r"\bto\s+(?!" + _NOT_VERB + r"\b)[a-z]{3,}\b")
DELEG_CREATE = re.compile(
    r"\b(establish|create|set up|appoint|renew|extend|prolong|continue)\w*\b[^.;]{0,90}?"
    r"\b(mandate|working group|special rapporteur|independent expert|special representative|"
    r"commission of inquiry|fact-finding|panel|forum|group of experts|special procedure|"
    r"advisory committee|open-ended)\b", re.I)
DELEG_WIN = 80          # actor must be the verb's object, not a citation deep in the clause


def is_delegation(text, dir_tier):
    if not dir_tier:
        return False
    if DELEG_CREATE.search(text):
        return True
    m = DELEG_ACTOR.search(text[:DELEG_WIN])
    return bool(m and DELEG_TASK.search(text, m.end()))

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


# Intensifiers can also sit INSIDE a multiword term ("Calls once again upon"), which a
# prefix-strip alone cannot reach. Deleting them anywhere in the head recovers the term.
_INFIX = re.compile(r"\b(?:" + "|".join(sorted((re.escape(a) for a in INTENS),
                                               key=len, reverse=True)) + r")\b")


def match_relaxed(head, terms):
    """(term, intensifier-removed?) allowing intensifiers anywhere in the head."""
    m = match(head, terms)
    if m:
        return m, False
    squeezed = re.sub(r"\s+", " ", _INFIX.sub("", head)).strip()
    if squeezed and squeezed != head:
        m = match(squeezed, terms)
        if m:
            return m, True
    return None, False

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

# These five are attested in the corpus (Applauds/Thanks/Highlights/Observes at low
# volume) but not in either UNITAR source consulted, so they stay OUT of the canonical
# OPERATIVE list and are scored as "beyond the glossary" — Encourages (~3,400 clauses)
# is the one that matters at scale.
NEWCANON = {"encourages": "Encourages", "applauds": "Applauds", "thanks": "Thanks",
            "highlights": "Highlights", "observes": "Observes"}
# extended operative vocabulary = UNITAR (canonical) + the still-uncanonical "new" verbs
OP_EXT = _byword(OPERATIVE + ["Encourages", "Applauds", "Thanks", "Highlights", "Observes"])

CTX_VERBS = ("Expresses", "Notes", "Takes note", "Recognizes")   # valence sits in the object


def code_clause(text):
    """(verb, dir, val, deleg) for one operative clause under the two-axis scheme.

    val is None for directive verbs AND for verbs carrying no valence code — 'not
    coded' must not average in as 'neutral 0'."""
    head = op_head(text)
    verb, _ = match_relaxed(head, OP_EXT)
    if not verb:
        return None, 0, None, False       # unrecognized head: nothing can be scored
    v = CANON.get(verb) or NEWCANON.get(verb) or verb.title()
    d = DIR_OF.get(v, 0)
    if v in CTX_VERBS:
        val = -1 if NEG_OBJ.search(text) else (1 if POS_OBJ.search(text) else 0)
    else:
        val = None if d else VAL_OF.get(v)
    return v, d, val, is_delegation(text, d)

def build_lang(cat, bundles):
    import statistics
    new_heads = collections.Counter(); intens = collections.Counter()
    UNITAR_L = set(OP_L)
    def track_new(text):
        """Operative heads the UNITAR list does not carry.

        Detection is by drafting convention, not by a whitelist: an operative clause
        opens with a third-person-singular present verb. A whitelist could only ever
        rediscover the verbs its author already suspected, which is not a finding."""
        head = op_head(text)
        m, relaxed = match_relaxed(head, OP_L)
        if m:                                                 # UNITAR term, possibly
            if relaxed:                                       # with an intensifier
                for a in sorted(INTENS, key=lambda s: -len(s)):
                    if a in head:
                        intens[(CANON[m], a)] += 1; break
            return
        m, _ = match_relaxed(head, OP_EXT)                     # extras: "Calls for"
        if m:
            new_heads[CANON.get(m) or NEWCANON.get(m) or m.title()] += 1; return
        w, *rest = head.split(" ") if head else [""]
        # third-person-singular present verb, and not a subject noun: an operative verb
        # takes an object or a preposition, never a modal/auxiliary/conjunction.
        if (len(w) >= 4 and w.endswith("s") and not w.endswith("ss")
                and (not rest or rest[0] not in SUBJECT_FOLLOWERS)):
            new_heads[w.title()] += 1
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
                           round(statistics.mean(o["val"]), 2) if o["val"] else None,
                           round(o["deleg"] / o["n"], 2), top])
    bySubj.sort(key=lambda r: -r[2])
    # verb table with axis coordinates for the scheme visualisation. Context-scored
    # verbs ("Expresses its grave concern" vs "…its appreciation") carry no fixed
    # valence, so we ship the resolved split and place the verb at its modal value —
    # filing them flat under 0 would misreport the largest expressive verb in the corpus.
    op_freq = collections.Counter()
    ctx_split = collections.defaultdict(collections.Counter)
    for d in cat:
        if d[5] or not d[2]:
            continue
        for label, text in bundles.get(d[2], {}).get(d[0], []):
            if label.startswith("OP") and "(" not in label:
                verb, dr, val, dg = code_clause(text)
                if verb:
                    op_freq[verb] += 1
                    if verb in CTX_VERBS:
                        ctx_split[verb][val] += 1
    verbs = []
    for v, c in op_freq.most_common():
        if v in ctx_split:
            sp = ctx_split[v]
            verbs.append([v, c, DIR_OF.get(v, 0), sp.most_common(1)[0][0],
                          {str(k): n for k, n in sorted(sp.items())}])
        else:
            verbs.append([v, c, DIR_OF.get(v, 0), VAL_OF.get(v, 0), None])
    (TX / "lang.json").write_text(json.dumps({
        # shipped so the Methodology tab quotes the vocabulary actually implemented
        # rather than a hand-written figure that can drift from it
        "vocab": {"operative": len(OPERATIVE), "preamble": len(PREAMBLE),
                  "extended": len(OP_EXT)},
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
