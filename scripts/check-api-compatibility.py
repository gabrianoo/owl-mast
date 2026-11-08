#!/usr/bin/env python3
"""Pre-rollout API compatibility check (OM-01.04 AC4, docs/api-compatibility.md).

Compares the API contract a frontend artifact supports (frontend/api-compatibility.json) with the
contract a backend publishes, either statically from the backend's api-contract.properties in this
checkout or live from a running backend's GET {prefix}/compatibility. Exit 0 when the pair is
compatible; exit 1 (with both contracts named) when it is not or when the descriptor is unavailable.
"""
from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_FRONTEND_MANIFEST = ROOT / "frontend" / "api-compatibility.json"
DEFAULT_BACKEND_CONTRACT = ROOT / "backend" / "src" / "main" / "resources" / "owlmast" / "api-contract.properties"


@dataclass(frozen=True)
class Contract:
    major: int
    minor: int

    def label(self) -> str:
        return f"{self.major}.{self.minor}"


@dataclass(frozen=True)
class Supported:
    major: int
    min_minor: int

    def label(self) -> str:
        return f"{self.major}.x (at least {self.major}.{self.min_minor})"


class CheckError(Exception):
    """A descriptor or manifest could not be read; treated as incompatible (fail closed)."""


def _non_negative_int(value: object, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise CheckError(f"{name} must be a non-negative integer, got {value!r}")
    return value


def read_frontend_manifest(path: Path) -> tuple[Supported, str, str]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise CheckError(f"cannot read frontend manifest {path}: {error}") from error
    supported = data.get("supportedApiContract")
    if not isinstance(supported, dict):
        raise CheckError(f"{path} lacks supportedApiContract")
    contract = Supported(
        _non_negative_int(supported.get("major"), "supportedApiContract.major"),
        _non_negative_int(supported.get("minMinor"), "supportedApiContract.minMinor"),
    )
    descriptor_path = data.get("descriptorPath", "/compatibility")
    if not isinstance(descriptor_path, str) or not descriptor_path.startswith("/"):
        raise CheckError(f"{path} has an invalid descriptorPath")
    return contract, str(data.get("frontendVersion", "unknown")), descriptor_path


def read_backend_properties(path: Path) -> Contract:
    values: dict[str, str] = {}
    try:
        for line in path.read_text(encoding="utf-8").splitlines():
            stripped = line.strip()
            if not stripped or stripped.startswith(("#", "!")):
                continue
            if "=" not in stripped:
                continue
            key, _, value = stripped.partition("=")
            values[key.strip()] = value.strip()
    except OSError as error:
        raise CheckError(f"cannot read backend contract {path}: {error}") from error
    try:
        return Contract(int(values["apiContract.major"]), int(values["apiContract.minor"]))
    except (KeyError, ValueError) as error:
        raise CheckError(f"{path} must define integer apiContract.major and apiContract.minor") from error


def parse_descriptor(body: bytes, source: str) -> tuple[Contract, str]:
    try:
        data = json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise CheckError(f"{source} did not return a JSON descriptor") from error
    if not isinstance(data, dict) or not isinstance(data.get("apiContract"), dict):
        raise CheckError(f"{source} descriptor lacks apiContract")
    api = data["apiContract"]
    contract = Contract(_non_negative_int(api.get("major"), "apiContract.major"), _non_negative_int(api.get("minor"), "apiContract.minor"))
    return contract, str(data.get("backendVersion", "unknown"))


def fetch_live_descriptor(backend_url: str, api_path_prefix: str, descriptor_path: str, timeout: float) -> tuple[Contract, str]:
    url = backend_url.rstrip("/") + api_path_prefix.rstrip("/") + descriptor_path
    request = urllib.request.Request(url, headers={"Accept": "application/json, application/problem+json"})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:  # noqa: S310 - operator-supplied URL
            if response.status != 200:
                raise CheckError(f"{url} answered {response.status}")
            return parse_descriptor(response.read(), url)
    except urllib.error.HTTPError as error:
        raise CheckError(f"{url} answered {error.code}; the pair cannot be verified") from error
    except urllib.error.URLError as error:
        raise CheckError(f"{url} is unreachable: {error.reason}") from error


def evaluate(backend: Contract, supported: Supported) -> tuple[bool, str]:
    if backend.major != supported.major:
        return False, f"INCOMPATIBLE: frontend supports API contract {supported.label()}; backend publishes {backend.label()} (different major)"
    if backend.minor < supported.min_minor:
        return False, f"INCOMPATIBLE: frontend needs at least API contract {supported.major}.{supported.min_minor}; backend publishes {backend.label()}"
    return True, f"COMPATIBLE: backend API contract {backend.label()} satisfies frontend requirement {supported.label()}"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--frontend-manifest", type=Path, default=DEFAULT_FRONTEND_MANIFEST)
    parser.add_argument("--backend-contract", type=Path, default=DEFAULT_BACKEND_CONTRACT, help="api-contract.properties of the backend build (static check)")
    parser.add_argument("--backend-url", help="base URL of a running backend; checks its live descriptor instead of the properties file")
    parser.add_argument("--api-path-prefix", default="/api", help="routing.apiPathPrefix the backend is served under (default /api)")
    parser.add_argument("--timeout", type=float, default=10.0)
    args = parser.parse_args(argv)

    try:
        supported, frontend_version, descriptor_path = read_frontend_manifest(args.frontend_manifest)
        if args.backend_url:
            backend, backend_version = fetch_live_descriptor(args.backend_url, args.api_path_prefix, descriptor_path, args.timeout)
            source = args.backend_url
        else:
            backend = read_backend_properties(args.backend_contract)
            backend_version = "checkout"
            source = str(args.backend_contract)
    except CheckError as error:
        print(f"INCOMPATIBLE (unverifiable): {error}", file=sys.stderr)
        return 1

    ok, verdict = evaluate(backend, supported)
    print(f"{verdict} [frontend {frontend_version}, backend {backend_version} from {source}]")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
