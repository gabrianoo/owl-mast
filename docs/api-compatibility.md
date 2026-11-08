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
| Pre-rollout | `scripts/check-api-compatibility.py --backend-url https://<backend> [--api-path-prefix /api]` against the running backend before enabling or upgrading the frontend | Exit 1 names both contracts; unreachable or 404 descriptor also exits 1 |
| Runtime | The shell's Daily Work "Workspace connection" panel reads the descriptor and shows Compatible / Incompatible / cannot verify; protected features stay unavailable on anything but Compatible | `frontend/src/routes/ConnectionPanel.tsx`, `routes.test.tsx`, `e2e/shell/states.spec.ts`, `e2e/smoke/backend.spec.ts` |
| Negative | `scripts/verify-quality-gates.sh` injects an incompatible backend contract and asserts the check fails | Gate `api-compatibility` |

Rollout order for a `minor` bump: backend first (it only adds), then frontend. For a `major` bump both
artifacts must be rolled together after the pre-rollout check passes against the new backend.

## Common error envelope

Every backend error response is an RFC 9457 problem detail (`application/problem+json`;
`spring.webflux.problemdetails.enabled=true`): `type`, `title`, `status`, `instance`. Stack traces,
exception messages and binding errors are never included. The frontend client
(`frontend/src/api/client.ts`) maps 401/403 to the denied state, 404 to not-found, other failures to a
problem state, and renders only its own safe copy plus the status code; `detail` is never shown.
