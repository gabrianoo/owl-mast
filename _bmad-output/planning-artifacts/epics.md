---
status: draft
created: 2026-11-05
updated: 2026-11-06
stepsCompleted: [1, 2, 3, 4]
review_status: pending-owner-review
implementation_status: not-started
inputDocuments:
  - prds/prd-owl-mast-2026-11-05/prd.md
  - prds/prd-owl-mast-2026-11-05/addendum.md
  - ux-designs/ux-owl-mast-2026-11-05/DESIGN.md
  - ux-designs/ux-owl-mast-2026-11-05/EXPERIENCE.md
  - architecture/architecture-owl-mast-2026-11-05/ARCHITECTURE-SPINE.md
  - architecture/architecture-owl-mast-2026-11-05/.memlog.md
  - architecture/architecture-owl-mast-2026-11-05/AGENT-INTEGRATION.md
---

# Owl Mast — full feature epic and task plan

Engineering execution status and priority are maintained in GitHub; see the [tracking contract](../../docs/engineering-tracking.md). Planning status fields and unchecked tasks below remain baseline specifications, not a live progress board.

## Scope and decision status

The full agreed feature scope is planned now and implemented in dependency-ordered slices. Native Claude Code and Codex work directly from the executing machine through MCP, plugins/hooks and OpenTelemetry, both standalone and when hosted by T3. T3 is an optional evidence source. The earlier proposal to defer full standalone reporting is superseded. This is a reviewable planning draft, not implementation, completed integration qualification, or approval of unresolved product assumptions.

The [architecture spine](architecture/architecture-owl-mast-2026-11-05/ARCHITECTURE-SPINE.md) is finalized as the implementation consistency contract after source reconciliation and independent review. This full backlog remains a planning draft for owner review and uses the explicit qualification gates below. The authoritative PRD/UX details remain binding when the inventories below abbreviate them. Separate frontend/backend builds and deployments and Testcontainers integration testing were adopted on 2026-11-06. Other UI proposals retain their original proposal status; separate deployment does not decide browser origins or authentication. This planning phase created no external tickets or live schedules.

The [native integration contract](architecture/architecture-owl-mast-2026-11-05/AGENT-INTEGRATION.md) describes the direct MCP/OTLP/plugin paths and distinguishes them from optional T3 enrichment. Detailed stories are split into one file per epic so separate implementation agents can work against bounded inputs. The [task index](epics/owl-mast-2026-11-05/TASKS.md) carries stable local story/task IDs and dependencies; these are planning IDs, not issued Jira tickets.

## Requirements Inventory

### Functional requirements

- **FR-1 — Separate project connections:** An administrator can configure distinct connections for Syntelligence’s Jira and GitHub, and Movesion’s separate Jira and Bitbucket.
- **FR-2 — Minimal enrollment:** A contributor can connect existing Claude and Codex clients to the same Owl Mast workspace and select projects they may access, without migrating repositories, trackers, or the current knowledge store. Realizes SC-2.
- **FR-3 — Connection health and recovery:** An authorized operator can inspect each connection’s last successful collection, current failure, and affected coverage.
- **FR-4 — Human, agent, and delegation attribution:** An authorized viewer can distinguish the initiating person, executing agent, delegation chain, and repository identity when the sources provide them.
- **FR-5 — Work-to-contribution evidence chain:** An authorized viewer can follow a work item to related runs, contributions, and acceptance evidence, and open the supporting source records.
- **FR-6 — Progress and dependencies:** An authorized lead can inspect project/work-item progress and relevant dependencies using source evidence.
- **FR-7 — Attention and incomplete observation:** An authorized viewer can find observed failures, explicit blockers, and work awaiting review without monitoring every execution tool.
- **FR-8 — Capture with provenance:** An authorized contributor or configured learning flow can submit a lesson, skill, or memory to its project with supporting evidence.
- **FR-9 — Review and knowledge lifecycle:** A knowledge maintainer can distinguish candidate, approved, superseded, withdrawn, and conflicting knowledge versions.
- **FR-10 — Scoped knowledge delivery:** Agents search on demand, then explicitly load selected exact-version knowledge. Validated guidance is the default; a client-controlled flag can include labelled unvalidated candidates without widening access or lifecycle eligibility. Bounded discovery/load avoids unsolicited context injection.
- **FR-11 — Delivery and reuse evidence:** An authorized reviewer can distinguish knowledge that was available, retrieved, delivered, and demonstrably reused.
- **FR-12 — Explicit company-wide promotion:** A knowledge maintainer can select automatic, manual-approval, or disabled promotion for a project. Automatic is the preferred operating mode once its publication policy and allowed audience are configured.
- **FR-13 — Withdrawal and supersession:** A knowledge maintainer can withdraw guidance, and the system can quarantine a version when it detects unreliable or conflicting evidence. Earlier deliveries remain traceable.
- **FR-14 — Preserve the current learning flow:** Hermes can continue its established learning/memory flow into Notion while Owl Mast observes and delivers permitted project knowledge.
- **FR-15 — Project and company views:** An authorized viewer can inspect project progress, agent activity, attention items, knowledge, and usage, then drill into permitted evidence.
- **FR-16 — Usage and cost semantics:** An authorized viewer can understand observed usage and attributable cost by project, client/model, agent, person, or work item where evidence supports that breakdown.
- **FR-17 — Enforce project and source access:** Every viewer and agent receives only data authorized for the requested purpose and audience.
- **FR-18 — Govern collected content:** Full agent conversation capture is on by default, including prompts, responses and tool arguments/results. Keep it active for 30 days, then archive it with authorized retrieval and provenance intact. Project knowledge does not expire at 30 days and no automatic archive purge is selected. Project collection controls, secret filtering, current source permissions and explicit coverage remain mandatory.
- **FR-19 — Keep execution authority outside Owl Mast:** Owl Mast observes work and performs authorized knowledge lifecycle operations without controlling agents or delivery pipelines.
- **FR-20 — Open-source repeatability:** An authorized pilot operator can reproduce the supported Owl Mast setup from its repository and documented prerequisites. Public-release packaging is a separate gate.
- **FR-21 — Preserve Notion-backed client workflows:** Claude and Codex can continue authorized Notion page creation and receive permitted Notion-backed knowledge/skills through the validated pilot integration.

### Non-functional requirements

- **NFR-1 — Isolation:** The pilot passes all cross-project and revoked-access negative cases in FR-17. No unauthorized content or inference-bearing snippet is returned. Failed access checks do not fall back to company scope.
- **NFR-2 — Evidence integrity:** Every displayed claim distinguishes source fact, inference, estimate, and unknown where applicable. Source timestamps and collection timestamps remain distinguishable; partial coverage cannot look complete.
- **NFR-3 — Resilience:** A connection outage preserves access to other authorized data with stale labels. Recovery is tested with duplicate and out-of-order records and does not silently lose or multiply observations.
- **NFR-4 — Freshness:** Each supported connection declares a collection cadence and the point at which data is marked stale; each knowledge-delivery path declares its cache/withdrawal behavior. Numeric latency and freshness budgets are set against the actual pilot environment before its performance acceptance run, not invented from research.
- **NFR-5 — Usability:** A contributor completes enrollment and obtains useful project knowledge using the supplied instructions, without bespoke developer intervention. The pilot records failures and help required as well as elapsed time, tests FR-2's proposed step ceiling, and calibrates time targets under §9.
- **NFR-6 — Diagnostic safety:** Operators can identify failed collection, authorization, delivery, and publication operations without exposing credentials or restricted source text in logs. Audit records identify the actor, project, operation, item/version where relevant, and outcome.

### Additional architecture requirements

- **AR-01:** Java 27, Spring Boot 4.1.2, Java application code and Gradle Kotlin DSL; qualify compatible dependency/toolchain pins instead of copying ConvaDesk versions.
- **AR-02:** One modular backend with ports/adapters and feature-oriented packages; modules own tables, mutations, APIs and event contracts. The frontend is independently built and deployed, with an explicit API compatibility contract.
- **AR-03:** Reactive WebFlux/Reactor and proposed R2DBC persistence; bounded isolated blocking adapters where unavoidable, explicit context propagation and transaction boundaries.
- **AR-04:** Functional composition and immutable values, focused Lombok/records, readable guard clauses, formatter/static-analysis/dependency checks in CI; choose Java-27-compatible tooling. Use Testcontainers for meaningful integration tests with real PostgreSQL/VectorChord and selected Keycloak flows; preserve fast unit/component tests.
- **AR-05:** PostgreSQL is primary store; VectorChord indexes embeddings. pgvector is permitted only as the required type/operator dependency, not its indexing methods.
- **AR-06:** Keep Markdown versions and complete skill package manifests/files/checksums; qualify large/binary and conversation archive storage while preserving original Notion/Git authority. Archive after 30 active days without losing content, stable identities or evidence links; curated project knowledge has its own lifecycle.
- **AR-07:** Source-qualified identities and first-class exact-version lineage across source evidence, knowledge versions, validation, publication and delivery/use. Preserve typed relationships, provenance, source/recorded times and correction/retraction history through archival and withdrawal; distinguish derivation from usage and enforce current permissions on lineage views.
- **AR-08:** AISQUAD is one tenant with separately permissioned Syntelligence/Movesion projects; preserve future SaaS and independent single-tenant self-hosting with isolation tests.
- **AR-09:** Keycloak manages personal Owl Mast accounts; many people may map to one external customer account without merging principals or inventing personal attribution. Initially every native agent enrollment belongs to a named person; unattended service-identity agent operation is deferred. Enrollment ownership is distinct from evidence of who initiated an action.
- **AR-10:** Application authorization boundary covers every disclosure and mutation; OpenFGA is a planned later adapter, not an initial deployed dependency.
- **AR-11:** Spring/PostgreSQL durable jobs in the same backend: atomic work enqueue, leases, bounded retries, idempotency, restart recovery and explicit terminal failure; no initial workflow engine.
- **AR-12:** Kubernetes installation has separate frontend/backend deployment artifacts and independently optional PostgreSQL/VectorChord and Keycloak, supporting existing compatible services when disabled. Routing/origin configuration is separate from deployment topology; Testcontainers is test infrastructure, not a production dependency.
- **AR-13:** Initial downtime/single-instance operation is acceptable; PVC snapshots preferred, requiring database consistency and restore qualification. RPO/RTO, backup retention and storage driver remain open; archived content and its metadata must be covered by recovery.
- **AR-14:** Plan native Claude/Codex integration fully now, both standalone and T3-hosted; clients send directly from executing machines using MCP/plugins/hooks/OpenTelemetry. T3 is optional context.
- **AR-15:** Implement authenticated MCP knowledge access and explicit OTLP receiver routes in the existing Spring app; outbound Spring telemetry export is not an ingestion receiver.
- **AR-16:** Keep observation, knowledge retrieval, native skill activation, semantic use and verified reuse separate; no agent control, shell, merge or deployment authority.
- **AR-17:** Tenant/project/purpose scope derives from trusted enrollment/credentials; source permission, redaction, retention and revocation apply before persistence/disclosure and to derivatives.
- **AR-18:** Version ingress/event/enrollment/knowledge contracts; carry provenance and capability coverage; reconcile cross-signal duplicates and metric temporality without fabricated completeness.
- **AR-19:** Client packages/configuration must preserve user settings, use secret references, support revoke/repair and state connectivity/offline-delivery limits. Native credentials remain bound to an individual user's current permitted scope, with separate personal enrollments on shared machines and no fallback to an unattended service identity.
- **AR-20:** Plan later multi-tenant rollout, two-pod availability and OpenFGA migration separately; do not commit billing, universal adapters, sandbox hosting or a workflow-engine product.

### UX design requirements

The 60 extraction IDs below supplement the original UX-01–24 decisions; they do not renumber them. UX-DR07–28 enumerate every shared component separately.

- **UX-DR01:** Exact accepted light/dark semantic and identity palette; system theme plus explicit override.
- **UX-DR02:** Defined system typography, readable wrapping and tabular numbers; 14px minimum key labels, 12px supplementary only.
- **UX-DR03:** Defined spacing/radii/page margins and 44px targets; tonal persistent panels and in-flow evidence.
- **UX-DR04:** Validate text/control/focus contrast in both rendered themes, 3px focus with 2px offset, readable disabled reasons and non-color selected cues.
- **UX-DR05:** Responsive >=1024, 600–1023 and <600 layouts; 320px reflow/200% zoom and phone graph/list/kanban parity.
- **UX-DR06:** Semantic keyboard/touch/screen-reader access, skip link and reduced motion; no hover/drag-only actions or fabricated progress.
- **UX-DR07:** brand-mark: preserve accepted owl SVG geometry/currentColor and wordmark; accessible decorative treatment.
- **UX-DR08:** scope-bar: retain authorized project/company/source/period; scope changes reauthorize and reset incompatible filters.
- **UX-DR09:** surface-navigation: current destination, labeled compact menu, safe return; hide unauthorized administration without counts.
- **UX-DR10:** work-summary: same permitted record basis for counts/drill-down, constant accessible-record label and distinct gaps.
- **UX-DR11:** attention-item: evidenced reason/source/age/state and policy-excluded text explanation; navigation without execution.
- **UX-DR12:** progress-evidence: numerator/denominator/basis/time and unknown/conflict states; no tracker editing.
- **UX-DR13:** work-record: source-qualified identity; distinct owner/initiator/agent/delegation/repository/status/progress.
- **UX-DR14:** ticket-chip: qualified accessible detail link, readable wrap and 44px hit area.
- **UX-DR15:** agent-chip: personal alias/color with immutable provider/type identity; no implied trust/status or identity merging.
- **UX-DR16:** focus-board: separate assigned-work epic/combined/kanban views; filters retain source ownership and status.
- **UX-DR17:** epic-group: explicit relation, labeled child-closure basis, concurrent/shared/unlinked records and deduplicated totals.
- **UX-DR18:** evidence-detail: source facts/inference/correlation, individual run fields, acceptance authority, typed dependencies and authorized history.
- **UX-DR19:** activity-list: bounded/filterable work and audit rows, both timestamps and stable reading position with New updates.
- **UX-DR20:** knowledge-record: exact version/provenance/evaluator/lifecycle; candidate submission and duplicate/conflict privacy.
- **UX-DR21:** delivery-receipt: separate availability/retrieval/delivery/reuse; verified version/artifact/time with independent recipient disclosure.
- **UX-DR22:** connection-readiness: separate observation/delivery capabilities per client/project, last success and configured/observed location.
- **UX-DR23:** promotion-review: exact version/audience/current policy; source and maintainer authorization; stale approval invalidation.
- **UX-DR24:** usage-breakdown: classes/units/period/coverage/attribution, independent input/output and equivalent chart/table.
- **UX-DR25:** settings-field: explicit save, validation, real result, retained unsaved choice and explained policy effects.
- **UX-DR26:** state-message: distinct loading/empty/error/offline/denied/stale/unsupported with safe persistent remediation.
- **UX-DR27:** action-control and dark variant: same authorized behavior, pending duplicate prevention, explicit affected version/audience and actual result.
- **UX-DR28:** external-link: descriptive destination/navigation only; return does not prove external success.
- **UX-DR29:** S1 Daily Work: own/colleague/project views, closures/attention/progress/recent activity/coverage; not assigned-only.
- **UX-DR30:** S2 Work/evidence: ticket/epic -> task/run -> contribution -> acceptance, individual metadata and dependencies/usage.
- **UX-DR31:** S3 Knowledge: scoped catalog/search/submission/lifecycle/company publications/Notion lineage/statistics/audit.
- **UX-DR32:** S4 Knowledge detail/history: exact version/conflicts/evaluation/provenance, permitted receipts/use/recipients/history.
- **UX-DR33:** S5 Connections/enrollment: native Claude/Codex, project selection, readiness, machine history, recovery and personal appearance.
- **UX-DR34:** S6 Promotion: automatic/manual/disabled policy, exceptions, exact safe publication preview/audience and lifecycle history.
- **UX-DR35:** S7 Usage: all supported client/model/effort/role/device/person/session/work dimensions, separate knowledge counts and permitted drill-down.
- **UX-DR36:** S8 Administration: source sites/scopes/permissions/capabilities, collection/retention and secret-free remediation.
- **UX-DR37:** S9 Preferences/notification return: push consent/kind/project controls, theme/save state and current authorized destination.
- **UX-DR38:** S10 Focus: assigned work across projects, parallel epics, combined/six-stage board with evidence/usage entry.
- **UX-DR39:** S11 Audit: full-system authorized object/version/actor/action/outcome/time history, not knowledge-only.
- **UX-DR40:** Stable route/title/h1 focus; dialog trap/inert/Escape/restore; polite coalesced arrivals and accessible load-more.
- **UX-DR41:** Field-level disclosure includes filters/counts/edges/snippets/copied IDs/recipients/history; revocation safely removes focused content; no residual leaks.
- **UX-DR42:** Offline denies new protected cache disclosure and queued admin/publication writes; reconnect reauthorizes and deduplicates; retain source/collection times.
- **UX-DR43:** Ticket progress uses measured criteria denominator/source/time; unknown/conflicting bases remain explicit.
- **UX-DR44:** Epic child-closure fraction stays labeled and separate from parent acceptance; distinguish assigned subset and authorized child set.
- **UX-DR45:** Closure/merge/check/acceptance/deployment and source fact/inference stay distinct; missing telemetry is not blockage or initiator proof.
- **UX-DR46:** UX-18: individual task-role runs/retries/children/concurrency, observed model/effort/session/location segments and configured-versus-observed values.
- **UX-DR47:** Token temporality/cache/window correctness; avoid cumulative/replay/parent-child overlap; no session-to-ticket allocation by association alone.
- **UX-DR48:** Exact-version knowledge lifecycle/eligibility/freshness; no cross-project fallback, duplicate Notion save or hidden-match disclosure.
- **UX-DR49:** Company-safe publication is separately versioned and audience-bound; changes invalidate checks; exceptions never bypass source permission.
- **UX-DR50:** UX-19/20: separate Skills/Memory read/load/delivery/observed application/human-verified reuse; exact versions and unknown coverage.
- **UX-DR51:** UX-21: audit all Owl Mast-created observations/correlations/summaries/knowledge/policies/configuration/aliases/notifications/outcomes with append-linked corrections.
- **UX-DR52:** UX-22: nonlinear Plan/Design/Build/Test/Deploy/Maintain with versioned project mapping, original source status, unmapped area and blocker badges; no drag mutation.
- **UX-DR53:** UX-23: bounded dependency graph and same-data list, prerequisite versus contribution and explicit versus inferred edges, visible cycles/gaps and no hidden stubs.
- **UX-DR54:** UX-24: configured machine/sandbox differs from time-qualified observed location; stable IDs/history/Unknown/Stale, no isolation/IP/path claims.
- **UX-DR55:** Push every distinct authorized observed work update by default; explicit event/project opt-outs, replay deduplication, reauthorize send/open, no silent digest or suppression.
- **UX-DR56:** Push not-requested/denied/unsupported independent of agent health; old notification opens current state with safe return; external arrival/recall limits.
- **UX-DR57:** Observed units/API-equivalent estimates/subscription allocation/actual bills remain separate with currency/period/price-source/date; unknown is not zero or ROI.
- **UX-DR58:** Personal alias proposal: 1–32 trimmed characters, fixed type/ID, duplicates disambiguated, accessible named colors/reset/save failure; shared authority open.
- **UX-DR59:** Both clients in both projects, actual source editions, isolated failures and independent readiness; measure recurring enrollment separately from setup.
- **UX-DR60:** Validate J1/J2/SC1–3/J6–11 and company overview with real authorized evidence and negative cases; old UX review did not validate UX18–24.

## Epic list

All nineteen epics are planned now. E01–E18 cover the full V1 plan; E17 is an optional T3 adapter and is not a prerequisite for native telemetry. E19 records the already-requested later evolution, without making it a POC release gate. Dependencies below describe implementation order, not reduced feature scope. Native standalone and T3-hosted validation both belong to E07/E08/E18.

| Epic | User outcome | Prerequisites | Scope |
|---|---|---|---|
| [E01 — Install and operate a reproducible Owl Mast workspace](epics/owl-mast-2026-11-05/epic-01.md) | Operator can run the selected stack, verify health and build changes with enforced engineering standards. | None | full V1 plan |
| [E02 — Manage tenants, personal accounts and authorized project access](epics/owl-mast-2026-11-05/epic-02.md) | People sign in independently and see only permitted tenant, project and source data, including shared external accounts. | E01 | full V1 plan |
| [E03 — Capture and maintain versioned project knowledge](epics/owl-mast-2026-11-05/epic-03.md) | Contributors and existing Notion/Hermes flows create traceable skills and memory without duplicate saves or lost source authority. | E02 | full V1 plan |
| [E04 — Retrieve authorized knowledge through MCP](epics/owl-mast-2026-11-05/epic-04.md) | Claude, Codex and authorized people find applicable exact-version knowledge through the same secured backend. | E03 | full V1 plan |
| [E05 — Enroll executing machines and native agent clients](epics/owl-mast-2026-11-05/epic-05.md) | Contributors register existing machines and clients once, select authorized projects and inspect separate observation/delivery readiness. | E02, E04 | full V1 plan |
| [E06 — Receive and normalize native telemetry reliably](epics/owl-mast-2026-11-05/epic-06.md) | Operators accept direct OTLP and semantic observations, inspect receipt/coverage and recover accepted work without duplicated accounting. | E05 | full V1 plan |
| [E07 — Use Claude Code with Owl Mast in every supported execution mode](epics/owl-mast-2026-11-05/epic-07.md) | Claude users retrieve knowledge and report supported lifecycle, usage and knowledge-use evidence standalone and within T3. | E06 | full V1 plan |
| [E08 — Use Codex with Owl Mast in every supported execution mode](epics/owl-mast-2026-11-05/epic-08.md) | Codex users receive the same product capabilities through native configuration, MCP, plugins/hooks and telemetry. | E06 | full V1 plan |
| [E09 — Connect both customer work environments](epics/owl-mast-2026-11-05/epic-09.md) | Teams observe Syntelligence Jira/GitHub and Movesion Jira/Bitbucket simultaneously with independent scopes and recovery. | E02, E06 | full V1 plan |
| [E10 — Trace work, runs, contributions and dependencies](epics/owl-mast-2026-11-05/epic-10.md) | A colleague can inspect the evidence chain, measured progress and explicit/inferred relationships without confusing activity with acceptance. | E06, E09 | full V1 plan |
| [E11 — Publish and revoke company-safe learning](epics/owl-mast-2026-11-05/epic-11.md) | Maintainers operate automatic/manual/disabled promotion and withdraw exact versions with permission-preserving derivative handling. | E03, E04 | full V1 plan |
| [E12 — Demonstrate skill and memory use and useful reuse](epics/owl-mast-2026-11-05/epic-12.md) | Reviewers distinguish availability, retrieval, delivery, native loading, observed use and human-verified useful outcomes. | E04, E07, E08 | full V1 plan |
| [E13 — Understand daily work and personal focus](epics/owl-mast-2026-11-05/epic-13.md) | Contributors and leads use Daily Work, company views, concurrent epic Focus and six-stage kanban with honest evidence and coverage. | E10 | full V1 plan |
| [E14 — Understand usage and cost with defensible attribution](epics/owl-mast-2026-11-05/epic-14.md) | People inspect per-task model/effort/session/machine/token usage and clearly separated cost classes without double-counting. | E06, E07, E08, E10 | full V1 plan |
| [E15 — Receive every eligible work update and return safely](epics/owl-mast-2026-11-05/epic-15.md) | Users control push preferences and open current authorized work from distinct update notifications on supported devices. | E10, E11 | full V1 plan |
| [E16 — Inspect full-system audit and govern retained data](epics/owl-mast-2026-11-05/epic-16.md) | Operators trace all Owl Mast actions and enforce collection, retention, removal and revocation across primary and derived records. | E02, E06, E11 | full V1 plan |
| [E17 — Enrich native observations with optional T3 context](epics/owl-mast-2026-11-05/epic-17.md) | T3 users add supported thread/delegation/workstation context without making T3 the path for native telemetry or execution authority. | E06, E10 | full V1 plan |
| [E18 — Prove the complete pilot and publish a reproducible release](epics/owl-mast-2026-11-05/epic-18.md) | The owner can accept live two-project outcomes, recovery and boundaries; operators can reproduce the release independently of public publication. | E01, E02, E03, E04, E05, E06, E07, E08, E09, E10, E11, E12, E13, E14, E15, E16 | full V1 plan |
| [E19 — Evolve tenant scale, permissions and availability](epics/owl-mast-2026-11-05/epic-19.md) | Operators can introduce multiple active tenants, OpenFGA and multiple application replicas when the agreed later-stage needs arise. | E18 | planned later evolution |

## Requirements coverage map

### Functional coverage

| Requirement | Planned epics |
|---|---|
| FR-1 | E02, E09, E18 |
| FR-2 | E05, E07, E08, E18 |
| FR-3 | E01, E05, E06, E09, E16, E17 |
| FR-4 | E05, E06, E07, E08, E10, E17 |
| FR-5 | E09, E10, E17, E18 |
| FR-6 | E09, E10, E13 |
| FR-7 | E10, E13, E15 |
| FR-8 | E03, E16 |
| FR-9 | E03, E11 |
| FR-10 | E04, E07, E08 |
| FR-11 | E07, E08, E12, E16, E18 |
| FR-12 | E11, E18 |
| FR-13 | E03, E11, E16 |
| FR-14 | E03 |
| FR-15 | E13, E15 |
| FR-16 | E06, E07, E08, E12, E14 |
| FR-17 | E02, E04, E11, E15, E16, E18, E19 |
| FR-18 | E02, E06, E16, E18 |
| FR-19 | E02, E05, E07, E08, E17 |
| FR-20 | E01, E16, E18, E19 |
| FR-21 | E03, E04, E07, E08, E18 |

### UX coverage

Every shared component and surface has a separate extraction ID above. Each epic and story must carry applicable IDs, in addition to its detailed source acceptance criteria.

| Requirement | Planned epics |
|---|---|
| UX-DR01 | E01 |
| UX-DR02 | E01 |
| UX-DR03 | E01 |
| UX-DR04 | E01, E18 |
| UX-DR05 | E01, E18 |
| UX-DR06 | E01, E18 |
| UX-DR07 | E01 |
| UX-DR08 | E01, E02, E13, E19 |
| UX-DR09 | E01, E13 |
| UX-DR10 | E13 |
| UX-DR11 | E13 |
| UX-DR12 | E10, E13 |
| UX-DR13 | E10, E13 |
| UX-DR14 | E10, E13 |
| UX-DR15 | E05, E13 |
| UX-DR16 | E13 |
| UX-DR17 | E13 |
| UX-DR18 | E10, E13 |
| UX-DR19 | E06, E13, E15, E16 |
| UX-DR20 | E03, E11 |
| UX-DR21 | E04, E07, E08, E12 |
| UX-DR22 | E05, E06, E07, E08, E09, E17 |
| UX-DR23 | E11 |
| UX-DR24 | E12, E14 |
| UX-DR25 | E01, E02, E03, E05, E11, E15 |
| UX-DR26 | E01, E02, E03, E05, E06, E09, E13, E15, E16 |
| UX-DR27 | E01, E02, E03, E11 |
| UX-DR28 | E01, E10 |
| UX-DR29 | E13 |
| UX-DR30 | E10, E13, E14, E17 |
| UX-DR31 | E03, E04 |
| UX-DR32 | E03, E04, E11, E12, E16 |
| UX-DR33 | E05, E07, E08, E17 |
| UX-DR34 | E11 |
| UX-DR35 | E12, E14 |
| UX-DR36 | E02, E05, E09, E16, E19 |
| UX-DR37 | E15 |
| UX-DR38 | E13 |
| UX-DR39 | E16 |
| UX-DR40 | E01, E13, E15, E18 |
| UX-DR41 | E02, E06, E10, E11, E13, E14, E15, E16, E18, E19 |
| UX-DR42 | E01, E06, E13, E15, E16, E18 |
| UX-DR43 | E09, E10, E13 |
| UX-DR44 | E10, E13 |
| UX-DR45 | E09, E10, E13 |
| UX-DR46 | E06, E07, E08, E10, E14, E17 |
| UX-DR47 | E06, E07, E08, E14 |
| UX-DR48 | E03, E04, E11, E16 |
| UX-DR49 | E11 |
| UX-DR50 | E07, E08, E12 |
| UX-DR51 | E01, E16 |
| UX-DR52 | E10, E13 |
| UX-DR53 | E10, E13 |
| UX-DR54 | E05, E06, E07, E08, E17 |
| UX-DR55 | E15, E18 |
| UX-DR56 | E15, E18 |
| UX-DR57 | E14 |
| UX-DR58 | E05 |
| UX-DR59 | E05, E07, E08, E09, E18 |
| UX-DR60 | E18 |

### Architecture and quality coverage

| Requirement | Planned epics |
|---|---|
| AR-01 | E01, E18 |
| AR-02 | E01, E19 |
| AR-03 | E01, E04, E06, E19 |
| AR-04 | E01, E18 |
| AR-05 | E01, E03, E04 |
| AR-06 | E03, E04, E07, E08, E16 |
| AR-07 | E01, E02, E06, E10, E16 |
| AR-08 | E02, E19 |
| AR-09 | E02, E05 |
| AR-10 | E02, E16, E19 |
| AR-11 | E01, E06, E09, E15, E16, E18 |
| AR-12 | E01, E18, E19 |
| AR-13 | E01, E16, E18, E19 |
| AR-14 | E05, E06, E07, E08, E18 |
| AR-15 | E04, E06 |
| AR-16 | E04, E07, E08, E12, E17 |
| AR-17 | E02, E04, E06, E11, E16 |
| AR-18 | E05, E06, E10, E14 |
| AR-19 | E05, E07, E08 |
| AR-20 | E19 |

NFR-1–NFR-6 are shared completion requirements, with focused proofs: E02/E04/E11/E16/E18 for isolation; E06/E10/E12/E14 for evidence integrity; E01/E06/E09/E18 for resilience; E05/E09/E18 for declared freshness; E01/E05/E07/E08/E13/E15/E18 for usability; and E01/E02/E06/E16/E18 for diagnostic safety. No feature can waive these by omitting a local tag.

## Delivery sequence and parallel work

| Stage | Work that can proceed after its prerequisites | Exit evidence |
|---|---|---|
| Foundation | E01, then E02 | Reproducible application, identity/scope boundaries, durable jobs and baseline audit contract. |
| Useful knowledge | E03, then E04 | Existing source learning retained; authorized version/package retrieval through MCP. |
| Enrollment and governance | E05 and E11 can proceed independently after their listed prerequisites | Registered executing clients with explicit scope; version-safe promotion policy. |
| Native evidence | E06, then E07/E08/E09/E16 in parallel | Receiver contract plus both native adapters, both work environments and inspectable audit/removal paths. |
| Evidence and reuse | E10 and E12 after their respective prerequisites | Work/run/contribution relationships and differentiated load/use/verified-reuse evidence. |
| Complete product views | E13/E14/E15 and optional E17 after their respective prerequisites | Daily/Focus views, defensible accounting, authorized all-update push and optional T3 context. |
| Pilot and release qualification | E18 | Real authorized two-project/client proof, failure recovery, UX/accessibility and separate public-release gate. |
| Planned later evolution | E19 | Multi-tenant operation, optional OpenFGA, multi-pod upgrades or measured extraction when selected. |

This sequence is not a schedule or delivery estimate. Do not enable real-data collection merely because an earlier implementation slice compiles. E07/E08 include both standalone and T3-hosted runtimes; E17 is not their prerequisite. Shared contracts allow parallel work after dependencies are fulfilled; stories only depend on earlier stories or prerequisite epics.

## Shared story completion rules

- Every story states a user outcome, requirement IDs, dependencies, testable success/error criteria and unchecked implementation tasks. Task IDs are stable local identifiers. Implementation tasks inherit the story's prerequisites; within a story they are ordered unless explicitly independent. Exception: qualification/contract-design work assigned to an owning story in the architecture spine's Deferred table may be pulled forward using documentation or synthetic fixtures before a consumer begins. The named owner publishes the shared contract once; production feature code/migrations, live actions and story completion remain behind the original prerequisites. This permits OM-05.02-T1 enrollment credential design before OM-04.03 MCP implementation without declaring E05 implemented.
- Implement only schema and APIs owned by the story. Feature modules call explicit interfaces rather than reading or writing another module's private tables. Version public ingress/event contracts and migrate overlapping versions deliberately.
- Every disclosure/mutation applies current tenant/project/source/purpose authorization, including fields, filters, graph expansion, historical payloads, counters and derived results. Unknown authorization fails closed. Test applicable negative paths alongside the useful path.
- Emit safe audit evidence from each feature's first mutation/ingestion story. A covered successful mutation commits atomically with its audit record or durable audit-publication intent; failed/denied attempts use a separate safe outcome path. E16 provides complete inspection, retention and reconciliation; it is not the point at which earlier actions begin to be audited.
- Actual and inferred identities, source/recorded times, unknown/unsupported/gap states, and observed versus estimated units remain distinguishable. Internal retries are permitted; agent execution/retry/merge/deployment controls remain excluded.
- Run meaningful tests and required build/format/static/dependency checks for implementation. Use Testcontainers with qualified, pinned PostgreSQL/VectorChord and Keycloak images where those integrations are exercised; do not substitute a database without the required extensions. Keep frontend unit/component tests, API compatibility checks and selected browser-to-real-backend paths. Validate interfaces with fixtures, then qualify actual clients/sources and Kubernetes recovery before claiming support. A synthetic test cannot satisfy live pilot proof.
- Preserve every applicable DESIGN/EXPERIENCE rule, including theme/contrast, focus/reading stability, phone/keyboard access, exact-version knowledge and notification authorization. Provisional UX details are explicitly resolved in the owning story.
- Owner decisions and live-access approvals are recorded at their stated checkpoints. A planned task is not permission to ingest customer data, schedule backups, publish a release or create accounts in external systems now.

## Decision and qualification gates

| Gate | Decision/evidence required | Owner/checkpoint | Planned work |
|---|---|---|---|
| A-1 | Adopted 2026-11-06: client-driven search/load, validated-only default and explicit client flag for labelled unvalidated candidates; bounded responses and no automatic lesson injection. | Decision settled; verify behavior in pilot knowledge-quality acceptance. | E03/E04/E07/E08 and OM-18.03. |
| A-2 | Adopted 2026-11-06: stop future retrieval of withdrawn/quarantined versions and promoted derivatives; preserve restricted history and lineage without promising recall of earlier external copies. | Decision settled; verify lifecycle propagation and disclosure behavior before live promotion. | E03/E11/E16 and OM-18.03. |
| A-3 | Full capture and 30 active days followed by retained archive adopted on 2026-11-06; no automatic archive purge or 30-day project-knowledge expiry. Qualify archive storage/recovery, other record-class policies and actual-environment permissions/destinations. | Defaults settled; product/project data owners and operator qualify remaining controls before live use. | OM-02.05, E06/E09/E16, OM-16.06. |
| A-4 — adopted 2026-11-06 | Disabled promotion prevents new publication, including queued/in-flight commits; existing publications remain eligible under current permissions/lifecycle until separately withdrawn, superseded or otherwise ineligible. | Verify concurrency-safe mode changes and continued eligible retrieval before live promotion. | E11 and OM-18.03. |
| A-5 | One reusable client profile plus project selection/readiness as the recurring enrollment ceiling. | Product owner + pilot participants, enrollment trials before acceptance. | E05/E07/E08 and OM-18.01. |
| A-6 | Minimum per-project verified reuse and cross-project publication samples. | Product owner + pilot participants, before acceptance sample selection. | E12 and OM-18.03. |
| Source feasibility | Actual Jira/Bitbucket editions, API/event availability, scoped credentials and source-permission authority. | Integration owner, before connector-specific commitments or estimates. | First E09 story. |
| Native capability | Claude/Codex versions, supported fields/signals, native skill activation, standalone/T3 configuration and loss windows. | Integration owner, before a supported-runtime claim. | E05–E08, OM-18.01. |
| Protocol/security | Browser login/session and origin policy for separate frontend/backend deployments; Keycloak/MCP OAuth interoperability; agent credential lifecycle; direct receiver auth, limits and redaction. | Architecture/security owner, before exposing authenticated integration beyond fixtures. | E02/E04/E05/E06. |
| Storage/recovery | VectorChord/R2DBC fit, large/binary storage, snapshot consistency, driver/failure coverage, frequency/retention and recovery targets. | Architecture/operator, before relying on live storage/recovery. | E01/E03/E04, OM-18.02. |
| UI/push | Separate frontend/backend deployment adopted; qualify frontend toolchain pins, API compatibility policy and browser/PWA/native push across target devices, including permitted previews and actual delivery limits. React/TypeScript/Vite remains the recommended frontend seed. | Product/UX/implementation owners, before claiming supported mobile push. | OM-01.04, first E15 story. |
| Publication authority | Named maintainers and authorized permitted-use input/company-safe policy. | Project data owners, before live promotion. | E11, OM-18.03. |
| Calibration | Work samples, existing acceptance authority/artifact, latency/freshness/setup budgets and baseline measures. | Product owner + pilot participants, before relevant acceptance run. | OM-18.01/03. |
| Public release | Open-source license, dependency compatibility and sanitized distributable artifacts. | Product owner, before public publication. | OM-18.04. |

## Full-scope acceptance

SC-1 (understand a colleague's work), SC-2 (useful learning reaches another contributor's agent) and SC-3 (company-safe cross-project reuse) must be demonstrated for the two required environments. All four Claude/Codex × project combinations remain required; the latest integration correction adds standalone and T3-hosted runtime qualification. Native logs, metrics and traces are separately capability-tested, with explicit unsupported/gap status rather than fabricated coverage.

SM-1–SM-5 and counter-metrics SM-C1–SM-C4 remain the outcome measures. All FR-17 negative cases must pass: both project directions, third identity, revoked user, same-project restricted source and source revocation after indexing. Promotion-mode/version races and derivative withdrawal are mandatory. The post-review UX-18–24 additions require new validation. Fixtures support tests; actual authorized source chains and human-verified reuse support acceptance.

The plan does not add agent execution controls, a replacement tracker/harness, sandbox hosting, monetization, predictive budget allocation, universal connectors or causal ROI claims. Future workflow engines and external collectors remain conditional choices, not hidden new deployment requirements.



## Stories and task navigation

The full plan contains **19 epics, 85 stories and 340 concrete tasks**. Each linked story includes its user outcome, requirement IDs, prerequisites, Given/When/Then acceptance criteria and implementation/verification tasks. All remain planned.

### E01 — Install and operate a reproducible Owl Mast workspace

- [OM-01.01 — Bootstrap the supported Java application](epics/owl-mast-2026-11-05/epic-01.md#om-01-01) — 4 tasks; prerequisites: None
- [OM-01.02 — Install optional state and identity dependencies](epics/owl-mast-2026-11-05/epic-01.md#om-01-02) — 4 tasks; prerequisites: OM-01.01
- [OM-01.03 — Recover accepted background work and record mutation evidence](epics/owl-mast-2026-11-05/epic-01.md#om-01-03) — 4 tasks; prerequisites: OM-01.01
- [OM-01.04 — Open an accessible workspace shell](epics/owl-mast-2026-11-05/epic-01.md#om-01-04) — 4 tasks; prerequisites: OM-01.01

### E02 — Manage tenants, personal accounts and authorized project access

- [OM-02.01 — Sign in with a personal Owl Mast identity](epics/owl-mast-2026-11-05/epic-02.md#om-02-01) — 4 tasks; prerequisites: E01
- [OM-02.02 — Create tenant and project membership boundaries](epics/owl-mast-2026-11-05/epic-02.md#om-02-02) — 4 tasks; prerequisites: OM-02.01
- [OM-02.03 — Map shared external accounts without merging people](epics/owl-mast-2026-11-05/epic-02.md#om-02-03) — 4 tasks; prerequisites: OM-02.02
- [OM-02.04 — Enforce resource and source permissions through one boundary](epics/owl-mast-2026-11-05/epic-02.md#om-02-04) — 4 tasks; prerequisites: OM-02.02
- [OM-02.05 — Approve collection boundaries before enabling live sources](epics/owl-mast-2026-11-05/epic-02.md#om-02-05) — 4 tasks; prerequisites: OM-02.04

### E03 — Capture and maintain versioned project knowledge

- [OM-03.01 — Submit project knowledge with immutable version identity](epics/owl-mast-2026-11-05/epic-03.md#om-03-01) — 4 tasks; prerequisites: E02
- [OM-03.02 — Preserve complete versioned skill packages](epics/owl-mast-2026-11-05/epic-03.md#om-03-02) — 4 tasks; prerequisites: OM-03.01
- [OM-03.03 — Synchronize permitted Notion knowledge and preserve Hermes capture](epics/owl-mast-2026-11-05/epic-03.md#om-03-03) — 4 tasks; prerequisites: OM-03.01, OM-03.02
- [OM-03.04 — Evaluate and correct project knowledge lifecycle states](epics/owl-mast-2026-11-05/epic-03.md#om-03-04) — 4 tasks; prerequisites: OM-03.01, OM-03.02
- [OM-03.05 — Browse and maintain knowledge in the scoped catalog and detail UI](epics/owl-mast-2026-11-05/epic-03.md#om-03-05) — 4 tasks; prerequisites: OM-03.03, OM-03.04

### E04 — Retrieve authorized knowledge through MCP

- [OM-04.01 — Build lexical and VectorChord retrieval over eligible knowledge](epics/owl-mast-2026-11-05/epic-04.md#om-04-01) — 4 tasks; prerequisites: E03
- [OM-04.02 — Return authorized exact-version knowledge with honest coverage](epics/owl-mast-2026-11-05/epic-04.md#om-04-02) — 4 tasks; prerequisites: OM-04.01
- [OM-04.03 — Expose authenticated remote MCP in the Spring backend](epics/owl-mast-2026-11-05/epic-04.md#om-04-03) — 4 tasks; prerequisites: OM-04.02
- [OM-04.04 — Deliver complete exact-version packages with explicit receipts](epics/owl-mast-2026-11-05/epic-04.md#om-04-04) — 4 tasks; prerequisites: OM-04.02, OM-04.03

### E05 — Enroll executing machines and native agent clients

- [OM-05.01 — Register a machine and client without conflating identities](epics/owl-mast-2026-11-05/epic-05.md#om-05-01) — 4 tasks; prerequisites: E02, E04.
- [OM-05.02 — Bind enrolled clients to authorized projects and revocable credentials](epics/owl-mast-2026-11-05/epic-05.md#om-05-02) — 4 tasks; prerequisites: OM-05.01.
- [OM-05.03 — Show observation and knowledge readiness independently](epics/owl-mast-2026-11-05/epic-05.md#om-05-03) — 4 tasks; prerequisites: OM-05.02.
- [OM-05.04 — Define portable native configuration packages and safe repair](epics/owl-mast-2026-11-05/epic-05.md#om-05-04) — 4 tasks; prerequisites: OM-05.02, OM-05.03.
- [OM-05.05 — Personalize agent appearance without changing identity](epics/owl-mast-2026-11-05/epic-05.md#om-05-05) — 4 tasks; prerequisites: OM-05.01, OM-05.02.

### E06 — Receive and normalize native telemetry reliably

- [OM-06.01 — Bind collection to enrollment and the approved content policy](epics/owl-mast-2026-11-05/epic-06.md#om-06-01) — 4 tasks; prerequisites: E05
- [OM-06.02 — Accept the native OTLP wire protocols in Spring](epics/owl-mast-2026-11-05/epic-06.md#om-06-02) — 4 tasks; prerequisites: OM-06.01
- [OM-06.03 — Normalize evidence without inventing missing identity or capability](epics/owl-mast-2026-11-05/epic-06.md#om-06-03) — 4 tasks; prerequisites: OM-06.02
- [OM-06.04 — Recover accepted observations and suppress repeated accounting](epics/owl-mast-2026-11-05/epic-06.md#om-06-04) — 4 tasks; prerequisites: OM-06.03
- [OM-06.05 — Make ingestion health and coverage inspectable](epics/owl-mast-2026-11-05/epic-06.md#om-06-05) — 3 tasks; prerequisites: OM-06.04

### E07 — Use Claude Code with Owl Mast in every supported execution mode

- [OM-07.01 — Package and qualify native Claude integration](epics/owl-mast-2026-11-05/epic-07.md#om-07-01) — 4 tasks; prerequisites: E06
- [OM-07.02 — Deliver exact knowledge and native skill packages to Claude](epics/owl-mast-2026-11-05/epic-07.md#om-07-02) — 4 tasks; prerequisites: OM-07.01
- [OM-07.03 — Send Claude observations directly without controlling execution](epics/owl-mast-2026-11-05/epic-07.md#om-07-03) — 4 tasks; prerequisites: OM-07.01
- [OM-07.04 — Prove Claude works across both projects and execution modes](epics/owl-mast-2026-11-05/epic-07.md#om-07-04) — 4 tasks; prerequisites: OM-07.02, OM-07.03

### E08 — Use Codex with Owl Mast in every supported execution mode

- [OM-08.01 — Package and qualify the native Codex connection](epics/owl-mast-2026-11-05/epic-08.md#om-08-01) — 4 tasks; prerequisites: E06
- [OM-08.02 — Deliver exact-version memory and complete Codex skills](epics/owl-mast-2026-11-05/epic-08.md#om-08-02) — 4 tasks; prerequisites: OM-08.01
- [OM-08.03 — Observe native Codex work with its actual event contracts](epics/owl-mast-2026-11-05/epic-08.md#om-08-03) — 4 tasks; prerequisites: OM-08.01
- [OM-08.04 — Prove Codex integration and recovery in all pilot combinations](epics/owl-mast-2026-11-05/epic-08.md#om-08-04) — 4 tasks; prerequisites: OM-08.02, OM-08.03

### E09 — Connect both customer work environments

- [OM-09.01 — Qualify actual source editions and permission contracts](epics/owl-mast-2026-11-05/epic-09.md#om-09-01) — 4 tasks; prerequisites: E02, E06
- [OM-09.02 — Observe both qualified Jira sites independently](epics/owl-mast-2026-11-05/epic-09.md#om-09-02) — 4 tasks; prerequisites: OM-09.01
- [OM-09.03 — Observe Syntelligence contributions from GitHub](epics/owl-mast-2026-11-05/epic-09.md#om-09-03) — 4 tasks; prerequisites: OM-09.01
- [OM-09.04 — Observe Movesion contributions from Bitbucket](epics/owl-mast-2026-11-05/epic-09.md#om-09-04) — 4 tasks; prerequisites: OM-09.01
- [OM-09.05 — Reconcile both environments and explain connection coverage](epics/owl-mast-2026-11-05/epic-09.md#om-09-05) — 4 tasks; prerequisites: OM-09.02, OM-09.03, OM-09.04

### E10 — Trace work, runs, contributions and dependencies

- [OM-10.01 — Correlate source records without inventing attribution](epics/owl-mast-2026-11-05/epic-10.md#om-10-01) — 4 tasks; prerequisites: E06, E09.
- [OM-10.02 — Inspect each observed task and run independently](epics/owl-mast-2026-11-05/epic-10.md#om-10-02) — 4 tasks; prerequisites: OM-10.01.
- [OM-10.03 — Calculate progress from explicit evidence](epics/owl-mast-2026-11-05/epic-10.md#om-10-03) — 4 tasks; prerequisites: OM-10.01.
- [OM-10.04 — Inspect the authorized dependency graph and equivalent list](epics/owl-mast-2026-11-05/epic-10.md#om-10-04) — 4 tasks; prerequisites: OM-10.01.
- [OM-10.05 — Follow work evidence into source tools safely](epics/owl-mast-2026-11-05/epic-10.md#om-10-05) — 4 tasks; prerequisites: OM-10.02, OM-10.03, OM-10.04.

### E11 — Publish and revoke company-safe learning

- [OM-11.01 — Configure project promotion policy and permitted audiences](epics/owl-mast-2026-11-05/epic-11.md#om-11-01) — 4 tasks; prerequisites: E03, E04
- [OM-11.02 — Evaluate an exact company-safe publication candidate](epics/owl-mast-2026-11-05/epic-11.md#om-11-02) — 4 tasks; prerequisites: OM-11.01
- [OM-11.03 — Publish safely in automatic and manual modes under races](epics/owl-mast-2026-11-05/epic-11.md#om-11-03) — 4 tasks; prerequisites: OM-11.01, OM-11.02
- [OM-11.04 — Withdraw or quarantine guidance and its promoted derivatives](epics/owl-mast-2026-11-05/epic-11.md#om-11-04) — 4 tasks; prerequisites: OM-11.03
- [OM-11.05 — Review promotion policy, exceptions and lifecycle in S6](epics/owl-mast-2026-11-05/epic-11.md#om-11-05) — 4 tasks; prerequisites: OM-11.01, OM-11.02, OM-11.03, OM-11.04

### E12 — Demonstrate skill and memory use and useful reuse

- [OM-12.01 — Preserve distinct exact-version knowledge evidence](epics/owl-mast-2026-11-05/epic-12.md#om-12-01) — 4 tasks; prerequisites: E04, E07, E08
- [OM-12.02 — Record human-verified useful reuse against task evidence](epics/owl-mast-2026-11-05/epic-12.md#om-12-02) — 4 tasks; prerequisites: OM-12.01
- [OM-12.03 — Aggregate Skills and Memory measurements without false completeness](epics/owl-mast-2026-11-05/epic-12.md#om-12-03) — 4 tasks; prerequisites: OM-12.01, OM-12.02
- [OM-12.04 — Inspect knowledge receipts, statistics and reuse evidence](epics/owl-mast-2026-11-05/epic-12.md#om-12-04) — 4 tasks; prerequisites: OM-12.02, OM-12.03

### E13 — Understand daily work and personal focus

- [OM-13.01 — Understand own and colleague work from Daily Work](epics/owl-mast-2026-11-05/epic-13.md#om-13-01) — 4 tasks; prerequisites: E10.
- [OM-13.02 — Compare authorized project context in a company view](epics/owl-mast-2026-11-05/epic-13.md#om-13-02) — 4 tasks; prerequisites: OM-13.01.
- [OM-13.03 — Follow assigned work across concurrent epics](epics/owl-mast-2026-11-05/epic-13.md#om-13-03) — 4 tasks; prerequisites: OM-13.01.
- [OM-13.04 — Inspect work through the six observed SDLC stages](epics/owl-mast-2026-11-05/epic-13.md#om-13-04) — 4 tasks; prerequisites: OM-13.03.
- [OM-13.05 — Keep live work views accessible and stable during change](epics/owl-mast-2026-11-05/epic-13.md#om-13-05) — 4 tasks; prerequisites: OM-13.01, OM-13.02, OM-13.03, OM-13.04.

### E14 — Understand usage and cost with defensible attribution

- [OM-14.01 — Calculate unique observed usage with correct counter semantics](epics/owl-mast-2026-11-05/epic-14.md#om-14-01) — 4 tasks; prerequisites: E06, E07, E08, E10
- [OM-14.02 — Attribute usage only to evidenced work and execution segments](epics/owl-mast-2026-11-05/epic-14.md#om-14-02) — 4 tasks; prerequisites: OM-14.01
- [OM-14.03 — Keep observed units, estimates, allocations and bills separate](epics/owl-mast-2026-11-05/epic-14.md#om-14-03) — 4 tasks; prerequisites: OM-14.02
- [OM-14.04 — Present S7 and contextual work usage with honest coverage](epics/owl-mast-2026-11-05/epic-14.md#om-14-04) — 4 tasks; prerequisites: OM-14.03

### E15 — Receive every eligible work update and return safely

- [OM-15.01 — Qualify the notification platform and choose supported packaging](epics/owl-mast-2026-11-05/epic-15.md#om-15-01) — 4 tasks; prerequisites: E10, E11.
- [OM-15.02 — Control notification preferences without hiding work updates](epics/owl-mast-2026-11-05/epic-15.md#om-15-02) — 4 tasks; prerequisites: OM-15.01.
- [OM-15.03 — Dispatch distinct updates through durable authorized work](epics/owl-mast-2026-11-05/epic-15.md#om-15-03) — 4 tasks; prerequisites: OM-15.01, OM-15.02.
- [OM-15.04 — Open the current authorized state from a notification](epics/owl-mast-2026-11-05/epic-15.md#om-15-04) — 4 tasks; prerequisites: OM-15.03.

### E16 — Inspect full-system audit and govern retained data

- [OM-16.01 — Query full-system audit with explicit coverage](epics/owl-mast-2026-11-05/epic-16.md#om-16-01) — 4 tasks; prerequisites: E02, E06, E11.
- [OM-16.02 — Inspect audit timelines and object changes accessibly](epics/owl-mast-2026-11-05/epic-16.md#om-16-02) — 4 tasks; prerequisites: OM-16.01.
- [OM-16.03 — Approve collection and retention policy before live ingestion](epics/owl-mast-2026-11-05/epic-16.md#om-16-03) — 4 tasks; prerequisites: OM-16.01.
- [OM-16.04 — Propagate removal and revocation through derived records](epics/owl-mast-2026-11-05/epic-16.md#om-16-04) — 4 tasks; prerequisites: OM-16.03, E11.
- [OM-16.05 — Preserve governance during replay and snapshot recovery](epics/owl-mast-2026-11-05/epic-16.md#om-16-05) — 4 tasks; prerequisites: OM-16.03, OM-16.04.
- [OM-16.06 — Archive conversations after 30 days without losing knowledge](epics/owl-mast-2026-11-05/epic-16.md#om-16-06) — 5 tasks; prerequisites: OM-16.05.

### E17 — Enrich native observations with optional T3 context

- [OM-17.01 — Qualify a minimal read-only T3 connection](epics/owl-mast-2026-11-05/epic-17.md#om-17-01) — 4 tasks; prerequisites: E06, E10
- [OM-17.02 — Reconcile T3 context with existing native evidence](epics/owl-mast-2026-11-05/epic-17.md#om-17-02) — 4 tasks; prerequisites: OM-17.01
- [OM-17.03 — Inspect and recover optional enrichment independently](epics/owl-mast-2026-11-05/epic-17.md#om-17-03) — 4 tasks; prerequisites: OM-17.02

### E18 — Prove the complete pilot and publish a reproducible release

- [OM-18.01 — Qualify the full runtime and source capability matrix](epics/owl-mast-2026-11-05/epic-18.md#om-18-01) — 4 tasks; prerequisites: E01, E02, E03, E04, E05, E06, E07, E08, E09, E10, E11, E12, E13, E14, E15, E16
- [OM-18.02 — Restore the installation and survive processing failures](epics/owl-mast-2026-11-05/epic-18.md#om-18-02) — 4 tasks; prerequisites: OM-18.01
- [OM-18.03 — Demonstrate observation-to-reuse and every access boundary](epics/owl-mast-2026-11-05/epic-18.md#om-18-03) — 4 tasks; prerequisites: OM-18.02
- [OM-18.04 — Package a reproducible internal and public-ready release](epics/owl-mast-2026-11-05/epic-18.md#om-18-04) — 4 tasks; prerequisites: OM-18.03

### E19 — Evolve tenant scale, permissions and availability

- [OM-19.01 — Operate multiple active tenants](epics/owl-mast-2026-11-05/epic-19.md#om-19-01) — 4 tasks; prerequisites: E18
- [OM-19.02 — Introduce fine-grained OpenFGA authorization](epics/owl-mast-2026-11-05/epic-19.md#om-19-02) — 4 tasks; prerequisites: OM-19.01
- [OM-19.03 — Run multiple application pods with compatible upgrades](epics/owl-mast-2026-11-05/epic-19.md#om-19-03) — 4 tasks; prerequisites: E18
- [OM-19.04 — Extract components only when measurements justify them](epics/owl-mast-2026-11-05/epic-19.md#om-19-04) — 4 tasks; prerequisites: E18

## Validation and handoff status

[Validation and exact story coverage](epics/owl-mast-2026-11-05/VALIDATION.md) records the checks and independent-review fixes. All 107 extracted requirement IDs map to stories; IDs, prerequisites and local links were checked. The complete plan remains `draft` for owner review. Actual integration qualification and the architecture/product gates above remain open; no feature has been implemented by this planning work.
