"""Stage 1 data report. Prints Markdown to stdout.

    python pipeline/report.py > pipeline/REPORT.md
"""
import collections
import math
import random
import statistics
import sys

from shapely import STRtree
from shapely.geometry import Point

import build as B

YEARS = range(2016, 2026)
DEFAULT_YEARS = range(*[int(v) + i for i, v in enumerate(sys.argv[1].split('-'))]) if len(sys.argv) > 1 else range(2023, 2026)
DEFAULT_RADIUS = 0.25 * B.MILE
OTS_2023 = 292

city = B.city_polygon()
area = city.buffer(B.BUFFER_MILES * B.MILE)
fwy = B.freeway_lines()
ints_all = B.intersections()
ints_city = [i for i in ints_all if city.contains(Point(i["x"], i["y"]))]
idx = B.intersection_index(ints_all)


def offset(r):
    return B.stated_offset(r)


def people_summary(ppl):
    c = collections.Counter(p["mode"] for p in ppl)
    s = collections.Counter(p["severity"] for p in ppl)
    return f"{len(ppl)} (walking {c['walk']}, biking {c['bike']}, scooters {c['scooter']}, in vehicles {c['vehicle']}; killed {s['killed']}, serious {s['serious']}, other {s['other']})"


def pct(n, d):
    return f"{100 * n / d:.1f}%" if d else "–"


# ------------------------------------------------------------------ load all years
data, yearly, located_all = {}, [], []
for y in YEARS:
    yd = B.load_year(y)
    data[y] = yd
    crashes = yd["crashes"]
    loc, missing, geocoded, unplaced = [], [], [], []
    for r in crashes:
        x, yy, how = B.locate(r, idx)
        r["_geocoded"] = how if how in ("street_names", "moved") else None
        if B.crash_xy(r) is None:
            missing.append(r)
        if how == "unplaced":
            if r["City Name"] == "San Mateo":
                unplaced.append(r)
            continue
        xy = (x, yy)
        r["_xy"] = xy
        if area.contains(Point(*xy)):
            loc.append(r)
            if r["_geocoded"]:
                geocoded.append(r)
    named = [r for r in crashes if r["City Name"] == "San Mateo"]
    kept = [r for r in loc if not B.is_freeway(r)]
    ppl, skipped = B.hurt_people(yd, {r["Collision Id"] for r in kept})
    for r in kept:
        r["_year"] = y
    located_all += kept
    yearly.append(dict(year=y, meta=yd["meta"], named=named, named_missing=[r for r in named if B.crash_xy(r) is None],
                       loc=loc, kept=kept, ppl=ppl, skipped=skipped, missing=missing, geocoded=geocoded, unplaced=unplaced))

out = []
P = out.append

P("# Stage 1 data report: San Mateo crashes\n")
m23 = data[2023]["meta"]
P(f"CCRS files downloaded {m23['downloaded']} from data.ca.gov (package `ccrs`). "
  f"City boundary: County of San Mateo GIS, Admin_Features layer 0 (CITY), feature \"SAN MATEO\". "
  f"Freeway and street geometry: OpenStreetMap via Overpass. Study area = city limits + {B.BUFFER_MILES} mile.\n")

# ------------------------------------------------------------------ 2023 funnel
y23 = next(v for v in yearly if v["year"] == 2023)
yd = data[2023]
P("## 1. 2023 in detail\n")
P("### How the count is built\n")
P("| Step | Crashes | People hurt |\n|---|---:|---:|")


def row(label, crashes):
    ppl, _ = B.hurt_people(yd, {r["Collision Id"] for r in crashes})
    P(f"| {label} | {len(crashes)} | {people_summary(ppl)} |")
    return ppl


row("Reports with City Name = San Mateo (any road)", y23["named"])
in_city = [r for r in y23["loc"] if city.contains(Point(*r["_xy"]))]
row("Located inside city limits (any road)", in_city)
row("Located inside city limits, freeways and ramps removed", [r for r in in_city if not B.is_freeway(r)])
row("City + 0.5 mi buffer (any road)", y23["loc"])
p23 = row("**City + 0.5 mi buffer, freeways and ramps removed (what the tool uses)**", y23["kept"])
fw23 = [r for r in y23["loc"] if B.is_freeway(r)]
fwp, _ = B.hurt_people(yd, {r["Collision Id"] for r in fw23})
P(f"\nFreeway exclusion removes **{len(fw23)} crashes** in the study area and **{len(fwp)} people hurt** "
  f"({sum(p['severity'] == 'killed' for p in fwp)} killed). "
  f"The 0.5-mile buffer adds {len(y23['kept']) - len([r for r in in_city if not B.is_freeway(r)])} surface-street crashes from neighboring cities.\n")
P("Crashes in the buffer by reported city: " + ", ".join(f"{k} {v}" for k, v in collections.Counter(r["City Name"] for r in y23["kept"]).most_common()) + "\n")

P("### Comparison with OTS (292 killed or injured in San Mateo city, 2023)\n")
smpd = [r for r in y23["named"] if r["NCIC Code"] == "4116"]
chp = [r for r in y23["named"] if r["NCIC Code"] != "4116"]
for label, cs in (("City Name = San Mateo, all roads", y23["named"]),
                  ("…reported by San Mateo Police (NCIC 4116)", smpd),
                  ("…reported by CHP (NCIC 93xx)", chp),
                  ("City Name = San Mateo, freeways removed", [r for r in y23["named"] if not B.is_freeway(r)]),
                  ("Inside city limits by location, freeways removed", [r for r in in_city if not B.is_freeway(r)])):
    ppl, _ = B.hurt_people(yd, {r["Collision Id"] for r in cs})
    ppl_strict, _ = B.hurt_people(yd, {r["Collision Id"] for r in cs}, count_witness_flagged=False)
    rep = sum(int(r["NumberInjured"] or 0) + int(r["NumberKilled"] or 0) for r in cs)
    P(f"- {label}: {len(ppl)} people (crash-level NumberInjured+NumberKilled = {rep}; excluding witness-flagged = {len(ppl_strict)})")
P("")

wf = [p for p in p23 if p["witness_flag"]]
P(f"### People with an injury recorded but flagged witness-only (2023, tool area): {len(wf)}\n")
for p in wf:
    r = next(c for c in y23["kept"] if c["Collision Id"] == p["crash"])
    P(f"- crash {p['crash']}: {p['code']}, person type '{p['person_type'] or '-'}', party {p['party_type']}/{p['vehicle']}; "
      f"crash total injured {r['NumberInjured']}; {r['PrimaryRoad']} & {r['SecondaryRoad']}")
P("")

P("### Field values used (2023, tool area)\n")
P("Injury severity (`ExtentOfInjuryCode`):\n")
for code, n in collections.Counter(p["code"] for p in p23).most_common():
    P(f"- `{code}` → {B.SEVERITY[code]}: {n}")
P(f"- blank → not counted (witness or uninjured): {y23['skipped'].get('no injury recorded (witness or uninjured)', 0)} person rows\n")
P("Mode (`InjuredPersonType`, then the person's party `PartyType` / `Vehicle1TypeDesc`):\n")
for (pt, party, veh, mode), n in collections.Counter((p["person_type"], p["party_type"], p["vehicle"], p["mode"]) for p in p23).most_common():
    P(f"- {pt or '(blank)'} / {party} / {veh or '(blank)'} → {mode}: {n}")
P("")

# ------------------------------------------------------------------ by year
P("## 2. All years (study area, freeways removed)\n")
P("| Year | Crashes kept | People hurt | Walking | Biking | In vehicles | Killed | Serious | Freeway crashes removed | No coords (SM + neighbors) | …placed from street names | …unplaced, City Name = San Mateo | Downloaded |")
P("|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|")
for v in yearly:
    c = collections.Counter(p["mode"] for p in v["ppl"])
    s = collections.Counter(p["severity"] for p in v["ppl"])
    P(f"| {v['year']} | {len(v['kept'])} | {len(v['ppl'])} | {c['walk']} | {c['bike']} | {c['vehicle']} | {s['killed']} | {s['serious']} | "
      f"{len(v['loc']) - len(v['kept'])} | {len(v['missing'])} | {len(v['geocoded'])} | {len(v['unplaced'])} | {v['meta']['downloaded']} |")
prior = [len(v["ppl"]) for v in yearly if v["year"] in (2023, 2024)]  # last complete years without agency gaps
last = yearly[-1]
P(f"\n2025 people hurt = {len(last['ppl'])} vs 2023–2024 average {statistics.mean(prior):.0f} "
  f"({100 * (len(last['ppl']) / statistics.mean(prior) - 1):+.0f}%).\n")

P("### Reporting gaps by agency (crash reports per month)\n")
P("| Year | San Mateo PD reports | months with ≤3 | CHP reports (City Name = San Mateo) | Belmont | Foster City | Burlingame | Hillsborough |")
P("|---|---:|---:|---:|---:|---:|---:|---:|")
for v in yearly:
    cr = data[v["year"]]["crashes"]
    smpd = [r for r in v["named"] if r["NCIC Code"] == "4116"]
    months = collections.Counter(int(r["Crash Date Time"].split("/")[0]) for r in smpd)
    low = [m for m in range(1, 13) if months.get(m, 0) <= 3]
    local = lambda c: sum(1 for r in cr if r["City Name"] == c and not r["NCIC Code"].startswith("93"))
    P(f"| {v['year']} | {len(smpd)} | {len(low)}{' (' + ','.join(map(str, low)) + ')' if low else ''} | "
      f"{sum(1 for r in v['named'] if r['NCIC Code'].startswith('93'))} | {local('Belmont')} | {local('Foster City')} | {local('Burlingame')} | {local('Hillsborough')} |")
P("")
P("### Missing coordinates\n")
for v in yearly:
    nm = v["named_missing"]
    P(f"- {v['year']}: City Name = San Mateo missing coordinates: {len(nm)} of {len(v['named'])} ({pct(len(nm), len(v['named']))}); "
      f"all nearby-city reports missing coordinates: {len(v['missing'])}, placed from street names and inside study area: {len(v['geocoded'])}")
P("\nUnplaced San Mateo reports (2021–2025) with anyone hurt:\n")
for v in yearly:
    if v["year"] < 2021:
        continue
    for r in v["unplaced"]:
        ppl, _ = B.hurt_people(data[v["year"]], {r["Collision Id"]})
        if ppl:
            P(f"- {r['Crash Date Time'][:10]} {r['PrimaryRoad']} & {r['SecondaryRoad']}: {people_summary(ppl)}; freeway={B.is_freeway(r)}")
P("")

# ------------------------------------------------------------------ intersections
P(f"## 3. Intersections at default settings (0.25 mile, {DEFAULT_YEARS[0]}–{DEFAULT_YEARS[-1]})\n")
pts = [r for r in located_all if r["_year"] in DEFAULT_YEARS]
ppl_by_crash = collections.defaultdict(list)
for y in DEFAULT_YEARS:
    v = next(v for v in yearly if v["year"] == y)
    for p in v["ppl"]:
        ppl_by_crash[p["crash"]].append(p)
geoms = [Point(*r["_xy"]) for r in pts]
tree = STRtree(geoms)
counts = []
for i in ints_city:
    near = tree.query(Point(i["x"], i["y"]), predicate="dwithin", distance=DEFAULT_RADIUS)
    ppl = [p for k in near for p in ppl_by_crash[pts[k]["Collision Id"]]]
    m = collections.Counter(p["mode"] for p in ppl)
    i["n"], i["walk"], i["bike"], i["veh"] = len(ppl), m["walk"], m["bike"], m["vehicle"]
    i["killed"] = sum(p["severity"] == "killed" for p in ppl)
    counts.append(len(ppl))
counts.sort()
q = statistics.quantiles(counts, n=20)
P(f"{len(ints_city)} intersections inside city limits (OSM nodes where two differently named streets meet; "
  f"same-name pairs within {B.MERGE_M} m merged).\n")
P(f"- median: **{statistics.median(counts):.0f}** people hurt within 0.25 mi")
P(f"- 25th percentile: {q[4]:.0f}; 75th: **{q[14]:.0f}**; 90th: **{q[17]:.0f}**; max: {counts[-1]}")
P(f"- share with zero: **{pct(sum(c == 0 for c in counts), len(counts))}**; with 1–4: {pct(sum(1 <= c <= 4 for c in counts), len(counts))}")
P(f"- total people hurt in study area {DEFAULT_YEARS[0]}–{DEFAULT_YEARS[-1]} (freeways removed): {sum(len(v) for v in ppl_by_crash.values())}\n")
P("Top 15:\n")
P("| # | Intersection | People hurt | Walking | Biking | In vehicles | Killed |\n|---:|---|---:|---:|---:|---:|---:|")
for n, i in enumerate(sorted(ints_city, key=lambda i: -i["n"])[:15], 1):
    P(f"| {n} | {i['a']} & {i['b']} | {i['n']} | {i['walk']} | {i['bike']} | {i['veh']} | {i['killed']} |")
for name in (("Alameda de las Pulgas", "Aragon Boulevard"), ("Monte Diablo Avenue", "North San Mateo Drive")):
    hit = [i for i in ints_city if {i["a"], i["b"]} == set(name)]
    for i in hit:
        rank = sum(c < i["n"] for c in counts) / len(counts)
        P(f"\nTest intersection {i['a']} & {i['b']}: {i['n']} people (walking {i['walk']}, biking {i['bike']}, in vehicles {i['veh']}, killed {i['killed']}); "
          f"more than {100 * rank:.0f}% of intersections")
    if not hit:
        P(f"\nTest intersection {name}: NOT FOUND in OSM intersection list")
P("")

# ------------------------------------------------------------------ coordinate checks
P("## 4. Coordinates vs. street descriptions\n")
checked = []
for r in pts:
    if r["_geocoded"] or not r["SecondaryRoad"]:
        continue
    hits = idx.get((B.street_key(r["PrimaryRoad"]), B.street_key(r["SecondaryRoad"])), [])
    if not hits:
        continue
    near = min(hits, key=lambda h: math.dist(r["_xy"], (h["x"], h["y"])))
    d_off, _ = offset(r)
    gap = math.dist(r["_xy"], (near["x"], near["y"]))
    checked.append((r, near, gap, d_off))
P(f"Of {len(pts)} located crashes {DEFAULT_YEARS[0]}–{DEFAULT_YEARS[-1]}, {len(checked)} have street names that match an OSM intersection. "
  f"Distance from the reported coordinates to that intersection, minus the stated offset:\n")
err = sorted(abs(g - o) for _, _, g, o in checked)
for t in (25, 50, 100, 200, 400):
    P(f"- within {t} m: {pct(sum(e <= t for e in err), len(err))}")
P("")
P("Five randomly chosen crashes (seed 2023):\n")
rnd = random.Random(2023)
for r, near, gap, d_off in rnd.sample(checked, 5):
    lon, lat = B.unproject(*r["_xy"])
    P(f"- **{r['Crash Date Time'][:10]}**, report says *{r['PrimaryRoad']}* & *{r['SecondaryRoad']}*"
      f"{f', {r[chr(83)+'econdaryDistance']} {r['SecondaryUnitOfMeasure'] or 'ft'} {r['SecondaryDirection']}' if d_off else ', at the intersection'}. "
      f"Coordinates {lat:.5f}, {lon:.5f} are {gap:.0f} m from OSM {near['a']} & {near['b']}.")
far = [(r, n, g, o) for r, n, g, o in checked if abs(g - o) > 200]
P(f"\nLargest mismatches ({len(far)} over 200 m):\n")
for r, near, gap, d_off in sorted(far, key=lambda t: -abs(t[2] - t[3]))[:8]:
    P(f"- {r['Crash Date Time'][:10]} {r['PrimaryRoad']} & {r['SecondaryRoad']}: {gap:.0f} m from the intersection, stated offset {d_off:.0f} m")

print("\n".join(out))
