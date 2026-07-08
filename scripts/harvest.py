"""
Complete harvest via per-year partitioning.

Invenio hard-caps deep pagination at jrec=5000, so ~1150 records ranked beyond
that are unreachable by paging. Each single year holds <200 voting records, so
querying `p=year:YYYY` returns the whole year in ONE request with no pagination
and no cap. Union across all years => complete coverage.

Writes data/raw/year_YYYY.xml (kept alongside page_*.xml; parser dedupes by 001).
Flags any year that hits the 200 ceiling so it can be sub-partitioned.
"""
import re
import sys
import time
from pathlib import Path
from playwright.sync_api import sync_playwright

BASE = "https://searchlibrary.ohchr.org"
SEARCH = f"{BASE}/search?c=Voting&cc=Voting&ln=en"
RAW = Path(__file__).resolve().parent.parent / "data" / "raw"
RAW.mkdir(parents=True, exist_ok=True)
YEARS = range(1945, 2028)
UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36")


def solve(page):
    page.goto(SEARCH, wait_until="domcontentloaded", timeout=60000)
    for _ in range(30):
        if "aws-waf-token" in {c["name"] for c in page.context.cookies()} \
                and "records found" in page.content():
            return True
        page.wait_for_timeout(1000)
    return False


def fetch(ctx, page, url, retries=4):
    for a in range(retries):
        r = ctx.request.get(url, timeout=60000)
        body = r.body()
        if r.status == 200 and body[:5].lstrip().startswith(b"<?xml"):
            return body.decode("utf-8", "replace")
        print(f"    challenge/err (status {r.status}), re-solving WAF...")
        solve(page)
        time.sleep(1.5)
    raise RuntimeError(f"failed: {url}")


def recids(xml):
    return re.findall(r'<controlfield tag="001">(\d+)</controlfield>', xml)


def merge_records(xmls):
    """Concatenate the <record>..</record> blocks from several MARCXML docs."""
    recs = []
    for x in xmls:
        recs += re.findall(r"<record>.*?</record>", x, re.S)
    return ('<?xml version="1.0" encoding="UTF-8"?>\n'
            '<collection xmlns="http://www.loc.gov/MARC21/slim">\n'
            + "\n".join(recs) + "\n</collection>\n")


def fetch_partition(ctx, page, query):
    """Fetch a whole partition, paging within it (safe: a year is <<5000 so the
    jrec deep-pagination cap is never reached). Returns merged MARCXML."""
    pages, jrec = [], 1
    while True:
        xml = fetch(ctx, page, f"{BASE}/search?c=Voting&cc=Voting&of=xm"
                               f"&rg=200&jrec={jrec}&{query}")
        n = len(recids(xml))
        pages.append(xml)
        if n < 200:
            break
        jrec += 200
        if jrec > 4000:      # guard: no single partition should be this big
            print("    WARN: partition unexpectedly large, stopping at cap")
            break
    return merge_records(pages)


def main():
    with sync_playwright() as p:
        b = p.chromium.launch(headless=True)
        ctx = b.new_context(user_agent=UA, locale="en-US",
                            viewport={"width": 1280, "height": 900})
        page = ctx.new_page()
        print("Solving WAF...")
        if not solve(page):
            print("ERROR: no token"); sys.exit(1)
        print("OK.\n")

        # force re-fetch of ceiling years discovered earlier (now paged within)
        for cy in (2016, 2021, 2022, 2023):
            f = RAW / f"year_{cy}.xml"
            if f.exists() and f.read_text(encoding="utf-8").count("<record>") <= 200:
                f.unlink()

        all_ids, total = set(), 0
        for y in YEARS:
            out = RAW / f"year_{y}.xml"
            if out.exists() and out.stat().st_size > 200:
                xml = out.read_text(encoding="utf-8")
            else:
                xml = fetch_partition(ctx, page, f"p=year%3A{y}")
                out.write_text(xml, encoding="utf-8")
                time.sleep(0.5)
            ids = recids(xml)
            if ids:
                total += len(ids)
                all_ids.update(ids)
                print(f"  year {y}: {len(ids):>3} records")

        # undated records: the complement of the whole year range
        uf = RAW / "undated.xml"
        if not uf.exists():
            xml = fetch_partition(ctx, page, "p=-year%3A1000-%3E2100")
            uf.write_text(xml, encoding="utf-8")
        undated_ids = set(recids(uf.read_text(encoding="utf-8")))
        print(f"\nUndated partition (NOT year:1000->2100): {len(undated_ids)} records")

        b.close()

        year_and_undated = all_ids | undated_ids
        print(f"\nYear harvest: {total} rows, {len(all_ids)} unique dated ids.")
        print(f"Years ∪ undated (self-sufficient): {len(year_and_undated)}   [target 6346]")

        # Independent cross-check against paginated pages
        page_ids = set()
        for f in RAW.glob("page_*.xml"):
            page_ids.update(recids(f.read_text(encoding="utf-8")))
        combined = year_and_undated | page_ids
        print(f"Paginated pages unique: {len(page_ids)}")
        print(f"COMBINED unique (all methods): {len(combined)}   [target 6346]")
        missed_by_year = page_ids - year_and_undated
        print(f"In pages but missed by year+undated: {len(missed_by_year)} "
              f"(should be 0 if self-sufficient)")
        if missed_by_year:
            print("  sample:", list(missed_by_year)[:10])


if __name__ == "__main__":
    main()
