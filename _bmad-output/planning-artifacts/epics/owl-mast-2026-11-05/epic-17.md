---
epic: E17
status: planned
review_status: pending-owner-review
implementation_status: not-started
---

# Epic E17 — Enrich native observations with optional T3 context

T3 users add permitted thread, delegation and workstation context through an optional read-only adapter. Native Claude/Codex integration sends directly from the executing machine and remains functional without this adapter. Installing T3 enrichment grants no agent, shell, merge or deployment authority to Owl Mast.

**Epic prerequisites:** E06, E10

<a id="om-17-01"></a>

### OM-17.01 — Qualify a minimal read-only T3 connection

As a T3 user, I want an optional connection with explicit capabilities and scopes, so that I can add context without moving native telemetry through T3.

**Requirements:** FR-3, FR-4, FR-17, FR-18, FR-19; NFR-1, NFR-2, NFR-6; AR-07, AR-14, AR-16, AR-17, AR-18, AR-19; UX-DR22, UX-DR33, UX-DR54

**Depends on:** E06, E10

**Acceptance criteria:**

- Given the installed T3 version and supported interfaces, when qualification runs, then stable thread/run identity, available work/delegation/location fields, pagination/history, permissions and read-only authentication are recorded from actual evidence rather than inferred from another version.
- Given proposed read access, when credentials and tools are configured, then only the qualified read-only surface is available; thread launch, prompts, shell, approval, worktree mutation, merge and deployment actions are excluded.
- Given activity APIs may include conversation content, when A-3's remaining archive/other-record-policy and destination rules or source permission is unresolved, then live collection remains gated and the adapter requests only permitted fields where possible; excluded content is never persisted or logged merely to extract metadata.
- Given T3 is absent, unreachable, unsupported or revoked, when a user works with Claude/Codex, then native MCP/hooks/OTLP remain independent and their readiness is unchanged by optional enrichment failure.

**Tasks:**

- [ ] **OM-17.01-T1** Qualify the actual T3 version/interface and record a capability/permission contract including unsupported native usage and exact-effort fields.
- [ ] **OM-17.01-T2** Implement enrollment-bound read-only connection configuration with protected credentials and no execution-capable port methods.
- [ ] **OM-17.01-T3** Apply A-3 and source-authorization gates to requested/received fields and verify safe handling of conversation-bearing responses.
- [ ] **OM-17.01-T4** Verify absent/revoked/unreachable T3 leaves direct native reporting and knowledge delivery operational.

<a id="om-17-02"></a>

### OM-17.02 — Reconcile T3 context with existing native evidence

As an authorized viewer, I want T3 context linked to the correct native work, so that it enriches the evidence chain without duplicating runs or consumption.

**Requirements:** FR-4, FR-5, FR-16, FR-17, FR-19; NFR-1, NFR-2, NFR-3; AR-07, AR-14, AR-16, AR-17, AR-18; UX-DR30, UX-DR41, UX-DR46, UX-DR47, UX-DR54

**Depends on:** OM-17.01

**Acceptance criteria:**

- Given source-supported native session/run references, when T3 context is matched, then typed links preserve the T3 and native namespaces, provenance, matching basis and times; ambiguous or unlinked records remain inspectable without a guessed merge.
- Given thread/delegation/workstation context, when normalized, then it adds only supplied evidence and distinguishes configured location from time-qualified observed execution; a workstation name or sandbox label does not prove live execution or security isolation.
- Given the same activity or usage appears in native and T3 observations, when reconciliation completes, then the evidence is linked without a second counted run/token/use event; missing stable matching information creates an explicit overlap issue rather than adding both totals.
- Given a title, status or provider default suggests an effort, initiator or acceptance result, when supported fields are absent, then those values remain unknown; upstream diagnostics are not promoted into unsupported business claims.
- Given a linked record is restricted or corrected, when the relation is queried, then current source authorization and correction history apply without leaking hidden nodes, titles, counts or edge stubs.

**Tasks:**

- [ ] **OM-17.02-T1** Implement bounded read collection and source-qualified context normalization through E06/E10 interfaces.
- [ ] **OM-17.02-T2** Implement evidence-based identity matching and typed enrichment links with explicit ambiguous/unlinked states.
- [ ] **OM-17.02-T3** Integrate overlap detection with the shared accounting/evidence contract rather than creating a separate T3 usage total.
- [ ] **OM-17.02-T4** Verify ID collisions, shared threads, conflicting context, duplicate native/T3 evidence, missing effort and revoked linked records.

<a id="om-17-03"></a>

### OM-17.03 — Inspect and recover optional enrichment independently

As an authorized operator, I want separate T3 health and safe recovery, so that optional context failures do not misrepresent native agent activity.

**Requirements:** FR-3, FR-4, FR-5, FR-17, FR-19; NFR-1, NFR-2, NFR-3, NFR-4, NFR-6; AR-11, AR-14, AR-17, AR-18, AR-19; UX-DR22, UX-DR26, UX-DR30, UX-DR33, UX-DR46, UX-DR54

**Depends on:** OM-17.02

**Acceptance criteria:**

- Given an optional T3 connection, when its health is inspected, then configured capability, last successful collection, failure/staleness, source/recorded time and affected context are shown independently from native observation and knowledge-delivery readiness.
- Given an outage, replay, reordered records or an interrupted checkpoint, when collection resumes, then durable bounded reconciliation recovers supported permitted context without multiplying linked runs or inventing unavailable historical data.
- Given disconnect or credential revocation, when the adapter stops, then no new T3 reads occur and historical context follows current permissions/retention; native clients continue directly and the UI never offers an execution-control substitute.
- Given a protected or unsupported field, when a user drills into enrichment, then missing/denied/stale states are clear and safe, including on keyboard/phone paths, without revealing hidden counts or source text.

**Tasks:**

- [ ] **OM-17.03-T1** Add independent connection-health and evidence-detail integration with supported-field coverage and safe remediation.
- [ ] **OM-17.03-T2** Implement qualified checkpoint/reconciliation and scoped durable retry behavior using the existing PostgreSQL job boundary.
- [ ] **OM-17.03-T3** Verify outage/replay/revocation behavior with native paths still active, including cross-project denial and protected historical context.
- [ ] **OM-17.03-T4** Document optional setup/repair/removal effects, current installed-version qualification and unresolved capability gaps without requiring T3 for native operation.

## Qualification and source notes

This optional epic is planned now; it is not a prerequisite for E07/E08 or native telemetry. Owner review, actual interface qualification and A-3's remaining archive/other-record-policy and environment-permission/destination prerequisites remain pending; the full-conversation default is adopted. Upstream source inspection is a research seed, not proof of installed runtime behavior.

- [T3 outside-agent documentation](https://github.com/pingdotgg/t3code/blob/main/docs/user/outside-agents.md) is the starting point for read-only access qualification.
- [Inspected T3 contracts](https://github.com/pingdotgg/t3code/blob/25b53299b75d4d8d1d0667ad47e9cfed3749776e/packages/contracts/src/orchestratorMcp.ts) anchor the research snapshot; do not generalize its field coverage to every release.
- [T3 Claude provider documentation](https://github.com/pingdotgg/t3code/blob/main/docs/user/providers-claude.md) and [telemetry documentation](https://github.com/pingdotgg/t3code/blob/main/docs/user/telemetry.md) do not establish complete native hook/configuration propagation or business-token coverage without qualification.
