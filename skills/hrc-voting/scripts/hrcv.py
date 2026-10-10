#!/usr/bin/env python3
"""Query the HRC Voting dataset: how States voted at the UN Commission on Human Rights
(1946-2006), the Human Rights Council (2006-) and, separately, the General Assembly's
Third Committee (plenary votes from 1970).

    python hrcv.py info
    python hrcv.py search "death penalty" --years 2010-2024
    python hrcv.py resolution A/HRC/RES/48/1
    python hrcv.py country Poland --by-year --list 10
    python hrcv.py partners Poland
    python hrcv.py compare Poland Hungary --years 2006-2026
    python hrcv.py adoption --body hrc
    python hrcv.py amendments --years 2020-2024
    python hrcv.py gaps
    python hrcv.py refresh            # needs network; otherwise the bundled snapshot is used

Standard library only. Defaults encode the dataset's safeguards: amendments are left out
of resolution counts, an abstention is never a vote against, and every answer states its
scope so the reader can see what was and was not counted. See ../references/pitfalls.md.
"""
import argparse
import csv
import gzip
import json
import os
import re
import sys
import unicodedata
import urllib.request
from collections import Counter, defaultdict
from pathlib import Path

SKILL = Path(__file__).resolve().parent.parent
BUNDLED = SKILL / "assets" / "data"
CACHE = Path(os.environ.get("HRCV_CACHE", Path.home() / ".cache" / "hrc-voting"))
RAW = "https://raw.githubusercontent.com/lszoszk/hrc-voting/main/data/csv/"
FILES = ["resolutions.csv", "votes_long.csv", "ga_resolutions.csv", "ga_votes_long.csv"]
SITE = "https://lszoszk.github.io/hrc-voting"
POS = {"Y": "Yes", "N": "No", "A": "Abstain"}
BODY = {"chr": "Commission on Human Rights", "hrc": "Human Rights Council"}


# ---------------------------------------------------------------- data access
def data_dir(arg=None):
    for cand in (arg, os.environ.get("HRCV_DATA")):
        if cand:
            return Path(cand), "user-supplied directory"
    if all((CACHE / f).exists() for f in FILES):
        return CACHE, "refreshed copy in " + str(CACHE)
    return BUNDLED, "bundled snapshot"


def open_csv(name, d):
    p = d / name
    if p.exists():
        return csv.DictReader(open(p, encoding="utf-8", newline=""))
    return csv.DictReader(gzip.open(d / (name + ".gz"), "rt", encoding="utf-8", newline=""))


def trim_title(t):
    return re.sub(r"\s*:\s*(draft\s+)?(resolution|decision|amendment)s?\s*/.*$", "", (t or "").strip(), flags=re.I).strip()


def is_amendment(r):
    return bool(re.search(r":\s*amendment", r["title"], re.I) or re.match(r"\s*amendment", r.get("draft", ""), re.I))


def slugify(s):
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")


class Data:
    def __init__(self, arg=None):
        d, self.source = data_dir(arg)
        meta = BUNDLED / "meta.json"
        self.meta = json.loads(meta.read_text()) if meta.exists() else {}
        self.res = {}
        for r in open_csv("resolutions.csv", d):
            r["am"] = is_amendment(r)
            self.res[r["record_id"]] = r
        self.cast, self.absent = defaultdict(dict), defaultdict(list)
        self.names = {}
        for v in open_csv("votes_long.csv", d):
            if v["vote"] in POS:
                self.cast[v["record_id"]][v["iso3"]] = v["vote"]
            elif v["vote"] == ".":
                self.absent[v["record_id"]].append(v["iso3"])
            self.names.setdefault(v["iso3"], v["country"].title())
        self.ga = {r["undl_id"]: r for r in open_csv("ga_resolutions.csv", d)}
        self.ga_cast, self.ga_absent = defaultdict(dict), defaultdict(list)
        for v in open_csv("ga_votes_long.csv", d):
            if v["vote"] in POS:
                self.ga_cast[v["undl_id"]][v["iso3"]] = v["vote"]
            elif v["vote"] == ".":
                self.ga_absent[v["undl_id"]].append(v["iso3"])
            self.names.setdefault(v["iso3"], v["country"].title())
        self.countries = {}
        cp = BUNDLED / "countries.csv"
        if cp.exists():
            for c in csv.DictReader(open(cp, encoding="utf-8")):
                self.countries[c["iso3"]] = c
        for iso, nm in self.names.items():
            self.countries.setdefault(iso, {"iso3": iso, "name": nm, "group": "", "historical": "0"})

    def cname(self, iso):
        return self.countries.get(iso, {}).get("name") or self.names.get(iso, iso)

    def find_country(self, q):
        q0 = q.strip()
        if q0.isupper() and q0 in self.countries:      # "GER" is a code (West Germany); "Ger" is a name prefix
            return q0
        ql = q0.lower()
        exact = [i for i, c in self.countries.items() if c["name"].lower() == ql]
        if exact:
            return exact[0]
        hits = [i for i, c in self.countries.items() if c["name"].lower().startswith(ql)] or \
               [i for i, c in self.countries.items() if ql in c["name"].lower()]
        if len(hits) == 1:
            return hits[0]
        sys.exit(f"Country '{q}' is {'ambiguous: ' + ', '.join(f'{self.cname(i)} ({i})' for i in hits[:8]) if hits else 'not found'}. Use the ISO3 code.")

    def scope_resolutions(self, body="both", years=None, amendments=False):
        """Recorded CHR/HRC records that have a per-country roll-call."""
        out = []
        for rid, r in self.res.items():
            if rid not in self.cast or (r["am"] and not amendments):
                continue
            if body in BODY and r["body"] != BODY[body]:
                continue
            if years and not (years[0] <= int(r["year"] or 0) <= years[1]):
                continue
            out.append(r)
        return sorted(out, key=lambda r: (r["date"], r["symbol"]))


def parse_years(s):
    if not s:
        return None
    m = re.fullmatch(r"(\d{4})(?:\s*[-–:]\s*(\d{4}))?", s.strip())
    if not m:
        sys.exit("--years takes YYYY or YYYY-YYYY")
    return int(m.group(1)), int(m.group(2) or m.group(1))


def pct(a, b):
    return f"{round(100 * a / b)}%" if b else "–"


def scope_line(body, years, amendments):
    b = {"both": "CHR + HRC", "chr": "CHR only", "hrc": "HRC only"}[body]
    y = f", {years[0]}–{years[1]}" if years else ""
    return f"Scope: {b}{y}; recorded votes only; " + ("resolutions AND amendments" if amendments else "amendments excluded") + "."


def footer(d):
    print(f"\n[data: {d.source}; v{d.meta.get('version', '?')}, {d.meta.get('snapshot_date', '?')}. "
          f"Known catalogue gaps: run `hrcv.py gaps`.]")


# ---------------------------------------------------------------- commands
def cmd_info(d, a):
    m = d.meta
    rec = [r for r in d.res.values() if r["record_id"] in d.cast]
    print(f"HRC Voting dataset v{m.get('version')} (snapshot of {m.get('snapshot_date')}; DOI 10.5281/zenodo.21281232)")
    print(f"  CHR/HRC catalogue records: {len(d.res):,} (of which {sum(r['am'] for r in d.res.values()):,} amendments)")
    cast = sum(len(v) for v in d.cast.values())
    print(f"  with a per-country roll-call: {len(rec):,}; {m.get('country_votes', cast):,} country-vote rows, of which {cast:,} are Yes/No/Abstain (the rest: absent or no position)")
    print(f"  General Assembly plenary resolutions (recorded vote, Third Committee texts): {len(d.ga):,}; State votes {sum(len(v) for v in d.ga_cast.values()):,} cast")
    print(f"  loaded from: {d.source}")
    print("  Not in this snapshot: GA Third Committee committee-stage votes (see the Hugging Face dataset, configs ga_committee_*), resolution texts.")


def cmd_search(d, a):
    years, q = parse_years(a.years), a.term.lower()
    rows = []
    for rid, r in d.res.items():
        if r["am"] and not a.amendments:
            continue
        if a.body in BODY and r["body"] != BODY[a.body]:
            continue
        if years and not (years[0] <= int(r["year"] or 0) <= years[1]):
            continue
        if a.mode == "recorded" and rid not in d.cast:
            continue
        if a.mode == "consensus" and r["vote_type"] != "ADOPTED WITHOUT VOTE":
            continue
        hay = " ".join([r["symbol"], r["title"], r["agenda_subject"], r["agenda_item_title"]]).lower()
        if all(w in hay for w in q.split()):
            rows.append(r)
    rows.sort(key=lambda r: (r["date"], r["symbol"]))
    print(f"{len(rows)} match(es) for '{a.term}' (amendments {'included' if a.amendments else 'excluded'}).")
    for r in rows[-a.limit:] if a.latest else rows[:a.limit]:
        t = Counter(d.cast.get(r["record_id"], {}).values())
        res = f"Y{t['Y']} N{t['N']} A{t['A']}" if r["record_id"] in d.cast else r["vote_type"].lower()
        print(f"  {r['date']}  {r['symbol']:<22} {trim_title(r['title'])[:80]}  [{res}]")
    if len(rows) > a.limit:
        print(f"  … {len(rows) - a.limit} more (raise --limit, or narrow with --years/--body)")
    footer(d)


def find_resolution(d, sym):
    s = sym.strip().lower()
    hits = [r for r in d.res.values() if r["symbol"].lower() == s] or [r for r in d.res.values() if s in r["symbol"].lower()]
    ga = [r for r in d.ga.values() if r["symbol"].lower() == s] or [r for r in d.ga.values() if s in r["symbol"].lower()]
    return hits, ga


def cmd_resolution(d, a):
    hits, ga = find_resolution(d, a.symbol)
    if not hits and not ga:
        sys.exit(f"No record with a symbol containing '{a.symbol}'. Try `search`.")
    if len(hits) + len(ga) > 1 and not any(h["symbol"].lower() == a.symbol.lower() for h in hits + ga):
        print("Several records match; narrow the symbol:")
        for r in (hits + ga)[:15]:
            print("  ", r["symbol"], "·", trim_title(r["title"])[:70])
        return
    if hits:
        r = hits[0]; rid = r["record_id"]
        cast, absent = d.cast.get(rid, {}), d.absent.get(rid, [])
    else:
        r = ga[0]; rid = r["undl_id"]
        cast, absent = d.ga_cast.get(rid, {}), d.ga_absent.get(rid, [])
    print(f"{r['symbol']} — {trim_title(r['title'])}")
    print(f"  date {r['date']} · {r['body']}" + (" · AMENDMENT (not a resolution; a Yes may oppose the parent text)" if r.get("am") else ""))
    for k, lab in (("agenda_subject", "subject"), ("main_sponsors", "main sponsors"), ("agenda_item_title", "agenda item")):
        if r.get(k, "").strip():
            print(f"  {lab}: {r[k].strip().rstrip(' -–—')}")
    t = Counter(cast.values())
    if cast:
        outcome = "rejected" if "reject" in (r.get("statement") or "").lower() else ("adopted" if t["Y"] > t["N"] else "not adopted" if t["N"] > t["Y"] else "tied")
        print(f"  recorded vote: {t['Y']} Yes, {t['N']} No, {t['A']} abstentions ({outcome}); {len(absent)} absent/not participating")
        for code, lab in (("Y", "Yes"), ("N", "No"), ("A", "Abstained")):
            print(f"  {lab}: " + ", ".join(sorted(d.cname(i) for i, v in cast.items() if v == code)))
        if absent:
            print("  Absent: " + ", ".join(sorted(d.cname(i) for i in absent)))
    else:
        print(f"  no per-country roll-call in the dataset (vote type: {r.get('vote_type') or 'n/a'}; official totals Y{r.get('yes') or '–'} N{r.get('no') or '–'} A{r.get('abstain') or '–'})")
    if r.get("record_url"):
        print(f"  source record: {r['record_url']}")
    if hits and not r["am"] and cast:
        print(f"  page: {SITE}/resolution/{slugify(r['symbol'])}/")
    footer(d)


def country_votes(d, iso, body, years, amendments):
    rows = []
    for r in d.scope_resolutions(body, years, amendments):
        v = d.cast[r["record_id"]].get(iso)
        if v:
            rows.append((r, v))
    return rows


def cmd_country(d, a):
    iso = d.find_country(a.country)
    c = d.countries[iso]
    years = parse_years(a.years)
    if a.body == "ga":
        rows = [(r, d.ga_cast[rid][iso]) for rid, r in d.ga.items() if iso in d.ga_cast.get(rid, {}) and (not years or years[0] <= int(r["year"]) <= years[1])]
        rows.sort(key=lambda x: x[0]["date"])
        scope = "General Assembly plenary, resolutions adopted by recorded vote (Third Committee texts); NOT combined with CHR/HRC"
    else:
        rows = country_votes(d, iso, a.body, years, a.amendments)
        scope = scope_line(a.body, years, a.amendments)[7:]
    print(f"{d.cname(iso)} ({iso})" + (f" — {c['group']} group" if c.get("group") else "") + (" — historical state" if c.get("historical") == "1" else ""))
    print(f"Scope: {scope}")
    if not rows:
        print("No recorded votes in this scope."); footer(d); return
    t = Counter(v for _, v in rows); n = len(rows)
    yrs = [int(r["year"]) for r, _ in rows]
    if a.body == "ga":
        absent = sum(1 for rid, r in d.ga.items() if iso in d.ga_absent.get(rid, []) and (not years or years[0] <= int(r["year"]) <= years[1]))
    else:
        absent = sum(1 for r in d.scope_resolutions(a.body, years, a.amendments) if iso in d.absent.get(r["record_id"], []))
    print(f"Votes cast: {n:,} ({min(yrs)}–{max(yrs)}): Yes {t['Y']:,} ({pct(t['Y'], n)}), No {t['N']:,} ({pct(t['N'], n)}), Abstain {t['A']:,} ({pct(t['A'], n)}); "
          f"recorded absent / not participating in {absent:,} more roll-calls (not a position)")
    if a.by_year:
        by = defaultdict(Counter)
        for r, v in rows:
            by[int(r["year"])][v] += 1
        print("Year  votes  Yes  No  Abstain")
        for y in sorted(by):
            c_ = by[y]; print(f"{y}  {sum(c_.values()):>5}  {c_['Y']:>3}  {c_['N']:>2}  {c_['A']:>7}")
    if a.list:
        print(f"Latest {min(a.list, n)} votes:")
        for r, v in rows[-a.list:][::-1]:
            print(f"  {r['date']}  {POS[v]:<7} {r['symbol']:<22} {trim_title(r['title'])[:70]}")
    if a.body != "ga":
        print(f"Dashboard: {SITE}/#country={iso}   Page: {SITE}/country/{slugify(d.cname(iso))}/")
    footer(d)


def agreement(d, i, j, rows_scope):
    sh = same = 0
    for r in rows_scope:
        c = d.cast[r["record_id"]]
        if i in c and j in c:
            sh += 1; same += c[i] == c[j]
    return same, sh


def cmd_partners(d, a):
    iso, years = d.find_country(a.country), parse_years(a.years)
    scope = d.scope_resolutions(a.body, years, False)
    mine = [r for r in scope if iso in d.cast[r["record_id"]]]
    others = {i for r in mine for i in d.cast[r["record_id"]] if i != iso}
    sc = []
    for j in others:
        same, sh = agreement(d, iso, j, mine)
        if sh >= a.min_shared:
            sc.append((same / sh, sh, j))
    sc.sort(key=lambda x: (-x[0], -x[1]))
    print(f"Voting partners of {d.cname(iso)} ({iso}). {scope_line(a.body, years, False)}")
    print(f"Agreement = share of shared votes with the same position (Yes/No/Abstain); partners need ≥{a.min_shared} shared votes. {len(mine)} votes cast by {d.cname(iso)}.")
    print("Closest:")
    for s, sh, j in sc[:a.top]:
        print(f"  {d.cname(j):<28} {round(100 * s):>3}%  of {sh} shared")
    print("Furthest:")
    for s, sh, j in sc[::-1][:a.top]:
        print(f"  {d.cname(j):<28} {round(100 * s):>3}%  of {sh} shared")
    print("Caution: raw agreement is inflated when most votes are lopsided (chance agreement); read it as descriptive.")
    footer(d)


def cmd_compare(d, a):
    i, j, years = d.find_country(a.a), d.find_country(a.b), parse_years(a.years)
    scope = [r for r in d.scope_resolutions(a.body, years, False) if i in d.cast[r["record_id"]] and j in d.cast[r["record_id"]]]
    same = sum(d.cast[r["record_id"]][i] == d.cast[r["record_id"]][j] for r in scope)
    print(f"{d.cname(i)} vs {d.cname(j)}. {scope_line(a.body, years, False)}")
    if not scope:
        print("No shared recorded votes."); footer(d); return
    print(f"Shared votes: {len(scope)}; same position: {same} ({pct(same, len(scope))}).")
    by = Counter(int(r["year"]) for r in scope)
    print("Shared votes fall in: " + ", ".join(f"{y} ({n})" for y, n in sorted(by.items())) +
          ". Only members vote, so compare two such rates only when the overlap years are alike.")
    opp = [r for r in scope if {d.cast[r['record_id']][i], d.cast[r['record_id']][j]} == {"Y", "N"}]
    print(f"Directly opposed (one Yes, one No): {len(opp)} ({pct(len(opp), len(scope))}).")
    diff = [r for r in scope if d.cast[r["record_id"]][i] != d.cast[r["record_id"]][j]]
    for r in diff[-a.list:][::-1]:
        print(f"  {r['date']}  {d.cname(i)}: {POS[d.cast[r['record_id']][i]]:<7} {d.cname(j)}: {POS[d.cast[r['record_id']][j]]:<7} {r['symbol']}  {trim_title(r['title'])[:50]}")
    footer(d)


def cmd_adoption(d, a):
    years = parse_years(a.years)
    rows = [r for r in d.res.values() if not r["am"] and r["vote_type"] not in ("WITHDRAWN", "NOT CONSIDERED")
            and (a.body == "both" or r["body"] == BODY.get(a.body)) and (not years or years[0] <= int(r["year"] or 0) <= years[1])]
    by = defaultdict(Counter)
    for r in rows:
        by[int(r["year"])]["free" if r["vote_type"] == "ADOPTED WITHOUT VOTE" else "voted" if r["record_id"] in d.cast or r["vote_type"].startswith("RECORDED") else "other"] += 1
    tot = Counter()
    print(f"Adoption modes, considered texts only (withdrawn / not-considered drafts and amendments excluded). Body: {a.body}.")
    print("Year  texts  without-a-vote  recorded-vote  other")
    for y in sorted(by):
        c = by[y]; n = sum(c.values()); tot.update(c)
        print(f"{y}  {n:>5}  {pct(c['free'], n):>14}  {pct(c['voted'], n):>13}  {c['other']:>5}")
    n = sum(tot.values())
    print(f"Total: {n:,} texts; adopted without a vote {pct(tot['free'], n)}; recorded vote {pct(tot['voted'], n)}.")
    print("Caution: 'without a vote' is not unanimity (delegations can dissociate), and 'other' = non-recorded votes, mostly Commission-era.")
    footer(d)


def amendment_outcome(r, has_rollcall):
    t = (r.get("draft") or "").lower()
    if r["vote_type"] == "WITHDRAWN" or "withdrawn" in t:
        return "withdrawn"
    if r["vote_type"] == "NOT CONSIDERED" or "not considered" in t:
        return "not acted upon"
    if "no action" in t:
        return "no-action motion"
    if "rejected" in t:
        return "rejected"
    if "adopted" in t:
        return "adopted"
    if has_rollcall:
        try:
            return "adopted" if int(r["yes"]) > int(r["no"]) else "rejected"
        except ValueError:
            pass
    return "unclassified"


def cmd_amendments(d, a):
    years = parse_years(a.years)
    by = defaultdict(Counter)
    for rid, r in d.res.items():
        if not r["am"] or (years and not (years[0] <= int(r["year"] or 0) <= years[1])) or (a.body in BODY and r["body"] != BODY[a.body]):
            continue
        by[int(r["year"])][amendment_outcome(r, rid in d.cast)] += 1
    kinds = ["rejected", "adopted", "withdrawn", "not acted upon", "no-action motion", "unclassified"]
    print("Amendments to draft texts by outcome (Human Rights Council records, catalogue-based).")
    print("Year  total  " + "  ".join(f"{k[:8]:>8}" for k in kinds))
    tot = Counter()
    for y in sorted(by):
        c = by[y]; tot.update(c)
        print(f"{y}  {sum(c.values()):>5}  " + "  ".join(f"{c[k]:>8}" for k in kinds))
    print(f"Total {sum(tot.values())}: " + ", ".join(f"{k} {tot[k]}" for k in kinds if tot[k]))
    print("Caution: the catalogue omits 21 amendments in 2020-2024 (A/HRC/48/L.49-57, 49/L.43, 11 from session 56): run `gaps`.")
    footer(d)


def cmd_gaps(d, a):
    p = SKILL / "references" / "known-gaps.md"
    print(p.read_text(encoding="utf-8") if p.exists() else "references/known-gaps.md is missing.")


def cmd_refresh(d, a):
    CACHE.mkdir(parents=True, exist_ok=True)
    for f in FILES:
        print("downloading", f, "…", flush=True)
        urllib.request.urlretrieve(RAW + f, CACHE / f)
    print(f"Refreshed copy written to {CACHE}. Delete that folder to go back to the bundled snapshot.")


# ---------------------------------------------------------------- selftest
def cmd_selftest(d, a):
    """Golden values from the v1.2.0 snapshot; a failure means the data or the logic changed."""
    fails = []

    def eq(label, got, want):
        if got != want:
            fails.append(f"{label}: got {got!r}, want {want!r}")
    eq("catalogue records", len(d.res), 6392)
    eq("records with roll-call", sum(1 for rid in d.res if rid in d.cast), 1716)
    eq("amendments", sum(r["am"] for r in d.res.values()), 749)
    r48 = next(r for r in d.res.values() if r["symbol"] == "A/HRC/RES/48/1")
    eq("A/HRC/RES/48/1 tally", dict(Counter(d.cast[r48["record_id"]].values())), {"Y": 28, "N": 5, "A": 14})
    pol = d.find_country("Poland")
    eq("Poland cast votes", len(country_votes(d, pol, "both", None, False)), 560)
    mine = [r for r in d.scope_resolutions("both", None, False) if pol in d.cast[r["record_id"]]]
    best = max(((agreement(d, pol, j, mine), j) for j in d.countries if j != pol and agreement(d, pol, j, mine)[1] >= 30), key=lambda x: x[0][0] / x[0][1])
    eq("Poland's closest partner", d.cname(best[1]), "Latvia")
    am = Counter()
    for rid, r in d.res.items():
        if r["am"] and 2020 <= int(r["year"] or 0) <= 2024:
            am[amendment_outcome(r, rid in d.cast)] += 1
    eq("amendments adopted 2020-2024", am["adopted"], 5)
    eq("amendments 2020", sum(1 for r in d.res.values() if r["am"] and r["year"] == "2020"), 58)
    eq("GA plenary resolutions", len(d.ga), 708)
    if fails:
        print("SELFTEST: FAIL"); [print("  ✗", f) for f in fails]; sys.exit(1)
    print(f"SELFTEST: OK (data: {d.source}, v{d.meta.get('version', '?')})")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--data", help="directory with the four CSVs (plain or .gz) instead of the bundled snapshot")
    sub = ap.add_subparsers(dest="cmd", required=True)

    def add(name, fn, help_):
        p = sub.add_parser(name, help=help_); p.set_defaults(fn=fn); return p
    add("info", cmd_info, "what the dataset holds")
    p = add("search", cmd_search, "find resolutions by words in symbol/title/subject")
    p.add_argument("term"); p.add_argument("--years"); p.add_argument("--body", choices=["chr", "hrc", "both"], default="both")
    p.add_argument("--mode", choices=["all", "recorded", "consensus"], default="all"); p.add_argument("--amendments", action="store_true")
    p.add_argument("--limit", type=int, default=25); p.add_argument("--latest", action="store_true")
    p = add("resolution", cmd_resolution, "one resolution: totals and how each State voted"); p.add_argument("symbol")
    p = add("country", cmd_country, "a State's voting record")
    p.add_argument("country"); p.add_argument("--years"); p.add_argument("--body", choices=["chr", "hrc", "both", "ga"], default="both")
    p.add_argument("--amendments", action="store_true"); p.add_argument("--by-year", action="store_true"); p.add_argument("--list", type=int, default=0)
    p = add("partners", cmd_partners, "closest and furthest voting partners")
    p.add_argument("country"); p.add_argument("--years"); p.add_argument("--body", choices=["chr", "hrc", "both"], default="both")
    p.add_argument("--min-shared", type=int, default=30); p.add_argument("--top", type=int, default=8)
    p = add("compare", cmd_compare, "two States head to head"); p.add_argument("a"); p.add_argument("b")
    p.add_argument("--years"); p.add_argument("--body", choices=["chr", "hrc", "both"], default="both"); p.add_argument("--list", type=int, default=10)
    p = add("adoption", cmd_adoption, "adopted without a vote vs recorded vote, by year")
    p.add_argument("--years"); p.add_argument("--body", choices=["chr", "hrc", "both"], default="hrc")
    p = add("amendments", cmd_amendments, "amendments by outcome and year"); p.add_argument("--years"); p.add_argument("--body", choices=["chr", "hrc"], default="hrc")
    add("gaps", cmd_gaps, "known gaps in the OHCHR catalogue")
    add("refresh", cmd_refresh, "download the latest CSVs from GitHub (needs network)")
    add("selftest", cmd_selftest, "check the bundled data against golden values")
    a = ap.parse_args()
    if a.cmd in ("gaps", "refresh"):
        a.fn(None, a); return
    a.fn(Data(a.data), a)


if __name__ == "__main__":
    main()
