"""Third Committee voting sheets (PDF) from un.org, sessions 65–78.

Each session page https://www.un.org/en/ga/third/<s>/votingsheets.shtml links the
electronic-board printout of every recorded vote (draft resolutions, amendments,
motions). They are the only per-State source for sessions whose summary records
were never issued (75 and 76, the pandemic sessions) and a cross-check for the
others. Files land in data/raw/ga/sheets/<session>/ with an index CSV
(session, file, link_text, symbol_hint, has_text).

Usage: python3 scripts/ga/harvest_sheets.py [--sessions 65-78]
"""
import argparse
import csv
import html
import re
import subprocess
import time
from pathlib import Path
from urllib.parse import urljoin

ROOT = Path(__file__).resolve().parent.parent.parent
RAW = ROOT / "data" / "raw" / "ga" / "sheets"
# un.org serves its pages only to browser-like agents (a plain research UA gets a stub)
UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Safari/605.1.15"
DELAY = 1.5


def get(url, dest=None):
    args = ["curl", "-sL", "--max-time", "120", "-A", UA, url]
    if dest:
        args += ["-o", str(dest)]
    r = subprocess.run(args, capture_output=True)
    time.sleep(DELAY)
    return r.stdout if not dest else None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--sessions", default="65-78")
    args = ap.parse_args()
    a, b = (int(x) for x in args.sessions.split("-"))
    RAW.mkdir(parents=True, exist_ok=True)
    index = RAW / "index.csv"
    seen = set()
    if index.exists():
        seen = {(r["session"], r["file"]) for r in csv.DictReader(open(index, encoding="utf-8"))}
    out = open(index, "a", newline="", encoding="utf-8")
    w = csv.DictWriter(out, fieldnames=["session", "file", "link_text", "symbol_hint", "has_text"])
    if not seen:
        w.writeheader()
    for session in range(a, b + 1):
        page_url = f"https://www.un.org/en/ga/third/{session}/votingsheets.shtml"
        page = get(page_url).decode("utf-8", "replace")
        links = re.findall(r'<a[^>]+href="([^"]+voting_sheets/[^"]+\.pdf)"[^>]*>(.*?)</a>', page, flags=re.S | re.I)
        sdir = RAW / str(session)
        sdir.mkdir(exist_ok=True)
        n = 0
        for href, text in links:
            url = urljoin(page_url, href.replace(" ", "%20"))
            fname = re.sub(r"[^A-Za-z0-9._-]+", "_", href.split("/")[-1])
            if (str(session), fname) in seen:
                continue
            dest = sdir / fname
            get(url, dest)
            text = html.unescape(re.sub(r"<[^>]+>", " ", text)).strip()
            # the symbol is in the link text ("Recorded vote on A/C.3/73/L.9/Rev.1") or,
            # on newer pages, in the file name (L.9.Rev.1.pdf)
            m = re.search(r"A/C\.3/\d+/L\.\d+(?:/Rev\.\d+)?", text)
            hint = m.group(0) if m else ""
            if not hint:
                m = re.match(r"(L\.\d+)(?:\.Rev\.(\d+))?", fname)
                if m:
                    hint = f"A/C.3/{session}/{m.group(1)}" + (f"/Rev.{m.group(2)}" if m.group(2) else "")
            has_text = 0
            if dest.exists() and dest.read_bytes()[:4] == b"%PDF":
                t = subprocess.run(["pdftotext", "-layout", str(dest), "-"], capture_output=True, text=True).stdout
                has_text = int(bool(re.search(r"\b(?:ALBANIA|ALGERIA|ANGOLA)\b", t)))
            w.writerow({"session": session, "file": fname, "link_text": text[:200], "symbol_hint": hint, "has_text": has_text})
            out.flush()
            n += 1
        print(f"[sheets] session {session}: {len(links)} links, {n} new", flush=True)


if __name__ == "__main__":
    main()
