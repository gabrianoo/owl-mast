---
name: Owl Mast
description: Draft behavior and journey contract for observing work and delivering scoped knowledge.
status: draft
updated: 2026-11-05
visual_identity: DESIGN.md
decision_log: .memlog.md
sources:
  - ../../prds/prd-owl-mast-2026-11-05/prd.md
  - ../../prds/prd-owl-mast-2026-11-05/addendum.md
  - ../../prds/prd-owl-mast-2026-11-05/.memlog.md
  - ../../prds/prd-owl-mast-2026-11-05/review-disposition.md
  - ../../briefs/brief-owl-mast-2026-11-05/brief.md
  - ../../briefs/brief-owl-mast-2026-11-05/addendum.md
  - ../../briefs/brief-owl-mast-2026-11-05/.memlog.md
  - ../../research/competitive-owl-mast-dashboard-references-2026-11-05/research.md
  - https://app.notion.com/p/40e8ce657080814ca0fdf40e67a36e8b
  - imports/manifest.md
---

# Owl Mast — Experience

## Foundation

**Draft, not a finalized specification.** [DESIGN.md](DESIGN.md) owns visual identity; [.memlog.md](.memlog.md) is the canonical discovery record. Source authority and exact inherited assumptions are available in the [PRD extraction](.working/source-prd.md) and [brief/reference extraction](.working/source-brief-references.md). Later user decisions resolve execution, ticket percentages, demand-driven knowledge, promotion authority, and every-update push. The latest user addition requires a separate Focus board and concurrent epic visibility.

| Label | Meaning |
|---|---|
| **[U]** | User-confirmed requirement or decision in the memlog and current discovery replies. |
| **[R]** | Requirement inherited from the finalized PRD; not a claim that the user selected its UI. |
| **[D]** | Visual decision made under the user's explicit delegation; recorded in DESIGN.md. |
| **[P]** | Designer proposal for review. Unless marked [U]/[R]/[D]/[A]/[OPEN], this draft's interactions, surfaces, defaults, and scenario steps are [P]. |
| **[A-n]** | Unconfirmed upstream PRD assumption; exact text, owner, and revisit condition remain unchanged. |
| **[OPEN]** | A remaining bounded dependency; no implementation capability is claimed without evidence. UX-Q1–3 are resolved. |

**[U]** Dedicated Owl Mast UI; laptop primary, tablet and phone supported; push desired (UX-01). Central knowledge must be readable by Claude and Codex (UX-02). **[U/R]** V1 observes work and delivers knowledge. Agent assignment, chat replies, launch/pause/cancel/retry, shell, merge, and deployment remain in existing tools such as T3 Code (UX-06; FR-19). A source link is navigation, never an action proxy.

**[R]** Open source and AISQUAD first; demonstrate both client types in both projects. Preserve Notion and Hermes-to-Notion learning; known page writing and unverified skill reading are separate capabilities. No UI framework, browser/PWA/native packaging, storage technology, or integration mechanism is selected. Initial administrator work may be complex; recurring enrollment must be minimal. The internal pilot handles permission-sensitive project/source data; no regulated-sector certification is asserted.

**[U]** Agents search for knowledge when needed; no default automatic context injection or human-selected sending (UX-08). Project-designated maintainers handle promotion exceptions/manual review, including the user when authorized (UX-09). Every observed work update triggers push by default and remains in the feed (UX-10). Focus is a separate assigned-work board with visible aggregation/stacking of concurrent epics; it does not replace the landing page.

## Information Architecture

**[P] Proposed structure:** Daily Work, Focus, Knowledge, Connections, and Usage are primary destinations. Promotion is within Knowledge; administrator setup is within Connections; Preferences is a utility destination. Work/evidence and knowledge detail are contextual destinations. Company context is an explicitly selected authorized aggregate, not an automatic cross-project default. First entry asks for an authorized project; subsequent entry proposes restoring the last still-authorized project. Daily Work/notifications cover authorized connected project work with visible scope controls; do not silently restrict them to the viewer's assignments. Focus defaults to assigned-to-me work.

| ID / surface | Entry and purpose | Journey / coverage |
|---|---|---|
| S1 Daily Work · [visual](mockups/daily-work.html) | Open Owl Mast; own/colleague filter, closures, attention, progress, recent updates, coverage. Feed versus wall remains unchosen. | J1, SC-1, J7; FR-4–7/15/17 |
| S2 Work and evidence detail · [visual](mockups/work-detail.html) | From work/attention/update; ticket or epic → runs → contributions → acceptance evidence; prerequisites/dependents in a readable list. | J1, SC-1, J7; FR-4–7/19 |
| S3 Knowledge · [visual](mockups/knowledge.html) | Scoped catalog/search, lifecycle filters, permitted submission, Notion lineage. Company-approved knowledge clearly carries its scope. | SC-2, SC-3; FR-8–10/14/21 |
| S4 Knowledge detail and delivery history · [visual](mockups/knowledge-detail.html) | Exact version, applicability, evaluation, conflicts, origin, permitted evidence, recipients, and lifecycle history. | SC-2, SC-3; FR-8–14/21 |
| S5 Connections and agent enrollment · [visual](mockups/connections.html) | Existing Claude/Codex clients, authorized project selection, independent observation and delivery readiness, recovery guidance. | J2, SC-2; FR-1–3/14/21 |
| S6 Promotion · [visual](mockups/promotion.html) | Per-project policy, manual reviews/automatic exceptions, exact publication preview, allowed audience, checks, history, withdrawal/supersession. | SC-3; FR-9/12/13/17 |
| S7 Usage · [visual](mockups/usage.html) | Project/company measurement, period, source coverage, supported client/model/agent/person/session/work attribution, estimate basis, unassigned portions. | J6; FR-16/17 |
| S8 Administrator setup · [visual](mockups/administrator-setup.html) | Separate source accounts/projects, capabilities, authorization, collection/retention policy, secret-free setup guidance. | J2; FR-1–3/18/20 |
| S9 Preferences and notification return · [visual](mockups/notifications.html) | Push consent/category choice and theme; notification reentry leads to the current authorized detail. | J7; UX-01, FR-17 |
| S10 Focus · [visual](mockups/focus.html) | Separate board for work assigned to Ahmed; stacked epic groups or a combined view, observed source status, concurrent agent contributions. | J8; latest user Focus request, FR-4–7/15/19 |

The proposed IA covers every required outcome, including the separate Focus board. A dependency graph is optional exploration within S2, not a required primary destination. The [daily-work study](mockups/daily-work.html) covers S1 and inline portions of S2; the [Focus study](mockups/focus.html) covers S10 and additional inline S2 evidence. These illustrative studies do not prove source integration, permissions, or full detail navigation. The user requested visual references for every surface (UX-14); each row links its screen. These are layout references with illustrative data and disabled source actions, not completed integrations. [Browse all visual references](mockups/gallery.html).

## Voice and Tone

Plain, specific, and evidence-aware. Brand voice lives in DESIGN.md. Use the state the source supports; omit inaccessible identities and details, including from error text. UI messages identify what happened and the useful next step without connector internals or alarming jargon.

| Say | Meaning preserved |
|---|---|
| “2 of 4 acceptance criteria complete · 50%.” | Measured ticket basis; source and observation time are available beside it. |
| “Progress unknown — no measurable breakdown.” | Not zero; not an estimate from agent activity. |
| “3 of 5 child tickets closed. Acceptance not recorded.” | Epic closure and parent acceptance stay separate. |
| “Observation ready. Knowledge delivery not verified.” | A connected agent is not proof that skills were read. |
| “Delivered to Codex. Useful reuse not yet verified.” | Receipt is not effectiveness. |
| “No matching knowledge in this authorized scope.” | Empty result only when scope/authorization succeeded. |
| “This item is unavailable. Return to your work.” | Safe denied/revoked destination without leaking its existence or title through detail. |
| “Last successful collection: … Current coverage is incomplete.” | Missing telemetry does not mean an agent is stuck. |

## Component Patterns

Visuals are in DESIGN.md.Components. These names are shared contracts, not a chosen implementation library.

| Component | Behavioral contract |
|---|---|
| `brand-mark` | Decorative beside visible Owl Mast text; hide duplicate graphic naming from assistive technology. If the combined identity is a home link, give it one descriptive name and normal keyboard/link behavior. |
| `scope-bar` | Persist project/source identity and period across summary/detail. Changing scope reauthorizes and resets incompatible filters; never silently substitutes another project. |
| `surface-navigation` | Announce destination and current selection; retain safe return location and filters. Hide unauthorized administration without exposing hidden work counts. |
| `work-summary` | Selecting a count opens its underlying permitted records with the same period/basis. Count authorized data only; show partial coverage. No individual productivity ranking. |
| `attention-item` | Open observed request/blocker/review evidence. Explain source, requester if known, age, and current state. No inline reply or execution control. |
| `progress-evidence` | Expand completed/total criteria or child set with source/time. Read-only; no tracker checkboxes, edits, or synthetic percentage for unknown work. |
| `work-record` | Open S2; distinguish owner, initiating person, executing agent, delegation, and repository identity. Unknown/inferred links remain labeled and inspectable. |
| `ticket-chip` | A labeled ticket reference opens its authorized S2 detail; source qualification disambiguates duplicate keys. Read-only tags do not masquerade as controls. |
| `agent-chip` | Show an editable owl display name/color with fixed provider/type icon and label. Underlying client/run identity remains inspectable; aliases never merge records, change permissions, or rename source/provider objects. Proposed S5 appearance settings are personal display preferences, reused across this viewer's surfaces; shared naming authority remains unspecified. |
| `focus-board` | Assigned-to-me work by default. Switch epic-grouped/combined presentation without changing source ownership or status; filters remain visible. No drag-to-reassign, status mutation, or agent execution controls. |
| `epic-group` | Group by explicit source epic relation; show simultaneous agent contributions across epics. Shared/unlinked/unknown records retain distinct labels. Combined unique-record totals deduplicate the same work/run rather than summing appearances. |
| `evidence-detail` | Expand source facts and correlation basis; preserve ambiguous/unlinked evidence. Acceptance names its approving authority or configured source rule and referenced artifact; missing authority cannot imply verified acceptance. Provide permitted source links. Dependencies distinguish explicit links from inference. |
| `activity-list` | Filter by authorized event type/person/period. Preserve reading position during new arrivals; offer “New updates” rather than moving rows under focus. Use bounded pages/load-more. |
| `knowledge-record` | Open exact version; submission records origin/scope/applicability. Distinguish human-reviewed from automatically evaluated guidance, showing evaluator or policy, basis, evaluated version, and time. Candidate submission does not approve or publish. Duplicate detection links to existing lineage. |
| `delivery-receipt` | Show available/retrieved/delivered/reused separately with observed evidence; show recipient/project/version/time only when authorized. Never infer use from reading. |
| `connection-readiness` | Present observation and delivery independently per client/project. Explain permission, unsupported capability, and unverified reading separately; no launch test. |
| `promotion-review` | Project-designated maintainers inspect exact candidate content/version and permitted audience before a manual decision [U: UX-09]. Recheck authority, policy, and version; changed content invalidates stale approval. Designation does not grant source access. |
| `usage-breakdown` | Offer supported project, client, model, agent, person, session, and work-item breakdowns. Compact ticket/epic summaries open the same scoped S7 detail. Filters preserve units/period/coverage; chart/table drill-down retains unassigned and unpriced records. Deduplicate shared usage in epic totals; ambiguous allocation stays unassigned. Unavailable attribution is labeled, never guessed. Costs never collapse distinct measurement classes or currencies. |
| `settings-field` | Save permitted settings explicitly with visible outcome; validate near the field. Policy changes show effects on pending/new publication; existing-publication behavior remains A-4. |
| `state-message` | Distinguish empty/loading/failure/offline/denied/stale/unsupported; give authorized recovery only. Important failures persist beside affected content. |
| `action-control`, `action-control-dark` | Same behavior in both themes. Explicit permitted knowledge/admin action; prevent duplicate submission while pending and show actual completion/failure. No optimistic publication. |
| `external-link` | Identify destination; navigation only. Missing/unsupported link is explained. Returning does not imply external action succeeded; await new source evidence. |

## State Patterns

The following baseline applies to **every S1–S10 surface**: cold-load shows labeled loading without placeholder numbers; keyboard focus stays visible and returns to the trigger after detail closes; expired/revoked access removes restricted data and uses neutral unavailable copy; authorization that cannot be checked fails closed. Offline means no newly disclosed protected content and no queued knowledge publication/admin writes. No offline sensitive-browsing capability is promised. Reconnect rechecks access before refresh. Source timestamps and collection timestamps remain distinct.

| Surface | Empty / first use | Error / stale / unsupported | Permission / offline specialization |
|---|---|---|---|
| S1 Daily Work · [visual](mockups/daily-work.html) | No authorized work, no matches, and no connected coverage are different messages. First use routes to authorized project/enrollment. | Keep valid data from healthy sources; label stale sections and incomplete totals. Unsupported telemetry never becomes zero. | No hidden-source counts or person associations; offline cannot masquerade as a live all-clear. |
| S2 Work/evidence | “No linked evidence” differs from “No matching records.” Unlinked activity remains findable. | Missing checklist → Unknown; stale checks retain source time; unsupported evidence type identified without a guessed result. | Denied source preview is not replaced with cached text or a cross-project record. |
| S3 Knowledge · [visual](mockups/knowledge.html) | Empty catalog and no relevant result are distinct from failed scope validation. | Submission failure retains only authorized unsent content in the current view; sync conflict does not overwrite newer source knowledge. | No default cross-project search fallback; offline submission is not represented as saved. |
| S4 Knowledge detail/history | No deliveries is not unavailable collection; no verified reuse is an explicit state. | Conflicting/superseded/withdrawn/version-unknown content carries lifecycle state; delivery capability unsupported is not no recipients. | Audit and recipient visibility checked separately; no inaccessible origin excerpt. |
| S5 Connections/enrollment | No clients prompts enrollment; no authorized projects gives safe access guidance. | Partial readiness, expired authorization, stale observation, unavailable client path, and unverified skill reading have separate reasons. | Membership does not prove source access; no protected readiness result from unverifiable cached rights. |
| S6 Promotion · [visual](mockups/promotion.html) | No eligible candidates, no reviews, and disabled policy are distinct. | Failed/uncertain safety checks keep project scope; changed version/policy requires reevaluation. No silent automatic retry under an obsolete mode. | Denied policy/review action is not shown as pending success; offline publication unavailable. |
| S7 Usage · [visual](mockups/usage.html) | No observed usage differs from unsupported/unpriced/unassigned/incomplete data. | Missing categories are unavailable; stale totals show period and coverage. Estimates show pricing source/date and basis. | Aggregate only authorized records; no invisible-source residual that discloses hidden usage. |
| S8 Administrator setup · [visual](mockups/administrator-setup.html) | Unconfigured project shows prerequisites and supported boundaries. | Each connector can fail independently; safe diagnostics identify remediation without credentials. Unsupported host/client capability labeled. | Only authorized administrators see configuration; permissions required are explained without requesting secrets in ordinary text. |
| S9 Preferences/return | Push not requested/denied/unsupported are independent of agent health. | Save failure retains visible unsaved choice; old notification opens latest authorized state, including already-resolved attention. | Revalidate on open; revoked target returns neutral unavailable, no title in error. Offline return cannot reveal protected cached detail. |
| S10 Focus · [visual](mockups/focus.html) | No assignments, no matches, and no observed epic mapping are distinct; ungrouped work stays visible. | Stale source status remains labeled; unsupported agent-to-epic mapping is Unknown, not inactivity. Shared records are not duplicated in aggregate totals. | Apply S1/S2 access rules to each group/card and count; offline cannot imply the board is current. |

## Interaction Primitives

- Use click/tap and standard keyboard controls. Every expandable detail has a labeled trigger, announced expanded state, and predictable focus order. Escape closes the top temporary layer; no stacked dialogs.
- Navigation and filters are read-only. Pending knowledge/admin writes disable duplicate activation, preserve applicable context, and report actual success or a safe error; retries recheck permission/version. Do not turn a failed mutation into success by clearing the form.
- Project changes, deep links, searches, notification previews, and exports if later added all preserve source-level authorization. Retained filters never grant access or disclose restricted labels.
- Proposal: show the reporting window explicitly and start with “Today” in the viewer's timezone; permit a custom period. This is not a confirmed reporting preference. Exact source timestamps remain inspectable with timezone.
- No drag requirement, hover-only action, auto-playing media, or mandatory keyboard shortcut. Selection, copy, and ordinary scrolling remain native. A source link opening is not proof of work advancement.

## Accessibility Floor

**[P] Target:** [WCAG 2.2 AA](https://www.w3.org/TR/WCAG22/) for the chosen UI surface; implementation verification follows architecture. Visual contrast and exact tokens live in DESIGN.md. All functions work with keyboard, touch, and screen reader, with labels and state announcements independent of color.

- Use semantic headings, lists, tables, form labels, and landmarks; provide a skip-to-content route and logical focus order. Charts/relationships have equivalent labeled lists/tables.
- Text zoom to 200% and reflow at 320 CSS px must preserve essential content/actions. Use `{typography.body}` for reading, `{typography.row}` for compact lists, and minimum `{spacing.control-target}` hit areas. Focus must not be covered by sticky UI.
- Announce meaningful loading/result/error changes politely; do not announce each incoming event or move focus on refresh. Validation identifies the failing field and remedy.
- Respect reduced motion; disable nonessential transitions. Unknown progress exposes a text state, not a false progressbar value. Permission and stale states remain understandable without color.
- Phone and tablet layout must survive enlarged text and landscape. Critical operations do not depend on precise gestures; confirmation describes the affected version/audience, not just “Are you sure?”

## Responsive & Platform

**[U]** Laptop, tablet, and phone daily use. **[P]** One consistent navigation vocabulary and account/project context across sizes; browser/PWA/native choice remains an architecture input because push support and enrollment routes must be validated, not assumed.

| Layout width | Proposed behavior |
|---|---|
| ≥1024px | Labeled navigation rail; main area can use two columns. S2 detail can preserve the surrounding work context. |
| 600–1023px | Labeled navigation menu; flexible panel pairs only when readable. Evidence can expand to full width. |
| <600px | Single column; summary → attention → work/progress → updates/coverage. S2/S4/S6 detail uses full width with explicit Back. |

Mobile V1 supports observation, alerts, and evidence. Replies/assignments belong in another app (UX-06). The visual references demonstrate the layouts; these spine rules govern implementation and take precedence over prototype deviations. Theme follows system with override **[D]**. Offline operation, installability, background behavior, and rich notification actions are not promised. No schedule/digest has been chosen. English microcopy is the working draft language; localization markets and translated content behavior are not established.

## Evidence, progress, and knowledge semantics

**[U/R] Ticket progress:** completed acceptance criteria/checklist items ÷ measurable items, with numerator, denominator, basis, source, and observation time. No breakdown → **Unknown**. No measurable items also → Unknown, not 0%/100%. Changed criteria visibly change the denominator. If criteria and another checklist disagree, show both labeled measures or “Basis needs review”; do not silently combine them.

**[P/R] Epic progress:** show source-scoped closed child tickets ÷ known in-scope child tickets, explicitly labeled **child tickets closed**, with coverage and changes to the child set. This is a proposed representation, not user-confirmed acceptance semantics. Never average heterogeneous ticket percentages. Unknown/incomplete child scope prevents a complete-looking rollup. Parent acceptance stays a separate sourced fact. Closures are events in the selected period, not credit for all work performed by the owner.

**[R] Evidence:** keep tracker closure, merged contribution, checks-passed/skipped/not-run, acceptance, and deployment separate. Label source fact, confirmed mapping, inference, estimate, and unknown. Preserve explicit versus inferred dependencies; do not convert stale collection into a blocker or infer initiator from commit author/credential alone (FR-4–7).

**[R] Knowledge:** project scope by default. Exact versions carry origin, scope, applicability, evaluation, freshness, and permitted references. Candidate/approved/conflicting/superseded/withdrawn are distinct. “Available” means eligible in scope; “retrieved” means a read is observed; “delivered” means receipt is observed; “demonstrably reused” needs task evidence and human verification. Truncation/omission is visible without revealing restricted content. Preserve Hermes → Notion; no duplicate save, bulk migration, or silent overwrite. Existing Notion page creation never proves skill reading, approval, promotion, or reuse.

**[R] Promotion:** automatic is the preferred mode, with manual-approval and disabled available per project. A mode is not a license to widen source permissions. Evaluate a specific version for an explicitly permitted company audience; failed/uncertain checks retain project scope. Mode/version changes invalidate pending publication under the former conditions. Withdrawal cannot erase external clients' earlier copies/actions; recheck eligibility before future delivery and withhold if unverifiable. Detailed defaults remain A-1/A-2/A-4.

**[R] Usage:** separate observed units, API-equivalent estimates, subscription allocation, and actual bills. Show period, source coverage, unknown/unassigned/unpriced portions, attribution basis, and estimate price/date. No token count, closure count, or retrieval count is an individual productivity/ROI score.

**[U] Identity presentation:** the user requests ticket/agent chips, customizable owl agent names/colors, and an agent-type icon. **[P]** Keep appearance settings in S5 as personal aliases with an accessible color palette; enforce readable text/marker contrast, retaining a fixed type label and original identity in evidence. Owl names in mocks are illustrative. Styling a record never establishes agent attribution.

**[P] Contextual cost presentation:** full analysis remains S7; ticket and epic views include a compact Usage & cost summary with a labeled measurement class and scoped drill-down. An amount requires supported attribution, currency, period, coverage, and its estimate/allocation/billing basis. Epics aggregate distinct attributable records once; they never sum duplicated shared runs. Jira or repository metadata alone does not prove agent consumption or cost. No linked measurement means Unavailable, not zero; this proposal responds to the user's request to make costs discoverable on work.

## Inspiration & Anti-patterns

- ConvaDesk concepts retained: scoped overview, attention separated from progress, work-to-evidence drill-down, dependency inspection, and honest usage attribution. [Ticket detail](imports/IMG_AB4D1C8F3C45-1.jpeg), [dependencies](imports/IMG_A9CC932E588C-1.jpeg), and [overview](imports/IMG_EF516651E585-1.jpeg) ground these concepts; dense graphs do not become a phone requirement.
- [Usage summary](imports/IMG_BC54BCBE01C2-1.jpeg), [attribution table](imports/IMG_3626EBD8C28F-1.jpeg), and [continuation](imports/IMG_DE187537BF11-1.jpeg) preserve measurement scope and unassigned work. Their figures are not pilot facts. [Manifest](imports/manifest.md) identifies the supplied inputs.
- Ponytail informs visual restraint as documented in DESIGN.md; activity streaks and token totals do not define Owl Mast's success. T3's two-agent setup is an experience reference; exact enrollment mechanics remain unverified. Owl Mast does not copy its execution interface.
- Avoid one synthetic “done” status, invented progress, equal treatment of no data and zero, silent cross-project search, hidden permissions inside counts, and new manual recaps to make learning transferable.

## Key Flows

Named actors mirror the PRD. **Ahmed and Mohamed are scenario participants, not assumed current access-role holders.** Any administrator/maintainer step below is conditional on verified authorization. Illustrative lesson/work names are fixtures. All interaction details are [P] unless tied to [U]/[R]; none describe a completed pilot test.

### J1 — Ahmed checks his work before leaving home

1. Ahmed opens the dedicated UI on his laptop and enters/restores an authorized project (S1).
2. He sees his work status, observed attention needs, and progress basis with current collection coverage [U: UX-04/06/07].
3. He opens an attention item in S2, reads the request, provenance, and time, and checks whether it is still current.
4. **Climax:** he understands what needs his judgment and has sufficient permitted evidence to continue in T3 or another existing tool. Owl Mast exposes no reply/assignment control [U: UX-06].
5. Later, he can inspect the same authorized context on his phone; new source evidence, not opening an external link, updates the observed outcome.

Failure: source collection is stale → label the gap, keep healthy authorized evidence available, and avoid claiming work is blocked or resolved. Lost access/offline → S2's safe unavailable state.

### SC-1 — Ahmed understands Mohamed’s work.

1. Ahmed chooses Mohamed within an authorized project and explicit reporting period in S1.
2. He reads tickets closed, blockers, and completion percentages for Mohamed's tickets/epics, in that priority [U: UX-05].
3. In S2, he expands the criteria behind a ticket percentage; missing measurable breakdown shows Unknown [U: UX-07]. Epic closure basis is labeled separately.
4. He follows work → runs → contributions → acceptance evidence, inspecting owner/initiator/agent mappings and explicit versus inferred dependencies [R: FR-4–7].
5. **Climax:** Ahmed can explain what is closed, what is blocked, and what the progress evidence establishes without asking Mohamed for a recap. Advice or agent instructions occur in the existing tool.

Failure: contradictory status/acceptance, ambiguous attribution, or stale evidence remains visible as separate facts. S1 summary cannot erase S2 uncertainty; permission-denied evidence reveals no hidden record detail.

### J2 — Ahmed prepares the workspace and connects existing agents (supports SC-2)

1. When authorized as administrator, Ahmed opens S8 and records project/source boundaries, supported capabilities, and safe setup prerequisites [R: FR-1/18/20].
2. He distinguishes **Syntelligence → its Jira + GitHub** from **Movesion → its separate Jira + Bitbucket**. Duplicate keys/names retain account/site and project identity.
3. He reviews collection/retention permissions; A-3 remains unresolved before live ingestion. No source credential is pasted into ordinary knowledge or diagnostic text.
4. As an authorized contributor, Ahmed enrolls existing Claude and Codex clients through S5. **[A-5]** Proposed recurrence: one client connection/profile, authorized project selection, readiness; routine sessions reuse enrollment. Exact commands/mechanism are deferred.
5. **Climax:** he can see observation readiness and knowledge-delivery readiness independently for each client in each project, including unverified Notion skill reading. One green connection cannot stand for all four client/project combinations.

Failure: a Movesion source failure does not invalidate healthy Syntelligence data; unsupported client capability gives safe remediation rather than a successful badge. Do not relabel the required second project/client as optional.

### SC-2 — Ahmed’s next agent receives useful learning.

1. Mohamed's work produces a sourced lesson; existing Hermes → Notion capture or authorized Claude/Codex page creation preserves its origin in S3/S4 [R: FR-8/14/21]. An explicit Owl Mast submission, if used, captures project, origin, applicability, and evidence without duplicating an existing save.
2. S4 distinguishes the candidate from approved knowledge, preserves duplicate lineage, and shows conflict/evaluation/version. Default delivery eligibility remains **A-1**.
3. Ahmed's enrolled agent has explicit authorized project context and **searches for knowledge when it needs it [U: UX-08]**. The default is agent-initiated retrieval, not automatic injection or a human selecting every delivery.
4. Through the selected validated path, the agent receives applicable permitted knowledge with item/version, scope, source, freshness, and any truncation/omission [R: FR-10]. Notion skill discovery and reading are demonstrated separately from page creation.
5. S4 records available/retrieved/delivered states with observed evidence. Ahmed can inspect a receipt without storing a complete conversation.
6. **Climax:** a task artifact and human verification show the lesson helped Ahmed's next task without a copied recap. Only then record demonstrable reuse [R: FR-11]; A-6's minimum sample size remains provisional.

Failure: no matching knowledge → honest empty result; failed scope/authorization → no delivery; conflicting/stale/withdrawn knowledge → lifecycle treatment with A-1/A-2 clearly provisional. Never fill a gap with another project's content or overwrite newer Notion knowledge silently.

### SC-3 — Mohamed's reusable lesson reaches the other project.

1. Mohamed's lesson begins project-scoped. A **project-designated maintainer [U: UX-09]**, represented by Ahmed when authorized, opens S6 to handle exceptions or manual review. This scenario does not grant Ahmed permissions.
2. The selected project mode is automatic, manual-approval, or disabled [R: FR-12]. Automatic evaluates a version; manual requires authorized approval; disabled does not publish a new version.
3. S6 shows the exact proposed company-safe content, permitted audience, originating version, policy, checks, and rationale. Restricted source details are absent from the wider payload.
4. In automatic mode, passing required checks permits publication under policy; failed/uncertain cases stay project-scoped and enter the authorized exception view. In manual mode, a reviewer decides on that exact evaluated version. Changes require reevaluation.
5. **Climax:** Ahmed's authorized agent in the other project receives the explicitly permitted published knowledge without receiving restricted original evidence [R: FR-12/17]. S4 records delivery separately from reuse.
6. A maintainer can inspect history, supersede or withdraw a version, and see earlier deliveries subject to permissions. Explain that external past copies/actions cannot be erased; current delivery eligibility is checked again [R: FR-13].
7. Changing mode prevents pending publication under the previous mode. Disabling is not silently portrayed as revoking old publications: existing-version behavior is **A-4**; withdrawal/quarantine details are **A-2**.

Failure: revoked rights, a changed candidate, a changed policy, unverifiable eligibility, or failed publication prevents a success claim. The UI identifies the safe next review action and retains an authorized audit trail.

### J6 — Ahmed checks what observed usage means

1. From an authorized project/company scope, Ahmed opens S7 and sets the period and supported client/model/agent/person/work filters.
2. He sees which measurement classes are observed, estimated, allocated, billed, or unavailable; coverage and unassigned portions accompany totals [R: FR-16].
3. He opens a source/session/work breakdown, retaining price/date for estimates and correlation basis for attribution.
4. **Climax:** he can state what was measured and what remains unknown without mistaking token volume or an API-equivalent estimate for a bill or productivity score.

Failure: incomplete/unsupported collection remains unavailable rather than zero. Hidden-source usage is not exposed through aggregate differences. An unassigned record remains unassigned until supported evidence exists.

### J7 — Ahmed returns from a phone notification

1. Ahmed opens S9 and requests push; explain the purpose before asking operating-system permission. **Every observed work update triggers push by default [U: UX-10]** across the authorized connected project scope, not only his assignments. Visible controls can change his follow/notification scope; permission remains unchanged.
2. Proposal: use a generic lock-screen preview such as “Owl Mast has an update” until he opens it. The recipient's current project/source rights are checked before any notification disclosure; push permission grants no extra content access.
3. Ahmed opens the notification. Recheck current access and load the relevant S2/S4/S6 destination with current source state; suppress an unauthorized or obsolete sensitive preview.
4. **Climax:** he understands the current permitted event on his phone and can inspect evidence; action, if needed, remains in another app. A resolved request says it has changed rather than urging an obsolete response.

Failure: denied/unsupported push leaves in-app observation usable. Revoked access gives neutral unavailable; offline does not expose protected cached content. Deduplicate replay of the same source event, but do not silently throttle distinct updates or replace them with a digest. Platform delivery constraints must be disclosed; push arrival is not guaranteed. Already delivered external notification copies cannot be promised recall. No digest schedule or external messaging is created by this specification.

### J8 — Ahmed focuses on his assigned work across several epics

1. From the landing page, Ahmed opens the separate Focus board (S10), showing work assigned to him within his authorized project scope [U: latest Focus request].
2. He sees stacked epic groups, each with source-qualified work, measured progress, blockers, and observed agent activity. These grouping mechanics are a designer proposal; the need to see concurrent epics is confirmed.
3. He expands two epics where Claude and Codex are contributing simultaneously. An agent may appear in several groups; shared or unknown attribution remains labeled, and a combined total counts unique supported records rather than appearances. Whole-epic context distinguishes the epic's permitted child set from Ahmed's assigned-ticket subset. An unlinked run appears in his personal context only with confirmed association to him, such as an explicit initiating-person record.
4. He can switch to a combined view to inspect all assigned work, then open a work record in S2 for its evidence. Source statuses remain read-only; no dragging changes assignments/status or directs an agent.
5. **Climax:** Ahmed can see the state of his parallel work and the evidence requiring attention without mistaking the landing feed for his board. Any execution decision continues in the existing tool.

Failure: missing epic/agent mapping leaves work in an explicit ungrouped/unknown section; stale collection cannot imply idle agents or complete epics. Permission-filtered groups never reveal hidden titles or counts.

## Open decisions and inherited assumptions

| Resolved UX question | Confirmed decision |
|---|---|
| **UX-Q1 / UX-08 — knowledge entry** | The agent searches when it needs knowledge. This does not resolve A-1 eligibility, select storage, or authorize execution. |
| **UX-Q2 / UX-09 — promotion authority** | Project-designated maintainers handle exceptions/manual review; source access and publication authority remain separate. |
| **UX-Q3 / UX-10 — push interruption** | Every observed work update triggers push by default. No silent attention-only substitution or digest. Actual platform delivery remains to be validated. |

Original **A-1–A-6 remain unconfirmed**. Their exact semantics, owner, and revisit condition are in the [source extraction](.working/source-prd.md#exact-tagged-assumptions--remain-proposals), original [PRD assumptions index](../../prds/prd-owl-mast-2026-11-05/prd.md), and [.memlog.md](.memlog.md); this draft does not replace them. A-1 concerns default delivery eligibility; A-2 withdrawal/quarantine; A-3 collected-content defaults; A-4 existing publications after disabling promotion; A-5 enrollment step ceiling; A-6 minimum proof cases.

Bounded refinements remain designer proposals: exact Daily Work/feed layout, Focus grouping/combined presentation, reporting-period default, epic child-closure representation, and generic notification previews. These do not reopen confirmed needs. Architecture must validate packaging/push support, source-app links, and real client enrollment/delivery paths; pre-live/acceptance owners must revisit A-1–A-6 at their stated checkpoints. No missing implementation evidence becomes a capability promise. All four review lenses are selected on Claude Opus 5.5 Ultrathink; review and final polish remain. Input reconciliation is complete and all surfaces have visual references. The additional live-data sample is separate from these illustrative references and does not establish pilot success.
