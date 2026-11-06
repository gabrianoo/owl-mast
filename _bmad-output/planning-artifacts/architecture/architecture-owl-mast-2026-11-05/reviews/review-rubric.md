# Architecture spine rubric review

Date: 2026-11-06

**Verdict: pass after two bounded clarity fixes.** No critical/high finding or new load-bearing product choice. The spine is appropriate for initiative-level contract and qualification work; it does not certify live integration or deployment readiness. Mechanical lint was reported passed before this independent semantic review.

## Findings

### R-RUB-1 — Make the tenant publication boundary explicit (medium; autofix)

**Where:** AD-3 and AD-11.

AD-3 requires trusted tenant/project context and a synthetic second tenant; AD-11 defines an audience-bound company publication, but neither expressly says its origin, publication owner and company audience remain inside one tenant. Generic current-authorization checks alone do not define that product boundary: a future builder could implement a globally addressable company library with policy-controlled cross-tenant recipients while another implements a tenant-local publication scope.

The existing plan already requires cross-tenant collision/disclosure prevention in OM-02.02 AC2. Tighten the spine using that settled boundary: knowledge/publication ownership and the company publication audience are tenant-scoped; project-to-company promotion never crosses tenants. Explicitly preserve independent single-tenant self-hosting. No new sharing feature or tenancy choice is requested.

**Acceptance:** a publication from tenant A cannot be promoted or addressed as ordinary company knowledge in tenant B, even if project/resource keys collide; authorized cross-project publication within A remains supported.

### R-RUB-2 — Give backup retention one policy authority (medium; autofix)

**Where:** Deferred rows owned by OM-16.03 and OM-18.02.

The table promises one decision owner per shared choice, yet OM-16.03 owns other record-class/**backup retention** policy while OM-18.02 separately owns snapshot/backup **cadence/retention**. This permits governance and operator work to choose incompatible retention values, particularly when online removal and retained recovery copies differ. The source plan similarly separates governed policy (OM-16.03/16.05) from operator recovery qualification (OM-18.02), so the seam needs an explicit consumer relation.

Keep governance/OM-16.03 as the owner of record/backup retention and authorized-removal policy. Make OM-18.02 select/qualify snapshot support, consistency, failure coverage, cadence and RPO/RTO while consuming and verifying that approved retention policy; report a mismatch rather than override it. An alternative single owner is acceptable, but the same value must not be independently decided twice.

**Acceptance:** the recovery runbook references the approved policy version; restore/expiry qualification detects a storage configuration that violates it.

## Good-spine checklist

| Dimension | Assessment |
| --- | --- |
| Named paradigm and dependency direction | Pass. Modular monolith with ports/adapters, feature ownership, acyclic module dependencies and public contracts constrain independently built capabilities. |
| Real divergence points | Pass after R-RUB-1/2. Identity, access, source authority, exact versions, lineage, retrieval/capture/publication/withdrawal, native collection, evidence/cost and notifications are explicit. |
| Enforceable Rules | Pass. Rules identify mutation/disclosure/effect boundaries and observable negative cases. No exactly-once external-effect, external-copy recall or two-pod HA claim is made. |
| Deferred decisions | Pass after R-RUB-2. Named story owners and consumer gates keep unknown frontend/auth/provider/credential/protocol choices from being selected independently. The explicit design-only prerequisite exception allows early shared-contract work without waiving production implementation dependencies. |
| Operational/environmental envelope | Pass. Kubernetes topology, separate artifacts, optional bundled/external dependencies, self-hosting, synthetic CI, persistence, recovery, failure domains and later scaling are decided or gated. |
| Source capability breadth | Pass. PRD/UX remain binding detailed sources; the capability map covers E01–E19 including optional T3 and later evolution. Prior source-reconciliation fixes are present. |
| Existing code and parent invariants | Not applicable as brownfield ratification: no application implementation or parent spine is claimed. Historical proposals remain distinguishable from adopted decisions. |
| Current technology evidence | Dedicated research reviewer owns this check. This review does not independently assert current version availability. The spine limits Stack pins to the user's Java/Spring choices and gates other versions/fit before their consumers. |
| Size/altitude | Pass. Sixteen ADs and a substantial Deferred table are justified by the broad initiative; it avoids full entity schemas, endpoint inventories and duplicated UX design. |

## Limits

Read the current spine, reviewer-gate checklist and relevant epic identity/governance/recovery constraints. No application, integration, Kubernetes or recovery tests were executed. This review does not imply owner approval of the separate epic planning draft or authorization for live operations. Only this review file was written.
