---
name: hrc-voting-cite
description: Cite the HRC Voting dataset and UN human-rights votes correctly — dataset DOI, BibTeX/APA/OSCOLA forms, how to cite a specific resolution with its vote tally, a methods or data-availability note, licence and attribution wording. Use whenever the user asks how to cite HRC Voting, the Zenodo/Hugging Face dataset, a Human Rights Council or Commission on Human Rights resolution together with how States voted, or wants a methods footnote, chart caption or data statement for an analysis built on UN voting records — even if they only say "how do I reference this vote" or "write the data section". Companion to the hrc-voting skill (https://lszoszk.github.io/hrc-voting/, DOI 10.5281/zenodo.21281232).
---

# Citing HRC Voting and the votes in it

A number taken from the dataset has three sources, and a careful citation names each one: the **UN document** (what was
decided), the **record of the vote** (who voted how), and the **dataset** (how it was harvested and processed). Mixing
them up is the usual error: readers should be able to check the text at the UN, the tally at the OHCHR record, and the
processing in the versioned dataset.

## 1. The dataset (cite whenever you used its processing, counts or derived figures)

Use the **concept DOI** for general references and the **version DOI** when an exact figure must be reproducible.
The dashboard is not versioned, so never cite only its URL.

- Concept DOI (always the latest version): https://doi.org/10.5281/zenodo.21281232
- v1.2.0 (data snapshot 28 Sep 2026): https://doi.org/10.5281/zenodo.23010658

APA-style:
> Szoszkiewicz, Ł. (2026). *UN Human Rights Voting Records — CHR · HRC · GA Third Committee* (v1.2.0) [Software]. Zenodo. https://doi.org/10.5281/zenodo.21281232

BibTeX:
```bibtex
@software{szoszkiewicz_hrc_voting_2026,
  author    = {Szoszkiewicz, {\L}ukasz},
  title     = {UN Human Rights Voting Records --- CHR {\textperiodcentered} HRC {\textperiodcentered} GA Third Committee},
  year      = {2026},
  version   = {1.2.0},
  publisher = {Zenodo},
  doi       = {10.5281/zenodo.21281232},
  url       = {https://lszoszk.github.io/hrc-voting/}
}
```
Footnote style (OSCOLA-like; adapt punctuation to the edition in force):
> Łukasz Szoszkiewicz, *UN Human Rights Voting Records — CHR · HRC · GA Third Committee* (v1.2.0, Zenodo 2026) <https://doi.org/10.5281/zenodo.21281232> accessed 10 October 2026.

If the `hrc-voting` skill reports a newer snapshot than v1.2.0, use the version shown in its output (`info`) and the
concept DOI, and say that the version DOI is on the Zenodo record.

## 2. A resolution and its vote

Cite the UN document from its symbol and date (the `date` field is the adoption date), then give the tally with its source.
The tally is a fact about the vote, not about the text.

OSCOLA-style examples (check against your style guide; the symbols are the stable part):
- Human Rights Council: UNHRC Res 48/1 (7 October 2021) UN Doc A/HRC/RES/48/1, adopted by recorded vote (28 Yes, 5 No, 14 abstentions).
- Commission on Human Rights: UNCHR Res 2005/80 (21 April 2005) UN Doc E/CN.4/RES/2005/80.
- General Assembly: UNGA Res 2647 (XXV) (30 November 1970) UN Doc A/RES/2647(XXV).
- An amendment is not a resolution: cite its L-document and the draft it amends, e.g. "Amendment A/HRC/48/L.59 to draft resolution
  A/HRC/48/L.8 (adopted by 16 votes to 13, with 16 abstentions)" and do not describe it as a resolution.

Source line for the tally: "Votes as recorded in the OHCHR Library voting records, <record_url from the data>, accessed [date]."
For General Assembly votes: "United Nations Dag Hammarskjöld Library, General Assembly Voting Data, version 5 (February 2026),
https://digitallibrary.un.org/record/4060887".

Wording that stays accurate: "adopted by a recorded vote of 28 to 5, with 14 abstentions"; "adopted without a vote" or "by
consensus" (never "unanimously": delegations can dissociate); "rejected" only when the record says so.

## 3. Methods or data-availability note (fill the brackets)

> Voting data come from HRC Voting v[1.2.0] (Szoszkiewicz 2026; snapshot [28 September 2026]), which harvests the OHCHR Library
> "Voting" collection for the Commission on Human Rights and the Human Rights Council ([6,392] catalogued records, [1,716] with
> a per-State roll-call) and, for the General Assembly, the UN Dag Hammarskjöld Library's General Assembly voting data (v5).
> [Amendments to draft texts were excluded / analysed separately.] An abstention is not counted as a vote against; outcomes follow
> Yes versus No. The catalogue omits two of the Council's rejected draft texts and 21 amendments in 2020–2024 [relevant if the
> analysis touches them], which the dataset documents. Data and code: https://doi.org/10.5281/zenodo.21281232.

Drop sentences that do not apply, but keep the version, the snapshot date and the amendments decision: those are what a
reader needs to reproduce the numbers.

## 4. Chart and table captions

"Source: HRC Voting v1.2.0 (Szoszkiewicz 2026), based on OHCHR Library voting records; recorded votes, amendments excluded."
The dashboard's own CSV/PNG exports are already stamped with the source, scope and access date; keep that stamp.

## 5. Licence and attribution

- HRC Voting code and derived datasets: PolyForm Noncommercial 1.0.0. Research, education, non-profit and personal use are free;
  commercial use needs a separate licence from the author.
- The underlying records are public UN documents. The General Assembly voting data is "Copyright, United Nations; non-commercial
  use, with attribution".
- HRC Voting is independent of the United Nations; do not suggest UN endorsement or call it "the UN's dataset".

## 6. Before the numbers go out

1. Scope stated (body, years, recorded votes, amendments in or out).
2. Version and snapshot date stated.
3. Percentages come with their denominators; "adopted without a vote" is not called unanimity.
4. General Assembly figures are not added to Commission/Council figures.
5. Anything touching 2020–2025 amendments or rejected texts mentions the known gaps (`hrc-voting` skill → `gaps`).
