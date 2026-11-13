#!/usr/bin/env bash
# Shell and Python lint gate (E01-R-11): the repository's own scripts and Python had no static check in CI.
#   - shellcheck v0.11.0 over every shell file of the repository itself (*.sh anywhere outside the excluded
#     directories below, and the frontend image's entrypoint fragments), at severity `warning`: errors and
#     warnings fail; `info` and `style` notes do not (the scripts use `A && B || C` and single-quoted
#     psql/jsonpath text deliberately). Shell embedded in other files (the chart's ConfigMap scripts, the bash
#     stubs inside the deploy tests) is not extracted and not linted here.
#   - ruff (version pinned with hashes in scripts/lint-requirements.txt) over scripts/, deploy/ and automation/
#     with the rule set in ruff.toml (syntax errors, pyflakes, bugbear).
# The vendored BMAD tooling (.agents, .claude, .codex, _bmad, _bmad-output), dependency and build output
# (node_modules, build, dist, .gradle) and the Gradle wrapper script (`gradlew`, no .sh suffix) are not ours
# and are not linted. `scripts/verify-quality-gates.sh` injects one shell and one Python defect into a copy
# and requires this script to fail naming each. Tools: OWLMAST_SHELLCHECK / OWLMAST_RUFF name binaries to use as given; otherwise shellcheck is
# fetched (linux-x86_64 release archive, sha256 verified, re-extracted on every run) into OWLMAST_TOOLS_DIR
# or a scratch directory, and ruff is installed from the hashed requirements into a virtual environment there
# (never taken from PATH).
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SHELLCHECK_VERSION=v0.11.0
SHELLCHECK_SHA256=8c3be12b05d5c177a04c29e3c78ce89ac86f1595681cab149b65b97c4e227198
RUFF_VERSION="$(sed -n 's/^ruff==\([^ ]*\).*/\1/p' "$ROOT/scripts/lint-requirements.txt")"
[ -n "$RUFF_VERSION" ] || { echo "verify-script-lint: scripts/lint-requirements.txt does not pin ruff" >&2; exit 1; }
cd "$ROOT"

# shellcheck source=scripts/hashed-venv.sh
. "$ROOT/scripts/hashed-venv.sh"
TOOLS="${OWLMAST_TOOLS_DIR:-}"
SCRATCH_TOOLS=""
RUN_TOOLS=""
trap 'rm -rf ${RUN_TOOLS:+"$RUN_TOOLS"} ${HASHED_VENV:+"$HASHED_VENV"} ${SCRATCH_TOOLS:+"$SCRATCH_TOOLS"}' EXIT
scratch_tools() {
  if [ -z "$TOOLS" ]; then
    SCRATCH_TOOLS="$(mktemp -d "${TMPDIR:-/tmp}/owlmast-lint.XXXXXX")"
    TOOLS="$SCRATCH_TOOLS"
  fi
  mkdir -p "$TOOLS"
}

if [ -z "${OWLMAST_SHELLCHECK:-}" ]; then
  platform="$(uname -s)-$(uname -m)"
  if [ "$platform" != "Linux-x86_64" ]; then
    echo "verify-script-lint: the pinned shellcheck download is linux-x86_64 only; this host is $platform. Set OWLMAST_SHELLCHECK to shellcheck $SHELLCHECK_VERSION." >&2
    exit 1
  fi
  scratch_tools
  archive="$TOOLS/shellcheck-$SHELLCHECK_VERSION.tar.xz"
  if ! echo "$SHELLCHECK_SHA256  $archive" | sha256sum -c --status - >/dev/null 2>&1; then
    curl -fsSL -o "$archive" "https://github.com/koalaman/shellcheck/releases/download/$SHELLCHECK_VERSION/shellcheck-$SHELLCHECK_VERSION.linux.x86_64.tar.xz"
  fi
  echo "$SHELLCHECK_SHA256  $archive" | sha256sum -c -
  # Extracted into a directory of this run (removed on exit), so a run sharing OWLMAST_TOOLS_DIR never
  # replaces the binary another one is using (review cycle 4).
  RUN_TOOLS="$(mktemp -d "$TOOLS/shellcheck.XXXXXX")"
  tar -xJf "$archive" -C "$RUN_TOOLS" --strip-components=1 "shellcheck-$SHELLCHECK_VERSION/shellcheck"
  OWLMAST_SHELLCHECK="$RUN_TOOLS/shellcheck"
fi
shellcheck_version="$("$OWLMAST_SHELLCHECK" --version | sed -n 's/^version: //p')"
[ "v$shellcheck_version" = "$SHELLCHECK_VERSION" ] || { echo "verify-script-lint: $OWLMAST_SHELLCHECK is shellcheck $shellcheck_version, not $SHELLCHECK_VERSION" >&2; exit 1; }

if [ -z "${OWLMAST_RUFF:-}" ]; then
  # Never a ruff found on PATH: a version string proves nothing about the binary. scripts/hashed-venv.sh
  # installs ruff from the hashed requirements into a new environment of this run (never a reused one, wheels
  # only), removed on exit.
  scratch_tools
  hashed_venv "$TOOLS" ruff-venv scripts/lint-requirements.txt
  ruff_venv="$HASHED_VENV"
  OWLMAST_RUFF="$ruff_venv/bin/ruff"
fi
[ "$("$OWLMAST_RUFF" --version)" = "ruff $RUFF_VERSION" ] || { echo "verify-script-lint: $OWLMAST_RUFF is $("$OWLMAST_RUFF" --version), not ruff $RUFF_VERSION" >&2; exit 1; }

# Every shell file of the repository itself, found by name so a new script anywhere is picked up without
# editing this file (and without needing a git checkout).
mapfile -t shell_files < <(
  find . \( -name .git -o -name node_modules -o -name build -o -name dist -o -name .gradle -o -name .agents -o -name .claude \
            -o -name .codex -o -name _bmad -o -name _bmad-output \) -prune \
         -o -type f \( -name '*.sh' -o -path './frontend/docker-entrypoint.d/*' \) -print | sed 's|^\./||' | sort)
[ "${#shell_files[@]}" -gt 0 ] || { echo "verify-script-lint: no shell scripts found under $ROOT" >&2; exit 1; }

failures=0
echo "== shellcheck $SHELLCHECK_VERSION (severity warning) over ${#shell_files[@]} file(s): ${shell_files[*]}"
if "$OWLMAST_SHELLCHECK" --severity=warning "${shell_files[@]}"; then
  echo "ok   [shellcheck]"
else
  echo "FAIL [shellcheck]"; failures=$((failures + 1))
fi

echo "== ruff $RUFF_VERSION (ruff.toml) over scripts deploy automation"
if "$OWLMAST_RUFF" check --no-cache scripts deploy automation; then
  echo "ok   [ruff]"
else
  echo "FAIL [ruff]"; failures=$((failures + 1))
fi

if [ "$failures" -ne 0 ]; then
  echo "$failures lint gate(s) failed"
  exit 1
fi
echo "shell and Python lint gates pass"
