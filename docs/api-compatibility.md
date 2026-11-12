# API compatibility policy (OM-01.04 AC4)

Frontend and backend are separate artifacts with separate release cadences (AD-14). A deployment
pairs one frontend image with one backend image; this policy says which pairs are supported and how
an unsupported pair is detected before rollout and at runtime.

## Contract version

The backend publishes one **API contract version** `major.minor`:

- source of truth: `backend/src/main/resources/owlmast/api-contract.properties`
  (`apiContract.major`, `apiContract.minor`), read at startup by the `compatibility` feature;
- published at `GET /api/compatibility` (no authentication, no protected content):

```json
{"service":"owl-mast-backend","backendVersion":"0.1.0-SNAPSHOT","apiContract":{"major":1,"minor":0}}
```

Rules for changing it:

| Change | Bump |
| --- | --- |
| Add an endpoint, field, enum value or optional parameter | `minor` + 1 |
| Remove or rename anything, change a type, tighten validation, change an error envelope | `major` + 1, `minor` = 0 |

The frontend declares what it supports in `frontend/api-compatibility.json`:

```json
{"frontendVersion":"0.1.0","supportedApiContract":{"major":1,"minMinor":0},"descriptorPath":"/compatibility"}
```

## Compatibility rule

A pair is **compatible** when `backend.major == frontend.major` and `backend.minor >= frontend.minMinor`.
Any other pair, and any backend that does not answer the descriptor, is **unsupported** (fail closed).

## Where the rule is enforced

| Stage | Mechanism | Evidence |
| --- | --- | --- |
| Build | `scripts/check-api-compatibility.py` (static): compares the checkout's manifest and properties | CI job `frontend`; `deploy/tests/test_api_compatibility.py` |
| Pre-rollout | `scripts/check-api-compatibility.py --frontend-url https://<frontend> --backend-url https://<backend> [--api-path-prefix /api]` against the artifacts being rolled out, before enabling or upgrading either | Exit 1 names both contracts; an unreachable, 404, timed-out or malformed descriptor or manifest also exits 1 with one `INCOMPATIBLE (unverifiable)` line naming the frontend contract when it is known; `deploy/tests/test_api_compatibility.py`, `scripts/verify-frontend-artifact.sh` |
| Runtime | The shell's Daily Work "Workspace connection" panel reads the descriptor and shows Compatible / Incompatible / cannot verify. A downgrade (other major, lower minor, no descriptor) replaces a shown "Compatible" at once. The verdict is displayed only: nothing is gated on it yet, because the shell has no protected feature. The first protected feature must refuse to load unless the verdict is Compatible | `frontend/src/routes/ConnectionPanel.tsx`, `routes.test.tsx`, `e2e/shell/states.spec.ts`, `e2e/smoke/backend.spec.ts` |
| Negative | `scripts/verify-quality-gates.sh` injects an incompatible backend contract and asserts the check fails | Gate `api-compatibility` |

### Which frontend the pre-rollout check judges

The frontend build publishes its manifest next to the shell, and the image serves it at
`GET /api-compatibility.json` (same content as `frontend/api-compatibility.json` at the commit the image
was built from). `--frontend-url` reads that copy, so the check judges the artifact it is pointed at.
Point it at the candidate, not at what is already deployed: the public origin serves the old frontend
until the rollout (and nothing before the first one). Run the candidate image locally
(`docker run --rm -p 127.0.0.1:8081:8080 <image>` and `--frontend-url http://127.0.0.1:8081`) or
port-forward to a canary; use the public origin only to re-check after the rollout. The same applies to
`--backend-url` for a backend that is being upgraded.
Without `--frontend-url` the script reads the manifest of the checkout it runs from: correct for the
build-time check in CI, wrong for a rollout whenever the checkout and the image are at different
commits. An image that does not publish the manifest answers 404 and the check exits 1. An empty
`--frontend-url` or `--backend-url` (an unset pipeline variable) is refused, never read as "use the
checkout".

The manifest path shares the string prefix `/api` with the backend's API path. The chart's routes match
by path segment (`pathType: Prefix`, `PathPrefix`), so `/api-compatibility.json` reaches the frontend. A
router that matches by string prefix would send it to the backend; the check then reports the manifest
as unverifiable (exit 1).

The check is a command an operator or pipeline runs; the chart does not run it as a Helm hook
(a hook would need egress to both artifacts and its own image; not decided in OM-01.04).

Rollout order for a `minor` bump: backend first (it only adds), then frontend. For a `major` bump both
artifacts must be rolled together after the pre-rollout check passes against the new backend.

## Common error envelope

Backend error responses are RFC 9457 problem details (`application/problem+json`): `type`, `title`,
`status`, `instance`. Two mechanisms produce them:

- `spring.webflux.problemdetails.enabled=true` covers Spring's own error responses (unknown path 404,
  405, 415, validation, `ResponseStatusException`); verified by `CompatibilityEndpointIT` and
  `UnhandledFailureIT`.
- `platform/web/UnhandledFailureAdvice` covers an exception that leaves a controller unhandled: status
  500 with no message, class name, cause or trace (the log names the exception classes only); verified by
  `UnhandledFailureIT`.

Not covered:

- A failure raised outside a controller (a web filter, the codec layer before a handler is chosen) still
  gets Spring Boot's default error body, which is `application/json` with `status`, `error`, `path` and
  `requestId` and, by Boot's defaults, no message or trace. No such filter exists yet; the story that adds
  one (authentication, E02) must bring it under the envelope.
- An exception type that should carry its own status. The catch-all answers 500 for everything Spring
  does not already map, so the story that introduces authentication or authorization exceptions (E02)
  must map them to 401/403 in a more specific advice; otherwise the shell would show a problem state
  where it should show the denied state.

Stack traces, exception messages and binding errors are never included. The frontend client
(`frontend/src/api/client.ts`) maps 401/403 to the denied state, 404 to not-found, other failures to a
problem state, and renders only its own safe copy plus the status code; `detail` is never shown. A 2xx
answer that is not a descriptor is reported as unverifiable, never as "status 200".
