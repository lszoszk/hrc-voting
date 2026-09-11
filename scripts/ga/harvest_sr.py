"""Harvest Third Committee summary records (A/C.3/<session>/SR.<n>) from UN Documents.

The symbol API hands back whatever exists for the symbol: .docx (recent), .doc
(older sessions) or the SPA shell (HTML, ~1.3 kB) when the record is missing or
not yet published. Files land in data/raw/ga/sr/<session>/SR.<n>.<ext>; a run log
(harvest_log.csv) makes the script resumable. Meeting numbers run 1.. until
STOP_AFTER consecutive misses past MIN_MEETINGS.

Usage: python3 scripts/ga/harvest_sr.py --sessions 55-80 [--delay 1.5]
"""
import argparse
import csv
import subprocess
import time
import urllib.parse
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
RAW = ROOT / "data" / "raw" / "ga" / "sr"
API = "https://documents.un.org/api/symbol/access?s={sym}&l=en&t=docx"
UA = "Mozilla/5.0 (research harvest; l.szoszkiewicz@amu.edu.pl)"
MIN_MEETINGS = 25
STOP_AFTER = 5


def kind_of(path):
    head = path.read_bytes()[:8]
    if head.startswith(b"PK"):
        return "docx"
    if head.startswith(b"\xd0\xcf\x11\xe0"):
        return "doc"
    if head.startswith(b"%PDF"):
        return "pdf"
    return "missing"


def fetch(sym, dest, delay):
    url = API.format(sym=urllib.parse.quote(sym, safe=""))
    r = subprocess.run(["curl", "-sL", "--max-time", "120", "-A", UA, "-o", str(dest), "-w", "%{http_code}", url],
                       capture_output=True, text=True)
    time.sleep(delay)
    return r.stdout.strip()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--sessions", default="55-80")
    ap.add_argument("--delay", type=float, default=1.5)
    args = ap.parse_args()
    a, b = (int(x) for x in args.sessions.split("-"))
    RAW.mkdir(parents=True, exist_ok=True)
    for session in range(a, b + 1):
        sdir = RAW / str(session)
        sdir.mkdir(exist_ok=True)
        # one log per session: workers on disjoint ranges never share a file
        LOG = sdir / "harvest_log.csv"
        done = {}
        if LOG.exists():
            for row in csv.DictReader(open(LOG, encoding="utf-8")):
                done[row["symbol"]] = row
        log = open(LOG, "a", newline="", encoding="utf-8")
        w = csv.DictWriter(log, fieldnames=["symbol", "http", "kind", "bytes", "file"])
        if not done:
            w.writeheader()
        misses = 0
        n = 0
        found = 0
        while True:
            n += 1
            sym = f"A/C.3/{session}/SR.{n}"
            if sym in done and done[sym]["kind"] != "missing":
                found += 1; misses = 0; continue
            if sym in done and done[sym]["kind"] == "missing" and n > MIN_MEETINGS:
                misses += 1
                if misses >= STOP_AFTER:
                    break
                continue
            tmp = sdir / f"SR.{n}.tmp"
            http = fetch(sym, tmp, args.delay)
            kind = kind_of(tmp) if tmp.exists() else "missing"
            if kind == "missing":
                tmp.unlink(missing_ok=True)
                misses += 1
                w.writerow({"symbol": sym, "http": http, "kind": kind, "bytes": 0, "file": ""}); log.flush()
                if n > MIN_MEETINGS and misses >= STOP_AFTER:
                    break
                continue
            dest = sdir / f"SR.{n}.{kind}"
            tmp.rename(dest)
            misses = 0; found += 1
            w.writerow({"symbol": sym, "http": http, "kind": kind, "bytes": dest.stat().st_size, "file": str(dest.relative_to(ROOT))}); log.flush()
        log.close()
        print(f"[sr] session {session}: {found} records, stopped at SR.{n}", flush=True)


if __name__ == "__main__":
    main()
