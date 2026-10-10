---
name: hrc-voting
description: Query and analyse UN human-rights voting records — how States voted on resolutions of the Commission on Human Rights (1946–2006) and the Human Rights Council (2006–), plus General Assembly Third Committee plenary votes (1970–). Use this whenever the user asks how a country voted at the HRC/CHR/UNGA Third Committee, which States vote together, voting blocs or alignment, consensus versus recorded votes, amendments at the Council, roll-call counts, or wants a published figure about Council votes checked — even if they never name the dataset. Bundles an offline snapshot (v1.2.0, 28 Sep 2026; 6,392 CHR/HRC records, 80,676 country votes, 708 GA resolutions) and a CLI that applies the dataset's safeguards (amendments vs resolutions, abstention is not "against", catalogue gaps). Part of HRC Voting (https://lszoszk.github.io/hrc-voting/, DOI 10.5281/zenodo.21281232).
---

# HRC Voting: how States vote on UN human-rights texts

The dataset harvests the OHCHR Library's "Voting" collection (Commission and Council) and adds the General
Assembly's Third Committee texts decided by recorded vote (UN Digital Library). It is independent of the UN. This
skill answers questions from a bundled snapshot, so it works offline; the snapshot's date is printed in every answer.

## How to answer

1. **Run the CLI instead of recalling facts.** Votes are exactly the kind of detail memory gets wrong.
   `python scripts/hrcv.py <command>` (path relative to this skill's folder; Python 3, standard library only).
2. **State the scope in the answer**: body (CHR, HRC, or GA), years, "recorded votes only", "amendments excluded", and the
   snapshot version/date. The CLI prints this; carry it into your reply. Without it a number can be misread
   by an order of magnitude (e.g. 1,251 resolutions vs 1,716 roll-call records vs 6,392 catalogued records).
3. **Apply the safeguards below** before interpreting. They exist because each one is a mistake that has already been made
   with this kind of data; `references/pitfalls.md` explains the reasoning.
4. **Link the source**: resolutions carry an OHCHR record URL; countries have a dashboard deep link
   (`https://lszoszk.github.io/hrc-voting/#country=POL`) and a plain page (`…/hrc-voting/country/poland/`).

## Commands

| Question | Command |
|---|---|
| What is in the data, how old is it | `info` |
| Find resolutions on a topic | `search "death penalty" --years 2010-2024 [--mode recorded] [--body hrc]` |
| One resolution: tally and every State's vote | `resolution A/HRC/RES/48/1` |
| A State's record (totals, per year, latest votes) | `country Poland [--years 2006-2026] [--by-year] [--list 10] [--body ga]` |
| Closest / furthest voting partners | `partners Poland [--years …] [--min-shared 30]` |
| Two States head to head | `compare Poland Hungary --years 2006-2026` |
| Consensus vs recorded vote over time | `adoption --body hrc [--years …]` |
| Amendments by outcome and year | `amendments --years 2020-2024` |
| Known gaps in the source catalogue | `gaps` |
| Check the bundled data | `selftest` |
| Newer data (needs network) | `refresh` (then the CLI prefers the refreshed copy) |

For anything the commands do not cover, load the CSVs directly (`assets/data/*.csv.gz`, schema in
`references/schema.md`) and keep the same defaults. The Hugging Face dataset `lszoszk/hrc-voting` (10 parquet configs)
has more: committee-stage votes, clause-level resolution texts, derived columns (`prevailing_side`, `adopted`).

## Safeguards (the defaults of every command)

- **Amendments are not resolutions.** They are 27% of all roll-calls; a Yes on a hostile amendment often opposes the text's aim.
  Excluded by default, reported separately (`amendments`).
- **Abstention ≠ against.** The outcome is Yes vs No; never `max(Yes, No, Abstain)`.
- **Roll-calls are the contested minority**: 73% of records carry no per-country roll-call, 60% were adopted without a vote.
  Say what the denominator is. "Adopted without a vote" is not unanimity.
- **Absent (`.`) and not-a-member (empty) are not positions.** Agreement is computed over shared votes only.
- **Do not add the General Assembly to CHR/HRC.** Different body, plenary votes, no consensus texts in the source.
- **The catalogue has gaps** (2 of the Council's 3 rejected drafts and 21 amendments in 2020–2024 are missing). If the
  question touches 2020–2025 amendments or rejected texts, run `gaps` and say so.
- **Raw agreement is inflated by lopsided votes**; report shared-vote counts and keep the language descriptive.

## Output habits that help the reader

- Lead with the answer, then the scope line, then caveats that change the reading (not all of them).
- Give counts next to percentages ("54% of 560 votes").
- For a claim being fact-checked, follow `references/verification.md` and present claim / dataset / source / reason.
- For citations of the dataset or of a vote, hand over to the `hrc-voting-cite` skill if it is installed.

## Files

- `scripts/hrcv.py` — the CLI (selftest included).
- `assets/data/` — gzipped CSVs, `countries.csv`, `meta.json` (version, snapshot date, counts).
- `references/pitfalls.md` — the reasoning behind the safeguards. Read before interpretive claims.
- `references/known-gaps.md` — what the catalogue lacks, with figures verified against the Council's session reports.
- `references/schema.md` — columns and vote codes.
- `references/verification.md` — how to check a published figure against the session reports.
