# Epic and integration reconciliation — 2026-11-06

Verdict: the spine preserves the full planned product and the adopted policies. Fix two contract/sequence inconsistencies before handoff; no additional product choice or service is required.

Scope: `ARCHITECTURE-SPINE.md`, `AGENT-INTEGRATION.md`, the epic index and the relevant E01–E06/E10/E12/E18 contracts. This is a document reconciliation, not runtime qualification or a complete task re-review. The existing 19-epic/85-story/340-task scope is unchanged.

## P1 — High: qualification pull-forward conflicts with the task prerequisites

**Evidence:** the spine's Deferred preamble (line 203) allows a decision/qualification task to run before its owner's whole epic. The epic index (line 315) says *all* tasks inherit their story prerequisites, with no qualification exception. E05 requires E04, and OM-05.02 requires OM-05.01. However, the spine assigns the native credential/delegation contract to OM-05.02 while OM-04.03 already qualifies and implements MCP OAuth/token lifecycle and grants. Thus an implementer following the epic order must either choose part of that contract before its named owner is allowed to work or wait on a prerequisite cycle. The same general issue affects early consumers of later schema/retention/recovery qualification.

**Fix:** reconcile the index and relevant tasks with the spine. Explicitly distinguish non-implementing contract/qualification work that may be pulled forward from the implementation tasks that retain their listed dependencies. Name the precise contract tasks and required outputs before the first consumer; preserve the existing story IDs and do not imply an entire later feature is complete. Alternatively, move the common credential-contract decision to an earlier owner and have enrollment consume it. No credential mechanism needs to be selected in this review.

## P2 — Medium: the ownership map and deferred contract owners are not fully reconciled

**Evidence:** the Deferred row at line 220 gives OM-06.03 ownership of canonical observation/**correlation** schemas, while OM-10.01-T1 explicitly defines source-qualified work/run/contribution identifiers and typed correlation/assertion contracts. `AGENT-INTEGRATION.md` also assigns normalized runs/segments and work/contribution relationships to Evidence, whereas the spine groups normalization under Ingestion without spelling out the transfer. In addition, its MCP boundary says the Knowledge module exposes search/read/package retrieval, while the spine says Retrieval owns scoped search/load. These may be intended facades, but the current documents do not identify which is the authoritative operation/schema owner and which is an adapter/projection.

**Failure mode:** independently built ingestion and evidence features can each create a canonical run/correlation representation; independently built knowledge and retrieval features can each publish the knowledge wire contract. Both can cite a planning document and claim owner-only writes under AD-2.

**Fix:** name the boundary once: Ingestion owns accepted source observations/receipts and normalization; Evidence owns canonical work/run/correlation assertions and consumes normalized observations; Knowledge owns item/version/lifecycle/publication and authoritative eligibility; Retrieval owns derived indexes and query/load orchestration against Knowledge's owner API (or choose an equally explicit facade split). Assign observation-envelope qualification to OM-06.03 and correlation/reference-contract qualification to OM-10.01, with any needed early contract work governed by P1. Reconcile the MCP row in the integration companion. Make clear which owner records delivery/use evidence and which modules only project it. This needs a short owner table/contract sentence, not complete database or API schemas.

## Preserved constraints

- One modular backend, separate frontend deployment, Kubernetes, optional bundled PostgreSQL/VectorChord and Keycloak, and a single real tenant with isolated projects remain consistent with the plan.
- Native Claude/Codex support remains complete for standalone and T3-hosted operation; T3 is optional enrichment, not a gateway. MCP, semantic observations and inbound OTLP remain distinct interfaces.
- Adopted A-1/A-2/A-4, full capture with 30 active days followed by retained archive, individual enrollment ownership and first-class lineage all landed.
- Atomic successful-mutation audit/work durability, current-permission enforcement, external-copy limits and recovery quarantine are preserved.
- Undecided frontend/auth/provider/image/recovery details remain visible qualifications rather than accidental selections. Existing endpoint spellings stay proposals.
- Known stale "coaching seed"/draft handoff text is already assigned to the parent for final status reconciliation and is not counted as another finding here.

No source or implementation file was modified by this review.
