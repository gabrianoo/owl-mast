# Frontend shell (OM-01.04)

The web client is an independent artifact in `frontend/`: its own toolchain, tests, image and
release cadence (AD-14). It is never bundled into the backend image and is not a Gradle subproject.
The backend serves only `/api/*` and `/actuator/*`; the ingress or Gateway route (`routing.*` in the
chart) sends `/` to the frontend image and `/api` to the backend. The actuator is not routed unless
`routing.exposeActuator=true`.

## Framework decision and qualified pins (OM-01.04-T1)

**Decision (owner, 2026-11-08):** React + TypeScript + Vite is the accepted UI framework. Every pin
below is an exact version published at least two weeks before 2026-11-08, read from the npm
registry (`npm view <pkg> time`) or Docker Hub on that day, and locked in `frontend/package-lock.json`
(`.npmrc`: `save-exact`, `engine-strict`). Peer ranges were checked with `npm view <pkg>@<v> peerDependencies`.

| Component | Pin | Published | Why this one |
| --- | --- | --- | --- |
| Node.js | 24.21.0 (`.nvmrc`, `engines`, build image `node:24.21.0-alpine@sha256:ebfe2f90…`) | 2026-09-18 (image) | Current LTS line; jsdom 30 requires Node ≥ 24.15 |
| React / react-dom | 19.1.10 | 2026-10-14 | Latest stable 19.x on the registry |
| TypeScript | 6.0.3 | 2026-04-16 | Newest line inside typescript-eslint 8.72's supported range (`>=4.8.4 <6.1.0`); TypeScript 7 (2026-07-08) is outside it |
| Vite | 8.3.5 | 2026-10-21 | 8.3.6 (2026-11-05) is younger than two weeks |
| @vitejs/plugin-react | 6.1.2 | 2026-10-05 | Peer `vite ^8` |
| Vitest / @vitest/coverage-v8 | 4.1.12 | 2026-10-15 | 5.x (2026-11-02) is younger than two weeks; peer `vite ^8` |
| jsdom | 30.1.3 | 2026-10-15 | 31.0.0 (2026-11-05) is younger than two weeks |
| @testing-library/react / dom / jest-dom / user-event | 16.3.3 / 10.4.2 / 7.0.1 / 14.6.8 | 2026-08-27 / 2026-09-13 / 2026-08-09 / 2026-10-13 | jest-dom 7 ships the `vitest` matcher entry |
| axe-core / @axe-core/playwright | 4.14.0 / 4.14.0 | 2026-10-05 / 2026-10-15 | WCAG 2.2 rules; Playwright integration for rendered checks |
| @playwright/test / playwright-core | 1.64.1 | 2026-10-14 | 1.65.0 (2026-11-05) is younger than two weeks; `playwright-core` is pinned explicitly so axe's peer resolves to one copy |
| ESLint / @eslint/js | 9.39.5 | 2026-07-10 | `eslint-plugin-jsx-a11y` 6.10.2 declares peer `eslint ^3…^9`; ESLint 10 would need `--legacy-peer-deps`. The registry marks 9.x as no longer supported: see residual risks |
| typescript-eslint | 8.72.0 | 2026-10-19 | `strictTypeChecked` + `stylisticTypeChecked` |
| eslint-plugin-jsx-a11y / eslint-plugin-react-hooks / globals | 6.10.2 / 7.1.1 / 17.13.0 | 2024-10-26 / 2026-04-17 / 2026-10-01 | Static accessibility and hooks rules |
| @types/react, @types/react-dom / @types/node | 19.3.0 / 24.19.2 | 2026-09-09 / 2026-10-09 | Match React 19 and Node 24 |
| Runtime image | `nginxinc/nginx-unprivileged:1.31.7-alpine@sha256:b5047b9b…` | 2026-10-19 | Listens on 8080 as UID 101, matching `frontend.containerPort` and the pod security context in the chart |
| CI action | `actions/setup-node` v7.1.0 `949feb2413d6458794dcd2491c4babbbce0c15c1` | 2026-10-08 | Pinned by commit like the other actions |

No routing library: the shell has six destinations and needs deterministic title/focus/return
behaviour, so `src/app/router.tsx` wraps the History API in about 100 lines.

## Everyday commands (run in `frontend/`)

| Command | What it does |
| --- | --- |
| `npm ci` | Install the locked dependencies (Node 24.21.0 required). |
| `npm run dev` | Vite dev server on 5173, proxying `/api` and `/actuator` to `OWLMAST_BACKEND_URL` (default `http://127.0.0.1:8080`, e.g. `./gradlew :backend:bootTestRun --args='--server.port=8080'`). |
| `npm run lint` / `npm run typecheck` | ESLint (strict type-checked, jsx-a11y strict, react-hooks) and `tsc` for app, config and e2e projects. |
| `npm test` / `npm run test:coverage` | Vitest + Testing Library in jsdom: tokens against DESIGN.md, owl mark against the accepted SVG, contrast arithmetic, theme, router, primitives, connection states, preferences. |
| `npm run build` | Production bundle in `dist/`, including `api-compatibility.json` (the contract this build supports, read by the pre-rollout check with `--frontend-url`). |
| `npm run test:e2e` | Playwright `shell` project against `vite preview`: axe WCAG 2.2 AA in light and dark at 1280 px and 320 px, keyboard flow, dialog return, 320 px reflow, 200 % text size alone and combined with 320 px and 640 px, 44 px targets, reduced motion, every connection state including its axe scan (API mocked per test), the runtime API prefix chain and the pre-paint theme script. |
| `npm run test:e2e:smoke` | Playwright `smoke` project: starts the real backend (`bootTestRun`, disposable VectorChord container) and checks the browser → backend path through the routing contract. Needs Docker and free ports 18080 and 4174: neither server is reused, so a leftover listener fails the run instead of testing a stale backend. Both servers stop on SIGTERM when the run ends. |
| `scripts/verify-frontend-artifact.sh` (repo root) | Builds the image and proves its runtime contract (non-root, 8080, SPA fallback, `/owlmast-config.json`, published `/api-compatibility.json`, 404 below the API prefix, start-up refusal of an `OWLMAST_API_PATH_PREFIX` that is unsafe or names a path or page of the shell, headers, immutable caching for served hashed assets only (a missing one is `no-store`), no JDK). With `OWLMAST_IMAGE_BROWSER_SMOKE=1` (set in CI; needs `npm ci` and `npx playwright install chromium`) it also runs Chromium against the container (`e2e/image`, `playwright.image.config.ts`): the production CSP, the nginx template and the config endpoint in a real browser. |
| `scripts/check-api-compatibility.py` (repo root) | Frontend/backend contract check: static from the checkout, or against the artifacts with `--frontend-url` and `--backend-url`; see [api-compatibility.md](api-compatibility.md). |

CI runs the same commands: job `frontend` (lint, typecheck, unit/component with coverage, build,
browser suite, static pair check) and job `frontend-backend-smoke` (image contract, Chromium against the
image, and real-backend smoke). `scripts/verify-quality-gates.sh` additionally proves three frontend gates fail on injected
violations (jsx-a11y, type error, token drift) and that the pair check rejects an incompatible pair.

## What the shell implements (T2/T3)

- **Tokens** (`src/design/tokens.css`): every DESIGN.md colour, typography, radius and spacing value as
  CSS custom properties; unsuffixed values in light mode, `-dark` values under `prefers-color-scheme:
  dark` and under the explicit override `html[data-owl-theme="dark"]`; font sizes as rem equivalents of
  the DESIGN px so browser text scaling applies. `tokens.test.ts` reads DESIGN.md and fails on any drift.
- **Owl mark** (`src/design/owlMark.ts`, `BrandMark`): the accepted `assets/owl-mark.svg` geometry,
  1.8 stroke, round caps/joins, `currentColor` on the primary token, decorative beside the visible
  name; `public/owl-mark.svg` is a byte-identical copy used as favicon.
- **Theme**: follows the device; Preferences offers Follow device / Light / Dark with explicit Save
  and the real save result; the choice persists in `localStorage` (`owlmast.theme`) and is applied
  before first paint by `public/theme-boot.js`. The script is a static file (the CSP forbids inline
  scripts), so it repeats the storage key; `theme.test.tsx` fails if it drifts from
  `THEME_STORAGE_KEY`, and `e2e/shell/theme.spec.ts` proves the attribute is set with the application
  bundle blocked.
- **Shell**: skip link, brand home link, `surface-navigation` (persistent rail ≥ 1024 px, labelled
  menu button below), `scope-bar` (project, source identity, period, "Change scope" opening a native
  modal dialog), `main` with the destination h1. Route change sets the title to `<Destination> · Owl
  Mast` and focuses the h1; Back returns to the prior in-app location or Daily Work.
- **Primitives** (`src/primitives`): `StateMessage` (loading/empty/error/offline/denied/stale/
  unsupported/ready as text), `ActionButton` (no duplicate activation while pending, real outcome
  only), `ExternalLink`, `SettingsField`, `ModalDialog` (native `<dialog>`, focus restore),
  `useRevalidatingResource` + `NewUpdates` (changed values wait behind one polite announcement).
- **Connection panel** (Daily Work): loads `GET {apiPathPrefix}/compatibility`, renders the pair
  verdict and every state; offline requests nothing and labels shown values stale; denied removes
  content and focuses the neutral heading; re-checks every 30 s behind "New updates".
- **Destinations**: Daily Work, Focus, Knowledge, Connections, Usage show honest first-use states
  (no invented counts); Preferences holds theme settings and states that push is not offered.

## Accessibility verification (T4)

| Check | Where | Evidence |
| --- | --- | --- |
| Contrast | `tokens.test.ts` (arithmetic for every text/surface, outline and identity pair, both themes); `e2e/shell/accessibility.spec.ts` (axe `color-contrast` on rendered pages, light and dark) | ≥ 4.5:1 text, ≥ 3:1 outlines/markers; axe reports zero violations |
| Keyboard flow | `e2e/shell/keyboard.spec.ts` | Skip link first, Enter into main, menu button at 320 px, dialog Escape/return, Back focuses the prior h1 |
| Screen-reader labels | axe + `Shell.test.tsx` | Landmarks, `aria-current`, decorative mark hidden, polite status regions |
| Reduced motion | `e2e/shell/layout.spec.ts` | Transition and animation durations ≤ 0.001 s under `prefers-reduced-motion: reduce` |
| 320 px / 200 % | `e2e/shell/layout.spec.ts` | No horizontal overflow at 320 px and at 200 % root font size on 1280 px |
| 44 px targets | `e2e/shell/layout.spec.ts` | Every visible control ≥ 44 × 44 CSS px |
| Theme override | `e2e/shell/theme.spec.ts` | Exact tokens for system dark, explicit light override survives reload |

## Residual risks and deferrals

- **Browser authentication, session and origin policy** are not implemented (explicit protocol/security
  gate, OM-02.01). The shell has no authorized project, says so, and performs no protected fetch; the
  compatibility descriptor is public by design.
- **Push** is not offered or requested (UI/push gate, first E15 story). Preferences shows an
  unsupported state instead of a control.
- **Real authenticated journeys** arrive with E02/E18; the smoke here proves the browser → backend
  path only through the public descriptor and readiness probe.
- **ESLint 9.39.5** is pinned because `eslint-plugin-jsx-a11y` has no ESLint 10 release; the registry
  marks 9.x as unsupported. Re-pin to ESLint 10 when jsx-a11y supports it, or replace the static
  rules with the rendered axe checks already in place.
- **Qualified browser**: Chromium 1248 (Playwright 1.64.1) on Linux x86_64 only. Firefox/WebKit, real
  assistive technology and phone devices are not exercised; the 320 px/200 % checks are emulated.
- **Kind deployment of the frontend image** (chart `frontend.enabled=true`) is not performed in this
  story; `scripts/verify-frontend-artifact.sh` proves the container contract and the chart tests
  already render the frontend Deployment/Service and routes.
