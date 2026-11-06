---
id: SPEC-owl-mast
companions:
  - ../../planning-artifacts/prds/prd-owl-mast-2026-11-05/prd.md
  - ../../planning-artifacts/prds/prd-owl-mast-2026-11-05/addendum.md
  - ../../planning-artifacts/architecture/architecture-owl-mast-2026-11-05/ARCHITECTURE-SPINE.md
  - ../../planning-artifacts/architecture/architecture-owl-mast-2026-11-05/AGENT-INTEGRATION.md
  - ../../planning-artifacts/ux-designs/ux-owl-mast-2026-11-05/DESIGN.md
  - ../../planning-artifacts/ux-designs/ux-owl-mast-2026-11-05/EXPERIENCE.md
  - ../../planning-artifacts/epics.md
  - ../../planning-artifacts/epics/owl-mast-2026-11-05/epic-01.md
  - ../../planning-artifacts/epics/owl-mast-2026-11-05/epic-02.md
  - ../../planning-artifacts/epics/owl-mast-2026-11-05/epic-03.md
  - ../../planning-artifacts/epics/owl-mast-2026-11-05/epic-04.md
  - ../../planning-artifacts/epics/owl-mast-2026-11-05/epic-05.md
  - ../../planning-artifacts/epics/owl-mast-2026-11-05/epic-06.md
  - ../../planning-artifacts/epics/owl-mast-2026-11-05/epic-07.md
  - ../../planning-artifacts/epics/owl-mast-2026-11-05/epic-08.md
  - ../../planning-artifacts/epics/owl-mast-2026-11-05/epic-09.md
  - ../../planning-artifacts/epics/owl-mast-2026-11-05/epic-10.md
  - ../../planning-artifacts/epics/owl-mast-2026-11-05/epic-11.md
  - ../../planning-artifacts/epics/owl-mast-2026-11-05/epic-12.md
  - ../../planning-artifacts/epics/owl-mast-2026-11-05/epic-13.md
  - ../../planning-artifacts/epics/owl-mast-2026-11-05/epic-14.md
  - ../../planning-artifacts/epics/owl-mast-2026-11-05/epic-15.md
  - ../../planning-artifacts/epics/owl-mast-2026-11-05/epic-16.md
  - ../../planning-artifacts/epics/owl-mast-2026-11-05/epic-17.md
  - ../../planning-artifacts/epics/owl-mast-2026-11-05/epic-18.md
  - ../../planning-artifacts/epics/owl-mast-2026-11-05/epic-19.md
sources: []
---

# Owl Mast — implementation specification

This kernel and its adopted companions define the build contract. Read the companions for detailed acceptance criteria, architecture decisions and UX behavior; this summary does not replace them.

## Why

Contributors and leads need source-backed understanding of colleague and agent work, then useful authorized learning for the next contributor without a manual recap. Owl Mast connects observation to reuse while preserving existing execution, tracker, repository and Notion/Hermes authorities.

## Capabilities

- **CAP-1 — Operate reproducibly**
  - **intent:** Operators can build, install, inspect and recover Owl Mast in its supported environment.
  - **success:** E01/E18 demonstrate clean reproduction, independent web/backend artifacts, durable work/audit and qualified recovery with stated loss limits.

- **CAP-2 — Connect people and clients safely**
  - **intent:** Contributors can use personal identities and reusable client enrollments in their authorized projects.
  - **success:** E02/E05 prove separate observation/delivery readiness, shared-account identity separation and current-access denial across both projects and a second synthetic tenant.

- **CAP-3 — Observe both work environments**
  - **intent:** Teams can collect source-backed work and native Claude/Codex activity from executing machines.
  - **success:** E06–E09 qualify both Jira sites, GitHub/Bitbucket and both clients standalone/T3-hosted, including replay, isolated failure and explicit per-field coverage; E17 adds optional read-only context.

- **CAP-4 — Preserve and retrieve useful knowledge**
  - **intent:** Contributors and agents can retain versioned project learning and explicitly discover and load applicable knowledge.
  - **success:** E03/E04 preserve Notion/Hermes authority and complete skill packages, enforce validated-default selected-version delivery with explicit candidate opt-in, and prove revocation without unsolicited context injection.

- **CAP-5 — Publish and withdraw permitted learning**
  - **intent:** Maintainers can publish evaluated company-safe versions and stop future managed delivery of withdrawn guidance.
  - **success:** E11 proves automatic/manual/disabled publication, exact-version race guards, tenant-local audiences and transitive derivative withdrawal with restricted lineage history.

- **CAP-6 — Understand work from evidence**
  - **intent:** Contributors and leads can inspect progress, individual runs, contributions and dependencies through Daily Work and separate assigned-work Focus views.
  - **success:** E10/E13 provide the eleven-surface UX contract where applicable, six observed SDLC stages, graph/list parity, source-qualified run fields and distinct closure/check/acceptance/deployment facts across accessible device layouts.

- **CAP-7 — Explain usage and useful reuse**
  - **intent:** Reviewers can inspect attributable consumption and evidence of knowledge delivery, loading, use and verified reuse.
  - **success:** E12/E14 retain independent event types, exact versions, human-verified task evidence, deduplicated usage and separate estimates/allocations/bills with unknown and unassigned coverage.

- **CAP-8 — Receive eligible updates**
  - **intent:** Users can receive distinct observed work updates and return to current authorized evidence.
  - **success:** E15 qualifies target-device push, explicit preferences, replay deduplication, current send/open authorization and accessible return without silently replacing updates with a digest.

- **CAP-9 — Govern retained evidence**
  - **intent:** Authorized operators can inspect full-system audit and apply collection, archive, removal and recovery policy.
  - **success:** E16 preserves exact-version lineage through 30-active-day conversation archiving and verifies current permissions, secret exclusion, governed cleanup and the single recovery-quarantine release authority.

## Constraints

- Preserve the adopted AD-1 through AD-16, requirement IDs and all 19 epics, 85 stories and 340 tasks with their existing OM IDs, acceptance criteria and prerequisite direction; E17 remains optional and E19 later evolution, neither a required V1 acceptance gate.
- Architecture, ownership, stack and verification follow the adopted spine: Java 27/Spring Boot 4.1.2, one modular reactive backend, independent frontend, PostgreSQL/VectorChord, Keycloak, Kubernetes and qualified Testcontainers; unselected tool/provider/browser/native credential pins remain qualification work.
- Tenant/project/source/purpose and recipient permissions govern all current and historical disclosure and effects; secrets never enter payloads, derived indexes or diagnostics. Missing authority fails closed and invalidation overrides ordinary buffered/offline UI behavior.
- Exact-version provenance, typed lineage and explicit unknown/partial coverage govern every projection; delivery, native loading, observed application and human-verified reuse remain distinct, as do closure, acceptance and deployment.
- Adopted A-1/A-2/A-4 and A-3 capture/archive defaults remain settled: client-led validated-default retrieval, derivative withdrawal, disabled promotion preserving existing eligible publications, full capture with overrides and 30 active days then retained archive without automatic purge or project-knowledge expiry.
- All owning-story gates in the spine Deferred table and epics decision/qualification gates remain binding. Only designated contract-design/qualification portions may run early using documentation/synthetic fixtures; production implementation, live actions and completion retain original prerequisites.
- DESIGN.md and EXPERIENCE.md retain exact accepted assets/tokens, accessibility and all S1–S11/J/SC behaviors with their original adopted/delegated/proposed labels; inherited A-5/A-6 and bounded UX choices remain unconfirmed at their stated checkpoints.
- GitHub Issues/Projects own engineering progress and prioritization; repository documents define the contract and Git history records revisions. Preserve necessary BMAD automation state; GitHub-backed loop execution or synchronization is not qualified merely by changing tracking settings.
- Withdrawal prevents future ordinary retrieval and Owl Mast-managed delivery, materialization and refresh; it cannot recall previously delivered external context or prevent independent native use of retained copies without separately qualified enforcement (AD-12).

## Non-goals

- Agent execution, routing, shell, merge or deployment controls; replacing existing trackers, coding harnesses or the Notion/Hermes source workflow.
- Universal connectors, sandbox hosting, monetization, predictive budget allocation, causal ROI or individual productivity claims.
- E19 multi-tenant rollout, OpenFGA, multi-pod availability or measured component extraction as initial-pilot requirements; these remain planned later work under the existing gates.

## Success signal

The owner accepts live authorized SC-1/SC-2/SC-3 demonstrations across Syntelligence and Movesion with Claude and Codex, supported standalone/T3-hosted runtime evidence, verified useful reuse, SM-1–SM-5 and SM-C1–SM-C4 measurements, and every required isolation/publication negative case passing. Samples, budgets and acceptance authority are agreed before the run; fixtures cannot replace live proof, and internal acceptance is separate from public release.

## Open Questions

The inherited questions retain their existing owners and checkpoints in the [spine’s Deferred table](../../planning-artifacts/architecture/architecture-owl-mast-2026-11-05/ARCHITECTURE-SPINE.md#deferred) and [epic qualification gates](../../planning-artifacts/epics.md#decision-and-qualification-gates). Which qualified choices and evidence satisfy each gate must be recorded before its consumer proceeds; no new feature-discovery round is required. A-5/A-6 and bounded UX proposals remain unconfirmed. Earlier upstream “not selected” statements are superseded only where the finalized AD decisions explicitly adopt that choice.
