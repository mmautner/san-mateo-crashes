"""Download CCRS yearly files from data.ca.gov and keep only rows near San Mateo.

The statewide files are large (~470 MB per year), so each is streamed and
filtered on the fly. Filtered copies are cached in pipeline/cache/<year>/ along
with the date they were downloaded. Rerun with --refresh to fetch again.

    python pipeline/fetch.py [--refresh] [YEAR ...]   crash data (all years by default)
    python pipeline/fetch.py --geo [--refresh]        boundaries, council districts, OSM streets

Kept crash rows:
  - coordinates inside a generous box around San Mateo city + 0.5 mile, or
  - no usable coordinates and a City Name in or next to San Mateo (these are
    located later from their street names), or
  - City Name = San Mateo (for comparison with official city totals).
Injured/witness/passenger rows and party rows are kept for those crashes only.
"""
import csv
import datetime
import io
import json
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

CKAN = "https://data.ca.gov/api/3/action/package_show?id=ccrs"
CACHE = Path(__file__).parent / "cache"
UA = {"User-Agent": "san-mateo-crashes pipeline (https://maxmautner.com/crashes/)"}

# lon/lat box comfortably containing San Mateo city limits plus half a mile
BOX = (-122.375, 37.495, -122.255, 37.620)
NEARBY_CITIES = {"San Mateo", "Burlingame", "Hillsborough", "Belmont", "Foster City", "Unincorporated"}
SAN_MATEO_COUNTY = "41"

csv.field_size_limit(sys.maxsize)


def resources():
    req = urllib.request.Request(CKAN, headers=UA)
    pkg = json.load(urllib.request.urlopen(req))["result"]
    out = {}
    for r in pkg["resources"]:
        kind, _, year = r["name"].rpartition("_")
        if year.isdigit() and kind in ("Crashes", "InjuredWitnessPassengers", "Parties"):
            out[(kind, int(year))] = r["url"]
    return out


def stream_rows(url):
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req) as resp:
        text = io.TextIOWrapper(resp, encoding="utf-8-sig", newline="")
        reader = csv.reader(text)
        header = [h.strip() for h in next(reader)]
        yield header
        yield from reader


def coords(row):
    try:
        lat, lon = float(row["Latitude"]), float(row["Longitude"])
    except (TypeError, ValueError):
        return None
    if not lat or not lon:
        return None
    if lon > 0:  # a few reports drop the minus sign
        lon = -lon
    return lon, lat


def keep_crash(row):
    if row["City Name"].strip() == "San Mateo":
        return True
    c = coords(row)
    if c is None:
        return row["County Code"].strip() == SAN_MATEO_COUNTY and row["City Name"].strip() in NEARBY_CITIES
    return BOX[0] <= c[0] <= BOX[2] and BOX[1] <= c[1] <= BOX[3]


def filter_to(url, dest, keep):
    rows = stream_rows(url)
    header = next(rows)
    n_in = n_out = 0
    tmp = dest.with_suffix(".part")
    with open(tmp, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(header)
        for values in rows:
            n_in += 1
            row = dict(zip(header, values))
            if keep(row):
                w.writerow(values)
                n_out += 1
    tmp.rename(dest)
    return n_in, n_out


def fetch_year(year, urls, refresh=False):
    d = CACHE / str(year)
    meta_path = d / "meta.json"
    if meta_path.exists() and not refresh:
        return json.loads(meta_path.read_text())
    d.mkdir(parents=True, exist_ok=True)
    meta = {"year": year, "downloaded": datetime.date.today().isoformat(), "files": {}}

    n_in, n_out = filter_to(urls[("Crashes", year)], d / "crashes.csv", keep_crash)
    meta["files"]["crashes"] = {"url": urls[("Crashes", year)], "statewide_rows": n_in, "kept_rows": n_out}
    with open(d / "crashes.csv", newline="") as f:
        ids = {r["Collision Id"] for r in csv.DictReader(f)}

    for kind, name, id_col in (("InjuredWitnessPassengers", "people.csv", "CollisionId"),
                               ("Parties", "parties.csv", "CollisionId")):
        n_in, n_out = filter_to(urls[(kind, year)], d / name, lambda r: r[id_col].strip() in ids)
        meta["files"][name.removesuffix(".csv")] = {"url": urls[(kind, year)], "statewide_rows": n_in, "kept_rows": n_out}

    meta_path.write_text(json.dumps(meta, indent=2))
    return meta


GEO_SOURCES = {
    # County of San Mateo GIS, city boundaries layer; feature 24 = SAN MATEO
    "san_mateo_city.geojson": "https://gis.smcgov.org/maps/rest/services/FeatureServices/Admin_Features/MapServer/0/query"
                              "?where=OBJECTID%3D24&outFields=NAME&returnGeometry=true&outSR=4326&f=geojson",
    # City of San Mateo council voting districts
    "council_districts.geojson": "https://services2.arcgis.com/g26Y0m7OCdjU0ObA/arcgis/rest/services/"
                                 "City_of_San_Mateo_Council_Voting_Districts/FeatureServer/0/query"
                                 "?where=1%3D1&outFields=*&returnGeometry=true&outSR=4326&f=geojson",
}
OVERPASS = ["https://overpass-api.de/api/interpreter", "https://overpass.kumi.systems/api/interpreter"]


def overpass(query, tries=4):
    """Overpass servers are often busy (406/429/502/504): retry, alternating mirrors."""
    body = urllib.parse.urlencode({"data": query}).encode()
    for k in range(tries):
        url = OVERPASS[k % len(OVERPASS)]
        try:
            return urllib.request.urlopen(urllib.request.Request(url, data=body, headers=UA), timeout=300).read()
        except urllib.error.HTTPError as e:
            print(f"  {url}: HTTP {e.code}, retrying", flush=True)
            time.sleep(10 * (k + 1))
    raise RuntimeError("Overpass unavailable; try again later")
OSM_QUERIES = {
    "osm_motorways.json": '[out:json][timeout:120];way["highway"~"^(motorway|motorway_link|trunk|trunk_link)$"]'
                          f"({BOX[1]},{BOX[0]},{BOX[3]},{BOX[2]});out tags geom;",
    "osm_streets.json": '[out:json][timeout:180];(way["highway"~"^(trunk|primary|secondary|tertiary|unclassified|'
                        'residential|living_street|trunk_link|primary_link|secondary_link|tertiary_link)$"]["name"]'
                        f"({BOX[1]},{BOX[0]},{BOX[3]},{BOX[2]}););out body;>;out skel qt;",
}


def fetch_geo(refresh=False):
    """City boundary, council districts and OpenStreetMap streets."""
    geo = CACHE / "geo"
    geo.mkdir(parents=True, exist_ok=True)
    for name, url in GEO_SOURCES.items():
        if refresh or not (geo / name).exists():
            data = urllib.request.urlopen(urllib.request.Request(url, headers=UA)).read()
            assert json.loads(data)["features"], f"{name}: no features"
            (geo / name).write_bytes(data)
            print("fetched", name, flush=True)
    for name, q in OSM_QUERIES.items():
        if refresh or not (geo / name).exists():
            data = overpass(q)
            assert json.loads(data)["elements"], f"{name}: no elements"
            (geo / name).write_bytes(data)
            print("fetched", name, flush=True)
    (geo / "downloaded.txt").write_text(datetime.date.today().isoformat() + "\n") if refresh else None


def main(argv):
    refresh = "--refresh" in argv
    if "--geo" in argv:
        fetch_geo(refresh)
        return
    years = [int(a) for a in argv if a.isdigit()]
    urls = resources()
    if not years:
        years = sorted({y for (_, y) in urls})
    for y in years:
        m = fetch_year(y, urls, refresh)
        print(y, m["downloaded"], {k: v["kept_rows"] for k, v in m["files"].items()}, flush=True)


if __name__ == "__main__":
    main(sys.argv[1:])
