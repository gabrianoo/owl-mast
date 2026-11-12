#!/usr/bin/env bash
# OM-01.04 AC4: build the independent frontend image and prove its runtime contract without any
# backend: serves the shell on 8080 as a non-root user, falls back to index.html for app routes,
# publishes the API path prefix it was deployed with, and contains no JDK or backend jar.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
IMAGE="${OWLMAST_FRONTEND_IMAGE:-owl-mast/frontend:0.1.0-verify}"
NAME="owlmast-frontend-verify-$$"
PREFIX="/owl/api"

cleanup() { docker rm -f "$NAME" >/dev/null 2>&1 || true; }
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
check "hashed assets served with immutable caching" bash -c "asset=\$(curl -fsS '$BASE/' | grep -o '/assets/[^\"]*\\.js' | head -n1); curl -fsSI \"$BASE\$asset\" | grep -qi 'immutable'"
check "no JDK in the image" bash -c "! docker run --rm --entrypoint sh '$IMAGE' -c 'command -v java'"
check "no backend jar in the image" bash -c "! docker run --rm --entrypoint sh '$IMAGE' -c 'find / -name \"*.jar\" 2>/dev/null | grep -q .'"
check "image does not proxy the backend (/api is handled by the shell fallback, not nginx proxy)" bash -c "curl -fsS '$BASE/api/compatibility' | grep -q '<div id=\"root\">'"

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

if [ "$failures" -ne 0 ]; then
  echo "$failures frontend artifact check(s) failed"
  exit 1
fi
echo "frontend artifact $IMAGE honours the deployment contract"
