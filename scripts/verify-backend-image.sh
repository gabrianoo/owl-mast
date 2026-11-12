#!/usr/bin/env bash
# OM-01.02-T2 backend runtime image check (PR #109 review 4513680598): build the image the chart defaults to
# from the bootJar and prove its contract, so a version bump, a JDK URL/checksum change or a UID mismatch
# with the chart fails CI instead of the next manual Kind run.
#   - the jar named by backend/Dockerfile (ARG JAR_FILE) and allowed by backend/.dockerignore is the
#     executable bootJar Gradle produces for the version in backend/build.gradle.kts;
#   - `docker build` succeeds (the Temurin tarball checksum is verified inside the build);
#   - the image runs as UID/GID 10001, the identity the chart's backend Deployment enforces;
#   - the JVM is the qualified Temurin 27.0.1 and starts on a read-only root with /tmp as tmpfs;
#   - the application jar is present at /app/owl-mast.jar and is a Spring Boot executable archive;
#   - the APPLICATION starts on that read-only root as the chart runs it (UID/GID, no capabilities, no new
#     privileges, /tmp the only writable path): the image's own entrypoint launches Spring Boot with the
#     environment variables the chart's backend Deployment renders (same names, the database URLs with the
#     ?sslMode= / ?sslmode= parameter the chart always appends; a deploy test compares the two), the database on a
#     closed loopback port. Three starts:
#       1. an https issuer without the plaintext opt-in (an external issuer);
#       2. an http issuer with the opt-in, which is what the default bundled install renders;
#       3. an http issuer WITHOUT the opt-in, which must be refused by the identity configuration. It is the
#          control that the binding checks of starts 1 and 2 can fail.
#     In starts 1 and 2 the context binds the configuration (the identity configuration logs the issuer it
#     bound), creates the beans that PRECEDE database initialisation and stops at the first database connection
#     (the Flyway initializer), which is refused by design. A broken launcher, a class-loading failure, a
#     configuration-binding failure or a filesystem write outside /tmp up to that point fails here instead of on
#     the next Kind run.
#     NOT proven here (image-level proof, not runtime qualification): the beans Spring Boot creates only after
#     database initialisation (the R2DBC-backed adapters and whatever depends on them) and everything after the
#     first database connection, that is the migrations, the R2DBC pool, the Netty listener and any file the
#     running application writes. Those belong to the Kind qualification (scripts/qualify-local-install.sh).
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

# The application itself, started by the image's own entrypoint exactly as the chart's pod runs it, with the
# variables the chart's backend Deployment renders (deploy/tests compares the names and the URL forms with a
# render). There is no network and nothing listens on the loopback port, so a healthy image binds its
# configuration, creates the beans that precede database initialisation and exits when the Flyway
# initializer's first connection is refused; any other ending is a failure of the image, not of the configuration.
smoke_log=""
smoke_rc=0
smoke() { # smoke <issuer> <allow-insecure-issuer>: sets smoke_log and smoke_rc
  local name="owlmast-backend-smoke-$$"
  smoke_rc=0
  smoke_log="$(timeout 180 docker run --name "$name" --network none --read-only --tmpfs /tmp:rw,size=64m \
    --user "$chart_uid:$chart_gid" --cap-drop ALL --security-opt no-new-privileges \
    -e SERVER_PORT=8080 \
    -e JAVA_TOOL_OPTIONS=-XX:MaxRAMPercentage=75 \
    -e "OWLMAST_DATABASE_R2DBC_URL=r2dbc:postgresql://127.0.0.1:1/owlmast?sslMode=disable" \
    -e "OWLMAST_DATABASE_JDBC_URL=jdbc:postgresql://127.0.0.1:1/owlmast?sslmode=disable" \
    -e OWLMAST_DATABASE_USERNAME=smoke -e OWLMAST_DATABASE_PASSWORD=smoke \
    -e "OWLMAST_IDENTITY_ISSUER_URI=$1" -e "OWLMAST_IDENTITY_ALLOW_INSECURE_ISSUER=$2" "$IMAGE" 2>&1)" || smoke_rc=$?
  docker rm -f "$name" >/dev/null 2>&1 || true
}
smoke_checks() { # smoke_checks <label> <issuer> <allow-insecure-issuer>: a start that must reach the first database connection
  local label="$1" before="$failures"
  check "$label: the application process ended by itself (no hang, exit code $smoke_rc)" test "$smoke_rc" -ne 0 -a "$smoke_rc" -ne 124
  check "$label: Spring Boot started from the image entrypoint" grep -q 'Starting OwlMastApplication' <<<"$smoke_log"
  check "$label: the identity configuration was bound (issuer $2, plaintext accepted: $3)" grep -qF "Identity issuer $2 (plaintext issuer accepted: $3)" <<<"$smoke_log"
  check "$label: no configuration-binding refusal" bash -c '! grep -Eq "owlmast\.identity\.|Failed to bind properties|ConfigurationPropertiesBindException" <<<"$1"' _ "$smoke_log"
  check "$label: bean creation reached the actuator endpoints" grep -Eq "Exposing [0-9]+ endpoints? beneath base path '/actuator'" <<<"$smoke_log"
  check "$label: startup stopped at the first database connection (Flyway initializer, connection refused)" bash -c 'grep -q "flywayInitializer" <<<"$1" && grep -q "Connection to 127.0.0.1:1 refused" <<<"$1"' _ "$smoke_log"
  check "$label: no filesystem, launcher or class-loading failure on the read-only root up to that point" bash -c '! grep -Eqi "Read-only file system|Permission denied|AccessDeniedException|ClassNotFoundException|NoClassDefFoundError|Unable to access jarfile|no main manifest attribute|UnsatisfiedLinkError" <<<"$1"' _ "$smoke_log"
  if [ "$failures" -ne "$before" ]; then echo "---- application output of '$label' (last 40 lines)"; tail -n 40 <<<"$smoke_log"; fi
}

echo "== start the application on the read-only root (expected to stop at the first database connection)"
smoke https://idp.invalid/realms/owl-mast false
smoke_checks "external https issuer" https://idp.invalid/realms/owl-mast false
# What the default bundled install renders: the cluster-local Keycloak over http, with the explicit opt-in.
smoke http://owl-mast-keycloak:8080/realms/owl-mast true
smoke_checks "bundled http issuer with the opt-in" http://owl-mast-keycloak:8080/realms/owl-mast true
# Control: the same http issuer without the opt-in is refused by the identity configuration, before any
# database connection. It proves the binding checks above are able to fail.
smoke http://owl-mast-keycloak:8080/realms/owl-mast false
check "control: an http issuer without the opt-in is refused by the identity configuration" grep -q 'owlmast.identity.issuer-uri must use https' <<<"$smoke_log"
check "control: the refused start ended by itself and never reached the database (exit code $smoke_rc)" bash -c '[ "$2" -ne 0 ] && [ "$2" -ne 124 ] && ! grep -q "Connection to 127.0.0.1:1 refused" <<<"$1"' _ "$smoke_log" "$smoke_rc"

if [ "$failures" -ne 0 ]; then
  echo "$failures backend image check(s) failed"
  exit 1
fi
echo "backend image $IMAGE honours the chart's image contract (start proven up to the first database connection, for the beans that precede database initialisation; runtime qualification is the Kind run)"
