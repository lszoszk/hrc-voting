"""PROTOTYPE: static, crawlable pages for every country and every recorded resolution.

    python scripts/build_static_pages.py --out /path/to/site/hrc-voting

The dashboard is one JavaScript page, so a search engine or an AI crawler sees one URL
and none of the data. This writes plain HTML (no JavaScript needed to read it):

    country/                       index of countries
    country/<slug>/                one page per country: summary, year by year, voting
                                   partners, every recorded vote; votes.csv beside it
    resolution/                    index of resolutions by year
    resolution/<slug>/             one page per recorded resolution: totals, who voted how
    sitemap.xml                    every URL above plus the dashboard

Scope of the prototype: Commission and Council (CHR/HRC), recorded votes, amendments
left out (they are edit instructions, not resolutions; see Methodology 09). Standard
library only, so it can run in the Pages workflow without installing anything.
"""
import argparse
import csv
import datetime as dt
import gzip
import html
import json
import re
import time
import unicodedata
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SITE = "https://lszoszk.github.io"
MIN_VOTES = 20          # a country needs this many cast votes to get its own page
MIN_SHARED = 30         # shared votes needed before two states are called partners
POS = {"Y": "Yes", "N": "No", "A": "Abstain"}
TITLE = "UN Human Rights Voting Records — CHR · HRC · GA Third Committee"
DOI = "https://doi.org/10.5281/zenodo.21281232"

CSS = """
:root{--paper:#F2EFE8;--paper-2:#EAE6DD;--ink:#0F0F10;--ink-2:#2A2824;--dim:#525049;--line:rgba(15,15,16,.16);--accent:#a3322a;--yes:#20713c;--no:#a83a30;--abs:#a07312}
*{box-sizing:border-box}
body{margin:0;background:var(--paper);color:var(--ink);font:15px/1.6 Georgia,'Times New Roman',serif}
a{color:inherit;text-decoration-color:var(--line);text-underline-offset:2px}a:hover{color:var(--accent)}
.wrap{max-width:62rem;margin:0 auto;padding:0 20px 48px}
header.top{border-bottom:1px solid var(--line);background:var(--paper)}
header.top .wrap{display:flex;gap:18px;align-items:baseline;padding:12px 20px;flex-wrap:wrap;font:11px/1.4 ui-monospace,Menlo,monospace;letter-spacing:.12em;text-transform:uppercase}
header.top a{text-decoration:none;color:var(--dim)}header.top a.b{color:var(--ink);font-weight:700}
h1{font-size:34px;line-height:1.15;font-weight:400;margin:28px 0 6px;letter-spacing:-.01em}
h2{font:700 11px/1.4 ui-monospace,Menlo,monospace;letter-spacing:.16em;text-transform:uppercase;margin:32px 0 10px;border-bottom:1px solid var(--line);padding-bottom:6px}
.sub{font:12px/1.5 ui-monospace,Menlo,monospace;color:var(--dim);margin:0 0 14px}
p{max-width:46rem}
table{border-collapse:collapse;width:100%;font:12px/1.45 ui-monospace,Menlo,monospace}
th,td{text-align:left;padding:5px 8px;border-bottom:1px solid var(--line);vertical-align:top}
th{font-weight:700;color:var(--dim);font-size:10px;letter-spacing:.1em;text-transform:uppercase}
td.n,th.n{text-align:right;font-variant-numeric:tabular-nums}
.Y{color:var(--yes);font-weight:700}.N{color:var(--no);font-weight:700}.A{color:var(--abs);font-weight:700}.D{color:var(--dim)}
.cols{display:grid;grid-template-columns:repeat(auto-fit,minmax(15rem,1fr));gap:18px}
ul.l{list-style:none;margin:0;padding:0;font:12px/1.7 ui-monospace,Menlo,monospace}
.pill{display:inline-block;font:11px/1.4 ui-monospace,Menlo,monospace;margin:2px 6px 2px 0;white-space:nowrap}
dl{display:grid;grid-template-columns:max-content 1fr;gap:4px 18px;font:12px/1.5 ui-monospace,Menlo,monospace}dt{color:var(--dim)}dd{margin:0}
footer{border-top:1px solid var(--line);margin-top:40px;padding-top:14px;font:11px/1.6 ui-monospace,Menlo,monospace;color:var(--dim)}
.scroll{overflow-x:auto}
"""

COUNT = """<script>(function(){if(navigator.doNotTrack==='1'||window.doNotTrack==='1')return;var s=document.createElement('script');s.async=true;s.src='https://gc.zgo.at/count.js';s.dataset.goatcounter='https://lszoszk.goatcounter.com/count';document.head.appendChild(s);})();</script>"""


def slugify(s):
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")


def esc(s):
    return html.escape(str(s), quote=True)


def trim_title(t):
    return re.sub(r"\s*:\s*(draft\s+)?(resolution|decision|amendment)s?\s*/.*$", "", t.strip(), flags=re.I).strip()


def is_amendment(r):
    return bool(re.search(r":\s*amendment", r["title"], re.I) or re.match(r"\s*amendment", r.get("draft", ""), re.I))


def clip(s, n=155):
    s = " ".join(s.split())
    return s if len(s) <= n else s[:n].rsplit(" ", 1)[0].rstrip(",;:.") + "…"


def fmt(n):
    return f"{n:,}"


def pct(a, b):
    return f"{round(100 * a / b)}%" if b else "–"


def jsonld(*nodes):
    return ('<script type="application/ld+json">' +
            json.dumps({"@context": "https://schema.org", "@graph": list(nodes)}, ensure_ascii=False).replace("</", "<\\/") +
            "</script>")


def page(path, title, desc, body, base, nodes, canonical):
    url = f"{SITE}{base}{canonical}"
    return f"""<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>{esc(title)}</title>
<meta name="description" content="{esc(clip(desc))}">
<link rel="canonical" href="{url}">
<meta property="og:type" content="website"><meta property="og:site_name" content="HRC Voting"><meta property="og:title" content="{esc(title)}">
<meta property="og:description" content="{esc(desc)}"><meta property="og:url" content="{url}">
<meta property="og:image" content="{SITE}{base}/social-card.png"><meta name="twitter:card" content="summary_large_image">
<link rel="stylesheet" href="{base}/static.css">
{jsonld(*nodes)}
</head><body>
<header class="top"><div class="wrap"><a class="b" href="{base}/">UN Human Rights Voting Records</a><a href="{base}/country/">Countries</a><a href="{base}/resolution/">Resolutions</a><a href="{base}/">Open the dashboard</a></div></header>
<main class="wrap">
{body}
<footer>Source: <a href="https://searchlibrary.ohchr.org/search?c=Voting">OHCHR Library voting records</a>; independent of the UN. Data and code: <a href="https://github.com/lszoszk/hrc-voting">GitHub</a> · <a href="{DOI}">Zenodo (DOI)</a> · <a href="https://huggingface.co/datasets/lszoszk/hrc-voting">Hugging Face</a>. Licence: PolyForm Noncommercial 1.0.0. Cite as: Szoszkiewicz, Ł. (2026). {esc(TITLE)}. {DOI}. Known gaps in the catalogue are listed in the dashboard's Methodology (§06).</footer>
</main>{COUNT}
</body></html>
"""


def load():
    res = list(csv.DictReader(open(ROOT / "data/csv/resolutions.csv", encoding="utf-8")))
    votes = list(csv.DictReader(open(ROOT / "data/csv/votes_long.csv", encoding="utf-8")))
    raw = (ROOT / "dashboard/data.js").read_text(encoding="utf-8")
    payload = json.loads(raw[len("window.DATA = "):].rstrip().rstrip(";"))
    return res, votes, payload


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True, help="directory that will be served at /hrc-voting/")
    ap.add_argument("--base", default="/hrc-voting")
    a = ap.parse_args()
    t0 = time.time()
    out, base = Path(a.out), a.base.rstrip("/")
    res, votes, payload = load()
    groups = payload["meta"]["groupLabels"]
    cinfo = {c["iso3"]: c for c in payload["countries"]}

    # ---- which resolutions get a page ------------------------------------------------
    byrec = {r["record_id"]: r for r in res}
    cast = defaultdict(dict)          # record_id -> iso3 -> Y/N/A
    absent = defaultdict(list)        # record_id -> [iso3 not participating]
    names = {}
    for v in votes:
        names[v["iso3"]] = v["country"].title()
        if v["vote"] in POS:
            cast[v["record_id"]][v["iso3"]] = v["vote"]
        elif v["vote"] == ".":
            absent[v["record_id"]].append(v["iso3"])
    pages = [r for r in res if r["record_id"] in cast and not is_amendment(r)]
    pages.sort(key=lambda r: (r["date"], r["symbol"]))
    slugs, used = {}, Counter()
    for r in pages:
        s = slugify(r["symbol"]) or r["record_id"]
        used[s] += 1
        slugs[r["record_id"]] = s if used[s] == 1 else f"{s}-{r['record_id']}"
    pset = {r["record_id"] for r in pages}

    # ---- per-country tallies ---------------------------------------------------------
    cv = defaultdict(dict)            # iso3 -> record_id -> vote (cast, page resolutions only)
    cabs = Counter()
    for rid in pset:
        for iso, v in cast[rid].items():
            cv[iso][rid] = v
        for iso in absent[rid]:
            cabs[iso] += 1
    eligible = sorted([i for i in cv if len(cv[i]) >= MIN_VOTES], key=lambda i: names.get(i, i))
    cname = {i: (cinfo.get(i, {}).get("name") or names.get(i, i)) for i in cv}
    cslug, su = {}, Counter()
    for i in eligible:
        s = slugify(cname[i]); su[s] += 1
        cslug[i] = s if su[s] == 1 else f"{s}-{i.lower()}"

    # ---- voting partners -------------------------------------------------------------
    partners = {}
    for i in eligible:
        sc = []
        for j in eligible:
            if i == j:
                continue
            a_, b_ = (cv[i], cv[j]) if len(cv[i]) < len(cv[j]) else (cv[j], cv[i])
            shared = [r for r in a_ if r in b_]
            if len(shared) >= MIN_SHARED:
                sc.append((sum(cv[i][r] == cv[j][r] for r in shared) / len(shared), len(shared), j))
        sc.sort(key=lambda x: (-x[0], -x[1]))
        partners[i] = (sc[:8], sc[::-1][:8])

    css = out / "static.css"
    out.mkdir(parents=True, exist_ok=True)
    css.write_text(CSS, encoding="utf-8")
    urls = [f"{SITE}{base}/", f"{SITE}{base}/country/", f"{SITE}{base}/resolution/"]
    dataset_id = f"{SITE}{base}/#dataset"
    lic = "https://polyformproject.org/licenses/noncommercial/1.0.0/"
    org = {"@type": "Person", "name": "Łukasz Szoszkiewicz", "identifier": "https://orcid.org/0000-0001-6671-2893"}

    def crumbs(*items):
        return {"@type": "BreadcrumbList", "itemListElement": [
            {"@type": "ListItem", "position": n + 1, "name": nm, "item": f"{SITE}{base}{u}"} for n, (nm, u) in enumerate(items)]}

    # ---- resolution pages ------------------------------------------------------------
    subj_idx = defaultdict(list)
    for r in pages:
        if r["agenda_subject"].strip():
            subj_idx[r["agenda_subject"].strip()].append(r)
    for r in pages:
        rid, slug = r["record_id"], slugs[r["record_id"]]
        title = trim_title(r["title"]) or r["symbol"]
        rejected = "reject" in (r.get("statement") or "").lower()
        tally = Counter(cast[rid].values())
        y, n_, ab = (tally["Y"], tally["N"], tally["A"])
        outcome = ("Rejected" if rejected else "Adopted") + f" by recorded vote: {y} Yes, {n_} No, {ab} abstentions"
        groups_html = []
        for code, label, cls in (("Y", "Yes", "Y"), ("N", "No", "N"), ("A", "Abstained", "A")):
            ids = sorted([i for i, v in cast[rid].items() if v == code], key=lambda i: cname.get(i, i))
            li = "".join(f'<span class="pill">{(f"<a href={chr(34)}{base}/country/{cslug[i]}/{chr(34)}>{esc(cname.get(i, i))}</a>" if i in cslug else esc(cname.get(i, i)))}</span>' for i in ids)
            groups_html.append(f'<div><h2><span class="{cls}">{label}</span> ({len(ids)})</h2>{li or "<span class=D>none</span>"}</div>')
        ab_ids = sorted(absent[rid], key=lambda i: cname.get(i, i))
        abs_html = ("".join(f'<span class="pill">{esc(cname.get(i, i))}</span>' for i in ab_ids)) or "<span class=D>none</span>"
        chain = subj_idx.get(r["agenda_subject"].strip(), [])
        pos = next((k for k, x in enumerate(chain) if x["record_id"] == rid), None)
        rel = [] if pos is None else chain[max(0, pos - 3):pos] + chain[pos + 1:pos + 4]
        rel_html = "".join(f'<li>{esc(x["year"])} · <a href="{base}/resolution/{slugs[x["record_id"]]}/">{esc(x["symbol"])}</a> {esc(trim_title(x["title"])[:90])}</li>' for x in rel)
        facts = [("Symbol", r["symbol"]), ("Date", r["date"]), ("Body", r["body"]), ("Outcome", outcome),
                 ("Subject", r["agenda_subject"]), ("Agenda item", r["agenda_item_title"].strip().rstrip("-–— ")),
                 ("Main sponsors", re.sub(r"^Main sponsors?:\s*", "", r["main_sponsors"]))]
        dl = "".join(f"<dt>{k}</dt><dd>{esc(v)}</dd>" for k, v in facts if v and v.strip())
        links = [f'<a href="{esc(r["record_url"])}">OHCHR record</a>']
        if r["url_resolution"].strip():
            links.append(f'<a href="{esc(r["url_resolution"])}">Adopted text</a>')
        if r["url_draft"].strip():
            links.append(f'<a href="{esc(r["url_draft"])}">Draft</a>')
        body = (f'<h1>{esc(title)}</h1><p class="sub">{esc(r["symbol"])} · {esc(r["date"])} · {esc(r["body"])}</p>'
                f"<dl>{dl}</dl><p class=sub>Sources: {' · '.join(links)}</p>"
                f'<div class="cols">{"".join(groups_html)}</div>'
                f"<h2>Absent or not participating ({len(ab_ids)})</h2>{abs_html}"
                + (f"<h2>Neighbouring votes on the same subject</h2><ul class=l>{rel_html}</ul>" if rel_html else ""))
        desc = f"{r['symbol']} ({r['date'][:4]}): {outcome.lower()}. How each State voted on '{title[:90]}'."
        node = {"@type": "CreativeWork", "name": title, "identifier": r["symbol"], "datePublished": r["date"],
                "url": f"{SITE}{base}/resolution/{slug}/", "isPartOf": {"@id": dataset_id},
                "publisher": {"@type": "Organization", "name": r["body"]}, "license": lic, "inLanguage": "en"}
        d = out / "resolution" / slug
        d.mkdir(parents=True, exist_ok=True)
        (d / "index.html").write_text(page(d, f"{r['symbol']}: {title[:80]} | HRC Voting", desc[:300], body, base,
                                           [crumbs(("UN Human Rights Voting Records", "/"), ("Resolutions", "/resolution/"), (r["symbol"], f"/resolution/{slug}/")), node],
                                           f"/resolution/{slug}/"), encoding="utf-8")
        urls.append(f"{SITE}{base}/resolution/{slug}/")

    # ---- resolution index ------------------------------------------------------------
    byyear = defaultdict(list)
    for r in pages:
        byyear[r["year"]].append(r)
    blocks = "".join(
        f"<h2>{y} ({len(rs)})</h2><ul class=l>" + "".join(
            f'<li><a href="{base}/resolution/{slugs[r["record_id"]]}/">{esc(r["symbol"])}</a> {esc(trim_title(r["title"])[:100])}</li>' for r in rs) + "</ul>"
        for y, rs in sorted(byyear.items(), reverse=True))
    d = out / "resolution"
    (d / "index.html").write_text(page(d, "Recorded votes of the Commission on Human Rights and the Human Rights Council | HRC Voting",
        f"All {fmt(len(pages))} resolutions and decisions of the Commission on Human Rights and the Human Rights Council decided by recorded vote, with how each State voted.",
        f"<h1>Recorded votes, {pages[0]['year']}–{pages[-1]['year']}</h1><p>{fmt(len(pages))} resolutions and decisions of the Commission on Human Rights and the Human Rights Council decided by recorded vote. Each page lists how every State voted.</p>{blocks}",
        base, [crumbs(("UN Human Rights Voting Records", "/"), ("Resolutions", "/resolution/"))], "/resolution/"), encoding="utf-8")

    # ---- country pages ---------------------------------------------------------------
    rows_idx = []
    for i in eligible:
        nm, slug = cname[i], cslug[i]
        rids = sorted(cv[i], key=lambda r: (byrec[r]["date"], byrec[r]["symbol"]))
        tl = Counter(cv[i].values()); n = len(rids)
        years = [int(byrec[r]["year"]) for r in rids]
        y0, y1 = min(years), max(years)
        peryear = defaultdict(Counter)
        for r in rids:
            peryear[int(byrec[r]["year"])][cv[i][r]] += 1
        close, far = partners[i]
        pl = lambda lst: "".join(
            f'<li><a href="{base}/country/{cslug[j]}/">{esc(cname[j])}</a> · {round(100 * s)}% of {sh} shared votes</li>' for s, sh, j in lst)
        group = groups.get(cinfo.get(i, {}).get("group", ""), "")
        txt = (f"Between {y0} and {y1}, {esc(nm)} cast {fmt(n)} votes on resolutions and decisions of the Commission on Human Rights and the Human Rights Council "
               f"that were decided by recorded vote: {pct(tl['Y'], n)} Yes, {pct(tl['N'], n)} No and {pct(tl['A'], n)} abstentions. "
               + (f"It was recorded as absent or not participating in {fmt(cabs[i])} further roll-calls." if cabs[i] else "")
               + (f" In this dataset it belongs to the {esc(group)} group." if group else ""))
        if close:
            txt += (f" It voted most often with {esc(cname[close[0][2]])} ({round(100 * close[0][0])}% agreement on shared votes)"
                    + (f" and least often with {esc(cname[far[0][2]])} ({round(100 * far[0][0])}%)." if far else "."))
        yr_rows = "".join(f"<tr><td>{y}</td><td class=n>{sum(c.values())}</td><td class='n Y'>{c['Y']}</td><td class='n N'>{c['N']}</td><td class='n A'>{c['A']}</td></tr>" for y, c in sorted(peryear.items()))
        vote_rows = "".join(
            f'<tr><td>{esc(byrec[r]["year"])}</td><td><a href="{base}/resolution/{slugs[r]}/">{esc(byrec[r]["symbol"])}</a></td><td>{esc(trim_title(byrec[r]["title"])[:95])}</td><td class="{cv[i][r]}">{POS[cv[i][r]]}</td></tr>'
            for r in reversed(rids))
        body = (f"<h1>{esc(nm)} at the UN Commission on Human Rights and Human Rights Council</h1>"
                f'<p class="sub">Recorded votes {y0}–{y1} · {fmt(n)} votes · <a href="{base}/country/{slug}/votes.csv">download CSV</a></p><p>{txt}</p>'
                f'<p class=sub>The <a href="{base}/">interactive dashboard</a> adds a world map of agreement with {esc(nm)}, regional-group cohesion and the consensus view.</p>'
                f'<div class="cols"><div><h2>Closest voting partners</h2><ul class=l>{pl(close)}</ul></div><div><h2>Furthest voting partners</h2><ul class=l>{pl(far)}</ul></div></div>'
                f'<h2>Year by year</h2><div class=scroll><table><tr><th>Year</th><th class=n>Votes</th><th class=n>Yes</th><th class=n>No</th><th class=n>Abstain</th></tr>{yr_rows}</table></div>'
                f'<h2>Every recorded vote</h2><div class=scroll><table><tr><th>Year</th><th>Resolution</th><th>Title</th><th>Vote</th></tr>{vote_rows}</table></div>')
        desc = (f"How {nm} voted on {fmt(n)} recorded resolutions of the UN Commission on Human Rights and Human Rights Council, {y0}–{y1}: "
                f"{pct(tl['Y'], n)} Yes, {pct(tl['N'], n)} No, {pct(tl['A'], n)} abstentions.")
        nodes = [crumbs(("UN Human Rights Voting Records", "/"), ("Countries", "/country/"), (nm, f"/country/{slug}/")),
                 {"@type": "Dataset", "name": f"Voting record of {nm} at the UN Commission on Human Rights and Human Rights Council",
                  "description": desc, "url": f"{SITE}{base}/country/{slug}/", "isPartOf": {"@id": dataset_id}, "creator": org,
                  "temporalCoverage": f"{y0}/{y1}", "license": lic, "isAccessibleForFree": True, "inLanguage": "en",
                  "distribution": {"@type": "DataDownload", "encodingFormat": "text/csv", "contentUrl": f"{SITE}{base}/country/{slug}/votes.csv"}}]
        d = out / "country" / slug
        d.mkdir(parents=True, exist_ok=True)
        (d / "index.html").write_text(page(d, f"{nm}: voting record at the UN Human Rights Council | HRC Voting", desc, body, base, nodes, f"/country/{slug}/"), encoding="utf-8")
        with open(d / "votes.csv", "w", newline="", encoding="utf-8") as f:
            w = csv.writer(f); w.writerow(["symbol", "date", "year", "body", "vote", "title", "record_url"])
            for r in rids:
                w.writerow([byrec[r]["symbol"], byrec[r]["date"], byrec[r]["year"], byrec[r]["body"], POS[cv[i][r]], trim_title(byrec[r]["title"]), byrec[r]["record_url"]])
        urls.append(f"{SITE}{base}/country/{slug}/")
        rows_idx.append((nm, slug, group, y0, y1, n))

    # ---- country index + sitemap -----------------------------------------------------
    tr = "".join(f'<tr><td><a href="{base}/country/{s}/">{esc(nm)}</a></td><td>{esc(g)}</td><td>{a_}–{b_}</td><td class=n>{fmt(n)}</td></tr>' for nm, s, g, a_, b_, n in rows_idx)
    d = out / "country"
    (d / "index.html").write_text(page(d, "Countries at the UN Commission on Human Rights and Human Rights Council | HRC Voting",
        f"Voting records of {len(rows_idx)} States at the UN Commission on Human Rights and the Human Rights Council: Yes, No and abstentions on every recorded resolution.",
        f"<h1>Countries</h1><p>{len(rows_idx)} States with at least {MIN_VOTES} recorded votes at the Commission on Human Rights and the Human Rights Council (1947–2026).</p>"
        f"<div class=scroll><table><tr><th>Country</th><th>Group</th><th>Years</th><th class=n>Votes</th></tr>{tr}</table></div>",
        base, [crumbs(("UN Human Rights Voting Records", "/"), ("Countries", "/country/"))], "/country/"), encoding="utf-8")
    today = re.search(r'^date-released:\s*"([^"]+)"', (ROOT / "CITATION.cff").read_text(encoding="utf-8"), re.M).group(1)
    (out / "sitemap.xml").write_text('<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n' +
        "".join(f"<url><loc>{u}</loc><lastmod>{today}</lastmod></url>\n" for u in urls) + "</urlset>\n", encoding="utf-8")

    # ---- report ----------------------------------------------------------------------
    files = [p for p in out.rglob("*") if p.is_file()]
    raw = sum(p.stat().st_size for p in files)
    gz = sum(len(gzip.compress(p.read_bytes(), 6)) for p in files)
    big = sorted(files, key=lambda p: -p.stat().st_size)[:3]
    print(f"countries with a page: {len(eligible)} of {len(cv)} · resolution pages: {len(pages)} · urls in sitemap: {len(urls)}")
    print(f"files: {len(files)} · raw {raw/1e6:.1f} MB · gzip {gz/1e6:.1f} MB · built in {time.time()-t0:.1f}s")
    print("largest:", ", ".join(f"{p.relative_to(out)} {p.stat().st_size/1e3:.0f} KB" for p in big))


if __name__ == "__main__":
    main()
