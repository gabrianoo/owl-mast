# Validation Report — Owl Mast

- **DESIGN.md:** [visual contract](DESIGN.md)
- **EXPERIENCE.md:** [behavior contract](EXPERIENCE.md)
- **Run date:** 2026-11-05
- **Review model/settings:** Claude Opus 5.5, Ultrathink; all four selected lenses.

## Review synthesis

The independent reviews found a structurally sound pair that preserves confirmed choices and A-1–A-6, but required bounded fixes before finalization. The original findings include one critical token gap and nine high findings across scope, identity, notifications, permissions and focus behavior. These counts describe the reviewed drafts, not remaining defects or unique deduplicated issues.

The author applied or explicitly adapted every finding below. Editorial review adds 23 structure rows (18 changes, 5 preserve) and 21 prose rows, kept unranked. This is author remediation with static and visual-reference checks, not an independent post-fix approval, a usability test, WCAG conformance, source integration or a pilot success claim. Original reports and pre-edit spine snapshots remain available.

## Original category verdicts

- 1. Flow coverage — adequate
- 2. Token completeness — thin
- 3. Component coverage — adequate
- 4. State coverage — adequate
- 5. Visual reference coverage — adequate
- 6. Bloat and overspecification — adequate
- 7. Inheritance discipline — adequate
- 8. Shape fit — strong

## Findings by original severity

### Critical (1)

#### T1 · 2. Token completeness — Agent identity colors have no tokens, hex values, dark pairs, or contrast targets.

Original source: [review-rubric.md](review-rubric.md). Original locations refer to the reviewed snapshot.

D:162 and E:90 require a user-changeable colored marker. E:166 requires an "accessible color palette," and D:79 defines no identity color. Mocks fill the gap three ways:
  - host `--chart-1` through `--chart-4` in `connections.html`, `focus.html`, and `daily-work.html`
  - literal `#9F8CEB` and `#C7A06D` in `knowledge-detail.html:42`, with no dark pair, measuring 2.47:1 and 2.11:1 on light `secondary-surface` (2.83:1 and 2.42:1 on `card`), below the 3:1 boundary target if the marker is meaningful
  - "Blue / Cyan / Amber" in the `connections.html` color field, which reuses hues D:115–118 reserves for orientation, knowledge, and attention

  This also violates D:122 ("do not… introduce unmeasured accent tints") and undermines D:162's rule that personal color never implies status. Rubric rule applied: missing hex is critical, and this affects every `agent-chip` on every surface. *Fix:* add a [D]/[P] token family such as `agent-identity-1…n` with `-dark` pairs, hues distinct from semantic roles, and a measured marker target. Reference it from `agent-chip` and align the S5 picker. Palette contents remain delegated designer proposals; alias ownership is handled in C1.

**Disposition:** Applied: four dedicated identity token pairs, diamond markers, neutral fallback and named picker; all 16 identity contrast checks pass.

### High (9)

#### F1 · 1. Flow coverage — Focus has two incompatible default scopes.

Original source: [review-rubric.md](review-rubric.md). Original locations refer to the reviewed snapshot.

E:44 says company context is explicitly selected and "not an automatic cross-project default." E:254 says Focus shows work "within his authorized project scope." `focus.html:173` defaults to "Both permitted projects," and its summary reports "5 assigned tickets across 3 epics" across Syntelligence and Movesion. E:150 makes the spine win, so a builder following it could hide the cross-project concurrency that UX-12 exists to show; a builder following the mock would ship an aggregate the IA forbids as a default. *Fix:* add one sentence to S10 (E:57) and J8 step 1 (E:254) choosing a labeled [P] default. Recommended: Focus may open on all authorized projects as an explicit, visibly labeled aggregate, with project and source on every card. Add this exception to E:44.

**Disposition:** Applied: IA and J8 explicitly propose all authorized projects as the labeled Focus exception; project sections and filter remain visible.

#### F2 · 1. Flow coverage — "Observed work update," the push trigger, is undefined, and the push controls use conflicting terms.

Original source: [review-rubric.md](review-rubric.md). Original locations refer to the reviewed snapshot.

UX-10 is preserved at E:40, E:245, and E:268, but nothing lists which events count. J7 step 3 (E:247) routes notifications to S2, S4, or S6, which implies knowledge and promotion events may notify even though the decision says "work update." S1's filters also include Knowledge (`daily-work.html`, Recent updates). S9 promises "category choice" (E:56), J7 says "follow/notification scope" (E:245), and `notifications.html` offers only followed projects and a generic-preview option. A category control could recreate the attention-only filter that UX-10 rejects, and architecture has no event classes to design against. *Fix:* add a short [P] event table to S9 or J7 listing each event class, whether it counts as a work update under UX-10, and its destination. Replace "category choice" with the controls actually intended. Keep every-update as the default and platform delivery as an implementation validation.

**Disposition:** Applied: event table defines work changes, separate knowledge/system categories, default-enabled preferences, destinations, replay handling and authorization.

#### C1 · 3. Component coverage — Alias rendering has no fallback or identity level.

Original source: [review-rubric.md](review-rubric.md). Original locations refer to the reviewed snapshot.

E:90 defines aliases as this viewer's personal display preferences, and D:162 makes an owl name part of every `agent-chip`. Nothing specifies what a viewer sees for an agent they have not named, including a colleague's agent, which SC-1 depends on. Nothing specifies whether an alias attaches to a client enrollment, a client-project pair, or a run, or how invalid, duplicate, or failed saves behave. Illustrative fixtures show the ambiguity: "Tawny" is a client-project identity in `connections.html` (`CL-SYN-01`), a run `CL-17` initiated by Ahmed in `usage.html`, and run `CL-21` on Mohamed's work in `work-detail.html`. *Fix:* add a [P] rule to E:90 and D:162:
  - the identity level an alias attaches to
  - the unaliased display, such as fixed type label plus stable short ID and a neutral marker
  - name validation and whether duplicates are allowed
  - reset behavior
  - a save-failure entry in the S5 state row (E:115)

  Keep shared naming authority explicitly unresolved, as E:90 already says.

**Disposition:** Applied: viewer-local client aliases, fixed type/ID fallback, length validation, duplicate disambiguation, reset, failure and revocation rules.

#### PK-1 · Permissions and knowledge lifecycle — Permission-filtered totals must either look complete or reveal that records are hidden

Original source: [review-permissions-knowledge.md](review-permissions-knowledge.md). Original locations refer to the reviewed snapshot.

**Location:** `EXPERIENCE.md:85` (`work-summary`: "Count authorized data only; show partial coverage"), `:111` (no hidden-source counts), `:117`, `:156` (incomplete child scope "prevents a complete-looking rollup"), `:260` ("never reveal hidden titles or counts"). `DESIGN.md:157–159`, `:164`. `mockups/daily-work.html:210`, `mockups/focus.html:237`, `mockups/usage.html:124`. Source: PRD FR-6 line 108, NFR-1 line 249, NFR-2 line 250.

**Evidence:** The contract requires partial coverage to show and also forbids disclosing hidden records, but never says how both hold when the partiality comes from permissions. The references differ:

- Daily Work states an absolute: "Denominator: five tickets in this epic", under "Your owned scope".
- Focus says "permitted epic tickets", but only inside a collapsed disclosure, and its visible label is "Epic: 3/5 tracker-closed".
- Usage places "only permitted … records" inside a collapsed disclosure.

**Impact:** A viewer who cannot read 3 of 8 child tickets sees "5 of 5 child tickets closed", an apparently finished epic. If an "incomplete" label appears only when something is actually hidden, that label itself discloses hidden records. SC-1's climax ("can explain what is closed") then fails silently, and two viewers get different figures with no signal why.

**Minimal fix:** Add one rule to `work-summary`, `epic-group`, and `usage-breakdown`:

- Every aggregate carries a constant, always-visible basis label, such as "Counted from records you can access". It appears identically whether or not anything is hidden, so it reveals nothing and never implies a whole-source total.
- A permission-scoped rollup never presents as "all closed" or "complete" without that label.
- Source-collection gaps (FR-3) keep their own conditional "incomplete" label, separate from this basis label.
- Search omission notices (`:160`) count only eligible results that were truncated, never results filtered out by permission.
- Change the Daily Work denominator copy to match.

**Disposition:** Applied: constant accessible-record basis on aggregates, separate collection-gap warnings, no permission-omission counts.

#### PK-2 · Permissions and knowledge lifecycle — A project-scoped lesson has no reader check when it derives from restricted same-project material

Original source: [review-permissions-knowledge.md](review-permissions-knowledge.md). Original locations refer to the reviewed snapshot.

**Location:** `EXPERIENCE.md:160` (project scope; "permitted references"), `:95`, `:114` ("no inaccessible origin excerpt"), `:98`, SC-2 `:213–216`. `mockups/knowledge-detail.html:38`, `mockups/knowledge.html:42`. Source: PRD FR-17 lines 209–211, FR-21 line 244, FR-12 line 161.

**Evidence:** The contract gates excerpts and references, not the lesson itself. S4's mock says "Visible in Syntelligence · Original source access is checked separately", and S3's says "Source access is required to inspect the supporting record", so the body's visibility is decided at project level. The restricted-content checks in FR-12 apply only to company promotion. Nothing equivalent applies when Hermes or Notion capture produces a project lesson from a restricted Jira record or a narrowly shared Notion page.

**Impact:**

- SC-2's Mohamed → Ahmed path can deliver restricted text to a same-project agent, or show it in S3. This is the FR-17 case of a same-project user lacking source access, reached through a derivative rather than a preview. It also covers the case where source permission is removed after indexing.
- Evaluation basis and check-reason text are derived content with the same exposure.
- `promotion-review` is internally unresolved. A maintainer must "inspect exact candidate content", yet "designation does not grant source access". The contract does not say what happens when the candidate contains material that maintainer may not read.

**Minimal fix:** State that project scope is a ceiling, not a read grant.

- A version's title, body, evaluation basis, and check reasons are disclosed, delivered, or returned in search only to a person or agent authorized for the material they derive from, or after a version has been evaluated as safe for the wider project audience.
- If this cannot be determined, withhold the version (fail closed) under the existing S3/S4 and SC-2 failure copy.
- Add an S6 state: "This review needs a maintainer with access to its source." No decision is recorded and the item stays project-scoped.

This keeps the project-default confirmed direction and selects no mechanism.

**Disposition:** Applied: whole derivative payload requires source-derived authorization or an evaluated wider-audience version; inaccessible maintainer review has a safe no-decision state.

#### PK-3 · Permissions and knowledge lifecycle — A company publication has neither its own identity nor a defined view for readers in another project

Original source: [review-permissions-knowledge.md](review-permissions-knowledge.md). Original locations refer to the reviewed snapshot.

**Location:** SC-3 `EXPERIENCE.md:226–229`, `:95`, `:114`, `:162`. `DESIGN.md:167`, `:170`. `mockups/promotion.html:41–42`, `mockups/knowledge-detail.html:39`. Source: PRD FR-12 lines 162–164, A-2 line 172, SM-5 line 278.

**Evidence:**

- S6's "Exact proposed company content" differs from S4's v3 body: it drops "and inspect its reported result" and the third sentence. Yet the record is labeled "Evaluated source version SYN-K07 · v3" and the control says "Approve v3 for this audience". What was approved is therefore not the exact content of v3, despite FR-12's "exact version".
- `knowledge-record` shows evaluator or policy, basis, and origin with no audience distinction, and the ID format embeds the source project key.
- No surface or reference shows SC-3's climax: how a reader or agent in the other project sees the published item.

**Impact:** A Movesion reader of the published item could see "SYN-K07", Syntelligence's evaluator, a basis describing source records, and lineage. All of that is provenance FR-12 reserves for authorized readers. Withdrawal, supersession, receipts, and reuse also have no unambiguous version to attach to, and A-2's "promoted derivatives" has no representation.

**Minimal fix:**

- Define a publication as its own versioned record: publication ID without the source project key, exact text, audience, policy version, publishing person or automation identity, and a restricted reference to the originating version.
- Bind approval and automatic evaluation to that record, and relabel the control to approve that publication version.
- Add a "company reader" field list to S4: content, publication version, company scope, applicability, freshness, and evaluated-by-policy or reviewed-by-person kind. Origin project, source ID, named evaluator, basis, and other projects' receipts appear only to authorized readers.
- Add a visual reference for this state. Whether the published text may differ from the source is a product detail; if it may, the record above carries it.

**Disposition:** Applied: independent CMP-K04 publication version binds exact text and audience; company-reader state excludes restricted origin/evaluation/receipt fields.

#### PK-4 · Permissions and knowledge lifecycle — After withdrawal, human-read surfaces can keep showing the withdrawn content

Original source: [review-permissions-knowledge.md](review-permissions-knowledge.md). Original locations refer to the reviewed snapshot.

**Location:** `EXPERIENCE.md:114` ("Conflicting/superseded/withdrawn … content carries lifecycle state"), `:162`, `:229`, `:96`, `:94`, J7 `:247`. `mockups/daily-work.html:272`, `:287`. No reference shows a withdrawn state (zero occurrences of "withdrawn" in `knowledge.html`, `knowledge-detail.html`, `daily-work.html`, `notifications.html`). Source: PRD FR-13 lines 170–174, FR-18 line 218.

**Evidence:** The withdrawal contract covers future agent delivery and external copies. For Owl Mast's own surfaces, the only statement is that content "carries lifecycle state", which reads as still displayed with a label. Feed rows embed the lesson title ("Stable account identifiers · v3"), and S9's return can land on S4.

**Impact:** Take an automatically published version withdrawn because its text exposed a customer detail. Former-audience readers can still read the title or body through S3, S4, S6 history, feed rows, and old notification links. That contradicts FR-18 ("cannot leave excluded content in snippets, caches, exports, or derived summaries"). Separately, a receipt for that version keeps looking healthy, so a recipient cannot tell that guidance they received has since been withdrawn.

**Minimal fix:** Add a post-withdrawal row covering S3, S4, S6, the activity feed, notification return, and receipts:

- Former-audience readers see the lifecycle state, plus a neutral reference when the withdrawal reason concerns safety or permission, without the body or title.
- Authorized maintainers or auditors see the audit record.
- Feed rows and receipts for that version show "since withdrawn" or "since superseded".
- Superseded content may stay readable.

Keep A-2's exact retention and retrieval default open, with this as the state contract it resolves.

**Disposition:** Applied: withdrawn payloads are suppressed across human-read surfaces and receipts; neutral lifecycle return and restricted audit are separate. A-2 remains open.

#### A11Y-01 · Accessibility and responsive behavior — Live refresh and removal of focused content are only partly specified

Original source: [review-accessibility.md](review-accessibility.md). Original locations refer to the reviewed snapshot.

**Type:** Contract
**Location:** `EXPERIENCE.md:94` (`activity-list`), `:107` (State baseline), `:136` (Accessibility Floor), `:245` (every update pushes). No reference shows a refresh state: a search for "New updates" across all ten surfaces finds nothing.

**Evidence:** "Preserve reading position" and the "New updates" affordance apply only to `activity-list`. `:136` forbids announcing each event and moving focus on refresh, which is right, but three things remain undefined:
- how a screen-reader user learns that buffered updates exist;
- where focus goes after "New updates" is activated;
- what happens on S1 summaries, S2 open evidence, S7 totals and S10 boards when data refreshes.

`:107` also says expired or revoked access "removes restricted data", without saying where focus goes if the focused element was part of that data.

**Impact:** keyboard and screen-reader users can have focus silently dropped to the document start when a record is revoked or refiltered. Open evidence may collapse during a poll. Non-visual users may never learn that buffered updates are waiting. Auto-updating content without user control is also relevant to WCAG 2.2.2, and focus order to 2.4.3.

**Minimal fix:** add this rule to Accessibility Floor, for all of S1–S10:

> Refresh never reorders, collapses, or removes content under focus or the reading position without a user action. New list items wait behind "New updates", announced through one coalesced polite status ("3 new updates"), not per event. Activating it moves focus to the first new item. Open disclosures and scroll position survive refresh. If the focused element must be removed for permission or scope reasons, move focus to the nearest surviving section heading or the neutral `state-message`, and announce it politely without naming restricted content.

**Disposition:** Applied: all-surface refresh buffering, polite coalesced announcement, disclosure/reading-position preservation and safe focus after revocation.

#### A11Y-02 · Accessibility and responsive behavior — Arrival focus, announcement and return path are undefined for notification and contextual entry

Original source: [review-accessibility.md](review-accessibility.md). Original locations refer to the reviewed snapshot.

**Type:** Contract, with a Reference note
**Location:** `EXPERIENCE.md:107` (focus "returns to the trigger after detail closes"), `:119`, `:124`, `:148` (explicit Back only for `<600px`, S2/S4/S6), `:247`, `:248`; `DESIGN.md:142` (temporary overlaid detail); `mockups/notifications.html:10` (return card and unavailable note).

**Evidence:** a notification deep link has no trigger to return to and may have no in-app history. The spines do not define:
- initial focus or title change on arrival;
- where "this has changed" sits relative to the heading;
- the Back destination when no history exists;
- whether a wide-layout S2 overlay is modal, with focus moved in and the background inert.

In the references:
- The S9 return card sits inside Preferences, with `aria-current` on Preferences. There is no arrival state on an S2/S4/S6 destination.
- No reference has a Back control (zero matches).
- The S9 unavailable note says "Return to your workspace" with no control to do so.
- The resolved status (`<p class="status success">`) comes before the `<h3>`, so heading navigation skips it.

**Impact:** a screen-reader user opening a push on a phone can land with focus at the start of the document or nowhere defined, hear no page change, and miss that the request is already resolved. That is the climax of J7. A revoked target can also become a dead end. Relevant to WCAG 2.4.3 and 4.1.3.

**Minimal fix:** add this rule to Interaction Primitives:

> On any route or contextual entry, update the page title and move focus to the destination `h1`. For notification entry, the `h1` or the first content after it states the current state and notification time. Back returns to the prior location, or to S1 in the same authorized project when there is no history. The neutral unavailable state has a working link to the user's work and receives focus at its heading. A temporary overlay is a named modal dialog with focus inside, an inert background, and focus returned to its trigger.

The Back rule applies wherever a contextual destination has no surrounding navigation, not just below 600px.

---

**Disposition:** Applied: destination title/h1 focus, current state/time, Back fallback, safe return link, modal focus contract and explicit notification arrival fixture.

### Medium (34)

#### F3 · 1. Flow coverage — Two user-requested behaviors have no flow.

Original source: [review-rubric.md](review-rubric.md). Original locations refer to the reviewed snapshot.

Alias and color editing (UX-15) and contextual cost drill-down (UX-17) appear only in component rows and semantics (E:90, E:99, E:166, E:168). S5's row (E:52) omits appearance settings, S2 and S10 (E:49, E:57) omit Usage & cost, and J6 enters only from a project or company scope (E:236). Stories have no sequence or climax to build from. *Fix:* add one step or a short branch: J2 or a J2 appendix for appearance editing, and a J6 entry from a ticket or epic summary with scope retained. Add both to the IA rows, tagged [P].

**Disposition:** Applied: S2/S5/S10 IA and J2 appearance/J6 contextual-cost branches now cover the requested behavior.

#### F4 · 1. Flow coverage — FR-15's company view has no flow, visual, or surface state outside S7.

Original source: [review-rubric.md](review-rubric.md). Original locations refer to the reviewed snapshot.

FR-15 covers progress, agent activity, attention, knowledge, and usage. S1 and S10 claim FR-15 (E:48, E:57), but SC-1 and J1 are project-scoped, only J6 mentions company scope (E:236), and no mock shows a labeled company aggregate. *Fix:* add a J6 or S1 branch that selects company context and shows the aggregate label, partial coverage, and drill-down context. Alternatively, state which surfaces have company scope in V1.

**Disposition:** Applied: named company-overview branch and navigation.html show progress, agent activity, attention, knowledge and Usage entry with permission-safe counts.

#### T2 · 2. Token completeness — Component frontmatter contradicts component prose for two load-bearing text colors.

Original source: [review-rubric.md](review-rubric.md). Original locations refer to the reviewed snapshot.

`attention-item` sets `textColor: {colors.attention}` (D:75), but D:158 says "Body remains main text." `state-message` sets `{colors.secondary-text}` (D:90), but D:113 requires main text for permission and failure messages, and E:101 uses this component for denied and failure states. Code that mirrors the tokens will implement the wrong hierarchy. *Fix:* set both text colors to `{colors.text}`. Express amber as a marker property on `attention-item`.

**Disposition:** Applied: attention-item and state-message use main text; attention color marks the reason.

#### C2 · 3. Component coverage — Recurring UI elements have no component contract.

Original source: [review-rubric.md](review-rubric.md). Original locations refer to the reviewed snapshot.

Mocks and spines rely on these without rows:
  - person, view, and filter switches (S1 My work/Mohamed, S1 update filters, S10 By epic/Together, S3 lifecycle filters; E:91, E:94)
  - lifecycle and status badges (`knowledge-detail.html`, `promotion.html`)
  - disclosures (native details on every surface; E:124 gives only general behavior)
  - notification preview (`notifications.html`)
  - secondary actions ("Keep project-scoped" in `promotion.html`; D:174 defines only a filled primary action)

  Parity checks pass only because these were never named, so downstream teams will define them inconsistently. *Fix:* add `filter-control`, `status-badge`, `disclosure`, and `notification-preview` to frontmatter and both tables, and add a secondary `action-control` variant. Alternatively, explicitly classify any of these as native primitives with stated rules.

**Disposition:** Applied: native filters, switches, badges, disclosures, previews and secondary actions explicitly inherit named component contracts.

#### S1 · 4. State coverage — System quarantine is not a user-visible lifecycle state.

Original source: [review-rubric.md](review-rubric.md). Original locations refer to the reviewed snapshot.

FR-13 says the system can quarantine a version. E:160's distinct-state list and E:114's S4 row omit it, leaving only passing mentions of quarantine at E:230 and E:270. `knowledge-record` (E:95) has no way to distinguish a system quarantine from a maintainer withdrawal. *Fix:* add Quarantined, with its system origin, to E:160 and E:114. Keep retrieval and re-publication semantics deferred to A-2.

**Disposition:** Applied: system quarantine is a distinct visible lifecycle state; A-2 effects remain provisional.

#### V1 · 5. Visual reference coverage — The proposed navigation appears in no reference.

Original source: [review-rubric.md](review-rubric.md). Original locations refer to the reviewed snapshot.

E:44 defines five primary destinations plus Preferences. D:134 and E:146 commit to a rail at ≥1024px and a labeled menu below that. Actual mock shells differ:
  - `daily-work.html:194` has no navigation, although J8 starts "From the landing page" (E:254)
  - `focus.html:170` shows two items and `usage.html:101` three
  - `knowledge.html`, `knowledge-detail.html`, and `promotion.html` show "Workspace / Knowledge," and "Workspace" is not an IA term
  - `notifications.html` shows two items and `connections.html` shows sub-navigation
  - `work-detail.html:105` shows a breadcrumb

  E:150's "demonstrate the layouts" and D:177's "uses the defined components" overstate this for `surface-navigation`. The spine controls, but the most cross-cutting shell has never been drawn. *Fix:* add one shared shell reference at wide and compact widths, or narrow both claims and note that navigation is spine-only.

**Disposition:** Applied: navigation.html supplies the complete rail, compact menu and contextual/company branch; individual mocks remain focused compositions.

#### V2 · 5. Visual reference coverage — The host-theme caveat covers one mock, but the dependency affects all ten.

Original source: [review-rubric.md](review-rubric.md). Original locations refer to the reviewed snapshot.

D:136 discloses it only for `daily-work.html`. `daily-work`, `focus`, `connections`, `notifications`, and `administrator-setup` use undefined host variables almost entirely without fallbacks (94–116 uses). `work-detail` and `usage` fall back mostly to system colors; `knowledge`, `knowledge-detail`, and `promotion` fall back to DESIGN hex for the core palette. The gallery copies its parent's computed variables, which are empty outside a host. By CSS rules, panels in the first five lose fills and borders when opened directly (inferred; not rendered). This matches the brief's known boundary but is not disclosed to spine readers. *Fix:* move the caveat to D:177 and E:59, naming which rendering context the references need. Optionally inject a standalone DESIGN token block so references are usable in architecture and story work.

**Disposition:** Applied: exact standalone fallback layer in every reference; host rendering limitation disclosed for the complete set.

#### V3 · 5. Visual reference coverage — Key lifecycle actions and states have no reference.

Original source: [review-rubric.md](review-rubric.md). Original locations refer to the reviewed snapshot.

S6's row promises withdrawal and supersession (E:53), and SC-3 steps 6–7 depend on them along with mode changes. `promotion.html` shows modes, one exception, and one manual review, with no withdraw, supersede, or mode-change preview. `knowledge-detail.html`'s only alternate is unavailable, despite E:114's conflicting, superseded, withdrawn, and version-unknown states. D:174 and E:138 specify destructive styling and confirmation, but nothing shows them. *Fix:* add static alternates in native disclosures, or state in E:59 that these states are spine-only.

**Disposition:** Applied: knowledge/promotion references show withdrawal, supersession, quarantine, audit and mode-change alternatives.

#### V4 · 5. Visual reference coverage — Epic progress is displayed three different ways.

Original source: [review-rubric.md](review-rubric.md). Original locations refer to the reviewed snapshot.

E:156 requires the label "child tickets closed," and Voice uses "3 of 5 child tickets closed" with no percentage (E:69). `daily-work.html:210` makes "60%" dominant with "3 of 5 tickets closed," despite D:185's warning about big percentages. `focus.html` shows "Epic: 3/5 tracker-closed" with a bar. SC-1 step 2 tags "completion percentages for… tickets/epics" as [U: UX-05] (E:194), while UX-07 defines only tickets, leaving epic percentages unresolved. `daily-work.html:210` also labels "Your owned scope" while its basis says "five tickets in this epic," blurring the distinction J8 requires (E:256). *Fix:* state in E:156 whether a derived percentage may accompany the fraction, keeping the proposal labeled [P] and the fraction dominant. Use one label across S1, S2, S10, and Voice, and correct the S1 scope text.

**Disposition:** Applied: epic fraction and child-tickets-closed label dominate; optional percentage and record-set basis are explicit.

#### I1 · 7. Inheritance discipline — The PRD's "knowledge maintainer" role is never mapped.

Original source: [review-rubric.md](review-rubric.md). Original locations refer to the reviewed snapshot.

That exact term has zero occurrences in either spine (PRD §2, FR-12, FR-13). E uses "project-designated maintainer" and "maintainer" (E:98, E:224, E:229). UX-09 confirms exceptions and manual review, while the PRD role also covers policy configuration and withdrawal. E:100 and E:225 never say who may change the mode. Architecture could model one role or two. *Fix:* add one line, preserving the user's term and assigning no real people: "A project-designated maintainer is the PRD's knowledge maintainer for that project," or state explicitly if they differ. Name that authority in the S6 policy rule.

**Disposition:** Applied: project-designated maintainer maps to the PRD knowledge-maintainer role for that project; policy/lifecycle authority remains authorization-bound.

#### PK-5 · Permissions and knowledge lifecycle — A generic push can still reveal a restricted update, and the "non-generic" preview is undefined

Original source: [review-permissions-knowledge.md](review-permissions-knowledge.md). Original locations refer to the reviewed snapshot.

**Location:** J7 `EXPERIENCE.md:245–246`, `:250`; `mockups/notifications.html:10`. Source: NFR-1 line 249, FR-18 line 218.

**Evidence and impact:**

- "Rights are checked before any notification disclosure" can be read as: send "Owl Mast has an update" for every project event and withhold only the detail. The arrival and timing of a push for a record the recipient cannot read is an inference-bearing signal.
- The mock's "Use a generic preview" checkbox implies a richer mode, but no contract defines its content. With every-update push, it could put customer titles on lock screens in copies the spine admits cannot be recalled.

**Minimal fix:** Keep UX-10 and add three rules:

- Push eligibility is evaluated per recipient and per source record at send time, including when the recipient's device session has ended. An unauthorized or unverifiable update produces no push at all, not a generic one.
- This withholding is not throttling or a digest, and the feed follows the same rule.
- Either remove the preview checkbox or list exactly which fields a non-generic preview may carry.

**Disposition:** Applied: unauthorized/unverifiable events send no push, even generic; only generic preview is currently proposed.

#### PK-6 · Permissions and knowledge lifecycle — Receipts have no boundary for colleagues, other projects, or query text

Original source: [review-permissions-knowledge.md](review-permissions-knowledge.md). Original locations refer to the reviewed snapshot.

**Location:** `EXPERIENCE.md:96`, `:114`, `:229`; `DESIGN.md:168`; `mockups/knowledge-detail.html:44`; `mockups/daily-work.html:287`. Source: FR-11 line 152, FR-13 line 170, A-3 line 217.

**Evidence and impact:**

- SC-3 asks maintainers to see earlier deliveries "subject to permissions", but no state exists for recipients outside the maintainer's access. They either see cross-project recipients or get no sense of withdrawal impact.
- The mock adds "Requested context: Syntelligence Jira · SYN-42 · Check review", beyond FR-11's recipient, project, item/version, and time. For a cross-project delivery, this would show one customer's work to another project's maintainer.
- On-demand search also creates a new data flow, agent query text, whose retention and visibility are undefined.
- Daily Work's "A sync lesson reached Eagle" shows a colleague's receipt with the lesson title, with no stated link to S4's separate recipient-visibility check.

**Minimal fix:**

- Apply `delivery-receipt` visibility wherever a receipt appears, including feed rows and push.
- Requested context and query text are gated to the recipient's project access. Their retention is undecided, so mark it [OPEN] under A-3 rather than implying they are stored.
- Add a state showing the maintainer a neutral statement that deliveries outside their access exist under the publication's permitted audience, without identities or task context. The publication's audience is already known to its maintainer, so this reveals nothing new.

**Disposition:** Applied: receipt visibility follows recipient-project access everywhere; constant visibility note avoids hidden identities/counts; query/context retention remains OPEN under A-3.

#### PK-7 · Permissions and knowledge lifecycle — Personal aliases are undefined for other people's agents, and the references contradict the personal scope

Original source: [review-permissions-knowledge.md](review-permissions-knowledge.md). Original locations refer to the reviewed snapshot.

**Location:** `EXPERIENCE.md:90`, `:166`; `DESIGN.md:162`. `mockups/daily-work.html:241`, `:287`; `focus.html:210–213`; `connections.html:10`; `administrator-setup.html:10`; `work-detail.html:143`; `knowledge-detail.html:42`, `:44`; `usage.html:118–119`.

**Evidence:** The contract says aliases are per-viewer preferences, and DESIGN says "User-chosen owl display name". It does not say what a chip shows for an agent the viewer did not name, or whose clients S5 lists. The fixtures show one alias on different agents and people:

| Alias | Depicted as |
|---|---|
| Eagle | Ahmed-initiated Movesion run CX-4 in Focus; Mohamed's Syntelligence Codex session in Daily Work |
| Barn | Movesion client in Connections and Focus; Mohamed's Syntelligence Claude in Daily Work |
| Tawny | Ahmed's CL-17 in Focus and Usage; Mohamed's CL-21 in Work Detail; Mohamed's contributor agent in Knowledge Detail |

S8 also shows contributors' aliases to an administrator, and alias text is embedded in feed titles.

**Impact:** If one person's alias renders for another viewer, free text from one person crosses audiences, and the same name can point to different agents. Evidence reading then becomes unreliable (FR-4). Implementers would also have to guess the shared-naming authority the spine leaves unspecified.

**Minimal fix (designer proposal, no shared-naming decision):**

- A viewer sees only their own alias for a client. Otherwise the chip shows the fixed type label plus a stable short identifier.
- Another person's alias is never rendered in S1–S10, push, receipts, or audit.
- Alias settings list only clients the viewer may currently see, and drop out when access is revoked.
- Keep S5 scoped to the viewer's own clients unless a separate shared-workspace view is defined (FR-15).
- Correct the fixtures so each alias names one client throughout.

**Disposition:** Applied: aliases are viewer-local client preferences; other viewers use fixed type/ID. Fixtures separate client identities from runs and align ownership.

#### PK-8 · Permissions and knowledge lifecycle — Contextual cost lacks a viewer rule and an epic scope, and its fixtures violate its own attribution rule

Original source: [review-permissions-knowledge.md](review-permissions-knowledge.md). Original locations refer to the reviewed snapshot.

**Location:** `EXPERIENCE.md:99`, `:117`, `:120`, `:168`. `mockups/usage.html:118–119`, `focus.html:194`, `:210`, `daily-work.html:210–211`, `:236`. Source: FR-16 lines 197–201, FR-17 line 207.

**Evidence and impact:**

1. S10 applies S1/S2 access to each card, so anyone who can read a ticket gets its cost. No rule says that allocation or bill classes need separate authority, or that a share of a company-wide subscription could let a viewer infer the other project's share by subtraction. S7's residual rule isn't stated for allocation bases.
2. Focus's epic cost doesn't say whether it covers the whole permitted child set or only the viewer's assigned subset, though Focus distinguishes those for closure counts.
3. False state: Focus and Daily Work show SYN-42 as "Usage & cost: Unavailable … No linked usage records", while S7 shows SYN-42 with 0.60M tokens and $3.60 from an "explicit session work reference" on the same date.
4. False state: S7 assigns all of CL-17's session to SYN-42, while Focus says that one session links both SYN-42 and SYN-67. Under `:99`, "ambiguous allocation stays unassigned". S7 also assigns SYN-67 to Mohamed's Snowy CX-16, while Focus links it to Ahmed's CL-17 and Daily Work calls it "Define project sync rules".

**Minimal fix:**

- Contextual summaries show only classes the viewer may see in S7.
- Allocation or bill figures never expose a basis from which an inaccessible share can be derived.
- Each epic amount names its record set.
- Align the three references: one illustrative SYN-42 state and an unassigned or explicitly split shared session.

**Disposition:** Applied: contextual class access equals S7; allocation cannot expose inaccessible residuals; epic sets are named and shared session usage remains unassigned.

#### PK-9 · Permissions and knowledge lifecycle — The "Shared run" label and its evidence text can reveal hidden work

Original source: [review-permissions-knowledge.md](review-permissions-knowledge.md). Original locations refer to the reviewed snapshot.

**Location:** `EXPERIENCE.md:92`, `:256`, `:260`; `DESIGN.md:164`; `mockups/focus.html:210`, `:223`, `:234`.

**Evidence and impact:** A "Shared" marker and "One confirmed session links SYN-42 in SYN-10 and SYN-67 in SYN-20" assume the viewer can see both sides. For a viewer with only SYN-10, the marker reveals another linked item and the text names it. The rule at `:260` covers hidden titles and counts, not this label or a run linked across projects.

**Minimal fix:** Show the marker, references, and shared-run labels only for links the viewer can read; otherwise render the run as an ordinary run. A run's other-project links never appear in the other project's scope. Deduplicated totals count only records the viewer can access.

**Disposition:** Applied: shared labels/counterparts require readable same-project links; inaccessible counterparts produce ordinary run presentation.

#### PK-10 · Permissions and knowledge lifecycle — Maintainers own exceptions, but the exception has no resolution path

Original source: [review-permissions-knowledge.md](review-permissions-knowledge.md). Original locations refer to the reviewed snapshot.

**Location:** `EXPERIENCE.md:40`, `:53`, `:227`, `:232`; `mockups/promotion.html:41`. Source: UX-09, FR-12 line 161.

**Evidence and impact:** The mock tells the maintainer to "Confirm permitted company use before evaluating this version again", and also that "A human decision cannot bypass the required checks". Nothing says where that confirmation is recorded, who may give it (the maintainer or a project data owner), or what outcomes exist. The confirmed exception-handling job therefore has no defined action. Under the preferred automatic mode, this is the main human touchpoint. A version whose lineage carries a withdrawal also needs a defined outcome. Without one, implementers may build an override, which the spine forbids, or a dead end.

**Minimal fix:** Enumerate exception outcomes on `promotion-review`:

- Keep project-scoped with a recorded reason.
- Correct the content, creating a new version that gets a new evaluation.
- Request re-evaluation after the missing permission or policy input is recorded by its authorized owner.

Mark the owner of the use-permission input as [OPEN] instead of implying it is the maintainer.

**Disposition:** Applied: keep project-scoped, correct as new version, or request reevaluation after authorized input; owner remains OPEN and no override bypasses checks.

#### PK-11 · Permissions and knowledge lifecycle — The required quarantine state is missing from the lifecycle model

Original source: [review-permissions-knowledge.md](review-permissions-knowledge.md). Original locations refer to the reviewed snapshot.

**Location:** `EXPERIENCE.md:53`, `:114`, `:160`, `:230`, `:270`; `DESIGN.md:167`; zero occurrences in `knowledge.html`, `knowledge-detail.html`, and `promotion.html`. `reconcile-prd.md:25`. Source: FR-13 line 170, SM-5 line 278.

**Evidence and impact:** FR-13's system quarantine is a requirement outside A-2. A-2 only proposes its effects. The spine's lifecycle list omits quarantined, S4 has no state for it, and no maintainer path or actor record exists. Reconciliation filed it entirely under A-2. SM-5 tests quarantine blocking new delivery, and a system-initiated change with no surface would look like silent disappearance.

**Minimal fix:** Add **Quarantined (system-initiated, with reason and time)** as a distinct state in Knowledge semantics, `knowledge-record`, S3 filters, S4/S6 states, and the maintainer exception view. Leave its exact retrieval effects to A-2.

**Disposition:** Applied: system quarantine appears in semantics, catalog filters, detail and maintainer alternatives; retrieval defaults remain A-2.

#### PK-12 · Permissions and knowledge lifecycle — Withdrawal and receipts don't disclose independent Notion or client access

Original source: [review-permissions-knowledge.md](review-permissions-knowledge.md). Original locations refer to the reviewed snapshot.

**Location:** `EXPERIENCE.md:96`, `:114`, `:162`, `:229`; `mockups/knowledge-detail.html:44`. Source: FR-17 line 211, FR-21 line 245.

**Evidence and impact:** The spine discloses the limit on "earlier copies" but not ongoing independent access: a client with its own Notion access can still read the source page after an Owl Mast withdrawal, and that read produces no receipt. So "withdrawn" can be taken to mean no agent can get it now, and "no deliveries" can be taken to mean nobody read it. The PRD requires these limits to be reported separately.

**Minimal fix:**

- Label withdrawal outcomes "Owl Mast delivery stopped" and add one line noting that direct source or client access is governed separately.
- Label receipts as covering Owl Mast-mediated delivery only, so "No deliveries" isn't read as no reads.
- Whether a withdrawal should also change the Notion page stays with the implementation design, per FR-14.

**Disposition:** Applied: Owl Mast-only delivery and receipt boundaries explicitly distinguish independent Notion/client access and prior copies.

#### PK-13 · Permissions and knowledge lifecycle — Attention items assume captured session text, which the A-3 default wouldn't collect

Original source: [review-permissions-knowledge.md](review-permissions-knowledge.md). Original locations refer to the reviewed snapshot.

**Location:** `EXPERIENCE.md:86`, J1 `:185`; `mockups/daily-work.html:264`, `:279`. Source: A-3 line 217, FR-7 line 116.

**Evidence and impact:** J1 has Ahmed "read the request", and the mock shows a body taken from a "linked Claude session", including for Mohamed's work. A-3's proposed default collects metadata, references, and deliberately submitted knowledge, with raw chat needing explicit enablement. No state covers that default, so building the shown body presumes the unresolved answer, and colleagues read session content before data owners decide.

**Minimal fix:** Add an attention and S2 state: "Request text isn't collected under this project's policy", showing reason, source, time, and the source link (all FR-7 needs). Show captured text only where policy permits. Keep A-3 open.

**Disposition:** Applied: request-text-not-collected state preserves A-3; references show source metadata/link when text collection is excluded.

#### PK-14 · Permissions and knowledge lifecycle — Duplicate and conflict references are a side channel

Original source: [review-permissions-knowledge.md](review-permissions-knowledge.md). Original locations refer to the reviewed snapshot.

**Location:** `EXPERIENCE.md:95` ("Duplicate detection links to existing lineage"), `:51`, `:214`. Source: FR-8 line 130, FR-9 line 137.

**Evidence and impact:** Submitting a lesson that matches a restricted item, or an item in another project, would return a link or a "duplicate" result that confirms the item exists. Conflict exposure has the same risk if the conflicting version isn't visible to that recipient. FR-9's exposure duty has no stated scope limit.

**Minimal fix:**

- Readers and agents see duplicate or conflict references only for versions they can access.
- For anything else, the submission records neutrally ("Saved as a candidate") and the match is routed to an authorized maintainer.
- Two projects' private items are never compared in anything shown to a reader.

**Disposition:** Applied: duplicate/conflict links require access; restricted matches receive neutral candidate acknowledgement and private authorized routing.

#### PK-15 · Permissions and knowledge lifecycle — "Assigned to me" has no identity-mapping guard or state

Original source: [review-permissions-knowledge.md](review-permissions-knowledge.md). Original locations refer to the reviewed snapshot.

**Location:** `EXPERIENCE.md:44`, `:91`, `:120`, `:193`, `:254`. Source: FR-1 line 65, FR-4 line 93.

**Evidence and impact:** Focus and the S1 person filter need one person's identities across two Jira sites, but no contract says how assignment is established. S10 has only "No assignments" as an empty state. An unmapped identity would give a false "nothing assigned" on the page meant to show parallel work, and matching by display name could show another person's work, which FR-1 explicitly rejects.

**Minimal fix:** Attribute assignment only through a source-provided identity or confirmed mapping, never a display-name match. Add a per-source S1/S10 state: "Your identity in this source isn't confirmed; assigned work may be missing." The mapping mechanism stays with architecture.

**Disposition:** Applied: assigned-to-me requires source identity or confirmed mapping, with a distinct unmapped-source state.

#### PK-16 · Permissions and knowledge lifecycle — Reuse verification has no actor, action, or boundary

Original source: [review-permissions-knowledge.md](review-permissions-knowledge.md). Original locations refer to the reviewed snapshot.

**Location:** SC-2 `EXPERIENCE.md:218`, `:96`, `:114`; `mockups/knowledge-detail.html:44`. Source: FR-11 line 153, A-6 line 276.

**Evidence and impact:** "Only then record demonstrable reuse" names no verifier or surface, and `delivery-receipt` has no write action. SM-3's proof therefore can't be recorded from this contract. In the SC-3 case, the task artifact lives in the recipient project, so attaching it to the origin project's S4 would expose it to that project's maintainers.

**Minimal fix:** Define a permitted action on the receipt: an authorized reviewer records verified reuse with the version, artifact reference, and time. The artifact reference is visible only to readers with access to its project; origin-project readers see only "Reuse verified in a permitted project". The sample size stays A-6.

**Disposition:** Applied: authorized reviewer records verified reuse on a receipt with version/artifact/time; artifact visibility follows its project.

#### A11Y-03 · Accessibility and responsive behavior — Identical generic pushes give no way to tell updates apart

Original source: [review-accessibility.md](review-accessibility.md). Original locations refer to the reviewed snapshot.

**Type:** Contract
**Location:** `EXPERIENCE.md:245`, `:246`, `:250`; `mockups/notifications.html:10` ("Owl Mast has an update").

**Evidence:** default every-update push [U] combined with a proposed generic preview [P] produces repeated identical notifications. The S9 reference shows "Opened from the 08:32 notification", but `EXPERIENCE.md` does not require anything equivalent. `:250` dedupes replays but does not require distinct updates to stay distinct at the platform level.

**Impact:** screen-reader users hear the same sentence for every update and cannot judge which matters before opening. Sighted users are in the same position. After opening one, nothing leads to the others. On some platforms, a reused notification identifier would also replace earlier notifications, which conflicts with the no-silent-loss intent.

**Minimal fix:** keep every-update push and the generic default, and add to J7:
- Each distinct source event uses its own notification identity; only replays dedupe.
- Arrival shows the notification time and a labeled link to other updates since then in S1.
- Platform stacking is acceptable only if no update is dropped or summarized away.

**Disposition:** Applied: distinct event notification identities, replay-only deduplication, preserved platform stacking and link to other updates.

#### A11Y-04 · Accessibility and responsive behavior — Interactive chips can nest or overlap; agent-chip interactivity is undefined

Original source: [review-accessibility.md](review-accessibility.md). Original locations refer to the reviewed snapshot.

**Type:** Contract
**Location:** `EXPERIENCE.md:85`, `:86`, `:88`, `:89`, `:90`; `DESIGN.md:161`, `:162`; `mockups/daily-work.html:176` (`.tag-line` gap 7px).

**Evidence:**
- `work-record` and `attention-item` "open" a destination, and `ticket-chip` also opens S2, with no statement of which element is the control. If the row is the link, the chip becomes nested interactive content.
- A chip's 44px hit area extends beyond its capsule, but chip rows use 6–8px gaps, so adjacent interactive chips would overlap.
- `agent-chip` says identity is "inspectable" without saying whether the chip is itself a control.
- The accessible output is just "Tawny Claude", which can sound like one name.
- `agent-chip` has no rule for long or unbroken aliases.

**Impact:** nested controls behave unpredictably with assistive technology, and overlapping targets cause wrong taps on phones. A long alias could overflow and be clipped by `.app { overflow: hidden }`.

**Minimal fix:** add these rules:
- A record has one primary link, its title. Chips are siblings, never nested inside a row link.
- Interactive chip hit areas must not overlap; add spacing or stack them.
- `agent-chip` is read-only unless explicitly linked, and is exposed as "Tawny, Claude agent".
- Aliases wrap with `overflow-wrap: anywhere` under a defined maximum length.

**Disposition:** Applied: title is primary link, chips are siblings/read-only unless linked, no overlapping targets, type-aware names and bounded wrapping aliases.

#### A11Y-05 · Accessibility and responsive behavior — Personal agent colors have no measured palette and overlap reserved status colors

Original source: [review-accessibility.md](review-accessibility.md). Original locations refer to the reviewed snapshot.

**Type:** Contract
**Location:** `DESIGN.md:19`–`45` (no identity or chart tokens), `:122`, `:162`; `EXPERIENCE.md:166`; `mockups/connections.html:10` (options Blue, Cyan, Amber); `mockups/knowledge-detail.html:42`, `:44` (hard-coded `#C7A06D`, `#9F8CEB`).

**Evidence:** the spine requires an "accessible color palette" and readable markers, but no such tokens exist. The contrast calculation has no identity pairs, and `DESIGN.md:122` forbids unmeasured accents. The prototype's color options match the blue, cyan and amber used for selection, knowledge and attention, even though `DESIGN.md:162` says personal color never implies status. Calculated from the exact palette, the hard-coded markers fall below the 3:1 target in light mode:

| Marker | Light card | Light secondary surface | Dark card | Dark secondary surface |
|---|---:|---:|---:|---:|
| `#C7A06D` | 2.42:1 | 2.11:1 | 7.21:1 | 6.23:1 |
| `#9F8CEB` | 2.83:1 | 2.47:1 | 6.17:1 | 5.33:1 |

**Impact:** because the alias and type text remain, this is not a color-only failure. It does mean the requested color differentiation fades for low-vision users in light mode, and an amber owl can read as "needs attention".

**Minimal fix:** keep color customization and add a designer-proposed set of named light/dark identity pairs, each ≥3:1 on card and secondary surface. Add them to the contrast calculation. Avoid exact semantic hues, or keep identity visibly distinct from status markers by using a different marker shape. Alias and type text stay mandatory.

**Disposition:** Applied with T1: measured identity palette, diamond shape and fixed type/name text.

#### A11Y-06 · Accessibility and responsive behavior — Selected filters and view switches rely on a 1.15:1 fill change

Original source: [review-accessibility.md](review-accessibility.md). Original locations refer to the reviewed snapshot.

**Type:** Reference, with a Contract clarification
**Location:** `mockups/daily-work.html:36`, `:96`; `mockups/focus.html:40`; `DESIGN.md:122`, `:150`.

**Evidence:** selected state is a card fill on a secondary surface, or the reverse, at a calculated 1.15:1 in light and 1.16:1 in dark, plus a text-color and weight change. `aria-pressed` is correct programmatically. `DESIGN.md:150` asks for "a visible indicator" but gives no contrast target for it. Background-only indicators may also disappear in Windows forced-colors mode, and no reference has a `forced-colors` rule.

**Impact:** low-vision users may not be able to see which person, layout or event filter is active, including whether they are viewing their own work or Mohamed's. Relevant to WCAG 1.4.11.

**Minimal fix:** in `DESIGN.md:150`, say that the selection indicator is ≥3:1 and is not background-only. In the references, add a 2px primary underline or inset outline to the existing selected state. No layout change is needed.

**Disposition:** Applied: selected controls gain non-background-only ≥3:1 indicators and forced-colors treatment.

#### A11Y-07 · Accessibility and responsive behavior — Focus ring is clipped on Focus board epic disclosures

Original source: [review-accessibility.md](review-accessibility.md). Original locations refer to the reviewed snapshot.

**Type:** Reference
**Location:** `mockups/focus.html:14` (outline with 3px offset), `:43` (`.epic { overflow: hidden }`), `:59` (full-bleed `.epic-work > summary`).

**Evidence:** the ring draws 3–6px outside a summary that spans the full width of a clipping parent. Left and right edges are clipped for every epic, and the bottom edge too when collapsed, leaving only the top edge visible.

**Impact:** this weakens the 3px focus indicator on the primary control of each S10 epic group (`DESIGN.md:150`). Relevant to WCAG 2.4.7. This pattern was checked in Daily Work and does not recur there: its focusable content has at least 14px of inset.

**Minimal fix:** on this one selector, use a negative `outline-offset` such as `-3px`, or inset the summary by 8px.

**Disposition:** Applied: Focus disclosure ring inset to avoid clipping.

#### A11Y-08 · Accessibility and responsive behavior — Focus board run links: accessible name, target size and return path

Original source: [review-accessibility.md](review-accessibility.md). Original locations refer to the reviewed snapshot.

**Type:** Reference
**Location:** `mockups/focus.html:223` (`aria-label`), `:234` ("Same evidence"), `:95`, `:259`–`:268`; `EXPERIENCE.md:107`; `DESIGN.md:132`.

**Evidence:**
1. `aria-label="Observed evidence for Tawny, Claude"` replaces the visible "Tawny Claude Shared run evidence". The name loses "Shared run" and doesn't contain the visible label.
2. "Same evidence" is an inline link with no minimum size, so it is well under the 44px target. Its text has no context out of sequence.
3. These links can jump to a run in another epic. Focus moves correctly, but there's no way back to the originating ticket.

**Impact:**
- Screen-reader users don't hear the shared-run fact that the design is careful to state.
- Speech-control users can't say the visible label (WCAG 2.5.3).
- Touch users get a small target.
- Keyboard users lose their place on long boards.

**Minimal fix:**
1. Remove `aria-label` and add visually hidden ticket context within the link text.
2. Make the shared-run link `display: inline-flex; min-height: 44px`, with text such as "Same evidence as SYN-42's run".
3. After a jump, offer "Back to SYN-67", or state in the contract that an in-page jump provides a return link.

**Disposition:** Applied: visible shared-link naming, 44px targets, contextual evidence labels and return-to-origin links.

#### A11Y-09 · Accessibility and responsive behavior — Key facts and field labels are set at 12px

Original source: [review-accessibility.md](review-accessibility.md). Original locations refer to the reviewed snapshot.

**Type:** Reference, with a small Contract gap
**Location:** `DESIGN.md:126`, `:185`.
- `mockups/focus.html:36` (Project scope label), `:41` (assigned ticket and run counts), `:91` (`.run-state`: "Reported active · 08:42"), `:96` (counted-once note), `:111`, `:113` (source state time).
- `mockups/connections.html`, `administrator-setup.html`, `notifications.html`, line 6: `.meta` ("Last successful collection 07:55", "Latest collection 09:18"), `.readiness-time`, `.notification-state-label`, `.workspace span` ("Authorized administrator").

**Evidence:** `DESIGN.md:126` keeps key facts, source identity, access messages and labels at the 14px floor. These uses aren't supplementary. Freshness is not named in that list, although `:185` requires it to be readable. The Daily Work, S2, S3, S4, S6 and S7 references correctly avoid 12px outside their study notes.

**Impact:** totals, field labels, access role and collection freshness become the smallest text on the phone, which works against the product's core promise of readable evidence.

**Minimal fix:** add "freshness and field labels" to `DESIGN.md:126`. Move these selectors to 14px, reserving 12px for truly supplementary text.

**Disposition:** Applied: operational labels, freshness, counts, access roles and run states use at least 14px.

#### A11Y-10 · Accessibility and responsive behavior — "Persist" and "remain visible" could produce a blocking sticky scope bar

Original source: [review-accessibility.md](review-accessibility.md). Original locations refer to the reviewed snapshot.

**Type:** Contract
**Location:** `DESIGN.md:155`; `EXPERIENCE.md:83`, `:135`, `:138`.

**Evidence:** `scope-bar` must "persist" and "remain visible" while wrapping on phone. This does not say whether that means present on each surface or fixed during scrolling. No reference makes it sticky, but an implementer could reasonably do so. A wrapped project, source and period bar at 200% text or in phone landscape could take much of the viewport.

**Impact:** low-vision and landscape users could have little reading area left, and focused content could be obscured despite `:135`. Relevant to WCAG 1.4.10 and 2.4.11.

**Minimal fix:** clarify that persistence means present in the page and on each summary or detail surface. It does not stick at compact widths or enlarged text. A wide-layout sticky bar must leave focused content unobscured.

**Disposition:** Applied: scope persistence means present, not sticky on compact/enlarged-text layouts; wide sticky UI cannot obscure focus.

#### A11Y-11 · Accessibility and responsive behavior — Long evidence and usage views lack phone, zoom and paging rules

Original source: [review-accessibility.md](review-accessibility.md). Original locations refer to the reviewed snapshot.

**Type:** Contract
**Location:** `EXPERIENCE.md:94`, `:99`, `:134`, `:135`; `DESIGN.md:165`, `:171`, `:187`; `mockups/usage.html:114`–`:122` (the rows are a good model).

**Evidence:**
- `DESIGN.md:187` says what not to do, forcing a wide table into phone-sized text, but gives no required alternative for model, person or session breakdowns. Only one row-based work-item view is shown.
- Paging is defined only for `activity-list`; S2 evidence and S7 rows are unbounded.
- "Load-more" has no focus rule.
- Long phone pages have no section navigation. S2 has six major panels and S10 repeats two disclosures per ticket.
- Long unbroken values such as IDs, branch names, URLs and log excerpts have no wrapping rule outside some `dd` styles.

**Impact:** at 320 CSS px or 200% text, implementers may ship clipped tables or sideways scrolling, and keyboard or screen-reader users face long traversal. Load-more can strand focus.

**Minimal fix:** add these rules:
- Below 600px or at enlarged text, breakdowns become labeled rows, with each value keeping its unit and measurement class. Any retained table scroller is a named, keyboard-focusable region with real headers.
- All potentially long lists use bounded pages. Load-more moves focus to the first new item and announces the count.
- Long detail pages offer in-page section links.
- Evidence values wrap, and unwrappable excerpts scroll inside a focusable region.

**Disposition:** Applied: labeled responsive rows, bounded lists, load-more focus/count, section links and safely wrapping/scrolled evidence.

#### A11Y-12 · Accessibility and responsive behavior — Phone-width clipping risk under enlarged text

Original source: [review-accessibility.md](review-accessibility.md). Original locations refer to the reviewed snapshot.

**Type:** Reference
**Location:** `mockups/daily-work.html:37`, `:153` (three-up summary retained on phone), `:19` (`.app { overflow: hidden }`), which is also used in the other references; `mockups/usage.html:28` (`.nav` without wrap); `EXPERIENCE.md:135`.

**Evidence (static estimate):**
- At 320px, each stat content column is about 70px; at 390px, about 93px.
- That fits 14px labels at normal text size.
- With text-only zoom to 200%, a word like "observed" needs about 115px and has no `overflow-wrap`.
- Usage's three-item nav needs about 360px at 200% text.
- `.app { overflow: hidden }` turns overflow into clipped, unreachable content rather than scrolling.

**Impact:** summary labels can collide and navigation labels can be cut off at the text size the spine requires.

**Minimal fix:** keep the accepted three-up appearance at default text size (UX-13) with `grid-template-columns: repeat(auto-fit, minmax(min(100%, 6em), 1fr))`, which collapses as text grows. Add `flex-wrap: wrap` to `.nav`, as most other references already do. Use `overflow: clip` only for corners with a checked inner reflow, or remove the clipping. Verify after the change.

**Disposition:** Applied: auto-fit statistics, wrapping navigation and unclipped content. Narrow previews supplement the static checks; full text/zoom testing remains implementation work.

#### A11Y-13 · Accessibility and responsive behavior — Feed event type is exposed only through a hidden icon

Original source: [review-accessibility.md](review-accessibility.md). Original locations refer to the reviewed snapshot.

**Type:** Reference
**Location:** `mockups/daily-work.html:298`, `:103`–`:105`; `DESIGN.md:166`.

**Evidence:** `activity-list` requires "event type" in each row. In the mock, the only type marker is an `aria-hidden` icon, colored by kind. Icon shapes differ, so it's not strictly color-only visually, but it provides no text and nothing programmatic. Filters offer "Needs input / Closed / Knowledge / Reviews", yet rows carry no matching label.

**Impact:** screen-reader users, and anyone who doesn't memorize the icons, must infer type from the title. The filtered categories can't be verified on the row.

**Minimal fix:** add a short visible type label to each row, using the same vocabulary as the filters. Keep the icon decorative.

**Disposition:** Applied: visible feed event types match filter vocabulary; icons remain decorative.

#### A11Y-14 · Accessibility and responsive behavior — S9 settings pattern lacks group semantics and a matching label

Original source: [review-accessibility.md](review-accessibility.md). Original locations refer to the reviewed snapshot.

**Type:** Reference (the controls are deliberately disabled; the semantic pattern is what would be copied)
**Location:** `mockups/notifications.html:10`; `DESIGN.md:172`; `EXPERIENCE.md:134`.

**Evidence:**
- "Followed project scope" is a `<p>` above checkboxes, with no `fieldset` and `legend`; no reference has one.
- Appearance has a visible `<p>Appearance</p>` while the select's real label is sr-only "Theme", so the visible and programmatic names differ.
- `DESIGN.md:172` requires a persistent label above the field.

**Impact:** a screen-reader user hears "Syntelligence, checkbox" without the group's meaning at J7's first step, and a speech user can't say the visible "Appearance". Relevant to WCAG 1.3.1 and 2.5.3.

**Minimal fix:** use `fieldset` and `legend` for the followed-project group. Make "Appearance" the visible `<label>` of the select.

---

**Disposition:** Applied: project/event preferences use fieldset/legend and visible Appearance label.

### Low (25)

#### F5 · 1. Flow coverage — FR-3 recovery non-duplication is missing.

Original source: [review-rubric.md](review-rubric.md). Original locations refer to the reviewed snapshot.

PRD FR-3 requires that recovery not duplicate contributions, runs, or usage. E:250 covers only notification replay, and E:92 and E:99 cover only shared-run totals. *Fix:* add one clause to S5/S8 state patterns or the J2 failure path.

**Disposition:** Applied: recovery preserves unique observations, contributions, runs, receipts and usage.

#### F6 · 1. Flow coverage — Flow numbering is unexplained.

Original source: [review-rubric.md](review-rubric.md). Original locations refer to the reviewed snapshot.

IDs jump from J2 to J6 with no note, and J-IDs are not PRD identifiers. *Fix:* add one line saying J-IDs are UX-local and gaps are intentional, or renumber them.

**Disposition:** Applied: SC/J identifier purpose and unused J3–J5 are explained without inventing historical reasons.

#### T3 · 2. Token completeness — Data-visualization colors are unspecified.

Original source: [review-rubric.md](review-rubric.md). Original locations refer to the reviewed snapshot.

D:171 and E:99 require charts, but `usage.html` uses `--share` and `--chart-2` with no DESIGN token. *Fix:* add a chart or share-bar token, or state that V1 bars use `{colors.primary}` on `{colors.secondary-surface}`.

**Disposition:** Applied: charts use primary on secondary surface with labeled equivalents.

#### T4 · 2. Token completeness — `action-control-dark` is redundant.

Original source: [review-rubric.md](review-rubric.md). Original locations refer to the reviewed snapshot.

The D:106 mapping already covers dark mode, yet this is the only component with a separate dark entry, and D:106 presents it as an example of a variant. *Fix:* remove it and rely on the mapping, or state clearly why this component alone is enumerated. Update D:92, D:174, and E:102 together.

**Disposition:** Adapted: retained explicit light/dark export variants and documented precedence and shared behavior.

#### V5 · 5. Visual reference coverage — Mock vocabulary drifts from spine vocabulary.

Original source: [review-rubric.md](review-rubric.md). Original locations refer to the reviewed snapshot.

"Work in focus" in `daily-work.html:211` collides with the separate Focus board, the confusion J8's climax warns about (E:258). Other drift: "Together" vs "combined" (E:91), "Daily work" vs "Daily Work" (E:44), and "Receiving observations" vs "Observation ready" (E:70). *Fix:* align labels; rename the S1 section, for example to "Active work."

**Disposition:** Applied: Active work, Daily Work, Combined, and Observation ready vocabulary aligned.

#### V6 · 5. Visual reference coverage — Visual links are inconsistent in the state table.

Original source: [review-rubric.md](review-rubric.md). Original locations refer to the reviewed snapshot.

S2, S4, S5, and S9 rows have no visual links (E:112, E:114, E:115, E:119); the other six do. *Fix:* link all ten or remove them from this table, since the IA already links each surface.

**Disposition:** Applied: all ten state-table surfaces have visual links.

#### B1 · 6. Bloat and overspecification — Process status sits in contract text.

Original source: [review-rubric.md](review-rubric.md). Original locations refer to the reviewed snapshot.

E:272 records reviewer selection ("All four review lenses… Claude Opus 5.5 Ultrathink") and reconciliation progress. E:25's "latest user addition" is a session note. Neither helps a downstream builder, and both go stale at finalization. *Fix:* keep these in `.memlog.md` only.

**Disposition:** Applied: session/review status moved outside the contracts.

#### B2 · 6. Bloat and overspecification — Some rules are restated or misplaced.

Original source: [review-rubric.md](review-rubric.md). Original locations refer to the reviewed snapshot.

The execution boundary recurs at E:36, E:86, E:91, E:186, E:197, E:150, E:257, and E:258. E:158–164 partly restate FR text that semantic and component rows also apply. D:136 and D:138 carry surface order and Focus behavior that E:148, E:91, and E:92 own. *Fix:* keep one authoritative statement in each case and reference it elsewhere; retain repetition only where a flow step needs it.

**Disposition:** Adapted: redundant prose reduced; execution boundaries at journey climaxes and assumption reminders preserved intentionally, as editorial review recommends.

#### I2 · 7. Inheritance discipline — Stable decision IDs are replaced by "latest" wording.

Original source: [review-rubric.md](review-rubric.md). Original locations refer to the reviewed snapshot.

E never cites UX-11, UX-12, UX-13, UX-15, or UX-17 (E:25, E:40, E:57, E:166, E:168, E:254 use phrases such as "latest Focus request"), and later decisions have already made "latest" wrong. UX-16 is a sample boundary and needs no citation. *Fix:* cite the memlog IDs.

**Disposition:** Applied: stable UX decision IDs replace latest wording.

#### I3 · 7. Inheritance discipline — `[OPEN]` is defined but never applied.

Original source: [review-rubric.md](review-rubric.md). Original locations refer to the reviewed snapshot.

It appears only in the E:32 and E:34 definitions. E:272 lists bounded refinements without shared alias authority or the palette (E:90, E:166), so real open items are harder to find. *Fix:* tag remaining items `[OPEN]` and add them to the register, or remove the label.

**Disposition:** Applied: OPEN tags identify remaining bounded dependencies; identity palette is now specified.

#### I4 · 7. Inheritance discipline — Some handoff evidence links only to `.working/`.

Original source: [review-rubric.md](review-rubric.md). Original locations refer to the reviewed snapshot.

D:122 and E:270 point to `.working/palette-contrast.md` and `.working/source-prd.md`, a folder the skill treats as working space. A-1–A-6 are also safe in the PRD and memlog, but the contrast evidence is not. *Fix:* promote the contrast calculation or confirm `.working/` ships with the package.

**Disposition:** Applied: palette evidence promoted to assets/palette-contrast.md; original .working source extracts remain in the package.

#### SH1 · 8. Shape fit — The Responsive table specifies only part of the surface set.

Original source: [review-rubric.md](review-rubric.md). Original locations refer to the reviewed snapshot.

E:148 gives phone order for S1 and full-width rules for S2, S4, and S6. S7's wide table and S3, S5, and S8 have no phone rule beyond D:187's general warning; D:138 covers S10 separately. `daily-work.html` uses 540px and 800px breakpoints rather than D:134's 600/1024px. *Fix:* add one general rule or per-surface phone rows, starting with S7 tables, and align the mock breakpoints.

**Disposition:** Applied: common phone rules cover all surfaces, labeled Usage rows and bounded lists; breakpoints aligned.

#### PK-17 · Permissions and knowledge lifecycle — Focus opens with a cross-project aggregate, against the IA's default

Original source: [review-permissions-knowledge.md](review-permissions-knowledge.md). Original locations refer to the reviewed snapshot.

**Location:** `EXPERIENCE.md:44`, `:254`; `mockups/focus.html:173`, `:216`.

The IA says company context is explicitly selected, "not an automatic cross-project default". Focus defaults to "Both permitted projects". It is labeled and contains only authorized data, so this is a contract inconsistency rather than a leak. **Fix:** state explicitly whether Focus is a deliberate exception for the concurrent-work need, or start it from the restored project.

**Disposition:** Applied with F1: Focus is the explicit labeled proposed cross-project exception.

#### PK-18 · Permissions and knowledge lifecycle — Reference copy departs from the safe patterns the spine defines

Original source: [review-permissions-knowledge.md](review-permissions-knowledge.md). Original locations refer to the reviewed snapshot.

**Location and fix:**

- `mockups/usage.html:124` names Movesion and its tools on a Syntelligence-scoped screen, against `EXPERIENCE.md:63`. Remove it, or render it only for viewers authorized for both.
- `mockups/notifications.html:10` adds "Its current access could not be verified" to the neutral message, which differs from a missing item. Use the single copy at `EXPERIENCE.md:73`.
- `mockups/knowledge.html:43` omits a scope marker on candidate SYN-K12, against `DESIGN.md:167`. Add one.
- `mockups/knowledge-detail.html:44` merges "Retrieved and delivered" on one row, though its timestamps differ. Show separate rows, per `EXPERIENCE.md:96`.

**Disposition:** Applied: safe unavailable copy, scope badges, split receipt times, and authorized-only cross-project mentions.

#### PK-19 · Permissions and knowledge lifecycle — One source failure is shown as a single client's state

Original source: [review-permissions-knowledge.md](review-permissions-knowledge.md). Original locations refer to the reviewed snapshot.

**Location:** `mockups/connections.html:10`, `administrator-setup.html:10`, `focus.html:223`; `EXPERIENCE.md:115`.

S8 shows the Movesion Jira authorization as expired at the source level. S5 shows only Barn affected and withholds its knowledge because "source access cannot be verified", while Eagle in the same project shows healthy observation with only "Not verified". Focus's Movesion cards say "Source observed 08:42", while S5 and S8 show that Jira's last success was 07:55. **Fix:** show the shared source failure on both Movesion clients, apply the withholding consistently where it depends on that source, and label Focus's snapshot accordingly.

**Disposition:** Applied: Movesion Jira failure appears on both dependent clients, setup and Focus, consistently last-success 07:55.

#### PK-20 · Permissions and knowledge lifecycle — Administrator authority isn't scoped to a project

Original source: [review-permissions-knowledge.md](review-permissions-knowledge.md). Original locations refer to the reviewed snapshot.

**Location:** `EXPERIENCE.md:55`, `:118`; `mockups/administrator-setup.html:10`. Source: FR-18 line 215.

"Only authorized administrators" and a single two-customer page can be read as company-wide administration. **Fix:** S8 lists only projects the viewer administers, and another project's site, repository, and client identities don't appear. The mock remains valid for someone who administers both.

**Disposition:** Applied: S8 contains only projects this viewer administers; two-project fixture states dual authorization.

#### PK-21 · Permissions and knowledge lifecycle — Enabling automatic mode and the successful-publication path aren't shown

Original source: [review-permissions-knowledge.md](review-permissions-knowledge.md). Original locations refer to the reviewed snapshot.

**Location:** `EXPERIENCE.md:100`, `:230`; `mockups/promotion.html`. Source: FR-12 lines 164–165.

SC-3 step 7 covers switching away from automatic. It doesn't cover switching to it, which evaluates existing candidates and may publish many under the preferred mode. References show only withheld and pending-manual states. **Fix:** make the mode-change confirmation state that existing candidates will be evaluated and name the audience. Add one reference for a published-by-policy record showing the automation identity and policy version.

**Disposition:** Applied: enabling automatic mode confirms evaluation of existing candidates/audience; successful policy publication is shown.

#### A11Y-15 · Accessibility and responsive behavior — Repeated disclosure labels lack context

Original source: [review-accessibility.md](review-accessibility.md). Original locations refer to the reviewed snapshot.

**Type:** Reference
**Location:** `mockups/connections.html:10` ("Readiness evidence" ×4); `mockups/usage.html:118`, `:119` ("Inspect attribution" ×2); `mockups/daily-work.html:298` ("View evidence" ×4 rendered); `mockups/focus.html:223` ("Work evidence" ×5, "Usage & cost: Unavailable" ×8 rendered in the By epic view); `EXPERIENCE.md:124`.

**Impact:** in a screen reader's controls list or with voice commands, the triggers are indistinguishable.

**Minimal fix:** add visually hidden context such as the ticket key or client/project. Keep the visible text.

**Disposition:** Applied: repeated disclosures carry ticket/client context.

#### A11Y-16 · Accessibility and responsive behavior — CSS disclosure markers may enter the accessible name

Original source: [review-accessibility.md](review-accessibility.md). Original locations refer to the reviewed snapshot.

**Type:** Reference
**Location:** `mockups/work-detail.html:54`–`:55`, `mockups/usage.html:67`–`:68` (`+`, `−`); `mockups/knowledge.html:23` and the same rule in `knowledge-detail.html` and `promotion.html` (`›`, `⌄`). The Daily Work, Focus and shell references already use `aria-hidden` SVG chevrons correctly.

**Impact:** some browser and screen-reader combinations may read "Inspect attribution plus", on top of the native expanded state.

**Minimal fix:** reuse the `aria-hidden` SVG chevron, or use `content: '+' / ''`, subject to the browser-support check.

**Disposition:** Applied: decorative SVG disclosure markers replace spoken CSS glyphs.

#### A11Y-17 · Accessibility and responsive behavior — `aria-label` on generic elements

Original source: [review-accessibility.md](review-accessibility.md). Original locations refer to the reviewed snapshot.

**Type:** Reference
**Location:** `mockups/daily-work.html:203` (`.summary`), `:233` (`ticketChip`; also `focus.html:191`), `mockups/knowledge.html:39` (`.filter-row`).

**Evidence:** these `<span>` and `<div>` elements have no role, and support for naming them is unreliable. The chip's source qualification is otherwise only in a hover `title`. Project/source context is usually visible nearby, so this isn't a data loss on screen, but `EXPERIENCE.md:89`'s qualification may not be heard.

**Minimal fix:** use visually hidden text inside the chip, and `role="group"` on named groups.

**Disposition:** Applied: named groups have roles; chip qualification uses text rather than labels on generic spans.

#### A11Y-18 · Accessibility and responsive behavior — `<p>` placed directly in `<dl>` groups detaches provenance from its value

Original source: [review-accessibility.md](review-accessibility.md). Original locations refer to the reviewed snapshot.

**Type:** Reference
**Location:** `mockups/work-detail.html:123`–`:126`; `mockups/usage.html:107`–`:110`.

**Impact:** invalid `dl` structure can leave source or coverage notes unassociated with their fact, for example "1.20M tokens priced · 0.40M unpriced".

**Minimal fix:** move each `<p>` into its `<dd>`, or into a second `<dd>`.

**Disposition:** Applied: provenance paragraphs are inside definition values.

#### A11Y-19 · Accessibility and responsive behavior — Component tokens conflict with text rules

Original source: [review-accessibility.md](review-accessibility.md). Original locations refer to the reviewed snapshot.

**Type:** Contract
**Location:** `DESIGN.md:75` vs `:158` (`attention-item` token uses attention text; the table says the body is main text); `DESIGN.md:90` vs `:113` (`state-message` uses secondary text, while permission and failure text should be main text).

**Impact:** both pairs pass contrast (5.41:1 or better), so this isn't a contrast failure. An implementer following the token would lower emphasis on failures, permissions and attention text.

**Minimal fix:** set both component text tokens to `{colors.text}`. Use the attention color only on the marker, and secondary text only for supporting lines.

**Disposition:** Applied with T2: component text tokens match main-text rules.

#### A11Y-20 · Accessibility and responsive behavior — Other reference drift from the spines

Original source: [review-accessibility.md](review-accessibility.md). Original locations refer to the reviewed snapshot.

**Type:** Reference (the spines win; correct these if the mockups will be copied)

| Location | Drift | Impact | Fix |
|---|---|---|---|
| `mockups/daily-work.html:131`, `:140` vs `DESIGN.md:134` | Breakpoints 540/800 instead of 600/1024; two columns remain at 541–599px. | Layout at those widths differs from the contract. | Align the values. |
| `mockups/focus.html:10`–`:11` (live); `usage.html:55`; shell references line 6 vs `DESIGN.md:126` | Selects render at 14px; the contract says inputs are 16px. | iOS may zoom on focus. | Set inputs to 16px. |
| `mockups/focus.html:244` | Together view goes from `h1` to `h3`, and "Distinct observed agent runs" is a `<p>`. | Heading navigation is less clear. | Add a section `h2`. |
| `mockups/daily-work.html:209` | Section is named only by the title, without "Needs your input". | The attention reason is missing from region navigation. | Include the label's ID in `aria-labelledby`. |
| `mockups/usage.html:118`–`:120` vs `DESIGN.md:171` | Row totals "0.60M · 37.5%" have no unit. | The measure is ambiguous when read out alone. | Write "0.60M tokens". |
| Daily/Focus vs `work-detail`/`usage` vs `knowledge*` vs `DESIGN.md:162` | "Fixed" Claude/Codex placeholder glyphs differ across three families. Marker forms differ too. | Weakens consistent recognition. Glyphs stay illustrative. | Use one placeholder per type and one marker form. |
| `mockups/daily-work.html:52` vs `DESIGN.md:122`, `:158` | Attention panel is a 5% amber tint; spec says neutral panel and no unmeasured tints. | No contrast problem: the secondary text calculates to 5.79:1 light, 7.66:1 dark. It's a rule inconsistency only. | Use a neutral panel, or measure and record the tint. |

**Disposition:** Applied: breakpoint/input/heading/unit/vocabulary consistency, neutral attention panel and shared provider glyph family.

#### A11Y-21 · Accessibility and responsive behavior — Standalone references lose focus rings or fall below the ring target

Original source: [review-accessibility.md](review-accessibility.md). Original locations refer to the reviewed snapshot.

**Type:** Reference (does not affect the product or host-rendered previews)
**Location:** `daily-work.html:14`, `focus.html:14`, and line 6 of `connections.html`, `administrator-setup.html`, `notifications.html`, all using `var(--ring)` with no fallback. `knowledge.html:10`, `knowledge-detail.html:10`, `promotion.html:10` use a fixed `#2456D6` fallback that their dark media query doesn't override.

**Evidence:**
- Without host tokens, an undefined variable invalidates the outline at computed-value time, so the rule removes the browser's default ring as well. The same applies to progress fills and agent dots.
- In dark mode, `#2456D6` calculates to 3.07:1 on canvas, 2.81:1 on card and 2.42:1 on secondary surface.
- `DESIGN.md` links these files directly, so opening them outside the host is a realistic way to review them.

**Impact:** reviewers could misjudge focus visibility and bars, or validate the wrong thing.

**Minimal fix:** give the tokens exact-palette fallbacks, or label each file as host-rendered only. The existing "not proof of the standalone palette" note doesn't cover the lost focus ring.

**Disposition:** Applied: exact light/dark standalone fallbacks include focus and identity colors; embedded host colors still need separate evaluation.

#### A11Y-22 · Accessibility and responsive behavior — Gallery chooser label and iframe height

Original source: [review-accessibility.md](review-accessibility.md). Original locations refer to the reviewed snapshot.

**Type:** Reference
**Location:** `mockups/gallery.html:1`.

**Evidence:** `aria-label="Choose a visual reference"` overrides the visible "Screen" label. Height is set only on load, capped at 1750px, so expanding details adds nested scrolling in the frame.

**Impact:** a speech-input mismatch, plus awkward nested scrolling at phone widths. This affects review only.

**Minimal fix:** remove the `aria-label`, and either update the height when disclosures toggle or link each screen to its standalone file.

---

**Disposition:** Applied: Screen label matches select name; gallery resizes for content changes and links every standalone reference.

## Editorial findings (unranked)

[Original 44-row review](review-editorial.md) and [row-by-row disposition](review-disposition.md#editorial--completed). Structure was applied before prose; five PRESERVE rows remain, optional effects were clarified without a new ban, and canonical headings/source assumptions are intact.

## Remaining validation boundaries

All A-1–A-6 owners and checkpoints remain in their original sources. Packaging/push delivery, source authorization and revocation enforcement, actual enrollment and skill reading, real assistive-technology/text-scaling behavior, source-use permission ownership and query retention still require their stated downstream evidence. Jira and Bitbucket sampling remain unconnected; the private GitHub sample is partial and separate.

## Reviewer files

- [Completeness and consistency](review-rubric.md)
- [Permissions and knowledge lifecycle](review-permissions-knowledge.md)
- [Accessibility and responsive behavior](review-accessibility.md)
- [Structure and prose](review-editorial.md)
- [Disposition and verification](review-disposition.md)
