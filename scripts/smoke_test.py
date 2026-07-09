"""file:// smoke test — simulates a colleague double-clicking dashboard/index.html.
Walks every tab, key interactions, all three palettes, the ⌘K palette and the new
heatmap country-sets; fails on any console/page error. Also saves per-tab screenshots
to notes/shots/ for visual review."""
from pathlib import Path
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parent.parent
INDEX = ROOT / "dashboard" / "index.html"
SHOTS = ROOT / "notes" / "shots"
SHOTS.mkdir(parents=True, exist_ok=True)
errors = []

with sync_playwright() as p:
    b = p.chromium.launch(headless=True)
    pg = b.new_context(viewport={"width": 1440, "height": 1000}).new_page()
    pg.on("console", lambda m: errors.append(f"[console.{m.type}] {m.text}")
          if m.type == "error" else None)
    pg.on("pageerror", lambda e: errors.append(f"[pageerror] {e}"))
    pg.goto(INDEX.as_uri())
    pg.wait_for_timeout(700)

    checks = {}
    checks["DATA loaded"] = pg.evaluate("!!window.DATA && DATA.res.length")
    # privacy: from file:// (offline artifact) GA must NOT load and the consent
    # banner must NOT appear — it only activates on http(s).
    pg.wait_for_timeout(800)
    checks["file:// GA script absent"] = pg.evaluate("!document.querySelector('script[src*=googletagmanager]')")
    checks["file:// consent banner absent"] = pg.evaluate("!document.querySelector('.ga-consent')")
    checks["masthead stat"] = pg.evaluate("document.getElementById('hd-stat').textContent")
    checks["overview tiles"] = pg.evaluate("document.querySelectorAll('#ov-tiles .tile').length")
    checks["ov legend"] = pg.evaluate("document.getElementById('ov-legend').textContent.includes('Commission')")
    checks["most divided rows"] = pg.evaluate("document.querySelectorAll('#ov-close .gtr').length")
    pg.screenshot(path=str(SHOTS / "01_overview_paper.png"))
    # single-resolution roll-call overlay (drill-down from a table row)
    pg.evaluate("document.querySelector('#ov-close .reslink').click()")
    pg.wait_for_timeout(200)
    checks["rollcall opens"] = pg.evaluate("document.getElementById('rc-wrap').classList.contains('open')")
    checks["rollcall map paths"] = pg.evaluate("document.querySelectorAll('#rc-map path').length")
    checks["rollcall list cols"] = pg.evaluate("document.querySelectorAll('#rc-lists .rc-col').length")
    pg.evaluate("document.getElementById('rc-close').click()")
    checks["rollcall closes"] = pg.evaluate("!document.getElementById('rc-wrap').classList.contains('open')")

    pg.click('.tab[data-view="country"]')
    checks["country rows"] = pg.evaluate("document.querySelectorAll('#c-rows .gtr').length")
    pg.select_option("#c-country", "POL")
    checks["country switch (POL rows)"] = pg.evaluate("document.querySelectorAll('#c-rows .gtr').length")
    checks["vote pills"] = pg.evaluate("document.querySelectorAll('#c-rows .pill').length > 0")
    checks["composition rects"] = pg.evaluate("document.querySelectorAll('#c-timeline rect').length")
    checks["align top rows"] = pg.evaluate("document.querySelectorAll('#c-align-top text').length")
    checks["align bot rows"] = pg.evaluate("document.querySelectorAll('#c-align-bot text').length")
    checks["map paths"] = pg.evaluate("document.querySelectorAll('#c-map path').length")
    checks["map dots"] = pg.evaluate("document.querySelectorAll('#c-map circle').length")
    checks["subject col (country)"] = pg.evaluate("[...document.querySelectorAll('#c-head .gtc')].some(x=>x.textContent.includes('Subject'))")
    pg.screenshot(path=str(SHOTS / "02_country.png"))

    pg.click('.tab[data-view="topics"]')
    checks["chip border"] = pg.evaluate(
        "getComputedStyle(document.querySelector('.chip')).borderTopWidth")
    pg.fill("#t-search", "tor")
    pg.wait_for_timeout(150)
    checks["suggest items"] = pg.evaluate("document.querySelectorAll('#t-suggest .sitem[data-s]').length")
    pg.keyboard.press("Enter")
    checks["topic rows"] = pg.evaluate("document.querySelectorAll('#t-rows .gtr').length")
    checks["trend svg"] = pg.evaluate("document.querySelectorAll('#t-trend svg').length")
    checks["trend note"] = pg.evaluate("document.getElementById('t-trendnote').textContent")
    pg.screenshot(path=str(SHOTS / "03_topics.png"))

    pg.click('.tab[data-view="blocs"]')
    pg.wait_for_timeout(300)
    checks["heat cells (active)"] = pg.evaluate("document.querySelectorAll('#b-heat rect').length")
    for kind in ("agree30", "disagree30"):
        pg.select_option("#b-set", kind)
        pg.wait_for_timeout(400)
        checks[f"heat cells ({kind})"] = pg.evaluate("document.querySelectorAll('#b-heat rect').length")
        checks[f"note ({kind})"] = pg.evaluate("document.getElementById('b-note').textContent")[:60]
    pg.screenshot(path=str(SHOTS / "04_blocs_disagree30.png"))
    pg.select_option("#b-set", "active")
    pg.wait_for_timeout(300)
    # alignment-geometry panels
    checks["mds points"] = pg.evaluate("document.querySelectorAll('#b-mds circle').length")
    checks["mds anchors note"] = pg.evaluate("document.getElementById('b-mds-note').textContent")
    checks["cohesion bars"] = pg.evaluate("document.querySelectorAll('#b-cohesion rect').length")
    checks["isolation labels"] = pg.evaluate("document.querySelectorAll('#b-isolation text').length")
    pg.select_option("#b-poleY", "RUS")  # change an anchor
    pg.wait_for_timeout(400)
    checks["mds after anchor change"] = pg.evaluate("document.getElementById('b-mds-note').textContent")
    pg.select_option("#b-poleY", "CHN")

    pg.click('.tab[data-view="method"]')
    checks["method total"] = pg.evaluate("document.getElementById('m-tile-total').textContent")
    checks["method vt rows"] = pg.evaluate("document.querySelectorAll('#m-vt .gtr').length")
    pg.screenshot(path=str(SHOTS / "05_method.png"))

    # ⌘K palette
    pg.keyboard.press("Meta+k")
    checks["cmdk opens"] = pg.evaluate("document.getElementById('k-wrap').classList.contains('open')")
    pg.fill("#k-in", "palestine")
    pg.wait_for_timeout(100)
    checks["cmdk items"] = pg.evaluate("document.querySelectorAll('.kitem').length")
    pg.keyboard.press("Enter")
    checks["cmdk nav -> view"] = pg.evaluate("document.querySelector('.tab.on').dataset.view")

    # palettes
    pg.click('.tab[data-view="overview"]')
    for pal in ("terminal", "ink", "paper"):
        pg.click(f'.palbtn[data-pal="{pal}"]')
        pg.wait_for_timeout(200)
        checks[f"palette {pal}"] = pg.evaluate("document.getElementById('vr').dataset.palette")
        if pal != "paper":
            pg.screenshot(path=str(SHOTS / f"06_overview_{pal}.png"))

    b.close()

print("--- file:// smoke (design build) ---")
for k, v in checks.items():
    print(f"  {k}: {v}")
print(f"\nconsole/page errors: {len(errors)}")
for e in errors[:10]:
    print(" ", e)
ok = (checks["DATA loaded"] and checks["overview tiles"] == 4 and checks["country rows"]
      and checks["map paths"] > 150 and checks["composition rects"] > 50
      and checks["align top rows"] and checks["subject col (country)"]
      and checks["suggest items"] and checks["topic rows"] and checks["trend svg"]
      and checks["heat cells (agree30)"] == 900 and checks["heat cells (disagree30)"] == 900
      and checks["mds points"] > 20 and checks["cohesion bars"] == 10 and checks["isolation labels"] > 40
      and "anchors" in checks["mds anchors note"] and "Russia" in checks["mds after anchor change"]
      and checks["chip border"] == "1px" and checks["cmdk opens"]
      and checks["rollcall opens"] and checks["rollcall map paths"] > 150 and checks["rollcall list cols"] >= 3
      and checks["file:// GA script absent"] and checks["file:// consent banner absent"]
      and checks["palette paper"] == "paper" and not errors)
print("SMOKE:", "PASS" if ok else "FAIL")
raise SystemExit(0 if ok else 1)
