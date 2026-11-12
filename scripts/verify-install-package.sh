#!/usr/bin/env bash
# OM-01.02 packaging checks: lint and render the owl-mast chart for every bundled/external
# combination and assert fail-closed validation. Uses OWLMAST_HELM when set; otherwise fetches the
# qualified Helm 4.3.1 (checksum verified) into a scratch directory. Installed Helm 3.x is not used.
# A cached tool in OWLMAST_TOOLS_DIR (created if missing) is never trusted as is: the Helm binary is
# re-extracted on every run from an archive whose sha256 is verified and must report version v4.3.1; the
# kubectl binary's own sha256 is re-verified and its client gitVersion must be v1.36.1. Binaries supplied
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
  TOOLS="${OWLMAST_TOOLS_DIR:-$(mktemp -d "${TMPDIR:-/tmp}/owlmast-helm.XXXXXX")}"
  mkdir -p "$TOOLS"
  if ! sha256_ok "$TOOLS/helm.tar.gz" "$HELM_SHA256"; then
    curl -fsSL -o "$TOOLS/helm.tar.gz" "https://get.helm.sh/helm-${HELM_VERSION}-linux-amd64.tar.gz"
  fi
  echo "$HELM_SHA256  $TOOLS/helm.tar.gz" | sha256sum -c -
  # Always (re-)extract from the verified archive, so a cached binary never stands in for it.
  rm -f "$TOOLS/helm"
  tar -xzf "$TOOLS/helm.tar.gz" -C "$TOOLS" --strip-components=1 linux-amd64/helm
  export OWLMAST_HELM="$TOOLS/helm"
  [ "$("$OWLMAST_HELM" version --template '{{.Version}}')" = "$HELM_VERSION" ] || { echo "verify-install-package: $OWLMAST_HELM is not Helm $HELM_VERSION" >&2; exit 1; }
fi

# The discovery regression drives the real Kubernetes client against a loopback server. Use the official
# kubectl v1.36.1 release binary (checksum verified) unless OWLMAST_KUBECTL names one.
if [ -z "${OWLMAST_KUBECTL:-}" ]; then
  require_pinned_platform
  TOOLS="${OWLMAST_TOOLS_DIR:-${TOOLS:-$(mktemp -d "${TMPDIR:-/tmp}/owlmast-kubectl.XXXXXX")}}"
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
# against the pinned upstream schema offline). Both are pinned, with their dependencies and hashes, in
# deploy/tests/requirements.txt (generated from requirements.in). When the interpreter already has exactly
# the two pinned versions nothing is installed; otherwise the pinned set is installed with hash checking, so
# a floating range can no longer change what the suite runs against (E01-R-11).
REQUIREMENTS="$ROOT/deploy/tests/requirements.txt"
pins_installed() {
  python3 - "$REQUIREMENTS" <<'PY'
import re, sys
from importlib import metadata
wanted = {}
for line in open(sys.argv[1], encoding="utf-8"):
    match = re.match(r"^(pyyaml|jsonschema)==(\S+)", line.strip(), re.IGNORECASE)
    if match:
        wanted[match.group(1).lower()] = match.group(2)
if set(wanted) != {"pyyaml", "jsonschema"}:
    sys.exit("verify-install-package: deploy/tests/requirements.txt must pin PyYAML and jsonschema")
for name, version in wanted.items():
    try:
        found = metadata.version(name)
    except metadata.PackageNotFoundError:
        sys.exit(1)
    if found != version:
        sys.exit(1)
PY
}
if ! pins_installed; then
  python3 -m pip install --quiet --disable-pip-version-check --require-hashes -r "$REQUIREMENTS"
  pins_installed || { echo "verify-install-package: the pinned PyYAML/jsonschema of deploy/tests/requirements.txt are not the ones python3 imports" >&2; exit 1; }
fi
cd "$ROOT"
python3 -m unittest discover -s deploy/tests -t . -v
