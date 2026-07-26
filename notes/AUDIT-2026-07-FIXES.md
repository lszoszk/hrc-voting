# hrc-voting — what changed in response to the audit

Branch `audit-fixes`, 2026-07-26. Every finding in `AUDIT-2026-07.md` is addressed.
`smoke_test.py`, `audit.py` and `export_test.py` pass with zero console errors at
1440×1000 and 375×740.

Three further problems surfaced while fixing the ones already found; they are marked
**NEW** below.

---

## Data pipeline

**NEW — three MARC records carried another state's ISO code.** `repair_iso()` in
`parse_marcxml.py` now trusts the country name in 967$e and takes the code from the
corpus majority, printing every repair:

```
iso3 repaired: rec 21027 E/CN.4/RES/1992/S-2/1 — HUNGARY was 'HND', now 'HUN'
iso3 repaired: rec 21028 E/CN.4/RES/1999/S-4/1 — NORWAY  was 'PER', now 'NOR'
iso3 repaired: rec 30508 A/HRC/51/L.43         — BRAZIL  was 'BEN', now 'BRA'
```

Each had been moving one vote onto another state's profile, and two of them made the
same state appear twice on one resolution. Found because the corrected masthead count
(80,156) disagreed with the row count (80,158) — the duplicates were collapsing in a
Map keyed by (country, resolution).

**NEW — annexed instruments were being scored as operative paragraphs.** Declarations
and protocols reproduced after a resolution restart their numbering at 1, and
`segment()` absorbed their articles into the operative sequence: "Peasants … have the
right to" (A/HRC/RES/39/12) and "Indigenous peoples have the collective right to"
(A/HRC/RES/1/2) were being read as Council commitments. Numbering restarts now open an
`AX*` label — still fully searchable in the Texts tab, excluded from verb scoring.
**1,529 clauses (3.4%) left the Language corpus.**

**A9 — country-situation heuristic.** `PLACES` in `build_dashboard_data.py` closes the
gap for territories and non-voting states. 12 tags moved out of "Thematic", including
GOLAN HEIGHTS (32 resolutions), MYANMAR, SOUTH SUDAN, XIZANG (CHINA), DARFUR (SUDAN).

**B6 — display names.** `display_name()` is now the single source of truth, so the UI
and every CSV agree: `Bosnia and Herzegovina`, `Côte d'Ivoire`, `Guinea-Bissau`,
`Republic of Korea`, `São Tomé and Príncipe`. Historical states are flagged (`hist`)
and China carries a `repBreak` marker for the 1971 ROC→PRC transition.

**A14 — the dropped roll-call row is no longer silent.** The build prints it, and the
README explains the resulting 80,158 vs 80,159.

---

## Measures that did not match their documentation

**A1 — "Most often outvoted" now measures the side that prevailed.** It took
`max(Y,N,A)`, so a plurality of abstentions counted as a verdict; on 53 adopted
resolutions the winning Yes bloc was scored as outvoted. The prevailing side is now
whichever of Yes or No is larger; Yes/No ties are skipped rather than tie-broken by
column order. Bars carry a **95% Wilson interval** and the vote count, so a 62-vote
record no longer reads like a 953-vote one.

| 2006–2026 | before | after |
|---|---|---|
| 1 | Canada 89% | Canada 87% (n=62, CI 77–93) |
| 3 | United States 68% | DR Congo 66% (n=136, CI 58–74) |
| 6 | United Kingdom 59% | *falls to #9* |

CSV column renamed `minority_side_pct` → `losing_side_pct`, plus CI bounds.
`export_test.py` updated to match.

**A2 — "Not a member" markers.** 12 calendar years contain no recorded vote for anyone,
so the old rule told users France and the UK were off a Commission they sat on
continuously. Markers are now drawn only for years the chamber actually took roll-calls,
and say "No recorded vote cast" rather than asserting non-membership. The tile is
"Voting span", not "Membership span".

```
FRA before : 1949 · 1951 · 1953 · 1956–1957 · 1959–1963 · 1965 · 1973 · 1977 · 2012–2013 · 2017–2020
FRA after  : 1977 · 2012–2013 · 2017–2020        ← the real ones
```

**A4 — delegation counted mentions, not machinery.** It fired on 40.1% of operative
clauses, mostly bare references ("Expresses its appreciation for the preliminary
report…"). A clause now qualifies only if it is *directive* **and** either establishes /
renews / extends a mechanism, or names a UN actor as the object of the verb and gives
it something to do. **40.1% → 17.2%**, and the spurious downward trend largely
disappears (1993: 51%→24%; 2026: 36%→20%) — the old series was tracking the growth of
OHCHR and the special procedures, not drafting behaviour.

**A5 — `Demands` sat in two directive tiers.** Removed from D4 (an assert now prevents
recurrence), so the on-screen "D5 · DECIDES / DEMANDS / ESTABLISHES" header no longer
contradicts a list that omitted it. `Denounces` dropped from the −2 header, where it was
advertised but coded −1.

---

## Statistical floors

**A6 — topic trends.** A direction is stated only with ≥5 year-points, ≥8 years of span
and |t| ≥ 2; otherwise "no clear trend" or "too few years to fit a trend". R², year count
and resolution count are always shown, and the running year is excluded from the fit.

```
Capital punishment      rising ≈ +4.9 pp/decade (R²=0.64) · 17 years, 17 resolutions   [kept]
Self-determination      no clear trend · 13 years, 25 resolutions                      [was "rising +3.4"]
Human rights defenders  too few years to fit a trend (3 years, 4 resolutions)          [was "falling −7.7"]
```

**A7 — consensus flips.** Halves are split by position, not time, so a "before/after"
could straddle a 20-year gap. Series are ranked by Δ×√n instead of raw Δ, and thin or
lopsided ones (n<10, or a half spanning <5 years, or halves differing by ≥10 years) move
to a "Candidates" group. The panel now opens with BURUNDI (n=31), SUDAN (n=30),
TERRORISM (n=33) instead of POLAND (n=6) and CHINA (n=6). 25 of 33 held back; the CSV
carries both half-spans and a `held_back_as_candidate` flag.

**A12 — the running year.** 2026 is drawn at 45% opacity with an "in progress" label on
the overview and consensus charts, flagged in tooltips, and excluded from fitted slopes
and from the consensus peak/low note.

**A13 — exposure.** Covered by the Wilson intervals in A1; no reasonable count floor
helped (Canada n=62 survives even a floor of 50, while the UK has 433).

---

## Language tab

**A3 — corpus range.** The axis spanned 1947–2026 over a corpus that starts in 1993,
leaving half the plot blank. The axis is now clamped to the data, a corpus banner sits
at the top of the tab, and the headline reads "Commission **1993–2005** 3.4 → Council
**2006–2026** 3.5" instead of implying the full Commission era.

**A8 — vocabulary counts.** Methodology claimed "103 operative verbs, 56 preambular
openers" against an implemented 77 and 49. The figures are now read live from
`lang.json.vocab`, so they cannot drift again. The "beyond the glossary" panel is driven
by a drafting-convention rule (a clause-opening third-person-singular verb, with a guard
against subject nouns) rather than a whitelist that could only rediscover verbs its
author already suspected.

**A10 — `Expresses`.** Scored per clause in the trend but filed flat under "0 · neutral"
in the vocabulary chart — for the largest expressive verb in the corpus. It now sits at
its modal value and ships its split, which turns out to matter:

```
Expresses   1,869 clauses   +1 19% · 0 4% · −1 77%
```

It is the second-largest source of negative sentiment, not a neutral verb.

**A11 — uncoded verbs.** `VAL_OF.get(v, 0)` scored "not coded" as "neutral". Now returns
`None` and is excluded from the mean, as directive verbs already were.

**NEW — the scatter's colour encoding was meaningless.** Dots were coloured by
`r[4]>0.5?'AFRICAN':r[2]>3.8?'WEOG':'ASIA_PACIFIC'` — thresholds on the two plotted axes,
rendered in UN regional-group colours, implying a regional split that was not in the
data. Now coloured by country-situation vs thematic, with a legend.

---

## Interface

**B1 — mobile chrome.** Was 57% of a 375×812 viewport; now 28%. All eight tabs stay
visible (no hidden scroll) but lose their index numbers and shrink; the footer stays one
line; the masthead is compact.

| | before | after |
|---|---|---|
| masthead | 188px | 103px |
| tabs | 129px | 85px |
| **content** | **347px** | **581px** (+67%) |
| footer | 139px | 43px |

**B2 — headline counts follow Scope.** The masthead said "1,705 recorded" while the tile
below it said 1,248. Both now update with the filter and name the active scope.

**B3 — acronyms.** `tc()` rendered OHCHR as "Ohchr" and HIV/AIDS as "Hiv/Aids". Only five
acronyms occur across the whole subject vocabulary (verified against `data.js` and
`lang.json`); they are restored after casing.

**B4 — footer clipping** at 1280px: the citation truncates with an ellipsis instead of
the dataset stat being cut mid-word.

**B5 — consent banner** reserves scroll room (`.ga-open .inner`) instead of covering the
first chart and the "most divided votes" table; more compact on small screens.

**B7 — the tour** lists all eight views (was six) and labels the roll-call stat correctly.

**B8 — alignment map** says "28 of 30 highlighted (2 below the 20-shared-vote threshold
with an anchor)" instead of silently dropping two.

**B9 — historical states** are marked "· historical" in the picker. Deliberately without
a year range: `first`/`last` are the years a state cast *recorded* votes, so
Czechoslovakia would have read "1991–1992".

**B10 — clause markers.** `clauseBody()` strips the enumerator the label already carries,
so sub-items render "OP2(e) To adopt…" not "OP2(e)(e) To adopt…".

---

## Tooling & docs

- **`scripts/build_single_file.py` (new)** — the e-mail build was a manual copy step
  described in the audit notes, which is why it had drifted behind `index.html`. It is
  now a script, wired into the README's refresh sequence.
- **README** — documents all eight views, the whole text pipeline (`mirror_ap_ohchr.py`,
  `harvest_ods_texts.py`, `build_text_index.py`, `tag_terms.py`, `dashboard/texts/`), the
  test scripts, the three ISO repairs, the 12 empty years, and the dropped row.
- **`export_test.py`** — updated for the renamed outvoted column.

---

## Follow-up: second UNITAR source (2026-07-26)

Cross-checked the vocabulary against a second, publicly downloadable UNITAR source —
[*Guidelines for United Nations Resolutions* (2020)](https://unitar.org/sites/default/files/media/publication/doc/UN%20Resolution%20Guidelines_Handbook_English-7x10-Unitar_1.pdf),
Annex VII "Resolutions: frequently used terms" — independent of the JG-1/02/10 glossary
the module was built from. It changed three things.

**Four operative verbs were misreported as "drafting drift".** `Appreciates`,
`Underscores`, `Calls for` and `Discourages` are all attested in Annex VII but were
missing from `OPERATIVE`, so the Language tab was presenting real UNITAR vocabulary as
evidence of departure from the glossary. Moved into the canonical list; `Discourages`
coded DIR 2 mirroring `Encourages` (0 occurrences in this corpus, but the asymmetry
would have been a coding gap). Twelve preambular openers were likewise missing
(`Commending`, `Desiring`, `Determined`, `Disturbed`, `Guided`, `Having received`,
`Realizing`, `Renewing its commitment`, `Thanking`, `Underscoring`, …).

| | before | after |
|---|---|---|
| operative vocabulary | 77 | **81** |
| preambular vocabulary | 49 | **59** |
| operative clauses matched to UNITAR | 88.9% | **89.9%** |
| preambular clauses matched | — | **95.4%** |
| "beyond the glossary" headline | Encourages + *Calls for, Underscores, Appreciates* | Encourages (3,440) + low-volume *Applauds, Thanks, Highlights, Observes* |

The `Encourages` finding survives intact and is now cleaner: it is absent from **both**
UNITAR sources at ~3,440 clauses, which is the whole point.

**The context-scoring of `Notes` / `Takes note` / `Expresses` / `Recognizes` turned out
to have direct legal authority.** A 2001 UN Office of Legal Affairs opinion, endorsed by
the General Assembly in **decision 55/488** and reproduced in Annex VI of the same
handbook, holds that the bare terms "takes note of" and "notes" are neutral —
"constitute neither approval nor disapproval" — while UNITAR's glossary separately
catalogues the valenced compounds ("notes with appreciation", "notes with concern") as
distinct entries. That is exactly what `code_clause` does via `NEG_OBJ`/`POS_OBJ`. This
was previously presented as an author-defined coding decision; it is now cited.

**A1 gained independent grounding.** Excluding abstentions from "the side that
prevailed" was argued on first principles in the fix above. GA **rule 86** states that a
member which abstains is "considered as not voting", and only affirmative/negative votes
count toward the required majority (1986 OLA opinion, Annex I of the handbook). Cited in
Methodology §08, with an explicit note that CHR/HRC run under their own rules rather than
the GA's — consistent with the tab's existing warning about transferring GA-specific
findings.

Links added at four points: the Language intro (Annex VII, vocabulary provenance), the
new Notes/Takes-note bullet (Annex VI), the outvoted bullet (Annex I, rule 86), and the
first-run Tour's "Honest by default" slide — where it earns its place as the general
claim the slide is making: *nothing here invents a scale*. Topics are OHCHR's own
catalogued tags, the verb ladder is UNITAR's own glossary, and even the neutral reading
of "takes note" is a UN legal opinion rather than an authorial choice. Also in the
`tag_terms.py` docstring and the README.

---

## Not changed, deliberately

- **The Agreement Index** matches Hix–Noury–Roland exactly; left alone.
- **The chance-agreement and consensus-inclusion caveats** (Häge 2011; Häge & Hug 2016)
  undercut the tab's own numbers and are the best thing in the Methodology tab. Kept
  verbatim.
- **Raw voting-coincidence** is still reported uncorrected for chance. Correcting it
  (e.g. Cohen's κ or the Häge adjustment) changes what the matrix means and is a research
  decision, not an audit fix — worth a look, but it should be your call.
