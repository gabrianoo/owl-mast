# Owl Mast architecture handoff

Use this prompt in a fresh context. This is a handoff, not an architecture decision or approval of a technology stack.

```text
$bmad-architecture

Create Owl Mast's architecture from the finalized PRD and UX package. Guide me through unresolved architecture decisions and tradeoffs; preserve confirmed product and UX choices. Do not start implementation or generate epics/stories in this session.

Read my Agent Operating Guide:
https://app.notion.com/p/4078ce65708081988dbfe2d980c7fe86
Consult and update the existing project context:
https://app.notion.com/p/40e8ce657080814ca0fdf40e67a36e8b

Read these local inputs:
- _bmad-output/planning-artifacts/prds/prd-owl-mast-2026-11-05/: prd.md, addendum.md, .memlog.md, review-disposition.md.
- _bmad-output/planning-artifacts/ux-designs/ux-owl-mast-2026-11-05/: DESIGN.md, EXPERIENCE.md, .memlog.md, review-disposition.md, validation-report.md, and the relevant mockups and reconciliation notes.
- Consult the existing brief and competitive research when needed. The UX spines govern over mockups. UX-18–24 are later user-confirmed amendments; the earlier independent review predates them. Reconcile explicit scope deltas with the PRD and identify unresolved conflicts rather than silently dropping additions.

Preserve these constraints:
- Open source, AISQUAD first. V1 observes work and delivers knowledge; direct agent execution, assignment and machine routing stay outside V1.
- Syntelligence uses Jira + GitHub; Movesion uses a separate Jira + Bitbucket. Both support Claude and Codex. Preserve project, source, recipient and telemetry permissions throughout.
- Dedicated responsive UI on laptop/tablet/phone. Push defaults to every observed work update under the UX event definition. Daily Work and assigned-to-me Focus are distinct.
- Central knowledge supports on-demand agent search. Preserve existing Notion and Hermes-to-Notion workflows; current Notion skill reading is unverified.
- Knowledge defaults to project scope; prefer automatic company-safe promotion, with manual-approval and disabled modes and project-designated maintainers.
- Initial administrator setup may be complex; recurring contributor/agent onboarding must require minimal effort and expose configured versus observed machine/sandbox context.
- Observe task roles, agent/client identities, model, exact effort, session, machine, token IN/OUT and defensible ticket/epic attribution. Keep observed usage, API-equivalent estimates, subscription allocation and actual bills distinct.
- Separate skill/memory loads, observed application and verified useful reuse. Missing telemetry is Unavailable, not zero.
- Target audit history for everything Owl Mast creates. Knowledge/Skills may be a proposed first slice if effort warrants it; do not silently reduce the target.
- Focus has six nonlinear stages: Plan, Design, Build, Test, Deploy, Maintain. Preserve tracker status and measurable acceptance progress separately; keep unmapped work visible.
- Provide a permission-preserving ticket/PR dependency graph and equivalent list. Neo4j is an option to evaluate, not a selected requirement.

Keep PRD assumptions A-1–A-6 distinct from confirmed requirements and resolve or defer them at their stated checkpoints. Limited source connection reads and static mockups are not proof of product integration, permissions, agent telemetry or knowledge delivery.

Work through application/deployment boundaries, source and agent adapters, identity/access, knowledge lifecycle, event collection and deduplication, usage attribution, audit coverage/retention, notification delivery, and relationship queries. Compare realistic options before binding major choices and verify current technology versions/fit. Record architecture decisions and deferred items in ARCHITECTURE-SPINE.md and the architecture decision log; save durable decisions in the existing Notion project record. Follow the architecture skill's activation and review workflow.
```

The repository gallery contains sanitized illustrative references. The self-contained Downloads review additionally contains private source snapshots and remains local; do not copy its live source data into the repository or infer missing telemetry from it.
