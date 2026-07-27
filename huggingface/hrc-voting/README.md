---
pretty_name: UN Human Rights Voting Records (CHR 1946–2006 · HRC 2006–)
homepage: https://lszoszk.github.io/hrc-voting/
license: other
license_name: polyform-noncommercial-1.0.0
license_link: https://polyformproject.org/licenses/noncommercial/1.0.0/
annotations_creators:
- expert-generated
- found
language_creators:
- found
multilinguality:
- monolingual
language:
- en
source_datasets:
- original
task_categories:
- tabular-classification
- text-classification
- text-retrieval
task_ids:
- multi-class-classification
size_categories:
- 10K<n<100K
tags:
- human-rights
- united-nations
- human-rights-council
- commission-on-human-rights
- roll-call-votes
- voting-records
- international-relations
- political-science
- legal
viewer: true
configs:
- config_name: resolutions
  default: true
  data_files:
  - split: train
    path: data/resolutions-train.parquet
- config_name: votes
  data_files:
  - split: train
    path: data/votes-train.parquet
- config_name: clauses
  data_files:
  - split: train
    path: data/clauses-train.parquet
---

# UN Human Rights Voting Records — CHR · HRC

Every voting record catalogued by the OHCHR Search Library for the **UN Commission on
Human Rights (1946–2006)** and its successor the **Human Rights Council (2006–present)**:
6,346 resolutions, 80,159 individual country roll-call votes, and 96,451 clause-segmented
paragraphs of the adopted texts.

Harvested from the OHCHR Search Library's MARCXML export and parsed with the pipeline in
[`lszoszk/hrc-voting`](https://github.com/lszoszk/hrc-voting). The record count matches
the collection's own reported total exactly, verified by three independent harvest
methods. An interactive dashboard over the same data is at
<https://lszoszk.github.io/hrc-voting/>.

## Configs

| config | rows | one row is | period |
|---|---|---|---|
| `resolutions` *(default)* | 6,346 | a catalogued resolution, decision or amendment | 1946–2026 |
| `votes` | 80,159 | one country's position on one resolution | 1947–2026 |
| `clauses` | 96,451 | one preambular / operative / annex clause | 1993–2026 |

```python
from datasets import load_dataset

res    = load_dataset("lszoszk/hrc-voting", "resolutions", split="train")
votes  = load_dataset("lszoszk/hrc-voting", "votes",       split="train")
clauses= load_dataset("lszoszk/hrc-voting", "clauses",     split="train")
```

`record_id` is the join key across all three.

## Read this before analysing

These are the four things most likely to produce a wrong result. The first two are
mistakes this project made and corrected; derived columns are provided so you do not
have to repeat them.

**1. Only 27% of resolutions have a per-country roll-call.** 1,705 of 6,346. The rest
were adopted without a vote or published as totals only, so no individual positions
exist. Roll-call statistics describe *contested* politics, not the Council's output —
a well-documented selection problem (Fjelstul, Hug & Kilby 2025). Filter on
`has_rollcall`.

**2. An abstention is not a vote against.** Under the chamber's own rules a member that
abstains is "considered as not voting", so the outcome turns on Yes vs No alone. Taking
`max(yes, no, abstain)` as the winning side — the obvious-looking move — scores the
winning Yes bloc as *defeated* on **53 adopted resolutions** in this corpus, where more
members abstained than voted Yes but the text still carried. Use `prevailing_side` /
`adopted`, which are computed correctly (Yes vs No, null on a 6-case tie).

**3. Amendments are not resolutions.** 731 catalogued items are amendments to draft
texts, and 462 of them went to a recorded vote — 27% of all roll-calls, almost all
post-2010. A Yes on a hostile amendment frequently *opposes* the parent text's aim, so
pooling them with resolutions inverts meaning. Filter on `is_amendment`.

**4. ~9% of roll-calls do not reconcile with the official totals.** For 148 recorded
votes the sum of individual Yes/No/Abstain positions does not match the resolution's
official 996 totals, almost always by a small margin in abstentions or
non-participation. These are inconsistencies in OHCHR's own cataloguing and are
preserved as-is; the official totals are treated as authoritative. Filter on
`rollcall_reconciles`.

## Config: `resolutions`

One row per catalogued item. Vote totals are the **official** figures from MARC 996,
which exist for many resolutions that have no per-country breakdown.

```json
{
  "record_id": "35356",
  "symbol": "A/HRC/RES/61/10",
  "title": "Torture and other cruel, inhuman or degrading treatment or punishment: mandate of the Special Rapporteur : resolution /",
  "date": "2026-03-30", "year": 2026, "body": "HRC",
  "vote_type": "ADOPTED WITHOUT VOTE", "adoption_mode": "adopted without a vote",
  "is_amendment": false,
  "subject": "TORTURE AND INHUMAN TREATMENT - SPECIAL RAPPORTEURS",
  "agenda_item_no": "3.",
  "agenda_item_title": "Promotion and protection of all human rights, civil, political, economic, social and cultural rights, including the right to development.",
  "main_sponsors": "Denmark", "meeting": "Adopted at the 52nd meeting",
  "yes": null, "no": null, "abstain": null, "nonvoting": null, "total": null,
  "n_rollcall": 0, "has_rollcall": false,
  "prevailing_side": null, "adopted": null, "rollcall_reconciles": null,
  "url_resolution": "http://undocs.org/A/HRC/RES/61/10",
  "url_draft": "http://undocs.org/A/HRC/61/L.10",
  "record_url": "https://searchlibrary.ohchr.org/record/35356"
}
```

- `record_id` — stable Invenio id (MARC 001); join key
- `symbol` — e.g. `A/HRC/RES/61/29`, `E/CN.4/RES/2005/1`
- `title`, `date`, `year`, `body` — `CHR` or `HRC`
- `vote_type` — raw catalogue value (MARC 591); `adoption_mode` — readable form
- `is_amendment` — an amendment to a draft text, detected from two agreeing catalogue
  signals (a `: amendment /` title marker and the MARC 993 draft note)
- `subject` — OHCHR's own controlled subject heading (MARC 991$d); **not** ML-derived
- `agenda_item_no`, `agenda_item_title`, `main_sponsors`, `meeting`
- `yes`, `no`, `abstain`, `nonvoting`, `total` — official totals (MARC 996), null when
  the catalogue records none
- `n_rollcall`, `has_rollcall` — number of per-country rows in `votes`
- `prevailing_side` — `Y`, `N`, or null (tie / no totals) — **see caveat 2**
- `adopted` — `prevailing_side == "Y"`, null when undetermined
- `rollcall_reconciles` — whether the roll-call tally matches the official totals; null
  when there is no roll-call — **see caveat 4**
- `url_resolution`, `url_draft`, `record_url`

Adoption modes: adopted without a vote 3,835 · recorded vote 1,713 · non-recorded vote
371 · withdrawn 236 · non-recorded unanimous 142 · not considered 33 · non-recorded no
information 15 · recorded at a closed meeting 1. Bodies: CHR 3,082 · HRC 3,264.

## Config: `votes`

One row per (resolution, country). 154 states appear.

- `record_id`, `symbol`, `date`, `year`, `body`
- `iso3`, `country` — ISO-3166 alpha-3 and the name as catalogued
- `un_regional_group` — WEOG / Eastern Europe / GRULAC / African / Asia-Pacific,
  assigned by present-day membership and applied across the whole period
- `vote` — raw code, `vote_label` — readable
- `is_cast_vote` — true for `Y`/`N`/`A` only
- `prevailing_side`, `with_prevailing_side` — whether this state was on the side that
  prevailed; null when it cast no vote or the resolution had no Yes/No outcome
- `subject`, `is_amendment` — denormalised from `resolutions` for convenient filtering

Vote codes: `Y` yes 44,536 · `N` no 18,368 · `A` abstain 15,911 · `.` absent or not
participating 701 · empty 643 (not a member at the time, or no position recorded).

## Config: `clauses`

Clause-segmented full text of 4,437 resolutions, **1993–2026** — the earliest the
OHCHR/ODS document mirrors reach, so this config covers a much shorter period than the
other two. Extracted from `.doc`/`.pdf` originals and segmented on structural markers.

- `record_id`, `symbol`, `year`, `body`, `subject`, `title`, `is_amendment`,
  `adoption_mode`, `adopted`
- `clause_index`, `clause_label` — e.g. `PP3`, `OP7`, `OP2(a)`, `AX1`
- `clause_type` — `preambular` 35,670 · `operative` 42,957 · `operative_subitem` 12,498 ·
  `annex` 2,082 · `other` 3,244
- `text`, `n_chars`, `n_words`

Four **experimental** columns score top-level operative clauses only (null elsewhere).
Each operative paragraph opens by drafting convention with a controlled verb, matched
against UNITAR's *Terms Used in Resolutions* glossaries; 98.5% of operative clauses
resolve to a verb.

- `operative_verb` — canonical form, e.g. `Requests`, `Calls upon`, `Condemns`
- `directive_force` — 5 decisional (*Decides, Demands, Establishes*) · 4 strong
  exhortation (*Urges, Calls upon*) · 3 tasking (*Requests, Recommends*) · 2 invitation
  (*Invites, Encourages*); null for non-directive verbs
- `sentiment` — −2 condemnation … 0 neutral registering … +2 commendation; null for
  directive verbs and for verbs carrying no valence code. For *Notes*, *Takes note*,
  *Recognizes* and *Expresses* the score is resolved **per clause** from the object
  ("*with concern*" → −1, "*with appreciation*" → +1), following a 2001 UN Office of
  Legal Affairs opinion (endorsed in GA decision 55/488) that the bare terms are neutral
- `creates_or_tasks_machinery` — the delegation axis: true only when a *directive* clause
  establishes, renews or extends a mechanism, or names a UN actor and gives it something
  to do (17.4% of operative clauses). A passing mention of a rapporteur or a report does
  **not** count; scoring mentions instead put 40% of clauses on this axis and imported a
  spurious trend, since OHCHR and the special procedures only expanded after 1993

**These columns measure rhetorical / directive hardness, not legal bindingness.** Even
"Decides" binds only under Security-Council Chapter VII; CHR and HRC resolutions are
formally non-binding whatever the verb. Tagging only the leading verb also omits the
addressee and the precision of the ask. The tiers are grounded in the "legalization"
framework (Abbott, Keohane, Moravcsik, Slaughter & Snidal 2000) and a content-analysis
approach developed for Security Council resolutions (Benson & Tucker 2022); the exact
rank within a tier and the numeric spacing are an author-defined coding.

Articles of annexed declarations and protocols are labelled `annex`, not `operative` —
they are treaty-style text, not commitments of the organ, and conflating them shifts
every operative-verb statistic.

## Known data-quality notes

- **Three MARC `967$b` codes contradicted their country name** and are repaired by the
  pipeline, which trusts the name: rec 21027 HUNGARY was coded `HND`, rec 21028 NORWAY
  was `PER`, rec 30508 BRAZIL was `BEN`. Each had been moving one vote onto another
  state's profile.
- **One roll-call row has no country** (rec 24737, `E/CN.4/RES/6(XX)`, 1964) — a
  malformed MARC field. It is kept for fidelity to the source, with `iso3` null.
- **One vote-code typo** (`y` → `Y`, UK 2011) is normalised. Nothing else is altered.
- **12 calendar years contain no recorded vote at all** (1949, 1951, 1953, 1956–57,
  1959–63, 1965, 1973). A state's absence from the roll-call in those years says nothing
  about its membership.
- **`CHN` spans a change of representation, not of state** — the China seat passed from
  the Republic of China to the PRC in October 1971; the catalogue records both as `CHN`.
- **`un_regional_group` is applied anachronistically.** Groups are present-day; the
  Commission's membership and the groups themselves changed over 60 years.
- Historical states appear under their own codes (`CSK` Czechoslovakia, `SUN` Soviet
  Union, `YUG` Yugoslavia, `DDR`/`GER` the two Germanys).

## Suitable for

Roll-call and ideal-point analysis of a small elected chamber (as opposed to the UN
General Assembly, which most of the quantitative literature studies); bloc and alignment
work; agenda and subject analysis using the catalogue's own controlled vocabulary;
clause-level retrieval over UN human-rights text; and study of drafting language and
institutional commitment.

Most quantitative UN-voting findings come from the **General Assembly** — universal
membership, plenary voting. The Commission (53 members elected by ECOSOC) and the
Council (47, elected by the GA under regional quotas) are small elected chambers where
membership itself is selected and absence is marginal. Treat GA findings as hypotheses
here, not established facts.

## Provenance and reproduction

Source: OHCHR Search Library, [Voting collection](https://searchlibrary.ohchr.org/search?c=Voting).
The full pipeline — harvest, parse, build — is in the repository and this package is
rebuilt from committed outputs by
[`scripts/prepare_hf_dataset.py`](https://github.com/lszoszk/hrc-voting/blob/main/scripts/prepare_hf_dataset.py).
Methods and caveats are documented in the dashboard's Methodology tab and in
`notes/AUDIT-2026-07.md`.

## Licence

Code and data are released under the **PolyForm Noncommercial License 1.0.0**: research,
education, non-profit and personal use are permitted; **commercial use requires a
separate licence from the author.** The underlying voting records are public UN documents
from the OHCHR Search Library.

## Citation

> Szoszkiewicz, Ł. (2026). *OHCHR Voting Records — CHR · HRC* (v1.0.0) [Software].
> Zenodo. https://doi.org/10.5281/zenodo.21281232

```bibtex
@software{szoszkiewicz_hrc_voting_2026,
  author    = {Szoszkiewicz, {\L}ukasz},
  title     = {OHCHR Voting Records --- CHR {\textperiodcentered} HRC},
  year      = {2026},
  version   = {1.0.0},
  publisher = {Zenodo},
  doi       = {10.5281/zenodo.21281232},
  url       = {https://lszoszk.github.io/hrc-voting/}
}
```

Built and maintained by [Łukasz Szoszkiewicz](https://lszoszk.github.io/) (Adam
Mickiewicz University, Poznań) · [ORCID 0000-0001-6671-2893](https://orcid.org/0000-0001-6671-2893).
