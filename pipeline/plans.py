"""Match city plans' named locations to this site's intersections.

    python pipeline/plans.py      # site/plans/*.json -> site/data/plans.json

Each site/plans/<id>.json is entered by hand from a city plan (see its _readme).
This script only locates what the plans name; it never changes their contents,
so rerunning it gives the same output. It stops with an error if a named
location can't be matched to exactly one place.
"""
import json
import math
import sys

from shapely.geometry import Point

import build as B

PLANS = B.HERE.parent / "site" / "plans"
OUT = B.HERE.parent / "site" / "data" / "plans.json"
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


def segment_line(idx, seg, where):
    # an end that matches several places (5th Ave & El Camino Real also exists in Belmont)
    # is resolved to the one nearest the segment's other end
    e1 = locate_corner(idx, seg["street"], seg["from"], where=where, many=True)
    e2 = locate_corner(idx, seg["street"], seg["to"], where=where, many=True)
    p1, p2 = min(((a, b) for a in e1 for b in e2), key=lambda ab: math.dist(*ab))
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
    return [[round(c, 6) for c in B.unproject(x, y)] for _, x, y in pts]


def main():
    ints = B.intersections()
    idx = B.intersection_index(ints)
    site_ints = json.loads((B.HERE.parent / "site" / "data" / "intersections.json").read_text())
    site_pts = [(i[0], B.project(i[2] / 1e5, i[3] / 1e5), {B.street_key(n) for n in i[1].split(" & ")}) for i in site_ints]

    out = {"plans": [], "intersections": [], "segments": [], "projects": {}}
    for path in sorted(PLANS.glob("*.json")):
        plan = json.loads(path.read_text())
        pid = plan["id"]
        out["plans"].append({k: plan[k] for k in ("id", "title", "short", "adopted", "url", "pdf", "method") if k in plan})
        out["projects"][pid] = plan.get("projects", {})
        for loc in plan.get("intersections", []):
            where = f"{path.name} #{loc['rank']} {loc['name']}"
            x, y = locate_corner(idx, *loc["streets"], pick=loc.get("pick"), where=where,
                                 max_gap=loc.get("max_gap_m", CLOSEST_APPROACH_M))
            # attach to a page only when that page names the same two streets
            want = {B.street_key(n) for s in loc["streets"] for n in s.split("|")}
            same = [(sid, math.dist((x, y), p)) for sid, p, keys in site_pts if len(keys & want) == 2]
            site_id, d = min(same, key=lambda t: t[1]) if same else (None, math.inf)
            lon, lat = B.unproject(x, y)
            out["intersections"].append({
                "plan": pid, **{k: loc[k] for k in ("rank", "tier", "name", "project", "status", "project_url") if k in loc},
                "id": site_id if d < SAME_PLACE_M else None, "lon": round(lon, 6), "lat": round(lat, 6)})
            print(f"  {where} -> {site_id if d < SAME_PLACE_M else '(no page)'} ({d:.0f} m)")
        for seg in plan.get("segments", []):
            where = f"{path.name} segment #{seg['rank']} {seg['name']}"
            line = segment_line(idx, seg, where)
            out["segments"].append({"plan": pid, **{k: seg[k] for k in ("rank", "name", "project") if k in seg}, "line": line})
            print(f"  {where} -> {len(line)} points")
    OUT.write_text(json.dumps(out, separators=(",", ":"), ensure_ascii=False))
    print(f"wrote {OUT} ({OUT.stat().st_size} bytes)")


if __name__ == "__main__":
    main()
