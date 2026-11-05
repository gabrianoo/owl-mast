# Spine Pair Review — Owl Mast

Lens: completeness and consistency (rubric walker). Static document review on 2026-11-05. Line references use `DESIGN.md` (D), `EXPERIENCE.md` (E), and `mockups/*.html` as read. No mock was rendered, and this is not a usability, accessibility, permission, or integration test.

## Overall verdict

The pair has a sound structure and preserves the confirmed choices: names, links, tokens, and surface coverage all pass, and A-1–A-6 remain open and intact. It should not be finalized until one critical gap and three high-severity contract conflicts are resolved, because each would make downstream builders invent behavior: agent identity colors have no tokens, Focus has conflicting default-scope instructions, "observed work update" has no event definition, and alias rendering is undefined for agents the viewer has not named. All four, and the ten medium findings, are bounded edits that do not reopen any user decision.

| Category | Verdict | Critical | High | Medium | Low |
|---|---|---:|---:|---:|---:|
| 1. Flow coverage | adequate | 0 | 2 | 2 | 2 |
| 2. Token completeness | thin | 1 | 0 | 1 | 2 |
| 3. Component coverage | adequate | 0 | 1 | 1 | 0 |
| 4. State coverage | adequate | 0 | 0 | 1 | 0 |
| 5. Visual reference coverage | adequate | 0 | 0 | 4 | 2 |
| 6. Bloat and overspecification | adequate | 0 | 0 | 0 | 2 |
| 7. Inheritance discipline | adequate | 0 | 0 | 1 | 3 |
| 8. Shape fit | strong | 0 | 0 | 0 | 1 |
| **Total (26)** | | **1** | **3** | **10** | **12** |

## 1. Flow coverage — adequate

Checked SC-1, SC-2, and SC-3 against the PRD, plus J1, J2, J6, J7, and J8. All eight flows have a named protagonist, numbered steps, a climax, and a failure path. All 21 FRs map through the IA table. SC names match the PRD verbatim.

### Findings

- **high — F1. Focus has two incompatible default scopes.** E:44 says company context is explicitly selected and "not an automatic cross-project default." E:254 says Focus shows work "within his authorized project scope." `focus.html:173` defaults to "Both permitted projects," and its summary reports "5 assigned tickets across 3 epics" across Syntelligence and Movesion. E:150 makes the spine win, so a builder following it could hide the cross-project concurrency that UX-12 exists to show; a builder following the mock would ship an aggregate the IA forbids as a default. *Fix:* add one sentence to S10 (E:57) and J8 step 1 (E:254) choosing a labeled [P] default. Recommended: Focus may open on all authorized projects as an explicit, visibly labeled aggregate, with project and source on every card. Add this exception to E:44.

- **high — F2. "Observed work update," the push trigger, is undefined, and the push controls use conflicting terms.** UX-10 is preserved at E:40, E:245, and E:268, but nothing lists which events count. J7 step 3 (E:247) routes notifications to S2, S4, or S6, which implies knowledge and promotion events may notify even though the decision says "work update." S1's filters also include Knowledge (`daily-work.html`, Recent updates). S9 promises "category choice" (E:56), J7 says "follow/notification scope" (E:245), and `notifications.html` offers only followed projects and a generic-preview option. A category control could recreate the attention-only filter that UX-10 rejects, and architecture has no event classes to design against. *Fix:* add a short [P] event table to S9 or J7 listing each event class, whether it counts as a work update under UX-10, and its destination. Replace "category choice" with the controls actually intended. Keep every-update as the default and platform delivery as an implementation validation.

- **medium — F3. Two user-requested behaviors have no flow.** Alias and color editing (UX-15) and contextual cost drill-down (UX-17) appear only in component rows and semantics (E:90, E:99, E:166, E:168). S5's row (E:52) omits appearance settings, S2 and S10 (E:49, E:57) omit Usage & cost, and J6 enters only from a project or company scope (E:236). Stories have no sequence or climax to build from. *Fix:* add one step or a short branch: J2 or a J2 appendix for appearance editing, and a J6 entry from a ticket or epic summary with scope retained. Add both to the IA rows, tagged [P].

- **medium — F4. FR-15's company view has no flow, visual, or surface state outside S7.** FR-15 covers progress, agent activity, attention, knowledge, and usage. S1 and S10 claim FR-15 (E:48, E:57), but SC-1 and J1 are project-scoped, only J6 mentions company scope (E:236), and no mock shows a labeled company aggregate. *Fix:* add a J6 or S1 branch that selects company context and shows the aggregate label, partial coverage, and drill-down context. Alternatively, state which surfaces have company scope in V1.

- **low — F5. FR-3 recovery non-duplication is missing.** PRD FR-3 requires that recovery not duplicate contributions, runs, or usage. E:250 covers only notification replay, and E:92 and E:99 cover only shared-run totals. *Fix:* add one clause to S5/S8 state patterns or the J2 failure path.

- **low — F6. Flow numbering is unexplained.** IDs jump from J2 to J6 with no note, and J-IDs are not PRD identifiers. *Fix:* add one line saying J-IDs are UX-local and gaps are intentional, or renumber them.

## 2. Token completeness — thin

Parsed YAML: 26 colors form 13 light/dark pairs, all six-digit hex. All 45 `{path}` references resolve in both spines. I recalculated all 25 reported contrast pairs, and they match D:122 and `.working/palette-contrast.md`. The core palette is strong; the verdict is thin because one required color family has no tokens.

### Findings

- **critical — T1. Agent identity colors have no tokens, hex values, dark pairs, or contrast targets.** D:162 and E:90 require a user-changeable colored marker. E:166 requires an "accessible color palette," and D:79 defines no identity color. Mocks fill the gap three ways:
  - host `--chart-1` through `--chart-4` in `connections.html`, `focus.html`, and `daily-work.html`
  - literal `#9F8CEB` and `#C7A06D` in `knowledge-detail.html:42`, with no dark pair, measuring 2.47:1 and 2.11:1 on light `secondary-surface` (2.83:1 and 2.42:1 on `card`), below the 3:1 boundary target if the marker is meaningful
  - "Blue / Cyan / Amber" in the `connections.html` color field, which reuses hues D:115–118 reserves for orientation, knowledge, and attention

  This also violates D:122 ("do not… introduce unmeasured accent tints") and undermines D:162's rule that personal color never implies status. Rubric rule applied: missing hex is critical, and this affects every `agent-chip` on every surface. *Fix:* add a [D]/[P] token family such as `agent-identity-1…n` with `-dark` pairs, hues distinct from semantic roles, and a measured marker target. Reference it from `agent-chip` and align the S5 picker. Palette contents remain delegated designer proposals; alias ownership is handled in C1.

- **medium — T2. Component frontmatter contradicts component prose for two load-bearing text colors.** `attention-item` sets `textColor: {colors.attention}` (D:75), but D:158 says "Body remains main text." `state-message` sets `{colors.secondary-text}` (D:90), but D:113 requires main text for permission and failure messages, and E:101 uses this component for denied and failure states. Code that mirrors the tokens will implement the wrong hierarchy. *Fix:* set both text colors to `{colors.text}`. Express amber as a marker property on `attention-item`.

- **low — T3. Data-visualization colors are unspecified.** D:171 and E:99 require charts, but `usage.html` uses `--share` and `--chart-2` with no DESIGN token. *Fix:* add a chart or share-bar token, or state that V1 bars use `{colors.primary}` on `{colors.secondary-surface}`.

- **low — T4. `action-control-dark` is redundant.** The D:106 mapping already covers dark mode, yet this is the only component with a separate dark entry, and D:106 presents it as an example of a variant. *Fix:* remove it and rely on the mapping, or state clearly why this component alone is enumerated. Update D:92, D:174, and E:102 together.

## 3. Component coverage — adequate

All 23 frontmatter components have rows in both D:Components and E:Component Patterns, with no name drift and real behavioral rules. Gaps are in rules and in components used but not named.

### Findings

- **high — C1. Alias rendering has no fallback or identity level.** E:90 defines aliases as this viewer's personal display preferences, and D:162 makes an owl name part of every `agent-chip`. Nothing specifies what a viewer sees for an agent they have not named, including a colleague's agent, which SC-1 depends on. Nothing specifies whether an alias attaches to a client enrollment, a client-project pair, or a run, or how invalid, duplicate, or failed saves behave. Illustrative fixtures show the ambiguity: "Tawny" is a client-project identity in `connections.html` (`CL-SYN-01`), a run `CL-17` initiated by Ahmed in `usage.html`, and run `CL-21` on Mohamed's work in `work-detail.html`. *Fix:* add a [P] rule to E:90 and D:162:
  - the identity level an alias attaches to
  - the unaliased display, such as fixed type label plus stable short ID and a neutral marker
  - name validation and whether duplicates are allowed
  - reset behavior
  - a save-failure entry in the S5 state row (E:115)

  Keep shared naming authority explicitly unresolved, as E:90 already says.

- **medium — C2. Recurring UI elements have no component contract.** Mocks and spines rely on these without rows:
  - person, view, and filter switches (S1 My work/Mohamed, S1 update filters, S10 By epic/Together, S3 lifecycle filters; E:91, E:94)
  - lifecycle and status badges (`knowledge-detail.html`, `promotion.html`)
  - disclosures (native details on every surface; E:124 gives only general behavior)
  - notification preview (`notifications.html`)
  - secondary actions ("Keep project-scoped" in `promotion.html`; D:174 defines only a filled primary action)

  Parity checks pass only because these were never named, so downstream teams will define them inconsistently. *Fix:* add `filter-control`, `status-badge`, `disclosure`, and `notification-preview` to frontmatter and both tables, and add a secondary `action-control` variant. Alternatively, explicitly classify any of these as native primitives with stated rules.

## 4. State coverage — adequate

The E:107 baseline covers cold-load, focus, revoked access, unverifiable authorization, offline, and reconnect for S1–S10. E:111–120 specializes empty, error, stale, unsupported, permission, and offline states for all ten surfaces. Alias save failure is covered by C1.

### Findings

- **medium — S1. System quarantine is not a user-visible lifecycle state.** FR-13 says the system can quarantine a version. E:160's distinct-state list and E:114's S4 row omit it, leaving only passing mentions of quarantine at E:230 and E:270. `knowledge-record` (E:95) has no way to distinguish a system quarantine from a maintainer withdrawal. *Fix:* add Quarantined, with its system origin, to E:160 and E:114. Keep retrieval and re-publication semantics deferred to A-2.

## 5. Visual reference coverage — adequate

No orphans: all 11 mocks, 6 imports, the manifest, and the mark resolve and are named in context; the two spines together link everything. Spines-win is stated (D:98, E:150). All ten gallery embeds are identical to their standalone files. Static disabled actions and illustrative data are expected and not findings.

### Findings

- **medium — V1. The proposed navigation appears in no reference.** E:44 defines five primary destinations plus Preferences. D:134 and E:146 commit to a rail at ≥1024px and a labeled menu below that. Actual mock shells differ:
  - `daily-work.html:194` has no navigation, although J8 starts "From the landing page" (E:254)
  - `focus.html:170` shows two items and `usage.html:101` three
  - `knowledge.html`, `knowledge-detail.html`, and `promotion.html` show "Workspace / Knowledge," and "Workspace" is not an IA term
  - `notifications.html` shows two items and `connections.html` shows sub-navigation
  - `work-detail.html:105` shows a breadcrumb

  E:150's "demonstrate the layouts" and D:177's "uses the defined components" overstate this for `surface-navigation`. The spine controls, but the most cross-cutting shell has never been drawn. *Fix:* add one shared shell reference at wide and compact widths, or narrow both claims and note that navigation is spine-only.

- **medium — V2. The host-theme caveat covers one mock, but the dependency affects all ten.** D:136 discloses it only for `daily-work.html`. `daily-work`, `focus`, `connections`, `notifications`, and `administrator-setup` use undefined host variables almost entirely without fallbacks (94–116 uses). `work-detail` and `usage` fall back mostly to system colors; `knowledge`, `knowledge-detail`, and `promotion` fall back to DESIGN hex for the core palette. The gallery copies its parent's computed variables, which are empty outside a host. By CSS rules, panels in the first five lose fills and borders when opened directly (inferred; not rendered). This matches the brief's known boundary but is not disclosed to spine readers. *Fix:* move the caveat to D:177 and E:59, naming which rendering context the references need. Optionally inject a standalone DESIGN token block so references are usable in architecture and story work.

- **medium — V3. Key lifecycle actions and states have no reference.** S6's row promises withdrawal and supersession (E:53), and SC-3 steps 6–7 depend on them along with mode changes. `promotion.html` shows modes, one exception, and one manual review, with no withdraw, supersede, or mode-change preview. `knowledge-detail.html`'s only alternate is unavailable, despite E:114's conflicting, superseded, withdrawn, and version-unknown states. D:174 and E:138 specify destructive styling and confirmation, but nothing shows them. *Fix:* add static alternates in native disclosures, or state in E:59 that these states are spine-only.

- **medium — V4. Epic progress is displayed three different ways.** E:156 requires the label "child tickets closed," and Voice uses "3 of 5 child tickets closed" with no percentage (E:69). `daily-work.html:210` makes "60%" dominant with "3 of 5 tickets closed," despite D:185's warning about big percentages. `focus.html` shows "Epic: 3/5 tracker-closed" with a bar. SC-1 step 2 tags "completion percentages for… tickets/epics" as [U: UX-05] (E:194), while UX-07 defines only tickets, leaving epic percentages unresolved. `daily-work.html:210` also labels "Your owned scope" while its basis says "five tickets in this epic," blurring the distinction J8 requires (E:256). *Fix:* state in E:156 whether a derived percentage may accompany the fraction, keeping the proposal labeled [P] and the fraction dominant. Use one label across S1, S2, S10, and Voice, and correct the S1 scope text.

- **low — V5. Mock vocabulary drifts from spine vocabulary.** "Work in focus" in `daily-work.html:211` collides with the separate Focus board, the confusion J8's climax warns about (E:258). Other drift: "Together" vs "combined" (E:91), "Daily work" vs "Daily Work" (E:44), and "Receiving observations" vs "Observation ready" (E:70). *Fix:* align labels; rename the S1 section, for example to "Active work."

- **low — V6. Visual links are inconsistent in the state table.** S2, S4, S5, and S9 rows have no visual links (E:112, E:114, E:115, E:119); the other six do. *Fix:* link all ten or remove them from this table, since the IA already links each surface.

## 6. Bloat and overspecification — adequate

Size is mostly justified by ten surfaces and permission-sensitive semantics. The added Evidence section earns its place. Pixel values are limited, and tables are used appropriately.

### Findings

- **low — B1. Process status sits in contract text.** E:272 records reviewer selection ("All four review lenses… Claude Opus 5.5 Ultrathink") and reconciliation progress. E:25's "latest user addition" is a session note. Neither helps a downstream builder, and both go stale at finalization. *Fix:* keep these in `.memlog.md` only.

- **low — B2. Some rules are restated or misplaced.** The execution boundary recurs at E:36, E:86, E:91, E:186, E:197, E:150, E:257, and E:258. E:158–164 partly restate FR text that semantic and component rows also apply. D:136 and D:138 carry surface order and Focus behavior that E:148, E:91, and E:92 own. *Fix:* keep one authoritative statement in each case and reference it elsewhere; retain repetition only where a flow step needs it.

## 7. Inheritance discipline — adequate

`sources` are identical in both spines and all local paths resolve (the Notion URL was not opened, per the brief). SC names match verbatim. Component names match across every section, and E's token references resolve. A-1–A-6 remain unconfirmed, with exact semantics, owners, and revisit conditions retained by reference and in the memlog. No confirmed user choice was altered.

### Findings

- **medium — I1. The PRD's "knowledge maintainer" role is never mapped.** That exact term has zero occurrences in either spine (PRD §2, FR-12, FR-13). E uses "project-designated maintainer" and "maintainer" (E:98, E:224, E:229). UX-09 confirms exceptions and manual review, while the PRD role also covers policy configuration and withdrawal. E:100 and E:225 never say who may change the mode. Architecture could model one role or two. *Fix:* add one line, preserving the user's term and assigning no real people: "A project-designated maintainer is the PRD's knowledge maintainer for that project," or state explicitly if they differ. Name that authority in the S6 policy rule.

- **low — I2. Stable decision IDs are replaced by "latest" wording.** E never cites UX-11, UX-12, UX-13, UX-15, or UX-17 (E:25, E:40, E:57, E:166, E:168, E:254 use phrases such as "latest Focus request"), and later decisions have already made "latest" wrong. UX-16 is a sample boundary and needs no citation. *Fix:* cite the memlog IDs.

- **low — I3. `[OPEN]` is defined but never applied.** It appears only in the E:32 and E:34 definitions. E:272 lists bounded refinements without shared alias authority or the palette (E:90, E:166), so real open items are harder to find. *Fix:* tag remaining items `[OPEN]` and add them to the register, or remove the label.

- **low — I4. Some handoff evidence links only to `.working/`.** D:122 and E:270 point to `.working/palette-contrast.md` and `.working/source-prd.md`, a folder the skill treats as working space. A-1–A-6 are also safe in the PRD and memlog, but the contrast evidence is not. *Fix:* promote the contrast calculation or confirm `.working/` ships with the package.

## 8. Shape fit — strong

DESIGN.md keeps canonical section order. EXPERIENCE.md has all required defaults plus triggered Responsive & Platform and Inspiration & Anti-patterns sections. Its two invented sections (semantics and the assumptions register) earn their place. Depth exceeds the five shape examples, which is defensible because they cover far smaller products.

### Findings

- **low — SH1. The Responsive table specifies only part of the surface set.** E:148 gives phone order for S1 and full-width rules for S2, S4, and S6. S7's wide table and S3, S5, and S8 have no phone rule beyond D:187's general warning; D:138 covers S10 separately. `daily-work.html` uses 540px and 800px breakpoints rather than D:134's 600/1024px. *Fix:* add one general rule or per-surface phone rows, starting with S7 tables, and align the mock breakpoints.

## Mechanical notes

- **Names and links:** no broken local links or frontmatter paths; no unresolved tokens; no component-name drift (23 of 23 across frontmatter and both tables). Mermaid is not used.
- **Frontmatter:** both spines are `status: draft`, as expected before finalization. `spacing.1` and `spacing.6` have no `{path}` reference but are part of the stated scale (D:132).
- **Contrast:** recalculated values match all 25 reported pairs and are token calculations only, not rendered-state results. `control-outline` is correctly the control boundary; `divider` is correctly decorative.
- **Usage fixture arithmetic:** `usage.html` totals are internally consistent (1.60M units, 1.20M priced + 0.40M unpriced, $7.20).
- **Stale working note, not a spine defect:** `.working/draft-coverage.md` still says 21 components and "S3–S10 spine-only." Neither spine links it.

## Not treated as defects

These are implementation validations or known boundaries:

- Real Jira, GitHub, or Bitbucket integrations and the outside-repository live sample, which was not inspected
- Claude and Codex enrollment, and Notion skill reading
- Push delivery and packaging
- Authorization enforcement
- Final provider artwork
- Standalone palette rendering as proof of accepted color
- Pilot success
- A-1–A-6 outcomes at their stated checkpoints
- Framework and architecture choices

Source reconciliation is coverage evidence, not a usability test, and this review does not treat it as one.
