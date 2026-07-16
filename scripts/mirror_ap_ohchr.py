"""Prophylactic mirror of ap.ohchr.org per-resolution texts (legacy server, may vanish).

Scope — the two eras where ap.ohchr.org is the best/only per-resolution source:
  * CHR 1993–2005 resolutions + decisions (born-digital Word)
  * HRC sessions 1–11, i.e. pre-Oct-2009 (standalone texts absent from ODS)

Uses the symbol resolver  dpage_e.aspx?si=<symbol>  and downloads the English file.
Resumable: skips symbols already on disk (or logged as missing). ~1.5 s/request.

Output: data/ap_mirror/<safe_symbol>.<ext> + mirror_log.csv (symbol,status,file)
"""
import csv, re, time, subprocess
from pathlib import Path
from urllib.parse import quote

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "data" / "ap_mirror"
OUT.mkdir(parents=True, exist_ok=True)
LOG = OUT / "mirror_log.csv"
UA = {"User-Agent": "Mozilla/5.0 (research mirror; l.szoszkiewicz@amu.edu.pl)"}
BASE = "https://ap.ohchr.org/documents/"
DELAY = 1.5

def in_scope(r):
    sym, y = r["symbol"], r["year"]
    if sym.startswith("E/CN.4/") and y.isdigit() and 1993 <= int(y) <= 2005:
        return True
    m = re.match(r"A/HRC/(?:RES|DEC)/(\d+)/", sym)
    return bool(m and int(m.group(1)) <= 11)

def fetch(url, binary=True, timeout=40):
    # curl instead of urllib: framework Python lacks SSL certs (known project gotcha)
    r = subprocess.run(["curl", "-sf", "-m", str(timeout), "-A", UA["User-Agent"], url],
                       capture_output=True)
    if r.returncode != 0:
        raise RuntimeError(f"curl exit {r.returncode}")
    return r.stdout if binary else r.stdout.decode("utf-8", "replace")

def main():
    rows = [r for r in csv.DictReader(open(ROOT / "data/csv/resolutions.csv", encoding="utf-8"))
            if in_scope(r)]
    done = set()
    if LOG.exists():
        done = {r[0] for r in csv.reader(open(LOG, encoding="utf-8"))
                if r and not r[1].startswith("error")}
    todo = [r for r in rows if r["symbol"] not in done]
    print(f"in scope: {len(rows)} · already logged: {len(done & {r['symbol'] for r in rows})} · to do: {len(todo)}", flush=True)

    log = open(LOG, "a", newline="", encoding="utf-8")
    w = csv.writer(log)
    ok = miss = err = 0
    for i, r in enumerate(todo):
        sym = r["symbol"]
        try:
            page = fetch(BASE + "dpage_e.aspx?si=" + quote(sym, safe=""), binary=False)
            m = re.search(r'href="(E/[^"]+\.(?:doc|pdf))"', page, re.I)
            if not m:
                w.writerow([sym, "missing", ""]); miss += 1
            else:
                href = m.group(1)
                blob = fetch(BASE + href.replace(" ", "%20"))
                if len(blob) < 500:
                    w.writerow([sym, "tiny", href]); miss += 1
                else:
                    fname = re.sub(r"[^A-Za-z0-9._-]", "_", sym) + Path(href).suffix.lower()
                    (OUT / fname).write_bytes(blob)
                    w.writerow([sym, "ok", fname]); ok += 1
        except Exception as e:
            w.writerow([sym, f"error:{type(e).__name__}", ""]); err += 1
        log.flush()
        if (i + 1) % 50 == 0:
            print(f"  {i+1}/{len(todo)}  ok={ok} missing={miss} err={err}", flush=True)
        time.sleep(DELAY)
    print(f"DONE. ok={ok} missing={miss} err={err} → {OUT}", flush=True)

if __name__ == "__main__":
    main()
