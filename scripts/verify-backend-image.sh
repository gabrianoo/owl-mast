#!/usr/bin/env bash
# OM-01.02-T2 backend runtime image check (PR #109 review 4513680598): build the image the chart defaults to
# from the bootJar and prove its contract, so a version bump, a JDK URL/checksum change or a UID mismatch
# with the chart fails CI instead of the next manual Kind run.
#   - the jar named by backend/Dockerfile (ARG JAR_FILE) and allowed by backend/.dockerignore is the
#     executable bootJar Gradle produces for the version in backend/build.gradle.kts;
#   - `docker build` succeeds (the Temurin tarball checksum is verified inside the build);
#   - the image runs as UID/GID 10001, the identity the chart's backend Deployment enforces;
#   - the JVM is the qualified Temurin 27.0.1 and starts on a read-only root with /tmp as tmpfs;
#   - the application jar is present at /app/owl-mast.jar and is a Spring Boot executable archive.
# Usage: scripts/verify-backend-image.sh   (builds the bootJar first unless OWLMAST_SKIP_BOOTJAR=1)
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
IMAGE="${OWLMAST_BACKEND_IMAGE:-owl-mast/backend:0.1.0-verify}"
cd "$ROOT"

failures=0
check() {
  local name="$1"
  shift
  if "$@"; then echo "ok   [$name]"; else echo "FAIL [$name]"; failures=$((failures + 1)); fi
}

version="$(sed -n 's/^version = "\(.*\)"$/\1/p' backend/build.gradle.kts)"
jar_arg="$(sed -n 's/^ARG JAR_FILE=//p' backend/Dockerfile)"
allowed="$(sed -n 's/^!//p' backend/.dockerignore)"
chart_uid="$(sed -n '/^    spec:/,/containers:/s/^        runAsUser: //p' deploy/helm/owl-mast/templates/backend-deployment.yaml)"
chart_gid="$(sed -n '/^    spec:/,/containers:/s/^        runAsGroup: //p' deploy/helm/owl-mast/templates/backend-deployment.yaml)"
echo "== backend version $version, Dockerfile jar $jar_arg, .dockerignore allows $allowed, chart runs as $chart_uid:$chart_gid"
[ -n "$version" ] || { echo "FAIL: no version in backend/build.gradle.kts"; exit 1; }
check "Dockerfile JAR_FILE is the bootJar of version $version" test "$jar_arg" = "build/libs/backend-$version.jar"
check ".dockerignore admits exactly that jar" test "$allowed" = "$jar_arg"
if [ "$failures" -ne 0 ]; then echo "$failures backend image check(s) failed before the build"; exit 1; fi

if [ "${OWLMAST_SKIP_BOOTJAR:-}" != 1 ]; then
  ./gradlew :backend:bootJar --console=plain -q
fi
check "bootJar produced backend/$jar_arg" test -f "backend/$jar_arg"
if [ "$failures" -ne 0 ]; then exit 1; fi

echo "== build $IMAGE"
docker build --quiet -t "$IMAGE" -f backend/Dockerfile backend >/dev/null

run() { docker run --rm --network none --read-only --tmpfs /tmp:rw,size=64m "$@"; }
uid="$(run --entrypoint id "$IMAGE" -u)"
gid="$(run --entrypoint id "$IMAGE" -g)"
check "image user is UID $uid, the chart's runAsUser $chart_uid" test "$uid" = "$chart_uid"
check "image group is GID $gid, the chart's runAsGroup $chart_gid" test "$gid" = "$chart_gid"
check "image user is not root" test "$uid" != 0
java_version="$(run --entrypoint java "$IMAGE" -version 2>&1)"
check "qualified JVM (Temurin 27.0.1) starts on a read-only root" grep -q 'Temurin-27.0.1' <<<"$java_version"
check "application jar present at /app/owl-mast.jar" run --entrypoint test "$IMAGE" -f /app/owl-mast.jar
check "application jar is a Spring Boot executable archive" bash -c "docker run --rm --network none --entrypoint sh '$IMAGE' -c 'cd /tmp && jar tf /app/owl-mast.jar 2>/dev/null || unzip -l /app/owl-mast.jar' | grep 'BOOT-INF/lib/' >/dev/null"
check "entrypoint runs the application jar" bash -c "[ \"\$(docker image inspect -f '{{json .Config.Entrypoint}}' '$IMAGE')\" = '[\"java\",\"-jar\",\"/app/owl-mast.jar\"]' ]"

if [ "$failures" -ne 0 ]; then
  echo "$failures backend image check(s) failed"
  exit 1
fi
echo "backend image $IMAGE honours the chart's runtime contract"
