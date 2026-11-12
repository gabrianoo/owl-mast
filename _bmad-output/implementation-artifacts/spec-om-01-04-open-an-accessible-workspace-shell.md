---
title: 'OM-01.04 — Open an accessible workspace shell'
type: 'feature'
created: '2026-11-08'
status: 'in-review'
route: 'dispatch'
review_loop_iteration: 2
baseline_commit: 'eff1971d1d731ba352e001ba078235a950338142'
context:
  - '{project-root}/_bmad-output/implementation-artifacts/epic-1-context.md'
  - '{project-root}/docs/engineering-tracking.md'
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** The repository has a qualified backend and an installation package with frontend deployment/routing values, but no web client: no recorded UI framework decision, no independently built/tested/packaged shell, no API compatibility policy, and none of the accepted DESIGN/EXPERIENCE shell behaviour (tokens, owl mark, theme override, navigation, focus/title, safe state messages) exists in code.

**Approach:** Add `frontend/`, an independently built React + TypeScript + Vite single-page shell with exact qualified pins and a committed lockfile, its own lint/typecheck/unit/e2e/build commands, its own non-root nginx image honouring the chart's `OWLMAST_API_PATH_PREFIX` contract, and a documented, executable API compatibility policy: the backend publishes `GET /api/compatibility` (new `compatibility` feature) and RFC 9457 problem details as the common error envelope; the frontend declares the contract it supports; a pre-rollout script and the shell itself detect incompatible pairs. Tracking: GitHub issue #23 (OM-01.04), epic #1 (E01); ENG-01 run `run-20261108-e01`, authorization `run-20261108-e01:OM-01.04:1`.

**Owner decision (2026-11-08, coordinator chat):** React + TypeScript + Vite is ACCEPTED as the UI framework (AC1/T1). Pins are qualified here: exact versions at least two weeks old on 2026-11-08, lockfile committed.

## Boundaries & Constraints

**Always:** Preserve AC1–AC4 and task IDs OM-01.04-T1..T4 verbatim. Exact DESIGN.md tokens (colors light/dark, typography, radii, spacing, 44px targets), the accepted `assets/owl-mark.svg` geometry with `currentColor`, system theme with explicit override, 3px focus outline with 2px offset, skip link, landmarks, title/h1 focus on route change, dialog trap/inert/Escape/return, reduced motion, 320px reflow and 200% text zoom. Distinct loading/empty/error/offline/denied/stale/unsupported messages with safe copy; offline never discloses protected content from cache; denied removes protected content and fails closed; pending actions never show invented success. Frontend and backend remain separate artifacts/images (AD-14); pins come from registry/release metadata recorded in `docs/frontend.md`. Backend code follows the feature-package convention and passes every existing gate.

**Never:** Bundle the UI into the backend image or serve it from Spring; implement browser authentication, session/origin policy or push (explicit qualification gates; E02/E15/E18 own the real journeys); invent data, counts or progress for feature destinations; edit `automation/policy.toml`, `automation/examples/*`, `automation/unattended/`; merge, tick issue checkboxes, change Project status or comment on issue #23; store secrets.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| Tokens preserved | DESIGN.md frontmatter vs `tokens.css` | Every color (light + `-dark`), typography, radius and spacing token matches exactly; rem sizes equal the px at 16px root | Test fails naming the token |
| Owl mark preserved | `assets/owl-mark.svg` vs `BrandMark` | Same viewBox, stroke 1.8, round caps/joins, identical path data, `currentColor`, `aria-hidden`, paired with visible "Owl Mast" text | Test fails naming the attribute |
| Theme | no preference / `light` / `dark` saved | Follows `prefers-color-scheme`; override sets `data-owl-theme` and `color-scheme`; Preferences saves only on explicit Save and shows the actual result | Storage failure shows an error, keeps the unsaved choice visible |
| Route change | keyboard navigation to another destination | `document.title` = "<Destination> · Owl Mast", h1 receives focus, `aria-current="page"` moves, compact menu stays labelled | Unknown path → Unsupported page with neutral copy and a working return link |
| Dialog | open "Change scope" | Native modal: focus inside, background inert, Escape closes, focus returns to the trigger | — |
| Compatibility | backend descriptor major = supported major and minor ≥ required | "Compatible" panel with backend version and contract | Different major / lower minor → Unsupported state naming both contracts; 404 → cannot verify, fail closed |
| Offline | `navigator.onLine=false` or `offline` event | Offline state message; protected fetches are not made and no cached protected data is newly rendered; previously shown values labelled stale | Reconnect re-checks before refreshing |
| Denied | protected fetch answers 401/403 | Protected content removed, neutral "This item is unavailable" heading focused, return link works | No title or detail of the denied item leaks |
| Pending action | Save clicked, promise unsettled | Button disabled against duplicates, `aria-busy`, label retained, no success text | Rejection → error text beside the control, form state retained |
| New updates | poll returns changed values while reading | Values do not move; one polite "1 new update" announcement; activating applies and focuses the changed section | — |
| Image | `docker run -e OWLMAST_API_PATH_PREFIX=/api` on port 8080 as non-root | `/` and `/focus` (SPA fallback) return 200; `/owlmast-config.json` echoes the prefix; no JDK/backend jar in the image | Build fails if `npm ci` or `vite build` fails |
| Pre-rollout check | `scripts/check-api-compatibility.py` static pair or `--backend-url` | Exit 0 and a one-line verdict for compatible pairs | Exit 1 naming both contracts for incompatible pairs or an unreachable descriptor |

</frozen-after-approval>

## Code Map

- `_bmad-output/planning-artifacts/ux-designs/ux-owl-mast-2026-11-05/DESIGN.md`, `EXPERIENCE.md`, `assets/owl-mark.svg`, `assets/reference-theme.css`, `assets/palette-contrast.md`, `mockups/navigation.html` -- visual/behavioural contract; tests read DESIGN.md and the SVG directly.
- `deploy/helm/owl-mast/values.yaml` (`frontend.*`, `routing.*`), `templates/frontend-deployment.yaml` -- runtime contract for the image: port 8080, non-root, readiness `GET /`, env `OWLMAST_API_PATH_PREFIX`.
- `backend/src/main/java/com/aisquad/owlmast/{bootstrap,access}` -- feature-package shape to copy for the new `compatibility` feature; `FeatureModuleRules` (ArchUnit) constrains `api`/`adapter` dependencies.
- `backend/src/integrationTest/java/com/aisquad/owlmast/HealthEndpointIT.java` -- pattern for the compatibility endpoint IT (random port, `ContainersConfiguration`, `StubIdentityConfiguration`).
- `backend/src/test/java/com/aisquad/owlmast/TestOwlMastApplication.java` -- `bootTestRun` entry used by the browser-to-backend smoke.
- `.github/workflows/ci.yml`, `scripts/verify-quality-gates.sh`, `scripts/verify-install-package.sh`, `deploy/tests/` -- CI shape (ubuntu-26.04, SHA-pinned actions), negative gate style, deploy Python tests.
- `docs/{development,installation,toolchain-qualification}.md`, `README.md` -- documentation homes to extend.

## Tasks & Acceptance

**Execution:**
- [x] `frontend/package.json`, `package-lock.json`, `.nvmrc`, `.npmrc`, `tsconfig*.json`, `vite.config.ts`, `eslint.config.js`, `playwright.config.ts`, `index.html` -- qualified exact pins (Node 24.21.0, React 19.1.10, TypeScript 6.0.3, Vite 8.3.5, Vitest 4.1.12, ESLint 9.39.5 + typescript-eslint 8.72.0 + jsx-a11y 6.10.2 + react-hooks 7.1.1, Testing Library, axe-core 4.14.0, Playwright 1.64.1), scripts `lint`/`typecheck`/`test`/`build`/`test:e2e` -- T1.
- [x] `frontend/src/design/tokens.css`, `base.css`, `src/app/shell/BrandMark.tsx`, `public/owl-mark.svg` + tests -- exact DESIGN tokens as CSS custom properties, rem typography, 44px controls, focus ring, reduced motion, accepted owl mark -- T2, AC1.
- [x] `frontend/src/theme/*` -- system theme + explicit override persisted locally; `data-owl-theme` on `<html>` -- T2, AC1.
- [x] `frontend/src/app/{router,destinations,App}.tsx`, `src/app/shell/{Shell,SkipLink,PrimaryNavigation,ScopeBar}.tsx`, `src/state/{scope,connectivity}.tsx` -- history router, rail/compact menu, scope bar (project, source identity, period), title/h1 focus, safe return -- T2/T3, AC2.
- [x] `frontend/src/primitives/{StateMessage,ActionButton,ExternalLink,SettingsField,ModalDialog,NewUpdates}.tsx` + tests -- shared primitives per UX-DR25/26/27/28/40 -- T2/T3, AC2/AC3.
- [x] `frontend/src/api/{config,client,compatibility,problem}.ts`, `frontend/api-compatibility.json`, `src/routes/*.tsx` -- runtime config, protected/offline-aware client, compatibility verdict, route views with honest first-use states -- T1/T3, AC3/AC4.
- [x] `backend/src/main/java/com/aisquad/owlmast/compatibility/**`, `src/main/resources/owlmast/api-contract.properties`, `application.yaml` (problem details) + unit/IT tests -- published contract descriptor and common error envelope -- T1, AC4.
- [x] `frontend/Dockerfile`, `frontend/nginx/default.conf.template`, `frontend/.dockerignore`, `scripts/verify-frontend-artifact.sh` -- independent image on node:24.21.0-alpine → nginxinc/nginx-unprivileged:1.31.7-alpine (digests), port 8080, SPA fallback, config endpoint -- T1, AC4.
- [x] `scripts/check-api-compatibility.py`, `deploy/tests/test_api_compatibility.py`, `docs/api-compatibility.md` -- policy and pre-rollout check with negative tests -- T1/T4, AC4.
- [x] `frontend/e2e/*.spec.ts` -- Playwright: axe (light/dark, 1280/320), keyboard flow, dialog return, 320px/200% reflow, 44px targets, reduced motion, mocked offline/denied/unsupported/incompatible states, real-backend smoke (`bootTestRun`) -- T4, AC2/AC3/AC4.
- [x] `.github/workflows/ci.yml`, `scripts/verify-quality-gates.sh` -- `frontend` job and `frontend-backend-smoke` job on ubuntu-26.04 with SHA-pinned setup-node; negative frontend gates (jsx-a11y, type error, token drift) -- T1/T4.
- [x] `docs/frontend.md`, `docs/development.md`, `docs/installation.md`, `README.md`, `settings.gradle.kts` comment -- pins with sources, commands, image, deferrals -- T1/T4.

**Acceptance Criteria:** AC1–AC4 as stated in epic-01.md for OM-01.04; verified by the commands below.

## Implementation Notes

- 2026-11-08: Unattended run `run-20261108-e01`; checkpoint approvals come from the coordinator's pre-authorization of T1–T4 and the owner's recorded framework decision. Executed directly, no subagents. Push and PR creation are required by the run brief (the bmad-build default of no push is overridden by the coordinator).
- Pins resolved from registry/Docker Hub metadata on 2026-11-08 (table and reasons in `docs/frontend.md`). Two constraints shaped them: typescript-eslint 8.72 caps TypeScript below 6.1 (so 6.0.3, not 7.0.2), and eslint-plugin-jsx-a11y 6.10.2 has no ESLint 10 peer (so ESLint 9.39.5, flagged as a residual risk). `playwright-core` is pinned explicitly because `@axe-core/playwright` otherwise pulled a second copy and broke the `Page` type.
- Surprises: jsdom 30 implements neither `showModal` nor `scrollIntoView`, so `vitest.setup.ts` shims the dialog API and the skip link guards the call; the real modal behaviour is proven in Chromium. `react-hooks` 7 forbids `setState` in effects, so media-query and connectivity tracking use `useSyncExternalStore` and the compact menu derives "open" from the path. A native `<dialog>` lets Tab leave to the browser UI (focus on `body`), never to the inert page: the e2e assertion was adjusted to that semantics. The first e2e run was flaky when Tab was pressed before React rendered; the test now waits for the h1.
- WebFlux 404s on unknown paths honour `spring.webflux.problemdetails.enabled=true` (verified by `CompatibilityEndpointIT`): `application/problem+json`, no `trace`/`exception` fields.
- Image: `nginx-unprivileged` processes `/etc/nginx/templates/*.template` with envsubst for defined environment variables only, so nginx's own `$uri` survives; security headers live in an included file because `add_header` does not inherit. The pre-paint theme script moved to `public/theme-boot.js` so the CSP can forbid inline scripts.
- Verified on this machine (WSL2, Docker Desktop 29.9.2, Node 24.21.0): `./gradlew build` (42 unit + 27 integration tests, 0 failures); `scripts/verify-quality-gates.sh` (9/9 gates fail on injected violations: 5 backend + jsx-a11y, tsc, token drift, API pair); `python3 -m unittest discover -s automation/tests -t .` (339 tests OK); `scripts/verify-install-package.sh` (63 deploy tests OK, including 6 for the pair check); frontend `npm run check` (0 lint/type errors, 70 unit/component tests), `npx playwright test` (40 shell tests, run twice: 80/80), `npm run test:e2e:smoke` (3 tests against the real backend started by `bootTestRun`), `scripts/verify-frontend-artifact.sh` (11/11 image checks). CI is wired in `.github/workflows/ci.yml` (jobs `frontend`, `frontend-backend-smoke`; `gate-negative-checks` gained Node); the first CI run happens on the PR.
- Not done here (recorded as deferrals in `docs/frontend.md` and the PR): browser authentication/origin policy, push, real authenticated journeys (E02/E15/E18), Kind deployment of the frontend image, non-Chromium browsers and real assistive technology.

## Design Notes

- Router is a 60-line history wrapper (no react-router pin): six destinations plus Unsupported; focus moves to the destination h1 only after an in-app navigation, never on first paint.
- Compatibility rule (consumer side): compatible iff `backend.major == frontend.major && backend.minor >= frontend.minMinor`. The backend is only a publisher; the same rule lives in `scripts/check-api-compatibility.py` for pre-rollout checks.
- Protected fetches use `cache: 'no-store'` and are refused while offline before any network or cache access, so nothing protected is newly disclosed; the compatibility descriptor is public but goes through the same client.
- The image learns the API prefix through nginx's `envsubst` template → `/owlmast-config.json`; the Vite dev server proxies `/api` and `/actuator` to the backend instead.

## Verification

**Commands:**
- `./gradlew build --console=plain` -- expected: backend gates, unit and integration suites pass including `CompatibilityEndpointIT`.
- `scripts/verify-quality-gates.sh` -- expected: every backend gate and the three frontend gates fail on injected violations.
- `python3 -m unittest discover -s automation/tests -t .` -- expected: unchanged, passes.
- `cd frontend && npm ci && npm run lint && npm run typecheck && npm test && npm run build` -- expected: 0 lint errors, 0 type errors, all unit/component tests pass, `dist/` produced.
- `cd frontend && npx playwright test --project=shell` -- expected: accessibility, keyboard, reflow, state tests pass in Chromium.
- `cd frontend && npm run test:e2e:smoke` (`npx playwright test -c playwright.smoke.config.ts`; the `smoke` project is not in the default config) -- expected: real backend (`bootTestRun`) answers `/api/compatibility`, the shell shows "Compatible".
- `scripts/verify-frontend-artifact.sh` -- expected: image builds, serves `/`, `/focus`, `/owlmast-config.json` on 8080 as UID 101, contains no Java.
- `scripts/check-api-compatibility.py` -- expected: static pair compatible, exit 0.

## Review Triage Log

Round 1 (GPT-6 Astra High on `3d2f91a`) was triaged and repaired in `379e07c` and `e509d10`; its table is in the PR #112 description.

Round 2: coordinator review of `8570ec6`, plus CI runs 42441700521 (`3d2f91a`) and 42442580262 (`8570ec6`). Triaged 2026-11-08 in an interactive `/bmad-build` repair.

| # | Finding | Verdict | Route | Evidence and repair |
|---|---------|---------|-------|---------------------|
| R2-1 | P1 (AC3) `useRevalidatingResource.ts:118`: with A and B outstanding, A's denial did not invalidate B; B's late success had a higher token, became pending, and "Show update" restored denied content although no request was issued after the denial | high | patch | Verified: `accept` compared only against `accepted` and the offline floor, so B (token 3 > A's 2) passed. Repair: an `invalidates` response, which for the panel is a denial, raises the ledger floor to every token issued when it is accepted. Only a later-issued load can restore content. The option `applyImmediately(current, next)` became `invalidates(next)`, since its only caller was the denial rule. Tests: `denial barrier` suite with the exact A/B/A-denied/B-late order (nothing restored, `pendingCount` 0, `applyPending` no-op) and a post-denial request C that restores content through "Show update". Both fail with the floor raise removed. |
| R2-2 | P2 `ConnectionPanel.tsx:81`: `stale={!online}` showed "Compatible frontend and backend" again as soon as the connection returned, before any re-check | medium | patch | Verified: the label depended only on `online`. Repair: the hook records the token that produced or last confirmed the shown value and a disconnect floor, and reports `stale` until a load issued after reconnecting either confirms it (equal answer) or replaces it (applied update). The panel uses `!online \|\| resource.stale`. Tests: hook `stale until a post-reconnect load` case and panel `keeps "Last known values" after reconnecting until the post-reconnect check succeeds`. The panel test fails with the old `stale={!online}`. |
| R2-3 | CI: both Playwright jobs timed out after 120 s waiting for `config.webServer` | high | patch | Root cause: `vite preview` without `--host` binds the first address `localhost` resolves to. On the GitHub Ubuntu runners `/etc/hosts` maps `localhost` to `::1` as well, and glibc orders `::1` first, so the preview listened on `[::1]:4173`/`4174` while Playwright polled `127.0.0.1`. On this WSL machine `localhost` resolves only to 127.0.0.1, which is why it passed locally. Reproduced locally: a preview bound to `::1` answers `[::1]` and refuses 127.0.0.1. The job logs gave no hint because webServer stdout was not piped. Repair: both configs pass `--host 127.0.0.1` and pipe preview stdout (the bound URL is now logged), and CI prints `getent ahosts localhost` before each browser step. The smoke's `curl: (56) Connection reset by peer` came from the readiness wait in `scripts/verify-frontend-artifact.sh` (Docker's port proxy resets while nginx starts). It was harmless, since all 11 checks passed, and the wait loop is now silent. |
| R2-4 | Local smoke needed a manual backend restart | low | patch | Not reproduced: the old config left no orphan in a fresh run, because the Gradle daemon cancels `bootTestRun` when the client dies. The plausible cause is `reuseExistingServer: !CI`, which silently reuses whatever already listens on 18080. Repair: neither smoke server is reused, so a leftover listener fails loudly. Gradle runs with `--no-daemon`, matching CI. Both servers get `gracefulShutdown: SIGTERM`. Two consecutive local runs (3/3 each) left nothing on 18080/4174 and no backend JVM. |

Gates on the round-2 tree (local, no manual restarts): `npm run lint` 0 errors; `npm run typecheck` 0 errors; `npm test` 79/79; `npm run build` OK; the new hook and panel tests 25 consecutive runs, 25/25; `CI=1 npx playwright test` 40/40; `npm run test:e2e:smoke` twice back to back, 3/3 each; `scripts/verify-frontend-artifact.sh` 11/11.

CI on `98f393a` (run 42478184347): all 6 jobs pass. Browser suite 40/40, smoke 3/3. The new `getent ahosts localhost` step prints `::1` first on the runner, which confirms the R2-3 root cause. The previews logged `Local: http://127.0.0.1:4173/` and `:4174/`.
