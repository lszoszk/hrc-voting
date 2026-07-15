"""
Build the compact data payload for the static dashboard.

Only RECORDED votes carry per-country roll-calls, so the country-profile and
bloc/alignment analysis operate on those (~1,705 resolutions). Emits
dashboard/data.js as `window.DATA = {...}` so index.html works from file://
(a <script src> load, not fetch).
"""
import collections
import csv
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CSV = ROOT / "data" / "csv"
OUT = ROOT / "dashboard"
OUT.mkdir(exist_ok=True)

# UN regional groups (best-effort; editable). Note UN quirks: Cyprus & Turkey
# and Central-Asian states sit in Asia-Pacific; Israel & USA in WEOG.
GROUPS = {
    "WEOG": "AND AUS AUT BEL CAN DNK FIN FRA DEU GER GRC ISL IRL ISR ITA LIE LUX MLT MCO "
            "NLD NZL NOR PRT SMR ESP SWE CHE TUR GBR USA".split(),
    "EEG": "ALB ARM AZE BLR BIH BGR HRV CZE CSK EST GEO HUN LVA LTU MNE MKD POL MDA "
           "ROU RUS SRB SVK SVN UKR YUG DDR SUN".split(),
    "GRULAC": "ATG ARG BHS BRB BLZ BOL BRA CHL COL CRI CUB DMA DOM ECU SLV GRD GTM GUY "
              "HTI HND JAM MEX NIC PAN PRY PER KNA LCA VCT SUR TTO URY VEN".split(),
    "AFRICAN": "DZA AGO BEN BWA BFA BDI CPV CMR CAF TCD COM COG COD CIV DJI EGY GNQ ERI "
               "SWZ ETH GAB GMB GHA GIN GNB KEN LSO LBR LBY MDG MWI MLI MRT MUS MAR MOZ "
               "NAM NER NGA RWA STP SEN SYC SLE SOM ZAF SSD SDN TGO TUN UGA TZA ZMB ZWE".split(),
    "ASIA_PACIFIC": "AFG BHR BGD BTN BRN KHM CHN CYP PRK FJI IND IDN IRN IRQ JPN JOR KAZ "
                    "KWT KGZ LAO LBN MYS MDV MHL FSM MNG MMR NRU NPL OMN PAK PLW PNG PHL "
                    "QAT KOR SAU SGP SLB LKA SYR TJK THA TLS TON TKM TUV ARE UZB VUT VNM "
                    "YEM WSM KIR".split(),
}
ISO2GROUP = {iso: g for g, lst in GROUPS.items() for iso in lst}
GROUP_LABEL = {"WEOG": "Western Europe & Others", "EEG": "Eastern Europe",
               "GRULAC": "Latin America & Caribbean", "AFRICAN": "African",
               "ASIA_PACIFIC": "Asia-Pacific", "": "Other/Unassigned"}


def main():
    res_rows = list(csv.DictReader(open(CSV / "resolutions.csv", encoding="utf-8")))
    vote_rows = list(csv.DictReader(open(CSV / "votes_long.csv", encoding="utf-8")))

    # recorded resolutions only (those with roll-call rows)
    recorded = [r for r in res_rows
                if r["n_rollcall"].isdigit() and int(r["n_rollcall"]) > 0]
    idx = {r["record_id"]: i for i, r in enumerate(recorded)}

    # ---- coverage stats over ALL 6,346 resolutions (for the Methodology tab) ----
    def has_totals(r):
        return r["yes"].isdigit() and (int(r["yes"]) + int(r["no"]) + int(r["abstain"])) > 0

    vote_type_counts = collections.Counter(r["vote_type"] for r in res_rows)
    vote_type_rollcall = collections.Counter(
        r["vote_type"] for r in recorded)
    vote_types = [{"type": t or "(blank)", "count": c,
                   "hasRollcall": vote_type_rollcall.get(t, 0)}
                  for t, c in vote_type_counts.most_common()]

    body_all = collections.Counter(
        "HRC" if "Council" in r["body"] else "CHR" for r in res_rows)

    no_rollcall_rows = [r for r in res_rows if r["record_id"] not in idx]
    totals_no_rollcall = sum(1 for r in no_rollcall_rows if has_totals(r))
    neither = len(no_rollcall_rows) - totals_no_rollcall

    def decade(y):
        return (y // 10) * 10
    dec_all = collections.Counter(
        decade(int(r["year"])) for r in res_rows if r["year"].isdigit())
    dec_rec = collections.Counter(
        decade(int(r["year"])) for r in recorded if r["year"].isdigit())
    decades = [{"decade": d, "all": dec_all[d], "recorded": dec_rec.get(d, 0)}
               for d in sorted(dec_all)]

    n_subjects_all = len({r["agenda_subject"].strip() for r in res_rows
                          if r["agenda_subject"].strip()})

    def clean_item(s):
        return s.strip().rstrip(" -").strip()

    # ---- resAll: ALL 6,346 resolutions, lean rows for the Consensus tab ----
    import re
    VT_CODE = {
        "ADOPTED WITHOUT VOTE": "C",
        "RECORDED": "V",
        "NON-RECORDED": "NR",
        "NON-RECORDED, adopted unanimously": "NRU",
        "WITHDRAWN": "WD",
        "NOT CONSIDERED": "NC",
        "NON-RECORDED, no voting information available": "NRX",
        "RECORDED, adopted at a closed meeting": "VC",
    }

    def trim_title(t):
        # strip catalogue boilerplate: "... : resolution / adopted by ..." etc.
        return re.sub(r"\s*:\s*(draft\s+)?(resolution|decision|amendment)s?\s*/.*$",
                      "", t.strip(), flags=re.I).strip()

    res_all = []
    for r in res_rows:
        row = {
            "id": r["record_id"], "sym": r["symbol"], "t": trim_title(r["title"]),
            "year": int(r["year"]) if r["year"].isdigit() else None,
            "body": "HRC" if "Council" in r["body"] else "CHR",
            "subj": r["agenda_subject"].strip(),
            "vt": VT_CODE.get(r["vote_type"], "O"),
        }
        if r["yes"].isdigit() and (int(r["yes"]) + int(r["no"]) + int(r["abstain"])) > 0:
            row["y"], row["n"], row["a"] = int(r["yes"]), int(r["no"]), int(r["abstain"])
        res_all.append(row)

    res = [{
        "id": r["record_id"], "sym": r["symbol"], "title": r["title"],
        "year": int(r["year"]) if r["year"].isdigit() else None,
        "date": r["date"].strip(),                    # 269$a raw YYYYMMDD (may be partial)
        "body": "HRC" if "Council" in r["body"] else "CHR",
        "subj": r["agenda_subject"].strip(),          # 991$d controlled subject tag
        "item": clean_item(r["agenda_item_title"]),   # 991$c formal agenda item
        "spon": r["main_sponsors"].strip(),           # 500$a main sponsors
        "mtg": r["meeting"].strip(),                   # 952$a meeting adopted at
        "urlR": r["url_resolution"].strip(),          # 856$u resolution on undocs
        "urlD": r["url_draft"].strip(),                # 856$u draft on undocs
        "y": int(r["yes"]) if r["yes"].isdigit() else None,
        "n": int(r["no"]) if r["no"].isdigit() else None,
        "a": int(r["abstain"]) if r["abstain"].isdigit() else None,
    } for r in recorded]

    # per-country vote matrix + latest display name
    votes = {}        # iso3 -> {"r":[resIdx...], "v":"codes"}
    latest_name = {}  # iso3 -> (year, name)
    res_tally = collections.defaultdict(collections.Counter)  # ri -> Counter(code)
    code_map = {"Y": "Y", "N": "N", "A": "A", ".": ".", "": "-"}
    for v in vote_rows:
        iso = v["iso3"]
        if not iso or v["record_id"] not in idx:
            continue
        ri = idx[v["record_id"]]
        code = code_map.get(v["vote"], "-")
        votes.setdefault(iso, {"r": [], "v": ""})
        votes[iso]["r"].append(ri)
        votes[iso]["v"] += code
        res_tally[ri][code] += 1
        yr = int(v["year"]) if v["year"].isdigit() else 0
        if iso not in latest_name or yr >= latest_name[iso][0]:
            latest_name[iso] = (yr, v["country"].title())

    # reconciliation: roll-call tally (967) vs official totals (996), recorded only
    reconciled, mismatched = 0, 0
    for ri, r in enumerate(recorded):
        if not (r["yes"].isdigit() and r["no"].isdigit() and r["abstain"].isdigit()):
            continue
        t = res_tally[ri]
        if (t["Y"] == int(r["yes"]) and t["N"] == int(r["no"])
                and t["A"] == int(r["abstain"])):
            reconciled += 1
        else:
            mismatched += 1

    # country stats
    countries = []
    for iso, d in sorted(votes.items()):
        codes = d["v"]
        yrs = [res[ri]["year"] for ri in d["r"] if res[ri]["year"]]
        countries.append({
            "iso3": iso,
            "name": latest_name[iso][1],
            "group": ISO2GROUP.get(iso, ""),
            "n": len(codes),
            "y": codes.count("Y"), "no": codes.count("N"), "a": codes.count("A"),
            "absent": codes.count("."), "blank": codes.count("-"),
            "first": min(yrs) if yrs else None,
            "last": max(yrs) if yrs else None,
        })

    # --- subject index (topic chips) with country-situation detection ---
    cnames = {n.upper() for (_, n) in latest_name.values()}
    cnames |= {"PALESTINE", "STATE OF PALESTINE", "OCCUPIED ARAB TERRITORIES",
               "OCCUPIED PALESTINIAN TERRITORY", "SOUTHERN AFRICA", "KOSOVO",
               "WESTERN SAHARA", "IRAN", "SYRIA", "BURMA"}

    def is_country_subject(s):
        u = s.upper().strip()
        if not u:
            return False
        if u in cnames:
            return True
        # e.g. "HUMAN RIGHTS - BELARUS", "ISRAEL - ARAB COUNTRIES"
        return any(len(c) > 5 and c in u for c in cnames)

    subj_counts = collections.Counter(r["subj"] for r in res if r["subj"])
    subjects = [{"name": s, "n": n, "cs": is_country_subject(s)}
                for s, n in subj_counts.most_common()]

    payload = {
        "meta": {
            "nResolutions": len(res),
            "nCountries": len(countries),
            "yearMin": min(r["year"] for r in res if r["year"]),
            "yearMax": max(r["year"] for r in res if r["year"]),
            "groupLabels": GROUP_LABEL,
            "coverage": {
                "totalResolutions": len(res_rows),
                "recordedResolutions": len(recorded),
                "voteTypes": vote_types,
                "bodyAll": dict(body_all),
                "totalsNoRollcall": totals_no_rollcall,
                "neitherTotalsNorRollcall": neither,
                "decades": decades,
                "nSubjectsAll": n_subjects_all,
                "nSubjectsRecorded": len(subjects),
                "reconciled": reconciled,
                "mismatched": mismatched,
            },
        },
        "res": res,
        "countries": countries,
        "votes": votes,
        "subjects": subjects,
        "resAll": res_all,
    }

    js = "window.DATA = " + json.dumps(payload, separators=(",", ":"),
                                       ensure_ascii=False) + ";\n"
    (OUT / "data.js").write_text(js, encoding="utf-8")
    size = (OUT / "data.js").stat().st_size
    unassigned = [c["iso3"] for c in countries if not c["group"]]
    print(f"data.js written: {size/1024:.0f} KB")
    print(f"  {len(res)} resolutions, {len(countries)} countries")
    print(f"  unassigned to a UN group ({len(unassigned)}): {unassigned}")


if __name__ == "__main__":
    main()
