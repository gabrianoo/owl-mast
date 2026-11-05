# Access and knowledge requirements review

Date: 2026-11-05. Scope: `prd.md` and `addendum.md`; access isolation, source permissions, knowledge delivery and publication, lifecycle, observation boundaries, and two-toolchain acceptance.

Latest steering acknowledged: automatic eligibility marking and promotion are desired, with manual approval and disabled modes. The saved draft was being updated from its earlier manual-only wording during review. That earlier wording is not raised as a finding here. This review does not require a human to approve every item.

Verdict: two actionable gaps in the stated data boundary and acceptance proof. Counts: 0 critical, 1 high, 1 medium, 0 low. Neither requires reopening the confirmed product scope or choosing an implementation stack.

## AK-1 — High: secret exclusion stops at selected output types

**Location:** FR-18, supported by NFR-6; relevant to capture, indexing and automatic promotion.

**Evidence:** FR-18 says secrets are excluded from “knowledge and visible telemetry,” then protects search snippets and generated summaries. NFR-6 covers diagnostic logs. Raw transcripts can be enabled under A-3, and retained source evidence is an explicit product concept, but these clauses never say whether secret-bearing raw payloads, retained evidence or derived indexes must be rejected/redacted before persistence.

**Failure case:** a connected source contains a credential in an otherwise authorized record. Owl Mast retains the raw record or embeds/indexes its content while hiding the credential in its normal UI. That implementation can satisfy the listed output checks while retaining sensitive content that a later extraction or promotion process can resurface. Automatic marking/promotion increases the importance of this boundary; it does not require disabling automation.

**Fix:** make secret exclusion apply before durable capture/indexing/publication of source payloads and their derivatives, including optional raw conversations. When a content check fails or is unavailable, the item must not become deliverable or promotable. Record safe failure metadata without storing the rejected content. Keep integration authentication material in the designated credential mechanism; this content rule should not accidentally prohibit necessary connector authentication.

**Acceptance:** use synthetic secret-bearing source content and prove it is absent from retained content, retrieval/index results, summaries, logs, and company publication. A failed scanner/check must leave the item unpublished, even in automatic mode. Do not use real secrets as test fixtures.

## AK-2 — Medium: the pilot's negative cases do not exercise shared-credential overreach within a project

**Location:** FR-17 and SM-5; addendum “Architecture validation work.”

**Evidence:** FR-17 correctly prohibits a shared connection from granting every viewer all its source access. Its enumerated tests cover cross-project access, an unauthorized third identity, and a revoked user. They do not require a currently enrolled project member who lacks access to one particular source record or repository. The addendum mentions restricted source records, but the PRD's pilot acceptance cases do not pin down this distinct failure mode.

**Failure case:** a valid Syntelligence member can retrieve a restricted Syntelligence source record through Owl Mast's broad integration credentials. Cross-project isolation and revoked-membership tests still pass. The declared boundary proof can therefore miss the principal shared-credential failure the PRD intends to prevent.

**Fix:** add a same-project restricted-source case to FR-17/SM-5, using a connection that can read the record and a recipient that cannot. Also verify a record-level source ACL change for a still-enrolled user. Exercise every relevant channel: search/preview, knowledge derived from the source, aggregate disclosure, and any export provided. A company-safe promoted derivative may be readable under its separately authorized publication policy; the original private evidence and its private metadata must remain inaccessible.

**Acceptance:** both toolchains demonstrate that project membership and connection access do not bypass source-record permissions. The intended company-wide derivative can be consumed without leaking the restricted original. Permission reconciliation and revocation timing may be designed later, but the required security outcome and negative case should be explicit now.

## Covered adequately or intentionally pending

- The two Jira accounts and GitHub/Bitbucket boundary are explicit; neither demonstration can substitute for the other. Actual editions/client event feasibility remain honestly disclosed follow-up work.
- Initial project administration and recurring enrollment are separately measured. Minimal recurring enrollment can coexist with complex initial setup.
- Source-qualified identities, unknown attribution, stale observations, and separate acceptance/merge/deployment facts are present.
- Agent launch, pause, cancel, retry, merge and deployment controls remain outside Owl Mast. Automatic knowledge promotion is a knowledge-publication policy and does not add agent execution authority.
- Versioned knowledge, scoped provenance, corrections, supersession, withdrawal, and limits on recalling previously delivered external context are present. Exact authority, client cache behavior, and retention rules are disclosed pending decisions, not additional findings.
- Mode-specific automatic/manual/disabled publication behavior must be reflected in the parent's in-progress update. Failed or uncertain eligibility checks should prevent publication without implying that every successful automatic case needs human approval.

## Final re-check — updated requirements, 2026-11-05

Freshly reread the saved PRD and addendum after the client/promotion update, with particular attention to FR-2, FR-9, FR-12–FR-13, FR-17–FR-18, FR-21, the assumptions index, and downstream handoff. The original findings above are preserved as the review snapshot; this section supersedes their unresolved status.

**Final verdict:** ready for UX and architecture with bounded assumptions. Remaining concrete defects in this review scope: **0 critical, 0 high, 0 medium**. This is a requirements readiness verdict, not verification of implemented access controls, integrations or automatic classification accuracy.

### Original findings resolved

- **AK-1 — Resolved.** FR-18 now excludes credential secrets from persisted observation payloads, knowledge, indexes, logs and generated summaries, and extends exclusion to snippets, caches, exports and derived summaries. Integration authentication remains in designated protected configuration. FR-12 requires publication checks for restricted content and secrets; failed or uncertain checks do not publish. The original hidden-persistence/output-only loophole is closed at the requirement level.
- **AK-2 — Resolved.** FR-17 explicitly adds the same-project user without permission to a restricted source record and permission removed after indexing. Shared-credential access does not override recipient authorization; unverifiable authorization fails closed. Revocation covers cached/indexed material and derived summaries. SM-5 now includes restricted-source cases. A separately permitted company-safe publication is distinguished from its inaccessible original, with independent withdrawal governed by FR-13.

### Changed behavior checked

- **Promotion modes:** FR-12 supports the preferred automatic mode, manual approval of an exact version, and disabled publication while project capture/delivery continue. The checks establish provenance, applicability, permitted use/audience, restricted-content and secret exclusion, and absence of unresolved contradiction/withdrawal. Failed or uncertain eligibility is visible and leaves content project-scoped. Automatic publication is not unconditional sharing and does not require human approval for every passing item.
- **Version and policy transitions:** each edited version receives an independent decision; the publishing actor, knowledge version, policy version, time and basis are recorded. Policy changes are permission-limited and audited. Switching out of automatic mode blocks pending automatic publication under the old mode. Re-enabling automatic mode evaluates candidates against the current policy. A-4 explicitly distinguishes stopping future publication from withdrawal of prior publications.
- **Withdrawal and delivery:** FR-13 covers quarantine/withdrawal, promoted derivatives, audit history, fresh evaluation before re-publication, and a current-eligibility check before new cached delivery. Inability to check eligibility withholds the item. Limits on recalling previously delivered external context are honest. A-2 supplies a bounded default and a pre-live-promotion revisit point.
- **Client scope and recurring effort:** FR-2 requires existing Claude and Codex clients in one workspace with authorized project selection, separately verifies observation and knowledge readiness, and avoids repeated source credential setup or manual context copying. A-5 labels the proposed enrollment-step ceiling. SM-2 exercises all four client/project combinations and returning sessions. Initial administrative complexity is not incorrectly treated as a recurring enrollment failure.
- **Notion continuity:** FR-21 distinguishes user-reported page creation from unverified skill reading, requires scope/version checks, preserves existing Notion use, and separates independent client permissions from Owl Mast-mediated delivery. It does not silently require a new memory store or a full Hermes client adapter. T3 Code remains an experience reference and does not introduce execution controls.

### Bounded downstream work

The remaining assumptions have named owners and validation conditions: guidance eligibility defaults, withdrawal behavior, optional raw-content handling, disabled-mode treatment of existing publications, enrollment effort, and pilot sample sizes. Actual Jira/Bitbucket variants, client contracts, processing/deployment destinations, numeric freshness/time budgets and component selection remain architecture/validation work. They do not weaken project isolation or permit live customer ingestion before the stated data-handling gate. UX and architecture can proceed; connector estimates and implementation readiness still require the documented feasibility work.
