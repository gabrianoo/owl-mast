#!/usr/bin/env python3
"""Pre-rollout API compatibility check (OM-01.04 AC4, docs/api-compatibility.md).

Compares the API contract a frontend artifact supports with the contract a backend publishes.

Frontend side: frontend/api-compatibility.json in this checkout (build-time check), or, with
--frontend-url, the copy the deployed frontend artifact publishes at /api-compatibility.json. Use
--frontend-url before a rollout: a checkout at another commit than the image says nothing about it.
Backend side: the backend's api-contract.properties in this checkout, or, with --backend-url, a
running backend's GET {prefix}/compatibility.

Exit 0 when the pair is compatible; exit 1 (with both contracts named) when it is not, and exit 1
with one "INCOMPATIBLE (unverifiable)" line when either side cannot be read (fail closed). The
script never ends in a traceback: automation parses the verdict line.
"""
from __future__ import annotations

import argparse
import http.client
import json
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_FRONTEND_MANIFEST = ROOT / "frontend" / "api-compatibility.json"
DEFAULT_BACKEND_CONTRACT = ROOT / "backend" / "src" / "main" / "resources" / "owlmast" / "api-contract.properties"
FRONTEND_MANIFEST_PATH = "/api-compatibility.json"
# A descriptor or manifest is a few hundred bytes; anything larger is not one.
MAX_BODY_BYTES = 1024 * 1024
MAX_TIMEOUT_SECONDS = 3600.0


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


def _one_line(value: object) -> str:
    """Remote text for the verdict line: whitespace runs (newlines included) become one space, bounded."""
    return " ".join(str(value).split())[:80] or "unknown"


def _load_json(text: str, source: object, what: str) -> object:
    try:
        return json.loads(text)
    except (ValueError, RecursionError) as error:  # RecursionError: deeply nested input
        raise CheckError(f"{what} {source} is not JSON: {type(error).__name__}") from error


def _non_negative_int(value: object, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise CheckError(f"{name} must be a non-negative integer, got {value!r}")
    return value


def parse_frontend_manifest(text: str, source: object) -> tuple[Supported, str, str]:
    data = _load_json(text, source, "frontend manifest")
    if not isinstance(data, dict):
        raise CheckError(f"frontend manifest {source} must be a JSON object")
    supported = data.get("supportedApiContract")
    if not isinstance(supported, dict):
        raise CheckError(f"{source} lacks supportedApiContract")
    contract = Supported(
        _non_negative_int(supported.get("major"), "supportedApiContract.major"),
        _non_negative_int(supported.get("minMinor"), "supportedApiContract.minMinor"),
    )
    descriptor_path = data.get("descriptorPath", "/compatibility")
    if not isinstance(descriptor_path, str) or not descriptor_path.startswith("/"):
        raise CheckError(f"{source} has an invalid descriptorPath")
    return contract, _one_line(data.get("frontendVersion", "unknown")), descriptor_path


def read_frontend_manifest(path: Path) -> tuple[Supported, str, str]:
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, ValueError) as error:  # ValueError: UnicodeDecodeError (not UTF-8)
        raise CheckError(f"cannot read frontend manifest {path}: {error}") from error
    return parse_frontend_manifest(text, path)


def fetch_frontend_manifest(frontend_url: str, timeout: float) -> tuple[Supported, str, str]:
    """The manifest the deployed frontend artifact publishes (emitted by its build, served by its image)."""
    url = _base_url(frontend_url, "--frontend-url") + FRONTEND_MANIFEST_PATH
    body = _http_get(url, timeout, "application/json")
    try:
        text = body.decode("utf-8")
    except UnicodeDecodeError as error:
        raise CheckError(f"{url} did not return a UTF-8 manifest") from error
    return parse_frontend_manifest(text, url)


_PROPERTY_LINE = re.compile(r"^[ \t\f]*(?P<key>(?:\\.|[^\\=: \t\f])*)[ \t\f]*[=:]?[ \t\f]*(?P<value>.*)$", re.DOTALL)
_PROPERTY_LINE_END = re.compile(r"\r\n|\n|\r")
_CONTINUED = re.compile(r"(?<!\\)(?:\\\\)*\\$")
_DECIMAL = re.compile(r"[0-9]{1,10}")
# What String.trim() removes: every character up to U+0020, and nothing else (not U+00A0).
_JAVA_TRIM = "".join(chr(code) for code in range(0x21))


def parse_properties(text: str, source: object = "properties") -> dict[str, str]:
    """Key/value lines as java.util.Properties.load reads them (the backend's own loader).

    Lines end at \\n, \\r or \\r\\n only; the key ends at the first unescaped '=', ':' or
    whitespace; '#' and '!' start comments; later keys win. A line continuation (a line ending in
    an odd number of backslashes) is refused rather than interpreted: the contract file needs none,
    and a half-implemented join could read a different number than the backend loads.
    """
    values: dict[str, str] = {}
    for line in _PROPERTY_LINE_END.split(text):
        stripped = line.lstrip(" \t\f")
        if not stripped or stripped.startswith(("#", "!")):
            continue
        if _CONTINUED.search(line):
            raise CheckError(f"{source} uses a line continuation, which this check does not interpret")
        match = _PROPERTY_LINE.match(line)
        if match is None or not match.group("key"):
            continue
        key = re.sub(r"\\(.)", r"\1", match.group("key"))
        values[key] = match.group("value")
    return values


def _contract_number(values: dict[str, str], key: str, path: Path) -> int:
    value = values.get(key)
    if value is None:
        raise CheckError(f"{path} must define {key}")
    # The backend trims and uses Integer.parseInt; only plain ASCII decimals mean the same to both.
    trimmed = value.strip(_JAVA_TRIM)
    if not _DECIMAL.fullmatch(trimmed) or int(trimmed) > 2**31 - 1:
        raise CheckError(f"{path} must define {key} as a plain non-negative decimal integer, got {value!r}")
    return int(trimmed)


def read_backend_properties(path: Path) -> Contract:
    try:
        # java.util.Properties.load(InputStream) reads ISO-8859-1; every byte sequence decodes.
        values = parse_properties(path.read_bytes().decode("iso-8859-1"), path)
    except OSError as error:
        raise CheckError(f"cannot read backend contract {path}: {error}") from error
    return Contract(_contract_number(values, "apiContract.major", path), _contract_number(values, "apiContract.minor", path))


def parse_descriptor(body: bytes, source: str) -> tuple[Contract, str]:
    try:
        text = body.decode("utf-8")
    except UnicodeDecodeError as error:
        raise CheckError(f"{source} did not return a JSON descriptor") from error
    data = _load_json(text, source, "descriptor from")
    if not isinstance(data, dict) or not isinstance(data.get("apiContract"), dict):
        raise CheckError(f"{source} descriptor lacks apiContract")
    api = data["apiContract"]
    contract = Contract(_non_negative_int(api.get("major"), "apiContract.major"), _non_negative_int(api.get("minor"), "apiContract.minor"))
    return contract, _one_line(data.get("backendVersion", "unknown"))


def _base_url(value: str, option: str) -> str:
    """An http(s) base URL with a host; anything else would make urllib raise instead of a verdict."""
    try:
        parts = urllib.parse.urlsplit(value)
        host = parts.hostname
        _ = parts.port  # raises ValueError for a non-numeric or out-of-range port
    except ValueError as error:
        raise CheckError(f"invalid {option} {value!r}: {error}") from error
    if parts.scheme not in ("http", "https") or not host:
        raise CheckError(f"invalid {option} {value!r}: expected http://host[:port] or https://host[:port]")
    if parts.query or parts.fragment or "?" in value or "#" in value:
        raise CheckError(f"invalid {option} {value!r}: a base URL has no query or fragment")
    return value.rstrip("/")


def _http_get(url: str, timeout: float, accept: str) -> bytes:
    """GET that turns every transport failure into CheckError (timeout, reset, truncated body, bad URL)."""
    try:
        request = urllib.request.Request(url, headers={"Accept": accept})
        with urllib.request.urlopen(request, timeout=timeout) as response:  # noqa: S310 - operator-supplied URL
            if response.status != 200:
                raise CheckError(f"{url} answered {response.status}; the pair cannot be verified")
            body = response.read(MAX_BODY_BYTES + 1)
            if len(body) > MAX_BODY_BYTES:
                raise CheckError(f"{url} answered with more than {MAX_BODY_BYTES} bytes; the pair cannot be verified")
            return body
    except urllib.error.HTTPError as error:
        error.close()  # the error object owns the response socket
        raise CheckError(f"{url} answered {error.code}; the pair cannot be verified") from None
    except urllib.error.URLError as error:
        raise CheckError(f"{url} is unreachable: {error.reason}") from error
    except TimeoutError as error:
        raise CheckError(f"{url} did not answer within {timeout:g}s") from error
    except (OSError, http.client.HTTPException) as error:
        raise CheckError(f"{url} failed mid-answer: {type(error).__name__}") from error
    except ValueError as error:
        raise CheckError(f"invalid URL {url!r}: {error}") from error


def fetch_live_descriptor(backend_url: str, api_path_prefix: str, descriptor_path: str, timeout: float) -> tuple[Contract, str]:
    if not api_path_prefix.startswith("/"):
        # Appended to the base URL as written: without the slash it would extend the host name.
        raise CheckError(f"invalid --api-path-prefix {api_path_prefix!r}: it must start with '/'")
    url = _base_url(backend_url, "--backend-url") + api_path_prefix.rstrip("/") + descriptor_path
    return parse_descriptor(_http_get(url, timeout, "application/json, application/problem+json"), url)


def evaluate(backend: Contract, supported: Supported) -> tuple[bool, str]:
    if backend.major != supported.major:
        return False, f"INCOMPATIBLE: frontend supports API contract {supported.label()}; backend publishes {backend.label()} (different major)"
    if backend.minor < supported.min_minor:
        return False, f"INCOMPATIBLE: frontend needs at least API contract {supported.major}.{supported.min_minor}; backend publishes {backend.label()}"
    return True, f"COMPATIBLE: backend API contract {backend.label()} satisfies frontend requirement {supported.label()}"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--frontend-manifest", type=Path, default=DEFAULT_FRONTEND_MANIFEST, help="manifest file of the frontend build (default: this checkout)")
    parser.add_argument("--frontend-url", help=f"base URL of a deployed frontend; reads the manifest it publishes at {FRONTEND_MANIFEST_PATH} instead of the file")
    parser.add_argument("--backend-contract", type=Path, default=DEFAULT_BACKEND_CONTRACT, help="api-contract.properties of the backend build (static check)")
    parser.add_argument("--backend-url", help="base URL of a running backend; checks its live descriptor instead of the properties file")
    parser.add_argument("--api-path-prefix", default="/api", help="routing.apiPathPrefix the backend is served under (default /api)")
    parser.add_argument("--timeout", type=float, default=10.0)
    args = parser.parse_args(argv)

    # Named in the unverifiable verdict once known, so the line always says what the frontend needs.
    frontend = "frontend contract unknown"
    try:
        # An empty URL is a mistake (an unset pipeline variable), never "use the checkout instead".
        for option, value in (("--frontend-url", args.frontend_url), ("--backend-url", args.backend_url)):
            if value is not None and not value.strip():
                raise CheckError(f"invalid {option} {value!r}: empty")
        if not 0 < args.timeout <= MAX_TIMEOUT_SECONDS:  # also false for nan
            raise CheckError(f"invalid --timeout {args.timeout!r}: expected seconds in (0, {MAX_TIMEOUT_SECONDS:g}]")
        if args.frontend_url:
            supported, frontend_version, descriptor_path = fetch_frontend_manifest(args.frontend_url, args.timeout)
            frontend_source = args.frontend_url
        else:
            supported, frontend_version, descriptor_path = read_frontend_manifest(args.frontend_manifest)
            frontend_source = str(args.frontend_manifest)
        frontend = f"frontend {frontend_version} supports API contract {supported.label()}, from {frontend_source}"
        if args.backend_url:
            backend, backend_version = fetch_live_descriptor(args.backend_url, args.api_path_prefix, descriptor_path, args.timeout)
            source = args.backend_url
        else:
            backend = read_backend_properties(args.backend_contract)
            backend_version = "checkout"
            source = str(args.backend_contract)
    except CheckError as error:
        print(f"INCOMPATIBLE (unverifiable): {error} [{frontend}; backend contract unknown]", file=sys.stderr)
        return 1

    ok, verdict = evaluate(backend, supported)
    print(f"{verdict} [frontend {frontend_version} from {frontend_source}, backend {backend_version} from {source}]")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
