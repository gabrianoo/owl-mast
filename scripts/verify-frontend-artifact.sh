#!/usr/bin/env bash
# OM-01.04 AC4: build the independent frontend image and prove its runtime contract without any
# backend: serves the shell on 8080 as a non-root user, falls back to index.html for app routes,
# publishes the API path prefix it was deployed with and the API contract it supports, answers 404
# below the API prefix (it never proxies or impersonates the backend), refuses an unsafe prefix at
# start-up, and contains no JDK or backend jar.
#
# OWLMAST_IMAGE_BROWSER_SMOKE=1 also runs Chromium against the container (frontend/e2e/image): the
# production CSP, the nginx template and /owlmast-config.json in a real browser. It needs
# `npm ci` and `npx playwright install chromium` in frontend/ first; CI sets it.
#
# The prefix below is deliberately not /api: it proves the image hands over whatever it is given.
# The chart itself only ever passes /api (it refuses any other routing.apiPathPrefix because the
# backend serves /api and no rewrite is rendered).
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
IMAGE="${OWLMAST_FRONTEND_IMAGE:-owl-mast/frontend:0.1.0-verify}"
NAME="owlmast-frontend-verify-$$"
PREFIX="/owl/api"

TMP="$(mktemp -d)"

cleanup() { docker rm -f "$NAME" >/dev/null 2>&1 || true; rm -rf "$TMP"; }
trap cleanup EXIT

echo "== build $IMAGE"
docker build --quiet -t "$IMAGE" "$ROOT/frontend" >/dev/null

echo "== run as the image's own user with OWLMAST_API_PATH_PREFIX=$PREFIX"
docker run -d --name "$NAME" -e "OWLMAST_API_PATH_PREFIX=$PREFIX" -p 127.0.0.1::8080 "$IMAGE" >/dev/null
PORT="$(docker port "$NAME" 8080/tcp | head -n1 | sed 's/.*://')"
BASE="http://127.0.0.1:$PORT"
# Readiness wait: Docker's port proxy accepts and resets connections until nginx listens, so the
# attempts stay silent; the checks below report any real failure.
for _ in $(seq 1 50); do
  if curl -fs -o /dev/null "$BASE/"; then break; fi
  sleep 0.2
done

failures=0
check() {
  local name="$1"
  shift
  if "$@"; then echo "ok   [$name]"; else echo "FAIL [$name]"; failures=$((failures + 1)); fi
}

uid="$(docker exec "$NAME" id -u)"
check "non-root runtime user (uid $uid)" test "$uid" != "0"
check "readiness GET / is 200 and serves the shell" bash -c "curl -fsS '$BASE/' | grep -q '<div id=\"root\">'"
check "SPA fallback GET /focus is 200 with the shell" bash -c "curl -fsS '$BASE/focus' | grep -q 'theme-boot.js'"
check "unknown static asset is 404, not index.html" bash -c "[ \"\$(curl -s -o /dev/null -w '%{http_code}' '$BASE/assets/missing.js')\" = 404 ]"
check "config endpoint echoes the deployed API prefix" bash -c "[ \"\$(curl -fsS '$BASE/owlmast-config.json')\" = '{\"apiPathPrefix\":\"$PREFIX\"}' ]"
check "config endpoint is JSON and not cached" bash -c "curl -fsSI '$BASE/owlmast-config.json' | grep -qi 'content-type: application/json' && curl -fsSI '$BASE/owlmast-config.json' | grep -qi 'cache-control: no-store'"
check "security headers present" bash -c "curl -fsSI '$BASE/' | grep -qi 'content-security-policy' && curl -fsSI '$BASE/' | grep -qi 'x-content-type-options: nosniff'"
# A location-level add_header replaces the server-level ones, so each location includes the shared
# headers itself; a location that loses the include loses CSP, nosniff and X-Frame-Options, and a
# misroute 404 that loses no-store can be kept by a cache as the "no descriptor" answer.
has_headers() {
  local headers
  headers="$(curl -sS -o /dev/null -D - "$1" | tr -d '\r')" || return 1
  local wanted
  for wanted in "content-security-policy: default-src 'self'; script-src 'self'; " 'x-content-type-options: nosniff' 'x-frame-options: DENY' 'referrer-policy: same-origin' "${@:2}"; do
    grep -qiF -- "$wanted" <<<"$headers" || { echo "      $1 lacks '$wanted'"; return 1; }
  done
  [ "$(grep -ci '^content-security-policy:' <<<"$headers")" = 1 ] || { echo "      $1 answers with more than one Content-Security-Policy"; return 1; }
}
IMMUTABLE='cache-control: public, max-age=31536000, immutable'
HASHED_ASSET="$(curl -fsS "$BASE/" | grep -o '/assets/[^"]*\.js' | head -n1)"
check "the shell references a hashed asset" test -n "$HASHED_ASSET"
for path in / /focus /owlmast-config.json /api-compatibility.json "$PREFIX" "$PREFIX/compatibility" "$PREFIX/deeper/path" "$HASHED_ASSET" /assets/missing.js; do
  case "$path" in
    "$HASHED_ASSET") check "security headers and the immutable policy on $path" has_headers "$BASE$path" "$IMMUTABLE" ;;
    *) check "security headers and no-store on $path" has_headers "$BASE$path" 'cache-control: no-store' ;;
  esac
done
# Only an answer that carries the hashed file is immutable. A missing asset (an old pod asked for
# the new build's name during a rolling update) must not be kept for a year; the 304 that
# revalidates the file replaces the stored headers, so it repeats the policy of the 200.
# Prints "<status> <Cache-Control value>" once per Cache-Control header of one answer, so a second
# header or another status cannot pass.
status_and_cache() { curl -sS -o /dev/null -D - "$@" | tr -d '\r' | awk 'NR==1 { status=$2 } tolower($1)=="cache-control:" { sub(/^[^:]*: /, ""); print status, $0 }'; }
IMMUTABLE_VALUE="${IMMUTABLE#cache-control: }"
check "a missing asset is 404 and not cacheable (exactly no-store)" test "$(status_and_cache "$BASE/assets/missing.js")" = '404 no-store'
check "a missing path below /assets/ is not cacheable either" test "$(status_and_cache "$BASE/assets/a/b.css")" = '404 no-store'
check "the hashed asset is immutable for a year (exact value)" test "$(status_and_cache "$BASE$HASHED_ASSET")" = "200 $IMMUTABLE_VALUE"
ETAG="$(curl -sSI "$BASE$HASHED_ASSET" | tr -d '\r' | sed -n 's/^[Ee][Tt]ag: //p' || true)"
check "the hashed asset has an ETag" test -n "$ETAG"
check "a 304 for the hashed asset repeats the immutable policy" test "$(status_and_cache -H "If-None-Match: ${ETAG:-\"none\"}" "$BASE$HASHED_ASSET")" = "304 $IMMUTABLE_VALUE"
# Ranges are off (max_ranges 0): nginx adds the headers before the range filter and again for a 416,
# which would answer an unsatisfiable range with both cache policies and every security header twice.
check "a range request for the hashed asset is answered whole, with one policy" test "$(status_and_cache -H 'Range: bytes=0-9' "$BASE$HASHED_ASSET")" = "200 $IMMUTABLE_VALUE"
check "an unsatisfiable range on the hashed asset is no 416 with two policies" test "$(status_and_cache -H 'Range: bytes=999999999-' "$BASE$HASHED_ASSET")" = "200 $IMMUTABLE_VALUE"
check "an unsatisfiable range on the shell is no 416 with every header twice" test "$(status_and_cache -H 'Range: bytes=999999999-' "$BASE/")" = '200 no-store'
check "container variables named like nginx variables do not reach the template (status, uri)" bash -c "docker run --rm -e status=200 -e uri=/index.html '$IMAGE' nginx -T 2>/dev/null | grep -qF 'map \$status \$owlmast_asset_cache_control' && docker run --rm -e status=200 -e uri=/index.html '$IMAGE' nginx -T 2>/dev/null | grep -qF 'try_files \$uri /index.html'"
check "no JDK in the image" bash -c "! docker run --rm --entrypoint sh '$IMAGE' -c 'command -v java'"
check "no backend jar in the image" bash -c "! docker run --rm --entrypoint sh '$IMAGE' -c 'find / -name \"*.jar\" 2>/dev/null | grep -q .'"
check "a request below the API prefix is 404, never the shell (misrouted API fails closed)" bash -c "[ \"\$(curl -s -o \"$TMP/misrouted\" -w '%{http_code}' '$BASE$PREFIX/compatibility')\" = 404 ] && ! grep -q '<div id=\"root\">' \"$TMP/misrouted\""
check "the API prefix itself is 404 too" bash -c "[ \"\$(curl -s -o /dev/null -w '%{http_code}' '$BASE$PREFIX')\" = 404 ]"
check "the API prefix match is a path segment (a sibling path is still the shell)" bash -c "curl -fsS '$BASE${PREFIX}x' | grep -q '<div id=\"root\">'"
check "image does not proxy the backend (no upstream is configured)" bash -c "! docker exec '$NAME' nginx -T 2>/dev/null | grep -q 'proxy_pass'"
check "published API contract equals the build's manifest" bash -c "curl -fsS '$BASE/api-compatibility.json' | cmp -s - '$ROOT/frontend/api-compatibility.json'"
check "published API contract is JSON and not cached" bash -c "curl -fsSI '$BASE/api-compatibility.json' | grep -qi 'content-type: application/json' && curl -fsSI '$BASE/api-compatibility.json' | grep -qi 'cache-control: no-store'"
check "pre-rollout check reads the contract from the running artifact (--frontend-url)" bash -c "python3 '$ROOT/scripts/check-api-compatibility.py' --frontend-url '$BASE' | grep -q \"^COMPATIBLE: .*from $BASE\""

# Start-up guard (docker-entrypoint.d/16-owlmast-api-prefix.envsh): a prefix that would break the
# nginx template, be read as an nginx variable or point the shell at another origin stops the
# container with a diagnostic instead of serving a misconfigured shell.
refuses_prefix() {
  local out
  if out="$(docker run --rm -e "OWLMAST_API_PATH_PREFIX=$1" "$IMAGE" nginx -t 2>&1)"; then
    echo "      started with prefix '$1'"; return 1
  fi
  grep -q 'OWLMAST_API_PATH_PREFIX' <<<"$out" || { echo "      no diagnostic for '$1': $out"; return 1; }
}
for bad in "/a'b" '/a$b' '/a"b' '/a b' '/a%2Fb' '/a;b' '//evil.example' '/a//b' '/a/../b' '/a/./b' '/a/..' 'api' '' '/' '//' '/assets' '/assets/x' '/owlmast-config.json' '/api-compatibility.json' \
  '/index.html' '/theme-boot.js' '/owl-mark.svg' '/index.html/' '/index.html/x' '/theme-boot.js/x' \
  '/focus' '/knowledge' '/connections' '/usage' '/preferences' '/usage/' '/focus/x' '/preferences/api'; do
  check "start-up refuses OWLMAST_API_PATH_PREFIX='$bad'" refuses_prefix "$bad"
done
check "a prefix that only shares a string prefix with an own path or a shell page still starts (/assetsx, /index.htmlx, /api, /usagex, /owl/usage; /Usage, as the router matches case)" bash -c "for ok in /assetsx /index.htmlx /api /owl/index.html /usagex /owl/usage /Usage; do docker run --rm -e OWLMAST_API_PATH_PREFIX=\$ok '$IMAGE' nginx -t >/dev/null 2>&1 || { echo \"      refused \$ok\"; exit 1; }; done"
check "a trailing slash is normalised before the template is rendered" bash -c "docker run --rm -e OWLMAST_API_PATH_PREFIX=/owl/api/ '$IMAGE' nginx -T 2>/dev/null | grep -qF '{\"apiPathPrefix\":\"/owl/api\"}'"

# The chart runs the shell as UID/GID 101 on a read-only root with emptyDirs at /tmp and /etc/nginx/conf.d
# (deploy/helm/owl-mast/templates/frontend-deployment.yaml); the same constraints here.
CHART_FRONTEND="$ROOT/deploy/helm/owl-mast/templates/frontend-deployment.yaml"
RUN_UID="$(sed -n '/^    spec:/,/containers:/s/^        runAsUser: //p' "$CHART_FRONTEND")"
RUN_GID="$(sed -n '/^    spec:/,/containers:/s/^        runAsGroup: //p' "$CHART_FRONTEND")"
[ -n "$RUN_UID" ] && [ -n "$RUN_GID" ] || { echo "FAIL: runAsUser/runAsGroup not found in $CHART_FRONTEND"; exit 1; }
RO_NAME="$NAME-ro"
trap 'cleanup; docker rm -f "$RO_NAME" >/dev/null 2>&1 || true' EXIT
docker run -d --name "$RO_NAME" --user "$RUN_UID:$RUN_GID" --read-only --cap-drop ALL --security-opt no-new-privileges \
  --tmpfs "/tmp:rw,uid=$RUN_UID,gid=$RUN_GID" --tmpfs "/etc/nginx/conf.d:rw,uid=$RUN_UID,gid=$RUN_GID" \
  -e "OWLMAST_API_PATH_PREFIX=$PREFIX" -p 127.0.0.1::8080 "$IMAGE" >/dev/null
RO_BASE="http://127.0.0.1:$(docker port "$RO_NAME" 8080/tcp | head -n1 | sed 's/.*://')"
for _ in $(seq 1 50); do
  if curl -fs -o /dev/null "$RO_BASE/"; then break; fi
  sleep 0.2
done
check "chart runtime constraints (UID/GID $RUN_UID:$RUN_GID, read-only root, no capabilities, emptyDir paths): shell served" bash -c "curl -fsS '$RO_BASE/' | grep -q '<div id=\"root\">'"
check "chart runtime constraints: config endpoint rendered from the template" bash -c "[ \"\$(curl -fsS '$RO_BASE/owlmast-config.json')\" = '{\"apiPathPrefix\":\"$PREFIX\"}' ]"

if [ "${OWLMAST_IMAGE_BROWSER_SMOKE:-0}" = "1" ]; then
  echo "== Chromium against the image (production CSP, nginx template, runtime config)"
  check "browser smoke of the built image (frontend/e2e/image)" bash -c "cd '$ROOT/frontend' && OWLMAST_IMAGE_BASE_URL='$BASE' OWLMAST_IMAGE_API_PREFIX='$PREFIX' npm run --silent test:e2e:image"
elif [ -n "${CI:-}" ]; then
  # A dropped or misspelt variable in the workflow must not turn the browser check into a silent skip.
  echo "FAIL [browser smoke of the built image]: CI run without OWLMAST_IMAGE_BROWSER_SMOKE=1"
  failures=$((failures + 1))
else
  echo "skip [browser smoke of the built image]: set OWLMAST_IMAGE_BROWSER_SMOKE=1 (CI does)"
fi

if [ "$failures" -ne 0 ]; then
  echo "$failures frontend artifact check(s) failed"
  exit 1
fi
echo "frontend artifact $IMAGE honours the deployment contract"
