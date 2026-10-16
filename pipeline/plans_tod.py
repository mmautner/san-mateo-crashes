"""Extract the TOD Pedestrian Access Plan's project list into site/plans/tod.json.

    python pipeline/plans_tod.py      # then: python pipeline/plans.py

Source: City of San Mateo, Transit-Oriented Development Pedestrian Access Plan
(adopted November 21, 2022), "Priority Project Recommendations, Detailed List".
The PDF is downloaded once into pipeline/cache/plans/ and parsed with pdfplumber.
Each row's recommended changes are sorted into plain-language categories by
keyword (TREATMENTS below); the page links the plan for the full wording.
Rerunning on the same PDF gives the same output.
"""
import json
import re
import sys
import urllib.request
from pathlib import Path

import pdfplumber

HERE = Path(__file__).parent
CACHE = HERE / "cache" / "plans"
PDF_URL = "https://www.cityofsanmateo.org/DocumentCenter/View/89707"
OUT = HERE.parent / "site" / "plans" / "tod.json"

# Plain-language categories, in display order: (label, pattern over the plan's text)
TREATMENTS = [
    ("High-visibility crosswalks", r"high[- ]visibility|x-?walks?\b|ladder|continental"),
    ("A head start on the walk signal for people crossing", r"\bLPIs?\b|leading ped"),
    ("No right turn on red", r"NRTOR|no right turn on red|no right on red"),
    ("More time to cross", r"ft/sec|clearance|crossing time|walk time"),
    ("Walk signal comes on without pushing the button", r"recall"),
    ("Countdown walk signals", r"countdown"),
    ("Wider sidewalk corners that shorten the crossing", r"curb extension|bulb[- ]?out|corner radi|tighten"),
    ("Raised islands where people crossing can wait", r"refuge|median nose|median island"),
    ("Protected left-turn arrows", r"protect(ed)? left|left[- ]turn (phas|arrow)|split phase"),
    ("Stop lines set back from the crosswalk", r"advance (stop|limit|yield)|stop bar|limit line"),
    ("Curb ramps and push buttons for wheelchairs and strollers", r"\bADA\b|curb ramp|push[- ]?button|accessible ped"),
    ("Flashing beacons at the crosswalk", r"RRFB|beacon|\bPHB\b|HAWK"),
    ("A new or added crosswalk", r"new (crosswalk|crossing|x-?walk)|mid-?block cross|add (a )?(crosswalk|crossing|x-?walk)|install (a )?(crosswalk|x-?walk)"),
    ("Raised crosswalks or speed humps", r"raised (crosswalk|crossing|x-?walk|intersection)|speed (hump|table|cushion)"),
    ("Better lighting", r"light(ing)?\b"),
    ("Wider or repaired sidewalks", r"sidewalk (widen|width|gap|repair|replace)|widen (the )?sidewalk|new sidewalk|close (the )?sidewalk gap|fill (the )?gap"),
    ("Fewer or narrower car lanes", r"road diet|narrow (the )?(travel )?lanes|lane reduction|remove (a )?(travel )?lane"),
    ("Signal timing reviewed for people walking", r"cycle length|signal (phasing|timing)|timings?\b"),
    ("Signs pointing the way to the station", r"wayfinding"),
    ("Street trees and landscaping", r"\btrees?\b|landscap"),
    ("Daylighting: no parking right next to crosswalks", r"daylight|red curb|restrict parking|parking restriction"),
    ("Wider or repaired sidewalks", r"sidewalk is minimum|\d+[- ]f(oo)?t(-wide)? (wide )?sidewalk|through zone"),
    ("Redesign of the street and its intersections", r"reconfigur"),
    ("A new walking connection to the station", r"provide access|remove fence|new path|path across"),
    ("Being built as part of a nearby development", r"being implemented with|development project"),
]

# How the plan writes some names, and what to look for on the map instead
ALIASES = {
    "4th": "4th Ave", "ECR": "El Camino Real", "Delaware": "Delaware St", "S Claremont": "Claremont St",
    "Sunnybrae": "Sunnybrae Ave", "Sunnybra": "Sunnybrae Ave", "S Delawar": "S Delaware St",
    "Baldwin Ave- Baywood Ave": "Baldwin Ave", "17th Ave- Bovet Rd": "17th Ave",
    "Station Park Cir-92 on/off- ramps": "Station Park Cir", "Railroad": "Railroad Ave",
    "N Railroad Ave (west & east of tracks)": "N Railroad Ave", "N Railroad Ave (west of tracks)": "N Railroad Ave",
    "Pacific Blvd - Concar Dr": "Pacific Blvd", "Crystal Springs Road": "Crystal Springs Rd",
}
# Corners where the two roads cross at different levels, so the map has no shared point
MAX_GAP_M = {("El Camino Real", "Hillsdale Blvd"): 150}
# Endpoints that aren't streets: such rows are kept but not placed on the map
NOT_A_STREET = re.compile(r"station|tracks|parking|path|overpass|caltrain|edge of|access point|^$", re.I)


def fetch():
    CACHE.mkdir(parents=True, exist_ok=True)
    pdf = CACHE / "tod_priority_projects_detailed_list.pdf"
    if not pdf.exists():
        req = urllib.request.Request(PDF_URL, headers={"User-Agent": "san-mateo-crashes pipeline"})
        pdf.write_bytes(urllib.request.urlopen(req).read())
    return pdf


def name(s):
    s = re.sub(r"^at\s+", "", s.strip())
    return ALIASES.get(s, s)


def split_terms(text):
    """'short term: ... medium term: ...' -> (sooner, later, unspecified) text."""
    # a marker starts a line and ends in a colon; "(... for short term; ... medium term)" asides don't count
    parts = re.split(r"(?im)^\s*(short[- ]term|medium[- ]term|long[- ]term)\s*:", text)
    if len(parts) == 1:
        return "", "", text  # the plan gives no timing for this row
    sooner, later = parts[0], ""
    for k in range(1, len(parts), 2):
        if parts[k].lower().startswith("short"):
            sooner += " " + parts[k + 1]
        else:
            later += " " + parts[k + 1]
    return sooner, later, ""


def categories(text):
    return list(dict.fromkeys(label for label, pat in TREATMENTS if re.search(pat, text, re.I)))


def is_street(raw):
    raw = re.sub(r"^at\s+", "", raw.strip())
    return raw in ALIASES or not NOT_A_STREET.search(raw)


def main():
    rows = []
    with pdfplumber.open(fetch()) as pdf:
        for page_no, pg in enumerate(pdf.pages, 1):
            area = (pg.extract_text() or "").splitlines()[0].split(" - ")[-1].strip()
            for t in pg.extract_tables():
                for r in t:
                    text = (r[7] or "") if len(r) > 7 else ""  # keep line breaks: they mark short/medium term
                    r = [(c or "").replace("\n", " ").strip() for c in r] + [""] * 10
                    if r[0] in ("", "Project #"):
                        continue
                    rows.append({"project": r[0], "project_name": r[1], "road": r[2], "from": r[3], "to": r[4],
                                 "control": r[6], "text": text, "page": page_no, "area": area})

    intersections, segments, unplaced, uncategorized = {}, {}, [], []
    for r in rows:
        sooner, later, unspecified = split_terms(r["text"])
        cats_s, cats_l, cats_u = categories(sooner), categories(later), categories(unspecified)
        if not cats_s and not cats_l and not cats_u and r["text"]:
            uncategorized.append(r)
        is_corner = r["from"].startswith("at ") or (r["to"] == "" and r["control"])
        road, a, b = name(r["road"]), name(r["from"]), name(r["to"])
        if not is_street(r["road"]) or not is_street(r["from"]) or (not is_corner and not is_street(r["to"])):
            unplaced.append(f'{r["project"]}: {r["road"]} / {r["from"]} / {r["to"]}')
            continue
        if is_corner:
            key = (r["project"], road, a)
            e = intersections.setdefault(key, {"project": r["project"], "name": f"{road} & {a}", "streets": [road, a],
                                               "area": r["area"], "page": r["page"], "sooner": [], "later": [], "other": []})
            if (road, a) in MAX_GAP_M:
                e["max_gap_m"] = MAX_GAP_M[(road, a)]
        else:
            key = (r["project"], road, a, b)
            e = segments.setdefault(key, {"project": r["project"], "name": f"{road} from {a} to {b}", "street": road,
                                          "from": a, "to": b, "area": r["area"], "page": r["page"], "sooner": [], "later": [], "other": []})
        e["sooner"] = [c for c in dict.fromkeys(e["sooner"] + cats_s)]
        e["later"] = [c for c in dict.fromkeys(e["later"] + cats_l) if c not in e["sooner"]]
        e["other"] = [c for c in dict.fromkeys(e["other"] + cats_u) if c not in e["sooner"] and c not in e["later"]]

    plan = {
        "_readme": "Generated by pipeline/plans_tod.py from the plan's Priority Project Recommendations, Detailed List. "
                   "Do not edit by hand; change ALIASES or TREATMENTS in the script and rerun.",
        "id": "tod",
        "label": "Walking-to-Caltrain plan",
        "title": "Transit-Oriented Development Pedestrian Access Plan",
        "short": "the city's 2022 plan for walking to Caltrain stations",
        "adopted": "2022-11-21",
        "url": "https://www.cityofsanmateo.org/4566/TOD-Pedestrian-Access-Plan",
        "pdf": PDF_URL,
        "method": "The plan covers walking routes to the Downtown, Hayward Park and Hillsdale Caltrain stations "
                  "and El Camino Real, and doesn't rank its locations. Changes are summarized here in plain words.",
        "unranked": True,
        "list_label": "The plan's project list",
        "intersections": list(intersections.values()),
        "segments": list(segments.values()),
        "not_on_map": unplaced,
    }
    OUT.write_text(json.dumps(plan, indent=1, ensure_ascii=False) + "\n")
    print(f"{len(rows)} rows -> {len(intersections)} intersections, {len(segments)} segments, "
          f"{len(unplaced)} not on a street", file=sys.stderr)
    for u in unplaced:
        print("  not on a street:", u, file=sys.stderr)
    for r in uncategorized:
        print(f"  NO CATEGORY: {r['project']} {r['road']} {r['from']}: {r['text'][:160]}", file=sys.stderr)


if __name__ == "__main__":
    main()
