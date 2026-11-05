# Journey draft 01 — laptop, metro, and colleague catch-up

Discovery draft, 2026-11-05; updated for UX-06/07. V1 execution scope is resolved: observe and deliver knowledge in Owl Mast; interact with agents in another app. No final IA, implementation, or onboarding/promotion journey is selected here.

## Evidence and labels

- **[USER CONFIRMED]** means a preference/outcome recorded in [UX memlog](../.memlog.md), UX-01–07.
- **[DESIGN PROPOSAL]** means a concrete interaction or surface to explore, not a user choice.
- **[OPEN]** means a decision or real-story detail still missing. Current questions cover knowledge delivery, promotion authority, and push interruption level; this note adds no duplicate questions.
- Inherited product constraints are cited directly to [PRD](../../../prds/prd-owl-mast-2026-11-05/prd.md); they are not new user preferences. UX-06 resolves UX-04/05's direct-action ambiguity without changing the PRD scope.
- **Ahmed** and **Mohamed** retain PRD scenario names (PRD lines 30–32); Ahmed also names the user's narrated builder journey, consistent with the Notion personal identity confirmed by the root facilitator. A configured greeting is not a separate persona. Catch-up ordering applies UX-05 to SC-1; it is not a reported usability test.

## Journey A — Ahmed goes from laptop to metro

1. **[USER CONFIRMED] Morning entry.** Ahmed opens the dedicated Owl Mast UI on a laptop to check his own work. Laptop is primary; tablet and phone must also support daily use (UX-01, UX-04).
2. **[DESIGN PROPOSAL] Orient to current work.** A working surface called “My work” keeps authorized project context visible and distinguishes items needing input from ordinary progress. **[OPEN]** Default project/company scope, ordering, and whether an RSS-like wall helps. A feed/wall is exploratory, not selected (UX-01).
3. **[USER CONFIRMED] Find what needs judgment.** Ahmed wants to identify items awaiting input, then respond in another app such as T3 Code (UX-04, UX-06). **[DESIGN PROPOSAL]** Each observed item explains the request, linked work, requester when known, and freshness. Owl Mast has no reply/dispatch control. **[OPEN]** Concrete observed request examples and source-link availability.
4. **[USER CONFIRMED] Start the next piece of work elsewhere.** New planning, building, or evaluation assignments happen in another app for V1. Direct agent interaction is a later-phase ambition (UX-06). **[DESIGN PROPOSAL]** Owl Mast exposes a permitted source link when available, without claiming to start or resume execution. No deep-link contract is established.
5. **[USER CONFIRMED] Continue during the commute.** Ahmed uses his phone for daily observation (UX-01), while the mobile reply/assignment journey is excluded from V1 (UX-06). Owl Mast's V1 phone role is observing work, receiving alerts, and inspecting evidence; another app handles responses/actions. **[DESIGN PROPOSAL]** Reentry restores the relevant authorized work context. **[OPEN]** Reading depth, connectivity behavior, and available source handoffs.
6. **[USER CONFIRMED] Push can bring attention back.** Push notifications are wanted (UX-01). **[DESIGN PROPOSAL]** A notification opens the current authorized item and shows whether the original request is still actionable. **[OPEN]** Event types, alert urgency, preview content, consent controls, and interruption preferences; no default schedule or channel beyond desired push is established.
7. **[DESIGN PROPOSAL] Climax beat.** On the phone, Ahmed understands what needs attention and can inspect the supporting evidence, then continue in the existing execution app when useful. Opening a source link is not proof of response, accepted input, resumed execution, or completed work. Owl Mast shows any later outcome only when it has new evidence.

**Known outcome, not known mechanics:** meaningful observation continuity from laptop to phone is confirmed; execution remains elsewhere. A particular web/native packaging choice does not follow from it. Tablet daily use is required but has no narrated session yet.

## Journey B — Ahmed catches up with Mohamed

1. **[USER CONFIRMED] First questions.** For the colleague catch-up use case, prioritize tickets closed, blockers, and completion percentage for tickets/epics Mohamed owns (UX-05). **[DESIGN PROPOSAL]** Ahmed enters a person-filtered work view within authorized project context. **[OPEN]** Entry point and reporting period.
2. **[DESIGN PROPOSAL] Inspect the evidence behind the summary.** Ahmed opens a ticket/epic to see the source status, ownership, observed contributors/agents, changes, blockers, and acceptance evidence. These facts are required by SC-1/FR-4–7; the summary-to-detail ordering is a proposed interaction (PRD 30, 89–118).
3. **[USER CONFIRMED] Interpret ticket completion.** Ticket percentage means completed acceptance criteria or checklist items; show **Unknown** without a measurable breakdown (UX-07). **[DESIGN PROPOSAL]** Ahmed can inspect completed/total criteria and their source/time. **[OPEN]** Epic-level aggregation when child tickets use different or absent breakdowns; do not invent a weighted rollup.
4. **[DESIGN PROPOSAL] Resolve apparent disagreement.** A closed ticket may coexist with missing acceptance evidence, a blocked dependency, or stale collection. Ahmed can inspect each fact's source rather than receiving one synthetic “done” claim (FR-5–7). Unknown observation is not proof that Mohamed or an agent is stuck.
5. **[USER CONFIRMED] Help when useful, in the existing tool.** Input/advice and pushing agents forward use another app in V1; no direct agent interaction is included in Owl Mast (UX-05, UX-06). **[DESIGN PROPOSAL]** Link to the permitted source when available. Do not invent integrated messaging or a source-app action contract.
6. **[DESIGN PROPOSAL] Climax beat.** Ahmed can explain what is closed, what is blocked, and what the available completion evidence means without asking Mohamed for a recap; he knows whether to investigate or help in the existing tool. The understanding outcome is grounded in SC-1 and SM-1 (PRD 30, 274).

## IA coverage map — working labels, not final navigation

| Requested journey / entry | Confirmed outcome or inherited need | Candidate surface and status | Missing closure |
| --- | --- | --- | --- |
| Connect agents | Claude and Codex in both projects; minimal recurrence; separate observation/delivery readiness (FR-2). | **[DESIGN PROPOSAL]** “Connected agents” with project selection and readiness detail. | **[OPEN]** A real current starting point, actual enrollment interaction, error/recovery expectations. A-5 remains provisional. |
| Understand a colleague's work | UX-05 ordering; UX-07 ticket criteria/checklist percentage; SC-1 evidence-based understanding. | **[DESIGN PROPOSAL]** “Colleague work” summary → ticket/epic detail → permitted source evidence. | **[OPEN]** Time window, entry point, epic rollup. Execution help stays external. |
| Receive useful knowledge | **[USER CONFIRMED]** Centralized knowledge readable by Claude/Codex (UX-02); scoped delivery and source version (FR-10, FR-21). | **[DESIGN PROPOSAL]** Agent delivery result plus a human-readable knowledge detail/receipt. | **[OPEN]** Real recipient session, human involvement/visibility, delivery destination, usefulness feedback. Do not imply a new replacement store. |
| Manage promotion | Automatic preferred; manual and disabled modes; exact-version publication, audience, checks, audit (FR-12). | **[DESIGN PROPOSAL]** Project promotion policy, candidate/exception detail, and publication history. | **[OPEN]** Named maintainer's real session and review needs; A-1, A-2, A-4 remain unresolved defaults. |
| Laptop-to-phone own work | **[USER CONFIRMED]** Own status, attention, mobile observation; assignment/input in another app (UX-04, UX-06). | **[DESIGN PROPOSAL]** “My work” and a focused observed request/work detail supporting reentry. | **[OPEN]** Concrete observation example, reading depth, offline expectations, available source links. |
| Push notification and reentry | **[USER CONFIRMED]** Push desired (UX-01); authorization still governs returned content (FR-17). | **[DESIGN PROPOSAL]** Consent/preferences entry, authorized notification preview, and current item detail after open. | **[OPEN]** Trigger list, preview specificity, urgency and interruption rules; no scheduling chosen. |
| External source destination | **[USER CONFIRMED]** Agent interaction stays in another app; direct interaction is later phase (UX-06). Permitted source evidence links required by FR-19. | **[DESIGN PROPOSAL]** Source detail/link in the work context when available. | **[OPEN]** Actual link/deep-link support; no handoff success or external action is presumed. |

Coverage is incomplete by design: onboarding and promotion have required outcomes but no user-narrated interaction. A feed/wall can host some candidate entries, but no evidence yet makes it the universal home or establishes an RSS protocol requirement.

## Resolved scope boundary against FR-19

| Earlier user expression | Existing requirement | Resolution / remaining boundary |
| --- | --- | --- |
| “Start new work and assign it to an agent” (UX-04). | FR-19 excludes agent launch and shell execution; FR-15 does not require an agent launcher (PRD 193, 223–227). | **[USER CONFIRMED]** Direct interaction is later phase; another app handles assignments in V1 (UX-06). No Owl Mast dispatch control. |
| “Address items needing input” and “pushing agents forward” (UX-04/05). | FR-7 forbids launch/pause/cancel/retry/merge/deploy controls; FR-19 keeps execution authority external (PRD 118, 226–227). | **[USER CONFIRMED]** Owl Mast can observe attention needs, but responses/execution occur elsewhere. No inline agent reply, resume, or action-button proxy. |
| “Give input/advice” (UX-05). | Authorized knowledge submission exists (FR-8, PRD 126–130); FR-6 does not change tracker status (110); FR-19 permits knowledge lifecycle operations (223). | **[USER CONFIRMED]** Agent input stays external. Knowledge lifecycle operations remain in scope; do not relabel an agent command or tracker mutation as knowledge submission. |
| “Continue advancing work on a phone” (UX-04). | The same FR-17/19 boundaries apply across surfaces. | **[USER CONFIRMED]** Phone reply/assignment is excluded from V1. Mobile Owl Mast observes, alerts, and exposes permitted evidence; another app such as T3 handles action. |

There is no remaining execution-scope conflict and no PRD scope change is needed. Detailed source-app linking remains unverified; offering a link cannot be described as remote dispatch or successful execution.

## Notification authorization and source-access requirements

These are consequences of extending FR-17/NFR-1 to the newly requested push surface; concrete notification design remains proposed.

- Every notification body, title, badge/count, preview, and linked detail can disclose information. Its audience must be entitled to that content; project membership or shared connector credentials alone are insufficient (PRD 191, 207–211, 249).
- Source restrictions within the same project still apply. A notification must not reveal a restricted ticket title, request text, person association, private source link, or inference-bearing summary to an unauthorized recipient (FR-17; NFR-1).
- Notification preference/operating-system permission is separate from source/project authorization. Consent to alerts grants no additional data access. **[DESIGN PROPOSAL]** Explain the intended notification use when requesting permission; denied push must not be represented as failed agent enrollment.
- Recheck current access for new disclosures and on reentry. A queued alert does not preserve permission after revocation; opening an old notification must not expose cached/derived restricted content (PRD 209–211). No claim can be made that already delivered external notification copies can be recalled.
- If a user no longer has access, avoid exposing the hidden item through its error text, counts, or fallback scope. **[DESIGN PROPOSAL]** Show a neutral unavailable destination with a route back to authorized work; do not switch silently to another project.
- Distinguish stale collection from a genuine observed blocker/request (FR-3/7). **[DESIGN PROPOSAL]** On open, indicate when an authorized request has already been resolved or changed, rather than implying the original notification is still current.
- **[OPEN]** Preview privacy on a locked device, permitted notification details, triggers, and interruptions. The product can minimize previews; it cannot assume that source permission makes every lock-screen detail appropriate.

## Progress semantics carried forward from FR-6

- Progress must show its **scope, denominator, and observation time**. Added/removed work must change the denominator visibly (PRD 106–109). The reporting period for closed tickets remains open under UX-05.
- **[USER CONFIRMED]** Ticket percentage uses completed acceptance criteria or checklist items; show **Unknown** when no measurable breakdown exists (UX-07). No agent estimate or status-to-number mapping may substitute for that basis. **[OPEN]** Epic rollup across heterogeneous/unknown child breakdowns.
- Source-reported or inferred dependencies must be distinguishable. A blocked item needs supporting evidence or an unverified label (PRD 109).
- Tracker closure, merged contribution, passing checks, acceptance, and deployment are separate facts (FR-5, PRD 102). Completed subtasks do not establish parent acceptance (FR-6, 110).
- Source and collection timestamps are distinct; partial/unknown/stale observation cannot appear complete (NFR-2, 250; FR-3, 82–83).
- “Owned by Mohamed” is not causal credit for every contribution. Keep owner, initiator, executing agent, delegation, and repository identity distinct where available (FR-4, 91–94). Ticket closures/percentages are not a personal productivity score (UX-05).
- **[DESIGN PROPOSAL]** Make completed/total items and their evidence inspectable from a percentage label; pair the summary with coverage/freshness. **[OPEN]** If both acceptance criteria and another checklist exist or conflict, define which measurable source governs rather than silently combining them.
