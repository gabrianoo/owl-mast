#!/usr/bin/env bash
# Sourced by verify-install-package.sh and verify-script-lint.sh (E01-R-11): one Python virtual environment
# per run, installed from a hash-pinned requirements file.
#
# hashed_venv <home> <name> <requirements>: creates a new, empty directory `<home>/<name>.XXXXXX`, sets
# HASHED_VENV to it before anything is installed (so the caller's EXIT trap can remove it), and installs the
# requirements into it. Call it directly, not in $(...), so a failure stops the caller. Never a reused
# environment: an earlier one can hold a .pth file, sitecustomize or a changed pip that no distribution
# owns and no reinstall removes (review cycle 3), and a fixed path would let two runs that share <home>
# delete each other's environment (review cycle 4). Only pip's download cache is reused. --require-hashes
# checks every archive pip installs, and --only-binary :all: accepts wheels only, so no sdist is built: a
# build would fetch its build dependencies without hash checks (review cycle 4).
HASHED_VENV=""
hashed_venv() {
  local home="$1" name="$2" requirements="$3"
  mkdir -p "$home" || return 1
  HASHED_VENV="$(mktemp -d "$home/$name.XXXXXX")" || return 1
  python3 -m venv "$HASHED_VENV" || return 1
  "$HASHED_VENV/bin/python" -m pip install --quiet --disable-pip-version-check --require-hashes \
    --only-binary :all: --no-deps -r "$requirements" || return 1
}
