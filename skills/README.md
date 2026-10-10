# Claude skills for HRC Voting

Two [Agent Skills](https://docs.claude.com/en/docs/agents-and-tools/agent-skills/overview) that let Claude answer questions about
UN human-rights votes from this dataset, with the dataset's safeguards built in.

| Skill | What it does | Ask Claude things like |
|---|---|---|
| [`hrc-voting`](hrc-voting/SKILL.md) | Query and analyse how States voted at the Commission on Human Rights, the Human Rights Council and (plenary) the General Assembly's Third Committee. Bundles an **offline snapshot** (v1.2.0) and a CLI: resolution tallies, country records, voting partners, consensus vs recorded votes, amendments, known catalogue gaps, fact-checking against the Council's session reports. | "How did Poland vote at the HRC since 2006?" · "Which States vote most like Hungary?" · "Is it true only four HRC amendments were adopted in 2020–2024?" |
| [`hrc-voting-cite`](hrc-voting-cite/SKILL.md) | Cite the dataset (DOI, BibTeX, APA/OSCOLA-style), a resolution together with its vote, and write a methods or data-availability note, chart caption and licence statement. | "Give me the footnote for A/HRC/RES/48/1 with the vote." · "Write the data section for my chapter." |

The skills carry a gzipped copy of the data (1.3 MB) and work without network access. Every answer states its scope
(body, years, recorded votes only, amendments excluded) and the snapshot version.

## Install

Download the zip files (built from this folder by the Pages workflow):

- https://lszoszk.github.io/hrc-voting/skills/hrc-voting.zip
- https://lszoszk.github.io/hrc-voting/skills/hrc-voting-cite.zip

**Claude (claude.ai, Claude Desktop):** Settings → Capabilities → Skills → upload each zip (the exact menu name varies by app
version; skills need code execution enabled). **Claude Code:** unzip into your skills folder:

```bash
mkdir -p ~/.claude/skills
unzip hrc-voting.zip hrc-voting-cite.zip -d ~/.claude/skills   # or: ./.claude/skills for one project
```

In a clone of this repository, copy or link the folders from `skills/` the same way. Check an install with
`python ~/.claude/skills/hrc-voting/scripts/hrcv.py selftest`.

## Prefer a connector?

[`mcp-hrc-voting`](https://github.com/lszoszk/mcp-hrc-voting) is the same data as a Model Context Protocol server (nine read-only
tools, offline, same safeguards) for Claude Desktop, Claude Code and other MCP clients:
`claude mcp add --scope user hrc-voting -- npx -y github:lszoszk/mcp-hrc-voting`. Its golden values come from `hrcv.py`, so the
two answer identically.

## Newer data

The snapshot is the data of the release it was built for (`assets/data/meta.json`). `python scripts/hrcv.py refresh` downloads the
current CSVs from GitHub into `~/.cache/hrc-voting` (needs network) and the CLI then prefers them. Sandboxes without network
keep using the snapshot.

## For maintainers

```bash
python scripts/build_skill_snapshot.py        # refresh skills/hrc-voting/assets/data from data/csv after a re-harvest
python skills/hrc-voting/scripts/hrcv.py selftest
python scripts/check_figures.py               # fails if the snapshot or the figures quoted in the skills fall behind CITATION.cff
python scripts/package_skills.py --out dist   # what the Pages workflow publishes under /hrc-voting/skills/
```

The `selftest` golden values (6,392 records, 1,716 roll-calls, A/HRC/RES/48/1 = 28–5–14, Poland's 560 votes…) belong to v1.2.0; update them
with the snapshot at each release.

Licence: PolyForm Noncommercial 1.0.0, like the rest of the repository. The data are public UN records; HRC Voting is independent of
the United Nations.
