"""Say what on the site needs a person's attention. Run monthly by .github/workflows/freshness.yml.

    python pipeline/check_freshness.py      # prints one line per item; exit 1 if any

Standard library only. Checks:
  - a full year of crash data that the site doesn't have yet (from April on, once the
    year's reports have mostly arrived)
  - council members whose terms have ended (council.json "term_ends")
  - links to city plans and data sources that no longer open
"""
import datetime
import json
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).parent.parent
CKAN = "https://data.ca.gov/api/3/action/package_show?id=ccrs"
UA = {"User-Agent": "san-mateo-crashes freshness check (https://github.com/mmautner/san-mateo-crashes)"}


def get(url, method="GET"):
    return urllib.request.urlopen(urllib.request.Request(url, headers=UA, method=method), timeout=60)


def main():
    today = datetime.date.today()
    out = []

    meta = json.loads((ROOT / "site" / "data" / "crashes.json").read_text())["meta"]
    have = meta["years"][1]
    try:
        names = {r["name"] for r in json.load(get(CKAN))["result"]["resources"]}
        for y in range(have + 1, today.year):
            ready = today >= datetime.date(y + 1, 4, 1)
            if ready and all(f"{k}_{y}" in names for k in ("Crashes", "InjuredWitnessPassengers", "Parties")):
                out.append(f"Add {y} crash data: the site ends at {have}. See README \"Yearly refresh\".")
    except Exception as e:  # noqa: BLE001 - report, don't crash the check
        out.append(f"Couldn't read the CCRS listing on data.ca.gov: {e}")

    council = json.loads((ROOT / "site" / "council.json").read_text())
    for d, m in sorted(council["members"].items()):
        if m.get("term_ends") and m["term_ends"] < today.strftime("%Y-%m"):
            out.append(f"Council District {d}: {m['name']}'s term ended {m['term_ends']}; update site/council.json.")

    links = set()
    for f in sorted((ROOT / "site" / "plans").glob("*.json")):
        p = json.loads(f.read_text())
        links.update(u for u in (p.get("url"), p.get("pdf")) if u)
        for loc in p.get("intersections", []):
            if isinstance(loc.get("status"), dict):
                links.add(loc["status"]["source"])
            if loc.get("project_url"):
                links.add(loc["project_url"])
    cfg = json.loads((ROOT / "site" / "config.json").read_text())
    links.update(v for k, v in cfg.items() if isinstance(v, str) and v.startswith("http") and k != "site_url")
    for u in sorted(links):
        try:
            get(u).close()
        except Exception as e:  # noqa: BLE001
            out.append(f"Link doesn't open: {u} ({e})")

    for line in out:
        print(line)
    return 1 if out else 0


if __name__ == "__main__":
    sys.exit(main())
