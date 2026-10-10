# Checking a published claim about HRC votes

Use this when the user asks "is this figure right?" (a post, an article, a book chapter). The dataset is a catalogue; the
authority for the Council's actions is its official report of each session.

1. **Pin the scope of the claim**: body, period, record type (resolutions / decisions / amendments / texts rejected),
   what "adopted", "withdrawn", "put to a vote" mean. Many disagreements are definitional.
2. **Reproduce it with the CLI** using the same scope (`hrcv.py amendments --years 2020-2024`, `adoption`, `country`…).
3. **If the number differs, look in `references/known-gaps.md` first.** The catalogue misses specific items for 2020–2024.
4. **Go to the source for the session.** Session reports are `A/HRC/<session>/2`:
   `https://documents.un.org/api/symbol/access?s=A/HRC/48/2&l=en&t=pdf` (PDF; open data, no login). Sessions by year:
   2020: 43–45 · 2021: 46–48 · 2022: 49–51 · 2023: 52–54 · 2024: 55–57 · 2025: 58–60 · 2026: 61–63 (63 not yet reported).
   The report narrates each action in order, e.g. "the Human Rights Council rejected amendment A/HRC/48/L.50 by 22 votes
   to 9", "amendments A/HRC/48/L.49 and L.51 … had been withdrawn by the sponsor", "was not considered … in the
   absence of co-sponsorship by members of the Council", and lists every L-document in an annex.
   Draft texts: `https://documents.un.org/api/symbol/access?s=A/HRC/48/L.11&l=en&t=pdf`.
5. **Report the comparison as a table**: claim / dataset / session reports / why they differ. Name the source for each
   number. Where the claim matches the reports and the dataset does not, say the gap is in the catalogue.
6. **Do not "fix" the dataset silently** and do not present report-derived items as part of the dataset: they are
   supplementary and cited to the report.

Reference results (checked against the reports, sessions 43–59): amendments tabled 58, 103, 85, 68, 45 in 2020–2024;
five adopted; 23 not acted upon (no Council member requested action); three draft texts rejected in 2020–2025:
A/HRC/48/L.11 (2021), A/HRC/51/L.6 (2022) and A/HRC/59/L.1/Rev.1 (2025). Sessions before 43 were not checked against
their reports, so a claim about "all rejected texts since 2006" cannot be confirmed from this skill alone.
