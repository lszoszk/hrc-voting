"""User-perspective audit — desktop (1440) + mobile (375). For every tab and a few
interactions, records: horizontal page overflow, elements spilling past the viewport,
console/page errors, and per-tab screenshots into notes/shots/audit/. Read-only."""
from pathlib import Path
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parent.parent
INDEX = ROOT / "dashboard" / "index.html"
SHOTS = ROOT / "notes" / "shots" / "audit"
SHOTS.mkdir(parents=True, exist_ok=True)

OVERFLOW_JS = """() => {
  const vw = document.documentElement.clientWidth;
  const bad = [];
  document.querySelectorAll('body *').forEach(el => {
    const r = el.getBoundingClientRect();
    if (r.width === 0 || r.height === 0) return;
    // ignore elements that are legitimately scroll containers
    const ox = getComputedStyle(el).overflowX;
    if (r.right > vw + 1 && ox !== 'auto' && ox !== 'scroll' && !el.closest('.tblwrap') && !el.closest('#b-heat') && !el.closest('.suggest')) {
      bad.push(el.tagName.toLowerCase() + (el.id?'#'+el.id:'') + (el.className&&typeof el.className==='string'?'.'+el.className.split(' ')[0]:'') + ' →'+Math.round(r.right));
    }
  });
  return { pageScrollW: document.documentElement.scrollWidth, clientW: vw,
           horizontalScroll: document.documentElement.scrollWidth > vw + 1,
           spill: [...new Set(bad)].slice(0, 12) };
}"""

def audit(pg, tag):
    r = pg.evaluate(OVERFLOW_JS)
    flag = "  ⚠️ H-SCROLL" if r["horizontalScroll"] else ""
    print(f"  [{tag}] scrollW={r['pageScrollW']} clientW={r['clientW']}{flag}")
    if r["spill"]:
        print(f"       spill: {r['spill']}")
    return r["horizontalScroll"] or bool(r["spill"])

with sync_playwright() as p:
    b = p.chromium.launch(headless=True)
    for vp, label in [({"width":1440,"height":1000},"desktop"), ({"width":375,"height":740},"mobile")]:
        errors = []
        pg = b.new_context(viewport=vp, device_scale_factor=2).new_page()
        pg.on("console", lambda m: errors.append(f"{m.type}: {m.text}") if m.type=="error" else None)
        pg.on("pageerror", lambda e: errors.append(f"pageerror: {e}"))
        pg.goto(INDEX.as_uri()); pg.wait_for_timeout(700)
        print(f"\n===== {label} {vp['width']}×{vp['height']} =====")
        issues = 0
        for view in ["overview","country","topics","blocs","consensus","method"]:
            pg.click(f'.tab[data-view="{view}"]'); pg.wait_for_timeout(350)
            if view == "country":
                pg.select_option("#c-country", "USA"); pg.wait_for_timeout(400)
            if view == "topics":
                pg.evaluate("document.querySelector('.chip[data-s]')?.click()"); pg.wait_for_timeout(300)
            if view == "blocs":
                pg.wait_for_timeout(400)
            issues += audit(pg, view)
            pg.screenshot(path=str(SHOTS / f"{label}_{view}.png"), full_page=True)
        # cmdk
        pg.keyboard.press("Meta+k" if label=="desktop" else "Control+k")
        pg.wait_for_timeout(200)
        cmdk = pg.evaluate("document.getElementById('k-wrap').classList.contains('open')")
        pg.keyboard.press("Escape")
        print(f"  cmdk opens: {cmdk}")
        print(f"  console/page errors: {len(errors)}")
        for e in errors[:8]: print("    ", e)
        pg.close()
    b.close()
print("\naudit screenshots → notes/shots/audit/")
