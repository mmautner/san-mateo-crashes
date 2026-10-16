"""Shared logic for the San Mateo crash pipeline.

Loads the filtered CCRS cache (see fetch.py), selects crashes by location
(San Mateo city limits + 0.5 mile), drops limited-access freeways and their
ramps, classifies each injured person, and builds the intersection list from
OpenStreetMap.
"""
import collections
import csv
import json
import math
import re
from pathlib import Path

from pyproj import Transformer
from shapely import transform as shp_transform
from shapely.geometry import LineString, Point, shape
from shapely.ops import unary_union

HERE = Path(__file__).parent
CACHE = HERE / "cache"
GEO = CACHE / "geo"
MILE = 1609.344
BUFFER_MILES = 0.5

_to_m = Transformer.from_crs(4326, 32610, always_xy=True)
_to_ll = Transformer.from_crs(32610, 4326, always_xy=True)


def project(lon, lat):
    return _to_m.transform(lon, lat)


def unproject(x, y):
    return _to_ll.transform(x, y)


def _proj_geom(g):
    return shp_transform(g, lambda a: list(zip(*_to_m.transform(a[:, 0], a[:, 1]))))


# ---------------------------------------------------------------- geography

def city_polygon():
    gj = json.loads((GEO / "san_mateo_city.geojson").read_text())
    return _proj_geom(shape(gj["features"][0]["geometry"]))


def freeway_lines():
    els = json.loads((GEO / "osm_motorways.json").read_text())["elements"]
    return unary_union([_proj_geom(LineString([(g["lon"], g["lat"]) for g in e["geometry"]])) for e in els])


# ---------------------------------------------------------------- crash rows

def read_csv(path):
    with open(path, newline="", encoding="utf-8-sig") as f:
        return [{k.strip(): (v or "").strip() for k, v in r.items()} for r in csv.DictReader(f)]


def load_year(year):
    d = CACHE / str(year)
    return {
        "meta": json.loads((d / "meta.json").read_text()),
        "crashes": read_csv(d / "crashes.csv"),
        "people": read_csv(d / "people.csv"),
        "parties": read_csv(d / "parties.csv"),
    }


def crash_xy(r):
    try:
        lat, lon = float(r["Latitude"]), float(r["Longitude"])
    except ValueError:
        return None
    if not lat or not lon:
        return None
    if lon > 0:
        lon = -lon
    return project(lon, lat)


# Limited-access freeways through the area and their ramps. Matches the
# PrimaryRoad text as officers write it: "US-101 N/B", "SR-92 WB",
# "US 101 NB TO SR-92 EB", "I-280 SOUTHBOUND", "92 W/B", "SR-92 E/B OFFRAMP".
# SR-82 (El Camino Real) and other surface state routes are not matched.
FREEWAY_RE = re.compile(
    r"\b(US|I|SR|CA|HWY|HIGHWAY|RTE|RT|ROUTE|STATE ROUTE|INTERSTATE)[\s\-]*(101|92|280)\b"
    r"|^\s*(101|92|280)\s*([NSEW]/?B\b|NORTH|SOUTH|EAST|WEST)"
    r"|\bBAYSHORE (FWY|FREEWAY)\b|\bJ\.? ?ARTHUR YOUNGER\b|\bJUNIPERO SERRA (FWY|FREEWAY)\b"
    r"|\bRAMP\b|\b(ON|OFF)-?RAMP\b",
    re.I,
)


def is_freeway(r):
    """Crash is on a freeway or ramp: by the road the officer named as the
    crash location, or by the report's own freeway flag."""
    return bool(FREEWAY_RE.search(r["PrimaryRoad"])) or r.get("IsFreeway") == "True"


# ---------------------------------------------------------------- people

# ExtentOfInjuryCode values. "...Inactive" codes come from older versions of
# the CHP 555 form and are kept with their current equivalents.
SEVERITY = {
    "Fatal": "killed",
    "SuspectSerious": "serious",
    "SevereInactive": "serious",
    "SuspectMinor": "other",
    "PossibleInjury": "other",
    "ComplaintOfPainInactive": "other",
    "OtherVisibleInactive": "other",
}
# Mode of each injured person: walk, bike, scooter (stand-up electric scooters
# and boards), or vehicle (drivers and passengers of cars, trucks, buses,
# motorcycles and mopeds).
BIKE_VEHICLES = {"Bicycle", "ElectricBicycles", "MotorizedBicycle"}
SCOOTER_VEHICLES = {"GoPedZipElectricScooterAndMotorboard"}


def classify_mode(person, party):
    t = person["InjuredPersonType"]
    if t == "Pedestrian":
        return "walk"
    vt = party["Vehicle1TypeDesc"] if party else ""
    if vt in SCOOTER_VEHICLES:
        return "scooter"
    if t == "Bicyclist":
        return "bike"
    if party:
        if party["PartyType"] == "Pedestrian":
            return "walk"
        if party["PartyType"] == "Bicyclist" or vt in BIKE_VEHICLES:
            return "bike"
    return "vehicle"  # drivers, passengers, motorcyclists, bus riders


def hurt_people(year_data, crash_ids, count_witness_flagged=True):
    """People with an injury severity recorded, in the given crashes.

    Rows with no ExtentOfInjuryCode are witnesses or uninjured passengers and
    are skipped. Returns (list of dicts, Counter of skip reasons)."""
    parties = {(p["CollisionId"], p["PartyNumber"]): p for p in year_data["parties"]}
    out, skipped = [], collections.Counter()
    for p in year_data["people"]:
        if p["CollisionId"] not in crash_ids:
            continue
        sev = SEVERITY.get(p["ExtentOfInjuryCode"])
        if sev is None:
            skipped["no injury recorded (witness or uninjured)"] += 1
            continue
        if p["IsWitnessOnly"] == "True" and not count_witness_flagged:
            skipped["injury recorded but flagged witness-only"] += 1
            continue
        party = parties.get((p["CollisionId"], p["PartyNumber"]))
        out.append({
            "crash": p["CollisionId"],
            "severity": sev,
            "mode": classify_mode(p, party),
            "witness_flag": p["IsWitnessOnly"] == "True",
            "person_type": p["InjuredPersonType"],
            "party_type": party["PartyType"] if party else "",
            "vehicle": party["Vehicle1TypeDesc"] if party else "",
            "code": p["ExtentOfInjuryCode"],
        })
    return out, skipped


# ---------------------------------------------------------------- street names

_SUFFIX = {"AVENUE": "AV", "AVE": "AV", "BOULEVARD": "BL", "BLVD": "BL", "STREET": "ST", "DRIVE": "DR",
           "ROAD": "RD", "LANE": "LN", "COURT": "CT", "PLACE": "PL", "PARKWAY": "PKWY", "PKY": "PKWY",
           "HIGHWAY": "HWY", "WAY": "WY", "CIRCLE": "CIR", "TERRACE": "TER", "SQUARE": "SQ"}
_DIR = {"NORTH": "N", "SOUTH": "S", "EAST": "E", "WEST": "W"}
_ORD = {"FIRST": "1ST", "SECOND": "2ND", "THIRD": "3RD", "FOURTH": "4TH", "FIFTH": "5TH", "SIXTH": "6TH",
        "SEVENTH": "7TH", "EIGHTH": "8TH", "NINTH": "9TH", "TENTH": "10TH"}
_SUFFIXES = set(_SUFFIX.values()) | {"AL", "ALY", "TRL", "LOOP", "WALK", "ROW"}


def street_key(name):
    """Core of a street name for matching CCRS text to OSM names:
    'S EL CAMINO REAL' / 'SR-82 (EL CAMINO REAL)' / 'South El Camino Real'
    all give 'EL CAMINO REAL'; 'E 3RD AV' and 'East Third Avenue' give '3RD'."""
    s = name.upper()
    m = re.search(r"\(([^)]+)\)", s)
    if m and re.match(r"\s*(SR|US|I|CA)[\s\-]*\d", s):
        s = m.group(1)
    s = re.sub(r"\(.*?\)", " ", s)
    s = re.sub(r"[^A-Z0-9 ]", " ", s)
    toks = [_ORD.get(t, _DIR.get(t, _SUFFIX.get(t, t))) for t in s.split()]
    toks = [t for t in toks if t not in ("NB", "SB", "EB", "WB", "B")]
    if len(toks) > 1 and toks[0] in ("N", "S", "E", "W"):
        toks = toks[1:]
    if len(toks) > 1 and toks[-1] in _SUFFIXES:
        toks = toks[:-1]
    return " ".join(toks)


# ---------------------------------------------------------------- intersections

ROAD_RANK = {"trunk": 0, "primary": 1, "secondary": 2, "tertiary": 3, "unclassified": 4,
             "residential": 5, "living_street": 6}
MERGE_M = 60  # nodes of the same street pair closer than this are one intersection


def slugify(s):
    s = s.lower().replace("&", " and ")
    return re.sub(r"[^a-z0-9]+", "-", s).strip("-")


def intersections(within=None):
    """Street intersections from OSM, optionally only those inside `within`.

    An intersection is a node shared by streets with two or more different
    names. Nodes for the same name pair within MERGE_M meters (divided roads,
    offset corners) are merged into one point."""
    els = json.loads((GEO / "osm_streets.json").read_text())["elements"]
    nodes = {e["id"]: (e["lon"], e["lat"]) for e in els if e["type"] == "node"}
    names_at = collections.defaultdict(dict)  # node -> {name: rank}
    for w in (e for e in els if e["type"] == "way"):
        name = w["tags"].get("name")
        rank = ROAD_RANK.get(w["tags"]["highway"].removesuffix("_link"), 9)
        for n in w["nodes"]:
            prev = names_at[n].get(name)
            names_at[n][name] = rank if prev is None else min(prev, rank)
    groups = collections.defaultdict(list)  # (nameA, nameB) -> [(x, y)]
    for n, names in names_at.items():
        if len(names) < 2:
            continue
        x, y = project(*nodes[n])
        if within is not None and not within.contains(Point(x, y)):
            continue
        # the two most important streets name the corner
        # skip points where one street just changes prefix (N/S San Mateo Dr)
        distinct = {}
        for k in sorted(names, key=lambda k: (names[k], k)):
            distinct.setdefault(street_key(k), k)
        if len(distinct) < 2:
            continue
        a, b = list(distinct.values())[:2]
        pair = tuple(sorted((a, b), key=lambda k: (names[k], k)))
        groups[pair].append((x, y, names[a] + names[b]))
    out, used = [], collections.Counter()
    for (a, b), pts in groups.items():
        clusters = []
        for x, y, r in pts:
            for c in clusters:
                if math.dist((x, y), c["c"]) < MERGE_M:
                    c["pts"].append((x, y))
                    c["c"] = tuple(sum(v) / len(c["pts"]) for v in zip(*c["pts"]))
                    break
            else:
                clusters.append({"pts": [(x, y)], "c": (x, y), "rank": r})
        for c in clusters:
            base = slugify(f"{a} & {b}")
            used[base] += 1
            slug = base if used[base] == 1 else f"{base}-{used[base]}"
            lon, lat = unproject(*c["c"])
            out.append({"id": slug, "a": a, "b": b, "x": c["c"][0], "y": c["c"][1],
                        "lon": round(lon, 6), "lat": round(lat, 6), "rank": c["rank"]})
    return out


def intersection_index(ints):
    """(street_key, street_key) -> list of intersections, both orders."""
    idx = collections.defaultdict(list)
    for i in ints:
        ka, kb = street_key(i["a"]), street_key(i["b"])
        idx[(ka, kb)].append(i)
        idx[(kb, ka)].append(i)
    return idx


# ---------------------------------------------------------------- locating crashes

MOVE_IF_OFF_M = 200    # coordinates this far from the described spot are replaced
AMBIGUOUS_M = 300      # same two street names meeting this far apart: don't guess


def stated_offset(r):
    """Distance (m) and unit vector from the reference intersection, from the
    report's SecondaryDistance / SecondaryDirection (unit F = feet, M = miles)."""
    try:
        d = float(r["SecondaryDistance"] or 0)
    except ValueError:
        d = 0
    d *= MILE if r["SecondaryUnitOfMeasure"].upper().startswith("M") else 0.3048
    v = {"N": (0, 1), "S": (0, -1), "E": (1, 0), "W": (-1, 0)}.get(r["SecondaryDirection"].upper()[:1], (0, 0))
    return d, v


def described_location(r, idx):
    """Where the report's street description puts the crash: the intersection
    of PrimaryRoad and SecondaryRoad, moved by the stated distance and
    direction. None if the names don't match exactly one place."""
    hits = idx.get((street_key(r["PrimaryRoad"]), street_key(r["SecondaryRoad"])), [])
    if not hits or any(math.dist((hits[0]["x"], hits[0]["y"]), (h["x"], h["y"])) > AMBIGUOUS_M for h in hits):
        return None
    d, (vx, vy) = stated_offset(r)
    return hits[0]["x"] + d * vx, hits[0]["y"] + d * vy


def locate(r, idx):
    """(x, y, how). how is 'reported' (report's coordinates), 'street_names'
    (no coordinates; placed from the street description) or 'moved'
    (coordinates more than MOVE_IF_OFF_M from the street description; the
    description wins). (None, None, 'unplaced') if neither is usable."""
    xy = crash_xy(r)
    desc = described_location(r, idx) if r["SecondaryRoad"] else None
    if xy is None:
        return (*desc, "street_names") if desc else (None, None, "unplaced")
    if desc and math.dist(xy, desc) > MOVE_IF_OFF_M:
        return (*desc, "moved")
    return (*xy, "reported")


_ABBR = {"Avenue": "Ave", "Boulevard": "Blvd", "Street": "St", "Drive": "Dr", "Road": "Rd", "Lane": "Ln",
         "Court": "Ct", "Place": "Pl", "Parkway": "Pkwy", "Circle": "Cir", "Terrace": "Ter", "Highway": "Hwy"}
_DIRS = {"North": "N", "South": "S", "East": "E", "West": "W"}


def short_name(name):
    """'North San Mateo Drive' -> 'N San Mateo Dr'; 'Alameda de las Pulgas' unchanged."""
    w = name.split()
    if len(w) > 1 and w[0] in _DIRS:
        w[0] = _DIRS[w[0]]
    if len(w) > 1 and w[-1] in _ABBR:
        w[-1] = _ABBR[w[-1]]
    return " ".join(w)


# ---------------------------------------------------------------- crash details (plain language)
# Shown when someone taps a crash. Causes are the officer's judgment at the scene.

CRASH_TYPE = {
    "BROADSIDE": "Side-impact (broadside)", "REAR END": "Rear-end", "VEHICLE/PEDESTRAIN": "Vehicle hit a person walking",
    "VEHICLE/PEDESTRIAN": "Vehicle hit a person walking", "SIDE SWIPE": "Sideswipe", "HEAD-ON": "Head-on",
    "HIT OBJECT": "Hit an object", "OVERTURNED": "Rollover", "OTHER": "Other",
}
LIGHT = {
    "DAYLIGHT": "Daylight", "DUSK-DAWN": "Dusk or dawn", "DARK-STREET LIGHTS": "Dark, street lights on",
    "DARK-NO STREET LIGHTS": "Dark, no street lights", "DARK-STREET LIGHTS NOT FUNCTIONING*": "Dark, street lights not working",
}
PED_ACTION = {
    "CROSSING IN CROSS WALK AT INTERSECTION": "Crossing in the crosswalk at the intersection",
    "CROSSING IN CROSS WALK - NOT AT INTERSECTION": "Crossing in a mid-block crosswalk",
    "CROSSING - NOT IN CROSSWALK": "Crossing outside a crosswalk",
    "IN ROAD - INCLUDES SHOULDER": "In the road or on the shoulder",
    "NOT IN ROAD": "Not in the road (sidewalk or driveway)",
}
MOVEMENT = {
    "PROCEEDING STRAIGHT": "going straight", "MAKING LEFT TURN": "turning left", "MAKING RIGHT TURN": "turning right",
    "ENTERING TRAFFICD": "entering traffic", "ENTERING TRAFFIC": "entering traffic", "OTHER UNSAFE TURNING": "turning unsafely",
    "SLOWING/STOPPING": "slowing or stopping", "BACKING": "backing up", "CHANGING LANES": "changing lanes",
    "MAKING U TURN": "making a U-turn", "STOPPED": "stopped", "TRAVELLING WRONG WAY": "going the wrong way",
    "RAN OFF ROAD": "running off the road", "PASSING OTHER VEHICLE": "passing", "PARKED": "parked",
    "PARKING MANEUVER": "parking", "MERGING": "merging", "XING INTO OPPOSING LANE": "crossing into oncoming lanes",
    "LANE SPLITTING": "lane splitting",
}
# California Vehicle Code section -> what the officer said caused the crash
CAUSE = {
    "22350": "Unsafe speed for conditions",
    "22107": "Unsafe turn or lane change",
    "21950A": "Driver didn't yield to someone in a crosswalk",
    "21950": "Driver didn't yield to someone in a crosswalk",
    "21950B": "Person walking stepped into a vehicle's path",
    "21950C": "Driver didn't slow for someone in a crosswalk",
    "21453A": "Ran a red light", "21453": "Ran a red light", "21453B": "Ran a red light",
    "21453C": "Turned against a red arrow", "21453D": "Person walking against a red light",
    "21802A": "Didn't yield after stopping at a stop sign", "21802": "Didn't yield after stopping at a stop sign",
    "21801A": "Didn't yield while turning left or making a U-turn", "21801": "Didn't yield while turning left or making a U-turn",
    "22106": "Unsafe start or backing up",
    "21804A": "Didn't yield pulling out of a driveway or parking lot", "21804": "Didn't yield pulling out of a driveway or parking lot",
    "23152A": "Driving under the influence", "23152B": "Driving under the influence", "23152": "Driving under the influence",
    "23153A": "Driving under the influence", "23153B": "Driving under the influence", "23153": "Driving under the influence",
    "21703": "Following too closely",
    "21650": "On the wrong side of the road", "21650.1": "Riding a bike against traffic", "216501": "Riding a bike against traffic",
    "21658A": "Unsafe lane change", "21658": "Unsafe lane change",
    "22450A": "Didn't stop at a stop sign", "22450": "Didn't stop at a stop sign",
    "21800A": "Didn't yield at an intersection", "21800": "Didn't yield at an intersection",
    "21800B": "Didn't yield at an intersection", "21800C": "Didn't yield at an intersection",
    "21954A": "Person walking outside a crosswalk didn't yield", "21954": "Person walking outside a crosswalk didn't yield",
    "21952": "Driver didn't yield to a person on the sidewalk",
    "22517": "Car door opened into traffic",
    "21202": "Bike not riding near the right edge", "21202A": "Bike not riding near the right edge",
    "21955": "Person walking crossed between signals",
    "21456": "Person walking against the walk signal", "21456A": "Person walking against the walk signal",
    "21456B": "Person walking against the walk signal",
    "21460": "Crossed double yellow lines", "21460A": "Crossed double yellow lines",
    "21750": "Unsafe passing", "21755": "Unsafe passing on the right", "21755A": "Unsafe passing on the right",
    "22100": "Turned from the wrong lane", "22100A": "Turned from the wrong lane", "22100B": "Turned from the wrong lane",
    "23103": "Reckless driving", "23103A": "Reckless driving",
    "21451A": "Didn't yield on a green light", "21451": "Didn't yield on a green light",
    "21452A": "Ran a yellow light", "21457A": "Didn't stop at a flashing red", "21457": "Didn't stop at a flashing red",
    "21651": "Crossed a divider", "21651A": "Crossed a divider", "21651B": "Wrong way on a divided road",
    "21663": "Driving on the sidewalk", "21212": "Bike or scooter rider safety rule", "21235": "Scooter rule violation",
    "22101": "Ignored a turn-restriction sign", "22101D": "Ignored a turn-restriction sign",
    "21200": "Bike rider broke a traffic rule", "21201": "Bike missing required equipment",
    "21208": "Bike not using the bike lane", "21209": "Driver in the bike lane", "21209A": "Driver in the bike lane",
    "22526": "Blocked an intersection", "21717": "Unsafe turn across a bike lane",
    "21760": "Passed a bike too closely", "21760A": "Passed a bike too closely", "21760B": "Passed a bike too closely",
    "21760C": "Passed a bike too closely", "22103": "Unsafe U-turn", "21461A": "Ignored a traffic sign",
    "21461": "Ignored a traffic sign", "22109": "Stopped suddenly without signaling", "21751": "Unsafe passing",
    "22108": "Didn't signal before turning", "21803": "Didn't yield at a yield sign", "21803A": "Didn't yield at a yield sign",
    "22515": "Parked vehicle rolled away", "22515A": "Parked vehicle rolled away", "23104": "Reckless driving",
    "23104A": "Reckless driving", "UNSAFETURN": "Unsafe turn or lane change", "22400A": "Driving too slowly for traffic",
}


def normalize_section(s):
    """'21950(a) CVC' / 'CVC 21950(a)' / '21950A' / '22350 cvc' -> '21950A' / '22350'."""
    s = re.sub(r"\b(CVC|VC)\b", "", s.upper())
    s = re.sub(r"\(([A-Z0-9]+)\)", r"\1", s)
    return re.sub(r"[^0-9A-Z.]", "", s)


def cause_text(raw):
    code = normalize_section(raw)
    if not code:
        return ""
    if code in CAUSE:
        return CAUSE[code]
    base = re.match(r"\d+(\.\d+)?", code)
    if base and base.group(0) in CAUSE:
        return CAUSE[base.group(0)]
    return f"Vehicle Code {code}"


def primary_party_text(party):
    """'Driver turning left', 'Person on a bike going straight', 'Person walking'."""
    if not party:
        return ""
    pt, vt = party["PartyType"], party["Vehicle1TypeDesc"]
    if pt == "Pedestrian":
        return "Person walking"
    if pt == "ParkedVehicle":
        return "Parked vehicle"
    if pt == "Bicyclist" or vt in BIKE_VEHICLES:
        who = "Person on a bike"
    elif vt in SCOOTER_VEHICLES:
        who = "Person on a scooter"
    elif vt in ("Motorcycle", "MotorDrivenCycleScooter15HpOrLess"):
        who = "Motorcyclist"
    elif vt == "OtherUnknownHitAndRunDriver":
        who = "Hit-and-run driver"
    else:
        who = "Driver"
    move = MOVEMENT.get(party["MovementPrecCollDescription"], "")
    return f"{who} {move}".strip()


def crash_details(r, parties):
    """Plain-language facts from one report, for the tap-to-see card."""
    t = r["Crash Time Description"]
    hour = int(t[:-2]) if re.fullmatch(r"\d{3,4}", t) and int(t[:-2]) < 24 else None
    prim = next((p for p in parties if p["PartyNumber"] == r["PrimaryCollisionPartyNumber"]), None)
    return {
        "hour": hour,
        "light": LIGHT.get(r["LightingDescription"], ""),
        "type": CRASH_TYPE.get(r["Collision Type Description"], ""),
        "cause": cause_text(r["Primary Collision Factor Violation"]),
        "who": primary_party_text(prim),
        "ped": PED_ACTION.get(r["PedestrianActionDesc"], ""),
        "hitrun": r["HitRun"] in ("F", "M"),
    }
