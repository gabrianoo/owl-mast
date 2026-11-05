---
title: Owl Mast Product Requirements Document
status: final
created: 2026-11-05
updated: 2026-11-05
---

# Owl Mast Product Requirements Document

## 0. Purpose and decision status

The confirmed boundaries are open source, AISQUAD as first customer, observation and knowledge delivery for Syntelligence (Jira/GitHub) and Movesion (separate Jira/Bitbucket), project-default knowledge, and minimal recurring onboarding. Claude and Codex are required initially; T3 Code's existing two-agent setup is the experience reference. Initial administrator setup may be complex. The preferred promotion mode is automatic, with manual approval and disabled modes available. Each promotion is an explicit, recorded publication under the selected policy; project knowledge is never globally shared just because it was captured.

Older proposals for execution controls, a single-project pilot, or mandatory manual promotion are superseded. Detailed requirements translate the confirmed direction into observable behavior; tagged proposals remain subject to confirmation. Implementation choices and research depth belong in [addendum.md](addendum.md).

This PRD defines Owl Mast v1 for AISQUAD and supplies requirements for UX, architecture, and story creation. It builds on the [product brief](../../briefs/brief-owl-mast-2026-11-05/brief.md), its [addendum](../../briefs/brief-owl-mast-2026-11-05/addendum.md) and [decision log](../../briefs/brief-owl-mast-2026-11-05/.memlog.md), the [existing research](../../research/competitive-owl-mast-dashboard-references-2026-11-05/research.md), and the [Notion concept record](https://app.notion.com/p/40e8ce657080814ca0fdf40e67a36e8b).

## 1. Product vision and users

Owl Mast helps AISQUAD understand work performed by people and agents, and make useful project learning available to the next person or agent. Today, Mohamed can start several agents on a feature while Ahmed struggles to see their contributions or equip his own agents with what they learned. Shared Discord connected to Hermes is the current workaround; useful learning also flows from Hermes into Notion.

The product succeeds when a colleague can understand the work from evidence, then reuse an authorized lesson without a manual recap. Activity counts alone do not establish delivery, and captured conversations alone do not establish reliable knowledge. Owl Mast keeps the existing trackers, repositories, execution tools, and knowledge flow authoritative for their respective responsibilities.

AISQUAD is the first internal customer. The initial users are contributors who need project context, leads who need work and acceptance evidence, and the AISQUAD owner who needs an authorized overview of both projects. These are viewing needs, not an approved access-role hierarchy. Public adopters are an eventual audience for the open-source product; monetization and broad external deployment are outside the pilot.

### Source-grounded pilot scenarios

These scenarios restate the workflow recorded in the brief and Notion. They are acceptance scenarios, not claims that a detailed screen journey has been user-tested.

- **SC-1 — Ahmed understands Mohamed’s work.** Mohamed starts agents in an existing execution tool against a project work item. Ahmed inspects the work item, initiator, observed agents, contributions, blockers, and acceptance evidence in Owl Mast. He can follow the evidence to the source and see what observation missed. Starting or intervening in agents remains in their existing tool.
- **SC-2 — Ahmed’s next agent receives useful learning.** After Mohamed’s work produces a sourced lesson, Ahmed enrolls an existing agent in the authorized project. The agent receives the applicable lesson without Ahmed copying a recap. Receipt is recorded separately from demonstrated use. The lesson remains project-scoped.
- **SC-3 — Mohamed's reusable lesson reaches the other project.** Mohamed's lesson is evaluated under the project's promotion policy. In automatic mode, a qualifying company-safe version is published; manual mode requires an authorized person's approval; disabled mode publishes nothing new. The version identifies its permitted audience and retains controlled provenance. Ahmed's agent in the other project receives approved content without gaining access to the original project's restricted evidence.

All three must be demonstrated across the Syntelligence and Movesion boundaries. The pilot must support Claude and Codex in both projects. Exact screens and client-specific interactions remain UX and integration work; the reference is connecting existing agents to a common workspace, with execution remaining in their existing tools.

## 2. Shared vocabulary

| Term | Meaning |
| --- | --- |
| Company | AISQUAD, the initial organizational boundary. Ownership claims do not grant access or reuse rights. |
| Project | An explicit customer/work boundary with its own connections, memberships, knowledge, and permitted data use. |
| Connection | An authorized connection to one source account/site and a defined resource scope. |
| Work item | A source-qualified tracker item; includes source account/site, project, and identifier. |
| Human / agent identity | A known person or executing agent, linked to source identities with provenance. Unknown identities remain unknown. |
| Agent run | An observed execution session, including any available initiator and delegation relationships. |
| Contribution | A linked change, pull request, document, or other output associated with work. |
| Evidence | A source reference or permitted captured record supporting an observation or claim, with collection time and source identity. |
| Acceptance evidence | A source artifact showing that defined acceptance criteria were met, with its approving authority or configured source rule. Each pilot work item names its existing acceptance authority/artifact before demonstration. |
| Knowledge item | A versioned lesson, skill, or memory with scope, provenance, lifecycle state, and applicability. Raw records are evidence, not automatically guidance. |
| Promotion | Explicit publication of an evaluated knowledge version for company-wide use, authorized by an automatic policy or a person. It does not grant access to its original project. |
| Knowledge maintainer | A person authorized to configure a project's knowledge policy, review guidance, approve manual promotion, and withdraw knowledge. This permission does not bypass source access. |
| Coverage | What a connection/client can observe or deliver, what it actually collected, and where gaps or delays exist. |
| Enrollment | Connecting an existing contributor’s agent to an authorized project for observation and knowledge delivery. |

## 3. Functional requirements

### 3.1 Project setup and enrollment

Setup must preserve the teams’ existing tools and minimize repeated configuration. Initial integration administration and recurring agent enrollment are separate experiences and measurements.

#### FR-1 — Separate project connections

An administrator can configure distinct connections for Syntelligence’s Jira and GitHub, and Movesion’s separate Jira and Bitbucket.

- Both project environments can remain connected simultaneously. Identical Jira keys, repository names, or user display names in separate sources do not merge records.
- Each connection shows the account/site, authorized resources, project association, and supported capabilities. A failed or revoked connection does not make the other project unavailable.
- Exact hosting editions and permissions must be verified before connector implementation; a generic Jira or Bitbucket label does not establish compatibility.

#### FR-2 — Minimal enrollment

A contributor can connect existing Claude and Codex clients to the same Owl Mast workspace and select projects they may access, without migrating repositories, trackers, or the current knowledge store. Realizes SC-2.

- Enrollment identifies the selected project and verifies observation and knowledge-delivery readiness separately.
- Missing permissions or unsupported client capabilities produce specific next steps. Enrollment cannot silently select a different project or request unnecessary execution authority.
- **[ASSUMPTION A-5]** After administrator preparation, recurring enrollment requires at most one client connection/profile and an authorized project selection, followed by a readiness result. Routine sessions reuse that enrollment; contributors do not repeat source credentials, hand-copy lessons/skills, or configure project connectors. This proposed step ceiling makes “minimal effort” testable and is revisited in pilot enrollment trials.
- Administrative setup, contributor actions, manual steps, time to first useful knowledge delivery, and time to the first useful project action are recorded separately. Initial setup complexity is acceptable; recurring manual integration work is not. Time budgets are calibrated during the pilot (§9).

#### FR-3 — Connection health and recovery

An authorized operator can inspect each connection’s last successful collection, current failure, and affected coverage.

- Interrupted collection is shown as stale or unavailable, never as zero activity or completed work. Recovery does not duplicate contributions, runs, or usage already collected.
- An unsupported capability stays visibly unsupported after a connection otherwise succeeds. One healthy connector cannot imply full project coverage.

### 3.2 Work observation and evidence

Owl Mast answers who initiated work, what was observed, what changed, and what supports acceptance. It does not replace task ownership or execute corrective actions. Realizes SC-1.

#### FR-4 — Human, agent, and delegation attribution

An authorized viewer can distinguish the initiating person, executing agent, delegation chain, and repository identity when the sources provide them.

- Source-provided identity, an explicitly confirmed mapping, and an inferred association are distinguishable. Unattributed activity remains visible.
- A commit author or account credential alone cannot establish who initiated an agent run. Autonomous activity need not have an immediate human author.

#### FR-5 — Work-to-contribution evidence chain

An authorized viewer can follow a work item to related runs, contributions, and acceptance evidence, and open the supporting source records.

- Links identify their source and correlation basis. Unlinked or ambiguous records remain discoverable without being presented as certain matches.
- Both Jira→GitHub and separate Jira→Bitbucket demonstrations include a real work item, an observed run, a repository contribution, and actual acceptance evidence. In ordinary operation, missing evidence is explicitly labeled; an incomplete chain does not satisfy the pilot proof.
- A merged contribution, a completed tracker item, a passing check, acceptance, and deployment remain separate facts; one does not imply another.

#### FR-6 — Progress and dependencies

An authorized lead can inspect project/work-item progress and relevant dependencies using source evidence.

- Progress identifies its scope, denominator, and observation time. Added or removed work changes the denominator visibly.
- Dependencies distinguish explicit source relationships from inferred relationships. A blocked dependency names the evidence or states that it is unverified.
- Owl Mast does not change tracker status or declare a parent deliverable accepted solely because subtasks are complete.

#### FR-7 — Attention and incomplete observation

An authorized viewer can find observed failures, explicit blockers, and work awaiting review without monitoring every execution tool.

- Each attention item states why it appears, its source, and when it was last observed. The viewer can open the existing tool to investigate.
- Missing telemetry is “unknown” or “stale,” not proof of a failed or stalled agent. Reported successful checks disclose skipped/not-run status when that evidence exists.
- No attention item offers launch, pause, cancel, retry, merge, or deployment controls in v1.

### 3.3 Project knowledge and delivery

Knowledge must be useful to a new session, attributable, and bounded to its intended audience. The existing Hermes-to-Notion learning flow must continue. Realizes SC-2 and SC-3.

#### FR-8 — Capture with provenance

An authorized contributor or configured learning flow can submit a lesson, skill, or memory to its project with supporting evidence.

- Each knowledge item records origin, project, contributor/agent when known, creation/update time, applicability, and links to permitted evidence.
- Raw transcripts or extracted suggestions are not automatically labeled validated. An item without sufficient evidence can remain a candidate with uncertainty visible.
- Duplicate submissions can be recognized and linked to the existing item; ingestion retries cannot create independent approved copies.

#### FR-9 — Review and knowledge lifecycle

A knowledge maintainer can distinguish candidate, approved, superseded, withdrawn, and conflicting knowledge versions.

- Approval records which person or validation policy evaluated which version, the basis, and when. Automatically evaluated guidance is distinguishable from human-reviewed guidance. A correction preserves provenance and identifies the version it replaces.
- Conflicting guidance is exposed to the recipient instead of silently choosing the newest text as fact. An owner can identify items needing review.
- **[ASSUMPTION A-1]** Approved guidance is the default delivery set; candidates or unresolved conflicts require an explicitly labeled diagnostic request. Automated validation may approve guidance when configured checks pass. Product owner revisits this default during the pilot's knowledge-quality walkthrough.

#### FR-10 — Scoped knowledge delivery

An enrolled agent or authorized contributor can retrieve applicable project knowledge and approved company-wide knowledge without a manual recap.

- Delivery uses an explicit, authorized project context. Requests with missing or unauthorized scope fail without returning another project’s content.
- Results include the knowledge version, scope, applicability, freshness/review information, and permitted source references. If no relevant knowledge is found, delivery returns an empty result.
- Retrieval favors the requested task/project over loading every project’s history. The client contract must expose any truncation or omitted results relevant to interpreting the response.

#### FR-11 — Delivery and reuse evidence

An authorized reviewer can distinguish knowledge that was available, retrieved, delivered, and demonstrably reused.

- A retrieval record identifies the recipient, project, item/version, and time without requiring retention of a full conversation.
- Delivery alone is not counted as successful reuse. Pilot reuse evidence links a specific lesson/version to a subsequent task action or output and includes human verification of usefulness.
- Automatic claims of productivity or business impact are not inferred from retrieval counts.

#### FR-12 — Explicit company-wide promotion

A knowledge maintainer can select automatic, manual-approval, or disabled promotion for a project. Automatic is the preferred operating mode once its publication policy and allowed audience are configured.

- Automatic mode identifies reusable candidates and publishes only versions that pass the configured company-use checks. Manual mode identifies candidates but requires a knowledge maintainer's approval of the exact version. Disabled mode performs no new company promotion; project capture and project-scoped delivery continue.
- Before publication, checks establish provenance, reusable applicability, permitted audience/use, absence of restricted customer details or secrets, and no unresolved contradiction or withdrawal. Failed or uncertain checks leave the item project-scoped with a reason; automated confidence is not permission to disclose source content.
- The operation identifies the exact content and intended audience. New captures and edits remain project-scoped until that version independently passes the selected promotion mode. A previously approved version never grants automatic approval to subsequent edits.
- Company-wide content must be usable without exposing restricted customer text, credentials, source snippets, or private links to unauthorized recipients. Provenance remains available only to authorized readers.
- Promotion records the publishing person/automation identity, evaluated version, policy version, date, and decision basis. Company ownership alone never authorizes promotion.
- Policy changes are limited to authorized knowledge maintainers and audited. Switching to manual or disabled mode prevents an in-flight automatic publication from completing under the old mode; enabling automatic mode evaluates existing candidates against the current policy before publishing.
- **[ASSUMPTION A-4]** Disabling promotion stops new publication; already published versions remain retrievable until superseded or withdrawn. This separates a publication switch from revoking existing knowledge; product owner verifies the behavior during the policy walkthrough.

#### FR-13 — Withdrawal and supersession

A knowledge maintainer can withdraw guidance, and the system can quarantine a version when it detects unreliable or conflicting evidence. Earlier deliveries remain traceable.

- **[ASSUMPTION A-2]** Withdrawal or quarantine prevents future ordinary retrieval of the affected version and its promoted derivatives, while retaining a restricted audit record. Recipients can recognize the withdrawn/superseded version on their next knowledge request. Re-publication requires fresh evaluation under the current policy.
- Owl Mast does not claim it can erase context already delivered to an external client or undo an agent’s past actions. Cache/recipient handling must be specified in the delivery contract.
- Cached content must be checked against current eligibility before a new delivery; if eligibility cannot be checked, the item is withheld. This cannot revoke copies already held inside an external agent session.

#### FR-14 — Preserve the current learning flow

Hermes can continue its established learning/memory flow into Notion while Owl Mast observes and delivers permitted project knowledge.

- Pilot acceptance demonstrates continued Hermes-to-Notion capture and authorized delivery of the resulting knowledge through the validated v1 delivery path. Existing retrieval support is not presumed; adoption cannot require a bulk knowledge migration or a second manual save for every lesson.
- Source ownership, write responsibilities, and synchronization behavior are explicit in the implementation design. A sync failure is visible and cannot silently overwrite newer source knowledge.

### 3.4 Authorized views and usage

Views support contributors, leads, and the AISQUAD owner without promising visibility into inaccessible customer material.

#### FR-15 — Project and company views

An authorized viewer can inspect project progress, agent activity, attention items, knowledge, and usage, then drill into permitted evidence.

- A company view aggregates only the data the viewer is entitled to see. Project membership or company ownership alone does not override source restrictions.
- Filters retain project and time context during drill-down. Empty, unavailable, and incomplete states are distinct.
- The human experience includes a shared workspace showing connected Claude and Codex clients and their authorized project context, drawing on the user's T3 Code setup. It does not require a new coding chat/terminal, agent launcher, or a clone of T3 Code. Surface packaging remains a UX/architecture choice.

#### FR-16 — Usage and cost semantics

An authorized viewer can understand observed usage and attributable cost by project, client/model, agent, person, or work item where evidence supports that breakdown.

- Observed units, estimated API-equivalent cost, subscription allocation, and actual billed amounts are labeled separately; absent categories are unavailable, not zero.
- Totals show the observation period, coverage, unknown/unpriced/unassigned portions, and attribution basis. Missing data cannot produce a complete-looking ROI claim.
- Duplicate collection is not double-counted. Cost estimates record their pricing basis and date. Budget enforcement and autonomous allocation are outside v1.

### 3.5 Access and product boundaries

#### FR-17 — Enforce project and source access

Every viewer and agent receives only data authorized for the requested purpose and audience.

- Authorization applies to search, knowledge delivery, source previews, drill-downs, aggregates, and exports where provided. Shared connection credentials do not grant every viewer their full source access.
- Tests cover both directions between Syntelligence and Movesion, an unauthorized third identity, a revoked user, a same-project user lacking access to a restricted source record, and a source permission removed after content was indexed. Restricted reads must fail even when shared connection credentials can read that record; unverifiable authorization fails closed.
- Revocation prevents new reads through Owl Mast, including cached/indexed restricted material and derived summaries. A separately authorized company-safe publication does not expose its revoked source; if that publication's own permission is withdrawn, FR-13 applies. Previously delivered copies and external source access are reported as separate limits.

#### FR-18 — Govern collected content

A project administrator can identify and limit what content a connection collects and retains.

- **[ASSUMPTION A-3]** The pilot defaults to necessary metadata, permitted evidence references, and deliberately submitted knowledge; raw chat/transcript capture requires explicit project-level enablement and a stated retention policy.
- Credential secrets are excluded from persisted observation payloads, knowledge, indexes, logs, and generated summaries; integration credentials remain in designated protected configuration. Project administrators apply equivalent exclusion rules to restricted content. Redaction or access denial cannot leave excluded content in snippets, caches, exports, or derived summaries.
- Retention, removal, and propagation behavior for derived content must be documented and verified before live customer content is ingested. This PRD does not claim a legal compliance certification.

#### FR-19 — Keep execution authority outside Owl Mast

Owl Mast observes work and performs authorized knowledge lifecycle operations without controlling agents or delivery pipelines.

- Observation connections request only required read capabilities; knowledge writes are restricted to designated stores and approved scope changes.
- Interfaces and integration contracts contain no agent launch, pause, cancel, retry, shell execution, merge enforcement, or deployment action.
- Evidence links may open an existing tool; they do not execute its actions on the user’s behalf.

#### FR-20 — Open-source repeatability

An authorized pilot operator can reproduce the supported Owl Mast setup from its repository and documented prerequisites. Public-release packaging is a separate gate.

- Internal pilot reproduction includes configuration examples without secrets, installation instructions, supported integration/client boundaries, and limitations needed for the two-project workflow. Public open-source release additionally provides the distributable source and selected license.
- Real customer data and credentials are not published with the source. Dependency and license review is a release prerequisite; the license choice remains open.
- Deployment packaging and component selection belong to architecture. The pilot does not require public release before internal value can be tested.

### 3.6 Existing client and Notion integration

#### FR-21 — Preserve Notion-backed client workflows

Claude and Codex can continue authorized Notion page creation and receive permitted Notion-backed knowledge/skills through the validated pilot integration.

- User-reported page creation is verified in the pilot without adding a second manual capture step. Skill discovery, reading, project scoping, and delivery are tested separately; the user's belief that agents already read Notion skills is not treated as verified behavior.
- Supported skill delivery identifies the source version and applicable project; inaccessible or irrelevant skills are not copied into another project's context. Creating a page does not automatically make it approved guidance or company-wide knowledge.
- Integration preserves Notion's role in the current workspace without requiring a replacement memory store. Direct client access and Owl Mast-mediated delivery have documented permission boundaries; Owl Mast cannot promise to revoke access granted independently by Notion or a client.

## 4. Cross-cutting quality requirements

- **NFR-1 — Isolation:** The pilot passes all cross-project and revoked-access negative cases in FR-17. No unauthorized content or inference-bearing snippet is returned. Failed access checks do not fall back to company scope.
- **NFR-2 — Evidence integrity:** Every displayed claim distinguishes source fact, inference, estimate, and unknown where applicable. Source timestamps and collection timestamps remain distinguishable; partial coverage cannot look complete.
- **NFR-3 — Resilience:** A connection outage preserves access to other authorized data with stale labels. Recovery is tested with duplicate and out-of-order records and does not silently lose or multiply observations.
- **NFR-4 — Freshness:** Each supported connection declares a collection cadence and the point at which data is marked stale; each knowledge-delivery path declares its cache/withdrawal behavior. Numeric latency and freshness budgets are set against the actual pilot environment before its performance acceptance run, not invented from research.
- **NFR-5 — Usability:** A contributor completes enrollment and obtains useful project knowledge using the supplied instructions, without bespoke developer intervention. The pilot records failures and help required as well as elapsed time, tests FR-2's proposed step ceiling, and calibrates time targets under §9.
- **NFR-6 — Diagnostic safety:** Operators can identify failed collection, authorization, delivery, and publication operations without exposing credentials or restricted source text in logs. Audit records identify the actor, project, operation, item/version where relevant, and outcome.

## 5. MVP boundary and integrations

The MVP proves one complete observation-to-reuse workflow in each required environment. Implementing integrations sequentially is acceptable; release acceptance requires both.

| Environment | Required tracker and repository | Required proof |
| --- | --- | --- |
| Syntelligence | Its Jira account/site and GitHub | Work→run→contribution→acceptance evidence; Claude and Codex both enroll and receive permitted project knowledge |
| Movesion | Separate Jira account/site and Bitbucket | The same end-to-end proof with Claude and Codex, without relying on Syntelligence credentials or identifiers |
| Shared learning context | Existing Hermes→Notion flow | Learning still captured; authorized retrieval works; restricted knowledge stays in its project |

Claude and Codex are required; Hermes continuity covers the established learning flow, not a requirement to ship a third full client adapter. Other tools and separate AWS accounts are known context, not a commitment to additional v1 connectors. Exact provider editions, permissions, client integration contracts, and knowledge contracts are implementation discovery tasks; no stack has been selected.

**Excluded from v1:** agent execution controls; a replacement tracker or coding harness; merge/deployment enforcement; autonomous remediation; predictive budget allocation; proof of causal ROI; universal connector support; public operational data; unconditional company promotion; monetization and sandbox hosting. These exclusions protect the first observation-and-reuse outcome. Future consideration is not a delivery commitment.

## 6. Success and pilot acceptance

Success measures understanding and reuse while preserving boundaries. Numeric business improvement targets remain unconfirmed; the pilot must first establish a reproducible baseline.

- **SM-1 — Work understanding:** For comparable work in each project, record the time and outside help Ahmed needs to explain initiator/agents, changes, blockers, and acceptance evidence before and with Owl Mast. Verify the explanation against the sources. Validates FR-4–FR-7 and FR-15. Report improvement and errors together; no reduction target is yet approved.
- **SM-2 — Fresh-agent enrollment:** Record administrative connection setup separately from per-agent enrollment time, manual steps, assistance, first useful knowledge delivery, and first useful project action. A delivered lesson is an intermediate milestone; the outcome is useful work in the selected project. Measure all four Claude/Codex × Syntelligence/Movesion combinations against FR-2's step ceiling, including returning sessions. Validates FR-1–FR-3, FR-10, and FR-21. A failed setup remains in the denominator.
- **SM-3 — Demonstrated reuse:** **[ASSUMPTION A-6]** At least one sourced knowledge item in each project is delivered to a different contributor's agent and demonstrably helps its task without a copied recap. Separately demonstrate one explicit, company-safe promotion consumed from the other project. These are proposed minimum pilot proof cases, not statistical effectiveness claims. Validates FR-8–FR-14.
- **SM-4 — Observation completeness:** Each project demonstrates a work-to-acceptance evidence chain and discovery of an observed blocked/failed run that someone was not actively watching. Report observed, ambiguous, missing, and unsupported portions of the chain, plus usage attribution coverage. Validates FR-3–FR-7 and FR-16.
- **SM-5 — Boundary proof:** All project-isolation, restricted-source, and revoked-access acceptance cases pass. Demonstrate successful automatic promotion, failed/uncertain checks that keep an item private, manual approval, disabled promotion, mode changes during pending publication, edited versions, and withdrawal/quarantine blocking new delivery. Observations do not grant execution authority. Validates FR-12–FR-13 and FR-17–FR-19. A boundary failure blocks the pilot's acceptance regardless of other gains.

Counter-metrics prevent misleading success:

- **SM-C1 — Knowledge quality:** Track stale/conflicting guidance and repeated work alongside reuse counts.
- **SM-C2 — Understanding quality:** Track wrong or overconfident work explanations and review delays alongside faster understanding.
- **SM-C3 — Setup burden:** Track connection maintenance, human cleanup, and setup assistance alongside enrollment speed.
- **SM-C4 — Accounting coverage:** Track unassigned/unpriced activity and collection gaps alongside cost totals.

More captured text, more agent runs, and more retrieved items are not success targets.

The product owner accepts the pilot only after seeing both end-to-end demonstrations, the negative access cases, and the measured limitations. A synthetic fixture may exercise failure handling but cannot replace the live authorized toolchain proof. License/public release readiness is a separate decision from internal pilot usefulness.

## 7. Risks and operating constraints

The principal risks are incomplete source visibility, misleading identity/cost attribution, leakage through shared integration credentials, stale or contradictory learning, and setup effort that exceeds the benefit. FR-3–FR-18 make these observable and testable instead of promising perfect coverage.

Customer content access, collection permission, and acceptable processing destinations must be confirmed for each actual environment before live ingestion. AISQUAD ownership language does not decide those permissions. Product requirements define the boundaries; architecture selects a viable access model, storage/processing arrangement, and integration contracts that satisfy them.

## 8. Assumptions index

| ID | Proposal | Owner and revisit condition |
| --- | --- | --- |
| A-1 | Approved guidance is the default delivery set; candidates/conflicts require a diagnostic request (FR-9). | Product owner; revisit during the pilot knowledge-quality walkthrough. |
| A-2 | Withdrawal/quarantine stops new delivery, including promoted derivatives, with restricted audit history and explicit limits on previous copies (FR-13). | Product owner; revisit during the lifecycle walkthrough before live promotion. |
| A-3 | Metadata/references/submitted knowledge by default; raw transcripts require explicit enablement and retention (FR-18). | Product owner and project data owners; resolve before live-content ingestion. |
| A-4 | Disabling promotion stops new publications; withdrawing existing published versions is a separate action (FR-12). | Product owner; revisit during the policy walkthrough before live promotion. |
| A-5 | One client connection/profile plus authorized project selection; no repeated source setup or manual context copying (FR-2). | Product owner with pilot participants; revisit during enrollment trials before the acceptance run. |
| A-6 | One verified reuse per project and one company-safe cross-project reuse are minimum proof cases (SM-3). | Product owner with pilot participants; confirm sample selection before the acceptance run. |

## 9. Unresolved requirements and downstream handoff

### Confirmed choices and bounded design work

The user confirmed the initial Claude/Codex pair, T3 Code setup reference, acceptance of initial administrative complexity, minimal recurring effort, and automatic/manual/disabled promotion modes. Named knowledge maintainers and the company-use policy are project configuration, not a demand that every item receive human approval.

The functional requirements are suitable for UX and architecture discovery. The remaining assumptions have explicit defaults and validation points; none permits weaker project isolation. Integration feasibility must be established before committing connector estimates or claiming a ready-to-build implementation plan.

### Bounded follow-up work

- **Connector feasibility — architecture/integration owner:** verify actual Jira and Bitbucket editions, accounts, source permissions, identity/event availability, and capture limitations before estimating connector stories. Do not substitute a GitHub-only demo if Bitbucket work is harder.
- **Deployment and data handling — project data owners with architecture:** select the operating surface/deployment package and confirm permissible captured content, processing destinations, retention/removal rules, and access revocation before connecting real customer data. No managed-cloud or self-hosting commitment has been inferred from the T3 Code reference.
- **Pilot calibration — product owner with pilot participants:** select work items and their existing acceptance authority/artifact; establish baseline task samples, time targets, freshness/performance budgets, and effectiveness targets before the relevant acceptance run. The FR-2 step ceiling already defines recurring setup behavior. Report measured outcomes without retroactively selecting favorable thresholds.
- **Open-source license — product owner:** select the license and review dependency compatibility before public release; open-source direction is already decided.
- **UI detail — UX owner:** turn the source-grounded scenarios and T3 Code reference into tested user journeys. Preserve evidence, source freshness, coverage, and uncertainty in the design without adding execution controls.

The addendum retains research references and implementation questions. The PRD does not authorize deployment, publication of customer data, or changes to execution systems.
