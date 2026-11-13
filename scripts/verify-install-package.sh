#!/usr/bin/env bash
# OM-01.02 packaging checks: lint and render the owl-mast chart for every bundled/external
# combination and assert fail-closed validation. Uses OWLMAST_HELM when set; otherwise fetches the
# qualified Helm 4.3.1 (checksum verified) into OWLMAST_TOOLS_DIR or, when that is unset, a scratch directory that is
# removed on exit. Installed Helm 3.x is not used.
# A cached tool in OWLMAST_TOOLS_DIR (created if missing) is never trusted as is: the Helm binary is
# extracted on every run, into a directory of that run (removed on exit), from an archive whose sha256 is verified
# and must report version v4.3.1, so a run sharing OWLMAST_TOOLS_DIR never replaces the binary another one is using;
# the kubectl binary's own sha256 is re-verified and its client gitVersion must be v1.36.1. Binaries supplied
# through OWLMAST_HELM / OWLMAST_KUBECTL are used as given (not checksummed here; the chart tests still
# require Helm 4). The pinned downloads exist for linux-amd64 only; other platforms must supply both.
# OWLMAST_VERIFY_TOOLS_ONLY=1 stops after the tools are verified (used by the deploy tests).
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
HELM_VERSION=v4.3.1
HELM_SHA256=0403a88ae20913d11b10a2467b50087721fea7581736da6b9d3992f5357fe54b
KUBECTL_VERSION=v1.36.1
KUBECTL_SHA256=629d3f410e09bf49b64ae7079f7f0bda1191efed311f7d37fdbab0ad5b0ec2b7

sha256_ok() { echo "$2  $1" | sha256sum -c --status - 2>/dev/null; }
# A relative OWLMAST_TOOLS_DIR is resolved once, against the caller's directory, before anything is created in it:
# the suite runs after `cd "$ROOT"`, where a relative path would name another directory, and the EXIT trap would
# then miss the Helm directory and the environment this run made there (review cycle 9, R9-2).
if [ -n "${OWLMAST_TOOLS_DIR:-}" ]; then
  mkdir -p "$OWLMAST_TOOLS_DIR"
  OWLMAST_TOOLS_DIR="$(CDPATH='' cd -- "$OWLMAST_TOOLS_DIR" && pwd)"
fi
# What this run creates is removed on exit, also when the run fails: the directory it extracts Helm into, the scratch
# directory for the Helm and kubectl downloads (when OWLMAST_TOOLS_DIR is unset), the hashed environment and the
# scratch directory that holds it. Each name is cleared here first, so a value inherited from the caller's
# environment is never removed (review cycle 8, R8-1: the trap is set before scripts/hashed-venv.sh is sourced).
HASHED_VENV=""
RUN_HELM=""
SCRATCH_TOOLS=""
SCRATCH_HOME=""
trap 'rm -rf ${RUN_HELM:+"$RUN_HELM"} ${HASHED_VENV:+"$HASHED_VENV"} ${SCRATCH_HOME:+"$SCRATCH_HOME"} ${SCRATCH_TOOLS:+"$SCRATCH_TOOLS"}' EXIT
scratch_tools() {
  [ -n "$SCRATCH_TOOLS" ] || SCRATCH_TOOLS="$(mktemp -d "${TMPDIR:-/tmp}/owlmast-tools.XXXXXX")"
}
require_pinned_platform() {
  local platform; platform="$(uname -s)-$(uname -m)"
  if [ "$platform" != "Linux-x86_64" ]; then
    echo "verify-install-package: the pinned Helm/kubectl downloads are linux-amd64 only; this host is $platform." >&2
    echo "Set OWLMAST_HELM and OWLMAST_KUBECTL to qualified binaries for this platform." >&2
    exit 1
  fi
}

if [ -z "${OWLMAST_HELM:-}" ]; then
  require_pinned_platform
  [ -n "${OWLMAST_TOOLS_DIR:-}" ] || scratch_tools
  TOOLS="${OWLMAST_TOOLS_DIR:-$SCRATCH_TOOLS}"
  mkdir -p "$TOOLS"
  if ! sha256_ok "$TOOLS/helm.tar.gz" "$HELM_SHA256"; then
    curl -fsSL -o "$TOOLS/helm.tar.gz" "https://get.helm.sh/helm-${HELM_VERSION}-linux-amd64.tar.gz"
  fi
  echo "$HELM_SHA256  $TOOLS/helm.tar.gz" | sha256sum -c -
  # Always extract from the verified archive, so a cached binary never stands in for it, and into a directory of
  # this run, so a run sharing OWLMAST_TOOLS_DIR never deletes or rewrites the binary another one is using (R8-3).
  RUN_HELM="$(mktemp -d "$TOOLS/helm.XXXXXX")"
  tar -xzf "$TOOLS/helm.tar.gz" -C "$RUN_HELM" --strip-components=1 linux-amd64/helm
  export OWLMAST_HELM="$RUN_HELM/helm"
  [ "$("$OWLMAST_HELM" version --template '{{.Version}}')" = "$HELM_VERSION" ] || { echo "verify-install-package: $OWLMAST_HELM is not Helm $HELM_VERSION" >&2; exit 1; }
fi

# The discovery regression drives the real Kubernetes client against a loopback server. Use the official
# kubectl v1.36.1 release binary (checksum verified) unless OWLMAST_KUBECTL names one.
if [ -z "${OWLMAST_KUBECTL:-}" ]; then
  require_pinned_platform
  [ -n "${OWLMAST_TOOLS_DIR:-}" ] || scratch_tools
  TOOLS="${OWLMAST_TOOLS_DIR:-$SCRATCH_TOOLS}"
  mkdir -p "$TOOLS"
  if ! sha256_ok "$TOOLS/kubectl" "$KUBECTL_SHA256"; then
    rm -f "$TOOLS/kubectl"
    curl -fsSL -o "$TOOLS/kubectl" "https://dl.k8s.io/release/${KUBECTL_VERSION}/bin/linux/amd64/kubectl"
  fi
  echo "$KUBECTL_SHA256  $TOOLS/kubectl" | sha256sum -c -
  chmod 755 "$TOOLS/kubectl"
  export OWLMAST_KUBECTL="$TOOLS/kubectl"
  kubectl_version="$("$OWLMAST_KUBECTL" version --client -o json | python3 -c 'import json,sys; print(json.load(sys.stdin)["clientVersion"]["gitVersion"])')"
  [ "$kubectl_version" = "$KUBECTL_VERSION" ] || { echo "verify-install-package: $OWLMAST_KUBECTL reports $kubectl_version, not kubectl $KUBECTL_VERSION" >&2; exit 1; }
fi
"$OWLMAST_KUBECTL" version --client
"$OWLMAST_HELM" version
[ "${OWLMAST_VERIFY_TOOLS_ONLY:-}" = 1 ] && exit 0
# The deploy tests need PyYAML and jsonschema (the Gateway API schema tests validate rendered HTTPRoutes
# against the pinned upstream schema offline). The whole set, with its transitive dependencies, is pinned
# with hashes in deploy/tests/requirements.txt (generated from requirements.in) and installed with
# --require-hashes into a virtual environment of its own, so the suite never runs against whatever the
# interpreter happens to have and nothing is installed into it (E01-R-11). scripts/hashed-venv.sh creates a new
# environment on every run (never a reused one, wheels only) under OWLMAST_TOOLS_DIR when that is set and
# otherwise under a scratch directory, and this script removes it on exit.
REQUIREMENTS="$ROOT/deploy/tests/requirements.txt"
# shellcheck source=scripts/hashed-venv.sh
. "$ROOT/scripts/hashed-venv.sh"
VENV_HOME="${OWLMAST_TOOLS_DIR:-}"
[ -n "$VENV_HOME" ] || { SCRATCH_HOME="$(mktemp -d "${TMPDIR:-/tmp}/owlmast-deploy-tests.XXXXXX")"; VENV_HOME="$SCRATCH_HOME"; }
hashed_venv "$VENV_HOME" deploy-tests-venv "$REQUIREMENTS"
VENV="$HASHED_VENV"
"$VENV/bin/python" -m pip check --disable-pip-version-check
"$VENV/bin/python" -m pip list --format=freeze --disable-pip-version-check 2>/dev/null | grep -iE '^(pyyaml|jsonschema)=='
cd "$ROOT"
# The suite runs the scripts under test (qualify-local-install.sh parses manifests with `python3` and PyYAML), so
# the environment's interpreter comes first on PATH: the scripts see the pinned packages, never the host's.
PATH="$VENV/bin:$PATH" "$VENV/bin/python" -m unittest discover -s deploy/tests -t . -v
