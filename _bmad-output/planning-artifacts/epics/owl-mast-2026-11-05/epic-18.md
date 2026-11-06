---
epic: E18
status: planned
review_status: pending-owner-review
scope: v1
---

# Epic E18 — Prove the complete pilot and publish a reproducible release

The owner can judge real end-to-end value and boundaries, while an operator can reproduce the supported release.

**Epic prerequisites:** E01, E02, E03, E04, E05, E06, E07, E08, E09, E10, E11, E12, E13, E14, E15, E16

This is a planning draft. [Full scope and shared requirements](../../epics.md) apply to every story. Tasks are ordered within a story; its acceptance criteria determine completion. Policy decisions and live-environment approvals remain explicit gates.

<a id="om-18-01"></a>

### OM-18.01 — Qualify the full runtime and source capability matrix

As a pilot operator, I want to see measured support for every required runtime/source combination, so that unsupported behavior is explicit and never substituted with a narrower pilot.

**Requirements:** FR-1, FR-2, FR-3, FR-16, FR-21, NFR-4, NFR-5, AR-14, AR-18, UX-DR46, UX-DR47, UX-DR50, UX-DR54, UX-DR59

**Depends on:** E01, E02, E03, E04, E05, E06, E07, E08, E09, E10, E11, E12, E13, E14, E15, E16

**Acceptance criteria:**

- **AC1: Given** both native clients and both project environments, **when** standalone and T3-hosted validation runs, **then** enrollment, MCP delivery, hooks, logs/metrics/traces and per-field coverage are reported separately for the actual supported versions.
- **AC2: Given** a required field or supported signal is unavailable, **when** qualification completes, **then** the gap remains an acceptance blocker or explicit owner decision; neither fixtures nor T3 metadata are presented as measured native support.
- **AC3: Given** freshness and setup performance are evaluated, **when** acceptance measurements begin, **then** budgets and samples were agreed beforehand and failed trials stay in the denominator.

**Tasks:**

- [ ] **OM-18.01-T1** Create the Claude/Codex × standalone/T3-hosted × both-project capability matrix, including current machine/sandbox and optional signal restrictions.
- [ ] **OM-18.01-T2** Exercise model/effort changes, subagents/retries, native skill load/use, shared sessions and exporter configuration inheritance.
- [ ] **OM-18.01-T3** Validate direct Notion creation/reading separately from Owl Mast MCP and preserve Hermes capture without a second save.
- [ ] **OM-18.01-T4** Resolve A-5 and set source cadence/stale thresholds and measured latency/setup budgets before the acceptance run; publish limitations.

<a id="om-18-02"></a>

### OM-18.02 — Restore the installation and survive processing failures

As a operator, I want to recover accepted data and processing from the chosen storage backups, so that POC downtime does not turn into unexplained loss or duplicate accounting.

**Requirements:** FR-3, FR-20, NFR-3, NFR-6, AR-11, AR-12, AR-13, UX-DR42

**Depends on:** OM-18.01

**Acceptance criteria:**

- **AC1: Given** a qualified CSI storage implementation and complete database snapshot, **when** the installation is restored, **then** PostgreSQL/WAL, Keycloak data and required blob/configuration state are recoverable with measured results.
- **AC2: Given** a pod dies during ingest, normalization or notification processing, **when** the application restarts, **then** acknowledged work recovers and duplicates do not inflate counts or bypass current permissions.
- **AC3: Given** a client crashes before export or loses connectivity, **when** the incident is examined, **then** unreceived telemetry is not invented; the documented loss window and visible coverage accurately reflect the native exporter limits.
- **AC4: Given** a restored snapshot predates a membership/source revocation, knowledge withdrawal or completed notification, **when** recovery starts, **then** ordinary disclosure and external dispatch stay quarantined until current authority, eligibility and effect state are reconciled; unverifiable cases remain withheld with an explicit recovery exception rather than resurrecting access or blindly resending effects.

**Tasks:**

- [ ] **OM-18.02-T1** Choose snapshot support, consistency procedure, failure coverage and recovery targets with the operator; implement and qualify the backup-retention policy owned by OM-16.03 before relying on live backups.
- [ ] **OM-18.02-T2** Document and test restore into an isolated synthetic environment including database WAL, archived conversation payloads with their metadata/evidence links and separately stored artifacts; preserve encryption/secret references and consume and qualify the single Governance-owned OM-16.05 recovery quarantine/reconciliation/release gate before reads or external effects resume; do not implement a competing readiness/release authority.
- [ ] **OM-18.02-T3** Run bounded receiver saturation, partial acceptance, late/duplicate input, pod termination and stale-lease recovery; restore snapshots preceding revocation, withdrawal and a sent notification to verify fail-closed reconciliation and safe effect replay.
- [ ] **OM-18.02-T4** Publish measured RPO/RTO and native telemetry loss limits; propose an optional persistent collector only if measured requirements justify it, without deploying one automatically.

<a id="om-18-03"></a>

### OM-18.03 — Demonstrate observation-to-reuse and every access boundary

As a product owner, I want to evaluate real work understanding and useful learning, so that pilot acceptance rests on evidence from both customer environments.

**Requirements:** FR-2, FR-5, FR-11, FR-12, FR-13, FR-17, FR-18, FR-21, NFR-1, NFR-2, NFR-5, UX-DR04, UX-DR05, UX-DR06, UX-DR40, UX-DR41, UX-DR42, UX-DR55, UX-DR56, UX-DR60

**Depends on:** OM-18.02

**Acceptance criteria:**

- **AC1: Given** approved live data permissions and selected work samples, **when** SC-1, SC-2 and SC-3 are demonstrated, **then** both source chains, both clients, cross-contributor reuse and company-safe cross-project reuse have source-backed artifacts and named acceptance authority.
- **AC2: Given** the negative access/promotion/race matrix runs, **when** results are reviewed, **then** any cross-project, same-project restricted-source, revoked-access or publication-boundary failure blocks acceptance.
- **AC3: Given** all UX journeys and post-review UX18–24 additions, **when** keyboard/phone/desktop and live-update tests run, **then** required surfaces, graph/list, six-stage Focus, audit, token/knowledge counters and push return behave as specified.

**Tasks:**

- [ ] **OM-18.03-T1** Verify adopted A-1 client-driven validated-default/explicit-candidate behavior at knowledge-quality acceptance; verify adopted A-2 derivative withdrawal/lineage and A-4 disabled-mode behavior before live promotion, resolve A-6 before sample selection, and name permitted-use/maintainer authorities.
- [ ] **OM-18.03-T2** Capture SM-1–SM-5 plus SM-C1–SM-C4 with predeclared samples, failures/help/unknown coverage and source-verifiable acceptance artifacts.
- [ ] **OM-18.03-T3** Trace exact-version source-to-lesson-to-validation-to-publication-to-delivery/use lineage through archive/restore and withdrawal; exercise derivative chains, mode/version races, restricted ancestors, post-index revocation and recipient/aggregate leakage.
- [ ] **OM-18.03-T4** Run all named UX journeys and accessibility/device checks against separately packaged frontend/backend artifacts; reuse Testcontainers dependencies for synthetic integration cases, distinguish those from actual live proofs and obtain recorded owner acceptance.

<a id="om-18-04"></a>

### OM-18.04 — Package a reproducible internal and public-ready release

As a maintainer, I want to reproduce the pilot and prepare open-source distribution, so that adopters receive usable instructions without customer data or secrets.

**Requirements:** FR-20, AR-01, AR-04, AR-12, UX-DR59, UX-DR60

**Depends on:** OM-18.03

**Acceptance criteria:**

- **AC1: Given** a clean supported environment, **when** the installation and enrollment instructions are followed, **then** the documented internal pilot can be reproduced with secret-free configuration and clear limitations.
- **AC2: Given** public publication is proposed, **when** release readiness is reviewed, **then** the selected license and dependency compatibility are approved and private customer artifacts are absent.
- **AC3: Given** only the internal pilot is accepted, **when** release status is shown, **then** the plan does not imply a public release, publication authorization or SaaS monetization.

**Tasks:**

- [ ] **OM-18.04-T1** Produce versioned independent frontend/backend build/install/upgrade instructions with supported API version pairs, plus restore, native client enrollment, source connector and Testcontainers test runbooks with sanitized examples.
- [ ] **OM-18.04-T2** Complete dependency/license and distributable artifact review; obtain the owner license decision before public release.
- [ ] **OM-18.04-T3** Check that public artifacts exclude credentials, live screenshots, private telemetry and real source payloads.
- [ ] **OM-18.04-T4** Record internal acceptance and separate public-release checklist; do not publish, push releases or create external tickets in this planning work.
