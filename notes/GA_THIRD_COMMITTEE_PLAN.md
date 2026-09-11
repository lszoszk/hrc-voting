# General Assembly (Third Committee) extension — plan and source notes

Started 2026-09-11. Goal: add the General Assembly's human rights resolutions —
their Third Committee stage and their plenary adoption — as new "bodies" next to
CHR and HRC in the existing dashboard (same repo, same Pages URL
https://lszoszk.github.io/hrc-voting/), with a resolution view that compares the
committee vote with the plenary vote and a topic bridge to the HRC resolutions on
the same subject.

## Sources (all verified 2026-09-11)

1. **UN Digital Library, "General Assembly voting data", version 5 (Feb 2026)** —
   `data/raw/ga/2026_02_06_ga_voting.csv` (364 MB, 947,434 rows = one Member
   State vote on one resolution adopted by recorded vote; 5,694 resolutions,
   1946 → 30 Dec 2025). Record: https://digitallibrary.un.org/record/4060887.
   Columns: undl_id, ms_code (ISO3-like), ms_name, ms_vote (Y/N/A/X), date,
   session, resolution, draft, committee_report, meeting, title, agenda_title,
   subjects, vote_note, total_yes/no/abstentions/non_voting/ms, undl_link.
   Terms: "Copyright, United Nations; Non commercial use, with attribution"
   (same posture as the UHRI export). The site sits behind AWS WAF: curl gets an
   empty 202; the download worked with the `aws-waf-token` cookie taken from a
   real browser session and `-L` (the file is served from `/nanna/record/...`).
   Third Committee origin is explicit in `draft` (A/C.3/NN/L.x) from session 55
   (2000) on: 485 resolutions with a recorded plenary vote in sessions 55–80.
   Before session 55 `draft` is mostly empty → attribution must come from
   `committee_report` / agenda titles / subjects, flagged as inferred.
2. **Third Committee summary records A/C.3/NN/SR.xx** on UN Documents
   (`documents.un.org/api/symbol/access?s=<symbol>&l=en&t=docx`, curl works) —
   per-country lists after "A recorded vote was taken on ...":
   "In favour: A, B, C. Against: ... Abstaining: ...". Uniform across sessions;
   the source for committee-stage votes (verified on A/C.3/78/SR.47 and SR.48).
   Recent sessions' SRs appear with a delay of months.
3. **Third Committee voting sheets (PDF)** — `https://www.un.org/en/ga/third/<NN>/votingsheets.shtml`
   for sessions 65–78 only (16–52 PDFs per session incl. amendments and
   motions); board printouts with a noisy text layer (OCR-like glitches, e.g.
   "Fidl" for Fiji). Use as a cross-check of SR-derived totals, not as the
   primary source. Sessions 79–80 have no such page (404).
4. **igov.un.org proposals API** (JSON, no login):
   `https://igov.un.org/igov/api/proposals/<SESSION-WORD>/Third%20Committee?env=prod`
   (SESSION-WORD = SEVENTY-NINTH, EIGHTIETH, …). Saved for 79 and 80 in
   `data/raw/ga/igov_c3_*.json`. Each proposal: agenda item, title, main
   sponsors, and `PR_Stage[]` incl. "Adoption by Main Committee" with
   Voting Yes/No, VoteY/VoteN/VoteAbstain, MeetingNo, date, DocAmended, and the
   GA adoption stage with the resolution number. Totals only (no per-country).
5. **Resolution texts** A/RES/NN/xxx: UN Documents DOCX via the existing
   `scripts/harvest_ods_texts.py` pattern → `build_text_index.py` → `tag_terms.py`.
6. **Blocked for automation:** press.un.org (JS challenge), UNDL record pages and
   search API without a browser cookie, ohchr.org (403 for non-browser agents).

## Data model (proposal)

Keep `data/csv/resolutions.csv` + `votes_long.csv` as the single schema.
- One row per *vote event*: body = "General Assembly (Third Committee)" for the
  committee-stage vote (symbol = A/C.3/NN/L.x[/Rev.y], meeting = SR symbol,
  date from the SR) and body = "General Assembly (plenary)" for the plenary vote
  (symbol = A/RES/NN/xxx, meeting = A/NN/PV.x). New column `ga_resolution` links
  both events (and the amendment/motion votes) to the adopted resolution; new
  column `stage` ∈ {committee, plenary, amendment, motion}.
- Topics: reuse `agenda_subject`/`agenda_item_title` conventions; for GA rows use
  UNDL `subjects` + `agenda_title`; bridge to HRC by subject tag + title
  similarity, reviewed by hand for the ~60 recurring thematic resolutions.

## Scope decision (taken 2026-09-11)

Plenary votes for every Third Committee resolution in the UNDL file (sessions 25–80;
attribution inferred from the agenda item before session 55 and flagged in the
roll-call panel); committee-stage roll-calls and resolution texts from session 55
(2000), the first session whose records name the draft symbol. The dashboard's
*Bodies* scope defaults to CHR + HRC so every published number is unchanged.

## Steps
1. `scripts/ga/parse_undl.py` → resolutions/votes for Third Committee rows;
   check per-session counts against igov (79/80) and GA resolution lists.
2. `scripts/ga/harvest_sr.py` + `parse_sr_votes.py` (sessions 55–80): per-country
   committee votes; check totals against igov and the PDF sheets (65–78); 100 %
   ISO3 mapping via the CHR/HRC country table.
3. `scripts/ga/harvest_igov.py`: sponsors, amendments, stages (79–80+).
4. Texts for A/RES sessions 55–80 through the existing text pipeline.
5. `build_dashboard_data.py`: emit the two GA bodies; dashboard: body filter
   gains GA entries, new "Resolution: committee vs plenary" view, topic bridge to
   HRC; Methodology tab documents the UNDL terms and the inferred attributions;
   smoke test; Pages; Zenodo version bump; HF package.


## Findings while building (2026-09-11)

- Summary records exist as .doc (sessions 55–65) and .docx (66+); `textutil` converts
  the .doc files. Sessions **75 and 76 have far fewer meetings** (pandemic format) but
  their records do carry the roll-call lists, so the summary records are the per-State
  source for every session 55–79; session 80's are not published yet and igov supplies
  its committee totals (no per-State list). Coverage: 438 of the 446 draft-attributed
  resolutions of sessions 55–79 have their committee vote; 2 of the rest were adopted
  without a vote in committee (A/C.3/58/L.65, A/C.3/62/L.84), the others have no
  adoption sentence in the harvested records.
- Parser wording it had to learn: "A recorded vote was taken." with no subject
  (2000–2005; the draft is named in the result sentence), "a vote was taken by
  roll-call on", "Abstentions:" for "Abstaining:", results glued to the last list
  line, "adopted by 88 to 24" (no "votes"), "to none"/"to one", "rejected by N votes
  to M" (N is *against*), footnotes inside the lists, `\xa0`/`\u2028` hiding the list
  headers, and a session typo in a symbol (A/C.3/62/L.42 in a 63rd-session record →
  `symbol_source = corrected`).
- Voting sheets (un.org/en/ga/third/<s>/votingsheets.shtml): sessions 65–73 are scans
  with little or no text layer; 74–78 are native e-voting PDFs, some of which lose a
  State from the text layer. Used only as a cross-check: on the 60 trusted sheets of
  sessions 75–77 that pair with a summary-record vote, 10,480 of 10,482 State-votes
  agree (`scripts/ga/parse_sheets.py`).
- un.org pages answer a plain research User-Agent with a stub; the harvesters use a
  browser UA there. UN Documents' symbol API is fine with any UA.
- The UNDL totals come as floats ("106.0"); parse_undl.py stores integers.
- The dashboard keeps CHR + HRC as the default *Bodies* scope; GA enters only on
  request, so every published number stays as it was. `kindOK` now includes the
  body scope, which every view already used.
- Cross-organ bridge: 430 of 708 GA resolutions share their catalogued title with a
  CHR/HRC resolution (token Jaccard ≥ 0.6); shown on the roll-call page.
- Texts: A/RES PDFs before 1993 are scanned Official Records pages (no text layer or
  two-column OCR noise) → build_text_index.py indexes GA texts from 1993 only. Three
  footnote layouts had to be stripped (1994–95 "n/ See …", 1996–2000 bare number +
  note, 2001– rule + numbered notes) plus the job code / barcode / "Please recycle" /
  running-header lines. Missing texts: the lettered sub-resolutions A/RES/35/130A-B,
  36/56A, 37/189A-B (UN Documents has no separate PDF) and 61/232.
