# Architecture adversarial gate — Owl Mast V1

Date: 2026-11-06

Verdict: **Pass after one ownership clarification.** No new product decision, technology selection or deployment permission is needed. No critical or high finding was established. The remaining medium finding concerns two implementation owners for one recovery control contract.

Reviewed the [spine](../ARCHITECTURE-SPINE.md), [integration companion](../AGENT-INTEGRATION.md), [shared story rules](../../../epics.md), and the relevant E02/E03/E06/E07/E08/E11/E12/E16/E18/E19 stories after source reconciliation. This is an adversarial consistency review, not runtime qualification or verification of current technology versions.

## R1 — One recovery control contract needs one implementation owner

**Severity:** medium. **Disposition:** clarify ownership before handoff; no user choice required.

**Locations:** spine AD-15 and Deferred recovery/retention rows; [OM-16.05](../../../epics/owl-mast-2026-11-05/epic-16.md#om-16-05), especially T2/T3; [OM-18.02](../../../epics/owl-mast-2026-11-05/epic-18.md#om-18-02), especially T1/T2; [OM-16.03](../../../epics/owl-mast-2026-11-05/epic-16.md#om-16-03).

The spine correctly requires restored disclosure and external dispatch to remain quarantined until current authority, eligibility and effect outcomes reconcile. However, the Deferred table names OM-18.02 as the recovery owner, OM-16.05-T2 also implements recovery readiness gates, and OM-18.02-T2 again implements the quarantine/reconciliation gate. Backup retention is assigned both to OM-16.03's governance policy and OM-18.02's operational selection without stating their precedence.

**Two individually compliant units:**

- Governance implements a tenant-scoped recovery generation and release operation after permission/lifecycle reconciliation. It fails closed until that operation succeeds.
- Operations implements a separate process-level recovery flag and release operation after storage and external-effect reconciliation. It also fails closed, but expects a different readiness interface and scope.

Both respect AD-15's safety outcome and own only their records. They still deliver incompatible release authorities: API, job and dispatch consumers cannot identify which readiness contract to use or how the two releases compose. Keeping both closed avoids disclosure but can leave recovery unable to finish. Independent backup-retention choices create the same ownership ambiguity between policy and mechanism.

**Small fix:** assign Governance/OM-16.05 the single recovery-quarantine and reconciliation contract covering disclosure and external dispatch, with its required inputs from Access, Knowledge, data owners and effect owners. Consumers use that contract; Operations/OM-18.02 implements the storage runbook and exercises the existing contract instead of creating another gate. OM-16.03 owns approved retention policy; OM-18.02 selects compatible operational cadence/targets and verifies the approved retention settings. Add OM-16.05's contract to Deferred if it must be designed before its implementation prerequisites are complete. Keep all original safety and recovery acceptance cases.

## Adversarial pairs tested without a surviving finding

| Pair | Why the current contract closes the divergence |
| --- | --- |
| A feature mutation producer and the job/audit infrastructure | AD-5/AD-6 require one atomic database boundary for business state, required work and audit intent; OM-01.03 owns the transaction and envelope contract before producers implement it. External effects are explicitly outside assumed database atomicity. |
| Knowledge lifecycle and retrieval/index implementation | The reconciled ownership table makes Knowledge authoritative for versions, eligibility, MCP contracts and delivery receipts. Retrieval owns rebuildable indexes/query implementation. AD-9/AD-12 require current eligibility even while derived cleanup is pending. |
| Ingestion and work/reuse evidence | Observation-envelope ownership is separated from canonical work/run correlation and native-use/reuse assertions. OM-06.03 and OM-10.01 publish their respective contracts; source receipts are not delivery receipts or useful-reuse evidence. |
| MCP implementation and native enrollment | The bounded design-only prerequisite exception permits the credential contract to be agreed before MCP consumers implement it, without pretending enrollment production work or its whole epic is complete. |
| Publication and withdrawal workers | Exact content/policy/audience checks, commit-time disabled-mode checks, transitive derivation/publication invalidation and immediate delivery guards close stale-publication and eventual-cache-cleanup gaps. Usage links alone cannot propagate withdrawal. |
| Archive writer and content reader | The shared blob contract, stable identities, verified durable readback and locator publication rule prevent independent storage-location identities or release of the only readable copy before archive completion. |
| Tenant-scoped native ingestion and shared source-account import | Trusted enrollment scope, separate personal/external identities, explicit unknown attribution and synthetic second-tenant tests prevent payload claims or a shared customer account from becoming authority. |
| UI updates, notifications and knowledge loads | Permissions override buffered UI refresh; offline disclosure is constrained; notification scope differs from assigned-work Focus; work-update push cannot trigger unsolicited full lesson injection. |

Exact schemas and providers remain legitimate deferred decisions because they have named owners and consumer gates. This review does not require fixing every endpoint, database column, provider or deployment version in the spine.
