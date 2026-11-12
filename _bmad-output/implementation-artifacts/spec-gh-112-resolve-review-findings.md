---
title: 'PR #112 post-merge review 5876022641 — resolve the 31 findings (OM-01.04)'
type: 'bugfix'
created: '2026-11-12'
status: 'done'
route: 'dispatch'
review_loop_iteration: 0
baseline_commit: '11005d49d26d2ef209041973b481fcededc6c64f'
context:
  - '{project-root}/_bmad-output/implementation-artifacts/spec-om-01-04-open-an-accessible-workspace-shell.md'
  - '{project-root}/docs/api-compatibility.md'
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** PR #112 (OM-01.04, issue #23, merged as 137e084) received a post-merge COMMENT review (5876022641) with 31 inline findings: the shell keeps a stale "Compatible" verdict, pins error/offline answers, moves focus on background denials, documents a gate and a `protected` option that do not exist; the pre-rollout check crashes instead of failing closed; the image and several AC2/AC4 paths are unverified.

**Approach:** Verify every finding against main, fix each real one with a test where the behaviour is testable, decline (with a written reason) what is wrong, already fixed on main or out of scope, and ship one PR against main that refs #23 and answers every thread.

**Owner pre-approval (2026-11-12, run brief):** checkpoints continue to implementation; push, PR and thread replies/resolution are required; no merge, no change to issue #23 or the board.

## Boundaries & Constraints

**Always:** Keep AC1–AC4 of OM-01.04 and its frozen matrix; fail closed on every unverifiable pair; safe copy only (no backend detail, exception text or requested address rendered); frontend and backend stay separate artifacts; CI Ubuntu runners stay `ubuntu-26.04`; executable bits via `git update-index --chmod=+x`.

**Never:** Implement authentication, protected features or a runtime feature gate (no protected feature exists yet); add a path rewrite to the chart; change pins or the lockfile; merge; touch issue #23, the project board or the shared checkout.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| Verdict downgrade | "Compatible" shown; re-check answers other major, lower minor or 404 | Replaced at once, no user action | Later answers issued before it never restore the view |
| Non-content shown | shown answer is error, offline or not-found; next check differs | Replaces it directly (no "New updates") | — |
| Offline probe | probe `offline` while the browser still reports online | Offline state message in the panel | Next answer replaces it |
| Denial | 401/403 on first paint or a background re-check | Content removed, neutral heading, working return link; focus moves to the heading only when the removal dropped the user's focus | Polite live region announces otherwise |
| Client offline | `protected: true` while offline / `protected: false` while offline | Refused before the network / attempted with `no-store` | Failed fetch → `offline` or `error` |
| Prefix | `//host`, `/a/../b`, `/a/./b`, `/a/..` | Client falls back to `/api`; image refuses to start on a prefix outside `^/[A-Za-z0-9._~/-]*$` or with those segments | Diagnostic names the variable |
| Misroute | request under the image's API prefix reaches the frontend image | 404 (shell: "no descriptor"), never `index.html` | 2xx non-descriptor body → "not a valid descriptor" copy, no "status 200" |
| Pre-rollout check | non-object / non-UTF-8 manifest, timeout, reset, truncated body, URL without http(s) scheme, `:`/whitespace property separators, non-digit version | One-line `INCOMPATIBLE (unverifiable)` naming the frontend contract when known; exit 1 | Never a traceback |
| Deployed manifest | `--frontend-url <shell>` | Reads `<shell>/api-compatibility.json` published by the build | Missing/HTML answer → unverifiable, exit 1 |
| ActionButton | action throws / `type=submit` clicked while pending | Fixed safe failure text (or caller `failureMessage`) / no second submit | Thrown text never rendered |
| Compact menu | Escape, or activating the current page's link | Menu closes; Escape returns focus to the toggle | — |
| Backend 5xx | unhandled exception in a controller | `application/problem+json`, status 500, no `trace`/`message`/`exception` | Logged with `SafeFailure` only |

</frozen-after-approval>

## Code Map

- `frontend/src/primitives/useRevalidatingResource.ts` -- `runLoad` decides replace/confirm/pend; add `retains(shown)` (F11). `invalidates` already raises the floor.
- `frontend/src/routes/ConnectionPanel.tsx` -- `invalidatesView`, `ProbeView` (F1, F10, F11, F12, F20 copy, F27). Return target: `HOME` from `app/destinations.ts`, `Link` from `app/router.tsx`.
- `frontend/src/api/{client,config}.ts` -- offline guard (F13), `PREFIX_PATTERN` (F14).
- `frontend/src/primitives/{ActionButton,SettingsField}.tsx`, `routes/Preferences.tsx`, `app/shell/PrimaryNavigation.tsx` -- F21, F22, F24, F25, F26.
- `frontend/public/theme-boot.js` vs `theme/themePreference.ts` `THEME_STORAGE_KEY` (F30).
- `frontend/vite.config.ts`, `Dockerfile`, `nginx/default.conf.template` -- build output and image (F4, F15, F20); `nginx-unprivileged` runs executable `/docker-entrypoint.d/*.sh` before envsubst.
- `frontend/e2e/shell/*`, `playwright*.config.ts` -- vite preview has no CSP and no `/owlmast-config.json` (F16, F17, F29, F30, F31).
- `scripts/check-api-compatibility.py`, `deploy/tests/test_api_compatibility.py` (F4–F9); `scripts/verify-quality-gates.sh:150` (F18); `scripts/verify-frontend-artifact.sh` (F15, F16, F20); `.github/workflows/ci.yml` job `frontend-backend-smoke`.
- `backend/.../compatibility/CompatibilityEndpointIT.java` (F19, F23); `platform/diagnostics/SafeFailure`; `platform` must not depend on features (ArchUnit).
- `deploy/helm/owl-mast/templates/_helpers.tpl:374` -- main already refuses `routing.apiPathPrefix != /api` (c7578bb, test `test_api_prefix_is_exactly_what_the_backend_serves_and_the_frontend_calls`): F2 and the chart half of F15 need no change.

## Tasks & Acceptance

**Execution:**
- [x] `frontend/src/primitives/useRevalidatingResource.ts` + test -- `retains` option; a non-retained shown value is replaced directly -- F11.
- [x] `frontend/src/routes/ConnectionPanel.tsx`, `routes.test.tsx`, `e2e/shell/states.spec.ts` -- invalidate on not-found/incompatible; offline probe message; denial focus rule and return link; misroute copy -- F1, F10, F12, F20, F27.
- [x] `frontend/src/api/{client,config}.ts`, `api.test.ts` -- `protected` honoured; prefix rejects `//` and dot segments -- F13, F14.
- [x] `frontend/src/primitives/ActionButton.tsx`, `SettingsField.tsx`, `routes/Preferences.tsx`, `app/shell/PrimaryNavigation.tsx` + tests -- F21, F22, F24, F25, F26.
- [x] `frontend/src/theme/theme.test.tsx`, `e2e/shell/theme.spec.ts` -- boot script key and pre-paint attribute -- F30.
- [x] `frontend/e2e/shell/{accessibility,layout,keyboard,config}.spec.ts` -- axe on non-compatible states; 320/640px + 200%; non-default prefix chain -- F17, F29, F31.
- [x] `frontend/vite.config.ts`, `Dockerfile`, `nginx/*`, `docker-entrypoint.d/16-owlmast-api-prefix.envsh`, `playwright.image.config.ts`, `e2e/image/image.spec.ts`, `scripts/verify-frontend-artifact.sh`, `.github/workflows/ci.yml` -- published manifest, prefix guard, API prefix 404, browser smoke of the built image -- F4, F15, F16, F20.
- [x] `scripts/check-api-compatibility.py`, `deploy/tests/test_api_compatibility.py` -- fail-closed error handling, Java-like properties parsing, `--frontend-url` -- F4–F9.
- [x] `scripts/verify-quality-gates.sh` -- match `jsx-a11y/alt-text` alone -- F18.
- [x] `backend/.../platform/web/UnhandledFailureAdvice.java`, `CompatibilityEndpointIT.java` (+ test-only throwing controller) -- 500 as problem detail; version from `BuildProperties` -- F19, F23.
- [x] `docs/{api-compatibility,frontend,installation}.md`, OM-01.04 spec Verification line -- reword the runtime row (displayed, not gated), document `--frontend-url`, fix the smoke command -- F3, F4, F28.

**Round 2 (PR #119 review 5877269551, 10 findings R1–R10; reopened PR #112 thread 4551653276, P1):**
- [x] `frontend/docker-entrypoint.d/16-owlmast-api-prefix.envsh`, `scripts/verify-frontend-artifact.sh` -- refuse a prefix that names anything under the web root (or lies below it); negative list extended -- R1.
- [x] `scripts/check-api-compatibility.py`, `deploy/tests/test_api_compatibility.py` -- `descriptorPath` must be a plain absolute path; URLs with credentials refused and never printed; rejected values bounded; the verdict is one line whatever goes into it; escapes in property keys decoded as Java does -- R2, R7, R8, P1.
- [x] `frontend/src/routes/ConnectionPanel.tsx`, `routes.test.tsx`, `e2e/shell/states.spec.ts` -- a control the person left (focus fell to the document) is forgotten -- R3.
- [x] `frontend/src/app/shell/PrimaryNavigation.tsx`, `Shell.test.tsx`, `e2e/shell/keyboard.spec.ts` -- Escape ignored when handled, composing or a dialog is open -- R4.
- [x] `frontend/src/api/config.ts`, `api.test.ts` -- `/` falls back to `/api` -- R5.
- [x] `backend/.../platform/web/UnhandledFailureAdvice.java`, `UnhandledFailureIT.java` -- `Throwable`; `AssertionError` thrown and signalled -- R6.
- [x] `frontend/e2e/image/image.spec.ts`, `scripts/verify-frontend-artifact.sh` -- exact CSP directives; security headers and `no-store` on the manifest and misroute locations -- R9, R10.
- [x] `docs/api-compatibility.md` -- credentials, `descriptorPath`, `Error` envelope.

**Acceptance Criteria:**
- Given the 31 findings, when the PR is opened, then each is listed fixed or declined with a reason and every thread of review 5876022641 on PR #112 has a reply and is resolved.
- Given the changed code, when the frontend, deploy, script and backend gates run, then they pass, or the gate that could not run is reported with its reason.

## Implementation Notes

- 2026-11-12: owner-pre-approved run. Checkpoint 1 taken as "Approve and continue"; the spec is longer than 1600 tokens (31 findings in one goal) and was kept whole. Implemented directly: the run brief forbids handing the whole assignment to one subagent; the three review layers ran as subagents.
- Verified against main first. F2 and the chart half of F15 were already fixed by c7578bb (PR #109/#116 follow-up): `routing.apiPathPrefix` must be exactly `/api`, with a render test. No chart change here.
- F10 design: focus is never moved by a background or first-paint denial; it is repaired only when the change removed the control that held it (denial: neutral heading; other changes: panel heading). Chromium reports the removal as a `focusout` without destination while the control is still connected, so the tracker must not forget on that event (found by the e2e test).
- F11/F1: `retains` (hook) + `invalidatesView`/`retainsView` (panel). Failing closed is automatic; recovering from Incompatible or a denial still waits behind "New updates" (pinned by tests).
- F4: `vite build` emits `api-compatibility.json`; the image serves it; `--frontend-url` reads it. No Helm hook (deferred).
- F15/F20: image start-up guard `16-owlmast-api-prefix.envsh` (sourced by the base image's entrypoint; `COPY --chmod=0755`), nginx 404 at and below the prefix. The guard also refuses `/` and the image's own paths, which would shadow the shell or duplicate a location.
- F16: `playwright.image.config.ts` + `e2e/image`, run by `scripts/verify-frontend-artifact.sh` when `OWLMAST_IMAGE_BROWSER_SMOKE=1` (CI sets it; a CI run without it fails instead of skipping).
- F19: Boot's problem-details switch does not cover unhandled exceptions; `platform/web/UnhandledFailureAdvice` (lowest precedence) maps them to a 500 problem detail and logs class names only. Filter-level failures remain Boot's default body (documented, deferred to E02).
- Surprise: Playwright `getByText` matches substrings case-insensitively, so "Compatible frontend and backend" also matches "Incompatible …"; negative assertions use `{ exact: true }`.
- Verification results are in the PR description.
- Round 2 (2026-11-12, owner-pre-approved, same branch and PR #119): the run brief asked to extend this spec instead of opening a new one, so the status went back to `in-review` for the round. All ten findings of review 5877269551 and the reopened #112 finding were reproduced against 4b727cf before any change.
- R2: the review says the shell never reads `descriptorPath`. It does: `frontend/src/api/compatibility.ts` takes `DESCRIPTOR_PATH` from the same manifest at build time, so the published value is the path the shell calls. Pinning the check to `/compatibility` would make it disagree with a build that changes the manifest. The value is kept and restricted to `(/[A-Za-z0-9._~-]+)+` without dot segments.
- R3: in the app a click inside `main` moves focus to `main` (it has `tabindex=-1`), which the old code already handled; the gap was a click outside `main` (header, navigation background) or a programmatic blur. The e2e test clicks the empty part of the header and fails without the fix.
- R6 reverses triage row E16. Its reason ("not a failure to translate and continue from") did not hold: Boot's default handler answers an `Error` and the server continues either way, so only the envelope differs.
- R7: the `@` test comes first and the value is never printed, because the other "invalid URL" messages echo the value.
- Deferred (pre-existing, not caused by this round): the image still ships the base image's `50x.html` under the web root.
- P1: keys are decoded (`\uXXXX`, `\t`, `\n`, `\r`, `\f`, `\x` to `x`); a malformed `\u` is refused like Java throws. Values stay undecoded: an escaped number fails the decimal check (fail closed).

## Spec Change Log

## Review Triage Log

Pass 1 (2026-11-12): blind-hunter (B), edge-case-hunter (E), verification-gap (V) on the diff against 11005d4. No intent_gap or bad_spec; all kept findings routed to patch.

| # | Finding | Verdict | Evidence / action |
| --- | --- | --- | --- |
| B1 | Catch-all advice would turn future auth exceptions into 500 | low | True once E02 adds them; nothing on the classpath today. Constraint recorded in the advice Javadoc and docs. |
| B2 | 500 log line cannot be matched to a request | low | Patched: exchange log prefix (request id) added; path deliberately not logged. |
| B3 | Documented pre-rollout command points at the already-deployed frontend | medium | Patched in docs: point `--frontend-url` at the candidate image (local run or canary). |
| B4/E6 | Empty `--frontend-url`/`--backend-url` falls back to the checkout with exit 0 | high | Patched: empty value is unverifiable; test added. Mutual exclusion with the file options rejected (documented precedence). |
| B5/E2 | `RecursionError` from deeply nested JSON escapes | medium | Patched: caught in both parsers; test with 200000 `[`. |
| B6/E5 | Multi-line remote version breaks the one-line verdict | medium | Patched: versions collapsed to one bounded line; test with a forged line. |
| B7/E4 | No size cap or overall deadline on the HTTP read | low | Size cap patched (1 MiB, tested). Overall deadline rejected: a dripping server is not an everyday case and needs a second timing mechanism. |
| B8/E7 | Base URL with query/fragment; prefix without leading slash extends the host | medium | Patched and tested. |
| B9/E8 | Properties parsing differs from Java (line ends, continuation, trim) | medium | Patched: `\n`/`\r`/`\r\n` only, continuation refused, Java trim set; tests. |
| B10 | Two-URL invocation and manifest `descriptorPath` never exercised | medium | Patched: test with separate frontend and backend stubs. |
| B11/E10 | Focus repair covered only `denied` | medium | Patched: repair runs for every change that removes the focused control; test for rollback. |
| B12/E11 | `lastFocusedRef` can go stale | low | Tried forgetting on a destination-less focusout: it broke the repair in Chromium (e2e). Kept; the repair now clears the reference whenever it fires. |
| B13 | Recovery from Incompatible/denied waits for the user | low | By design (fail closed is automatic, recovery is content that waits); pinned by a test. |
| B14/E13/E14/E15 | Three prefix guards differ; `/` and `/assets` accepted by the image; `//` accepted by the shell | medium | Patched: image refuses `/` and its own paths; shell rejects empty segments before trimming; comments say "subset of the chart". |
| B15 | `/api-compatibility.json` shares the string prefix `/api`; exact prefix still served the shell | low | Exact-prefix 404 patched and checked; string-prefix routers documented. |
| B16 | ActionButton discards the thrown error | low | Patched: `console.error`, early return while pending. |
| B17 | Image browser smoke can silently not run in CI | medium | Patched: CI without the variable fails; `test:e2e:image` script added. |
| B18 | Test hygiene (linger bytes, docstring, skipped `""` case, spy restore, 31_000) | low | First three patched. Spy restore is false: `restoreMocks: true` in vite.config. `31_000` rejected: existing convention. |
| B19 | `titleProps` + DOM query is an indirect focus hook | low | Patched: `titleRef` prop. |
| E1 | 5000-digit contract number raises `ValueError` | medium | Patched: at most 10 digits; test. |
| E3 | `--timeout inf/nan/0` traceback or misreport | medium | Patched and tested. |
| E9 | 2xx non-descriptor waits behind "New updates" while Compatible is shown | medium | Patched: it invalidates; test. |
| E12 | Escape with focus outside the nav leaves the menu open | low | Patched: document listener, focus returned only from inside the menu; test. |
| E16 | Advice does not catch `Error` | false | Deliberate: `Exception` only. A JVM `Error` is not a request failure to translate and continue from; Boot's default handler still answers without trace or message. |
| E17 | Test-only controller is component-scanned into every IT context | false | Spring Boot's `TestTypeExcludeFilter` excludes nested classes of test classes from component scanning, which is why the explicit `@Import` is needed; the full integration suite passes unchanged. |
| E18 | Spec named a file that does not exist | low | Task line corrected. |
| E19 | `focusOnMount` has no production caller | low | Rejected: it is the primitive for the route-entry case EXPERIENCE.md requires ("Unavailable states focus their neutral heading"); kept and tested. |
| V1 | Advice log line not asserted | medium | Patched: `OutputCaptureExtension` asserts the line and the absence of the planted secret and of a trace. |
| V2 | Offline panel with a non-descriptor probe untested | medium | Patched: three cases (error, dropped connection, denial). |

Round 2 input (2026-11-12): PR #119 review 5877269551 (R1–R10) and the reopened PR #112 thread 4551653276 (P1), verified against 4b727cf.

| # | Finding | Verdict | Evidence / action |
| --- | --- | --- | --- |
| R1 | Prefix guard accepts `/index.html`, `/theme-boot.js`, `/owl-mark.svg` | high | Reproduced (the template renders `location = /index.html { return 404; }`). Patched: anything that exists under the web root at the prefix or a parent of it is refused; seven values added to the negative list, four near-misses to a positive check. |
| R2 | Remote `descriptorPath` is trusted | high | Newline forgery reproduced. Patched: plain absolute path only, and the verdict line is collapsed to one line at print time. "The shell never reads the field" is false (see Implementation Notes), so the value is not pinned to `/compatibility`. |
| R3 | Focus repair fires after the person left the panel | medium | Reproduced for a click outside `main` and for a blur. Patched: a destination-less `focusout` is re-checked in a microtask; unit and e2e tests (the e2e test fails without the fix). |
| R4 | One Escape closes the scope dialog and the compact menu | medium | Reproduced. Patched: handled, composing and dialog-open Escapes are ignored; unit and e2e tests. |
| R5 | Shell accepts `/`, image refuses it | medium | True. Patched: `/` falls back to `/api`; comment states what the image refuses on top. |
| R6 | Advice does not catch `Error` | medium | True (Boot's `application/json` body). Patched: `Throwable`; IT with `AssertionError` thrown and signalled. Reverses E16. |
| R7 | URL userinfo printed in verdicts | high | Reproduced. Patched: refused before any other URL check, value not printed; six cases per option. |
| R8 | Unbounded remote values in the verdict | medium | Reproduced (about 1 MiB line). Patched: every rejected value goes through `_one_line(repr(...))`; whole verdict capped at 2000 characters. |
| R9 | CSP e2e check is substring-only | medium | True. Patched: the header is parsed and compared with the whole policy, exactly one header, no report-only twin. |
| R10 | No header checks on the new nginx locations | medium | True. Patched: artifact script checks CSP, `nosniff`, `X-Frame-Options`, `Referrer-Policy` and `no-store` on eight paths; the image e2e does the same on six. |
| P1 | `\uXXXX` in property keys not decoded | high | Reproduced (false COMPATIBLE). Patched: keys decoded as `Properties.load` does; five accepting and three refusing cases. |

Pass 2 (2026-11-12): blind-hunter (B), edge-case-hunter (E), verification-gap (V) on the round 2 diff against 4b727cf. No intent_gap or bad_spec; kept findings routed to patch.

| # | Finding | Verdict | Evidence / action |
| --- | --- | --- | --- |
| 2B1 | A token in the query (`?access_token=`) is still echoed by the "invalid URL" messages | medium | True. Patched: a refused URL is never repeated, whatever the reason; six more cases per option. |
| 2B2/2E7 | `assertNotIn("user", err)` depends on the checkout path | medium | True (`/home/user/...`). Patched: unique marker. |
| 2B3/2E3 | ESC, NUL, C1 and bidi characters pass the one-line collapse | medium | True for remote versions and URLs. Patched: non-printable characters become `?` in `_one_line` and `_verdict_line`; base URLs must be printable ASCII; tests. |
| 2B4 | `--api-path-prefix` lacks the plain-path rule | medium | True (`/a?x=1`, `/a/../b` reached the request). Patched: same rule as `descriptorPath` after one trailing slash; `/` alone stays valid. |
| 2B5 | Accepted `descriptorPath` has no length bound | low | Patched: 1024 characters (the chart's cap); test. |
| 2B6/2E2 | Malformed `\u` in a value: Java refuses the file, the check said COMPATIBLE | medium | Reproduced. Patched: values are scanned with the same decoder; test. |
| 2B7 | Javadoc names `NoClassDefFoundError`, which Reactor treats as fatal in an operator | low | Patched: example removed, the limit stated in Javadoc and docs. |
| 2B8 | No IT for an `Error` raised inside an operator, or for a `LinkageError` | low | Rejected: a non-fatal error in an operator arrives as the same `onError` signal the "signalled" case covers; fatal ones reach no handler and the documentation now says so. |
| 2B9/2E6 | `parseCsp` duplicate check is case-sensitive | low | Patched: lowercased before the check. |
| 2B10 | Header test asserts no status and no hashed asset | medium | Patched: status, `Referrer-Policy`, report-only and cache policy per path, a real hashed asset and a missing one, in the e2e and in the artifact script. |
| 2B11/2E4 | `OWLMAST_WEB_ROOT` override lets the guard fail open | medium | True. Patched: override removed; a web root without `index.html` is refused; `/index.html` dropped from the explicit list. |
| 2B12 | `/50x.html` case pins a base-image leftover | low | Patched: case removed. Whether the image should ship `50x.html` is pre-existing and deferred. |
| 2B13 | `dialog[open]` also matches a non-modal dialog | low | Rejected: the shell has one dialog and it is modal; `:modal` is not available in the unit-test DOM, so the narrower selector would need a second code path. |
| 2B14 | `/` falls back silently; no `//` case | false | The fallback is silent for every refused value by design (the image guard is the diagnostic); `//` and `/api//` are already in the unsafe list of `api.test.ts`. |
| 2B15 | Docs paragraph incomplete | low | Patched: `@` anywhere, no authentication, the path rule, the 80/2000 limits. |
| 2E1/2E8 | `repr()`/`str()` of a 50000-deep remote value raises `RecursionError` | high | Reproduced (traceback). Patched in `_shown` and `_one_line`; tests for a rejected and an accepted nested value. |
| 2E5 | A `VirtualMachineError` thrown synchronously is answered as a plain 500 without a trace | low | Rejected: the answer is 500 either way, and logging class names only is the convention for every failure (`SafeFailure`); a rethrow branch would guard a state no test can produce reliably. |
| 2V1 | No test distinguishes `\t` decoding from the old `\x` to `x` rule | medium | Patched: `apiCon\tract.major` and three siblings must not be the contract key. |
| 2V2 | Control-character half of the URL check untested | medium | Patched with 2B3 (ESC, NUL, DEL, C1, bidi). |
| 2V3 | `_shown` pinned at one site only | medium | Patched for the remote `descriptorPath`; the operator-supplied sites no longer echo (2B1) or are covered by the prefix cases. |
| 2V4 | `_verdict_line` on stdout untested | low | Patched: manifest in a directory whose name holds a line break; remote version with ESC. |
| 2V5 | "Window lost focus keeps the control" untested | medium | Patched: unit test dispatches a destination-less `focusout` while the control stays active, then expects the repair. |

## Design Notes

- F10 narrows the OM-01.04 matrix row "Denied … heading focused": EXPERIENCE.md scopes that focus move to route/contextual entry ("Unavailable states focus their neutral heading"). A background poll or first paint is neither, so focus moves only to repair focus the removal dropped; the state is announced through the polite live region either way. Flagged to the owner in the PR.
- F3/F13: no protected feature exists, so the documentation is corrected instead of building a gate; `protected` gets its documented meaning in the client.
- F4: the manifest is emitted into the build output (`/api-compatibility.json`), so the deployed artifact answers for itself. A Helm pre-upgrade hook is not added: it needs cluster egress and image policy decisions outside this story.

## Verification

**Commands:**
- `cd frontend && npm run lint && npm run typecheck && npm test && npm run build` -- expected: clean, all unit/component tests pass.
- `cd frontend && npx playwright test` -- expected: shell suite passes in Chromium.
- `python3 -m unittest deploy.tests.test_api_compatibility` -- expected: pass.
- `scripts/verify-frontend-artifact.sh` (with `OWLMAST_IMAGE_BROWSER_SMOKE=1`) -- expected: image checks and browser smoke pass.
- `scripts/verify-quality-gates.sh` -- expected: every gate fails on its injected violation.
- `./gradlew :backend:build --console=plain` -- expected: unit and integration suites pass.
- `cd frontend && npm run test:e2e:smoke` -- expected: real-backend smoke passes.
