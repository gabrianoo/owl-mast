# Finalized PRD package — UX source extraction

Read in full on 2026-11-05. This is a source extraction for UX discovery, not a selection of visual preferences, operating surface, or architecture. No user-tested screen journeys are established by these sources.

## Sources and authority

[PRD](../../../prds/prd-owl-mast-2026-11-05/prd.md) (final, 324 lines); [addendum](../../../prds/prd-owl-mast-2026-11-05/addendum.md) (55 lines); [PRD memlog](../../../prds/prd-owl-mast-2026-11-05/.memlog.md) (22 lines); [review disposition](../../../prds/prd-owl-mast-2026-11-05/review-disposition.md) (21 lines). Line references use these versions as read.

Authority distinctions:

1. **User-confirmed direction** is identified in PRD §0, §9, and the memlog's later decisions. It supersedes earlier execution controls, one-project pilot, mandatory manual promotion, and uncertainty about initial clients.
2. **Specified PRD requirements** translate that direction into observable behavior. These are requirements for downstream design, but not evidence that the user chose a specific UI, hierarchy, color, interaction, or integration implementation.
3. **Six tagged assumptions** are bounded proposals, not confirmed decisions. Their original text and owners/revisit conditions are retained below.
4. **References and candidate mechanisms** are evidence or possibilities, not selections. Screenshots establish visible patterns, not proven integration or usability. Source: PRD lines 12–16; addendum lines 7–9; review disposition lines 3–17.

## User-confirmed direction

| Confirmed direction | Source |
| --- | --- |
| Open source; AISQUAD first. | PRD line 12; memlog line 6. |
| V1 observes work and delivers knowledge; agent execution remains in existing tools. | PRD lines 12–14, 30–34; memlog line 6. |
| Demonstrate Syntelligence's Jira + GitHub and Movesion's separate Jira + Bitbucket. A one-project proof is insufficient. | PRD lines 12–14, 34; memlog line 6. |
| Claude and Codex are both required initially, in both projects. T3 Code's two-agent setup is the experience reference. | PRD lines 12, 34; memlog lines 14, 16; review disposition line 9. |
| Initial administration can be complex. Recurring contributor/agent onboarding must require minimal effort. | PRD lines 12, 71–76; memlog line 14. The exact step ceiling is A-5, not a confirmed preference. |
| Preserve Hermes-to-Notion learning and existing Notion workflows. Existing client page creation is user-reported; current Notion skill reading is unverified. | PRD lines 122, 178–181, 241–245; memlog lines 13–16; addendum lines 21–25. |
| Knowledge defaults to the project; prefer automatic identification and promotion of reusable company-safe knowledge, with manual-approval and disabled modes available. | PRD lines 12, 158–166; memlog lines 15–16. Automatic operation remains policy-authorized publication of an evaluated version. |
| Project and source access must survive aggregation, retrieval, and promotion. Owning the company does not grant access or reuse rights. | PRD lines 12, 40–51, 191, 205–219; addendum line 23. |
| UX is the next phase; architecture follows. Ask only unresolved questions rather than repeating settled discovery. | Memlog lines 7, 22; current user instruction. |

## Functional requirements as UX obligations

The obligations here are specified by the finalized PRD. They do not select screens or visual treatments.

| ID | Concise UX obligation | Source lines |
| --- | --- | --- |
| FR-1 | Allow an administrator to distinguish and configure both projects' separate connections. Show account/site, authorized resource scope, associated project, and capabilities. Keep identically named source records distinct and failures isolated. Provider names alone must not imply verified compatibility. | PRD 61–67 |
| FR-2 | Connect existing Claude/Codex clients to a common workspace with an explicit authorized project. Present observation readiness and knowledge-delivery readiness separately, and actionable permission/capability failures. Separate initial administrator work from recurring enrollment; preserve A-5 as a proposed step ceiling. | PRD 69–76 |
| FR-3 | Show each connection's last successful collection, current failure, and affected coverage. Distinguish stale/unavailable/unsupported from zero or complete. Partial success cannot imply all capabilities work. Recovery must not duplicate visible activity. | PRD 78–83 |
| FR-4 | Distinguish initiating person, executing agent, delegation chain, and repository identity. Label source facts, confirmed mappings, inferred associations, and unknown attribution. Do not infer an initiator solely from a commit author or credential. | PRD 89–94 |
| FR-5 | Let viewers traverse work → runs → contributions → acceptance evidence and open permitted sources. Identify link source and correlation basis; retain ambiguous/unlinked items. Keep merged, tracker-completed, checks-passed, accepted, and deployed facts separate. | PRD 96–102 |
| FR-6 | Show scoped progress with denominator and observation time, visible scope changes, and explicit versus inferred dependencies. Identify blocker evidence or uncertainty. A completed child set cannot imply parent acceptance. | PRD 104–110 |
| FR-7 | Make observed failures, explicit blockers, and review needs discoverable with reason, source, freshness, and source-tool links. Unknown/stale telemetry is not a stalled or failed agent. Preserve skipped/not-run check information. No execution actions. | PRD 112–118 |
| FR-8 | Support project-scoped lesson/skill/memory submission with origin, contributor/agent when known, times, applicability, and permitted evidence. Distinguish candidates/raw records from validated knowledge; recognize duplicates without creating separate approved copies. | PRD 124–130 |
| FR-9 | Distinguish candidate, approved, superseded, withdrawn, and conflicting versions. Show evaluator/person/policy, evaluated version, basis, and time. Expose contradictions and items needing review. Default delivery eligibility remains A-1. | PRD 132–138 |
| FR-10 | Deliver applicable project and approved company knowledge within explicit authorized context. Show version, scope, applicability, freshness/review information, permitted references, and relevant truncation/omissions. Distinguish an empty relevant result from a scope/authorization failure; never substitute another project's content. | PRD 140–146 |
| FR-11 | Keep available, retrieved, delivered, and demonstrably reused states separate. Show recipient, project, item/version, and time without requiring full conversation retention. Claims of reuse require task evidence and human verification; retrieval counts do not prove productivity. | PRD 148–154 |
| FR-12 | Let authorized maintainers choose automatic/manual-approval/disabled promotion per project. Show exact version, target audience, policy, checks, publication result/reason, actor, date, and audit basis. Uncertain or failed checks keep content project-scoped. Edits require new evaluation. A mode change must prevent pending automatic publication under the old mode. Existing-publication behavior is A-4. | PRD 156–166 |
| FR-13 | Support withdrawal, supersession, and system quarantine with traceable earlier deliveries. Explain the inability to erase external clients' past copies/actions. Eligibility must be rechecked for new delivery; withhold if unverifiable. The detailed withdrawal/default retrieval behavior remains A-2. | PRD 168–174 |
| FR-14 | Preserve Hermes → Notion capture and demonstrate authorized delivery through a validated path. Avoid bulk migration or a second manual save. Make synchronization failures visible and prevent silent overwrite of newer source knowledge. | PRD 176–181 |
| FR-15 | Provide authorized project/company views of progress, agent activity, attention, knowledge, and usage with evidence drill-down. Retain project/time context. Distinguish empty/unavailable/incomplete. Show both connected clients and their authorized context; shared workspace does not establish a new coding chat, terminal, launcher, or T3 clone. | PRD 187–193 |
| FR-16 | Distinguish observed units, API-equivalent estimates, subscription allocation, and actual bills. Show observation period, coverage, unknown/unpriced/unassigned portions, attribution basis, and estimate pricing/date. Missing categories are unavailable, not zero. No complete-looking ROI or budget-control claims. | PRD 195–201 |
| FR-17 | Preserve authorization across search, delivery, source previews, drill-down, aggregates, and exports if present. Fail closed when authorization cannot be verified. Cover cross-project, same-project source restrictions, revoked users, and indexed/cached/derived data after revocation. Do not leak restricted text through summaries or snippets. | PRD 205–211 |
| FR-18 | Allow project administrators to identify and limit collected/retained content. Exclude secrets and restricted content throughout payloads, logs, indexes, snippets, caches, exports, and derived summaries. Collection defaults remain A-3; retention/removal rules need validation before live ingestion. | PRD 213–219 |
| FR-19 | Keep agent launch, pause, cancel, retry, shell execution, merge enforcement, and deployment out of every surface. Evidence links open existing tools without executing their actions. Authorized knowledge lifecycle operations remain in scope. | PRD 221–227 |
| FR-20 | Provide reproducible internal setup instructions, prerequisites, secret-free examples, and supported client/integration boundaries. Keep pilot reproduction separate from public-release packaging/license decisions. No customer data in public source. | PRD 229–235 |
| FR-21 | Preserve authorized Claude/Codex Notion page creation without a duplicate save, and separately demonstrate skill discovery, reading, scope, and delivery. Identify skill source version/project. Page creation does not imply approved guidance/promotion; independent Notion/client access has separate revocation limits. | PRD 239–245 |

## Exact tagged assumptions — remain proposals

Original tagged text is quoted verbatim. Owners/revisit conditions reproduce the assumptions index. Source copies supplied by the user are quoted for planning fidelity.

### [ASSUMPTION A-1] — default delivery eligibility

> Approved guidance is the default delivery set; candidates or unresolved conflicts require an explicitly labeled diagnostic request. Automated validation may approve guidance when configured checks pass. Product owner revisits this default during the pilot's knowledge-quality walkthrough.

Source: PRD line 138. **Owner and revisit condition:** Product owner; revisit during the pilot knowledge-quality walkthrough. Index: PRD line 301.

### [ASSUMPTION A-2] — withdrawal/quarantine

> Withdrawal or quarantine prevents future ordinary retrieval of the affected version and its promoted derivatives, while retaining a restricted audit record. Recipients can recognize the withdrawn/superseded version on their next knowledge request. Re-publication requires fresh evaluation under the current policy.

Source: PRD line 172. **Owner and revisit condition:** Product owner; revisit during the lifecycle walkthrough before live promotion. Index: PRD line 302.

### [ASSUMPTION A-3] — default collected content

> The pilot defaults to necessary metadata, permitted evidence references, and deliberately submitted knowledge; raw chat/transcript capture requires explicit project-level enablement and a stated retention policy.

Source: PRD line 217. **Owner and revisit condition:** Product owner and project data owners; resolve before live-content ingestion. Index: PRD line 303.

### [ASSUMPTION A-4] — disabled promotion and existing publications

> Disabling promotion stops new publication; already published versions remain retrievable until superseded or withdrawn. This separates a publication switch from revoking existing knowledge; product owner verifies the behavior during the policy walkthrough.

Source: PRD line 166. **Owner and revisit condition:** Product owner; revisit during the policy walkthrough before live promotion. Index: PRD line 304.

### [ASSUMPTION A-5] — enrollment step ceiling

> After administrator preparation, recurring enrollment requires at most one client connection/profile and an authorized project selection, followed by a readiness result. Routine sessions reuse that enrollment; contributors do not repeat source credentials, hand-copy lessons/skills, or configure project connectors. This proposed step ceiling makes “minimal effort” testable and is revisited in pilot enrollment trials.

Source: PRD line 75. **Owner and revisit condition:** Product owner with pilot participants; revisit during enrollment trials before the acceptance run. Index: PRD line 305.

### [ASSUMPTION A-6] — minimum proof cases

> At least one sourced knowledge item in each project is delivered to a different contributor's agent and demonstrably helps its task without a copied recap. Separately demonstrate one explicit, company-safe promotion consumed from the other project. These are proposed minimum pilot proof cases, not statistical effectiveness claims. Validates FR-8–FR-14.

Source: PRD line 276. **Owner and revisit condition:** Product owner with pilot participants; confirm sample selection before the acceptance run. Index: PRD line 306.

The review disposition explicitly permits UX/architecture discovery with all six assumptions open; each retains its pre-live or acceptance revisit point (review disposition line 17). No assumption weakens isolation (PRD line 314). Related specified safeguards such as rechecking current eligibility before a new delivery remain requirements even while the detailed default is provisional.

## Named protagonists and source scenarios

Use these names verbatim. These are source-grounded acceptance scenarios, not tested screen journeys (PRD lines 28–34).

| Source scenario | Established sequence and outcome | Discovery still needed |
| --- | --- | --- |
| **SC-1 — Ahmed understands Mohamed’s work.** | Mohamed starts agents in an existing execution tool against a project work item. Ahmed inspects work item, initiator, observed agents, contributions, blockers, and acceptance evidence in Owl Mast. He can inspect sources and observation gaps. | Ahmed's real entry point, first question, preferred working device, drill-down sequence, and the point at which he has enough evidence. |
| **SC-2 — Ahmed’s next agent receives useful learning.** | Mohamed's work produces a sourced lesson. Ahmed enrolls an existing agent into an authorized project. It receives applicable project learning without copied recap; receipt and demonstrated use remain separate. | The actual enrollment interaction and recurrence; where readiness/receipt is visible; what Ahmed needs to see or do when delivery is empty, unsupported, stale, or conflicted. |
| **SC-3 — Mohamed's reusable lesson reaches the other project.** | A lesson is evaluated under the project's selected promotion mode. A qualifying version reaches an explicitly permitted company audience. Ahmed's other-project agent receives it without receiving restricted original evidence. | The authorized maintainer's real session, how they inspect exact published content/audience/checks, and how exception handling, manual review, and mode changes fit their work. |

Both projects must demonstrate the full sequences; both clients enroll and receive permitted knowledge in both projects (PRD lines 34, 262–264). The initial administrator and knowledge maintainer are responsibilities, not named personas or an approved access-role hierarchy (PRD lines 24, 51). Do not invent a maintainer's name or equate company owner with access authority.

## Cross-cutting obligations for both UX spines

- Evidence states must distinguish source fact, inference, estimate, and unknown; separate source time from collection time; avoid complete-looking partial coverage (NFR-2, PRD line 250).
- A connector outage leaves other authorized data usable with stale labels; current capability and freshness gaps remain visible (NFR-3–4, PRD lines 251–252).
- Setup, authorization, delivery, and publication failures need safe actionable diagnostics; logs must not expose credentials or restricted text (NFR-6, PRD line 254).
- Pilot evaluation measures understanding accuracy, help needed, enrollment burden, first useful knowledge, first useful action, and demonstrated reuse. Fewer minutes or higher retrieval counts alone are insufficient (PRD lines 274–287).
- The access test scenarios include a same-project user who cannot access a source record and a source permission removed after indexing. A company aggregate, count, preview, or summary must not bypass those restrictions (PRD lines 209–211; review disposition line 15).
- Coverage/status model needs empty, unavailable, incomplete, stale, unsupported, ambiguous, and unknown where applicable. A completed tracker item, a merged contribution, a passing check, accepted work, and deployment remain distinct dimensions (PRD lines 82–83, 93, 100–102, 117, 192).
- Existing-source authority remains intact: no replacing trackers, repositories, execution tools, or the Hermes/Notion flow (PRD lines 22, 178–181, 245).

## What remains UX discovery

These are gaps left by the sources, not recommended answers:

1. **Operating surface and real usage context:** web, desktop, embedded, or multiple surfaces; actual devices, working environment, entry points, and which shared-workspace experience the T3 reference is meant to carry. Surface packaging is explicitly unresolved (PRD lines 193, 319). UX can decide use context without selecting deployment architecture.
2. **Visual identity and reference adoption:** which ConvaDesk visual qualities, if any, the user wants to carry over; density, typography, colors, shape, hierarchy, theme, and branding. No preference is established in the PRD package. The supplied screenshots are references, not reuse authorization (addendum lines 11–17).
3. **Real journey narration:** the concrete beginning, decisions, uncertainty, and successful outcome in the four requested journeys: connection, understanding work, receiving learning, managing promotion. SC-1–3 provide outcomes but not the user's chosen screen interactions (PRD lines 28–34, 322).
4. **Information architecture and default destination:** how an authorized person moves between company/project context, work evidence, connected agents, knowledge, and governance. The requirement to preserve project/time context is established; navigation grouping and landing surface are not (PRD lines 189–193).
5. **Knowledge feedback and interruption:** where recipients see delivery/readiness/usefulness evidence, how they inspect conflicts/withdrawals, and how maintainers encounter actionable exceptions. Notification channels, interruption level, frequency, and scheduled digests are not selected.
6. **Promotion interaction detail:** selecting modes, inspecting exact content and allowed audience, manual review, failed/uncertain checks, in-flight mode changes, and withdrawal. Whether old publications persist when disabling remains A-4; the detailed withdrawal/default set remains A-1/A-2.
7. **Access/error presentation:** how to explain unavailable context without leaking source details; how permitted users identify remediation, current scope, incomplete coverage, and reauthorization needs.
8. **Concern scan:** accessibility, keyboard/input needs, content density, responsive behavior, offline expectations, motion, languages, and dark mode are not specified. Discover actual needs without inventing preferences or promising offline access.

## What stays architecture, integration, or later calibration

| Downstream work | Boundary for UX |
| --- | --- |
| Jira/Bitbucket hosting editions, accounts, precise permissions, event/identity availability, client versions and capabilities. | Represent verified/unsupported/unknown capability honestly; do not choose a connector contract. Sources: PRD 318; addendum 41–45. |
| Deployment package, hosting, storage/processing destinations, transport, index, cache and revocation contracts. | Resolve working surface from user needs; leave implementation choices to architecture. No managed-cloud/self-hosted decision follows from T3. Sources: PRD 295, 319. |
| Notion skill discovery and delivery contract, Hermes synchronization/ownership, source of truth, duplicate reconciliation. | Preserve existing workflows and show readiness/failure; do not claim current skill reading is verified. Sources: PRD 180–181, 241–245; addendum 21–25. |
| Candidate components such as OpenTelemetry, Langfuse, MCP, generated context files, OKF, Operator Memory, Kody, CodeMie, Visdom, PAPI. | All unselected; not IA or stack requirements. Sources: addendum 29–35. |
| Content retention/removal and permission to collect/process real customer content. | A-3 remains provisional; data owners/architecture resolve before ingestion. Sources: PRD 217–219, 295, 303, 319. |
| Exact pilot work items, acceptance authority/artifact, time/freshness/performance thresholds, effectiveness targets, and A-6 samples. | Design observable measurements and evidence; do not invent numeric targets or retrospectively favorable thresholds. Sources: PRD 48, 252–253, 274–289, 320. |
| License, dependency compatibility, public-release distribution. | Open-source direction is confirmed; license and packaging are not. Internal pilot can precede public release. Sources: PRD 231–235, 321. |

## Reference implications without preference selection

The ConvaDesk reference package supports considering ticket evidence drill-down, dependency neighborhoods with graph/list alternatives, release/goal summaries with attention cues, and usage views that retain unassigned work and separate tokens from billing (addendum line 15). The completed/planned/absent-evidence inconsistency in one screenshot makes source/freshness/conflict visibility important; it does not establish the cause or prove a preferred design (addendum line 17). It offers no evidence for onboarding, cross-person delivery, or promotion interaction quality.
