---
name: Owl Mast
description: Behavior and journey contract for observing work and delivering scoped knowledge.
status: final
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
  - imports/ai-native-sdlc-playbook.pdf
---

# Owl Mast — Experience

## Foundation

**Final UX planning contract.** [DESIGN.md](DESIGN.md) owns visual identity; [.memlog.md](.memlog.md) is the canonical discovery record. Source authority and exact inherited assumptions are available in the [PRD extraction](.working/source-prd.md) and [brief/reference extraction](.working/source-brief-references.md). Component and state tables use terms defined in the semantics section after Responsive & Platform; remaining proposals and dependencies are in the final section.

**Post-review amendments — UX-18–UX-24:** the user added run evidence, skill/memory statistics, full-system audit, kanban, dependency graph and connection location after the completed review round. These additions preserve observation-only V1 and A-1–A-6; prior review conclusions do not validate them. The user-supplied playbook resolves the six kanban stage labels; source mappings remain to be validated.

| Label | Meaning |
|---|---|
| **[U]** | User-confirmed requirement or decision in the memlog and current discovery replies. |
| **[R]** | Requirement inherited from the finalized PRD; not a claim that the user selected its UI. |
| **[D]** | Visual decision made under the user's explicit delegation; recorded in DESIGN.md. |
| **[P]** | Designer proposal for review. Unless marked [U]/[R]/[D]/[A-n]/[OPEN], this contract’s interactions, surfaces, defaults, and scenario steps are [P]. |
| **[A-n]** | Unconfirmed upstream PRD assumption; exact text, owner, and revisit condition remain unchanged. |
| **[OPEN]** | A remaining bounded dependency; no implementation capability is claimed without evidence. |
| **[U/R]**, **[P/R]**, **[D/P]** | The passage combines both kinds of source; its sentences identify the confirmed, inherited, delegated, or proposed part. |
| **[U: UX-n]**, **[R: FR-n]** | The tag cites the decision or requirement. |

**[U]** Dedicated Owl Mast UI; laptop primary, tablet and phone supported; push desired (UX-01). Central knowledge must be readable by Claude and Codex (UX-02). **[U/R]** V1 observes work and delivers knowledge. Agent assignment, chat replies, launch/pause/cancel/retry, shell, merge, and deployment remain in existing tools such as T3 Code (UX-06; FR-19). A source link is navigation, never an action proxy.

**[U]** Agents search for knowledge when needed; no default automatic context injection or human-selected sending (UX-08). Project-designated maintainers handle promotion exceptions/manual review, including the user when authorized (UX-09). Every observed work update triggers push by default and remains in the feed (UX-10). Focus is a separate assigned-work board with visible aggregation/stacking of concurrent epics; it does not replace the landing page (UX-11, UX-12).

**[U: UX-18]** Tickets expose model name, effort for each task role, session ID, input/output tokens, and the machine/sandbox name that executed the task. Ahmed uses three T3 Code machines and load balances between them; Owl Mast observes their contributions without choosing or routing execution.

**[R]** Open source and AISQUAD first; demonstrate both client types in both projects. Preserve Notion and Hermes-to-Notion learning; known page writing and unverified skill reading are separate capabilities. No UI framework, browser/PWA/native packaging, storage technology, or integration mechanism is selected. Initial administrator work may be complex; recurring enrollment must be minimal. The internal pilot handles permission-sensitive project/source data; no regulated-sector certification is asserted.

**[U: UX-19–24]** Show how often skills and memory are loaded/used by agents; provide an audit trail for everything Owl Mast creates; add a kanban view, ticket/PR dependency graph, and machine/sandbox context to agent connections. The user prefers full audit coverage; Knowledge and Skills may be an initial implementation slice only if effort warrants it, not an agreed reduction of scope. The user-supplied [AI Native SDLC Playbook, pp. 8–9](imports/ai-native-sdlc-playbook.pdf) resolves the board stages: Plan, Design, Build, Test, Deploy, Maintain. The reference groups plays by nonlinear stage; its arrows express dependencies, not a mandatory stage sequence. Neo4j is a possible later architecture consideration, not a selected technology.

## Information Architecture

**[P] Proposed structure:** Daily Work, Focus, Knowledge, Connections, and Usage are primary destinations. Promotion is within Knowledge; administrator setup is within Connections; Preferences and Audit are utility destinations. Work/evidence and knowledge detail are contextual destinations. Skill/memory statistics are an S7 view with contextual entries from S3/S4; kanban is an S10 view and dependencies are available from S2/S10.

Company context is an explicitly selected authorized aggregate. **[P] Focus is the deliberate exception:** it opens on “All authorized projects · Assigned to me” to reveal parallel epics; project sections and a visible project filter retain their boundaries. This does not widen knowledge search or any other surface default. First entry asks for an authorized project; subsequent entry proposes restoring the last still-authorized project. Daily Work and notifications cover authorized connected project work with visible scope controls; do not silently restrict them to the viewer's assignments. Focus defaults to assigned-to-me work. “Assigned” requires a source-provided identity or confirmed mapping; never match people by display name. An unmapped source says “Your identity in this source isn’t confirmed; assigned work may be missing,” rather than reporting no assignments.

| ID / surface | Entry and purpose | Journey / coverage |
|---|---|---|
| S1 Daily Work · [visual](mockups/daily-work.html) | Open Owl Mast; own/colleague filter, closures, attention, progress, recent updates, coverage. Proposed order: scope and period → own/colleague summary → attention → epic and ticket evidence → recent updates → collection coverage; an IA proposal, not a confirmed feed-versus-wall choice. | J1, SC-1, J7; FR-4–7/15/17 |
| S2 Work and evidence detail · [visual](mockups/work-detail.html), [run history](mockups/run-history.html), [dependencies](mockups/dependencies.html) | From work/attention/update; ticket or epic → task/run evidence → contributions → acceptance evidence; model, effort, session, machine, token In/Out; typed ticket/PR relationships in graph and list; compact Usage & cost. | J1, SC-1, J7, J11; UX-18/23, FR-4–7/19 |
| S3 Knowledge · [visual](mockups/knowledge.html) | Scoped catalog/search, lifecycle filters, permitted submission, Notion lineage, item-level load/use statistics and audit entry. Company-approved knowledge clearly carries its scope. | SC-2, SC-3; FR-8–10/14/21 |
| S4 Knowledge detail and delivery history · [visual](mockups/knowledge-detail.html) | Exact version, applicability, evaluation, conflicts, origin, permitted evidence, recipients, load/use statistics and object audit history. | SC-2, SC-3; FR-8–14/21 |
| S5 Connections and agent enrollment · [visual](mockups/connections.html) | Existing Claude/Codex clients, authorized project selection, independent observation/delivery readiness, configured and observed machine/sandbox, freshness, recovery and appearance. | J2, SC-2; UX-24, FR-1–3/14/21 |
| S6 Promotion · [visual](mockups/promotion.html) | Per-project policy, manual reviews/automatic exceptions, exact publication preview, allowed audience, checks, history, withdrawal/supersession. | SC-3; FR-9/12/13/17 |
| S7 Usage · [visual](mockups/usage.html), [run history](mockups/run-history.html), [knowledge statistics](mockups/knowledge-usage.html) | Project/company measurement, period, source coverage, supported client/model/effort/task-role/machine/agent/person/session/work attribution, token In/Out, estimate basis, unassigned portions; separate skill/memory load, delivery, observed-use and verified-reuse evidence. | J6, J9; UX-18/19/20, FR-11/16/17 |
| S8 Administrator setup · [visual](mockups/administrator-setup.html) | Separate source accounts/projects, capabilities, authorization, collection/retention policy, secret-free setup guidance. | J2; FR-1–3/18/20 |
| S9 Preferences and notification return · [visual](mockups/notifications.html) | Push consent, visible event/project preferences, and theme; notification reentry leads to the current authorized detail. | J7; UX-01, FR-17 |
| S10 Focus · [visual](mockups/focus.html), [kanban](mockups/kanban.html) | Separate assigned-work board; epic/combined and kanban presentations, source status, concurrent contributions, dependencies and contextual usage. The six observed SDLC stages retain explicit mapping/evidence; unmapped work remains visible. | J8, J11; UX-11/12/22/23, FR-4–7/15/19 |
| S11 Audit · [visual](mockups/audit.html) | Authorized system activity by object/version, actor, action, outcome and time; object-level history from Knowledge/Skills and other created records. | J10; UX-21, FR-12/13/17 |

**[U: UX-23] A ticket dependency graph is required**, superseding the earlier optional-graph proposal. **[P]** Keep graph/list inspection within S2, reachable from Focus, rather than selecting another primary destination. The user requested visual references for every surface (UX-14); each row links its screen, and the [daily-work study](mockups/daily-work.html) and [Focus study](mockups/focus.html) also show inline S2 evidence. These are layout references with illustrative data and disabled source actions; they do not prove source integration, permissions, or full detail navigation. [Browse all visual references](mockups/gallery.html).

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
| “This item is unavailable. Return to your work.” | Safe denied/revoked destination without leaking its existence or title. |
| “Last successful collection: … Current coverage is incomplete.” | Missing telemetry does not mean an agent is stuck. |
| “Tokens in: 12,000 observed · partial coverage. Tokens out: Unavailable.” | Each direction has its own evidence; the observed subtotal is not a complete ticket total. |
| “Review · effort: Ultra · source-reported.” | Effort belongs to this task; its source label is not normalized into another provider's scale. |
| “Skill loads: 12 observed · partial coverage. Verified reuse: Unavailable.” | Successful loads and evidence of use are different measurements. |
| “Last observed on Builder laptop at 09:42. Current location unverified.” | Location freshness is not a live-running claim. |
| “Publication attempt failed. No new version created.” | An audit attempt is not a successful object creation. |

## Component Patterns

Visuals are in DESIGN.md.Components. These names are shared contracts, not a chosen implementation library. Native filters/switches expose pressed or selected state through settings-field/action-control rules; badges and notification previews use state-message semantics; disclosures use evidence-detail with native expanded state. Secondary actions retain action-control pending/error behavior and a descriptive label.

| Component | Behavioral contract |
|---|---|
| `brand-mark` | Decorative beside visible Owl Mast text; hide duplicate graphic naming from assistive technology. If the combined identity is a home link, give it one descriptive name and normal keyboard/link behavior. |
| `scope-bar` | Persist project/source identity and period across summary/detail. Changing scope reauthorizes and resets incompatible filters; never silently substitutes another project. |
| `surface-navigation` | Announce destination and current selection; retain safe return location and filters. Hide unauthorized administration without exposing hidden work counts. |
| `work-summary` | Selecting a count opens its underlying permitted records with the same period/basis. Every total displays “Counted from records you can access”, even when nothing is hidden. Conditional source-collection gaps are labeled separately; never expose hidden counts or imply a whole-source total. No individual productivity ranking. |
| `attention-item` | Open observed request/blocker/review evidence. Explain source, requester if known, age, and current state. No inline reply or execution control. If collection policy excludes request text, show “Request text isn’t collected under this project’s policy” with permitted source/reason/time/link; do not presume raw chat collection under A-3. |
| `progress-evidence` | Expand completed/total criteria or child set with source/time. Read-only; no tracker checkboxes, edits, or synthetic percentage for unknown work. |
| `work-record` | Open S2; distinguish owner, initiating person, executing agent, delegation, and repository identity. Unknown/inferred links remain labeled and inspectable. |
| `ticket-chip` | A labeled ticket reference opens its authorized S2 detail; source qualification disambiguates duplicate keys. Read-only tags do not masquerade as controls. |
| `agent-chip` | Read-only display of a personal owl alias/color with fixed provider/type icon and label; editing is a separate S5 action. Underlying client/run identity remains inspectable; aliases never merge records, change permissions, or rename source/provider objects. Proposed S5 appearance settings attach to a stable enrolled client, not a run or model. A run inherits that client’s viewer-local alias. Otherwise use type plus short client ID; never render another person’s alias. Shared naming authority remains open. |
| `focus-board` | Assigned-to-me work by default. Switch epic-grouped/combined/kanban presentation without changing source ownership or status; filters remain visible. Kanban uses Plan, Design, Build, Test, Deploy and Maintain, with explicit project mapping/evidence and original source status. Stage not mapped is a separate area; blocked is a badge. Stages do not enforce a linear workflow. No drag-to-reassign, status mutation, or agent execution controls. |
| `epic-group` | Group by explicit source epic relation; show simultaneous agent contributions across epics. Shared/unlinked/unknown records retain distinct labels. Combined unique-record totals deduplicate the same work/run rather than summing appearances. Shared markers and counterpart links require readable links within the displayed project; otherwise show an ordinary run. Every aggregate carries the constant accessible-record basis label. |
| `evidence-detail` | Expand source facts and correlation basis; preserve ambiguous/unlinked evidence. Ticket run history separates task roles and runs, retaining model, effort, session, machine, token coverage, source, and time under UX-18 semantics below. Acceptance names its approving authority or configured source rule and referenced artifact; missing authority cannot imply verified acceptance. Provide permitted source links. Dependencies distinguish explicit links from inference and ticket dependencies from PR contribution links; graph and list use the same authorized relation set. Object history opens permitted audit events without widening access. |
| `activity-list` | Filter by authorized event type/person/period. Preserve reading position during new arrivals; offer “New updates” rather than moving rows under focus. Use bounded pages/load-more. Audit mode additionally preserves actor kind, object/version, action, outcome, event/recorded time and permitted causal links; a later correction does not silently replace earlier history. |
| `knowledge-record` | Open exact version; submission records origin/scope/applicability. Distinguish human-reviewed from automatically evaluated guidance, showing evaluator or policy, basis, evaluated version, and time. Candidate submission does not approve or publish. Duplicate/conflict references appear only for accessible versions. A restricted match returns “Saved as a candidate” and routes the match privately to an authorized maintainer; it never exposes another project’s private item. Contextual statistics and audit entries retain exact version, scope, period and independent evidence permissions. |
| `delivery-receipt` | Show available/retrieved/delivered/reused separately with observed evidence; show recipient/project/version/time only when authorized. Never infer use from reading. An authorized reviewer can record verified reuse with exact version, permitted artifact reference, and time; artifact visibility follows the recipient project. Origin readers without artifact access receive only “Reuse verified in a permitted project”. |
| `connection-readiness` | Present observation and delivery independently per client/project. Explain permission, unsupported capability, and unverified reading separately; a shared source failure appears on every dependent client, with the same last-success time. Readiness checks do not launch an agent. Show configured machine/sandbox separately from last-observed location and time, with Unknown/Stale states; source-qualified client/machine IDs disambiguate names. Inspecting or selecting an enrollment context is not machine routing. |
| `promotion-review` | Project-designated maintainers inspect exact candidate content/version and permitted audience before a manual decision [U: UX-09]. Recheck authority, policy, and version; changed content invalidates stale approval. This is the PRD’s project-scoped knowledge-maintainer role: only its authorized actions include policy, review, supersession, and withdrawal. Designation does not grant source access. Without access to candidate material, show “This review needs a maintainer with access to its source”; no decision is recorded. |
| `usage-breakdown` | Offer supported project, client, model, effort, task-role, machine, agent, person, session, and work-item breakdowns. Ticket input/output tokens follow the attribution and counter rules below. Compact ticket/epic summaries open the same scoped S7 detail. Filters preserve units/period/coverage; chart/table drill-down retains unassigned and unpriced records. Deduplicate shared usage in epic totals; ambiguous allocation stays unassigned. Unavailable attribution is labeled, never guessed. Costs never collapse distinct measurement classes or currencies. Contextual summaries require the same class-specific access as S7; ticket access alone grants no telemetry or bill/allocation access. No allocation basis may reveal an inaccessible residual share. Every total carries the constant accessible-record basis label. Skill and memory counts follow the separate load/use definitions below and drill into the same permitted evidence, not a combined productivity score. |
| `settings-field` | Save permitted settings explicitly with visible outcome; validate near the field. Policy changes show effects on pending/new publication; existing-publication behavior remains A-4. |
| `state-message` | Distinguish empty/loading/failure/offline/denied/stale/unsupported; give authorized recovery only. Important failures persist beside affected content. |
| `action-control`, `action-control-dark` | Same behavior in both themes. Explicit permitted knowledge/admin action; prevent duplicate submission while pending and show actual completion/failure. No optimistic publication. |
| `external-link` | Identify destination; navigation only. Missing/unsupported link is explained. Returning does not imply external action succeeded; await new source evidence. |

## State Patterns

The following baseline applies to **every S1–S11 surface**:

- Cold-load shows labeled loading without placeholder numbers.
- Keyboard focus stays visible and returns to the trigger after detail closes.
- Expired/revoked access removes restricted data and uses neutral unavailable copy; authorization that cannot be checked fails closed.
- Offline means no newly disclosed protected content and no queued knowledge publication/admin writes. No offline sensitive-browsing capability is promised. Reconnect rechecks access before refresh. Recovery must not duplicate observations, contributions, runs, receipts, or usage.
- Source timestamps and collection timestamps remain distinct.

| Surface | Empty / first use | Error / stale / unsupported | Permission / offline specialization |
|---|---|---|---|
| S1 Daily Work · [visual](mockups/daily-work.html) | No authorized work, no matches, and no connected coverage are different messages. First use routes to authorized project/enrollment. | Keep valid data from healthy sources; label stale sections and incomplete totals. Unsupported telemetry never becomes zero. | No hidden-source counts or person associations; offline cannot masquerade as a live all-clear. |
| S2 Work/evidence · [visual](mockups/work-detail.html) | “No linked evidence” differs from “No matching records.” Unlinked activity remains findable. | Missing checklist → Unknown; missing model/effort/session/machine → Unknown with a safe collection reason. Run fields can be partial independently; stale evidence retains source time. | Denied source or run detail is not replaced with cached text or a cross-project record. Suppress protected identifiers, machine names and metrics together with their derived summaries. |
| S3 Knowledge · [visual](mockups/knowledge.html) | Empty catalog and no relevant result are distinct from failed scope validation. | Submission failure retains only authorized unsent content in the current view; sync conflict does not overwrite newer source knowledge. | No default cross-project search fallback; offline submission is not represented as saved. |
| S4 Knowledge detail/history · [visual](mockups/knowledge-detail.html) | “No deliveries” differs from “collection unavailable”; no verified reuse is an explicit state. | Conflicting/superseded/withdrawn/quarantined/version-unknown content follows the lifecycle rules below; “delivery capability unsupported” differs from “no recipients.” | Audit and recipient visibility checked separately; no inaccessible origin excerpt. |
| S5 Connections/enrollment · [visual](mockups/connections.html) | No clients prompts enrollment; no authorized projects gives safe access guidance. | Partial readiness, expired authorization, stale observation, unavailable client path, and unverified skill reading have separate reasons. | Membership does not prove source access; do not show protected readiness results when cached rights cannot be verified. |
| S6 Promotion · [visual](mockups/promotion.html) | No eligible candidates, no reviews, and disabled policy are distinct. | Failed/uncertain safety checks keep project scope; changed version/policy requires reevaluation. No silent automatic retry under an obsolete mode. | Denied policy/review action is not shown as pending success; offline publication unavailable. |
| S7 Usage · [visual](mockups/usage.html) | No observed usage differs from unsupported/unpriced/unassigned/incomplete data. | Input and output can be independently unavailable. Observed subtotals remain labeled partial when collection coverage is incomplete; conflicting counters stay unresolved. Estimates show pricing source/date and basis. | Aggregate only authorized records; no invisible-source residual, hidden-run denominator, or protected machine/model filter option. |
| S8 Administrator setup · [visual](mockups/administrator-setup.html) | Unconfigured project shows prerequisites and supported boundaries. | Each connector can fail independently; safe diagnostics identify remediation without credentials. Unsupported host/client capability labeled. | Only projects this viewer administers appear, including their source and client identities; permissions required are explained without requesting secrets in ordinary text. |
| S9 Preferences/return · [visual](mockups/notifications.html) | Push states (not requested, denied, unsupported) are independent of agent health. | Save failure retains visible unsaved choice; old notification opens latest authorized state, including already-resolved attention. | Revalidate on open; revoked target returns neutral unavailable, no title in error. Offline return cannot reveal protected cached detail. |
| S10 Focus · [visual](mockups/focus.html), [kanban](mockups/kanban.html) | No assignments, no matches and no mapped phase are distinct; unmapped work stays visible. | Stale source status remains labeled; unknown workflow mapping never implies a phase or inactivity. | Apply S1/S2 access to cards, column counts and relations; offline cannot imply currency. |
| S11 Audit · [visual](mockups/audit.html) | No events in a known-complete authorized window differs from no matches or unconfigured collection. | Delayed/incomplete coverage and failed operations are explicit; no invented events or continuity claim. | Protected objects, actors, diffs and causal links are withheld together; direct denied entry is neutral, with no historical payload. |

### Knowledge disclosure and lifecycle states [P/R]

Project scope is a ceiling, not a read grant. Titles, bodies, evaluation basis, check reasons, snippets, duplicates, and notifications require authorization for the material they derive from, or an evaluated version safe for the explicitly wider project audience. Unverifiable eligibility withholds the version, including after source access changes. This rule also covers submitted and Notion-derived lessons.

| State / audience | Visible behavior |
|---|---|
| Quarantined | Distinct system-initiated state with permitted reason/time and actor kind; S3 filter, S4 detail, and S6 exception/history expose it to authorized maintainers. Exact retrieval/retention defaults remain A-2. |
| Withdrawn, former audience | S3/S4/S6, feeds, notification return, and receipts suppress the withdrawn body/title and use a neutral reference plus “Since withdrawn”; authorized audit access is separate. Exact retention and client recognition remain A-2. |
| Superseded | Eligible readers may inspect the older version with “Since superseded” and a permitted replacement link; it must not appear current. |
| Receipt history | Shows available/retrieved/delivered/reused states separately, including later lifecycle changes. Independent Notion/client reads appear only if a validated observation path supplies authorized evidence; they are not silently counted as Owl Mast delivery receipts. |
| Withdrawal result | “Owl Mast delivery stopped.” Previously delivered copies/actions cannot be recalled; direct source/client access remains governed separately. Whether to alter the Notion source is an implementation-design question. |

Receipt visibility applies equally in S4, feed, push, and audit. Recipient identity/task context requires recipient-project access; an origin maintainer sees the constant note “Delivery history is limited to records you can access” and no hidden recipient count. **[OPEN, A-3]** Agent query text and requested-context retention/visibility are undecided; references do not imply they are stored.

## Interaction Primitives

- Use click/tap and standard keyboard controls. Every expandable detail has a labeled trigger, announced expanded state, and predictable focus order. Escape closes the top temporary layer; no stacked dialogs.
- Navigation and filters are read-only. Pending knowledge/admin writes disable duplicate activation, preserve applicable context, and report actual success or a safe error; retries recheck permission/version. Do not turn a failed mutation into success by clearing the form.
- Project changes, deep links, searches, notification previews, and exports if later added all preserve source-level authorization. Retained filters never grant access or disclose restricted labels.
- Proposal: show the reporting window explicitly and start with “Today” in the viewer's timezone; permit a custom period. This is not a confirmed reporting preference. Exact source timestamps remain inspectable with timezone.
- On route/contextual entry, update the page title and focus the destination h1. A notification arrival places its time and current-state change immediately after that heading, plus “Other updates since this notification” linking to S1. Back returns to the prior safe location, or S1 in the same authorized project with no history. If that project is no longer authorized, use the authorized-project chooser. Unavailable states focus their neutral heading and provide a working return link. Temporary overlays are named modal dialogs with focus inside, an inert background, and focus restored to the trigger.
- A record’s title is its primary link; chips are siblings, never nested interactive elements. Interactive chip hit areas must not overlap; stack when needed. Agent chips are read-only unless explicitly linked and read as “Tawny, Claude agent”. Alias text wraps anywhere rather than clipping.
- Lists are bounded, with a labeled result count and load-more control. Activation announces the added count and focuses the first newly loaded item. Repeated disclosures name their ticket/client context; long detail pages offer section links.
- No drag requirement, hover-only action, auto-playing media, or mandatory keyboard shortcut. Selection, copy, and ordinary scrolling remain native. A source link opening is not proof of work advancement.
- Run-history disclosures identify ticket, task role, and run. A shortened session ID offers an accessible full-value expansion and copy action only while that identifier is permitted; confirm copy or failure beside the control without including restricted text. Copying never launches or resumes a session. Filter changes do not hide the current scope, period, or missing-coverage note.

## Accessibility Floor

**[P] Target:** [WCAG 2.2 AA](https://www.w3.org/TR/WCAG22/) for the chosen UI surface; implementation verification follows architecture. Visual contrast and exact tokens live in DESIGN.md. All functions work with keyboard, touch, and screen reader, with labels and state announcements independent of color.

- Use semantic headings, lists, tables, form labels, and landmarks; provide a skip-to-content route and logical focus order. Charts/relationships have equivalent labeled lists/tables.
- Text zoom to 200% and reflow at 320 CSS px must preserve essential content/actions. Use `{typography.body}` for reading, `{typography.row}` for compact lists, and minimum `{spacing.control-target}` hit areas. Focus must not be covered by sticky UI.
- Announce meaningful loading/result/error changes politely. Validation identifies the failing field and remedy. Refresh across S1–S11 preserves focus, reading position, open disclosures, and stable summary/detail values while the person reads; new values/items wait behind “New updates”, announced once as a coalesced polite count. Activating it focuses the first new item or changed section. No per-event screen-reader interruption or unsolicited reorder.
- Permission/scope removal overrides retention: immediately remove protected content, move affected focus to the nearest surviving heading or neutral state-message, and announce the change without restricted names. This is the exception to preserving content under focus.
- Respect reduced motion; disable nonessential transitions. Unknown progress exposes a text state, not a false progressbar value. Permission and stale states remain understandable without color.
- Phone and tablet layout must survive enlarged text and landscape. Critical operations do not depend on precise gestures; confirmation describes the affected version/audience, not just “Are you sure?”

## Responsive & Platform

**[U]** Laptop, tablet, and phone daily use. **[P]** One consistent navigation vocabulary and account/project context across sizes; browser/PWA/native choice remains an architecture input because push support and enrollment routes must be validated, not assumed.

| Layout width | Proposed behavior |
|---|---|
| ≥1024px | Layout per DESIGN.md. S2 detail can preserve the surrounding work context. |
| 600–1023px | Layout per DESIGN.md. Evidence can expand to full width. |
| <600px | Single column; summary → attention → work/progress → updates/coverage. S2/S4/S6 detail uses full width with explicit Back. |

- Scope stays present in the page, not necessarily sticky. Compact layouts and enlarged text use normal flow; wide sticky elements must never cover focused content. S7 tables become labeled rows below 600px; filters/paging wrap and long values break safely. Essential two-dimensional evidence, if needed, has a named keyboard-focusable scroller and a readable list alternative.
- S2/S7 run history stacks implementation, review, and other observed task cards below 600px, retaining each card's model, effort, session, machine, time, and In/Out labels. Wide paired cards are a layout choice, not a requirement that work has exactly two runs. Long identifiers wrap in expanded detail; essential values never rely on hover.
- Mobile V1 supports observation, alerts, and evidence. Replies/assignments belong in another app (UX-06). Theme follows system with override **[D]**.
- Offline operation, installability, background behavior, and rich notification actions are not promised. No digest or notification schedule has been chosen; UX-10 excludes a silent digest.
- English microcopy is the working draft language; localization markets and translated content behavior are not established.

**[P] Board/graph/audit adaptation:** kanban columns remain selectable and readable below 600px, with a grouped-list alternative; dragging is never required. A graph has keyboard-operable selection and an equivalent relation list, without shrinking node labels to fit. Audit rows stack into chronological labeled entries; before/after details wrap and retain their field labels. Changing presentation preserves scope, filters and focused object.

## Evidence, knowledge, usage, and identity semantics

### [U/R] Ticket progress

completed acceptance criteria/checklist items ÷ measurable items, with numerator, denominator, basis, source, and observation time. No breakdown → **Unknown**. No measurable items also → Unknown, not 0%/100%. Changed criteria visibly change the denominator. If criteria and another checklist disagree, show both labeled measures or “Basis needs review”; do not silently combine them.

### [P/R] Epic progress

show source-scoped closed child tickets ÷ known in-scope child tickets, explicitly labeled **child tickets closed**, with coverage and changes to the child set. This is a proposed representation, not user-confirmed acceptance semantics. Never average heterogeneous ticket percentages. The fraction is dominant; a derived percentage is secondary. Always show “Counted from records you can access”; permission filtering never triggers a special hidden-record notice. Known collection gaps additionally label coverage incomplete. Name whether the set is the viewer’s assignments or the permitted epic child set. Parent acceptance stays a separate sourced fact. Closures are events in the selected period, not credit for all work performed by the owner.

### [R] Evidence

keep tracker closure, merged contribution, checks-passed/skipped/not-run, acceptance, and deployment separate. Label source fact, confirmed mapping, inference, estimate, and unknown. Preserve explicit versus inferred dependencies; do not convert stale collection into a blocker or infer initiator from commit author/credential alone (FR-4–7).

### [U: UX-18] Ticket run history

The five requested fields belong to each observed task/run and remain inspectable from its ticket. **[P/R]** Group by source-qualified ticket, then observed task role (implementation, review, planning, evaluation, or Unknown), with individual runs beneath it. Preserve retries, delegated children and simultaneous work; a ticket can have several models, efforts, sessions and machines. Observed model or effort changes within one session remain separate time-qualified segments. A compact summary says “Multiple” when necessary and expands the actual permitted records, rather than choosing one value. Role and independence require evidence; a record labeled review is not automatically an independent review.

| Field | Evidence and presentation contract [P/R] |
|---|---|
| Agent and model | Keep viewer-local owl alias, fixed Claude/Codex type, source-qualified client/run identity and model name distinct. Preserve the observed model identifier/version; a display name can accompany it. Never derive a model from the alias or current client default. |
| Effort | Show the exact task/run value and its source/time. Label a configured/requested value separately from runtime-reported effort; if both exist and differ, show both. Do not infer historical effort from current settings or equate labels across providers. User examples such as Opus 5.5, Medium and Ultra establish presentation needs, not verified provider availability or scale equivalence. |
| Session | Show the source's session ID qualified by provider/client or connection namespace; identical strings from different sources remain distinct. A task/run ID, delegation ID and session ID are separate facts. Missing session identity stays Unknown. |
| Machine / sandbox | Show the recorded friendly machine name and, when permitted, its stable source identity to disambiguate reused names. A sandbox name is not proof of security isolation. Do not require an IP, credential, local path or hostname disclosure. A changed execution location produces separate time-qualified evidence, not a rewrite of older runs. |
| Tokens in / Tokens out | Show independently sourced counts, units, observation window and counter basis. Missing one direction leaves that direction Unavailable, not zero or an inferred difference. If the provider includes cached input in input, label it as a subset and never add it again. Unknown provider accounting stays explicit. |

**[P/R] Attribution and totals:** ticket In/Out totals sum only compatible, uniquely observed usage portions attributable to that ticket. Distinguish a session-wide counter from task-specific consumption; a link alone does not allocate the whole session to a ticket. Shared or ambiguous usage remains unassigned. Do not add overlapping cumulative snapshots, replayed events, or a parent counter that already includes the displayed child usage. Distinct retry consumption can count once when evidenced and attributable. Unresolved overlap/conflict remains outside the subtotal with a safe coverage explanation. Epic/project totals deduplicate the same portions across appearances and retain the period and attribution basis. Prices remain in the separate measurement classes below.

**[P/R] Coverage and access:** show “Counted from records you can access” on every aggregate. Known collection gaps produce a partial observed subtotal, including separate In/Out coverage where needed; no supported measurement means Unavailable. Do not claim complete history from visible records alone or reveal hidden run counts, filter values or residual shares. Ticket access does not grant access to run metadata or usage: model, effort, IDs, machine names, counters, copied values and derived summaries require their source authorization. Fail closed on revocation or unverifiable access. These fields do not require raw conversations; A-3 remains unresolved. Source capability and historical availability must be validated before claiming collection support.

The [run-history reference](mockups/run-history.html) illustrates these contracts with synthetic records. No routing, load-balancing, assignment, retry or agent execution control is added.

### [U: UX-19/20] Skill and memory statistics

The requested statistics distinguish Skills from Memory. **[P]** Memory means authorized project knowledge/memory records and permitted company publications; it does not introduce collection of personal Notion memory. S7 shows each kind separately, with counts on S3/S4 item/version detail. Preserve the existing retrieved/delivered/reused distinctions rather than renaming every retrieval “used”.

| Measurement [P/R] | Required evidence and counting basis |
|---|---|
| Agent loads / reads | A validated observation that an agent successfully read or loaded a specific item/version. A search match, source-page view, UI click or repository fetch by this UX session is not enough. A successful delivery without a read/load acknowledgment remains a delivery. |
| Deliveries | Observed receipts to a permitted recipient context, counted separately. A partial or failed attempt is not a successful delivery/load. |
| Observed use | Source-supported skill invocation/application or memory application to a task, with its permitted event/artifact basis. Loading alone cannot establish this state; automatic detection is not assumed. |
| Verified reuse | Exact-version task evidence plus authorized human verification under FR-11. This remains distinct from observed use and is not a token, productivity or ROI score. |

**[P/R] Counting:** each metric names its unit, selected period, project, source coverage and attribution basis. Use source event time for the period; label any recorded-time fallback and collection delay. Deduplicate replay of the same source-qualified event. Distinct successful reloads may each count, including an observed cache load, with that basis labeled; do not collapse them merely because they share a session. Conversely, transport retries and duplicated receipts are not new loads. Count each item/version in a multi-item load only when its inclusion is observed. Display distinct agents/clients, sessions and items as separate dimensions, never as synonyms for load count. Unknown item/version or ambiguous attribution stays unassigned rather than guessed. Model, task and machine breakdowns require their own evidence.

**[P/R] Disclosure:** counts and drill-down share permissions, including item versions, recipient/task context and source-derived content. Show “Counted from records you can access” on every aggregate. A known collection gap produces a labeled partial observed subtotal; unsupported or unavailable observation is Unavailable, not zero. Zero is allowed only for a known-complete observed window over the stated authorized scope. Do not reveal restricted recipients through unique-count differences, hidden filter options or residual shares. Existing Notion source reading and this local preview establish no historical agent load/use count. Query/context retention remains A-3.

### [U: UX-21] Audit coverage

The requested target is an audit trail for everything Owl Mast creates. Knowledge and Skills may be an initial delivery slice if effort requires it, but no reduced scope or implementation sequence has been approved. **[P]** Provide S11 as a system audit utility and an object-history entry from every covered record; preserve the originating object/version and filters on return.

The target covers knowledge/skill versions and evaluations, publications and lifecycle changes, delivery/read/use evidence and receipts, ingested observations and correlation records, generated summaries, connection/enrollment records, configuration/policy and alias changes, and notification records/outcomes. A source PR or Jira ticket created elsewhere is an imported observation, not an Owl Mast-created source object. Audit collection should cover attributable state changes and relevant knowledge access events, not assume capture of every keystroke or raw conversation.

**[P/R] Event contract:** show a stable permitted event reference, object/type/version, action, outcome, human/agent/service actor, initiating identity when supported, source and recorded timestamps with timezone, reason, permitted source evidence and correlation/causal links. Authorized before/after fields or version comparisons explain changes; unavailable or redacted fields stay labeled without exposing the original value. Distinguish requested, successful, failed and unresolved outcomes. A failed creation attempt does not imply an object was created; a notification record does not prove push delivery. Missing actor, timestamp or causal evidence stays Unknown.

**[P/R] History and safety:** show later corrections/supersessions as additional linked events, without silently rewriting earlier user-visible history. This UX contract does not promise a particular immutable-storage, cryptographic, retention or completeness mechanism. Display coverage and delay explicitly; no events, no matches, unsupported collection and incomplete history are different states. Event IDs/order must not reveal restricted gaps. Access to an object does not automatically grant access to all actors, recipients, diffs or source material in its audit. Counts, filters, snippets and causal links follow the same source/recipient boundaries. Revocation or unverifiable access removes protected historical payloads; a direct unavailable entry uses neutral copy. Never place secrets, credential values or raw private conversation bodies in audit previews. Retention, allowed collection and restricted withdrawal history remain governed by A-2/A-3 and later architecture decisions.

### [U: UX-22/23] Kanban and dependencies

A kanban view is required within Focus. **[U: UX-22, supplied reference]** Its six stage labels are **Plan, Design, Build, Test, Deploy, Maintain**, following the user-supplied [AI Native SDLC Playbook, pp. 8–9](imports/ai-native-sdlc-playbook.pdf). These stages are nonlinear; the reference groups plays by stage and shows dependencies between plays. Adopting these labels does not adopt the playbook’s automation or create a required transition sequence.

**[P]** Present this as an observed SDLC-stage view over the same assigned-work scope. A primary ticket stage requires explicit project mapping or authorized artifact/evidence, with mapping version, source and observation time inspectable. Show original Jira/source status alongside it. “In progress” alone does not establish Build; “Done” or a merged PR does not establish Maintain. A ticket with no supported mapping stays in **Stage not mapped**, outside the six columns. Blocked is a badge with its evidence, not a seventh workflow stage. Keep concurrent contributions in other stages distinct from the ticket’s primary placement; do not duplicate or silently advance the ticket to express them. Counts use the accessible-record basis and unique tickets, while filters retain project, person and epic context. V1 is read-only: no drag-to-change status, assignment, or agent execution.

The ticket dependency graph is required, replacing the earlier optional graph. **[P/R]** Enter from a ticket or epic in S2/S10 and inspect its authorized neighborhood, with source-qualified ticket/PR identities. A directed “prerequisite → dependent” edge differs from “PR contributes to ticket”; labels and line patterns identify explicit versus inferred relationships, with source/time/basis on inspection. Inference never becomes a confirmed blocker or acceptance verdict. A linked merged PR cannot complete its ticket. Multiple PRs, shared contributions and contradictory relations stay inspectable without merging identities.

Graph and list contain the same permitted relation set. Support focus on a node, a bounded neighborhood and a safe return; phone and keyboard users can inspect the full information in the list. Loading, no known relation, unmapped evidence, unsupported source, delayed collection and visible cycles have distinct explanations. A cycle warning is based only on observable authorized relations and is not a declaration that all involved work is blocked. Do not show hidden-node placeholders, counts, labels or edge stubs that disclose inaccessible work. Collection gaps cannot establish “no dependencies”. Neo4j and other graph/storage choices remain architecture candidates, not UX commitments.

### [U: UX-24] Connected client location

S5 shows the machine/sandbox associated with each client. **[P/R]** Distinguish the configured enrollment location/profile from the last-observed execution location, its time and observation readiness. When no current observation exists, say Unknown or show the last observed location as stale; never imply that a connected client is running now. Friendly names are paired with stable source-qualified identity when permitted; reused names or aliases cannot merge clients or machines. One client may have multiple observed execution locations, retained as separate evidence. Changing an enrollment profile does not rewrite historical run location under UX-18 and does not route work. Do not require IPs, credentials or local paths, or imply that a named sandbox proves security isolation. Permissions apply to location fields and their derived filters/counts.

### [R] Knowledge

project scope by default. Exact versions carry origin, scope, applicability, evaluation, freshness, and permitted references. Candidate/approved/conflicting/superseded/withdrawn/quarantined are distinct. “Available” means eligible in scope; “retrieved” means a read is observed; “delivered” means receipt is observed; “demonstrably reused” needs task evidence and human verification. Truncation counts eligible results omitted by a result limit only; permission-filtered results produce no count or omission signal. Preserve Hermes → Notion; no duplicate save, bulk migration, or silent overwrite. Existing Notion page creation never proves skill reading, approval, promotion, or reuse.

### [R] Promotion

automatic is the preferred mode, with manual-approval and disabled available per project. A mode is not a license to widen source permissions. Evaluate a specific version for an explicitly permitted company audience; failed/uncertain checks retain project scope. Mode/version changes invalidate pending publication under the former conditions. Withdrawal cannot erase external clients' earlier copies/actions; recheck eligibility before future delivery and withhold if unverifiable. Detailed defaults remain A-1/A-2/A-4.

**[P] Publication identity and audience:** a company publication is its own versioned record, with an ID containing no source-project key, exact proposed text, permitted audience, policy version, publishing person/automation identity, and a restricted reference to the origin version. Approval or automatic evaluation binds to that exact publication version, including any sanitized text; changing it invalidates the decision. A company reader sees the publication content/version/scope/applicability/freshness and evaluation kind. Origin project/ID, named evaluator, detailed basis, and other projects’ receipts require separate access.

An exception offers three bounded outcomes: keep project-scoped with a reason; correct content as a new version and evaluate it; or request reevaluation after the missing permission/policy input is recorded by its authorized owner. No human override bypasses required checks. **[OPEN]** The authorized owner of permitted-use input must be assigned before live promotion; it is not automatically the reviewer. Enabling automatic mode confirms the audience and that existing candidates will be evaluated; the UI reports actual publications and withheld cases separately.

### [R] Usage

separate observed units, API-equivalent estimates, subscription allocation, and actual bills. Show period, source coverage, unknown/unassigned/unpriced portions, attribution basis, and estimate price/date. No token count, closure count, or retrieval count is an individual productivity/ROI score.

### [U] Identity presentation (UX-15)

the user requests ticket/agent chips, customizable owl agent names/colors, and an agent-type icon. **[P]** Keep appearance settings in S5 as personal aliases with an accessible color palette; enforce readable text/marker contrast, retaining a fixed type label and original identity in evidence. Appearance saves explicitly for one visible client in S5 (own clients by default); naming accepts 1–32 trimmed visible characters, with an inline error for empty/overlong/control-only values. Duplicate aliases are allowed only with the short client ID visible to disambiguate. Reset restores type + short ID and slate marker. Failed save retains the unsaved choice and prior active value; revoked client access removes the setting. Owl names in mocks are illustrative. Styling a record never establishes agent attribution.

### [P] Contextual cost presentation

full analysis remains S7; ticket and epic views include a compact Usage & cost summary with a labeled measurement class and scoped drill-down. An amount requires supported attribution, currency, period, coverage, and its estimate/allocation/billing basis. Jira or repository metadata alone does not prove agent consumption or cost. Every epic amount names its set (assigned subset or permitted child set); unsupported allocation of a shared session stays unassigned, so the ticket cost is Unavailable even when linked usage exists. No linked measurement means Unavailable, not zero; this proposal responds to the user's request to make costs discoverable on work (UX-17).

## Inspiration & Anti-patterns

- ConvaDesk concepts retained: scoped overview, attention separated from progress, work-to-evidence drill-down, dependency inspection, and honest usage attribution. [Ticket detail](imports/IMG_AB4D1C8F3C45-1.jpeg), [dependencies](imports/IMG_A9CC932E588C-1.jpeg), and [overview](imports/IMG_EF516651E585-1.jpeg) ground these concepts; dense graphs do not become a phone requirement.
- [Usage summary](imports/IMG_BC54BCBE01C2-1.jpeg), [attribution table](imports/IMG_3626EBD8C28F-1.jpeg), and [continuation](imports/IMG_DE187537BF11-1.jpeg) preserve measurement scope and unassigned work. Their figures are not pilot facts. [Manifest](imports/manifest.md) identifies the supplied inputs.
- The user-supplied colleague reference IMG_66D97E72A412-1.jpeg informs ticket-to-task run evidence and separate implementation/review coverage. Its figures, IDs, machine paths and status claims are not copied into the sanitized [run-history reference](mockups/run-history.html) or treated as pilot data; the original remains a private attachment.
- Ponytail informs visual restraint as documented in DESIGN.md; activity streaks and token totals do not define Owl Mast's success. T3's two-agent setup is an experience reference; exact enrollment mechanics remain unverified. Owl Mast does not copy its execution interface.
- Avoid one synthetic “done” status, invented progress, equal treatment of no data and zero, silent cross-project search, hidden permissions inside counts, and new manual recaps to make learning transferable.

## Key Flows

Named actors mirror the PRD. SC-n preserves the PRD scenario IDs; Jn identifies added UX journeys. Existing IDs are retained for stable references; J3–J5 are unused identifiers, not omitted journeys. **Ahmed and Mohamed are scenario participants, not assumed current access-role holders.** Any administrator/maintainer step below is conditional on verified authorization. Illustrative lesson/work names are fixtures. All interaction details are [P] unless tied to [U]/[R]; none describe a completed pilot test.

### J1 — Ahmed checks his work before leaving home

1. Ahmed opens the dedicated UI on his laptop and enters/restores an authorized project (S1).
2. He sees his work status, observed attention needs, and progress basis with current collection coverage [U: UX-04/06/07].
3. He opens an attention item in S2, reads any permitted request text (or its collection-policy absence), provenance, and time, and checks whether it is still current.
4. When he needs execution context, he expands the ticket's run history: implementation and review retain their own model, effort, session, machine and token In/Out evidence [U: UX-18]. He can see whether contributions came from different machines without assuming a shared session or model.
5. **Climax:** he understands what needs his judgment and has sufficient permitted evidence to continue in T3 or another existing tool. Owl Mast exposes no reply/assignment control [U: UX-06].
6. Later, he can inspect the same authorized context on his phone; new source evidence, not opening an external link, updates the observed outcome.

Failure: source collection is stale → label the gap, keep healthy authorized evidence available, and avoid claiming work is blocked or resolved. Lost access or offline → S2's safe unavailable state.

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
5. He checks each client’s configured machine/sandbox and last-observed execution location/time, retaining Unknown or Stale where observation is missing [U: UX-24].
6. **Climax:** he can identify where a client was observed and see observation/knowledge-delivery readiness independently for each project, including unverified Notion skill reading. A connection badge cannot stand for current execution or all four client/project combinations.

Optional appearance branch: from S5 Ahmed selects his client, changes its owl alias and named identity color, previews the fixed type/ID, and saves or resets. The change affects only his presentation, including subsequent runs of that client; it creates no shared naming authority.

Failure: a Movesion source failure does not invalidate healthy Syntelligence data; unsupported client capability gives safe remediation rather than a successful badge. Do not relabel the required second project/client as optional.

### SC-2 — Ahmed’s next agent receives useful learning.

1. Mohamed's work produces a sourced lesson; existing Hermes → Notion capture or authorized Claude/Codex page creation preserves its origin in S3/S4 [R: FR-8/14/21]. An explicit Owl Mast submission, if used, captures project, origin, applicability, and evidence without duplicating an existing save.
2. S4 distinguishes the candidate from approved knowledge, preserves duplicate lineage, and shows conflict/evaluation/version. Default delivery eligibility remains **A-1**.
3. Ahmed's enrolled agent has explicit authorized project context and **searches for knowledge when it needs it [U: UX-08]**. The default is agent-initiated retrieval, not automatic injection or a human selecting every delivery.
4. Through the selected validated path, the agent receives applicable permitted knowledge with item/version, scope, source, freshness, and any truncation/omission [R: FR-10]. Notion skill discovery and reading are demonstrated separately from page creation.
5. S4 records available/retrieved/delivered states with observed evidence. Ahmed can inspect a receipt without storing a complete conversation.
6. **Climax:** a task artifact and human verification show the lesson helped Ahmed's next task without a copied recap. An authorized reviewer then uses the receipt’s “Record verified reuse” action with the permitted task artifact; only then record demonstrable reuse [R: FR-11]; A-6's minimum sample size remains provisional.

Failure: no matching knowledge → honest empty result; failed scope/authorization → no delivery; conflicting/stale/withdrawn knowledge → lifecycle treatment with A-1/A-2 clearly provisional. Never fill a gap with another project's content or overwrite newer Notion knowledge silently.

### SC-3 — Mohamed's reusable lesson reaches the other project.

1. Mohamed's lesson begins project-scoped. A **project-designated maintainer [U: UX-09]**, represented by Ahmed when authorized, opens S6 to handle exceptions or manual review. This scenario does not grant Ahmed permissions.
2. The selected project mode is automatic, manual-approval, or disabled [R: FR-12]. Automatic evaluates a version; manual requires authorized approval; disabled does not publish a new version.
3. S6 shows the exact proposed company-safe content, permitted audience, originating version, policy, checks, and rationale. Restricted source details are absent from the wider payload.
4. In automatic mode, passing required checks permits publication under policy; failed/uncertain cases stay project-scoped and enter the authorized exception view. In manual mode, a reviewer decides on that exact evaluated version. Changes require reevaluation.
5. **Climax:** Ahmed's authorized agent in the other project receives the explicitly permitted published knowledge without receiving restricted original evidence [R: FR-12/17]. S4 shows the company-reader field set above and records delivery separately from reuse.
6. A maintainer can inspect history, supersede or withdraw a version, and see earlier deliveries subject to permissions. Owl Mast explains that external past copies/actions cannot be erased; current delivery eligibility is checked again [R: FR-13].
7. Changing mode prevents pending publication under the previous mode. Disabling is not silently portrayed as revoking old publications: existing-version behavior is **A-4**; withdrawal/quarantine details are **A-2**.

Failure: revoked rights, a changed candidate, a changed policy, unverifiable eligibility, or failed publication prevents a success claim. The UI identifies the safe next review action and retains an authorized audit trail.

### J6 — Ahmed checks what observed usage means

1. From a ticket or epic Usage & cost summary, or primary navigation in an authorized project/company scope, Ahmed opens S7 with the selected work set retained and sets the period and supported client/model/effort/task-role/machine/agent/person/work filters.
2. He sees which measurement classes are observed, estimated, allocated, billed, or unavailable; coverage and unassigned portions accompany totals [R: FR-16].
3. He opens the ticket's implementation and review records, checking each model, effort, session and machine against its source/time, then compares their independently observed token In/Out [U: UX-18]. Unknown or configured-only fields stay labeled.
4. He inspects the ticket subtotal's attribution and coverage. A shared session without supported allocation remains unassigned; price/date accompanies any separate estimate. Distinct retries count only once per observed usage portion.
5. **Climax:** he can explain which task used which observed model/effort and machine, and what usage is attributable, without treating missing history as zero or token volume as a bill or productivity score.

Failure: incomplete/unsupported collection remains unavailable rather than zero. Hidden-source usage is not exposed through aggregate differences. An unassigned record remains unassigned until supported evidence exists.

### J7 — Ahmed returns from a phone notification

1. Ahmed opens S9 and requests push; Owl Mast explains the purpose before asking operating-system permission. **Every observed work update triggers push by default [U: UX-10]** across the authorized connected project scope, not only his assignments. Visible controls can opt out of named event kinds or authorized projects; all are enabled initially. Person/assignment feed filters do not silently change push eligibility; source access remains unchanged.
2. Proposal: use a generic lock-screen preview such as “Owl Mast has an update” until he opens it. Eligibility is checked per recipient and source record at send time, including for an ended device session. An unauthorized or unverifiable event sends no push at all, including no generic push; the feed follows the same rule. This is authorization, not throttling. Rich previews are not selected; push permission grants no extra content access.
3. Ahmed opens the notification. Owl Mast rechecks current access and loads the relevant S2/S4/S6 destination with current source state; it suppresses an unauthorized or obsolete sensitive preview.
4. **Climax:** he understands the current permitted event on his phone and can inspect evidence; action, if needed, remains in another app. A resolved request says it has changed rather than urging an obsolete response.

Failure: denied/unsupported push leaves in-app observation usable. Revoked access gives neutral unavailable; offline does not expose protected cached content. Each distinct event retains a distinct notification identity and source time. Deduplicate replay of the same source event, but do not silently throttle distinct updates or replace them with a digest. Platform stacking may preserve distinct updates but cannot summarize or drop them. Platform delivery constraints must be disclosed; push arrival is not guaranteed. Owl Mast cannot promise to recall external notification copies already delivered. No digest schedule or external messaging is created by this specification.

### J8 — Ahmed focuses on his assigned work across several epics

1. From the landing page, Ahmed opens the separate Focus board (S10), showing work assigned to him across all authorized projects, in explicitly labeled project sections with a visible project filter [P] [U: UX-11].
2. He sees stacked epic groups, each with source-qualified work, measured progress, blockers, and observed agent activity. These grouping mechanics are a designer proposal; the need to see concurrent epics is confirmed.
3. He expands two epics where Claude and Codex are contributing simultaneously. An agent may appear in several groups; shared or unknown attribution remains labeled, and a combined total counts unique supported records rather than appearances. Whole-epic context distinguishes the epic's permitted child set from Ahmed's assigned-ticket subset. An unlinked run appears in his personal context only with confirmed association to him, such as an explicit initiating-person record.
4. He can switch epic/combined/kanban presentation to inspect assigned work, then open S2 evidence or dependencies. The kanban uses Plan, Design, Build, Test, Deploy and Maintain from the supplied playbook, with explicit stage evidence and original source status; unmapped work and cross-stage contributions remain distinct. No dragging changes assignments/status or directs an agent.
5. **Climax:** Ahmed can see the state of his parallel work and the evidence requiring attention without mistaking Daily Work for his board. Any execution decision continues in the existing tool.

Failure: missing epic/agent mapping leaves work in an explicit ungrouped/unknown section; stale collection cannot imply idle agents or complete epics. Permission-filtered groups never reveal hidden titles or counts.

### J9 — Ahmed checks whether skills and memory are reaching agents

1. From S7, or a permitted Skill/Memory item in S3/S4, Ahmed opens statistics for an explicit project, period and optional exact version [U: UX-19/20].
2. He compares successful agent loads, deliveries, observed use and verified reuse as separate measures. The view identifies observation coverage and unavailable counters.
3. He opens a count to inspect permitted client/session/task/machine events and their item/version evidence. Replays are deduplicated; distinct observed reloads retain their identity.
4. **Climax:** he can state how often a skill or memory was loaded and what evidence exists of its use, without equating reads with effectiveness or exposing another project’s tasks.

Failure: an uninstrumented Notion/client path shows Unavailable; an empty known-complete window may show zero. Permission loss removes the protected event and its derived disclosure.

### J10 — Ahmed traces what Owl Mast created

1. From a covered object’s History entry or the S11 Audit utility, Ahmed selects an authorized object/type, period, action or actor filter [U: UX-21].
2. He follows creation, evaluation, changes and outcomes for an exact version, distinguishing Owl Mast actions from observed changes in an external source.
3. He opens permitted before/after fields, reason, source times and causal links. Later corrections remain linked events; failed attempts remain visibly failed.
4. **Climax:** he can explain what the system created or changed, who or what initiated it, and which evidence supports the outcome, including known gaps.

Failure: incomplete history is labeled; no hidden-object count or sensitive former payload appears. Knowledge/Skills-first delivery, if later selected, must disclose unsupported record classes while preserving the full-coverage target.

### J11 — Ahmed inspects dependencies before following parallel work

1. Ahmed opens a ticket’s dependencies from S2 or Focus and selects graph or equivalent list [U: UX-23].
2. He follows explicit prerequisite/dependent relations and separately inspects the ticket’s PR contributions; inferred relations show their basis and uncertainty.
3. He sees source status, freshness and acceptance as distinct facts, with visible-cycle or collection-gap explanations where supported.
4. **Climax:** he understands which observed relationships matter to the work without mistaking a merged contribution for ticket completion or assuming the graph is exhaustive.

Failure: source access is rechecked on each expansion; no inaccessible node, edge stub or residual count is disclosed. Keyboard and phone inspection never depends on canvas dragging.

### Company overview branch [P/R: FR-15]

From S1’s explicit scope selector, Ahmed selects the authorized company view. It shows permitted progress by project, distinct agent activity, attention, and knowledge sharing, with a Usage link preserving the scope. Each aggregate retains the accessible-record basis; no hidden-source residual or private project name appears. He drills into a permitted project before inspecting its work or agent context. **Climax:** he can distinguish project health and reusable company publications without merging customer work or changing S3’s project-default search. The [navigation/company reference](mockups/navigation.html) illustrates the branch. Failure follows S1 coverage and permission states.

### Observed work and notification events [P, preserving UX-10]

A work update is a newly observed, meaningful source change to an eligible work record or its linked evidence. Every distinct eligible event pushes by default; polling/replays of unchanged facts do not create new events. This event vocabulary is a designer proposal for implementation, not a narrowing of UX-10.

| Event kind | Examples / treatment |
|---|---|
| Tracker change | New record, assignment, status/closure, epic membership, criteria/checklist added/completed/reopened; retain separate facts and source time. |
| Attention | Explicit blocker/request created, changed, or resolved; no inferred blocker from absent telemetry. |
| Agent observation | Observed run/session state or supported work-link change; no invented live activity and no transcript token stream. |
| Contribution/evidence | New or changed linked PR, review, checks, merge, acceptance, or deployment evidence; never collapse these into one “done”. |
| Knowledge lifecycle/delivery | Separate eligible feed category for version, evaluation, publication, receipt, supersession/withdrawal/quarantine; **[P] enabled in notification preferences initially**, with version/audience permission checks. Not a claim that a receipt equals work completion. |
| Connection coverage | Separate visible system status category; **[P] default push for a meaningful readiness failure/recovery**, not each collection attempt. |

Tracker, attention, agent, and contribution events open S2; knowledge events open the permitted S4 or S6 state; connection events open S5. S9 exposes these named kinds and authorized projects with all enabled initially, generic-preview explanation, and explicit save outcome. Feed filters and platform permission are separate controls. No category choice is inferred from opening Focus or following a colleague.

## Open decisions and inherited assumptions

- **[P] Bounded refinements:** exact Daily Work/feed layout, Focus grouping/combined presentation, Audit utility placement, reporting-period default, epic child-closure representation, and generic notification previews remain designer proposals. These do not reopen confirmed needs.
- **[OPEN]** Shared alias authority, query/context retention under A-3, and the owner of permitted-use input remain bounded dependencies; personal client aliases and source-authorized disclosure are the specified provisional behavior.
- **[OPEN]** Architecture must validate packaging/push support, source-app links, and real client enrollment/delivery paths; pre-live/acceptance owners must revisit A-1–A-6 at their stated checkpoints. No missing implementation evidence becomes a capability promise.
- **[OPEN]** UX-18 field collection, source namespaces, task-role/machine mappings and counter semantics require validation for each client/source. The user has confirmed their visibility, not a collector, storage schema, identity service, historical backfill or load-balancer design.
- **[OPEN: UX-19–24]** Validate read/load/use instrumentation, audit coverage/retention, source-to-column mappings, dependency evidence and client-location observation per source. Full-system audit is the requested target; no initial-slice limit or immutable-storage/database design is selected.
- The additional live-data sample is separate from the illustrative references and does not establish pilot success or historical skill/memory usage.

Original **A-1–A-6 remain unconfirmed**. Their exact semantics, owner, and revisit condition are in the [source extraction](.working/source-prd.md#exact-tagged-assumptions--remain-proposals), original [PRD assumptions index](../../prds/prd-owl-mast-2026-11-05/prd.md), and [.memlog.md](.memlog.md); this contract does not replace them. A-1 concerns default delivery eligibility; A-2 withdrawal/quarantine; A-3 collected-content defaults; A-4 existing publications after disabling promotion; A-5 enrollment step ceiling; A-6 minimum proof cases.

| Resolved UX question | Confirmed decision |
|---|---|
| **UX-Q1 / UX-08 — knowledge entry** | The agent searches when it needs knowledge. This does not resolve A-1 eligibility, select storage, or authorize execution. |
| **UX-Q2 / UX-09 — promotion authority** | Project-designated maintainers handle exceptions/manual review; source access and publication authority remain separate. |
| **UX-Q3 / UX-10 — push interruption** | Every observed work update triggers push by default. No silent attention-only substitution or digest. Actual platform delivery remains to be validated. |
