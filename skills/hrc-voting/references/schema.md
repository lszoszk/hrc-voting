# Data schema (bundled snapshot = data/csv of the repository)

## resolutions.csv — one row per catalogued CHR/HRC record (6,392)
`record_id` (stable OHCHR id; `record_url` links to it), `symbol` (e.g. A/HRC/RES/48/1, A/HRC/48/L.59 for an amendment,
E/CN.4/RES/1999/3), `title` (catalogue boilerplate ": resolution /…" — trim it), `statement`, `date`, `year`,
`body` (Commission on Human Rights | Human Rights Council), `vote_type`
(ADOPTED WITHOUT VOTE · RECORDED · NON-RECORDED · NON-RECORDED, adopted unanimously · WITHDRAWN · NOT CONSIDERED · …),
`agenda_subject` (OHCHR's controlled subject heading), `agenda_item_title`, `main_sponsors`, `draft` (for amendments:
"Amendment A/HRC/48/L.59 to draft resolution A/HRC/48/L.8 ADOPTED by a recorded vote"), `yes` `no` `abstain`
`nonvoting` `total` (official totals), `n_rollcall`, `url_resolution`, `url_draft`, `record_url`.
Amendment test: title contains ": amendment /" or `draft` starts with "Amendment" (749 records).

## votes_long.csv — one row per State per recorded resolution (80,676)
`record_id`, `symbol`, `date`, `year`, `body`, `vote_type`, `seq`, `iso3`, `country`, `vote`:
`Y` Yes · `N` No · `A` Abstain · `.` absent or not participating · empty = not a member / no position recorded.
Only Y, N, A are positions.

## ga_resolutions.csv / ga_votes_long.csv — General Assembly plenary (708 resolutions)
Resolutions adopted by recorded vote on texts that came out of the Third Committee, sessions 25–80 (1970–2025),
from the UN Dag Hammarskjöld Library's General Assembly voting data, version 5. Keys: `undl_id`, `symbol`
(A/RES/2647(XXV)), `session`, `draft` (A/C.3/…), `yes` `no` `abstain` `nonvoting`; votes use the same codes.
Consensus adoptions are NOT in the source, so no "without a vote" statistics exist for the Assembly.

## countries.csv — iso3, name, UN regional group (as used in the dashboard), historical-state flag
Historical states (Czechoslovakia, USSR, East/West Germany, Yugoslavia, Serbia and Montenegro, Yemen PDR) are separate
entries; they are not merged into their successors.

## Not bundled (online only)
Committee-stage votes (`ga_committee_events`, `ga_committee_votes`), clause-segmented resolution texts and derived
columns (`prevailing_side`, `adopted`, `rollcall_reconciles`, `is_amendment`) live in the Hugging Face dataset
`lszoszk/hrc-voting` (10 parquet configs). Per-country pages: https://lszoszk.github.io/hrc-voting/country/ .
