"""Harvest HRC-era full texts from the open documents.un.org symbol API.

Scope: every catalogued A/HRC/* symbol NOT covered by the ap.ohchr.org mirror
(i.e. RES/DEC of session >= 12 plus all L-documents/amendments). English PDFs.
Soft-404s (the SPA shell) come back as text/html — detected via the %PDF magic.

Resumable via ods_log.csv (symbol,status,file). ~1.6 s/request, polite.
Output: data/ods_texts/<safe_symbol>.pdf
"""
import csv, re, subprocess, time
from pathlib import Path
from urllib.parse import quote

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "data" / "ods_texts"
OUT.mkdir(parents=True, exist_ok=True)
LOG = OUT / "ods_log.csv"
API = "https://documents.un.org/api/symbol/access?s={}&l=en&t=pdf"
UA = "Mozilla/5.0 (research harvest; l.szoszkiewicz@amu.edu.pl)"
DELAY = 1.6

def in_scope(r):
    sym = r["symbol"]
    if not sym.startswith("A/HRC/"):
        return False
    m = re.match(r"A/HRC/(?:RES|DEC)/(\d+)/", sym)
    if m:                       # RES/DEC: mirror covered sessions 1-11
        return int(m.group(1)) >= 12
    return True                 # everything else (L-docs, PRST, amendments)

def main():
    rows = [r for r in csv.DictReader(open(ROOT / "data/csv/resolutions.csv", encoding="utf-8"))
            if in_scope(r)]
    done = set()
    if LOG.exists():
        done = {r[0] for r in csv.reader(open(LOG, encoding="utf-8"))
                if r and not r[1].startswith("error")}
    todo = [r for r in rows if r["symbol"] not in done]
    print(f"in scope: {len(rows)} · logged: {len(done)} · to do: {len(todo)}", flush=True)

    log = open(LOG, "a", newline="", encoding="utf-8")
    w = csv.writer(log)
    ok = miss = err = 0
    for i, r in enumerate(todo):
        sym = r["symbol"]
        try:
            p = subprocess.run(["curl", "-sfL", "-m", "60", "-A", UA,
                                API.format(quote(sym, safe=""))], capture_output=True)
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
    print(f"DONE. ok={ok} missing={miss} err={err} → {OUT}", flush=True)

if __name__ == "__main__":
    main()
