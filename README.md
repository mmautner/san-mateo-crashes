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
pipeline/.venv/bin/python pipeline/plans.py                  # city plan locations -> site/data/plans.json
pipeline/.venv/bin/python pipeline/report.py > pipeline/REPORT.md
```

Read `REPORT.md` before deploying. Check:
- **Reporting gaps**: the agency table. If a police department has months with almost no reports, add them to `GAPS` in `pipeline/export.py`, and move `DEFAULT_FIRST_YEAR` if the gap falls in the default range.
- **Newest year**: compare it with the two before it. Reports keep arriving for months; a low newest year may still be filling in.
- **Council**: `site/council.json` (districts 1, 3 and 5 change after the November 2026 election).
- **City plans**: when the city updates a plan or completes a project, edit `site/plans/<plan>.json` and rerun `pipeline/plans.py`.

The newest full year is picked up automatically (the current partial year is always left out).

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
