#!/usr/bin/env bash
# OM-01.02 packaging checks: lint and render the owl-mast chart for every bundled/external
# combination and assert fail-closed validation. Uses OWLMAST_HELM when set; otherwise fetches the
# qualified Helm 4.3.1 (checksum verified) into a scratch directory. Installed Helm 3.x is not used.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
HELM_VERSION=v4.3.1
HELM_SHA256=0403a88ae20913d11b10a2467b50087721fea7581736da6b9d3992f5357fe54b

if [ -z "${OWLMAST_HELM:-}" ]; then
  TOOLS="${OWLMAST_TOOLS_DIR:-$(mktemp -d "${TMPDIR:-/tmp}/owlmast-helm.XXXXXX")}"
  if [ ! -x "$TOOLS/helm" ]; then
    curl -fsSL -o "$TOOLS/helm.tar.gz" "https://get.helm.sh/helm-${HELM_VERSION}-linux-amd64.tar.gz"
    echo "$HELM_SHA256  $TOOLS/helm.tar.gz" | sha256sum -c -
    tar -xzf "$TOOLS/helm.tar.gz" -C "$TOOLS" --strip-components=1 linux-amd64/helm
  fi
  export OWLMAST_HELM="$TOOLS/helm"
fi

"$OWLMAST_HELM" version
python3 -c 'import yaml' 2>/dev/null || python3 -m pip install --quiet --disable-pip-version-check 'PyYAML>=6,<7'
cd "$ROOT"
python3 -m unittest discover -s deploy/tests -t . -v
