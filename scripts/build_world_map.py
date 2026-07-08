"""Build dashboard/world.js — compact Robinson-projected world map for the choropleth.

Source: Natural Earth 110m admin-0 countries (via johan/world.geo.json, ISO3 ids).
Small voter states missing at 110m (Maldives, Mauritius, Bahrain, ...) are added as
centroid DOTS so every state in the vote data can be coloured and hovered.

Output: window.WORLD = {W, H, paths:{ISO3:"M..."}, dots:{ISO3:[x,y]}, names:{ISO3:name}}
"""
import json, math, urllib.request
from pathlib import Path

SRC = "https://raw.githubusercontent.com/johan/world.geo.json/master/countries.geo.json"
OUT = Path(__file__).resolve().parent.parent / "dashboard" / "world.js"
DATA = Path(__file__).resolve().parent.parent / "dashboard" / "data.js"

# ---- Robinson projection (table interpolation) ----
_PLEN = [1.0000,0.9986,0.9954,0.9900,0.9822,0.9730,0.9600,0.9427,0.9216,0.8962,
         0.8679,0.8350,0.7986,0.7597,0.7186,0.6732,0.6213,0.5722,0.5322]
_PDFE = [0.0000,0.0620,0.1240,0.1860,0.2480,0.3100,0.3720,0.4340,0.4958,0.5571,
         0.6176,0.6769,0.7346,0.7903,0.8435,0.8936,0.9394,0.9761,1.0000]
def robinson(lon, lat):
    alat = abs(lat); i = min(int(alat / 5), 17); f = (alat - i*5) / 5
    plen = _PLEN[i] + (_PLEN[i+1]-_PLEN[i])*f
    pdfe = _PDFE[i] + (_PDFE[i+1]-_PDFE[i])*f
    x = 0.8487 * plen * math.radians(lon)
    y = 1.3523 * pdfe * (1 if lat >= 0 else -1)
    return x, y

W = 1000
SCALE = W / (2 * 0.8487 * math.pi)
H = int(2 * 1.3523 * SCALE) + 2
def project(lon, lat):
    x, y = robinson(lon, lat)
    return (W/2 + x*SCALE, H/2 - y*SCALE)

def ring_to_path(ring, min_area_px=3.0):
    pts = [project(lon, lat) for lon, lat in ring]
    # drop micro-rings (speck islands) to keep the file lean
    xs = [p[0] for p in pts]; ys = [p[1] for p in pts]
    if (max(xs)-min(xs)) * (max(ys)-min(ys)) < min_area_px: return ""
    d, last = [], None
    for x, y in pts:
        q = (round(x,1), round(y,1))
        if q == last: continue
        d.append(("M" if not d else "L") + f"{q[0]} {q[1]}"); last = q
    return "".join(d) + "Z" if len(d) >= 3 else ""

def feat_paths(geom):
    polys = geom["coordinates"] if geom["type"]=="MultiPolygon" else [geom["coordinates"]]
    out = []
    for poly in polys:
        for ring in poly:            # outer + holes; holes rare at 110m, harmless
            p = ring_to_path(ring)
            if p: out.append(p)
    return "".join(out)

# centroids (lon, lat) for voter states absent from the 110m map
DOTS = {"MDV":(73.5,4.2),"MUS":(57.55,-20.3),"BHR":(50.55,26.05),"SGP":(103.8,1.35),
        "CPV":(-23.6,15.1),"COM":(43.3,-11.7),"STP":(6.6,0.2),"SYC":(55.45,-4.6),
        "ATG":(-61.8,17.1),"BRB":(-59.55,13.15),"GRD":(-61.7,12.1),"LCA":(-61.0,13.9),
        "VCT":(-61.2,13.25),"KNA":(-62.7,17.3),"DMA":(-61.35,15.4),"WSM":(-172.1,-13.75),
        "TON":(-175.2,-21.2),"FJI":(178.0,-17.8),"MLT":(14.4,35.9),"BHS":(-77.4,24.25),
        "MCO":(7.4,43.7),"AND":(1.5,42.5),"LIE":(9.55,47.15),"SMR":(12.45,43.95),"LUX":(6.13,49.61),
        "MHL":(171.2,7.1),"KIR":(173.0,1.4),"FSM":(158.2,6.9),"NRU":(166.9,-0.5),
        "PLW":(134.5,7.5),"TUV":(179.2,-8.5),"SLB":(160.0,-9.6),"VUT":(167.0,-16.0)}

CACHE = Path("/private/tmp/claude-501/-Users-lszoszk-Desktop-GC-Database/2aa89920-17b7-4af2-bd10-f76a37ec4e0e/scratchpad/countries.geo.json")
if CACHE.exists():
    print("using cached", CACHE)
    geo = json.loads(CACHE.read_text())
else:
    print("fetching", SRC)
    geo = json.loads(urllib.request.urlopen(SRC, timeout=60).read())
paths, names = {}, {}
for f in geo["features"]:
    iso = f.get("id") or f["properties"].get("id")
    name = f["properties"].get("name", iso)
    if not iso or iso == "ATA": continue          # drop Antarctica
    d = feat_paths(f["geometry"])
    if d: paths[iso] = d; names[iso] = name

# our voters
data = json.loads(DATA.read_text().replace("window.DATA = ","").rstrip(";\n"))
voters = {c["iso3"]: c["name"] for c in data["countries"]}
dots = {}
for iso, ll in DOTS.items():
    if iso in voters and iso not in paths:
        x, y = project(*ll); dots[iso] = [round(x,1), round(y,1)]; names[iso] = voters[iso]

missing = sorted(set(voters) - set(paths) - set(dots))
world = {"W": W, "H": H, "paths": paths, "dots": dots, "names": names}
OUT.write_text("window.WORLD = " + json.dumps(world, separators=(",",":")) + ";\n")
print(f"world.js: {OUT.stat().st_size/1024:.0f} KB · {len(paths)} shapes · {len(dots)} dots")
print(f"voters with no map geometry ({len(missing)}, expected = historical entities): {missing}")
