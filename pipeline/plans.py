"""Match city plans' named locations to this site's intersections.

    python pipeline/plans.py      # site/plans/*.json -> site/data/plans.json

Each site/plans/<id>.json is entered by hand from a city plan (see its _readme).
This script only locates what the plans name; it never changes their contents,
so rerunning it gives the same output. It stops with an error if a named
location can't be matched to exactly one place.
"""
import json
import math
import re
import sys

from shapely.geometry import LineString, Point

import build as B

PLANS = B.HERE.parent / "site" / "plans"
KINDS = PLANS / "kinds.json"  # what each recommended change takes; not a plan
OUT = B.HERE.parent / "site" / "data" / "plans.json"
PLAN_ORDER = ["lrsp", "tod", "bmp", "ped"]  # safety plan first; then by how specific each plan is
SAME_PLACE_M = 120    # nodes for one named corner (divided roads, offset T's)
SEGMENT_WIDTH_M = 120  # how far street nodes may sit from the straight from->to line


def clusters(hits):
    """Group matches of one street pair into distinct places."""
    groups = []
    for h in hits:
        for g in groups:
            if math.dist((h["x"], h["y"]), g[0]) < SAME_PLACE_M:
                g[1].append(h)
                break
        else:
            groups.append([(h["x"], h["y"]), [h]])
    return [(sum(p["x"] for p in g) / len(g), sum(p["y"] for p in g) / len(g)) for _, g in groups]


NEAR_CITY = B.city_polygon().buffer(300)
CLOSEST_APPROACH_M = 50  # streets that meet through turn lanes share no node


def closest_approach(a, b, max_gap=CLOSEST_APPROACH_M):
    """Midpoint of the closest pair of nodes of two streets, if within max_gap meters."""
    na, nb = street_nodes(B.street_key(a)), street_nodes(B.street_key(b))
    best = min(((math.dist(p, q), p, q) for p in na for q in nb), default=None, key=lambda t: t[0])
    if best and best[0] <= max_gap:
        return [((best[1][0] + best[2][0]) / 2, (best[1][1] + best[2][1]) / 2)]
    return []


def locate_corner(idx, a, b, pick=None, where="", max_gap=CLOSEST_APPROACH_M, many=False):
    """a, b may list alternate OSM names separated by '|'."""
    pairs = [(x, y) for x in a.split("|") for y in b.split("|")]
    hits = [h for x, y in pairs for h in idx.get((B.street_key(x), B.street_key(y)), [])]
    # with "pick", choose among the raw junctions: offset T's (E/W Santa Inez) are close together
    places = ([(h["x"], h["y"]) for h in hits] if pick else clusters(hits)) \
        or [p for x, y in pairs for p in closest_approach(x, y, max_gap)][:1]
    if not places:
        sys.exit(f"{where}: no OSM intersection for {a} & {b}")
    if pick:
        axis = 0 if pick in ("east", "west") else 1
        return (max if pick in ("east", "north") else min)(places, key=lambda p: p[axis])
    if len(places) > 1:  # same names elsewhere (5th Ave & El Camino Real in Belmont): keep San Mateo's
        inside = [p for p in places if NEAR_CITY.contains(Point(*p))]
        places = inside or places
    if len(places) > 1 and not many:
        sys.exit(f"{where}: {a} & {b} matches {len(places)} places; add \"pick\"")
    return places if many else places[0]


_OSM = None


def street_nodes(key):
    global _OSM
    if _OSM is None:
        els = json.loads((B.GEO / "osm_streets.json").read_text())["elements"]
        _OSM = ({e["id"]: (e["lon"], e["lat"]) for e in els if e["type"] == "node"},
                [(B.street_key(e["tags"].get("name", "")), e["nodes"]) for e in els if e["type"] == "way"])
    nodes, ways = _OSM
    ids = {n for k, ns in ways if k == key for n in ns}
    return [B.project(*nodes[n]) for n in ids if n in nodes]


OPEN_END = re.compile(r"city limit|us-101|sr-92|i-280", re.I)
_CITY_EDGE = B.city_polygon().exterior
_FREEWAYS = B.freeway_lines()


def open_end(street, end, other, where, away_from=()):
    """Where a street reaches the city line (farthest such point from the other end) or a
    freeway (nearest such point to the other end). away_from: points of the plan's other
    segments on this street; the open end must lie beyond the known end, away from them."""
    nodes = street_nodes(B.street_key(street))
    if away_from:
        nodes = [p for p in nodes if all(math.dist(p, q) > math.dist(other, q) for q in away_from)]
    if re.search(r"city limit", end, re.I):
        near = [p for p in nodes if _CITY_EDGE.distance(Point(p)) < 150]
        pick = max
    else:
        near = [p for p in nodes if _FREEWAYS.distance(Point(p)) < 80]
        pick = min
    if not near:
        sys.exit(f"{where}: {street} doesn't reach {end} on the map")
    return pick(near, key=lambda p: math.dist(p, other))


def segment_line(idx, seg, where, siblings=()):
    # an end that matches several places (5th Ave & El Camino Real also exists in Belmont)
    # is resolved to the one nearest the segment's other end
    ends = [(seg["from"], None), (seg["to"], None)]
    known = [None, None]
    for k, (name, _) in enumerate(ends):
        if not OPEN_END.search(name):
            known[k] = locate_corner(idx, seg["street"], name, where=where, many=True)
    if known[0] is None and known[1] is None:
        sys.exit(f"{where}: neither end is a street")
    for k in (0, 1):  # an end at the city line or a freeway is placed on the street itself
        if known[k] is None:
            other = known[1 - k]
            away = [p for sib in siblings for p in sib]
            known[k] = [open_end(seg["street"], seg["from"] if k == 0 else seg["to"], o, where, away) for o in other]
    p1, p2 = min(((a, b) for a in known[0] for b in known[1]), key=lambda ab: math.dist(*ab))
    if math.dist(p1, p2) < 20:
        sys.exit(f"{where}: both ends resolve to the same place")
    if math.dist(p1, p2) > 3 * B.MILE:
        sys.exit(f"{where}: ends are {math.dist(p1, p2):.0f} m apart")
    dx, dy = p2[0] - p1[0], p2[1] - p1[1]
    L2 = dx * dx + dy * dy
    pts = []
    nodes = [n for name in seg["street"].split("|") for n in street_nodes(B.street_key(name))]
    for x, y in nodes:
        t = ((x - p1[0]) * dx + (y - p1[1]) * dy) / L2
        if -0.01 <= t <= 1.01:
            off = abs((x - p1[0]) * dy - (y - p1[1]) * dx) / math.sqrt(L2)
            if off < SEGMENT_WIDTH_M:
                pts.append((t, x, y))
    pts = [(0, *p1)] + sorted(pts) + [(1, *p2)]
    line = LineString([(x, y) for _, x, y in pts]).simplify(8)  # only used for distances; 8 m is plenty
    return [[round(c, 5) for c in B.unproject(x, y)] for x, y in line.coords]


def kinds_used(out):
    """{recommended change: quick | build | other} for every change the plans name; stops on one not in kinds.json."""
    table = {t: k for k, ts in json.loads(KINDS.read_text()).items() if not k.startswith("_") for t in ts}
    items = {x["facility"] for x in out["segments"] if x.get("facility")}
    for src in [*out["intersections"], *out["segments"], *(p for pr in out["projects"].values() for p in pr.values())]:
        for k in ("sooner", "later", "other"):
            items.update(src.get(k) or [])
    missing = sorted(items - table.keys())
    if missing:
        sys.exit("kinds.json doesn't say what these take:\n  " + "\n  ".join(missing))
    return {t: table[t] for t in sorted(items)}


def main():
    ints = B.intersections()
    idx = B.intersection_index(ints)
    site_ints = json.loads((B.HERE.parent / "site" / "data" / "intersections.json").read_text())
    site_pts = [(i[0], B.project(i[2] / 1e5, i[3] / 1e5), {B.street_key(n) for n in i[1].split(" & ")}) for i in site_ints]

    out = {"plans": [], "intersections": [], "segments": [], "projects": {}}
    order = {pid: k for k, pid in enumerate(PLAN_ORDER)}
    for path in sorted((p for p in PLANS.glob("*.json") if p != KINDS), key=lambda p: (order.get(p.stem, 99), p.stem)):
        plan = json.loads(path.read_text())
        pid = plan["id"]
        out["plans"].append({k: plan[k] for k in ("id", "label", "title", "short", "adopted", "url", "pdf", "method", "unranked", "list_label") if k in plan})
        # hand-entered plans must match exactly; generated ones (unranked lists) report misses and go on
        strict = plan.get("strict", not plan.get("unranked"))
        out["projects"][pid] = plan.get("projects", {})
        for loc in plan.get("intersections", []):
            where = f"{path.name} #{loc.get('rank') or loc.get('project') or '-'} {loc['name']}"
            try:
                x, y = locate_corner(idx, *loc["streets"], pick=loc.get("pick"), where=where,
                                     max_gap=loc.get("max_gap_m", CLOSEST_APPROACH_M))
            except SystemExit as e:
                if strict and not loc.get("optional"):
                    raise
                print(f"  SKIPPED {e}")
                continue
            # attach to a page only when that page names the same two streets
            want = {B.street_key(n) for s in loc["streets"] for n in s.split("|")}
            same = [(sid, math.dist((x, y), p)) for sid, p, keys in site_pts if len(keys & want) == 2]
            site_id, d = min(same, key=lambda t: t[1]) if same else (None, math.inf)
            lon, lat = B.unproject(x, y)
            out["intersections"].append({
                "plan": pid, **{k: v for k, v in loc.items() if k not in ("streets", "pick", "max_gap_m", "optional") and not k.startswith("_")},
                "id": site_id if d < SAME_PLACE_M else None, "lon": round(lon, 6), "lat": round(lat, 6)})
            print(f"  {where} -> {site_id if d < SAME_PLACE_M else '(no page)'} ({d:.0f} m)")
        # far points of closed segments on each street, so open ends ("to City Limit") point the other way
        closed = {}
        for seg in plan.get("segments", []):
            if not OPEN_END.search(seg["from"]) and not OPEN_END.search(seg["to"]):
                try:
                    ends = [locate_corner(idx, seg["street"], e, many=True) for e in (seg["from"], seg["to"])]
                except SystemExit:
                    continue
                closed.setdefault(B.street_key(seg["street"]), []).append([p for e in ends for p in e])
        for seg in plan.get("segments", []):
            where = f"{path.name} segment #{seg.get('rank') or seg.get('project') or '-'} {seg['name']}"
            try:
                line = segment_line(idx, seg, where, closed.get(B.street_key(seg["street"]), []))
            except SystemExit as e:
                if strict and not seg.get("optional"):
                    raise
                print(f"  SKIPPED {e}")
                continue
            out["segments"].append({"plan": pid, **{k: v for k, v in seg.items() if k not in ("street", "from", "to", "optional") and not k.startswith("_")}, "line": line})
            print(f"  {where} -> {len(line)} points")
    out["kinds"] = kinds_used(out)
    OUT.write_text(json.dumps(out, separators=(",", ":"), ensure_ascii=False))
    print(f"wrote {OUT} ({OUT.stat().st_size} bytes)")


if __name__ == "__main__":
    main()
