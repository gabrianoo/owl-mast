# Owl Mast task index

**Planning draft: 19 epics, 85 stories, 340 tasks.** All are planned; none are implemented by this work.

[Full scope, requirements, sequencing and decision gates](../../epics.md) · [Validation and story coverage](VALIDATION.md)

The epic files are authoritative for acceptance criteria, prerequisites and task state. This index is a generated navigation view. Implementation tasks inherit their story's prerequisites; tasks within a story are ordered unless explicitly independent. The full plan's explicit qualification/contract-design exception permits only the designated design portion to run early against documentation or synthetic fixtures; production implementation and story completion retain their prerequisites. E19 is planned later evolution; E17 is optional T3 enrichment. Full native standalone and T3-hosted Claude/Codex support is planned in E07/E08, independently of E17.

## E01 — Install and operate a reproducible Owl Mast workspace

### [OM-01.01 — Bootstrap the supported Java application](epic-01.md#om-01-01)

Prerequisites: None

- **OM-01.01-T1** — Qualify and pin Gradle/JDK/Lombok/formatter/analyzer/Testcontainers compatibility and the local/CI container runtime; record evidence and dependency locks without copying stale ConvaDesk pins.
- **OM-01.01-T2** — Create the minimal Spring application and feature/module convention with explicit ports; create only bootstrap-owned schema objects.
- **OM-01.01-T3** — Configure formatting, static analysis, dependency/architecture verification and CI build gates; document focused Lombok/records and functional composition conventions.
- **OM-01.01-T4** — Establish reusable Testcontainers PostgreSQL/VectorChord fixtures with pinned images and required extension configuration; exercise clean build/start, actual migrations and a representative reactive transaction/context test, and publish developer/CI commands.

### [OM-01.02 — Install optional state and identity dependencies](epic-01.md#om-01-02)

Prerequisites: OM-01.01

- **OM-01.02-T1** — Select and document the installation packaging and compatible immutable image/chart pins; validate optional-dependency values and existing-secret references.
- **OM-01.02-T2** — Package the backend and independently optional PostgreSQL/VectorChord and Keycloak with probes, resources and external connection settings; define separate frontend deployment/image/routing values for the shell artifact delivered by OM-01.04.
- **OM-01.02-T3** — Configure persistent-volume ownership and safe upgrade/uninstall retention behavior; leave snapshot cadence/provider decisions explicit.
- **OM-01.02-T4** — Validate bundled/bundled, bundled/external, external/bundled and external/external configurations using synthetic data; check independent frontend/backend image and routing values, then publish secret-free examples. Complete the real frontend artifact smoke check in OM-01.04.

### [OM-01.03 — Recover accepted background work and record mutation evidence](epic-01.md#om-01-03)

Prerequisites: OM-01.01

- **OM-01.03-T1** — Define the durable-work and minimal audit-envelope contracts, owner APIs and versioning rules consumed by later modules.
- **OM-01.03-T2** — Implement only the work/audit infrastructure tables, atomic business-change/work/audit-intent commit through module APIs and reactive transaction integration; keep failed-attempt audit independent of rolled-back business writes.
- **OM-01.03-T3** — Implement bounded claiming, lease recovery, retry/backoff, failure visibility and authorization recheck hooks; schedule wakeups without an external job service.
- **OM-01.03-T4** — Exercise rollback-before-enqueue, crash-after-commit-before-audit-publication, failed-attempt recording, stale-owner completion, concurrent claims and duplicate effect recovery.

### [OM-01.04 — Open an accessible workspace shell](epic-01.md#om-01-04)

Prerequisites: OM-01.01

- **OM-01.04-T1** — Qualify the recommended React/TypeScript/Vite seed and pins; create the independent frontend build/test/image pipeline and API compatibility policy, retaining browser authentication/origin and push support as explicit qualification gates.
- **OM-01.04-T2** — Implement shell navigation, scope/period context, accepted logo, theme/tokens and common settings/state/action/link primitives.
- **OM-01.04-T3** — Implement focus restoration, accessible loading/error/empty patterns and stable New updates interaction primitives.
- **OM-01.04-T4** — Validate component behavior, API contract compatibility, independent frontend/backend build artifacts and a focused browser-to-backend smoke path; check contrast, keyboard flow, screen-reader labels, reduced motion and responsive layouts against DESIGN.md. Real authenticated journeys follow in E02/E18.

## E02 — Manage tenants, personal accounts and authorized project access

### [OM-02.01 — Sign in with a personal Owl Mast identity](epic-02.md#om-02-01)

Prerequisites: E01

- **OM-02.01-T1** — Resolve realm/client, account invitation/registration and browser login/session/recovery policy for separate frontend/backend deployments; explicitly select the public-origin/routing boundary without inferring it from deployment separation.
- **OM-02.01-T2** — Configure Keycloak and reactive resource-server/login integration for the selected browser model, including redirect/proxy handling, cookie/token boundaries, applicable CSRF/CORS controls and revocation; keep native enrolled credentials separate.
- **OM-02.01-T3** — Implement principal lifecycle and safe sign-in/out/error states in the shell; preserve source-account separation.
- **OM-02.01-T4** — Use Testcontainers with a pinned Keycloak image and synthetic realm/users to exercise browser login/return across separately packaged services, wrong issuer/audience, expiration, logout/revocation and recovery; ensure diagnostics exclude credentials and apply the selected origin/CSRF policy.

### [OM-02.02 — Create tenant and project membership boundaries](epic-02.md#om-02-02)

Prerequisites: OM-02.01

- **OM-02.02-T1** — Define tenant/project/member identity and schema constraints; qualify transaction-bound PostgreSQL isolation for reactive access.
- **OM-02.02-T2** — Implement authorized project/tenant administration APIs and S8 scope management with audit events.
- **OM-02.02-T3** — Propagate trusted scope across HTTP, MCP, jobs and connection boundaries; reject client-asserted scope escalation.
- **OM-02.02-T4** — Exercise synthetic two-tenant, cross-project, revoked membership and identical-key isolation cases.

### [OM-02.03 — Map shared external accounts without merging people](epic-02.md#om-02-03)

Prerequisites: OM-02.02

- **OM-02.03-T1** — Implement source-qualified external-account bindings with purpose, authority, effective times and provenance.
- **OM-02.03-T2** — Keep connector credential references separate from user mapping and project visibility grants.
- **OM-02.03-T3** — Provide audited mapping administration and clear shared-account/unknown attribution presentation.
- **OM-02.03-T4** — Verify same visibility for explicitly granted users without granting all connector-visible records to all members.

### [OM-02.04 — Enforce resource and source permissions through one boundary](epic-02.md#om-02-04)

Prerequisites: OM-02.02

- **OM-02.04-T1** — Define the authorization port and initial membership/source-resource grant model with a documented owner of authoritative grants.
- **OM-02.04-T2** — Implement policy checks and revocation invalidation boundaries for feature APIs, jobs, MCP and query projections.
- **OM-02.04-T3** — Add reusable negative fixtures for both project directions, unauthorized third user, revoked user and restricted same-project source.
- **OM-02.04-T4** — Verify no permission fallback to company scope, no hidden counters/filter options and no execution capability in public contracts.

### [OM-02.05 — Approve collection boundaries before enabling live sources](epic-02.md#om-02-05)

Prerequisites: OM-02.04

- **OM-02.05-T1** — Record the adopted full-conversation default and resolve A-3's remaining actual-environment permissions, destinations and archive/other-record policies before live customer ingestion; do not invent retention durations.
- **OM-02.05-T2** — Implement versioned collection policy and activation gates shared by connectors, native telemetry and knowledge ingestion.
- **OM-02.05-T3** — Implement default-on conversation capture with project disable/narrow controls for prompts, responses, tool arguments/results and query/context fields; distinguish configured capture from live-source activation and verified coverage.
- **OM-02.05-T4** — Exercise default-on capture, project opt-out and deny/redact behavior through logs, receipts, queues, caches and derived summaries; emit safe policy audit events without conversation bodies.

## E03 — Capture and maintain versioned project knowledge

### [OM-03.01 — Submit project knowledge with immutable version identity](epic-03.md#om-03-01)

Prerequisites: E02

- **OM-03.01-T1** — Add only knowledge item/version, source-qualified submission identity and typed exact-version source/derivation lineage needed for capture; preserve source ownership, applicability, actor/time/evidence basis and explicit missing lineage.
- **OM-03.01-T2** — Implement the authorized submission boundary, collection exclusions and transactional deduplication/version creation through the selected persistence adapters.
- **OM-03.01-T3** — Emit safe creation/failure/correction audit events with actor, project, exact version, outcome and both timestamps for later audit consumption.
- **OM-03.01-T4** — Verify same-key cross-source isolation, duplicate replay, corrected versions, revoked source access and excluded-content handling; record the A-3 pre-live gate.

### [OM-03.02 — Preserve complete versioned skill packages](epic-03.md#om-03-02)

Prerequisites: OM-03.01

- **OM-03.02-T1** — Implement package manifest/file/checksum records and the exact-version association to knowledge records, without adding schemas for unrelated future artifacts.
- **OM-03.02-T2** — Implement completeness, path, content-policy and integrity validation; store supplied scripts as data without executing them.
- **OM-03.02-T3** — Qualify and record storage for large/binary package files against the selected PostgreSQL deployment and permitted external-storage option if needed, including removal and restore boundaries.
- **OM-03.02-T4** — Verify complete packages, changed assets, incomplete imports, corrupt checksums, prohibited content and cross-project package denial.

### [OM-03.03 — Synchronize permitted Notion knowledge and preserve Hermes capture](epic-03.md#om-03-03)

Prerequisites: OM-03.01, OM-03.02

- **OM-03.03-T1** — Inspect the real permitted Hermes-to-Notion capture and source schema, document ownership/write responsibilities and qualify the available Notion synchronization interface before connector implementation.
- **OM-03.03-T2** — Implement the scoped Notion adapter with protected credential references, durable synchronization/reconciliation jobs, source-version conflict handling and safe connection health.
- **OM-03.03-T3** — Map authorized source lessons and complete skills to the existing knowledge/package contracts, preserving source links without bulk migration or duplicate manual capture.
- **OM-03.03-T4** — Verify authorized Hermes capture continuity and Claude/Codex page creation separately from skill reading, plus restart, duplicate, late-edit and source-revocation cases; gate live content on A-3.

### [OM-03.04 — Evaluate and correct project knowledge lifecycle states](epic-03.md#om-03-04)

Prerequisites: OM-03.01, OM-03.02

- **OM-03.04-T1** — Implement exact-version evaluation, conflict, supersession, withdrawal and quarantine records with permission-checked transitions and append-linked corrections; preserve distinct validation/policy, derivation and supersession lineage rather than rewriting prior versions.
- **OM-03.04-T2** — Expose a current-eligibility query and lifecycle-change event contract usable by retrieval/publication adapters without depending on those later consumers.
- **OM-03.04-T3** — Implement concurrent-version guards and safe audit events for requested, successful, denied and failed lifecycle changes.
- **OM-03.04-T4** — Verify conflicting versions, stale decisions, revoked maintainer/source access, correction history and the adopted A-1 default/explicit-client opt-in; verify adopted A-2 withdrawal/derivative behavior and preserved restricted lineage.

### [OM-03.05 — Browse and maintain knowledge in the scoped catalog and detail UI](epic-03.md#om-03-05)

Prerequisites: OM-03.03, OM-03.04

- **OM-03.05-T1** — Build authorized catalog/detail read models and bounded filters from the knowledge module, including source lineage, exact versions and package completeness.
- **OM-03.05-T2** — Implement S3/S4 submission, lifecycle review and history presentation using the shared accessible components and explicit save/result behavior.
- **OM-03.05-T3** — Add permission-safe loading, empty, stale, unsupported, failure and revoked-content states, retaining authorized route/filter context.
- **OM-03.05-T4** — Verify submission and maintenance journeys, restricted conflicts, duplicate privacy, keyboard/screen-reader access, both themes and phone reflow without relying on future statistics or promotion modules.

## E04 — Retrieve authorized knowledge through MCP

### [OM-04.01 — Build lexical and VectorChord retrieval over eligible knowledge](epic-04.md#om-04-01)

Prerequisites: E03

- **OM-04.01-T1** — Qualify VectorChord/type/operator versions, R2DBC query/codec support and query plans on the selected PostgreSQL stack; record any bounded blocking adapter rather than assuming a JDBC Spring AI vector store is reactive.
- **OM-04.01-T2** — Implement only the lexical/chunk/embedding/index-status records needed for exact-version knowledge, including model/index version and current-eligibility/source bindings.
- **OM-04.01-T3** — Add durable index/update/invalidation jobs and scoped hybrid retrieval with declared freshness and lexical-degradation behavior; qualify any embedding destination before sending content.
- **OM-04.01-T4** — Verify restricted-source exclusion, post-index revocation, withdrawn versions, duplicate/late jobs, embedding failure and authorization before any downstream model receives retrieved context.

### [OM-04.02 — Return authorized exact-version knowledge with honest coverage](epic-04.md#om-04-02)

Prerequisites: OM-04.01

- **OM-04.02-T1** — Implement Knowledge-owned versioned bounded search-summary and selected-version load contracts, delegating derived index/query work to Retrieval, with trusted scope, an explicit client-controlled unvalidated flag defaulting off, validation/provenance labels, pagination/coverage and safe empty/failure semantics.
- **OM-04.02-T2** — Apply current project/source/purpose authorization, validation opt-in and lifecycle eligibility consistently to search, exact-version reads, caches and UI adapters; scope cached results by eligibility mode and recheck current state.
- **OM-04.02-T3** — Emit minimal retrieval evidence and diagnostic/audit events through owned module contracts, preserving recipient disclosure and A-3 collection limits.
- **OM-04.02-T4** — Verify validated-only defaults, explicit unvalidated opt-in, direct-ID/cache bypass attempts, candidate/conflict labels, bounded search/load, no unsolicited context injection and existing cross-project/revocation/hidden-match privacy cases.

### [OM-04.03 — Expose authenticated remote MCP in the Spring backend](epic-04.md#om-04-03)

Prerequisites: OM-04.02

- **OM-04.03-T1** — Qualify the Java/Spring MCP server transport and Keycloak OAuth integration with actual Claude/Codex clients, including discovery, registration, token validation and token lifecycle; record any missing supported capability explicitly.
- **OM-04.03-T2** — Implement authenticated remote MCP search and selected-version load adapters in the reactive Spring backend, exposing the client eligibility flag and bounded responses while isolating blocking calls and preserving request context.
- **OM-04.03-T3** — Define the client-facing setup contract using endpoint and credential references; document direct-network requirements, reconnect limits and the boundary to later enrollment/client packaging.
- **OM-04.03-T4** — Verify issuer/audience/scope failures, revocation, cross-project access and supported-client knowledge calls; keep standalone and T3-hosted native adapter qualification in their own dependent epics without requiring T3 here.

### [OM-04.04 — Deliver complete exact-version packages with explicit receipts](epic-04.md#om-04-04)

Prerequisites: OM-04.02, OM-04.03

- **OM-04.04-T1** — Implement authorized manifest/file delivery through the knowledge contract with exact-version checksums, bounded responses and explicit partial/corrupt-transfer outcomes.
- **OM-04.04-T2** — Add Knowledge-owned recipient-bound delivery acknowledgment and idempotent receipt records, keeping retrieval, delivery and client-reported native loading as separate evidence types.
- **OM-04.04-T3** — Specify the client package-verification/native-activation boundary and current-eligibility/cache behavior consumed by the native Claude/Codex adapters; do not introduce remote execution tools.
- **OM-04.04-T4** — Verify multi-file completeness, replayed receipts, unsupported acknowledgments, concurrent permission loss and withdrawn cached versions; verify adopted A-2 lineage-preserving withdrawal and managed-cache behavior.

## E05 — Enroll executing machines and native agent clients

### [OM-05.01 — Register a machine and client without conflating identities](epic-05.md#om-05-01)

Prerequisites: E02, E04.

- **OM-05.01-T1** — Define separate machine/client/enrollment identifiers, required personal owner, configured-location fields and observation-reference contracts; distinguish responsible owner from evidenced initiator and preserve source namespaces.
- **OM-05.01-T2** — Implement authorized idempotent enrollment/update APIs and transactionally reliable audit events.
- **OM-05.01-T3** — Build S5 registration and configured-versus-observed location presentation, including Unknown and Stale states.
- **OM-05.01-T4** — Verify retry, duplicate-name, changed-location, cross-tenant/revocation and shared-machine personal isolation; reject ownerless/service-only native enrollment without inventing initiator attribution.

### [OM-05.02 — Bind enrolled clients to authorized projects and revocable credentials](epic-05.md#om-05-02)

Prerequisites: OM-05.01.

- **OM-05.02-T1** — Qualify person-bound Keycloak authentication/delegation across MCP, hooks and OTLP; document enrollment, rotation, expiry and revocation without unattended service-account enrollment or assuming every exporter refreshes OAuth credentials.
- **OM-05.02-T2** — Implement personal-owner/project/purpose bindings, secret-reference configuration and credential lifecycle endpoints; enforce the intersection of current user permissions and enrollment grants.
- **OM-05.02-T3** — Add project selection, repair/revoke and explicit save/error states to S5 without exposing credential values.
- **OM-05.02-T4** — Test forged project attributes, shared source accounts/machines, owner suspension, expired/revoked grants and audit/redaction across MCP/hooks/OTLP; deny service-identity fallback and keep ownership separate from observed actor evidence.

### [OM-05.03 — Show observation and knowledge readiness independently](epic-05.md#om-05-03)

Prerequisites: OM-05.02.

- **OM-05.03-T1** — Define capability and evidence-receipt status contracts consumed later by ingestion and native adapters; include configured/unknown/unsupported/stale states.
- **OM-05.03-T2** — Implement independent knowledge-connectivity probes and observation-status projection with declared freshness configuration.
- **OM-05.03-T3** — Build the connection-readiness component and S5 per-client/project details with configured and observed location labels.
- **OM-05.03-T4** — Verify status transitions with contract fixtures, partial source failures, expired authorization and absence of execution side effects.

### [OM-05.04 — Define portable native configuration packages and safe repair](epic-05.md#om-05-04)

Prerequisites: OM-05.02, OM-05.03.

- **OM-05.04-T1** — Specify versioned enrollment/package manifests and the MCP, hook and OTLP configuration contracts implemented separately in E07/E08.
- **OM-05.04-T2** — Build secret-free generated setup/readiness instructions and a runtime capability matrix for standalone and T3-hosted modes.
- **OM-05.04-T3** — Define scoped configuration merge, repair, disable/revoke and compatibility checks without editing live user environments during development.
- **OM-05.04-T4** — Validate generated fixtures against existing-settings, unavailable endpoint, unsupported capability and A-3-gated scenarios.

### [OM-05.05 — Personalize agent appearance without changing identity](epic-05.md#om-05-05)

Prerequisites: OM-05.01, OM-05.02.

- **OM-05.05-T1** — Record the proposed alias validation/personal ownership rules and keep any shared-alias policy as an explicit unresolved decision.
- **OM-05.05-T2** — Implement viewer/client-scoped appearance persistence, validation, save/reset and audit events.
- **OM-05.05-T3** — Build named color selection and alias preview in S5; retain fixed provider/type labeling and accessible agent chips.
- **OM-05.05-T4** — Test duplicate names, validation, failed saves, cross-viewer isolation, contrast and revocation.

## E06 — Receive and normalize native telemetry reliably

### [OM-06.01 — Bind collection to enrollment and the approved content policy](epic-06.md#om-06-01)

Prerequisites: E05

- **OM-06.01-T1** — Define the versioned ingress authentication, enrollment binding and purpose-scoping contract for OTLP and semantic observations.
- **OM-06.01-T2** — Implement the pre-persistence field allowlist/redaction pipeline and collection-policy gate, including A-3 decision evidence and protected credential references.
- **OM-06.01-T3** — Add fixtures for default-on conversation capture, project opt-out, scope forgery, revoked enrollment, secret-bearing fields, excluded content and diagnostic leakage.
- **OM-06.01-T4** — Record permitted receipt/rejection audit fields and a policy-change contract that prevents queued processing from restoring excluded content.

### [OM-06.02 — Accept the native OTLP wire protocols in Spring](epic-06.md#om-06-02)

Prerequisites: OM-06.01

- **OM-06.02-T1** — Implement the three proposed OTLP WebFlux routes using pinned official message definitions, content negotiation, gzip handling and configurable resource bounds; implement `/api/v1/observations` separately against the versioned semantic contract.
- **OM-06.02-T2** — Commit redacted acceptance records and scoped durable processing jobs atomically through the owning module's transaction boundary.
- **OM-06.02-T3** — Implement signal-specific success, partial-success and failure responses, including rate/backpressure handling and safe error messages.
- **OM-06.02-T4** — Verify all three signals with binary/JSON, compressed/uncompressed, empty, malformed, oversized and storage-failure fixtures; document full versus base endpoint URL rules.

### [OM-06.03 — Normalize evidence without inventing missing identity or capability](epic-06.md#om-06-03)

Prerequisites: OM-06.02

- **OM-06.03-T1** — Define Ingestion-owned normalized observation-envelope, metric-sample, trace-link, conversation-message and semantic-evidence input contracts with source-qualified IDs, roles, turn/tool relationships and explicit capability/content coverage.
- **OM-06.03-T2** — Implement adapter routing, schema/version compatibility and normalization into owned PostgreSQL records, including authorized conversation content and ordered references, without direct cross-module table writes.
- **OM-06.03-T3** — Preserve original units, accounting semantics, time windows and configured-versus-observed values for downstream usage calculations.
- **OM-06.03-T4** — Verify missing fields, identity collisions, model/location changes, unknown schemas, duplicate/out-of-order conversation messages, tool pairing and redacted/truncated/unavailable content using synthetic fixtures.

### [OM-06.04 — Recover accepted observations and suppress repeated accounting](epic-06.md#om-06-04)

Prerequisites: OM-06.03

- **OM-06.04-T1** — Implement one durable retry owner, lease recovery, bounded backoff, idempotent normalization and explicit terminal failure in the existing backend.
- **OM-06.04-T2** — Define per-signal source identity, replay detection and cross-channel reconciliation rules, including unknown identity and overlap behavior.
- **OM-06.04-T3** — Exercise crash-after-acceptance, crash-before-acknowledgment, duplicate batches, late samples, concurrent claims and revoked-scope recovery.
- **OM-06.04-T4** — Document native exporter limits, receiver guarantees and the evidence threshold for an optional persistent Collector, without making it a prerequisite.

### [OM-06.05 — Make ingestion health and coverage inspectable](epic-06.md#om-06-05)

Prerequisites: OM-06.04

- **OM-06.05-T1** — Expose authorized health and bounded receipt/processing history APIs with declared cadence and stale-state configuration.
- **OM-06.05-T2** — Implement connection-readiness and activity-list integration with separate signal and delivery coverage and persistent safe failure states.
- **OM-06.05-T3** — Verify per-signal failure isolation, field-level revocation, source/recorded times, accessible update handling and secret-free recovery diagnostics.

## E07 — Use Claude Code with Owl Mast in every supported execution mode

### [OM-07.01 — Package and qualify native Claude integration](epic-07.md#om-07-01)

Prerequisites: E06

- **OM-07.01-T1** — Define the supported Claude versions/modes and package manifest, configuration merge/repair contract and owned-file inventory.
- **OM-07.01-T2** — Build the native package/configuration integration with enrollment-bound credentials, secret references and reversible preservation of existing settings.
- **OM-07.01-T3** — Qualify actual standalone and installed T3 execution paths for MCP availability, hooks, exporter settings, supported fields and credential handling.
- **OM-07.01-T4** — Add setup failure/repair checks and document transport reachability and native offline-buffering limits without installing a mandatory daemon.

### [OM-07.02 — Deliver exact knowledge and native skill packages to Claude](epic-07.md#om-07-02)

Prerequisites: OM-07.01

- **OM-07.02-T1** — Implement the Claude MCP knowledge adapter and project-context selection using existing authorization and versioned knowledge contracts.
- **OM-07.02-T2** — Implement qualified native skill-package materialization/refresh with manifest validation, ownership boundaries and explicit eligibility/cache behavior.
- **OM-07.02-T3** — Preserve and verify authorized Notion creation/read paths independently of Owl Mast knowledge receipts and native skill activation.
- **OM-07.02-T4** — Verify client-driven bounded search/selected load, validated default and explicit unvalidated opt-in in both modes, plus empty/denied/conflicting results, package corruption, withdrawal, interrupted delivery and receipts; no unsolicited lesson injection or inference that managed revocation prevents independent use of retained copies.

### [OM-07.03 — Send Claude observations directly without controlling execution](epic-07.md#om-07-03)

Prerequisites: OM-07.01

- **OM-07.03-T1** — Implement non-controlling lifecycle/knowledge hooks with bounded failure behavior and supported native correlation fields.
- **OM-07.03-T2** — Generate separate log/metric/trace exporter configuration with protocol, endpoint semantics and trace opt-in; apply the adopted prompt/response/tool-content capture default, project overrides and secret exclusions across supported content channels.
- **OM-07.03-T3** — Map Claude events and token categories into E06 contracts, preserving counter windows, cost provenance and capability/version coverage.
- **OM-07.03-T4** — Verify default-on capture and project opt-out, duplicate hook/OTLP evidence, partial/truncated content, shared accounts, redaction, failed connections and uncertain offline delivery; document content gaps explicitly.

### [OM-07.04 — Prove Claude works across both projects and execution modes](epic-07.md#om-07-04)

Prerequisites: OM-07.02, OM-07.03

- **OM-07.04-T1** — Build the four-cell project/mode qualification procedure and reproducible fixtures, including current installed T3/native versions.
- **OM-07.04-T2** — Exercise real authorized knowledge/reporting paths only after content-policy gates, retaining redacted outcome and capability evidence.
- **OM-07.04-T3** — Validate repair, refresh, rotation, withdrawal, project isolation, revoked access and disconnection behavior in both modes.
- **OM-07.04-T4** — Publish contributor setup/repair instructions and truthful readiness results with recurring enrollment measurements and unresolved gaps.

## E08 — Use Codex with Owl Mast in every supported execution mode

### [OM-08.01 — Package and qualify the native Codex connection](epic-08.md#om-08-01)

Prerequisites: E06

- **OM-08.01-T1** — Define the versioned Codex package manifest, supported modes, owned settings and managed-policy-compatible merge/repair behavior.
- **OM-08.01-T2** — Implement enrollment-bound MCP, hook and OTLP configuration with secret references and preservation of unrelated user configuration.
- **OM-08.01-T3** — Qualify the actual standalone and T3-hosted configurations and retain a capability matrix covering native settings, hooks and fields.
- **OM-08.01-T4** — Add failure/repair checks for unsupported clients, missing secrets, managed overrides and endpoint conflicts without changing execution authority.

### [OM-08.02 — Deliver exact-version memory and complete Codex skills](epic-08.md#om-08-02)

Prerequisites: OM-08.01

- **OM-08.02-T1** — Implement the Codex MCP knowledge adapter using current authorization and exact-version delivery contracts.
- **OM-08.02-T2** — Implement qualified native package discovery/materialization with manifest validation, preserved unrelated skills and explicit cache/withdrawal handling.
- **OM-08.02-T3** — Verify Notion page creation, source-authorized reading, skill activation and delivery receipts as separate paths in both modes.
- **OM-08.02-T4** — Verify client-driven bounded search/selected load, validated default, explicit unvalidated opt-in and no unsolicited lesson injection in both modes; retain restricted/empty/conflicting-result, invalid-manifest, interrupted-refresh and revoked-version tests and distinguish independent retained-copy use.

### [OM-08.03 — Observe native Codex work with its actual event contracts](epic-08.md#om-08-03)

Prerequisites: OM-08.01

- **OM-08.03-T1** — Implement qualified observational command/MCP hooks, including supported model-attempt evidence and bounded shutdown/startup behavior.
- **OM-08.03-T2** — Generate independent logs/metrics/traces configuration using native Codex keys, binary/JSON options, exact endpoints and protected authentication references.
- **OM-08.03-T3** — Map available conversation messages, roles, turn/agent/tool IDs and tool argument/result pairs into E06 alongside request tokens and usage semantics; preserve content gaps and do not assume metrics carry session-level detail.
- **OM-08.03-T4** — Apply default-on prompt/response/tool-content capture and project overrides; verify redaction, missing/truncated content, retries, null counts, startup races, background-hook cancellation and duplicate cross-signal records.

### [OM-08.04 — Prove Codex integration and recovery in all pilot combinations](epic-08.md#om-08-04)

Prerequisites: OM-08.02, OM-08.03

- **OM-08.04-T1** — Build and run the four-cell native/T3 project matrix against supported installed versions using safe fixtures before live-content gates.
- **OM-08.04-T2** — Validate authorized Notion, MCP, native skill and telemetry paths separately, retaining redacted capability evidence.
- **OM-08.04-T3** — Verify cross-project denial, revoked source access, withdrawn versions, startup/shutdown losses and repaired configurations.
- **OM-08.04-T4** — Publish contributor instructions and measured recurring setup/readiness outcomes without claiming unverified historical coverage.

## E09 — Connect both customer work environments

### [OM-09.01 — Qualify actual source editions and permission contracts](epic-09.md#om-09-01)

Prerequisites: E02, E06

- **OM-09.01-T1** — Inventory both Jira sites and the actual GitHub/Bitbucket instances with source-qualified identities, versions, owners and permitted resource selections.
- **OM-09.01-T2** — Qualify authentication, user/source entitlement, revocation and restricted-record behavior using approved minimal probes or redacted fixtures.
- **OM-09.01-T3** — Record edition-specific event/history/pagination/limit capabilities and accepted connector contracts before implementing the provider adapters.
- **OM-09.01-T4** — Record A-3, retention/removal and destination decisions as live-ingestion gates with unresolved items and owners; keep secrets in protected configuration only.

### [OM-09.02 — Observe both qualified Jira sites independently](epic-09.md#om-09-02)

Prerequisites: OM-09.01

- **OM-09.02-T1** — Implement the qualified Jira edition adapter or adapters for both sites behind source ports, with independently scoped secret references and configuration.
- **OM-09.02-T2** — Collect supported issue/history/criteria/relationship evidence using bounded pagination and authenticated webhooks or qualified polling.
- **OM-09.02-T3** — Implement checkpoints, rate-limit handling, incremental reconciliation and source-access refresh without direct tracker mutations.
- **OM-09.02-T4** — Verify colliding keys, record restrictions, source permission removal, reopened progress, pagination interruption and isolated site failure.

### [OM-09.03 — Observe Syntelligence contributions from GitHub](epic-09.md#om-09-03)

Prerequisites: OM-09.01

- **OM-09.03-T1** — Implement the qualified GitHub authentication and repository-scoped read adapter with protected credential references.
- **OM-09.03-T2** — Normalize contribution, review, check and supported deployment/acceptance-reference records with provenance and stable navigation identities.
- **OM-09.03-T3** — Implement verified webhook handling where permitted plus bounded incremental reconciliation, checkpointing and rate-limit/backoff behavior.
- **OM-09.03-T4** — Verify restricted repositories, revocation, duplicates, missing webhooks, renamed repositories and separate merge/check/acceptance facts.

### [OM-09.04 — Observe Movesion contributions from Bitbucket](epic-09.md#om-09-04)

Prerequisites: OM-09.01

- **OM-09.04-T1** — Implement the qualified Bitbucket Cloud or Data Center adapter for the actual installation, authentication and permission model.
- **OM-09.04-T2** — Map native contribution/review/build and supported deployment-reference semantics with source-qualified identities and documented capability gaps.
- **OM-09.04-T3** — Implement approved webhook/poll paths, durable checkpoints, bounded reconciliation and edition-specific rate-limit handling.
- **OM-09.04-T4** — Verify provider/name collisions, denied repositories, permission changes, out-of-order updates and recovery independent of GitHub/Jira availability.

### [OM-09.05 — Reconcile both environments and explain connection coverage](epic-09.md#om-09-05)

Prerequisites: OM-09.02, OM-09.03, OM-09.04

- **OM-09.05-T1** — Implement unified connection-health/readiness views with independent scopes, selected resources, collection cadence and safe remediation.
- **OM-09.05-T2** — Exercise a cross-provider recovery suite covering webhook gaps, checkpoint interruption, duplicates, reordering and source-access removal.
- **OM-09.05-T3** — Supply E10 with verified source-qualified work/contribution relationships and acceptance references, preserving ambiguous/unlinked records.
- **OM-09.05-T4** — Demonstrate simultaneous two-site Jira plus GitHub/Bitbucket operation using authorized samples after the live-content gates and record remaining coverage gaps.

## E10 — Trace work, runs, contributions and dependencies

### [OM-10.01 — Correlate source records without inventing attribution](epic-10.md#om-10-01)

Prerequisites: E06, E09.

- **OM-10.01-T1** — Define Evidence-owned source-qualified work/run/contribution identifiers and typed correlation/assertion contracts consuming the Ingestion observation envelope with provenance and correction links.
- **OM-10.01-T2** — Implement deterministic correlation policies and authorized correction/mapping operations with reliable audit emission.
- **OM-10.01-T3** — Expose permission-filtered evidence-chain queries including unlinked, ambiguous and contradictory records.
- **OM-10.01-T4** — Verify duplicate keys, shared credentials, late corrections, conflicting mappings and revocation across chained results.

### [OM-10.02 — Inspect each observed task and run independently](epic-10.md#om-10-02)

Prerequisites: OM-10.01.

- **OM-10.02-T1** — Define the per-task/per-run read projection with provider-native effort labels, time segments and independent coverage fields.
- **OM-10.02-T2** — Implement current-authorization run-history and permitted full-ID retrieval APIs without flattening parent/child records.
- **OM-10.02-T3** — Build responsive task cards, accessible disclosures and copy feedback using existing evidence-detail primitives.
- **OM-10.02-T4** — Test multiple models/locations, role uncertainty, missing counters, long IDs and revocation during detail/copy use.

### [OM-10.03 — Calculate progress from explicit evidence](epic-10.md#om-10-03)

Prerequisites: OM-10.01.

- **OM-10.03-T1** — Implement pure ticket-progress policies for measurable, empty, changed and conflicting denominators.
- **OM-10.03-T2** — Implement the proposed epic child-closure projection with named set, deduplication and independent acceptance evidence.
- **OM-10.03-T3** — Build progress-evidence drill-down with basis/source/time and accessible Unknown/conflict states.
- **OM-10.03-T4** — Verify denominator changes, inconsistent checklists, partial collection, permission changes and independent completion dimensions.

### [OM-10.04 — Inspect the authorized dependency graph and equivalent list](epic-10.md#om-10-04)

Prerequisites: OM-10.01.

- **OM-10.04-T1** — Define bounded relation query/paging contracts and graph/list parity rules over PostgreSQL typed assertions.
- **OM-10.04-T2** — Implement authorization-aware expansion and cycle/gap classification without requiring a graph database.
- **OM-10.04-T3** — Build labeled directed graph interactions and the equivalent keyboard/phone relationship list.
- **OM-10.04-T4** — Test contradictory edges, multiple PRs, visible cycles, bounded traversal, graph/list parity and revoked-node suppression.

### [OM-10.05 — Follow work evidence into source tools safely](epic-10.md#om-10-05)

Prerequisites: OM-10.02, OM-10.03, OM-10.04.

- **OM-10.05-T1** — Compose the S2 query model from the earlier bounded projections without adding a second owner for work or run facts.
- **OM-10.05-T2** — Implement source-qualified ticket chips, work records, evidence sections and safe descriptive source links.
- **OM-10.05-T3** — Add independent acceptance/check/deployment evidence, explicit blocker/request-policy states and a source-status-versus-evidenced-stage slot with mapping provenance.
- **OM-10.05-T4** — Verify authorized deep links, missing links, stale/partial evidence, return context and absence of execution controls.

## E11 — Publish and revoke company-safe learning

### [OM-11.01 — Configure project promotion policy and permitted audiences](epic-11.md#om-11-01)

Prerequisites: E03, E04

- **OM-11.01-T1** — Implement project promotion policy/audience versions and maintainer/permitted-use ownership bindings behind current authorization.
- **OM-11.01-T2** — Implement concurrency-safe policy save and mode-change events that invalidate work carrying the prior policy revision.
- **OM-11.01-T3** — Add mode-specific explanations and validation, including automatic candidate evaluation and adopted A-4: disabled mode stops new publication while existing eligible publications remain available until separately withdrawn, superseded or otherwise ineligible.
- **OM-11.01-T4** — Verify unauthorized policy changes, missing permitted-use ownership, stale saves, automatic/manual/disabled transitions and queued/in-flight publication rejection after disabling; existing eligible publications and lineage remain readable with safe audit evidence.

### [OM-11.02 — Evaluate an exact company-safe publication candidate](epic-11.md#om-11-02)

Prerequisites: OM-11.01

- **OM-11.02-T1** — Add only publication-candidate/version, restricted lineage and check-result records required for company-safe publication.
- **OM-11.02-T2** — Implement durable evaluation jobs with current policy/content bindings and explicit passed/failed/uncertain check evidence; qualify any optional Spring AI processing destination before use.
- **OM-11.02-T3** — Produce separate company-reader and maintainer projections, excluding source keys, private links, named actors or detailed reasons without their own authorization.
- **OM-11.02-T4** — Verify sensitive-content failures, unresolved contradiction, missing permitted-use approval, changed sanitized text and hidden-origin disclosure cases.

### [OM-11.03 — Publish safely in automatic and manual modes under races](epic-11.md#om-11-03)

Prerequisites: OM-11.01, OM-11.02

- **OM-11.03-T1** — Implement the publication commit boundary with exact content/policy/audience revision guards and fresh maintainer/source/use authorization.
- **OM-11.03-T2** — Wire automatic durable jobs and manual exact-version decisions to the same guarded publication operation; ensure disabled mode cannot enqueue or commit new publication.
- **OM-11.03-T3** — Emit idempotent publication/lifecycle/audit events and expose authorized operation outcomes without depending on notification or audit UI epics.
- **OM-11.03-T4** — Verify concurrent edits, pending automatic-to-manual/disabled changes, permission revocation, stale human approval, retry-after-commit and restart failure cases.

### [OM-11.04 — Withdraw or quarantine guidance and its promoted derivatives](epic-11.md#om-11-04)

Prerequisites: OM-11.03

- **OM-11.04-T1** — Implement transitive derivation/publication-aware eligibility invalidation and immediate delivery guards using exact-version lineage, with durable idempotent index/cache cleanup; ordinary retrieval stays denied while cleanup is pending.
- **OM-11.04-T2** — Implement supersession and fresh-evaluation republication paths while distinguishing source ACL changes from publication permission and reliability changes.
- **OM-11.04-T3** — Preserve permission-filtered lifecycle/receipt history and append-linked corrections with explicit external-copy and retention limits.
- **OM-11.04-T4** — Verify withdrawn cached versions, derivative chains, stalled cleanup jobs, independent company-publication access and lost publication permission; verify A-2 lineage preservation and A-4 disabled-mode behavior without conflating stopping publication with withdrawal.

### [OM-11.05 — Review promotion policy, exceptions and lifecycle in S6](epic-11.md#om-11-05)

Prerequisites: OM-11.01, OM-11.02, OM-11.03, OM-11.04

- **OM-11.05-T1** — Build S6 policy controls, exact-version preview, manual decisions and automatic exception views using the existing authorized application contracts.
- **OM-11.05-T2** — Add lifecycle/history navigation and separate company-reader presentation with field-level source, actor and recipient authorization.
- **OM-11.05-T3** — Implement accessible pending/save/conflict/error/offline behavior and explanations for policy changes, changed content and unavailable source authority.
- **OM-11.05-T4** — Verify manual and automatic journeys, all bounded exception paths, stale/revoked decisions, keyboard/phone use and restricted-history disclosure.

## E12 — Demonstrate skill and memory use and useful reuse

### [OM-12.01 — Preserve distinct exact-version knowledge evidence](epic-12.md#om-12-01)

Prerequisites: E04, E07, E08

- **OM-12.01-T1** — Add Evidence-owned native load/application/reuse assertion and link records consuming Ingestion observations and referencing Knowledge-owned exact versions/delivery receipts; do not duplicate receipt or lifecycle authority, preserving exact versions, event identity, independent states and coverage provenance.
- **OM-12.01-T2** — Implement event validation, idempotency, late-arrival handling and explicit unassigned/unsupported classification without reconstructing facts from conversation text.
- **OM-12.01-T3** — Apply recipient/item/source/purpose authorization and A-3 collection limits before storing evidence or emitting safe audit events; keep raw queries/conversations unnecessary.
- **OM-12.01-T4** — Verify both native clients' supported read/load/use signals, fetch-without-load, partial receipts, unknown versions, duplicate transport and genuinely repeated cached loads.

### [OM-12.02 — Record human-verified useful reuse against task evidence](epic-12.md#om-12-02)

Prerequisites: OM-12.01

- **OM-12.02-T1** — Implement the exact-version/task-artifact human verification contract and scoped persistence with explicit evidence and verifier authorization.
- **OM-12.02-T2** — Add idempotent verification, correction/retraction and permitted audit history without overwriting earlier recorded claims.
- **OM-12.02-T3** — Expose a permission-checked Record verified reuse action from an eligible receipt/detail record with honest missing-evidence validation.
- **OM-12.02-T4** — Verify positive and missing/denied-evidence cases, duplicate verification, corrections and recipient revocation; prepare the unresolved A-6 sample-selection checkpoint.

### [OM-12.03 — Aggregate Skills and Memory measurements without false completeness](epic-12.md#om-12-03)

Prerequisites: OM-12.01, OM-12.02

- **OM-12.03-T1** — Implement bounded authorized aggregate queries for distinct Skills/Memory metrics and supported dimensions, using event identity and exact-version links.
- **OM-12.03-T2** — Encode period selection, event-time/fallback rules, coverage completeness and zero/partial/unavailable semantics in the statistics contract.
- **OM-12.03-T3** — Implement matching authorized drill-down and filter-option queries with current recipient/source/item permissions and revocation invalidation.
- **OM-12.03-T4** — Verify replay versus reload counting, multi-item inclusion, late events, unknown attribution, complete/partial windows and permission-safe unique counts.

### [OM-12.04 — Inspect knowledge receipts, statistics and reuse evidence](epic-12.md#om-12-04)

Prerequisites: OM-12.02, OM-12.03

- **OM-12.04-T1** — Add item/version knowledge statistics to S3/S4 and the separate Skills/Memory section of S7 using the shared metrics contract and equivalent accessible chart/table representations.
- **OM-12.04-T2** — Implement receipt/event drill-down and contextual verification flows with stable project/period/version filters and explicit source/recipient disclosure boundaries.
- **OM-12.04-T3** — Provide honest empty, partial, unavailable, pending, failure and revoked-access states, including distinctions among delivery, load, use and verified reuse.
- **OM-12.04-T4** — Verify the J9 knowledge-measurement journey and FR-11 verification flow with both native clients, keyboard/screen-reader navigation, both themes and phone layouts; keep A-6 acceptance approval pending.

## E13 — Understand daily work and personal focus

### [OM-13.01 — Understand own and colleague work from Daily Work](epic-13.md#om-13-01)

Prerequisites: E10.

- **OM-13.01-T1** — Define S1 query composition and person/project/period filters over the established work-evidence read contracts.
- **OM-13.01-T2** — Build the proposed overview layout with summary, attention, progress, work/agent chips, updates and collection coverage components.
- **OM-13.01-T3** — Connect each summary/count to its exact permitted detail set and preserve source/time/coverage labels.
- **OM-13.01-T4** — Verify own/colleague views, partial outages, source identity ambiguity and permission-filtered drill-down consistency.

### [OM-13.02 — Compare authorized project context in a company view](epic-13.md#om-13-02)

Prerequisites: OM-13.01.

- **OM-13.02-T1** — Define authorized company aggregate queries with per-project coverage and independent disclosure checks.
- **OM-13.02-T2** — Build explicit company scope selection, project summaries and safe project drill-down/return navigation.
- **OM-13.02-T3** — Add stable basis/coverage labels and contract-level entry points for knowledge and usage capabilities as they become available.
- **OM-13.02-T4** — Test inaccessible projects, restricted same-project sources, partial collection and unchanged project-default knowledge scope.

### [OM-13.03 — Follow assigned work across concurrent epics](epic-13.md#om-13-03)

Prerequisites: OM-13.01.

- **OM-13.03-T1** — Implement assignment queries using confirmed identity mappings, with explicit shared/unknown source-identity states.
- **OM-13.03-T2** — Build the separate Focus route and proposed stacked-epic/combined views with persistent project and person context.
- **OM-13.03-T3** — Integrate unique-work/run grouping, explicit ungrouped areas and E10 detail/dependency navigation.
- **OM-13.03-T4** — Verify simultaneous epics, shared runs, unconfirmed identity, partial mappings and cross-project disclosure boundaries.

### [OM-13.04 — Inspect work through the six observed SDLC stages](epic-13.md#om-13-04)

Prerequisites: OM-13.03.

- **OM-13.04-T1** — Implement versioned authorized project-stage mapping configuration and provenance projection, auditing mapping changes.
- **OM-13.04-T2** — Build six-stage kanban, Stage not mapped area, blocker badges and distinct concurrent-contribution indicators.
- **OM-13.04-T3** — Provide phone/keyboard grouped-list parity and links to the same E10 evidence/dependency records.
- **OM-13.04-T4** — Verify nonlinear movement, absent/changed mappings, original status preservation, unique counts and revocation during view changes.

### [OM-13.05 — Keep live work views accessible and stable during change](epic-13.md#om-13-05)

Prerequisites: OM-13.01, OM-13.02, OM-13.03, OM-13.04.

- **OM-13.05-T1** — Apply shared update-buffering, scope-change and safe-return behavior to S1, company, S2 entry and S10 views.
- **OM-13.05-T2** — Add coalesced announcements, accessible paging and route/dialog focus behavior using the foundation components.
- **OM-13.05-T3** — Implement immediate protected-content removal and explicit offline/reconnect states without duplicating observation projections.
- **OM-13.05-T4** — Run meaningful keyboard, screen-reader, zoom/reflow, reduced-motion and revoked-focus scenarios across the completed work views.

## E14 — Understand usage and cost with defensible attribution

### [OM-14.01 — Calculate unique observed usage with correct counter semantics](epic-14.md#om-14-01)

Prerequisites: E06, E07, E08, E10

- **OM-14.01-T1** — Define canonical usage portions, source precedence, input/output/cache semantics and provenance for each qualified runtime/version.
- **OM-14.01-T2** — Implement temporality-aware aggregation with stream/epoch identity, replay suppression, ordered reconciliation and explicit gaps/conflicts.
- **OM-14.01-T3** — Implement parent/child and cross-signal overlap handling without adding telemetry sources that describe the same consumption.
- **OM-14.01-T4** — Verify cumulative resets, delta duplicates, late windows, missing directions, cache subsets, retries and inaccessible measurements with independent expected totals.

### [OM-14.02 — Attribute usage only to evidenced work and execution segments](epic-14.md#om-14-02)

Prerequisites: OM-14.01

- **OM-14.02-T1** — Implement source-backed work/person/context attribution rules and explicit unassigned states using E10 relationship evidence.
- **OM-14.02-T2** — Preserve execution segments and distinct configured/requested/observed values in attribution APIs and permitted drill-downs.
- **OM-14.02-T3** — Implement correction-aware recomputation and deduplicated epic/project rollups with field-level authorization.
- **OM-14.02-T4** — Verify shared sessions/accounts, ambiguous roles, concurrent children, historical machine changes and revoked-field aggregate behavior.

### [OM-14.03 — Keep observed units, estimates, allocations and bills separate](epic-14.md#om-14-03)

Prerequisites: OM-14.02

- **OM-14.03-T1** — Define separate observed-unit, API-equivalent estimate, subscription-allocation and actual-bill records with source/date/currency and access controls.
- **OM-14.03-T2** — Implement versioned price matching and estimation, plus authorized recording of allocation/billing evidence without an unsolicited payment integration.
- **OM-14.03-T3** — Implement class-specific aggregation, unpriced/unassigned handling and revision-aware recalculation.
- **OM-14.03-T4** — Verify wrong/missing prices, currency mixtures, changed price dates, inaccessible allocation inputs and non-additive measurement classes.

### [OM-14.04 — Present S7 and contextual work usage with honest coverage](epic-14.md#om-14-04)

Prerequisites: OM-14.03

- **OM-14.04-T1** — Build authorized S7 breakdown APIs and the chart/table UI with shared query semantics, period/scope retention and explicit measurement classes.
- **OM-14.04-T2** — Add ticket/epic usage summaries and run-segment drill-down with model/effort/session/machine provenance and independent In/Out states.
- **OM-14.04-T3** — Add accessible loading/error/empty/unsupported/stale behavior and links to separately scoped Skill/Memory statistics.
- **OM-14.04-T4** — Verify chart/table parity, phone/keyboard navigation, mixed-class display, hidden-record inference and mid-session revocation against expected calculations.

## E15 — Receive every eligible work update and return safely

### [OM-15.01 — Qualify the notification platform and choose supported packaging](epic-15.md#om-15-01)

Prerequisites: E10, E11.

- **OM-15.01-T1** — Inventory actual pilot devices/browser versions and research current push, installability and background constraints from primary documentation.
- **OM-15.01-T2** — Build a bounded qualification harness for consent/subscription, background arrival and authorized deep-link return using synthetic data.
- **OM-15.01-T3** — Record the supported platform matrix, failure limits and a reviewable browser/PWA packaging recommendation, retaining owner approval as a gate.
- **OM-15.01-T4** — Validate denied/unsupported/revoked-session behavior and the proposed generic-preview policy before transport implementation.

### [OM-15.02 — Control notification preferences without hiding work updates](epic-15.md#om-15-02)

Prerequisites: OM-15.01.

- **OM-15.02-T1** — Define product notification event kinds, replay identity and explicit preference defaults, separating product changes from raw telemetry packets.
- **OM-15.02-T2** — Implement authorized per-person/project/kind preferences and audit emission without coupling them to view filters.
- **OM-15.02-T3** — Build S9 consent explanation, permission states, explicit save/error behavior and access-safe event/project selectors.
- **OM-15.02-T4** — Verify initial all-update eligibility, opt-outs, failed saves, proposal labeling and revoked-project removal.

### [OM-15.03 — Dispatch distinct updates through durable authorized work](epic-15.md#om-15-03)

Prerequisites: OM-15.01, OM-15.02.

- **OM-15.03-T1** — Implement the event-to-recipient eligibility projection and atomic notification job creation using the existing PostgreSQL job module.
- **OM-15.03-T2** — Implement the selected platform subscription/transport adapter, credential references, revoke/expiry handling and permission rechecks at dispatch.
- **OM-15.03-T3** — Persist dispatch attempts and distinct outcomes with retry/backoff, replay deduplication and safe audit/diagnostic metadata.
- **OM-15.03-T4** — Test duplicate source events, bursts, changed preferences, revoked/ended sessions, pod restart, transport failure and ambiguous external delivery outcomes.

### [OM-15.04 — Open the current authorized state from a notification](epic-15.md#om-15-04)

Prerequisites: OM-15.03.

- **OM-15.04-T1** — Implement notification-reference resolution with current per-target authorization and lifecycle-aware destinations.
- **OM-15.04-T2** — Build safe route/focus/return behavior and current-state explanations for resolved, superseded, withdrawn and unavailable targets.
- **OM-15.04-T3** — Integrate a scoped updates link without changing notification preferences or exposing hidden event counts.
- **OM-15.04-T4** — Verify old alerts, revoked rights, unavailable projects, offline opening and accessible phone/keyboard return flows.

## E16 — Inspect full-system audit and govern retained data

### [OM-16.01 — Query full-system audit with explicit coverage](epic-16.md#om-16-01)

Prerequisites: E02, E06, E11.

- **OM-16.01-T1** — Inventory every producer/object class against the shared audit event contract and define testable coverage/completeness reporting.
- **OM-16.01-T2** — Implement bounded tenant/project/object/action/actor/time audit queries with independent field and causal-link authorization.
- **OM-16.01-T3** — Add explicit delayed/unsupported/failed/unknown projections and correction links without rewriting authoritative business history.
- **OM-16.01-T4** — Verify producer contract fixtures for all required classes, replay/correction behavior and inference-resistant filtered counts/IDs.

### [OM-16.02 — Inspect audit timelines and object changes accessibly](epic-16.md#om-16-02)

Prerequisites: OM-16.01.

- **OM-16.02-T1** — Build S11 filters, bounded activity-list rows, coverage labels and object-history navigation using the existing components.
- **OM-16.02-T2** — Implement accessible authorized diff/version/causal disclosures and stable source/recorded-time presentation.
- **OM-16.02-T3** — Apply safe empty/error/offline/revoked states, route focus and scoped return behavior.
- **OM-16.02-T4** — Test mobile/keyboard timelines, independently restricted actors/diffs, delayed producers and revocation during expanded history.

### [OM-16.03 — Approve collection and retention policy before live ingestion](epic-16.md#om-16-03)

Prerequisites: OM-16.01.

- **OM-16.03-T1** — Model Governance-owned versioned collection/retention policies, including backup retention, responsible owners and A-3 live-ingestion gates for source and client paths.
- **OM-16.03-T2** — Define and integrate pre-persistence field allowlists/redaction decisions with ingestion, knowledge, audit and diagnostic contracts.
- **OM-16.03-T3** — Build authorized policy configuration and audited activation showing 30 active days then archive, no automatic archive purge and preserved project knowledge; keep other record-class and backup policy choices explicit.
- **OM-16.03-T4** — Test default-on conversation capture, project opt-out, secret redaction, changed policies during queued work and unauthorized/failed policy saves; distinguish stopping new capture from deleting already retained content.

### [OM-16.04 — Propagate removal and revocation through derived records](epic-16.md#om-16-04)

Prerequisites: OM-16.03, E11.

- **OM-16.04-T1** — Define the authorized removal/revocation event and target inventory with separate immediate disclosure denial and asynchronous cleanup outcomes.
- **OM-16.04-T2** — Implement idempotent PostgreSQL-backed propagation jobs and per-target adapters/contracts for primary and derived storage.
- **OM-16.04-T3** — Add inspectable safe progress/failure/audit records and ensure query/dispatch paths consult current eligibility during cleanup.
- **OM-16.04-T4** — Test index/cache/summary/history leakage, interrupted cleanup, duplicate commands, source-authority boundaries and unrecoverable external copies.

### [OM-16.05 — Preserve governance during replay and snapshot recovery](epic-16.md#om-16-05)

Prerequisites: OM-16.03, OM-16.04.

- **OM-16.05-T1** — Specify Governance-owned replay ordering/current-policy rules and the shared restore quarantine/reconciliation/release contract consumed by protected reads, dispatch and readiness, including state newer than the selected snapshot.
- **OM-16.05-T2** — Implement the single Governance-owned recovery quarantine/release gate and idempotent reconciliation of lifecycle/removal/permission state and effect outcomes via owner APIs; reads and external dispatch consume this gate before resuming. OM-18.02 qualifies this implementation rather than creating a second release authority.
- **OM-16.05-T3** — Document governed snapshot retention/expiry and removal-reporting limits alongside the operational restore runbook.
- **OM-16.05-T4** — Verify synthetic restore-before-revocation, replay-before-withdrawal, missing policy evidence and incomplete cleanup cases without creating live backup schedules.

### [OM-16.06 — Archive conversations after 30 days without losing knowledge](epic-16.md#om-16-06)

Prerequisites: OM-16.05.

- **OM-16.06-T1** — Define the archive contract through the evidence-owning module API: immutable content/version identity, checksum, locator/status, policy version and the 30-day clock for late arrivals and long-running sessions; qualify storage without adding a mandatory separate service.
- **OM-16.06-T2** — Implement database-backed idempotent archive jobs with write/verify/publish transitions, integrity/readback checks and safe active-copy release only after a durable archive is reachable; preserve recovery checkpoints and audit outcomes.
- **OM-16.06-T3** — Preserve searchable authorized metadata and stable evidence links; implement permission-checked archive read/restore and archived/retrieving/unavailable presentation in existing detail views without treating archival as knowledge approval.
- **OM-16.06-T4** — Propagate revocation/removal/policy changes across archive metadata and payloads; cover archive inventory, credentials/configuration references and integrity checks in recovery procedures without promising unsupported snapshot erasure.
- **OM-16.06-T5** — Verify the 30-day boundary, late data, duplicate jobs, failed/corrupt archive writes, crash between verification and locator publication, retrieval denial and restore; assert project knowledge and its evidence links survive archiving and no age-only archive purge occurs.

## E17 — Enrich native observations with optional T3 context

### [OM-17.01 — Qualify a minimal read-only T3 connection](epic-17.md#om-17-01)

Prerequisites: E06, E10

- **OM-17.01-T1** — Qualify the actual T3 version/interface and record a capability/permission contract including unsupported native usage and exact-effort fields.
- **OM-17.01-T2** — Implement enrollment-bound read-only connection configuration with protected credentials and no execution-capable port methods.
- **OM-17.01-T3** — Apply A-3 and source-authorization gates to requested/received fields and verify safe handling of conversation-bearing responses.
- **OM-17.01-T4** — Verify absent/revoked/unreachable T3 leaves direct native reporting and knowledge delivery operational.

### [OM-17.02 — Reconcile T3 context with existing native evidence](epic-17.md#om-17-02)

Prerequisites: OM-17.01

- **OM-17.02-T1** — Implement bounded read collection and source-qualified context normalization through E06/E10 interfaces.
- **OM-17.02-T2** — Implement evidence-based identity matching and typed enrichment links with explicit ambiguous/unlinked states.
- **OM-17.02-T3** — Integrate overlap detection with the shared accounting/evidence contract rather than creating a separate T3 usage total.
- **OM-17.02-T4** — Verify ID collisions, shared threads, conflicting context, duplicate native/T3 evidence, missing effort and revoked linked records.

### [OM-17.03 — Inspect and recover optional enrichment independently](epic-17.md#om-17-03)

Prerequisites: OM-17.02

- **OM-17.03-T1** — Add independent connection-health and evidence-detail integration with supported-field coverage and safe remediation.
- **OM-17.03-T2** — Implement qualified checkpoint/reconciliation and scoped durable retry behavior using the existing PostgreSQL job boundary.
- **OM-17.03-T3** — Verify outage/replay/revocation behavior with native paths still active, including cross-project denial and protected historical context.
- **OM-17.03-T4** — Document optional setup/repair/removal effects, current installed-version qualification and unresolved capability gaps without requiring T3 for native operation.

## E18 — Prove the complete pilot and publish a reproducible release

### [OM-18.01 — Qualify the full runtime and source capability matrix](epic-18.md#om-18-01)

Prerequisites: E01, E02, E03, E04, E05, E06, E07, E08, E09, E10, E11, E12, E13, E14, E15, E16

- **OM-18.01-T1** — Create the Claude/Codex × standalone/T3-hosted × both-project capability matrix, including current machine/sandbox and optional signal restrictions.
- **OM-18.01-T2** — Exercise model/effort changes, subagents/retries, native skill load/use, shared sessions and exporter configuration inheritance.
- **OM-18.01-T3** — Validate direct Notion creation/reading separately from Owl Mast MCP and preserve Hermes capture without a second save.
- **OM-18.01-T4** — Resolve A-5 and set source cadence/stale thresholds and measured latency/setup budgets before the acceptance run; publish limitations.

### [OM-18.02 — Restore the installation and survive processing failures](epic-18.md#om-18-02)

Prerequisites: OM-18.01

- **OM-18.02-T1** — Choose snapshot support, consistency procedure, failure coverage and recovery targets with the operator; implement and qualify the backup-retention policy owned by OM-16.03 before relying on live backups.
- **OM-18.02-T2** — Document and test restore into an isolated synthetic environment including database WAL, archived conversation payloads with their metadata/evidence links and separately stored artifacts; preserve encryption/secret references and consume and qualify the single Governance-owned OM-16.05 recovery quarantine/reconciliation/release gate before reads or external effects resume; do not implement a competing readiness/release authority.
- **OM-18.02-T3** — Run bounded receiver saturation, partial acceptance, late/duplicate input, pod termination and stale-lease recovery; restore snapshots preceding revocation, withdrawal and a sent notification to verify fail-closed reconciliation and safe effect replay.
- **OM-18.02-T4** — Publish measured RPO/RTO and native telemetry loss limits; propose an optional persistent collector only if measured requirements justify it, without deploying one automatically.

### [OM-18.03 — Demonstrate observation-to-reuse and every access boundary](epic-18.md#om-18-03)

Prerequisites: OM-18.02

- **OM-18.03-T1** — Verify adopted A-1 client-driven validated-default/explicit-candidate behavior at knowledge-quality acceptance; verify adopted A-2 derivative withdrawal/lineage and A-4 disabled-mode behavior before live promotion, resolve A-6 before sample selection, and name permitted-use/maintainer authorities.
- **OM-18.03-T2** — Capture SM-1–SM-5 plus SM-C1–SM-C4 with predeclared samples, failures/help/unknown coverage and source-verifiable acceptance artifacts.
- **OM-18.03-T3** — Trace exact-version source-to-lesson-to-validation-to-publication-to-delivery/use lineage through archive/restore and withdrawal; exercise derivative chains, mode/version races, restricted ancestors, post-index revocation and recipient/aggregate leakage.
- **OM-18.03-T4** — Run all named UX journeys and accessibility/device checks against separately packaged frontend/backend artifacts; reuse Testcontainers dependencies for synthetic integration cases, distinguish those from actual live proofs and obtain recorded owner acceptance.

### [OM-18.04 — Package a reproducible internal and public-ready release](epic-18.md#om-18-04)

Prerequisites: OM-18.03

- **OM-18.04-T1** — Produce versioned independent frontend/backend build/install/upgrade instructions with supported API version pairs, plus restore, native client enrollment, source connector and Testcontainers test runbooks with sanitized examples.
- **OM-18.04-T2** — Complete dependency/license and distributable artifact review; obtain the owner license decision before public release.
- **OM-18.04-T3** — Check that public artifacts exclude credentials, live screenshots, private telemetry and real source payloads.
- **OM-18.04-T4** — Record internal acceptance and separate public-release checklist; do not publish, push releases or create external tickets in this planning work.

## E19 — Evolve tenant scale, permissions and availability

### [OM-19.01 — Operate multiple active tenants](epic-19.md#om-19-01)

Prerequisites: E18

- **OM-19.01-T1** — Define operator-led tenant onboarding/offboarding and per-tenant configuration over the existing tenant model; leave monetization outside scope.
- **OM-19.01-T2** — Exercise two-real-tenant-equivalent synthetic workloads across all stores, jobs, MCP/OTLP, notifications and audit views.
- **OM-19.01-T3** — Qualify per-tenant quotas/fair processing and export/removal boundaries before external tenant onboarding.
- **OM-19.01-T4** — Document migration from the AISQUAD-only profile and verify the independent single-tenant installation remains supported.

### [OM-19.02 — Introduce fine-grained OpenFGA authorization](epic-19.md#om-19-02)

Prerequisites: OM-19.01

- **OM-19.02-T1** — Model tenant/project/resource and permitted-use relationships; review how source revocation combines with internal grants.
- **OM-19.02-T2** — Implement the optional OpenFGA adapter and idempotent versioned grant synchronization without bypassing source authorization.
- **OM-19.02-T3** — Run shadow comparisons and all original/new negative cases before switching enforcement.
- **OM-19.02-T4** — Document rollback, model migration and outage behavior; add the optional deployment only when this later capability is selected.

### [OM-19.03 — Run multiple application pods with compatible upgrades](epic-19.md#om-19-03)

Prerequisites: E18

- **OM-19.03-T1** — Qualify multi-pod sessions/MCP behavior, any blob-volume access-mode constraints and cross-node placement/capacity.
- **OM-19.03-T2** — Implement rolling-update readiness/drain settings and backward-compatible schema/event migration procedures.
- **OM-19.03-T3** — Run overlapping-version, duplicate-worker and connection-drain scenarios with two replicas.
- **OM-19.03-T4** — Define separately scoped PostgreSQL/Keycloak/storage failover decisions if the availability target requires them; preserve the simple POC profile.

### [OM-19.04 — Extract components only when measurements justify them](epic-19.md#om-19-04)

Prerequisites: E18

- **OM-19.04-T1** — Instrument and measure queue age, workload fairness, recovery burden and resource bottlenecks against agreed targets.
- **OM-19.04-T2** — Compare separating the existing worker adapter with workflow-engine options only for demonstrated needs.
- **OM-19.04-T3** — Produce a concrete migration design including in-flight work, duplicate effects, version compatibility and rollback.
- **OM-19.04-T4** — Create implementation stories for the chosen later solution after that decision; keep this story a bounded evaluation deliverable.
