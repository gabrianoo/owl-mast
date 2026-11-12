#!/usr/bin/env python3
"""Pre-rollout API compatibility check (OM-01.04 AC4, docs/api-compatibility.md).

Compares the API contract a frontend artifact supports with the contract a backend publishes.

Frontend side: frontend/api-compatibility.json in this checkout (build-time check), or, with
--frontend-url, the copy the deployed frontend artifact publishes at /api-compatibility.json. Use
--frontend-url before a rollout: a checkout at another commit than the image says nothing about it.
Backend side: the backend's api-contract.properties in this checkout, or, with --backend-url, a
running backend's GET {prefix}/compatibility.

Credentials (opt-in): an endpoint that needs them gets one Authorization header value per side,
from the environment (OWLMAST_COMPAT_FRONTEND_AUTHORIZATION, OWLMAST_COMPAT_BACKEND_AUTHORIZATION)
or from a file (--frontend-authorization-file, --backend-authorization-file). The value is never
taken from the command line or a URL and never printed.

Exit 0 when the pair is compatible; exit 1 (with both contracts named) when it is not, and exit 1
with one "INCOMPATIBLE (unverifiable)" line when either side cannot be read (fail closed). The
script never ends in a traceback: automation parses the verdict line.
"""
from __future__ import annotations

import argparse
import http.client
import ipaddress
import json
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_FRONTEND_MANIFEST = ROOT / "frontend" / "api-compatibility.json"
DEFAULT_BACKEND_CONTRACT = ROOT / "backend" / "src" / "main" / "resources" / "owlmast" / "api-contract.properties"
FRONTEND_MANIFEST_PATH = "/api-compatibility.json"
# A descriptor or manifest is a few hundred bytes; anything larger is not one.
MAX_BODY_BYTES = 1024 * 1024
MAX_TIMEOUT_SECONDS = 3600.0
MAX_VERDICT_CHARS = 2000
# The chart caps routing.apiPathPrefix at the same length.
MAX_PATH_CHARS = 1024
# Credentials are opt-in and per side, so a backend token is never sent to the frontend host or
# the other way round. They are read from the environment or a file only: a command line is
# visible in the process list and in CI logs, and a URL is printed in the verdict.
AUTHORIZATION_ENV = {"frontend": "OWLMAST_COMPAT_FRONTEND_AUTHORIZATION", "backend": "OWLMAST_COMPAT_BACKEND_AUTHORIZATION"}
MAX_AUTHORIZATION_CHARS = 8192


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
    try:
        text = str(value)
    except RecursionError:  # a remote value nested deeper than str() can walk
        return "unknown"
    return _printable(" ".join(text.split())[:80]) or "unknown"


def _printable(text: str) -> str:
    """Every character a terminal or log viewer could act on (ESC, NUL, C1, bidi overrides) becomes '?'."""
    return "".join(character if character.isprintable() else "?" for character in text)


def _shown(value: object) -> str:
    """A rejected value for the verdict line: its repr (control characters escaped), one line, bounded."""
    try:
        text = repr(value)
    except RecursionError:  # a remote value nested deeper than repr() can walk
        text = "<deeply nested value>"
    return _one_line(text)


def _verdict_line(text: str) -> str:
    """The line automation parses: exactly one line of printable text, whatever a path or remote answer put into it."""
    return _printable(" ".join(text.split())[:MAX_VERDICT_CHARS])


def _load_json(text: str, source: object, what: str) -> object:
    try:
        return json.loads(text)
    except (ValueError, RecursionError) as error:  # RecursionError: deeply nested input
        raise CheckError(f"{what} {source} is not JSON: {type(error).__name__}") from error


def _non_negative_int(value: object, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise CheckError(f"{name} must be a non-negative integer, got {_shown(value)}")
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
    # Remote text that becomes part of the backend URL: one absolute path of unreserved characters
    # (the shell appends the same value to its API prefix), so it cannot carry a line break, a
    # query, another origin or a dot segment into the request or the verdict.
    if not isinstance(descriptor_path, str) or not _is_plain_path(descriptor_path):
        raise CheckError(f"{source} has an invalid descriptorPath: {_shown(descriptor_path)}")
    return contract, _one_line(data.get("frontendVersion", "unknown")), descriptor_path


_PLAIN_PATH = re.compile(r"(?:/[A-Za-z0-9._~-]+)+")


def _is_plain_path(value: str) -> bool:
    """'/segment[/segment...]' of unreserved characters: no empty, '.' or '..' segment, no trailing slash, bounded."""
    if len(value) > MAX_PATH_CHARS or _PLAIN_PATH.fullmatch(value) is None:
        return False
    return not any(segment in (".", "..") for segment in value.split("/"))


def read_frontend_manifest(path: Path) -> tuple[Supported, str, str]:
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, ValueError) as error:  # ValueError: UnicodeDecodeError (not UTF-8)
        raise CheckError(f"cannot read frontend manifest {path}: {error}") from error
    return parse_frontend_manifest(text, path)


def fetch_frontend_manifest(frontend_url: str, timeout: float, authorization: str | None = None) -> tuple[Supported, str, str]:
    """The manifest the deployed frontend artifact publishes (emitted by its build, served by its image)."""
    url = _base_url(frontend_url, "--frontend-url") + FRONTEND_MANIFEST_PATH
    if authorization is not None:
        _credentials_allowed(url, "--frontend-url")
    body = _http_get(url, timeout, "application/json", authorization)
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
        _unescape(match.group("value"), source)  # Java refuses the whole file on a malformed \\uXXXX in a value too
        values[_unescape(match.group("key"), source)] = match.group("value")
    return values


_ESCAPE = re.compile(r"\\(u[0-9A-Fa-f]{4}|.)", re.DOTALL)
_ESCAPED_CHARACTERS = {"t": "\t", "n": "\n", "r": "\r", "f": "\f"}


def _unescape(raw: str, source: object) -> str:
    """Escapes as Properties.load decodes them: \\uXXXX, \\t \\n \\r \\f, and \\x -> x for any other x.

    A key written with escapes is the same key to Java (apiContract.m\\u0061jor is apiContract.major)
    and so must be the same key here. Java throws on a malformed \\u sequence, in a key or a value,
    and the backend then loads nothing; this check refuses the file. Values are otherwise used as
    written: a contract number spelled with an escape is refused by the decimal check.
    """

    def decode(match: re.Match[str]) -> str:
        escaped = match.group(1)
        if len(escaped) == 5:
            return chr(int(escaped[1:], 16))
        if escaped == "u":
            raise CheckError(f"{source} has a malformed \\uXXXX escape")
        return _ESCAPED_CHARACTERS.get(escaped, escaped)

    return _ESCAPE.sub(decode, raw)


def _contract_number(values: dict[str, str], key: str, path: Path) -> int:
    value = values.get(key)
    if value is None:
        raise CheckError(f"{path} must define {key}")
    # The backend trims and uses Integer.parseInt; only plain ASCII decimals mean the same to both.
    trimmed = value.strip(_JAVA_TRIM)
    if not _DECIMAL.fullmatch(trimmed) or int(trimmed) > 2**31 - 1:
        raise CheckError(f"{path} must define {key} as a plain non-negative decimal integer, got {_shown(value)}")
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
    """An http(s) base URL with a host; anything else would make urllib raise instead of a verdict.

    A refused value is never repeated in the message: it is the one input that can hold a secret
    (user:token@host, ?access_token=...), and the verdict line ends up in CI logs.
    """
    if "@" in value:
        # Refused before anything else: an accepted URL is printed in every verdict line.
        raise CheckError(f"invalid {option}: credentials in the URL are not accepted (the value contains '@' and is not repeated here)")
    if any(not 0x21 <= ord(character) <= 0x7E for character in value):
        raise CheckError(f"invalid {option}: whitespace, a control character or a non-ASCII character in the URL")
    try:
        parts = urllib.parse.urlsplit(value)
        host = parts.hostname
        _ = parts.port  # raises ValueError for a non-numeric or out-of-range port
    except ValueError as error:
        raise CheckError(f"invalid {option}: {type(error).__name__} (malformed host or port)") from error
    if parts.scheme not in ("http", "https") or not host:
        raise CheckError(f"invalid {option}: expected http://host[:port] or https://host[:port]")
    if parts.query or parts.fragment or "?" in value or "#" in value:
        raise CheckError(f"invalid {option}: a base URL has no query or fragment (the value is not repeated here)")
    return value.rstrip("/")


def read_authorization(side: str, file: Path | None, url_given: bool, environ: Mapping[str, str]) -> str | None:
    """The Authorization header value for one side's request, or None when none is configured.

    No message here repeats the value or any part of it: it is a secret. The environment variable
    is ignored when it is empty (an unset pipeline secret) or when that side is read from the
    checkout; a file given for a side that is read from the checkout is a mistake.
    """
    option = f"--{side}-authorization-file"
    variable = AUTHORIZATION_ENV[side]
    from_environment = environ.get(variable) or None
    if file is not None:
        if not url_given:
            raise CheckError(f"{option} needs --{side}-url: credentials are sent to a URL only")
        if from_environment is not None:
            raise CheckError(f"{option} and {variable} are both set: choose one source for the {side} credentials")
        try:
            with file.open("rb") as handle:  # bounded: the path may be a device or a very large file
                raw = handle.read(MAX_AUTHORIZATION_CHARS + 3)
        except OSError as error:
            raise CheckError(f"cannot read {option}: {type(error).__name__}") from None
        if len(raw) > MAX_AUTHORIZATION_CHARS + 2:
            raise CheckError(f"invalid {option}: more than {MAX_AUTHORIZATION_CHARS} characters (the value is not repeated here)")
        try:
            value = raw.decode("ascii")
        except UnicodeDecodeError:
            raise CheckError(f"invalid {option}: not printable ASCII (the value is not repeated here)") from None
        # One line end, as an editor or `echo` leaves it; anything else in the file is part of the value.
        value = value[:-2] if value.endswith("\r\n") else value[:-1] if value.endswith("\n") else value
        source = option
    elif from_environment is not None and url_given:
        value, source = from_environment, variable
    else:
        return None
    # One header line of visible ASCII: no line break (a second header), no control character.
    if not value or len(value) > MAX_AUTHORIZATION_CHARS or value != value.strip(" ") or any(not 0x20 <= ord(character) <= 0x7E for character in value):
        raise CheckError(
            f"invalid {source}: expected one line of printable ASCII such as 'Bearer <token>', at most {MAX_AUTHORIZATION_CHARS} characters, "
            "without leading or trailing spaces (the value is not repeated here)"
        )
    return value


def _is_loopback(host: str) -> bool:
    if host.lower() == "localhost":
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


def _credentials_allowed(url: str, option: str) -> None:
    """Credentials leave this machine only over TLS; plain http is accepted for a loopback address (a port-forward)."""
    parts = urllib.parse.urlsplit(url)
    if parts.scheme != "https" and not _is_loopback(parts.hostname or ""):
        raise CheckError(f"{option} is plain http to a host that is not this machine: credentials are sent over https or to a loopback address only")


def _opener_with_credentials(url: str) -> urllib.request.OpenerDirector:
    """No redirects; and no proxy for plain http, which is a loopback address here.

    urllib takes proxies from the environment (http_proxy) and on Linux does not exempt
    localhost, so the plain request and its Authorization header would go to the proxy host. An
    https request keeps the configured proxy: it only relays the encrypted connection.
    """
    handlers: list[urllib.request.BaseHandler] = [_NoRedirect()]
    if urllib.parse.urlsplit(url).scheme != "https":
        handlers.append(urllib.request.ProxyHandler({}))
    return urllib.request.build_opener(*handlers)


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    """With credentials a redirect is not followed: urllib would repeat the Authorization header to the new host."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):  # noqa: ANN001, ARG002 - urllib API
        return None


def _http_get(url: str, timeout: float, accept: str, authorization: str | None = None) -> bytes:
    """GET that turns every transport failure into CheckError (timeout, reset, truncated body, bad URL).

    `authorization` is sent as the Authorization header of this request only; it is never part of
    a message.
    """
    try:
        request = urllib.request.Request(url, headers={"Accept": accept})
        if authorization is None:
            opener = urllib.request.build_opener()
        else:
            request.add_unredirected_header("Authorization", authorization)
            opener = _opener_with_credentials(url)
        with opener.open(request, timeout=timeout) as response:  # noqa: S310 - operator-supplied URL
            if response.status != 200:
                raise CheckError(f"{url} answered {response.status}; the pair cannot be verified")
            body = response.read(MAX_BODY_BYTES + 1)
            if len(body) > MAX_BODY_BYTES:
                raise CheckError(f"{url} answered with more than {MAX_BODY_BYTES} bytes; the pair cannot be verified")
            return body
    except urllib.error.HTTPError as error:
        error.close()  # the error object owns the response socket
        if authorization is not None and 300 <= error.code < 400:
            raise CheckError(f"{url} answered {error.code}; a redirect is not followed when credentials are sent") from None
        raise CheckError(f"{url} answered {error.code}; the pair cannot be verified") from None
    except urllib.error.URLError as error:
        raise CheckError(f"{url} is unreachable: {error.reason}") from error
    except TimeoutError as error:
        raise CheckError(f"{url} did not answer within {timeout:g}s") from error
    except (OSError, http.client.HTTPException) as error:
        raise CheckError(f"{url} failed mid-answer: {type(error).__name__}") from error
    except ValueError as error:
        if authorization is not None:  # http.client quotes a header it refuses
            raise CheckError(f"invalid URL or header for {_shown(url)}: {type(error).__name__}") from None
        raise CheckError(f"invalid URL {_shown(url)}: {error}") from error


def fetch_live_descriptor(
    backend_url: str, api_path_prefix: str, descriptor_path: str, timeout: float, authorization: str | None = None
) -> tuple[Contract, str]:
    # Appended to the base URL as written: without the leading slash it would extend the host name,
    # and a query, dot segment or control character would change which resource is asked. Same
    # rule as the shell and the image apply to the prefix; "/" alone is a backend served at the root.
    prefix = api_path_prefix[:-1] if api_path_prefix.endswith("/") else api_path_prefix
    if not api_path_prefix.startswith("/") or (prefix and not _is_plain_path(prefix)):
        raise CheckError(f"invalid --api-path-prefix {_shown(api_path_prefix)}: expected an absolute path such as /api")
    url = _base_url(backend_url, "--backend-url") + prefix + descriptor_path
    if authorization is not None:
        _credentials_allowed(url, "--backend-url")
    return parse_descriptor(_http_get(url, timeout, "application/json, application/problem+json", authorization), url)


def evaluate(backend: Contract, supported: Supported) -> tuple[bool, str]:
    if backend.major != supported.major:
        return False, f"INCOMPATIBLE: frontend supports API contract {supported.label()}; backend publishes {backend.label()} (different major)"
    if backend.minor < supported.min_minor:
        return False, f"INCOMPATIBLE: frontend needs at least API contract {supported.major}.{supported.min_minor}; backend publishes {backend.label()}"
    return True, f"COMPATIBLE: backend API contract {backend.label()} satisfies frontend requirement {supported.label()}"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--frontend-manifest", type=Path, default=DEFAULT_FRONTEND_MANIFEST, help="manifest file of the frontend build (default: this checkout)")
    parser.add_argument("--frontend-url", help=f"base URL of a deployed frontend; reads the manifest it publishes at {FRONTEND_MANIFEST_PATH} instead of the file")
    parser.add_argument("--backend-contract", type=Path, default=DEFAULT_BACKEND_CONTRACT, help="api-contract.properties of the backend build (static check)")
    parser.add_argument("--backend-url", help="base URL of a running backend; checks its live descriptor instead of the properties file")
    parser.add_argument("--api-path-prefix", default="/api", help="routing.apiPathPrefix the backend is served under (default /api)")
    parser.add_argument("--timeout", type=float, default=10.0)
    for side in ("frontend", "backend"):
        parser.add_argument(
            f"--{side}-authorization-file",
            type=Path,
            help=f"file holding the Authorization header value for --{side}-url (for example 'Bearer <token>'); "
            f"or set {AUTHORIZATION_ENV[side]}. The value itself is never an argument",
        )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    # Named in the unverifiable verdict once known, so the line always says what the frontend needs.
    frontend = "frontend contract unknown"
    try:
        # An empty URL is a mistake (an unset pipeline variable), never "use the checkout instead".
        for option, value in (("--frontend-url", args.frontend_url), ("--backend-url", args.backend_url)):
            if value is not None and not value.strip():
                raise CheckError(f"invalid {option} {_shown(value)}: empty")
        if not 0 < args.timeout <= MAX_TIMEOUT_SECONDS:  # also false for nan
            raise CheckError(f"invalid --timeout {args.timeout!r}: expected seconds in (0, {MAX_TIMEOUT_SECONDS:g}]")
        frontend_authorization = read_authorization("frontend", args.frontend_authorization_file, bool(args.frontend_url), os.environ)
        backend_authorization = read_authorization("backend", args.backend_authorization_file, bool(args.backend_url), os.environ)
        # Both sides are judged before the first request, so a refusal for one never follows a
        # request that already carried the other's credentials.
        for option, value, authorization in (("--frontend-url", args.frontend_url, frontend_authorization), ("--backend-url", args.backend_url, backend_authorization)):
            if authorization is not None:
                _credentials_allowed(_base_url(value, option), option)
        if args.frontend_url:
            supported, frontend_version, descriptor_path = fetch_frontend_manifest(args.frontend_url, args.timeout, frontend_authorization)
            frontend_source = args.frontend_url
        else:
            supported, frontend_version, descriptor_path = read_frontend_manifest(args.frontend_manifest)
            frontend_source = str(args.frontend_manifest)
        frontend = f"frontend {frontend_version} supports API contract {supported.label()}, from {frontend_source}"
        if args.backend_url:
            backend, backend_version = fetch_live_descriptor(args.backend_url, args.api_path_prefix, descriptor_path, args.timeout, backend_authorization)
            source = args.backend_url
        else:
            backend = read_backend_properties(args.backend_contract)
            backend_version = "checkout"
            source = str(args.backend_contract)
    except CheckError as error:
        print(_verdict_line(f"INCOMPATIBLE (unverifiable): {error} [{frontend}; backend contract unknown]"), file=sys.stderr)
        return 1

    ok, verdict = evaluate(backend, supported)
    print(_verdict_line(f"{verdict} [frontend {frontend_version} from {frontend_source}, backend {backend_version} from {source}]"))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
