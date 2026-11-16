#!/usr/bin/env bash
# Build the test-only real-application fixture. Arguments: fresh output directory, image tag,
# local backend base image (built with backend/Dockerfile). Artifacts are retained.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
[ "$#" -eq 3 ] || { echo 'usage: build-partition-fixture.sh NEW_OUTPUT IMAGE BASE_IMAGE' >&2; exit 2; }
mkdir "$1"
OUT="$(cd "$1" && pwd)"
BASE="$(docker image inspect "$3" --format '{{.Id}}')"
cd "$ROOT"
./gradlew -I scripts/partition-fixture/export.gradle -PfixtureOutput="$OUT" :backend:exportPartitionFixture
cat > "$OUT/Dockerfile" <<'DOCKER'
ARG BASE
FROM ${BASE}
COPY classes /fixture
ENTRYPOINT ["java", "--enable-native-access=ALL-UNNAMED", "-Xmx512m", "-cp", "/fixture:/fixture/*", "com.aisquad.owlmast.fixtures.restart.RestartFixtureProcess"]
DOCKER
git rev-parse HEAD > "$OUT/source-head.txt"
git diff --binary HEAD -- backend > "$OUT/backend.diff"
find backend/src -type f -print0 | sort -z | xargs -0 sha256sum > "$OUT/source-files.sha256"
printf '%s\n' "$BASE" > "$OUT/base-image-id.txt"
docker build --build-arg "BASE=$3" -t "$2" "$OUT"
[ "$(docker image inspect "$3" --format '{{.Id}}')" = "$BASE" ]
docker image inspect "$2" --format '{{.Id}}' > "$OUT/image-id.txt"
