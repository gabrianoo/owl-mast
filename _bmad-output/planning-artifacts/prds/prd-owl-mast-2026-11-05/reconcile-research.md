# Input reconciliation — existing Owl Mast research

Date: 2026-11-05. Reviewed draft artifacts while setup/delivery and promotion answers remain pending. This is reconciliation, not component selection or user approval.

**Inputs:** [competitive research](../../research/competitive-owl-mast-dashboard-references-2026-11-05/research.md), [research brief](../../research/competitive-owl-mast-dashboard-references-2026-11-05/brief.md), [research memory](../../research/competitive-owl-mast-dashboard-references-2026-11-05/.memlog.md), and [brainstorming memory](../../../brainstorming/brainstorm-owl-mast-2026-11-05/.memlog.md). Official sources narrowly rechecked during PRD discovery are linked in the PRD addendum; no new broad research was performed for this reconciliation.

**Compared with:** [PRD](prd.md) and [PRD addendum](addendum.md), all sections.

**Verdict:** No material research-reconciliation gap. Requirements preserve the relevant concerns while correctly treating research recommendations as proposals and superseding obsolete scope.

## Coverage and evidence boundaries

- Research lines 24 and 28–36 distinguish publisher evidence and analyst recommendations from tested results or approved scope. PRD §0 and the addendum's evidence hierarchy preserve this distinction. Neither claims unique market position, verified interoperability, proven savings or selected architecture.
- Research lines 32–35 and 48–54 separate activity, consumption, delivery and outcome, and API-equivalent estimates from billing. FR-5–FR-7, FR-16, NFR-2 and success counter-metrics retain these boundaries, coverage gaps, unknown attribution and pricing provenance.
- Research lines 66 and 110–112 highlight shared-credential risks, knowledge isolation and promotion. FR-8–FR-14, FR-17 and NFR-1 retain source access, lifecycle, both-project negative tests, restricted provenance and observed reuse. They do not adopt a vendor's authorization model as sufficient.
- Research lines 88 and 114–118 caution against a competing task board and call for evidence-based evaluation. PRD §§1, 3.2 and 5 keep existing trackers authoritative and require both real toolchain demonstrations. An unsupported connector is not treated as working merely because a product advertises an API.
- Research lines 98–112 contain memory-helper mechanisms and licensing distinctions. The addendum retains the unselected candidates, source ownership, current Hermes/Notion continuity and license/portability evaluation. Full vendor details remain available by link; omitting them from the PRD is appropriate condensation.
- Brainstorming suggestions for one-project/GitHub-only proof, strict merge enforcement and budget control are correctly superseded by current user decisions. Setup effort, stale/conflicting knowledge, unreliable attribution and maintenance costs remain visible as measurements or counter-metrics.

## Downstream detail to retain during implementation intake

Research lines 54 and 120–128 warn that T3 inbound automation webhooks do not establish an outbound telemetry/export contract; connector/export schemas and retention require testing. The draft's capability-verification requirements cover this generally. If T3, Ponytail, PAPI or another researched candidate is selected, carry that specific API-direction/contract check into the architecture evaluation. This is conditional follow-up, not an additional mandatory v1 integration or a blocker to PRD drafting.

No PRD or addendum edits were made by this reconciliation.
