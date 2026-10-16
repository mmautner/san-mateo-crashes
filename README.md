# San Mateo crash lookup

A static page at **maxmautner.com/san-mateo-crashes/** that shows how many people were hurt in police-reported crashes near any San Mateo intersection. One page per intersection, each with its own preview image for group chats. No server: everything is filtered in the browser from two small JSON files.

How the numbers are counted is on the live methodology page (`/san-mateo-crashes/methodology/`) and in `pipeline/REPORT.md`.

## Layout

| Path | What |
|---|---|
| `pipeline/fetch.py` | Downloads CCRS crash files from data.ca.gov (streamed and filtered to the San Mateo area), the city boundary, council districts and OpenStreetMap streets into `pipeline/cache/` (not committed) |
| `pipeline/build.py` | Shared rules: study area, freeway exclusion, who was hurt, crash placement, intersections |
| `pipeline/export.py` | Writes `site/data/crashes.json` and `site/data/intersections.json` |
| `pipeline/report.py` | Data-quality report → `pipeline/REPORT.md` |
| `site/static/core.js` | Counting and wording. Runs in the browser and, under Node, at build time |
| `site/plans/*.json` | City plans' priority locations and proposals, entered by hand with page citations. `pipeline/plans.py` matches them to intersections and stops on anything ambiguous |
| `site/council.json` | **Council members by district. Edit this when the council changes.** |
| `site/config.json` | Base path, bucket, CloudFront ID, contact address |
| `build_site.py` | Renders every page into `dist/` |
| `site/og/make_og.py` | Preview images (1200×630) |
| `deploy.sh` | Build, upload to S3, invalidate CloudFront |

## Yearly refresh (each spring, once the prior year's reports have arrived)

```sh
python3 -m venv pipeline/.venv && pipeline/.venv/bin/pip install -r pipeline/requirements.txt   # first time
pipeline/.venv/bin/python pipeline/fetch.py --refresh        # all years, ~30 min
pipeline/.venv/bin/python pipeline/fetch.py --geo --refresh  # boundaries, districts, streets
pipeline/.venv/bin/python pipeline/export.py
pipeline/.venv/bin/python pipeline/plans_tod.py              # TOD Pedestrian Access Plan PDF -> site/plans/tod.json
pipeline/.venv/bin/python pipeline/plans_bmp.py              # Bicycle Master Plan Appendix E -> site/plans/bmp.json
pipeline/.venv/bin/python pipeline/plans.py                  # city plan locations -> site/data/plans.json
pipeline/.venv/bin/python pipeline/report.py > pipeline/REPORT.md
```

Read `REPORT.md` before deploying. Check:
- **Reporting gaps**: the agency table. If a police department has months with almost no reports, add them to `GAPS` in `pipeline/export.py`, and move `DEFAULT_FIRST_YEAR` if the gap falls in the default range.
- **Newest year**: compare it with the two before it. Reports keep arriving for months; a low newest year may still be filling in.
- **Council**: `site/council.json` (districts 1, 3 and 5 change after the November 2026 election).
- **City plans**: `lrsp.json` and `ped.json` are entered by hand; `tod.json` and `bmp.json` are generated from the city's PDFs. When the city updates a plan or completes a project, edit the hand-entered file (or the extractor's alias tables) and rerun `pipeline/plans.py`. A new recommendation must be added to `site/plans/kinds.json` (what it takes: signal timing/signs/paint, construction, or studies/enforcement), or `plans.py` stops.

The newest full year is picked up automatically (the current partial year is always left out).

## Keeping it current

`.github/workflows/freshness.yml` runs `pipeline/check_freshness.py` on the 1st of each month and keeps one open issue, "Site needs updating", when a new full year of crash data is out, a council term has ended (`term_ends` in `site/council.json`), or a linked plan or source no longer opens. It doesn't rebuild anything. Why things are the way they are is in `DECISIONS.md`.

## Deploy

Needs Node (for pre-rendering) and the AWS CLI with the same profile the blog uses.

```sh
./deploy.sh --dry-run   # build and list uploads, change nothing
./deploy.sh             # upload and invalidate /san-mateo-crashes/*
./deploy.sh --prune     # also delete pages that no longer exist (asks first)
```

The script only writes under `s3://maxmautner.com/san-mateo-crashes/`. It never deletes anything unless you pass `--prune` and confirm.

**The blog's deploy must leave this prefix alone.** In the blog repo's `s3_website.yml`, `ignore_on_server` should list `^san-mateo-crashes/`. s3_website_revived matches each entry as an unanchored Ruby regex against the S3 key, and keeps any key that matches. Don't touch `/crashes/`: it's a permanent redirect to a blog post.

## Local preview

```sh
pipeline/.venv/bin/python build_site.py --dev   # --dev also copies the blog's compiled CSS for local use
cd dist && python3 -m http.server 8765          # http://127.0.0.1:8765/san-mateo-crashes/
```

## Adapting to another city, or more than one (not built yet)

The crash data (CCRS) already covers every police department in California. The counting and wording in `core.js` aren't specific to San Mateo. What doesn't carry over by itself is the local work that makes the numbers defensible: finding reporting gaps, council contacts, and the city's plans. This section is the plan for making a second city cheap, written in October 2026 after auditing the code.

### What is specific to San Mateo today

A fork for another city would currently have to edit about a dozen places:

| Where | What's hard-coded |
|---|---|
| `pipeline/fetch.py` | Map box around the city (`BOX`), neighboring city names (`NEARBY_CITIES`), `City Name == "San Mateo"`, the County of San Mateo GIS boundary layer and feature, the city's council-district map URL |
| `pipeline/build.py` | Freeway rule (`FREEWAY_RE`) knows only US-101, SR-92 and I-280 |
| `pipeline/export.py` | `GAPS` (the San Mateo Police Aug 2021 – Jul 2022 gap), `FIRST_YEAR`, `DEFAULT_FIRST_YEAR` |
| `pipeline/report.py` | Assumes San Mateo Police (NCIC 4116), its four neighbors, and an OTS comparison figure |
| `pipeline/plans.py` | Freeway names in `OPEN_END`; plan order `PLAN_ORDER` |
| `site/static/core.js` | "San Mateo intersections" in the comparison line; `LAT0` (latitude used for distances) |
| `site/static/app.js` | "No San Mateo intersection matches", "You don't seem to be in San Mateo", the plans intro listing four specific plans |
| `build_site.py` | Titles, front page, and a methodology page that is mostly San Mateo prose (freeways, neighbors, each plan's description) |
| `site/og/make_og.py` | "SAN MATEO CRASH LOOKUP" drawn into the images |
| Styling | Pages use maxmautner.com's `/assets/css/site.css` and header; a fork gets unstyled pages |
| `site/council.json`, `site/plans/` | Assume district elections and these four plans |

### The plan

1. **One `city.json`** holding everything city-specific: name, URL path, contact address, the city's service-request and traffic-calming links, freeways to leave out, known reporting gaps (each with its reason), default first year, example corners. Derive the rest: the map box and neighboring cities come from the boundary plus the half-mile band, and `LAT0` from the boundary's center. All wording reads the city name from the config.
2. **Statewide default sources**, so no county-specific GIS hunting:
   - Boundary: Census TIGER "places", found by city name (incorporated cities).
   - Streets: OpenStreetMap through Overpass, queried from the boundary's box (as now).
   - Council districts: optional (a GeoJSON URL or file). Without one, the email card addresses the whole council, which fits the many cities that elect at-large.
3. **A gap finder.** `report.py` prints reports per police department and month for every agency inside the boundary and band, and flags months that drop toward zero. That's how the San Mateo gap shows up. A forker must review it and write any gaps into `city.json` before deploying. This is the step that protects credibility; `FORKING.md` should say so plainly.
4. **Optional parts stay optional.** No `site/plans/` files means no plans section and no plan sentence in the email. Plan JSON files keep their current format, and `kinds.json` still has to sort every recommendation.
5. **A plain built-in stylesheet** (light and dark), used unless `city.json` names an external one. This deploy keeps using the blog's stylesheet and header.
6. **Deploy anywhere static.** Keep `deploy.sh` for S3 and CloudFront, and document GitHub Pages as the no-AWS option: build, then publish `dist/`.
7. **`FORKING.md`:** clone, edit `city.json`, run fetch → export → report, review the gap report, optionally add plans (with page citations, conservative wording, and every item sorted in `kinds.json`), build, deploy. Link `DECISIONS.md` for why the defaults are what they are.
8. **Prove it with a second city.** Build one end to end without touching anything but its config. Foster City is a good candidate: it's next door and has a single police department. Anything that has to be fixed by hand goes into the code or the guide. Then rebuild San Mateo and confirm the output is unchanged.

### Scaling past one city

At county scale (San Mateo County: about 20 cities, perhaps 20,000 intersections) nothing needs redesigning if each city is its own folder:

- **Page data:** one `crashes.json` and `intersections.json` per city (today 235 KB and 114 KB). A page only ever loads its own city's files.
- **Preview images:** about a minute per 1,400 images, so a county takes roughly 15 minutes. `deploy.sh` already uploads only changed files.
- **Comparison line:** keep it within each city. A statewide percentile would mostly compare cities with farmland.

Statewide (roughly 400,000–600,000 intersection pages, ~15–20 GB built) would need real changes:

- Preview images rendered on demand or one per city, not per intersection.
- A manifest instead of listing every S3 object on deploy.
- Search indexes split by city or by first letter.

The bigger limits are human, not technical:

- Reporting gaps must be reviewed agency by agency.
- There's no statewide list of council districts or members' emails.
- City plans have no common format. Road safety plans are nearly universal, because state safety grants require them, but each is a different PDF.

A statewide version should start as counts, map and list only, and only once the gap finder exists.
