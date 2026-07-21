"""Exercise every CSV + PNG export button, capture the downloads, and validate:
CSV parses with the right shape; PNG is a real non-blank raster. Runs on file://."""
import csv, io, struct
from pathlib import Path
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parent.parent
INDEX = ROOT / "dashboard" / "index.html"
OUT = ROOT / "notes" / "exports"
OUT.mkdir(parents=True, exist_ok=True)

def png_dims(b):
    if b[:8] != b"\x89PNG\r\n\x1a\n":
        return None
    w, h = struct.unpack(">II", b[16:24])
    return w, h

def grab(pg, selector, tag):
    with pg.expect_download(timeout=15000) as di:
        pg.click(selector)
    d = di.value
    path = OUT / d.suggested_filename
    d.save_as(str(path))
    return path

fails = []
with sync_playwright() as p:
    b = p.chromium.launch(headless=True)
    ctx = b.new_context(viewport={"width":1440,"height":1000}, accept_downloads=True)
    ctx.add_init_script("try{localStorage.setItem('hrc-tour-done','1')}catch(e){}")
    pg = ctx.new_page()
    pg.on("pageerror", lambda e: fails.append(f"pageerror: {e}"))
    pg.goto(INDEX.as_uri()); pg.wait_for_timeout(700)

    # --- Overview ---
    csv_ovtl = grab(pg, '[data-csv="ovtl"]', "ovtl")
    png_ovtl = grab(pg, '[data-png="ov-timeline"]', "ov-timeline")
    grab(pg, '[data-csv="ovmg"]', "ovmg")
    png_ovmg = grab(pg, '[data-png="ov-margin"]', "ov-margin")

    # --- Country (USA default) ---
    pg.click('.tab[data-view="country"]'); pg.wait_for_timeout(400)
    csv_ctl = grab(pg, '[data-csv="ctl"]', "ctl")
    grab(pg, '[data-png="c-timeline"]', "c-timeline")
    csv_cal = grab(pg, '[data-csv="cal"]', "cal")
    png_align = grab(pg, '[data-png="c-align-top,c-align-bot"]', "c-align")   # two stacked svgs
    png_map = grab(pg, '[data-png="c-map"]', "c-map")
    grab(pg, '[data-csv="crows"]', "crows")

    # --- Topics ---
    pg.click('.tab[data-view="topics"]')
    pg.evaluate("document.querySelector('.chip[data-s=\\'CAPITAL PUNISHMENT\\']').click()")
    pg.wait_for_timeout(300)
    csv_ttrend = grab(pg, '[data-csv="ttrend"]', "ttrend")
    grab(pg, '[data-png="t-trend"]', "t-trend")
    png_stance = grab(pg, '[data-png="t-stance"]', "t-stance")

    # --- Consensus (experimental) ---
    pg.click('.tab[data-view="consensus"]'); pg.wait_for_timeout(600)
    csv_cflips = grab(pg, '[data-csv="cflips"]', "cflips")
    png_strips = grab(pg, '[data-png="cn-strips"]', "cn-strips")
    csv_cero = grab(pg, '[data-csv="cero"]', "cero")
    pg.select_option("#g-kind", "all"); pg.wait_for_timeout(500)   # full catalogue for the explorer CSV
    csv_cexp = grab(pg, '[data-csv="cexplorer"]', "cexplorer")
    pg.select_option("#g-kind", "res"); pg.wait_for_timeout(400)

    # --- Blocs (heatmap + alignment-geometry panels) ---
    pg.click('.tab[data-view="blocs"]'); pg.wait_for_timeout(400)
    csv_bheat = grab(pg, '[data-csv="bheat"]', "bheat")
    png_heat = grab(pg, '[data-png="b-heat"]', "b-heat")
    csv_bmds = grab(pg, '[data-csv="bmds"]', "bmds")
    png_mds = grab(pg, '[data-png="b-mds"]', "b-mds")
    csv_bcoh = grab(pg, '[data-csv="bcoh"]', "bcoh")
    png_coh = grab(pg, '[data-png="b-cohesion"]', "b-cohesion")
    csv_biso = grab(pg, '[data-csv="biso"]', "biso")
    png_iso = grab(pg, '[data-png="b-isolation"]', "b-isolation")

    b.close()

# ---- validate CSVs ----
def check_csv(path, min_rows, must_have):
    txt = path.read_text(encoding="utf-8-sig")
    # citation title + source are prepended as `#` comment lines — verify + skip them
    has_cite = txt.startswith("# ") and "# Source: OHCHR" in txt.split("\n")[1]
    rows = [r for r in csv.reader(io.StringIO(txt)) if not (r and r[0].startswith("#"))]
    ok = has_cite and len(rows) - 1 >= min_rows and must_have in rows[0]
    print(f"  CSV {path.name}: {len(rows)-1} data rows, header={rows[0][:4]}… cite={'y' if has_cite else 'N'} {'OK' if ok else 'FAIL'}")
    if not ok: fails.append(f"csv {path.name}")
    return rows

check_csv(csv_ovtl, 60, "year")
check_csv(csv_ctl, 40, "yes")
check_csv(csv_cal, 100, "agreement_pct")
check_csv(csv_ttrend, 10, "avg_yes_share_pct")
bheat_rows = check_csv(csv_bheat, 30, "state")
print(f"  bheat matrix is square-ish: {len(bheat_rows[0])} cols × {len(bheat_rows)-1} rows")
check_csv(csv_bmds, 20, "shared_votes")
check_csv(csv_bcoh, 5, "agreement_index")
check_csv(csv_biso, 40, "minority_side_pct")
check_csv(csv_cflips, 30, "delta_pp")
check_csv(csv_cero, 60, "consensus_share_pct")
check_csv(csv_cexp, 6000, "mode")

# ---- validate PNGs ----
for path in [png_ovtl, png_ovmg, png_align, png_map, png_stance, png_heat,
             png_mds, png_coh, png_iso, png_strips]:
    data = path.read_bytes()
    dims = png_dims(data)
    ok = dims is not None and len(data) > 3000 and dims[0] > 100 and dims[1] > 60
    print(f"  PNG {path.name}: {len(data)//1024}KB {dims} {'OK' if ok else 'FAIL'}")
    if not ok: fails.append(f"png {path.name}")

print(f"\nexports saved to notes/exports/ · failures: {len(fails)}")
for f in fails: print("  ", f)
print("EXPORT TEST:", "PASS" if not fails else "FAIL")
