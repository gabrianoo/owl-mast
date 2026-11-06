---
epic: E06
status: planned
review_status: pending-owner-review
implementation_status: not-started
---

# Epic E06 — Receive and normalize native telemetry reliably

Operators receive direct observations from executing machines, inspect their permitted coverage, and recover accepted work without duplicated accounting. The OTLP receiver is application functionality inside the modular Spring backend; configuring Spring's outbound telemetry exporter does not implement it. Native clients do not require T3 or a separate Collector to reach Owl Mast. Follow the [agent integration planning contract](../../architecture/architecture-owl-mast-2026-11-05/AGENT-INTEGRATION.md): proposed routes `/ingest/otlp/v1/logs`, `/ingest/otlp/v1/metrics` and `/ingest/otlp/v1/traces` are separate from authenticated semantic observations at `/api/v1/observations`. Reuse the PostgreSQL jobs and audit envelope from OM-01.03 through the existing module boundaries.

**Epic prerequisites:** E05

<a id="om-06-01"></a>

### OM-06.01 — Bind collection to enrollment and the approved content policy

As a project administrator, I want every observation checked against its enrolled identity and collection policy, so that accepted metadata and content stay within authorized boundaries.

**Requirements:** FR-17, FR-18, FR-19; NFR-1, NFR-6; AR-08, AR-15, AR-17, AR-18; UX-DR41, UX-DR42

**Depends on:** E05

**Acceptance criteria:**

- Given an enrolled client, when it submits an observation, then tenant, allowed projects and purpose derive from trusted credentials and enrollment; payload attributes cannot widen that scope or establish a human initiator.
- Given the adopted default-on full-conversation policy but unresolved archive/other-record policies, actual-environment permission or destination rules, when live ingestion is activated, then only those remaining prerequisites gate activation. Once they are resolved, permitted prompts, responses and tool arguments/results are captured by default unless the project disables or narrows capture; secret exclusions remain mandatory.
- Given a payload containing credential material or policy-excluded content, when it is decoded, then exclusion/redaction occurs before observation persistence, diagnostic logs, indexes or derived processing; rejection diagnostics do not repeat excluded values.
- Given revoked, expired, wrong-project or unverifiable credentials, when any signal is received, then ingestion fails closed with a safe response and permitted audit evidence, without trying another project or company scope.

**Tasks:**

- [ ] **OM-06.01-T1** Define the versioned ingress authentication, enrollment binding and purpose-scoping contract for OTLP and semantic observations.
- [ ] **OM-06.01-T2** Implement the pre-persistence field allowlist/redaction pipeline and collection-policy gate, including A-3 decision evidence and protected credential references.
- [ ] **OM-06.01-T3** Add fixtures for default-on conversation capture, project opt-out, scope forgery, revoked enrollment, secret-bearing fields, excluded content and diagnostic leakage.
- [ ] **OM-06.01-T4** Record permitted receipt/rejection audit fields and a policy-change contract that prevents queued processing from restoring excluded content.

<a id="om-06-02"></a>

### OM-06.02 — Accept the native OTLP wire protocols in Spring

As an integration operator, I want a conforming receiver for logs, metrics and traces, so that native exporters can communicate directly with Owl Mast.

**Requirements:** FR-3, FR-16, FR-18; NFR-3, NFR-6; AR-02, AR-03, AR-11, AR-14, AR-15; UX-DR22, UX-DR26

**Depends on:** OM-06.01

**Acceptance criteria:**

- Given a qualified native exporter, when it posts to the separately documented logs, metrics or traces route, then the receiver decodes the corresponding OTLP message in binary protobuf or OTLP JSON with either identity or gzip encoding; JSON IDs, enums and 64-bit values follow OTLP rules.
- Given a valid authorized batch, when its permitted contents and required normalization work commit durably together, then the receiver returns HTTP 200 with the correct signal response and matching content type; a process-memory queue or outbound Spring exporter cannot stand in for durable acceptance.
- Given malformed, unsupported or oversized data, when validation fails, then the receiver returns a bounded protocol-appropriate error, limits decompressed as well as compressed input, and retains no rejected raw content.
- Given temporary unavailability or overload, when the receiver cannot durably accept the request, then it uses retryable OTLP status semantics and appropriate Retry-After guidance; deliberate partial acceptance reports rejected-item counts and is never used to request a later retry of temporary failures.

**Tasks:**

- [ ] **OM-06.02-T1** Implement the three proposed OTLP WebFlux routes using pinned official message definitions, content negotiation, gzip handling and configurable resource bounds; implement `/api/v1/observations` separately against the versioned semantic contract.
- [ ] **OM-06.02-T2** Commit redacted acceptance records and scoped durable processing jobs atomically through the owning module's transaction boundary.
- [ ] **OM-06.02-T3** Implement signal-specific success, partial-success and failure responses, including rate/backpressure handling and safe error messages.
- [ ] **OM-06.02-T4** Verify all three signals with binary/JSON, compressed/uncompressed, empty, malformed, oversized and storage-failure fixtures; document full versus base endpoint URL rules.

<a id="om-06-03"></a>

### OM-06.03 — Normalize evidence without inventing missing identity or capability

As an authorized viewer, I want different native signals represented consistently, so that their provenance and gaps remain understandable.

**Requirements:** FR-4, FR-16, FR-18; NFR-2, NFR-6; AR-07, AR-14, AR-16, AR-18; UX-DR19, UX-DR46, UX-DR47, UX-DR54

**Depends on:** OM-06.02

**Acceptance criteria:**

- Given accepted logs, metrics, traces or semantic observations, when they normalize, then source/runtime/version, contract version, source and recorded times, original metric units/temporality and available provider identifiers remain traceable to permitted evidence.
- Given a run with observed changes of model, effort or location, when its history is assembled, then time-qualified segments are preserved separately from current enrollment defaults; task, role, run, session, delegation and machine identities are not merged.
- Given absent or unsupported fields, when normalization completes, then it records missing/unsupported/unverified coverage rather than inventing zero tokens, a person, a Jira task, a host or a blocked state.
- Given a future event version, conflicting mapping or invalid source identifier, when interpretation is unsafe, then the record is quarantined or represented as uninterpreted permitted evidence with a bounded diagnostic; unrelated supported observations continue processing.
- Given permitted conversation content arrives through overlapping native channels, when history is assembled, then source-qualified session/turn/tool identifiers preserve message roles, order and tool argument/result relationships without duplicate messages; redacted, excluded, truncated and unavailable content remain distinct from complete captured content. Capturing a conversation does not approve it as reusable knowledge.

**Tasks:**

- [ ] **OM-06.03-T1** Define Ingestion-owned normalized observation-envelope, metric-sample, trace-link, conversation-message and semantic-evidence input contracts with source-qualified IDs, roles, turn/tool relationships and explicit capability/content coverage.
- [ ] **OM-06.03-T2** Implement adapter routing, schema/version compatibility and normalization into owned PostgreSQL records, including authorized conversation content and ordered references, without direct cross-module table writes.
- [ ] **OM-06.03-T3** Preserve original units, accounting semantics, time windows and configured-versus-observed values for downstream usage calculations.
- [ ] **OM-06.03-T4** Verify missing fields, identity collisions, model/location changes, unknown schemas, duplicate/out-of-order conversation messages, tool pairing and redacted/truncated/unavailable content using synthetic fixtures.

<a id="om-06-04"></a>

### OM-06.04 — Recover accepted observations and suppress repeated accounting

As an operator, I want interrupted and repeated processing to converge safely, so that pod replacement and transport retries do not silently multiply work or usage.

**Requirements:** FR-3, FR-16; NFR-2, NFR-3; AR-07, AR-11, AR-18; UX-DR42, UX-DR47

**Depends on:** OM-06.03

**Acceptance criteria:**

- Given a durably accepted batch and interrupted normalization, when the application restarts or a lease expires, then database-backed work resumes with bounded attempts and ownership-checked completion; terminal failures remain inspectable.
- Given duplicate, overlapping or out-of-order evidence from hooks, OTLP or later contextual adapters, when reconciliation runs, then stable source identities and documented matching rules prevent repeat accounting; ambiguous overlap remains explicit rather than guessed away.
- Given delta and cumulative samples or parent counters containing child usage, when observations are retained, then time windows, start epochs and containment evidence remain available for correct downstream accounting; receipt processing does not add all numeric samples together.
- Given client termination before export or a network outage exceeding its supported buffering, when collection resumes, then Owl Mast reports uncertain/missing coverage and does not claim an offline backlog, exactly-once delivery or recovered events it never received.
- Given authorization changes while work waits, when a worker resumes, then it rechecks current scope and policy before further disclosure or derived processing.

**Tasks:**

- [ ] **OM-06.04-T1** Implement one durable retry owner, lease recovery, bounded backoff, idempotent normalization and explicit terminal failure in the existing backend.
- [ ] **OM-06.04-T2** Define per-signal source identity, replay detection and cross-channel reconciliation rules, including unknown identity and overlap behavior.
- [ ] **OM-06.04-T3** Exercise crash-after-acceptance, crash-before-acknowledgment, duplicate batches, late samples, concurrent claims and revoked-scope recovery.
- [ ] **OM-06.04-T4** Document native exporter limits, receiver guarantees and the evidence threshold for an optional persistent Collector, without making it a prerequisite.

<a id="om-06-05"></a>

### OM-06.05 — Make ingestion health and coverage inspectable

As an authorized operator, I want per-client/project/signal health and safe recovery details, so that a connected badge cannot conceal missing observations.

**Requirements:** FR-3, FR-16, FR-18; NFR-2, NFR-4, NFR-6; AR-17, AR-18; UX-DR19, UX-DR22, UX-DR26, UX-DR41, UX-DR54

**Depends on:** OM-06.04

**Acceptance criteria:**

- Given independently configured signals, when readiness is shown, then configuration, last receipt, last normalized success, failure, source time, collection time and affected coverage are distinct from knowledge-delivery readiness and current agent activity.
- Given an outage, unsupported field or policy-excluded payload, when health is inspected, then the reason and authorized remediation differ; no missing observation is presented as zero use or an execution failure.
- Given new receipts while a user reads activity, when the list updates, then paging and reading position remain stable and arrivals are announced accessibly without exposing hidden counts or restricted diagnostic values.
- Given a revoked viewer or unavailable permission check, when health or recovery detail is requested, then protected fields, filters and historical values are withheld; other authorized connections stay usable.

**Tasks:**

- [ ] **OM-06.05-T1** Expose authorized health and bounded receipt/processing history APIs with declared cadence and stale-state configuration.
- [ ] **OM-06.05-T2** Implement connection-readiness and activity-list integration with separate signal and delivery coverage and persistent safe failure states.
- [ ] **OM-06.05-T3** Verify per-signal failure isolation, field-level revocation, source/recorded times, accessible update handling and secret-free recovery diagnostics.

## Qualification and source notes

A-3's full-conversation default is adopted. Retention, actual-environment permissions and allowed destinations remain owner/project-data-owner work before live-content ingestion. Native signal and content coverage must be verified by runtime and version. No tests or integrations have been performed by this planning artifact.

- [OTLP protocol](https://opentelemetry.io/docs/specs/otlp/) defines the three signal routes, encodings, compression, acknowledgment, rejection and retry semantics. HTTP 500 is not a general retry signal; use the specified retryable codes.
- [OTLP exporter configuration](https://opentelemetry.io/docs/specs/otel/protocol/exporter/) distinguishes a generic base URL from exact signal endpoints.
- [OTel metrics model](https://opentelemetry.io/docs/specs/otel/metrics/data-model/) defines temporality, timestamps and stream identity.
- [Spring Boot metrics](https://docs.spring.io/spring-boot/reference/actuator/metrics.html#actuator.metrics.export.otlp) describes outbound export, not the receiver planned here.
- [Collector resilience](https://opentelemetry.io/docs/collector/resiliency/) supports evaluating optional persistent buffering when operational evidence justifies it.
