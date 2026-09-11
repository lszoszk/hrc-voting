"""Harvest the English PDF of every General Assembly resolution in
data/csv/ga_resolutions.csv from the documents.un.org symbol API, into
data/ods_texts/ next to the HRC texts (same file naming, same log format as
scripts/harvest_ods_texts.py, so build_text_index.py can index both).

Resumable via data/ods_texts/ods_log.csv. ~1.6 s per request.
Usage: python3 scripts/ga/harvest_ga_texts.py
"""
import csv
import re
import subprocess
import time
from pathlib import Path
from urllib.parse import quote

ROOT = Path(__file__).resolve().parent.parent.parent
OUT = ROOT / "data" / "ods_texts"
OUT.mkdir(parents=True, exist_ok=True)
LOG = OUT / "ods_log.csv"
API = "https://documents.un.org/api/symbol/access?s={}&l=en&t=pdf"
UA = "Mozilla/5.0 (research harvest; l.szoszkiewicz@amu.edu.pl)"
DELAY = 1.6


def main():
    rows = list(csv.DictReader(open(ROOT / "data/csv/ga_resolutions.csv", encoding="utf-8")))
    done = set()
    if LOG.exists():
        done = {r[0] for r in csv.reader(open(LOG, encoding="utf-8")) if r and not r[1].startswith("error")}
    todo = [r for r in rows if r["symbol"] not in done]
    print(f"GA texts: {len(rows)} resolutions · logged: {len(rows) - len(todo)} · to do: {len(todo)}", flush=True)
    log = open(LOG, "a", newline="", encoding="utf-8")
    w = csv.writer(log)
    ok = miss = err = 0
    for i, r in enumerate(todo):
        sym = r["symbol"]
        try:
            p = subprocess.run(["curl", "-sfL", "-m", "60", "-A", UA, API.format(quote(sym, safe=""))], capture_output=True)
            blob = p.stdout
            if p.returncode != 0:
                w.writerow([sym, f"error:curl{p.returncode}", ""]); err += 1
            elif not blob.startswith(b"%PDF"):
                w.writerow([sym, "missing", ""]); miss += 1
            else:
                fname = re.sub(r"[^A-Za-z0-9._-]", "_", sym) + ".pdf"
                (OUT / fname).write_bytes(blob)
                w.writerow([sym, "ok", fname]); ok += 1
        except Exception as e:
            w.writerow([sym, f"error:{type(e).__name__}", ""]); err += 1
        log.flush()
        if (i + 1) % 100 == 0:
            print(f"  {i+1}/{len(todo)}  ok={ok} missing={miss} err={err}", flush=True)
        time.sleep(DELAY)
    print(f"DONE. ok={ok} missing={miss} err={err}", flush=True)


if __name__ == "__main__":
    main()
