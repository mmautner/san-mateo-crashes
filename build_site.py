"""Build the static site into dist/.

    python build_site.py                  # every intersection page
    python build_site.py --only ID ID     # just these intersection pages (prototype)
    python build_site.py --dev            # also write a local stand-in for the site stylesheet

Output layout mirrors the bucket: dist/crashes/... is synced to s3://<bucket>/crashes/.
"""
import argparse
import datetime
import hashlib
import html
import json
import re
import shutil
import subprocess
import sys
import urllib.parse
from pathlib import Path

ROOT = Path(__file__).parent
SITE = ROOT / "site"
DIST = ROOT / "dist"
CFG = json.loads((SITE / "config.json").read_text())
BASE = CFG["base"]
OUT = DIST / BASE.strip("/")
e = html.escape


def version():
    h = hashlib.sha256()
    for p in sorted([*(SITE / "static").iterdir(), *(SITE / "data").iterdir(), SITE / "council.json"]):
        h.update(p.read_bytes())
    return h.hexdigest()[:10]


VER = version()


def long_date(iso):
    d = datetime.date.fromisoformat(iso)
    return f"{d:%B} {d.day}, {d.year}"


HEADER = """<header role="banner">
  <a href="/" class="site-title">Max Mautner</a>
  <nav role="navigation"><ul>
    <li><a href="/writing/">Essays</a></li>
    <li><a href="/about/">About</a></li>
    <li><a href="/subscribe/" class="nav-button">Subscribe</a></li>
    <li><button class="dark-mode-toggle" id="darkModeToggle" aria-label="Toggle dark mode">
      <svg class="icon-sun" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true"><circle cx="12" cy="12" r="5"/><path d="M12 1v2M12 21v2M4.22 4.22l1.42 1.42M18.36 18.36l1.42 1.42M1 12h2M21 12h2M4.22 19.78l1.42-1.42M18.36 5.64l1.42-1.42"/></svg>
      <svg class="icon-moon" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true"><path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z"/></svg>
    </button></li>
  </ul></nav>
</header>
<script>(function(){var t=document.getElementById('darkModeToggle'),r=document.documentElement;t.addEventListener('click',function(){var d=r.getAttribute('data-theme')!=='dark';r.setAttribute('data-theme',d?'dark':'light');try{localStorage.setItem('theme',d?'dark':'light')}catch(e){}});})();</script>"""


def head(title, description, path, og_image=None):
    url = f"{CFG['site_url']}{path}"
    og = ""
    if og_image:
        og = f"""
  <meta property="og:image" content="{e(CFG['site_url'] + og_image)}">
  <meta property="og:image:width" content="1200">
  <meta property="og:image:height" content="630">
  <meta property="og:image:alt" content="{e(description)}">
  <meta name="twitter:card" content="summary_large_image">"""
    return f"""<!DOCTYPE html>
<html lang="en" data-base="{BASE}" data-version="{VER}" data-city-service="{e(CFG['city_service_request'])}" data-city-calming="{e(CFG['city_traffic_calming'])}">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <script>(function(){{var s=null;try{{s=localStorage.getItem('theme')}}catch(e){{}}var r=document.documentElement;r.setAttribute('data-theme',s||(matchMedia('(prefers-color-scheme: light)').matches?'light':'dark'));}})();</script>
  <title>{e(title)}</title>
  <meta name="description" content="{e(description)}">
  <link rel="canonical" href="{e(url)}">
  <meta property="og:type" content="website">
  <meta property="og:site_name" content="Max Mautner">
  <meta property="og:title" content="{e(title)}">
  <meta property="og:description" content="{e(description)}">
  <meta property="og:url" content="{e(url)}">{og}
  <link rel="icon" href="/favicon.png">
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link href="https://fonts.googleapis.com/css2?family=Newsreader:opsz,wght@6..72,400;6..72,500;6..72,600;6..72,700&family=IBM+Plex+Sans:wght@400;500;600&display=swap" rel="stylesheet">
  <link rel="stylesheet" href="{BASE}static/crashes.css?v={VER}">
  <link rel="stylesheet" href="{CFG['site_css']}">
  <link rel="preconnect" href="https://tiles.openfreemap.org" crossorigin>
  <script type="module" src="{BASE}static/app.js?v={VER}"></script>
</head>
<body>
<main role="main">
{HEADER}"""


FOOT = "</main>\n</body>\n</html>\n"


def search_box(label):
    return f"""<div class="cx-search">
  <label for="cx-q">{e(label)}</label>
  <div class="cx-search-row">
    <input id="cx-q" type="search" role="combobox" aria-autocomplete="list" aria-expanded="false"
      aria-controls="cx-options" autocomplete="off" autocapitalize="off" spellcheck="false"
      placeholder="Street name, like “Aragon” or “3rd & B”">
    <button type="button" class="cx-btn cx-locate" hidden>Use my location</button>
  </div>
  <ul class="cx-options" id="cx-options" role="listbox" hidden></ul>
  <p class="cx-status" role="status"></p>
</div>"""


def small_print(issue_title=None, page_url=None):
    issue = f"{CFG['repo_url']}/issues/new?" + urllib.parse.urlencode({
        "title": issue_title or "Possible error",
        "body": f"Page: {page_url or CFG['site_url'] + BASE}\n\nWhat looks wrong:\n",
    })
    contact = CFG["contact_email"]
    contact_line = (f'To ask for a crash to be removed, email <a href="mailto:{e(contact)}">{e(contact)}</a>.'
                    if contact else '<strong>[contact address needed]</strong>')
    return f"""<div class="cx-note">
  <p>These are crashes reported to police only. A <a href="{CFG['berkeley_url']}">UC Berkeley review</a> found that police reports captured 44% to 75% of pedestrian injuries seen at hospitals and 7% to 46% of bicycle injuries, so the real numbers are higher.</p>
  <p>Data: California Highway Patrol, <a href="{CFG['ccrs_url']}">California Crash Reporting System</a>. Crashes on US-101, SR-92 and I-280 and their ramps are not counted. <a href="{BASE}methodology/">How this was counted</a>.</p>
  <p>Made by <a href="/about/">Max Mautner</a> from public police data. <a href="{CFG['repo_url']}">The code is public</a>, so anyone can check how the numbers are counted.</p>
  <p><a href="{e(issue)}">Report an error</a>. {contact_line}</p>
</div>"""


def intersection_page(id_, p, meta):
    path = f"{BASE}{id_}/"
    title = f"Crashes near {p['label']}, San Mateo"
    return head(title, p["headline"], path, og_image=f"{BASE}og/{id_}.png") + f"""
<article class="cx cx-intersection" data-id="{e(id_)}">
  <span class="cx-eyebrow"><a href="{BASE}">San Mateo crash lookup</a> · <a href="{BASE}#cx-q">Look up another intersection</a></span>
  <h1>{e(p['label'])}</h1>
  <p class="cx-headline" id="cx-headline" aria-live="polite">{e(p['headline'])}</p>
  <p class="cx-at" id="cx-at">{e(p['at'])}</p>
  <p class="cx-context" id="cx-context">{e(p['context'])}</p>
  <p class="cx-meta">{e(meta['dataThrough'])}. Police-reported crashes only.</p>

  <div class="cx-controls" role="group" aria-label="Settings">
    <label>Distance<select id="cx-radius"></select></label>
    <label>From<select id="cx-from"></select></label>
    <label>Through<select id="cx-to"></select></label>
  </div>

  <figure class="cx-years" id="cx-years"></figure>

  <div class="cx-map" id="cx-map" role="img" aria-label="Map of the crashes listed below"></div>
  <ul class="cx-legend" aria-label="Map key">
    <li><span class="cx-key" style="background:var(--walk)"></span>Walking</li>
    <li><span class="cx-key" style="background:var(--bike)"></span>On a bike</li>
    <li><span class="cx-key" style="background:var(--scooter)"></span>On a scooter</li>
    <li><span class="cx-key cx-key-ring"></span>In a vehicle</li>
    <li><span class="cx-key cx-key-killed"></span>Killed (month and year only)</li>
  </ul>
  <p class="cx-meta" style="margin-top:6px">Each dot is one crash, colored by who was hurt. When several people were, the dot shows the person walking, biking or on a scooter. Tap a dot for details.</p>

  <section class="cx-patterns" id="cx-patterns" aria-live="polite"></section>

  <section class="cx-plan" id="cx-plan" hidden></section>

  <section class="cx-act">
    <h2>What you can do</h2>
    <div class="cx-act-item">
      <h3>Tell a neighbor</h3>
      <p>The link shows this corner's numbers in a text or group chat.</p>
      <button type="button" class="cx-btn" id="cx-share">Copy link</button>
    </div>
    <div class="cx-act-item" id="cx-council" hidden></div>
    <div class="cx-act-item">
      <h3>Ask the city to look at this corner</h3>
      <p><a href="{e(CFG['city_service_request'])}">Report a concern</a> to the city, or <a href="{e(CFG['city_traffic_calming'])}">request a traffic calming study</a> for your street.</p>
    </div>
  </section>

  <h2>Crashes</h2>
  <div class="cx-filters" id="cx-filters" role="group" aria-label="Show crashes where someone was"></div>
  <p class="cx-meta" id="cx-list-count"></p>
  <p class="cx-meta">Tap a crash for what the police report says. Tap a dot on the map for the same.</p>
  <ul class="cx-list" id="cx-list"></ul>
  <button type="button" class="cx-btn cx-more" id="cx-more" hidden></button>
  <noscript><p class="cx-meta">Turn on JavaScript to see the map and the list of crashes.</p></noscript>

  {search_box("Look up another intersection")}
  {small_print(f"Possible error: {p['label']}", CFG['site_url'] + path)}
</article>
""" + FOOT


def index_page(meta, pre):
    desc = "Look up how many people were hurt in crashes near any San Mateo intersection, from police reports."
    y0, y1 = meta["default_years"]
    by_year = meta["counts"]["citywide_people_by_year"]
    total = sum(by_year[str(y)] for y in range(y0, y1 + 1))
    weeks = (y1 - y0 + 1) * 52.18
    examples = [(i, pre[i]) for i in CFG.get("examples", []) if i in pre]
    cards = "".join(
        f'<li><a href="{BASE}{e(i)}/"><span class="cx-ex-name">{e(p["label"])}</span>'
        f'<span class="cx-ex-n"><strong>{p["n"]}</strong> {"person" if p["n"] == 1 else "people"} hurt within a quarter mile</span></a></li>'
        for i, p in examples)
    return head("Crashes near you in San Mateo", desc, BASE, og_image=f"{BASE}og/index.png") + f"""
<article class="cx">
  <span class="cx-eyebrow">San Mateo crash lookup</span>
  <h1>How many people were hurt in crashes near you?</h1>
  <p class="cx-headline">Since {y0}, police reported <strong>{total:,} people</strong> hurt in crashes on San Mateo's streets, about {round(total / weeks)} a week. That doesn't count freeways.</p>
  <p class="cx-context">Type a street and pick the nearest intersection to see how many were hurt near it, who they were, and what the city plans there.</p>
  {search_box("Your street or the nearest intersection")}
  {f'<h2 class="cx-ex-head">Or start with one of these</h2><ul class="cx-examples">{cards}</ul>' if cards else ""}
  <p class="cx-meta">{e(meta['dataThrough'])}. What you type stays on your device; nothing is sent anywhere.</p>
  {small_print()}
</article>
""" + FOOT


def methodology_page(meta):
    c = meta["counts"]
    MIN_PATTERN = 5
    gap = meta["gaps"][0]
    y0, y1 = meta["years"]
    d0 = meta["default_years"][0]
    return head("How the San Mateo crash lookup counts", "Sources, definitions and choices behind the San Mateo crash lookup.", f"{BASE}methodology/", og_image=f"{BASE}og/index.png") + f"""
<article class="cx cx-method">
  <span class="cx-eyebrow"><a href="{BASE}">San Mateo crash lookup</a></span>
  <h1>How this was counted</h1>
  <p>Every number on this site comes from police crash reports. Here is where they come from and what was done to them. The code is public: <a href="{CFG['repo_url']}">{e(CFG['repo_url'].removeprefix('https://'))}</a>.</p>

  <h2>Sources</h2>
  <ul>
    <li><strong>Crashes:</strong> California Highway Patrol, <a href="{CFG['ccrs_url']}">California Crash Reporting System (CCRS)</a> on data.ca.gov, yearly Crashes, InjuredWitnessPassengers and Parties files, {y0}–{y1}. Downloaded {long_date(meta['downloaded'])}. Police departments file these reports; CHP publishes them.</li>
    <li><strong>City limits:</strong> County of San Mateo GIS, city boundaries layer.</li>
    <li><strong>Council districts:</strong> City of San Mateo, council voting districts map.</li>
    <li><strong>Streets and intersections:</strong> OpenStreetMap contributors. Map tiles: OpenFreeMap.</li>
  </ul>

  <h2>Which crashes are included</h2>
  <ul>
    <li>Crashes inside San Mateo city limits plus a half-mile band around them, so a circle near the city line also counts crashes just across it in Burlingame, Hillsborough, Belmont or Foster City.</li>
    <li>The counts, map and list cover crashes in which someone was hurt or killed. Each page also says how many crashes police took reports on nearby where no one was hurt ({c['no_injury_crashes']:,} in {y0}–{y1}, away from freeways). Those have no further detail on the site. Nationally, about 60% of crashes where no one is hurt are never reported to police (<a href="{CFG['nhtsa_url']}">NHTSA, 2023</a>), so the real number of these crashes is higher.</li>
    <li><strong>Freeways are left out:</strong> crashes on US-101, SR-92 and I-280 and their on- and off-ramps. That removes {c['freeway_crashes_removed']:,} crash reports and {c['freeway_people_removed']:,} people hurt ({c['freeway_killed_removed']} killed) from {y0}–{y1}. El Camino Real and other surface streets, including state routes, are kept.</li>
    <li>{y0}–{y1}: {c['crashes']:,} crashes in which {c['people']:,} people were hurt, {c['killed']} of them killed.</li>
  </ul>

  <p>The citywide number on the front page counts only crashes inside San Mateo city limits (not the half-mile band), away from freeways.</p>

  <h2>Who counts as hurt</h2>
  <p>A person counts when the officer recorded an injury. Witnesses and passengers who were not hurt are not counted.</p>
  <table>
    <tr><th>On this site</th><th>Officer's injury level in the report</th></tr>
    <tr><td>Killed</td><td>Fatal</td></tr>
    <tr><td>Seriously injured</td><td>Suspected serious injury</td></tr>
    <tr><td>Injured</td><td>Suspected minor injury, possible injury, complaint of pain</td></tr>
  </table>
  <table>
    <tr><th>On this site</th><th>In the report</th></tr>
    <tr><td>Walking</td><td>Pedestrians</td></tr>
    <tr><td>On a bike</td><td>Bicyclists, including electric and motorized bicycles</td></tr>
    <tr><td>On a scooter</td><td>Riders of stand-up electric scooters and boards</td></tr>
    <tr><td>In a vehicle</td><td>Drivers and passengers of cars, trucks, buses, motorcycles and mopeds</td></tr>
  </table>
  <p>For deaths, the site shows only the month, year, and whether the person was walking, on a bike or scooter, or in a vehicle.</p>

  <h2>Crash details</h2>
  <p>Tapping a crash shows what the officer wrote: the hour, the light, the type of crash, who the officer found most at fault and what they were doing, the cause the officer recorded (translated from the California Vehicle Code section into plain words), and whether it was a hit and run. Fault and cause are the officer's judgment at the scene, not a court finding, and some reports contradict themselves; the site shows them as written. Crashes where someone died show none of these details. The summary of causes on each page counts only the crashes that have details, and a one-line summary appears only when at least {MIN_PATTERN} crashes are in range and the top cause appears at least 3 times.</p>

  <h2>Where each crash is placed</h2>
  <p>Most reports include coordinates. {c['placed_from_street_names']} crashes had none and were placed from the report's street description (the two streets, plus the distance and direction the officer recorded). {c['moved_to_street_description']} crashes had coordinates more than 200 meters from the streets the officer named; those were moved to the named location. Both kinds are marked “approximate” in the list.</p>

  <h2>Years</h2>
  <p>The site starts at {d0} by default. {e(gap['agency'])} reports from {datetime.date.fromisoformat(gap['from'] + '-01'):%B %Y} through {datetime.date.fromisoformat(gap['to'] + '-01'):%B %Y} are missing from the state's data, so counts for 2021 and 2022 are too low. Years back to {y0} can be added with the year controls. 2016 is left out because nearly all San Mateo Police reports for that year are missing. The current year is left out until it is complete.</p>

  <h2>City plans</h2>
  <p>Each page says whether the city's <a href="https://www.cityofsanmateo.org/4695/Local-Roadway-Safety-Plan">Local Roadway Safety Plan</a> (adopted May 20, 2024) lists the intersection, or a street segment through it, among its priority locations, and which listed locations fall within the chosen distance. Ranks and names come from the plan's Table 6 (page 48) and Table 7 (page 50). The proposed changes are plain-language summaries of its Table 9 (pages 75–76). The plan ranked locations using crashes from 2017 through 2021, weighted by severity, so its order differs from the counts here. A project's status is shown only when the city reports it complete; otherwise the page links to the city's project page. The source file for these entries is <code>site/plans/lrsp.json</code> in the code repository.</p>
  <p>Pages near the Downtown, Hayward Park and Hillsdale Caltrain stations and along El Camino Real also cite the city's <a href="https://www.cityofsanmateo.org/4566/TOD-Pedestrian-Access-Plan">Transit-Oriented Development Pedestrian Access Plan</a> (adopted November 21, 2022). Its project list doesn't rank locations. The site reads that list directly from the city's PDF and sorts each location's recommended changes into plain categories by keyword (for example, “LPI” becomes “a head start on the walk signal”), keeping the plan's short-term and medium-term split; each page links to the page of the plan's list with the full wording. Locations that aren't on a street, such as paths across the tracks or station parking lots, aren't placed on pages. The extraction is <code>pipeline/plans_tod.py</code>.</p>
  <p>Pages on or near a proposed bikeway also cite the city's <a href="https://www.cityofsanmateo.org/3944/Bicycle-Master-Plan-2020">Bicycle Master Plan</a> (adopted April 6, 2020), from its Appendix E project list: the street, its limits, the proposed kind of bikeway, and the plan's priority group (High, Medium-High, Medium-Low or Low, from a score for safety, comfort, equity and expected use). The site reads that table directly from the city's PDF. Where a bikeway ends at the city line or a freeway, the end is placed where the street meets it on the map. Projects on paths, overcrossings or parks that aren't streets on the map aren't placed on pages. Some of these bikeways may have been built since 2020. The extraction is <code>pipeline/plans_bmp.py</code>.</p>
  <p>Pages also cite the city's 2012 <a href="https://www.cityofsanmateo.org/2218/Pedestrian-Master-Plan">Pedestrian Master Plan</a> where its Appendix G names the location: corners recommended for wider sidewalk corners (Table G-4), stop lines set back from the crosswalk (Table G-6) or a pedestrian hybrid beacon (Table G-7), streets recommended for new sidewalks (Table G-1), and mid-block crosswalk upgrades (Table G-8). These were entered by hand from the plan, with page citations, in <code>site/plans/ped.json</code>. The plan's list of high-visibility crosswalk locations (its Appendix F) isn't included. Since the plan is from 2012, some of these changes may have been made.</p>

  <h2>Distances</h2>
  <p>Distances are straight-line distances from the point where the two streets meet. Walking times assume about 3 miles an hour: a quarter mile is about a 5-minute walk.</p>

  <h2>At the intersection</h2>
  <p>Each page also says how many of the people hurt nearby were hurt at the intersection itself: in crashes placed within 40 meters (about 130 feet) of where the two streets meet. The rest were on the streets around it.</p>

  <h2>Comparing intersections</h2>
  <p>An intersection is any place in city limits where two differently named streets meet ({c['intersections']:,} in all). The comparison line counts people hurt within the same distance and years around every one of them. If a location is below the middle, the site shows the typical (median) count instead of a percentage.</p>

  <h2>What this misses</h2>
  <p>Only crashes reported to police are here. A <a href="{CFG['berkeley_url']}">UC Berkeley review</a> found that police reports captured 44% to 75% of pedestrian injuries seen at hospitals and 7% to 46% of bicycle injuries, so the real numbers are higher. Nationally, NHTSA estimates that about 32% of crashes in which someone is hurt, and about 60% of crashes in which no one is hurt, are never reported to police (<a href="{CFG['nhtsa_url']}">The Economic and Societal Impact of Motor Vehicle Crashes, 2019, page 3</a>). That is why the site says “at least.”</p>
  {small_print("Possible error: methodology", CFG['site_url'] + BASE + 'methodology/')}
</article>
""" + FOOT


def write(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", nargs="*")
    ap.add_argument("--dev", action="store_true")
    a = ap.parse_args()

    pre = json.loads(subprocess.run(["node", str(SITE / "prerender.mjs"), str(SITE / "data"), *(a.only or [])],
                                    check=True, capture_output=True, text=True).stdout)
    meta = pre.pop("_meta")
    if OUT.exists():
        shutil.rmtree(OUT)
    shutil.copytree(SITE / "static", OUT / "static")
    shutil.copytree(SITE / "data", OUT / "data")
    shutil.copy(SITE / "council.json", OUT / "council.json")
    write(OUT / "index.html", index_page(meta, pre))
    write(OUT / "methodology" / "index.html", methodology_page(meta))
    for id_, p in pre.items():
        write(OUT / id_ / "index.html", intersection_page(id_, p, meta))
    (OUT / "prerender.json").write_text(json.dumps(pre))  # for OG images; not deployed
    if a.dev:
        blog = ROOT.parent / "maxmautner" / "_site" / "index.html"
        css = re.search(r"<style>(.*?)</style>", blog.read_text(), re.S).group(1)
        write(DIST / CFG["site_css"].lstrip("/"), css)
    print(f"built {len(pre)} intersection pages into {OUT} (version {VER})", file=sys.stderr)


if __name__ == "__main__":
    main()
