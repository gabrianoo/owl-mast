# PRD reconciliation — Owl Mast architecture spine

Date: 2026-11-06. Scope: the initial complete AD-1–AD-16 draft, reconciled against the current PRD. This is a source-reconciliation pass before the architecture reviewer gate; no application/runtime validation was performed.

**Verdict: aligned in its major choices, with three targeted consistency fixes before handoff.** None needs a new product or technology decision. Detailed acceptance behavior can remain in the PRD and owned stories.

## Findings

### R-PRD-1 — Medium: preserve the pre-ingestion governance gate

- **Source:** PRD FR-18, line 225: retention, removal and derived-content propagation behavior must be documented and verified before live customer ingestion. PRD §9 repeats the pre-live boundary. Existing OM-02.05 AC1/T1 already blocks activation without content/destination/retention policy and resolves archive/other-record policy before ingestion.
- **Spine gap:** AD-10 ends with collection/destination permission gating; the Deferred OM-02.05 row names only rights/destinations. The OM-16.03 row gates other record-class/removal policy only before “Live retention/removal mechanisms.” Read on its own, this permits ingestion before the policy qualification required by the PRD and E02.
- **Fix:** retain OM-16.03 as the policy-definition owner, but make its relevant contract a prerequisite for OM-02.05's live-ingestion activation. State that applicable retention/removal/derivative-propagation policy must be qualified before live customer ingestion. This does not require implementing every later governance UI first or choosing an archive purge policy.

### R-PRD-2 — Medium: carry the cost categories across the ownership boundary

- **Source:** PRD FR-16, lines 203–205, distinguishes observed units, API-equivalent estimates, subscription allocation and actual bills; totals expose coverage and unpriced/unassigned portions, and estimates retain pricing basis/date.
- **Spine gap:** AD-13 preserves generic fact/inference/estimate/unknown and count denominators, but it does not preserve those four accounting categories or pricing identity. Usage producers and UI consumers can comply with the present rule while treating an estimated API-equivalent value as subscription cost or combining independently observed bills and estimates.
- **Fix:** add one concise AD-13 accounting clause separating the four categories, requiring pricing basis/date on estimates and preserving unpriced/unassigned coverage. Exact currency precision, schemas and attribution algorithms can stay with the owner stories.

### R-PRD-3 — Medium: make connector failure containment explicit

- **Source:** PRD FR-1, line 66, requires one failed/revoked connection not to make the other project unavailable. NFR-3, line 257, preserves access to other authorized data during a connection outage.
- **Spine gap:** bounded adapters, stale states and fail-closed access are present, but the boundary of a connection failure is not stated. A shared ingestion or authorization-health gate could block every project when one connector fails while obeying the current broad rules.
- **Fix:** add to the integration/access rule that connection-scoped failure, revocation or unverifiable source authorization affects that scope, while independently authorized data remains usable with honest freshness/coverage labels. It does not permit stale authorization fallback for the affected source or promise survival of an installation-wide database failure.

## Covered requirements and accepted deferrals

- AD-1 preserves observation-only V1, existing source ownership, Hermes→Notion continuity and authorized direct Claude/Codex Notion writes. The spine does not require a third full Hermes adapter or a replacement knowledge store.
- AD-3/4 preserve individual identities, shared source-account mappings, tenant/project/source/recipient boundaries, current permission and limits on revoking external copies. Personally owned enrollments do not falsely identify the initiator of every observed event.
- AD-7/9–12 preserve exact-version lineage, approved-default client-driven search/load, explicit candidate inclusion, full conversation capture, 30 active days followed by retained archive, company publication, adopted A-4 and derivative-aware withdrawal. Captured evidence is not automatically approved guidance.
- AD-8/13 preserve direct native observations, optional T3 enrichment, distinct delivery/load/application/reuse evidence, missing-coverage semantics and non-causal ROI interpretation.
- AD-6/15/16 preserve durable processing/audit, snapshot recovery boundaries and tests that cannot replace authorized live two-project proof.
- Browser/authentication, source editions, native credentials/capability coverage, numeric performance budgets, archive implementation, A-5/A-6 calibration and license selection remain owned, gated work. These deferrals do not silently remove mandatory scope.

## Source status hygiene

PRD §5, line 272, still says “no stack has been selected.” Replace that historical statement with a reference to the adopted architecture choices while retaining unresolved compatibility qualifications. This is a source-status correction, not a disagreement with the selected stack.

No files other than this report were changed by this reconciliation pass.
