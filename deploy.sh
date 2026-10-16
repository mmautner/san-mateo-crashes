#!/usr/bin/env bash
# Build and publish the crash lookup to maxmautner.com/<base>/ (base from site/config.json).
#
#   ./deploy.sh              build, upload, invalidate CloudFront
#   ./deploy.sh --dry-run    build and show what would upload; change nothing
#   ./deploy.sh --prune      ALSO delete objects under <base>/ that the build no longer
#                            produces (shows the list and asks first)
#   ./deploy.sh --force      upload every file, even unchanged ones (use after changing
#                            cache or content-type settings below; those don't change bytes)
#
# Only files whose bytes differ from what's live are uploaded: each staged file's MD5 is
# compared with the S3 ETag (an MD5 for single-part uploads, which all of these are).
#
# Only keys under s3://<bucket>/<base>/ are ever written or deleted. The blog's
# own deploy (s3_website) must ignore this prefix; see README.
#
# Data refresh is separate and yearly:  pipeline/fetch.py --refresh, then pipeline/export.py.
#
# Credentials come from the AWS profile in $AWS_PROFILE (default "default"), like bin/deploy
# in the blog. The bucket has no versioning, so a normal deploy never deletes anything.
set -euo pipefail
cd "$(dirname "$0")"

DRY=0; PRUNE=0; FORCE=0
for a in "$@"; do
  case "$a" in
    --dry-run) DRY=1 ;;
    --prune) PRUNE=1 ;;
    --force) FORCE=1 ;;
    *) echo "unknown flag: $a" >&2; exit 2 ;;
  esac
done

PY=pipeline/.venv/bin/python
cfg() { "$PY" -c "import json,sys; print(json.load(open('site/config.json'))[sys.argv[1]])" "$1"; }
BUCKET="$(cfg s3_bucket)"
CF_ID="$(cfg cloudfront_distribution_id)"
PREFIX="$(cfg base | sed 's#^/*##; s#/*$##')"
export AWS_PROFILE="${AWS_PROFILE:-default}"

# Never let a config mistake point this at the bucket root or outside the prefix.
if [[ -z "$BUCKET" || -z "$PREFIX" || "$PREFIX" == *..* || "$PREFIX" == */* ]]; then
  echo "refusing: bucket='$BUCKET' prefix='$PREFIX'" >&2; exit 1
fi
DEST="s3://$BUCKET/$PREFIX/"

echo "==> Building site"
"$PY" build_site.py
echo "==> Rendering preview images"
"$PY" site/og/make_og.py

echo "==> Staging (gzip text files, as the blog does; CloudFront does not compress)"
STAGE=.deploy
rm -rf "$STAGE"
cp -R "dist/$PREFIX" "$STAGE"
rm -f "$STAGE/prerender.json"
find "$STAGE" -type f \( -name '*.html' -o -name '*.css' -o -name '*.js' -o -name '*.json' \) -print0 |
  while IFS= read -r -d '' f; do gzip -9 -n -c "$f" > "$f.gz" && mv "$f.gz" "$f"; done

echo "==> Comparing with what's live"
UPLOAD=.deploy-changed
rm -rf "$UPLOAD"
if [[ $FORCE == 1 ]]; then
  cp -R "$STAGE" "$UPLOAD"
  echo "   --force: uploading all $(find "$UPLOAD" -type f | wc -l | tr -d ' ') files"
else
  aws s3api list-objects-v2 --bucket "$BUCKET" --prefix "$PREFIX/" --output json > .deploy-remote.json
  "$PY" - "$STAGE" "$UPLOAD" "$PREFIX" .deploy-remote.json <<'PY'
import hashlib, json, shutil, sys
from pathlib import Path
stage, upload, prefix, remote = Path(sys.argv[1]), Path(sys.argv[2]), sys.argv[3], sys.argv[4]
live = {o["Key"]: o["ETag"].strip('"') for o in (json.loads(Path(remote).read_text() or "{}").get("Contents") or [])}
changed = new = 0
for f in sorted(p for p in stage.rglob("*") if p.is_file()):
    key = f"{prefix}/{f.relative_to(stage).as_posix()}"
    if live.get(key) == hashlib.md5(f.read_bytes()).hexdigest():
        continue
    new += key not in live
    changed += 1
    dest = upload / f.relative_to(stage)
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(f, dest)
total = sum(1 for p in stage.rglob("*") if p.is_file())
print(f"   {changed} of {total} files changed ({new} new); {total - changed} already live")
PY
  rm -f .deploy-remote.json
fi
mkdir -p "$UPLOAD"
N_UPLOAD=$(find "$UPLOAD" -type f | wc -l | tr -d ' ')

if [[ $DRY == 1 ]]; then SYNC=(aws s3 sync "$UPLOAD/" "$DEST" --dryrun)
else SYNC=(aws s3 sync "$UPLOAD/" "$DEST" --only-show-errors); fi

up() { # pattern content-type cache-seconds [gzip]
  local enc=(); [[ "${4:-}" == gzip ]] && enc=(--content-encoding gzip)
  "${SYNC[@]}" --exclude '*' --include "$1" --content-type "$2" --cache-control "max-age=$3" ${enc[@]+"${enc[@]}"}
}
echo "==> Uploading $N_UPLOAD files to $DEST"
up '*.png'  'image/png'                       86400
up '*.json' 'application/json; charset=utf-8'  3600 gzip
up '*.css'  'text/css; charset=utf-8'          3600 gzip
up '*.js'   'text/javascript; charset=utf-8'   3600 gzip
up '*.html' 'text/html; charset=utf-8'          300 gzip

if [[ $PRUNE == 1 ]]; then
  echo "==> Objects under $DEST that the build no longer produces:"
  GONE="$(aws s3 sync "$STAGE/" "$DEST" --delete --dryrun | sed -n 's#^(dryrun) delete: \(s3://.*\)$#\1#p')"
  if [[ -z "$GONE" ]]; then echo "   none"
  else
    echo "$GONE" | sed 's/^/   /'
    if [[ $DRY == 0 ]]; then
      read -r -p "Delete these $(echo "$GONE" | wc -l | tr -d ' ') objects? No versioning: this cannot be undone. Type 'delete': " ok
      if [[ "$ok" == delete ]]; then
        while IFS= read -r key; do
          [[ "$key" == "$DEST"* ]] || { echo "skipping $key (outside $DEST)" >&2; continue; }
          aws s3 rm "$key" --only-show-errors
        done <<< "$GONE"
        echo "   deleted"
      else echo "   kept everything"; fi
    fi
  fi
fi

if [[ $DRY == 0 && $N_UPLOAD == 0 ]]; then
  echo "==> Nothing changed; no invalidation needed."
elif [[ $DRY == 0 ]]; then
  echo "==> Invalidating CloudFront $CF_ID /$PREFIX/*"
  aws cloudfront create-invalidation --distribution-id "$CF_ID" --paths "/$PREFIX/*" \
    --query 'Invalidation.{id:Id,status:Status}' --output text
  echo "==> Live at https://maxmautner.com/$PREFIX/"
else
  echo "==> Dry run: nothing uploaded, nothing invalidated."
fi
