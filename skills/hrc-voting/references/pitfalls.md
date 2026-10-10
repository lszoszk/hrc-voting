# Pitfalls: what goes wrong with UN voting data, and why the defaults are what they are

Read this before any claim that goes beyond "State X voted Yes on text Y". Each item says what to do and why.

1. **Amendments are not resolutions.** The catalogue holds 749 amendments to draft texts, and 465 of them went to a recorded vote:
   27% of all roll-calls, almost all after 2010. A Yes on a hostile amendment often *opposes* the parent text's aim (votes
   "for" amendments to women's-rights texts are typically votes to weaken them). Pooling them with resolutions inverts
   meaning. The CLI leaves amendments out unless asked (`--amendments`) and says so in every scope line. Analyse them as
   their own population.
2. **An abstention is not a vote against.** Under the General Assembly rules the Council applies, a member that abstains is
   "considered as not voting"; the outcome turns on Yes vs No alone (a tie leaves no prevailing side). Never take
   `max(Yes, No, Abstain)` as the outcome: it scores a winning Yes bloc as defeated whenever abstentions are the plurality.
3. **Roll-call data describe contested politics, not the Council's output.** 73% of catalogued records carry no
   per-country roll-call and 60% were adopted without a vote (68% of considered non-amendment texts). A State's share of
   Yes votes among roll-calls says little about its overall behaviour. State the denominator.
4. **"Adopted without a vote" is not unanimity.** Delegations can dissociate or place reservations on record; a State can
   say it would vote against and still not call a vote. Use "adopted without a vote" or "by consensus", not "unanimously".
   Many HRC *decisions* are UPR outcomes adopted without a vote, which inflates the consensus share if mixed with resolutions.
5. **Absence, non-membership and no position are different.** `.` = absent / not participating (no position). Empty = not a
   member then, or no position recorded. Agreement between two States is computed over the votes both cast; "never voted"
   usually means "was never a member". Two agreement rates are only comparable when the overlap years are: a State may share 66 votes
   with one partner in 2010–2012 and 125 with another in 2006–2007 and 2020–2022, and both can read 100%.
6. **The Commission and the Council are different bodies.** CHR: 53 members elected by ECOSOC; HRC: 47 elected by the General
   Assembly, regional seats, membership criteria, from 2006. Read trends across 2006 with care; the dashboard marks the break.
7. **The General Assembly is a different record.** Universal membership (~193 States), plenary votes on Third Committee texts,
   and no consensus texts in the source, so there is no "adopted without a vote" statistic for it. Do not add GA and CHR/HRC
   counts together or compare raw shares across the two without saying so. Committee-stage roll-calls are separate records.
8. **Roll-call lists and official totals can disagree.** About 3% (49 votes) do not reconcile, mostly by a small margin in
   abstentions/non-participation. Treat the official totals as authoritative; the per-State list is shown as published.
9. **Historical States are separate entries** (USSR, Czechoslovakia, East and West Germany, Yugoslavia…). Do not merge
   them with successors silently.
10. **Raw agreement is inflated by lopsided votes.** Two States "agree" often by chance when most votes pass by a large majority.
    Say "voted the same way on X% of shared votes", report the number of shared votes, and avoid causal language
    ("aligned with", "follows") unless the user's question needs it and the evidence supports it.
11. **Partial years and lags.** 2026 is incomplete; the newest session may not yet be catalogued (see known-gaps.md).
12. **Counting what is counted.** "Resolutions", "decisions", presidential statements and amendments are all *records*;
    say which you mean. `search` and `country` count resolutions and decisions (amendments excluded) unless told otherwise.
