# PRD Quality Review — Owl Mast

## Overall verdict

The reviewed draft is coherent and evidence-conscious: observation leads to authorized knowledge reuse, and both customer toolchains are explicit acceptance conditions. Its readiness disclosures accurately represented the decisions pending when the review ran; the subsequent user answers listed below supersede those disclosures and must be incorporated before this review is used as a current gate. Two independent local clarifications would improve downstream acceptance decisions: define what counts as work acceptance, and distinguish pilot reproducibility from public-release packaging.

Review basis: the full PRD and addendum, using all seven dimensions in `prd-validation-checklist.md`. Severity counts: **0 critical, 0 high, 1 medium, 1 low**. Previously reported FR-5 acceptance-chain and SM-2 first-useful-action issues are fixed in the reviewed version.

**Snapshot note:** This review was completed immediately before a new user answer. That answer establishes Claude and Codex as the initial clients, T3 Code's two-agent setup as an experience reference, permission for complex initial administration with minimal recurring product setup, and a preference for automatic marking/promotion with selectable manual approval or disabled modes. Existing Notion page creation is confirmed; reading skills from Notion remains uncertain. Assertions below about explicit manual promotion and still-pending client selection describe the reviewed snapshot and are superseded by that answer, not objections to the new direction. R-Q1 and R-Q2 concern separate acceptance-language issues. This report has not reviewed the parent's forthcoming policy revision.

## Decision-readiness — adequate

The main decisions are unusually clear: §0 names the confirmed direction; §5 excludes execution, enforcement and a replacement harness; FR-12 rejects automatic company promotion. The trade-off is visible: preserving existing tools and requiring explicit promotion sacrifices centralized control and unrestricted sharing to focus the pilot on observing work and reusing authorized learning.

The remaining choices in §9 are real choices rather than disguised conclusions. The sentence “The PRD remains a draft while their material implications are unresolved” (`prd.md:287`) is correct. It prevents a draft with pending deployment, client-support and knowledge-authority decisions from being mistaken for a build authorization. Those disclosed readiness limits are not newly discovered defects and should not be papered over with invented decisions.

## Substance over theater — strong

The vision is specific to Mohamed's parallel agents, Ahmed's missing work visibility, and the current Discord/Hermes/Notion flow (§1). Contributors, leads and the company owner are described as viewing needs, explicitly not a fictitious access-role hierarchy. There is no unsupported novelty or ROI claim; the addendum explicitly acknowledges overlap with existing products.

The quality requirements in §4 address this product's actual risks: source-qualified identity, incomplete collection, cross-project isolation, stale evidence, duplicate events, knowledge withdrawal and diagnostic exposure. Numeric freshness and usability budgets are deferred openly to the real pilot environment. That limits final acceptance readiness but does not make the section generic NFR furniture.

## Strategic coherence — strong

The thesis is consistent from vision through acceptance: a colleague understands work from evidence and enables another agent to reuse a lesson without a copied recap (§1, SC-1/SC-2). Project connections, work evidence, knowledge delivery and authorized views form a single arc rather than unrelated features. The two-project requirement demonstrates organization-level value without expanding the product into an execution platform (§5).

SM-1 through SM-5 test understanding, fresh-agent usefulness, demonstrated reuse, evidence completeness and boundary preservation. The counter-metrics in §6 address false understanding, stale guidance, repeated work, integration maintenance and misleading cost totals. FR-11 expressly prevents a retrieval count from being treated as verified reuse. This is appropriate prioritization for an internal proof of value.

## Done-ness clarity — adequate

All FRs have at least one observable consequence. Examples include collision-free account/project identities in FR-1, explicit unsupported states in FR-3, missing-scope rejection in FR-10, a concrete knowledge-version-to-task link in FR-11 and negative access cases in FR-17. The repaired FR-5 now states that an incomplete chain does not satisfy pilot proof, while FR-2/SM-2 preserve first useful project action beyond the delivery milestone.

The PRD does not yet claim final quantitative acceptance: onboarding ceilings, performance/freshness budgets and supported clients are openly pending. There is one narrower semantic gap independent of those pending choices.

### Findings

- **[medium] R-Q1 — Define work acceptance independently of its neighboring signals** (§2; FR-5; SM-4, `prd.md:34–49,91–97,259`) — FR-5 requires “actual acceptance evidence” and correctly says a merge, completed tracker item, passing check, acceptance and deployment “remain separate facts.” However, the vocabulary never defines acceptance, and no pilot rule identifies the approving authority or qualifying source record for either project. A downstream team could require a release approval, accept a reviewer comment, or invent an Owl Mast approval workflow, with materially different scope. *Fix:* Define acceptance as a recorded decision or qualifying evidence under the project's existing acceptance practice. Before choosing pilot work items, record the agreed acceptance event/artifact and authorized decision-maker for each project; Owl Mast observes that evidence and does not introduce a new approval gate.

## Scope honesty — strong

The observation/execution boundary is repeated only where it prevents an easy misinterpretation: attention actions in FR-7, connector authority in FR-19 and MVP exclusions in §5. Knowledge writes remain allowed, so “observation” is not falsely converted into a blanket read-only architecture. Other tools and AWS accounts are treated as context rather than extra v1 connectors (§5).

Assumptions A-1 through A-3 are marked inline and indexed with owners/revisit points. Missing promotion authority, capture policy, deployment, instrumentation and performance choices remain visible; the document does not claim source capabilities have been validated. The only small scope ambiguity concerns which reproducibility obligations belong to the internal pilot versus the public release.

### Findings

- **[low] R-Q2 — Separate the internal pilot's source reproduction from public release packaging** (FR-20; §6, `prd.md:221–227,264`) — FR-20 says a “pilot operator” reproduces setup from “published source” and immediately describes what “the open-source release includes,” while §6 states “License/public release readiness is a separate decision from internal pilot usefulness.” The intended sequencing is sensible but these obligations are bundled under one FR without clear acceptance timing. *Fix:* State that the internal pilot must be reproducible by an authorized operator from the project repository and its documented prerequisites; mark the public source/configuration/license package as an additional public-release gate. This preserves the open-source commitment without making public publication an accidental internal-pilot prerequisite.

## Downstream usability — adequate

The grouped FR-1–FR-20 sequence, standalone quality requirements, glossary, pilot table, assumptions index and owner-bound follow-ups are easy for UX, architecture and story workflows to extract. Mechanism candidates are correctly retained in the addendum rather than mandated by the PRD. Source-grounded scenarios are explicitly distinguished from tested screen journeys (§1).

The principal extraction issue is R-Q1: acceptance is a load-bearing noun throughout FR-5, the integration table and SM-4 but lacks a shared definition. Once that is resolved and the pending user choices are recorded, downstream teams can work without inventing the product's access hierarchy, installation surface or approval semantics.

## Shape fit — strong

A capability-led PRD with three concise scenarios is appropriate for this internal, multi-person development tool. The scenarios preserve the human problem without constructing unsupported detailed journeys, and the document openly routes screen/client interactions into UX after surface choices are settled. Identity, source access, knowledge lifecycle and connector uncertainty earn the additional rigor because this artifact will feed architecture and stories.

The addendum holds screenshot interpretation, component options, research limitations and implementation validation work. That separation keeps the PRD about behavior and evidence rather than turning it into an unapproved stack design. A smaller hobby-style document would lose important project-boundary requirements; a full enterprise persona or compliance apparatus would add little here.

## Mechanical notes

- FR-1–FR-20, NFR-1–NFR-6, SM-1–SM-5, SM-C1–SM-C4 and SC-1–SC-3 are contiguous and unique in their respective namespaces.
- Assumptions A-1, A-2 and A-3 each appear inline and in the assumptions index; owners and revisit conditions round-trip.
- Internal section and requirement references resolve in the reviewed text. No implementation stack is silently introduced by an addendum candidate.
- SC-1 and SC-2 have named participants. SC-3 deliberately uses an unspecified authorized promoter while promotion authority remains pending; it is a scoped acceptance scenario, not a completed user journey. Do not manufacture a named promoter before the pending policy answer.
- R-Q1 is the substantive glossary gap; otherwise the separation among ownership, access, project scope, company publication and execution authority is consistent.
- Reviewed status is `draft`; the report does not imply finalization or claim pending user choices were answered.
