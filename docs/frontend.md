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
| `npx playwright install chromium` | Download the Chromium build that the locked Playwright expects. `npm ci` does not do this, so on a fresh machine `npm run test:e2e` and `npm run test:e2e:smoke` fail with "Executable doesn't exist" until it has run once (again after a Playwright bump). On a machine without the browser's system libraries use `npx playwright install --with-deps chromium`, as CI does. |
| `npm run dev` | Vite dev server on 5173, proxying `/api` and `/actuator` to `OWLMAST_BACKEND_URL` (default `http://127.0.0.1:8080`, e.g. `./gradlew :backend:bootTestRun --args='--server.port=8080'`). |
| `npm run lint` / `npm run typecheck` | ESLint (strict type-checked, jsx-a11y strict, react-hooks) and `tsc` for app, config and e2e projects. |
| `npm test` / `npm run test:coverage` | Vitest + Testing Library in jsdom: tokens against DESIGN.md, owl mark against the accepted SVG, contrast arithmetic, theme, router, primitives, connection states, session states and the CSRF contract, preferences. |
| `npm run build` | Production bundle in `dist/`, including `api-compatibility.json` (the contract this build supports, read by the pre-rollout check with `--frontend-url`). |
| `npm run test:e2e` | Playwright `shell` project against `vite preview`: axe WCAG 2.2 AA in light and dark at 1280 px and 320 px, keyboard flow, dialog return, 320 px reflow, 200 % text size alone and combined with 320 px and 640 px, 44 px targets, reduced motion, every connection and session state including its axe scan (API mocked per test; `e2e/shell/test.ts` gives every page a signed-in synthetic session unless the test mocks its own), the runtime API prefix chain and the pre-paint theme script. |
| `npm run test:e2e:smoke` | Playwright `smoke` project: starts the real backend (`bootTestRun`, disposable VectorChord container and the pinned Keycloak with a synthetic realm) and checks the browser → backend path through the routing contract, including one sign-in at Keycloak's own login page, the return to the shell, a reload and sign-out. The synthetic user's password is generated for the run and passed through `OWLMAST_FIXTURE_USER_PASSWORD`; it is never stored. Needs Docker and free ports 18080 and 4174: neither server is reused, so a leftover listener fails the run instead of testing a stale backend. Both servers stop on SIGTERM when the run ends. |
| `scripts/verify-frontend-artifact.sh` (repo root) | Builds the image and proves its runtime contract (non-root, 8080, SPA fallback, `/owlmast-config.json`, published `/api-compatibility.json`, 404 below the API prefix, start-up refusal of an `OWLMAST_API_PATH_PREFIX` that is unsafe or names a path or page of the shell, headers once on every answer including a 416, immutable caching for served hashed assets only (a missing one is `no-store`), template substitution limited to `OWLMAST_*`, no JDK). See [Image configuration](#image-configuration). With `OWLMAST_IMAGE_BROWSER_SMOKE=1` (set in CI; needs `npm ci` and `npx playwright install chromium`) it also runs Chromium against the container (`e2e/image`, `playwright.image.config.ts`): the production CSP, the nginx template and the config endpoint in a real browser. |
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
  unsupported/ready/signed-out as text), `ActionButton` (no duplicate activation while pending, real outcome
  only), `ExternalLink`, `SettingsField`, `ModalDialog` (native `<dialog>`, focus restore),
  `useRevalidatingResource` + `NewUpdates` (changed values wait behind one polite announcement).
- **Session** (`src/state/session.tsx`, `src/api/session.ts`, `SessionControl`, `SessionGate`):
  see [Session](#session-om-0201).
- **Connection panel** (Daily Work): loads `GET {apiPathPrefix}/compatibility`, renders the pair
  verdict and every state; offline requests nothing and labels shown values stale; denied removes
  content and focuses the neutral heading; re-checks every 30 s behind "New updates".
- **Destinations**: Daily Work, Focus, Knowledge, Connections, Usage show honest first-use states
  (no invented counts) to a signed-in person and the session state to everybody else; Preferences
  holds theme settings and states that push is not offered. The connection panel and Preferences
  need no session.

## Session (OM-02.01)

The backend holds the session and the tokens ([identity.md](identity.md)); the browser holds one
`HttpOnly` cookie that scripts cannot read. The shell stores nothing about the session: no token, no
copy in `localStorage` or `sessionStorage`. Requests keep `credentials: 'same-origin'`; there is no
CORS, and the image's Content-Security-Policy is unchanged (`connect-src 'self'`, `form-action
'self'`), because sign-in is a top-level navigation and sign-out is a same-origin `fetch`.

| Call (below the API prefix) | Use |
| --- | --- |
| `GET /session` | Public, 200: `{"state":"signed-out"}`, or `signed-in` with `person` (`principalId`, `displayName`) and `csrf` (`headerName`, `token`). 503 with the member `csrf` in the error envelope when the backend keeps a session it cannot confirm (an identity provider outage): nobody is shown as signed in, the token is kept and the shell treats the session as kept, so **Sign out** is offered. The client carries that one member of the error body and nothing else of it (`errorExtension`). Read on start, on window focus, when the page becomes visible, when the browser reports a connection again, every 60 s while the page is visible (a hidden tab does not poll: each read renews the session, and an unattended tab must not keep it alive), and after a protected call answered 401. A read is given up after 15 s. The limit is above the 10 s the backend gives the identity provider to answer a renewal, so the 503 of a provider that never answers still arrives. Any other answer (another shape, an error status, no answer) is a problem, never "signed in". The header name and token are checked before they are used as a header, in the 503 as in the signed-in answer; a 503 whose `csrf` fails the check is a failed read like any other. |
| `GET /session/sign-in` | A full-page navigation, never a `fetch`. The backend sends the browser to the identity provider and back to `/`. When sign-in does not complete it returns the browser to `/?sign-in=failed` or `/?sign-in=unavailable`; the shell reads the parameter once and removes it from the address (`history.replaceState`), so a reload or a copied link does not repeat it. |
| `POST /session/sign-out` | Sent with the CSRF header of the current session. 200 ends the session (`identityProvider`: `ended` or `unconfirmed`); 401 means there was none; on 403 the shell reads the session once and retries once when that read says signed in or is the 503 of a kept session. The CSRF token is the one of the last answer that carried one (a signed-in answer, or the 503 of a kept session): it is dropped when the backend says nobody is signed in and after a sign-out, and kept when a session read fails without one, because such a read says nothing about the session. |

`ApiClient.post` adds the CSRF header to every unsafe call; a `GET` never carries it. A 401 on a call
marked `protected: true` tells the session state, which reads the session again; a 403 is a denial
for a signed-in person and does not touch the session.

| State | When | What the person sees |
| --- | --- | --- |
| Loading | First read in flight | "Checking your session" (loading); no destination content, and not the signed-out state |
| Signed out | The backend says nobody is signed in | "You are signed out" with **Sign in**. After a sign-out whose end at the identity provider was not confirmed, a second sentence says so |
| Signed in | The backend names the person | Header: "Signed in as *display name*" (text only) and **Sign out**; destinations show their content |
| Expired | Somebody was signed in, or the backend said it keeps a session, and a later read or a 401 says otherwise, also when reads failed in between (the problem state remembers that a session was kept) | "Your session ended": the content that needed authorization is removed, focus moves to the message, **Sign in again** |
| Sign-in failed | Returned with `sign-in=failed`; shown for the first session answer after the return only | "Sign-in was not completed" (denied kind), **Sign in again**; says that an administrator creates accounts |
| Provider error | Returned with `sign-in=unavailable` | "The identity provider is unavailable" (error kind), **Retry sign-in** |
| Problem | The session endpoint gave no usable answer | "The session could not be checked" (error kind), **Retry** reads again; nothing that needs authorization is shown. The header says "Session not confirmed". When a session is kept, the header also offers **Sign out**: during an identity provider outage the backend answers the session read with 503 and still serves sign-out, so the person can end the session on this device. The shell knows a session is kept when somebody was signed in before the reads failed, or when the 503 carries `csrf`, in whatever state it arrives: a shell that starts during the outage, or one that showed "signed out" while another tab signed in. A failed read without `csrf` in a shell that saw nobody signed in offers no **Sign out**. A sign-out that fails is reported next to the button, which stays |

The display name is shown as text and is never treated as identity; the principal id is not shown.
Account creation, passwords and recovery belong to the identity provider: the shell has no form for
them. Evidence: `src/api/session.test.ts`, `src/state/session.test.tsx`, `e2e/shell/session.spec.ts`
(every state, the CSRF header on sign-out, sign-out while the session is not confirmed, also from a
shell that starts in that state with the token of the 503, axe in both
themes at 1280 px and 320 px, 44 px targets)
and `e2e/smoke/session.spec.ts` (real backend and Keycloak).

## Image configuration

The runtime image renders `frontend/nginx/default.conf.template` when the container starts. This
section is the one description of its rules; the chart, the guard and the tests refer to it.

### API path prefix

`OWLMAST_API_PATH_PREFIX` (image default `/api`) is published to the shell as
`/owlmast-config.json`, and the image answers 404 at and below it (a request there was misrouted).
The start-up guard `docker-entrypoint.d/16-owlmast-api-prefix.envsh` stops the container, with one
line that names the variable and the reason, unless the value:

1. is an absolute path of letters, digits, `.`, `_`, `~`, `-` and `/`, with no empty, `.` or `..`
   segment (one trailing slash is dropped);
2. is not the root `/`;
3. is not, and does not lie below, a path the image serves itself: `/assets`,
   `/owlmast-config.json`, `/api-compatibility.json` and every file or directory of the build output
   (`/index.html`, `/theme-boot.js`, `/owl-mark.svg`, ...);
4. does not start with a page of the shell: `/focus`, `/knowledge`, `/connections`, `/usage`,
   `/preferences` (first path segment, case-sensitive; `src/app/destinations.test.ts` fails when the
   guard's list and `DESTINATIONS` differ).

A refusal under rule 1 ends with the character rule; a refusal under rules 2 to 4 names what the
value collides with and what to choose instead. The shell applies rules 1 and 2 itself and falls back
to `/api` (`src/api/config.ts`).

Where the value can come from: the chart passes `routing.apiPathPrefix` and nothing else to the
container, and refuses at render time every value other than exactly `/api` (the backend serves only
`/api` and no rewrite is rendered), so a prefix the image would refuse never reaches a pod
(`deploy/tests/test_chart_render.py`, `test_a_prefix_the_frontend_image_refuses_never_reaches_it`).
The guard matters for a container started by hand or by another deployment tool.

### Adding a templated variable

The base image substitutes environment variables into the template with `envsubst`. The Dockerfile
sets `NGINX_ENVSUBST_FILTER=^OWLMAST_`, so only variables whose names start with `OWLMAST_` are
substituted and nginx's own variables (`$uri`, `$status`, `$owlmast_asset_cache_control`) reach nginx
unchanged, whatever the container environment holds. To add one:

1. Name it `OWLMAST_<NAME>` (upper case; nginx's own variables in the template stay lower case).
2. Give it a default in `frontend/Dockerfile` (`ENV OWLMAST_<NAME>=...`). A variable that is not set
   at all is not replaced by an empty string: the text stays, nginx reads it as an unknown variable of
   its own and the container does not start. A variable set to an empty value (`-e OWLMAST_<NAME>=`)
   is substituted as empty, so step 4 must refuse it where empty is not valid (the prefix guard does).
3. Use it in the template as `${OWLMAST_<NAME>}`.
4. Validate it before the template is rendered if it ends up inside an nginx string or a JSON
   document: add a guard next to `16-owlmast-api-prefix.envsh` (the entrypoint sources `*.envsh`
   files in order before `20-envsubst-on-templates.sh`), and copy it with `--chmod=0755`.
5. If the chart should set it, add it to `deploy/helm/owl-mast/templates/frontend-deployment.yaml`
   with a render test.

`scripts/verify-frontend-artifact.sh` checks that every `OWLMAST_` variable the template names has a
Dockerfile default, that the rendered configuration contains no unexpanded `${OWLMAST_...}`, that an
unset one stops the container, and that nginx's variables survive a container environment that defines
`status`, `uri` and `owlmast_asset_cache_control`.

### Headers, caching and ranges

Every location includes `nginx/owlmast-headers.conf` (nginx does not inherit `add_header` across
levels) and sets its own `Cache-Control`: `no-store` everywhere, except that an answer under
`/assets/` that carries the hashed file (200, 304) is immutable for a year.

Range requests are answered (206), one range per request (`max_ranges 1`; a request for several is
answered whole), except under `/assets/`. nginx adds the headers before its range
filter runs and again when it sends the error answer, so an unsatisfiable range answered in place
would carry every header twice. The template therefore sends the 416 from a named location that adds
nothing: the answer keeps the headers already written, once each, with `no-store`. Under `/assets/`
the header already written is the immutable policy, which stock nginx cannot take back, so ranges are
off there (`max_ranges 0`) and a hashed asset is always sent whole. Do not add `add_header` to the
named location or at server level.

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

- **Project authorization** is not implemented (OM-02.02). Sign-in is (OM-02.01, see
  [Session](#session-om-0201)): a signed-in person still has no authorized project, the scope bar and
  the first-use states say so, and the shell makes no protected fetch besides sign-out.
- **The session is polled, not pushed.** A session that ends at the identity provider is noticed at
  the next session read (focus, visibility, reconnect, every 60 s while the page is visible) or at the next protected call that
  answers 401, whichever comes first; until then the page keeps what it showed. The backend denies
  every protected call in that interval, so nothing new is disclosed.
- **A failed session read removes protected content** (fail closed), also when the cause is a short
  network fault: the person sees "The session could not be checked" with a Retry, and the next
  successful read restores the signed-in view. Sign-out stays available in the header meanwhile.
- **Sign-in returns to `/`**, not to the destination the person started from.
- **Push** is not offered or requested (UI/push gate, first E15 story). Preferences shows an
  unsupported state instead of a control.
- **Real authenticated journeys** beyond sign-in and sign-out arrive with the rest of E02 and E18;
  the smoke proves the public descriptor, the readiness probe and one login/return/sign-out run
  against a real Keycloak with a synthetic realm and user.
- **ESLint 9.39.5** is pinned because `eslint-plugin-jsx-a11y` has no ESLint 10 release; the registry
  marks 9.x as unsupported. Re-pin to ESLint 10 when jsx-a11y supports it, or replace the static
  rules with the rendered axe checks already in place.
- **Qualified browser**: Chromium 1248 (Playwright 1.64.1) on Linux x86_64 only. Firefox/WebKit, real
  assistive technology and phone devices are not exercised; the 320 px/200 % checks are emulated.
- **Kind deployment of the frontend image** (chart `frontend.enabled=true`) is not performed in this
  story; `scripts/verify-frontend-artifact.sh` proves the container contract and the chart tests
  already render the frontend Deployment/Service and routes.
