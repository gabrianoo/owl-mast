---
epic: E01
status: planned
review_status: pending-owner-review
scope: v1
---

# Epic E01 — Install and operate a reproducible Owl Mast workspace

An operator can build, start and inspect a reproducible deployment with the agreed engineering standards.

**Epic prerequisites:** None

This is a planning draft. [Full scope and shared requirements](../../epics.md) apply to every story. Tasks are ordered within a story; its acceptance criteria determine completion. Policy decisions and live-environment approvals remain explicit gates.

**Reconciliation of 2026-11-12 (drafted, owner decides).** After the [E01 retrospective](../../../implementation-artifacts/epic-1-retro-2026-11-12.md), two kinds of change were drafted here. Neither changes execution status, which stays in GitHub:

- **E01-R-09, accepted deviations.** Where an acceptance criterion was met under an interpretation the text did not record, the criterion now states what was built. Each such criterion carries a line starting "**Accepted deviation — pending owner confirmation**" with the original wording and the reason. The owner may reject any of them; rejecting OM-01.02 AC2 changes the epic's acceptance verdict.
- **E01-R-08, OM-01.03 review threads.** The 47 review threads left open on [PR #110](https://github.com/gabrianoo/owl-mast/pull/110) were triaged. OM-01.03's criteria and tasks below include the resulting clarifications; each states only what the merged code does and its tests show. The proposed disposition of each thread is in [e01-r08-pr110-thread-dispositions.md](../../../implementation-artifacts/e01-r08-pr110-thread-dispositions.md). The threads themselves are untouched on GitHub.

<a id="om-01-01"></a>

### OM-01.01 — Bootstrap the supported Java application

As a maintainer, I want to build a minimal runnable modular application, so that subsequent features share one verified toolchain.

**Requirements:** FR-20, AR-01, AR-02, AR-03, AR-04

**Depends on:** None

**Acceptance criteria:**

- **AC1: Given** a clean checkout and supported toolchain, **when** the documented build runs, **then** Java 27 application code and Spring Boot 4.1.2 compile through Gradle Kotlin DSL and a minimal health endpoint starts.
- **AC2: Given** a deliberately invalid module dependency or formatting/static-analysis violation, **when** CI runs, **then** the relevant gate fails with a useful diagnostic; feature packages own interfaces and persistence.
- **AC3: Given** reactive request and database paths, **when** context crosses asynchronous boundaries, **then** tenant/security context is explicit and blocking adapters are bounded; no ThreadLocal-only authorization assumption is introduced.
- **AC4: Given** a supported local/CI container runtime, **when** the foundational integration suite runs, **then** Testcontainers starts an isolated PostgreSQL/VectorChord image with its required pgvector dependency, exercises the actual migration/transaction path and cleans up; missing extension support or an unavailable required test runtime fails explicitly.

**Tasks:**

- [ ] **OM-01.01-T1** Qualify and pin Gradle/JDK/Lombok/formatter/analyzer/Testcontainers compatibility and the local/CI container runtime; record evidence and dependency locks without copying stale ConvaDesk pins.
- [ ] **OM-01.01-T2** Create the minimal Spring application and feature/module convention with explicit ports; create only bootstrap-owned schema objects.
- [ ] **OM-01.01-T3** Configure formatting, static analysis, dependency/architecture verification and CI build gates; document focused Lombok/records and functional composition conventions.
- [ ] **OM-01.01-T4** Establish reusable Testcontainers PostgreSQL/VectorChord fixtures with pinned images and required extension configuration; exercise clean build/start, actual migrations and a representative reactive transaction/context test, and publish developer/CI commands.

<a id="om-01-02"></a>

### OM-01.02 — Install optional state and identity dependencies

As a operator, I want to install Owl Mast with bundled or existing dependencies, so that a home-server or AWS Kubernetes environment can run the same product.

**Requirements:** FR-20, AR-05, AR-09, AR-12, AR-13

**Depends on:** OM-01.01

**Acceptance criteria:**

- **AC1: Given** a qualified Kubernetes/storage target, **when** the documented package is installed with bundled dependencies, **then** PostgreSQL with VectorChord and Keycloak have explicit health/readiness and durable-volume configuration.
- **AC2: Given** either bundled dependency is disabled, **when** external connection values are supplied, **then** the application uses that compatible instance; missing values fail validation; and disabling the identity bundle does not remove the identity requirement: no value turns it off, and the backend stays not ready until the configured issuer serves an OpenID Connect discovery document that names that issuer.
  - **Accepted deviation — pending owner confirmation** (E01-R-09, retrospective R3). Original wording: "disabling the bundle does not disable authentication". As built, the identity provider is a readiness requirement (`IdentityDiscoveryHealthIndicator`, `IdentityReadinessIT`), not request authentication: the backend has no Spring Security dependency and authenticates no request in E01. Request authentication, sessions and origins belong to OM-02.01. Lesson recorded by the retrospective: when a criterion uses a capability that does not exist yet, name the story that enforces it.
- **AC3: Given** PostgreSQL is shared for the POC, **when** applications connect, **then** Owl Mast and Keycloak use separate databases and separate login principals; each principal has no superuser, create-database, create-role or replication attribute, owns its own database, and can connect to no other (`PUBLIC` loses `CONNECT`); VectorChord is installed by the provisioning identity, a `vchordrq` index is used on synthetic vectors, and pgvector remains only its allowed dependency.
  - **Accepted deviation — pending owner confirmation** (E01-R-09, retrospective R4). Original wording: "separate databases/principals and restricted grants; VectorChord indexes are used". As built, isolation is between the two principals and their databases, not least privilege inside a database: each principal owns its database and therefore holds every right in it (the application role creates and migrates its own schemas). On an external shared server the chart cannot inspect the principals an operator supplies; it warns that it does not check them. Table-level grants, a separate migration role and row-level security are deferred (deferred-work ledger: append-only audit history, tenant RLS).
  - Not a deviation, recorded for the same criterion (retrospective R5): "VectorChord indexes are used" is shown by the Kind qualification on a synthetic table as the application principal. No product migration creates a vector index yet; the first story that does (E03/E04) adds the index and a lint that refuses `hnsw`/`ivfflat`.

**Tasks:**

- [ ] **OM-01.02-T1** Select and document the installation packaging and compatible immutable image/chart pins; validate optional-dependency values and existing-secret references.
- [ ] **OM-01.02-T2** Package the backend and independently optional PostgreSQL/VectorChord and Keycloak with probes, resources and external connection settings; define separate frontend deployment/image/routing values for the shell artifact delivered by OM-01.04.
- [ ] **OM-01.02-T3** Configure persistent-volume ownership and safe upgrade/uninstall retention behavior; leave snapshot cadence/provider decisions explicit.
- [ ] **OM-01.02-T4** Validate bundled/bundled, bundled/external, external/bundled and external/external configurations using synthetic data; check independent frontend/backend image and routing values, then publish secret-free examples. Complete the real frontend artifact smoke check in OM-01.04.

<a id="om-01-03"></a>

### OM-01.03 — Recover accepted background work and record mutation evidence

As a operator, I want to recover committed processing after pod replacement, so that accepted work is not lost when the single application instance restarts.

**Requirements:** FR-3, NFR-3, NFR-6, AR-02, AR-07, AR-11, UX-DR51

**Depends on:** OM-01.01

**Acceptance criteria:**

- **AC1: Given** a test-owned fixture module that changes its own business row and enqueues follow-up work through the jobs owner API in one scoped transaction, **when** that transaction commits, or rolls back for any reason, including an error raised after the enqueue call or a cancelled subscription (which is also how a timeout ends it), **then** the business row and the work record both exist after commit and neither exists after rollback.
  - An enqueue or an audited mutation without a bound tenant scope is rejected before any write.
  - Atomicity comes from composing the business change and the enqueue in one scoped transaction. An enqueue called outside any transaction opens its own and commits alone; the API cannot tell that a business change was meant to accompany it.
- **AC2: Given** pending work, with either two processors claiming it concurrently or a lease that expires before its holder finishes, **when** work is claimed, reclaimed and completed, **then**:
  - each item has at most one current lease holder;
  - a completion or failure write from a holder whose lease expired or was reclaimed is rejected and changes nothing;
  - a repeated external effect after reclaim either is applied once through an idempotency key derived from the work item, or leaves the item in an explicit outcome-uncertain state. An outcome-uncertain item is terminal: it is not retried automatically, it appears in the operator failure listing (AC5) with that state, and its reconciliation belongs to OM-16.05;
  - no item is marked succeeded without a recorded effect outcome;
  - every lease, expiry and next-attempt comparison uses the database clock, never an application instance's clock; lease duration, attempt limit and backoff defaults are stated in the contract, and a test fails when the document and the code disagree;
  - there is no lease renewal in v1: a handler must finish within its handler deadline, which is shorter than the lease, and is cancelled when it does not (renewal is deferred).
- **AC3: Given** a covered mutation (any mutation made through the audited-mutation API; later feature stories declare which of their mutations are covered), **when** its business transaction commits, **then** a durable audit-publication intent commits in the same transaction. The envelope carries:
  - envelope version and event ID;
  - actor kind (human, agent, service, or system) and actor ID (or explicit Unknown);
  - tenant;
  - project (or explicit Unknown until OM-02.02 supplies project identity);
  - object type, ID, and version;
  - action and outcome;
  - a safe reason (an exception class chain or a fixed code, never exception text or request data);
  - occurred and recorded times, both with timezone;
  - correlation ID.

  The envelope has no free-form payload field, and a secret value planted in the business input appears in no audit row, work record, persisted failure reason, operator listing or log line.
  - **Given** a business transaction that rolls back or an operation that is denied, **when** the outcome is recorded, **then** a failed or denied outcome record commits in a separate transaction, survives the rollback, and creates no business row and no succeeded record. If that separate write itself fails, the caller still receives the original error unchanged, the write failure is logged without secrets, and the outcome path never turns a failure into a success.
  - Not in the v1 envelope: a causal-event reference and a corrects/supersedes link, which OM-16.01 and EXPERIENCE.md expect. They are optional additions under the contract's compatibility rule and belong to OM-16.01; records written before then carry the correlation ID only. Rows written with project Unknown need a visibility rule from OM-02.02 and OM-16.01 (tenant-level operators only, or a backfill); neither story states one yet.
- **AC4: Given** a fault injected after a covered mutation's transaction commits and before its audit intent is published, **when** recovery runs, including running twice, **then** exactly one audit record for that event ID exists in the audit-owned history and can be read through the audit module's internal query API; and for every fixture mutation committed in the test, once the publisher has run, the history holds its record (no committed covered mutation is left without one).
  - A committed intent is never abandoned for lack of attempts: its publish item is retried, with capped backoff, until it is published. A publish item that cannot name an intent (missing or malformed event ID, no intent for the tenant) fails terminally and appears in the failure listing.
- **AC5: Given** a handler that fails, **when** it is retried, **then** attempt count, next-attempt time from a capped backoff, and a safe failure reason persist across restarts; after the configured maximum number of attempts (default stated in the contract), the item enters a terminal failed state. An operator can list terminal items (failed, denied and outcome-uncertain) for the bound tenant, with tenant, work type, attempt count, and safe reason but not payload contents.
  - The safe reason is the exception class chain or a fixed reason code, never exception text.
  - Invalid retry configuration (an attempt limit below 1, a backoff cap below its base, a handler deadline not shorter than the lease) fails application startup.
  - As built, the listing requires a bound tenant scope and returns only that tenant's items; it does not consult an authorization port, because none exists before OM-02.04 (deferred-work ledger; retrospective R8).
- **AC6: Given** non-terminal work and unpublished audit intents exist when the application process stops, **when** a new application instance starts against the same database, **then**, without manual action and within a bound stated in the test, each item reaches a terminal state (succeeded, failed, denied) or the outcome-uncertain state, and every unpublished intent is published. This story proves process restart with Testcontainers only; live Kubernetes pod-replacement qualification belongs to OM-18.02 (AC2, T3), and this story claims no Kubernetes recovery support. OM-18.02 names ingest, normalization and notification work; recovery of unpublished audit intents after pod replacement is not yet named there.
  - An item whose work type no handler of the running build registers, or whose contract version is newer than the build reads, is not claimed: it stays pending for an instance that can run it, and is neither failed nor dropped.
- **AC7: Given** the authorization recheck port at dispatch, **when** it denies, **then** the handler is not invoked and the item becomes terminal denied with a safe reason and is listed; **when** it cannot decide (an undecided answer, an error, or no answer in time), **then** the handler is not invoked and the item is released: back to pending with the reason `authorization-undecided`, the attempt not counted, and consecutive releases backed off like failed attempts. Until OM-02.04 supplies the real port, the default allows only handlers registered as tenant-internal system work and denies all others.
  - **Accepted deviation — pending owner confirmation** (E01-R-09, retrospective R9). Original wording: "the handler is not invoked and the item records a safe denied or blocked outcome". As built, "blocked" is not a recorded state: an undecided recheck leaves the item pending and retried, so an outage of the deciding component never exhausts an item's attempts. A dispatch denial marks the work item; it writes no separate audit record.
  - Who may register as tenant-internal system work is decided by the jobs owner, not by the handler: the jobs module keeps a closed list of the work types that hold the privilege (initially the audit-intent publisher only), a handler that registers that way for any other type stops the application at startup, and a module rule keeps the list out of reach of other feature modules. The audit-intent publisher is dispatched through the same recheck as any other handler, so a denial or an undecided answer leaves its intent unpublished, never dropped.
- **AC8: Given** work and audit records for two synthetic tenants, **when** processors claim and the audit query runs under one tenant's scope, **then** each record is processed only under its own tenant's scope and none is returned or completed under the other's.
- **AC9: Given** a later feature module, **when** it enqueues work or records audit, **then** it can do so only through the published, versioned work-item and audit-envelope contracts (Java API types plus a contract document with a compatibility rule for added fields and versions), enforced by module-rule and compatibility tests; processors are woken only by in-process Spring scheduling, with no external scheduler, broker or worker service.
  - The compatibility test compares the published types with a committed snapshot of the v1 shape and fails on a removed, renamed or retyped member.

**Tasks:**

- [ ] **OM-01.03-T1** Define and document the versioned durable-work and audit-envelope contracts (the fields listed in AC3; outcome and actor-kind vocabularies aligned with OM-16.01; a compatibility rule for added fields and versions), the audited-mutation and enqueue owner APIs, the backend service identity used by processors, and the authorization recheck port with its fail-closed default.
- [ ] **OM-01.03-T2** Implement only the jobs- and audit-owned infrastructure tables; an atomic commit of the business change, work record, and audit intent through module APIs and reactive transaction integration; the idempotent audit-intent publisher; and failed/denied outcome recording in a separate transaction independent of rolled-back business writes.
- [ ] **OM-01.03-T3** Implement tenant-scoped bounded claiming, lease expiry and reclaim, persisted retry/backoff with terminal failure, an operator failure listing without payloads and the dispatch-time authorization recheck; wake processors with in-process Spring scheduling only.
- [ ] **OM-01.03-T4** Exercise AC1–AC9 with Testcontainers PostgreSQL and a test-owned fixture module:
  - rollback before and after enqueue, and a cancelled subscription;
  - a fault-injected crash after commit and before audit publication, with repeated recovery;
  - failed and denied attempt recording, including a failing separate outcome write;
  - secret non-disclosure, including the persisted failure reason and the operator listing;
  - stale-owner completion, concurrent claims and duplicate effect recovery;
  - retry exhaustion and invalid retry configuration;
  - process-restart recovery;
  - fail-closed authorization, including a handler that registers itself as tenant-internal system work;
  - two-tenant isolation, including the operator listing;
  - the module rules and the compatibility test against the committed v1 snapshot (AC9).

<a id="om-01-04"></a>

### OM-01.04 — Open an accessible workspace shell

As a contributor, I want to navigate a consistent responsive workspace, so that feature views can be added without losing scope, readability or accessibility.

**Requirements:** FR-15, FR-20, NFR-5, AR-02, AR-04, AR-12, UX-DR01, UX-DR02, UX-DR03, UX-DR04, UX-DR05, UX-DR06, UX-DR07, UX-DR08, UX-DR09, UX-DR25, UX-DR26, UX-DR27, UX-DR28, UX-DR40, UX-DR42

**Depends on:** OM-01.01

**Acceptance criteria:**

- **AC1: Given** the UI framework decision is recorded, **when** the shell is rendered, **then** the accepted owl asset and exact light/dark tokens, typography, spacing and system-theme override are preserved.
- **AC2: Given** keyboard, screen reader or enlarged-text interaction, **when** navigation or a dialog changes context, **then** title/focus/labels/return behavior remain usable at 320px and at 200% text size with visible 44px controls; in E01 this is checked in Chromium with automated accessibility rules (axe, WCAG 2.2 AA) and role/name queries.
  - **Accepted deviation — pending owner confirmation** (E01-R-09, retrospective R7). Original wording: "remain usable at 320px and 200% zoom" for "keyboard, screen reader or enlarged-text interaction". As built, 200% is emulated by doubling the root font size (alone and combined with 320 px and 640 px widths), not by browser zoom; "screen reader" is evidenced by axe rules and by queries on accessible roles and names, not by a run with assistive technology; the browser suite runs in Chromium only. Real assistive-technology runs and other browsers are in E18.
- **AC3: Given** a route is loading, offline, denied or unsupported, **when** its state changes, **then** distinct safe messages appear, protected content is not newly exposed from cache, and pending operations never show invented success.
- **AC4: Given** separately packaged frontend and backend artifacts, **when** a supported frontend/backend version pair is built, tested or deployed, **then** neither requires bundling the UI into the backend image; the documented API compatibility policy is checked for the pair in a checkout by CI, and for a candidate pair of deployed artifacts by a documented check the operator runs before rollout, which reports an incompatible pair.
  - **Accepted deviation — pending owner confirmation** (E01-R-09, retrospective R6). Original wording: "the documented API compatibility policy is checked and incompatible pairs are detected before rollout". As built, CI checks only the static pair of the checkout; detecting an incompatible pair of deployed artifacts depends on the operator running `scripts/check-api-compatibility.py --frontend-url … --backend-url …` (docs/api-compatibility.md). Nothing runs it automatically, and the verdict the shell computes at run time is displayed but gates nothing. An automatic pre-rollout check and gating protected features on the verdict are deferred (deferred-work ledger, PR #112 threads).

**Tasks:**

- [ ] **OM-01.04-T1** Qualify the recommended React/TypeScript/Vite seed and pins; create the independent frontend build/test/image pipeline and API compatibility policy, retaining browser authentication/origin and push support as explicit qualification gates.
- [ ] **OM-01.04-T2** Implement shell navigation, scope/period context, accepted logo, theme/tokens and common settings/state/action/link primitives.
- [ ] **OM-01.04-T3** Implement focus restoration, accessible loading/error/empty patterns and stable New updates interaction primitives.
- [ ] **OM-01.04-T4** Validate component behavior, API contract compatibility, independent frontend/backend build artifacts and a focused browser-to-backend smoke path; check contrast, keyboard flow, screen-reader labels, reduced motion and responsive layouts against DESIGN.md. Real authenticated journeys follow in E02/E18.
