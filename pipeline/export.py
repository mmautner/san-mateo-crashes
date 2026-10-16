"""Write the page's data files.

    python pipeline/fetch.py          # once a year (or --refresh)
    python pipeline/export.py         # -> site/data/crashes.json, site/data/intersections.json

crashes.json
  crashes: [x, y, date, place, how, people, details] per crash with at least one person hurt
    x, y    longitude/latitude × 1e5, as integers
    date    "YYYY-MM-DD"; "YYYY-MM" when someone was killed (no day is published)
    place   index into `places` (nearest intersection label), or -1
    how     0 = report's coordinates, 1 = placed from the street description
            (no coordinates, or coordinates > 200 m from the description)
    people  string of 2-letter codes, one per person hurt:
            mode (w walking, b biking, s scooter, v in a vehicle) +
            severity (k killed, s seriously injured, o other injury)
    details 0 for crashes where someone was killed (only month, year and mode are published);
            otherwise [hour or -1, light, type, cause, who, ped, hit_and_run], where light..ped
            are indexes into text[light|type|cause|who|ped] (index 0 = not recorded)
  no_injury: [x, y, year - 2000] for each reported crash in the same area where no one was hurt
intersections.json
  [id, label, lon×1e5, lat×1e5, council district] for each intersection in city limits
"""
import collections
import datetime
import json
import math
import sys

from shapely import STRtree
from shapely.geometry import Point

import build as B

FIRST_YEAR = 2017          # 2016: San Mateo Police reports almost entirely missing
DEFAULT_FIRST_YEAR = 2023  # first year after the Aug 2021 – Jul 2022 reporting gap
GAPS = [{"agency": "San Mateo Police", "from": "2021-08", "to": "2022-07"}]
PLACE_WITHIN_M = 150

OUT = B.HERE.parent / "site" / "data"
MODE = {"walk": "w", "bike": "b", "scooter": "s", "vehicle": "v"}
SEV = {"killed": "k", "serious": "s", "other": "o"}


def council_districts():
    gj = json.loads((B.GEO / "council_districts.geojson").read_text())
    from shapely.geometry import shape
    return [(int(f["properties"]["DISTRICT"]), B._proj_geom(shape(f["geometry"]))) for f in gj["features"]]


def district_of(pt, districts):
    for n, poly in districts:
        if poly.contains(pt):
            return n
    # on a boundary street: nearest district
    return min(districts, key=lambda d: d[1].distance(pt))[0]


def label(i):
    return f"{B.short_name(i['a'])} & {B.short_name(i['b'])}"


def main():
    years = sorted(int(p.name) for p in B.CACHE.iterdir() if p.name.isdigit())
    last_full = datetime.date.today().year - 1
    years = [y for y in years if FIRST_YEAR <= y <= last_full]

    city = B.city_polygon()
    area = city.buffer(B.BUFFER_MILES * B.MILE)
    ints_all = B.intersections()
    idx = B.intersection_index(ints_all)
    districts = council_districts()

    # labels: sort each pair alphabetically so ids are predictable
    for i in ints_all:
        a, b = sorted((B.short_name(i["a"]), B.short_name(i["b"])), key=str.lower)
        i["label"] = f"{a} & {b}"
        i["slug"] = B.slugify(i["label"])
    tree = STRtree([Point(i["x"], i["y"]) for i in ints_all])

    places, place_ix = [], {}
    text = {k: [""] for k in ("light", "type", "cause", "who", "ped")}
    text_ix = {k: {"": 0} for k in text}

    def tix(kind, value):
        ix = text_ix[kind]
        if value not in ix:
            ix[value] = len(text[kind])
            text[kind].append(value)
        return ix[value]
    crashes, stats, downloaded = [], collections.Counter(), set()
    no_injury = []
    for y in years:
        yd = B.load_year(y)
        downloaded.add(yd["meta"]["downloaded"])
        kept, freeway_ids = {}, set()
        for r in yd["crashes"]:
            x, yy, how = B.locate(r, idx)
            if how == "unplaced":
                stats["unplaced"] += 1
                continue
            if not area.contains(Point(x, yy)):
                continue
            if B.is_freeway(r):
                stats["freeway"] += 1
                freeway_ids.add(r["Collision Id"])
                continue
            r["_loc"] = (x, yy, how)
            kept[r["Collision Id"]] = r
        people, _ = B.hurt_people(yd, set(kept))
        parties_by = collections.defaultdict(list)
        for p in yd["parties"]:
            if p["CollisionId"] in kept:
                parties_by[p["CollisionId"]].append(p)
        fw_people, _ = B.hurt_people(yd, freeway_ids)
        stats["freeway_people"] += len(fw_people)
        stats["freeway_killed"] += sum(p["severity"] == "killed" for p in fw_people)
        by_crash = collections.defaultdict(list)
        for p in people:
            by_crash[p["crash"]].append(p)
        for cid, r in kept.items():
            if cid not in by_crash:  # reported, but no one hurt
                lon, lat = B.unproject(*r["_loc"][:2])
                no_injury.append([round(lon * 1e5), round(lat * 1e5), y - 2000])
        for cid, ppl in by_crash.items():
            r = kept[cid]
            x, yy, how = r["_loc"]
            stats[how] += 1
            lon, lat = B.unproject(x, yy)
            m, d, yr = r["Crash Date Time"].split()[0].split("/")
            killed = any(p["severity"] == "killed" for p in ppl)
            date = f"{yr}-{int(m):02d}" if killed else f"{yr}-{int(m):02d}-{int(d):02d}"
            near = tree.query_nearest(Point(x, yy), max_distance=PLACE_WITHIN_M)
            place = -1
            if len(near):
                lab = ints_all[int(near[0])]["label"]
                place = place_ix.setdefault(lab, len(places))
                if place == len(places):
                    places.append(lab)
            order = sorted(ppl, key=lambda p: ("kso".index(SEV[p["severity"]]), p["mode"]))
            details = 0
            if not killed:
                dd = B.crash_details(r, parties_by[cid])
                details = [-1 if dd["hour"] is None else dd["hour"], *(tix(k, dd[k]) for k in ("light", "type", "cause", "who", "ped")),
                           1 if dd["hitrun"] else 0]
            crashes.append([round(lon * 1e5), round(lat * 1e5), date, place, 0 if how == "reported" else 1,
                            "".join(MODE[p["mode"]] + SEV[p["severity"]] for p in order), details])
    crashes.sort(key=lambda c: c[2], reverse=True)

    # intersections inside city limits; same label in two places gets a suffix
    seen = collections.Counter()
    ints_out = []
    for i in sorted((i for i in ints_all if city.contains(Point(i["x"], i["y"]))), key=lambda i: (i["slug"], i["x"])):
        seen[i["slug"]] += 1
        slug = i["slug"] if seen[i["slug"]] == 1 else f"{i['slug']}-{seen[i['slug']]}"
        ints_out.append([slug, i["label"], round(i["lon"] * 1e5), round(i["lat"] * 1e5),
                         district_of(Point(i["x"], i["y"]), districts)])

    meta = {
        "source": "California Highway Patrol, California Crash Reporting System (CCRS), data.ca.gov",
        "downloaded": max(downloaded),
        "built": datetime.date.today().isoformat(),
        "years": [years[0], years[-1]],
        "default_years": [DEFAULT_FIRST_YEAR, years[-1]],
        "gaps": GAPS,
        "data_through": f"{years[-1]}-12",
        "counts": {
            "crashes": len(crashes),
            "people": sum(len(c[5]) // 2 for c in crashes),
            "killed": sum(c[5][1::2].count("k") for c in crashes),
            "freeway_crashes_removed": stats["freeway"],
            "freeway_people_removed": stats["freeway_people"],
            "freeway_killed_removed": stats["freeway_killed"],
            "placed_from_street_names": stats["street_names"],
            "moved_to_street_description": stats["moved"],
            "intersections": None,
            "no_injury_crashes": None,
        },
    }
    meta["counts"]["intersections"] = len(ints_out)
    meta["counts"]["no_injury_crashes"] = len(no_injury)
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "crashes.json").write_text(json.dumps({"meta": meta, "places": places, "text": text, "crashes": crashes, "no_injury": no_injury}, separators=(",", ":")))
    (OUT / "intersections.json").write_text(json.dumps(ints_out, separators=(",", ":")))
    n_people = sum(len(c[5]) // 2 for c in crashes)
    print(f"{len(crashes)} crashes, {n_people} people hurt, {len(ints_out)} intersections, years {years[0]}-{years[-1]}", file=sys.stderr)
    print(f"placement: {dict(stats)}", file=sys.stderr)
    for f in ("crashes.json", "intersections.json"):
        print(f, (OUT / f).stat().st_size, "bytes", file=sys.stderr)


if __name__ == "__main__":
    main()
