# Owl Mast UX — accessibility and responsive review

**Lens:** accessibility and responsive behavior only. **Date:** 2026-11-05. **Status:** independent validation before finalization.

**Method:** static reading of `DESIGN.md`, `EXPERIENCE.md`, the ten surface references and `gallery.html`, including their CSS and scripts, plus `.working/palette-contrast.md`, the study notes and the memlog. Nothing was rendered, executed or tested with assistive technology. Layout widths marked "static estimate" are calculated from CSS, not measured. WCAG criteria are named only to explain why a finding matters; this is not a WCAG conformance claim.

## Summary

| Severity | Count | IDs |
|---|---:|---|
| Critical | 0 | — |
| High | 2 | A11Y-01, A11Y-02 |
| Medium | 12 | A11Y-03 – A11Y-14 |
| Low | 8 | A11Y-15 – A11Y-22 |

**Overall:** the accessibility floor is sound, and most gaps are small additions to it. The two high findings share one cause: focus and announcements are specified for user-triggered disclosure, but not for content that changes by itself or for arrival from outside the current page. Every observed update pushes by default, so J7 and live refresh will exercise both paths constantly.

**Severity scale**
- **Critical:** blocks a core flow for a whole group of users as specified.
- **High:** building a core flow as written would likely create a serious barrier.
- **Medium:** a contract gap or copied reference pattern would create a barrier on a specific flow or view.
- **Low:** limited impact, semantic clean-up or reference hygiene.

**Finding types**
- **Contract:** `DESIGN.md` or `EXPERIENCE.md` is silent or self-conflicting; change the spine.
- **Reference:** a mockup departs from the spines. The spines take precedence (`EXPERIENCE.md:150`), so this is not a contract defect, but correct it if implementers will copy the pattern.

## Boundaries respected

- **User decisions preserved:** every-update push, no digest or attention-only substitution (UX-10), customizable owl aliases and colors, fixed type icon and label (UX-15), the accepted owl mark, color direction and mobile appearance (UX-13), and observation-only V1 (UX-06). No fix below changes these.
- **Proposals:** generic lock-screen preview, palette details, grouping and layouts remain `[P]`. Fixes refine them; they do not treat them as user preferences.
- **Assumptions:** A-1–A-6 are untouched.
- **Prototype state:** disabled source actions, static navigation `<span>`s, illustrative data and host theme tokens are not reported as product defects. Host-token rendering was not used to judge the exact palette.

---

## High

### A11Y-01 — Live refresh and removal of focused content are only partly specified
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

### A11Y-02 — Arrival focus, announcement and return path are undefined for notification and contextual entry
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

## Medium

### A11Y-03 — Identical generic pushes give no way to tell updates apart
**Type:** Contract
**Location:** `EXPERIENCE.md:245`, `:246`, `:250`; `mockups/notifications.html:10` ("Owl Mast has an update").

**Evidence:** default every-update push [U] combined with a proposed generic preview [P] produces repeated identical notifications. The S9 reference shows "Opened from the 08:32 notification", but `EXPERIENCE.md` does not require anything equivalent. `:250` dedupes replays but does not require distinct updates to stay distinct at the platform level.

**Impact:** screen-reader users hear the same sentence for every update and cannot judge which matters before opening. Sighted users are in the same position. After opening one, nothing leads to the others. On some platforms, a reused notification identifier would also replace earlier notifications, which conflicts with the no-silent-loss intent.

**Minimal fix:** keep every-update push and the generic default, and add to J7:
- Each distinct source event uses its own notification identity; only replays dedupe.
- Arrival shows the notification time and a labeled link to other updates since then in S1.
- Platform stacking is acceptable only if no update is dropped or summarized away.

### A11Y-04 — Interactive chips can nest or overlap; agent-chip interactivity is undefined
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

### A11Y-05 — Personal agent colors have no measured palette and overlap reserved status colors
**Type:** Contract
**Location:** `DESIGN.md:19`–`45` (no identity or chart tokens), `:122`, `:162`; `EXPERIENCE.md:166`; `mockups/connections.html:10` (options Blue, Cyan, Amber); `mockups/knowledge-detail.html:42`, `:44` (hard-coded `#C7A06D`, `#9F8CEB`).

**Evidence:** the spine requires an "accessible color palette" and readable markers, but no such tokens exist. The contrast calculation has no identity pairs, and `DESIGN.md:122` forbids unmeasured accents. The prototype's color options match the blue, cyan and amber used for selection, knowledge and attention, even though `DESIGN.md:162` says personal color never implies status. Calculated from the exact palette, the hard-coded markers fall below the 3:1 target in light mode:

| Marker | Light card | Light secondary surface | Dark card | Dark secondary surface |
|---|---:|---:|---:|---:|
| `#C7A06D` | 2.42:1 | 2.11:1 | 7.21:1 | 6.23:1 |
| `#9F8CEB` | 2.83:1 | 2.47:1 | 6.17:1 | 5.33:1 |

**Impact:** because the alias and type text remain, this is not a color-only failure. It does mean the requested color differentiation fades for low-vision users in light mode, and an amber owl can read as "needs attention".

**Minimal fix:** keep color customization and add a designer-proposed set of named light/dark identity pairs, each ≥3:1 on card and secondary surface. Add them to the contrast calculation. Avoid exact semantic hues, or keep identity visibly distinct from status markers by using a different marker shape. Alias and type text stay mandatory.

### A11Y-06 — Selected filters and view switches rely on a 1.15:1 fill change
**Type:** Reference, with a Contract clarification
**Location:** `mockups/daily-work.html:36`, `:96`; `mockups/focus.html:40`; `DESIGN.md:122`, `:150`.

**Evidence:** selected state is a card fill on a secondary surface, or the reverse, at a calculated 1.15:1 in light and 1.16:1 in dark, plus a text-color and weight change. `aria-pressed` is correct programmatically. `DESIGN.md:150` asks for "a visible indicator" but gives no contrast target for it. Background-only indicators may also disappear in Windows forced-colors mode, and no reference has a `forced-colors` rule.

**Impact:** low-vision users may not be able to see which person, layout or event filter is active, including whether they are viewing their own work or Mohamed's. Relevant to WCAG 1.4.11.

**Minimal fix:** in `DESIGN.md:150`, say that the selection indicator is ≥3:1 and is not background-only. In the references, add a 2px primary underline or inset outline to the existing selected state. No layout change is needed.

### A11Y-07 — Focus ring is clipped on Focus board epic disclosures
**Type:** Reference
**Location:** `mockups/focus.html:14` (outline with 3px offset), `:43` (`.epic { overflow: hidden }`), `:59` (full-bleed `.epic-work > summary`).

**Evidence:** the ring draws 3–6px outside a summary that spans the full width of a clipping parent. Left and right edges are clipped for every epic, and the bottom edge too when collapsed, leaving only the top edge visible.

**Impact:** this weakens the 3px focus indicator on the primary control of each S10 epic group (`DESIGN.md:150`). Relevant to WCAG 2.4.7. This pattern was checked in Daily Work and does not recur there: its focusable content has at least 14px of inset.

**Minimal fix:** on this one selector, use a negative `outline-offset` such as `-3px`, or inset the summary by 8px.

### A11Y-08 — Focus board run links: accessible name, target size and return path
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

### A11Y-09 — Key facts and field labels are set at 12px
**Type:** Reference, with a small Contract gap
**Location:** `DESIGN.md:126`, `:185`.
- `mockups/focus.html:36` (Project scope label), `:41` (assigned ticket and run counts), `:91` (`.run-state`: "Reported active · 08:42"), `:96` (counted-once note), `:111`, `:113` (source state time).
- `mockups/connections.html`, `administrator-setup.html`, `notifications.html`, line 6: `.meta` ("Last successful collection 07:55", "Latest collection 09:18"), `.readiness-time`, `.notification-state-label`, `.workspace span` ("Authorized administrator").

**Evidence:** `DESIGN.md:126` keeps key facts, source identity, access messages and labels at the 14px floor. These uses aren't supplementary. Freshness is not named in that list, although `:185` requires it to be readable. The Daily Work, S2, S3, S4, S6 and S7 references correctly avoid 12px outside their study notes.

**Impact:** totals, field labels, access role and collection freshness become the smallest text on the phone, which works against the product's core promise of readable evidence.

**Minimal fix:** add "freshness and field labels" to `DESIGN.md:126`. Move these selectors to 14px, reserving 12px for truly supplementary text.

### A11Y-10 — "Persist" and "remain visible" could produce a blocking sticky scope bar
**Type:** Contract
**Location:** `DESIGN.md:155`; `EXPERIENCE.md:83`, `:135`, `:138`.

**Evidence:** `scope-bar` must "persist" and "remain visible" while wrapping on phone. This does not say whether that means present on each surface or fixed during scrolling. No reference makes it sticky, but an implementer could reasonably do so. A wrapped project, source and period bar at 200% text or in phone landscape could take much of the viewport.

**Impact:** low-vision and landscape users could have little reading area left, and focused content could be obscured despite `:135`. Relevant to WCAG 1.4.10 and 2.4.11.

**Minimal fix:** clarify that persistence means present in the page and on each summary or detail surface. It does not stick at compact widths or enlarged text. A wide-layout sticky bar must leave focused content unobscured.

### A11Y-11 — Long evidence and usage views lack phone, zoom and paging rules
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

### A11Y-12 — Phone-width clipping risk under enlarged text
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

### A11Y-13 — Feed event type is exposed only through a hidden icon
**Type:** Reference
**Location:** `mockups/daily-work.html:298`, `:103`–`:105`; `DESIGN.md:166`.

**Evidence:** `activity-list` requires "event type" in each row. In the mock, the only type marker is an `aria-hidden` icon, colored by kind. Icon shapes differ, so it's not strictly color-only visually, but it provides no text and nothing programmatic. Filters offer "Needs input / Closed / Knowledge / Reviews", yet rows carry no matching label.

**Impact:** screen-reader users, and anyone who doesn't memorize the icons, must infer type from the title. The filtered categories can't be verified on the row.

**Minimal fix:** add a short visible type label to each row, using the same vocabulary as the filters. Keep the icon decorative.

### A11Y-14 — S9 settings pattern lacks group semantics and a matching label
**Type:** Reference (the controls are deliberately disabled; the semantic pattern is what would be copied)
**Location:** `mockups/notifications.html:10`; `DESIGN.md:172`; `EXPERIENCE.md:134`.

**Evidence:**
- "Followed project scope" is a `<p>` above checkboxes, with no `fieldset` and `legend`; no reference has one.
- Appearance has a visible `<p>Appearance</p>` while the select's real label is sr-only "Theme", so the visible and programmatic names differ.
- `DESIGN.md:172` requires a persistent label above the field.

**Impact:** a screen-reader user hears "Syntelligence, checkbox" without the group's meaning at J7's first step, and a speech user can't say the visible "Appearance". Relevant to WCAG 1.3.1 and 2.5.3.

**Minimal fix:** use `fieldset` and `legend` for the followed-project group. Make "Appearance" the visible `<label>` of the select.

---

## Low

### A11Y-15 — Repeated disclosure labels lack context
**Type:** Reference
**Location:** `mockups/connections.html:10` ("Readiness evidence" ×4); `mockups/usage.html:118`, `:119` ("Inspect attribution" ×2); `mockups/daily-work.html:298` ("View evidence" ×4 rendered); `mockups/focus.html:223` ("Work evidence" ×5, "Usage & cost: Unavailable" ×8 rendered in the By epic view); `EXPERIENCE.md:124`.

**Impact:** in a screen reader's controls list or with voice commands, the triggers are indistinguishable.

**Minimal fix:** add visually hidden context such as the ticket key or client/project. Keep the visible text.

### A11Y-16 — CSS disclosure markers may enter the accessible name
**Type:** Reference
**Location:** `mockups/work-detail.html:54`–`:55`, `mockups/usage.html:67`–`:68` (`+`, `−`); `mockups/knowledge.html:23` and the same rule in `knowledge-detail.html` and `promotion.html` (`›`, `⌄`). The Daily Work, Focus and shell references already use `aria-hidden` SVG chevrons correctly.

**Impact:** some browser and screen-reader combinations may read "Inspect attribution plus", on top of the native expanded state.

**Minimal fix:** reuse the `aria-hidden` SVG chevron, or use `content: '+' / ''`, subject to the browser-support check.

### A11Y-17 — `aria-label` on generic elements
**Type:** Reference
**Location:** `mockups/daily-work.html:203` (`.summary`), `:233` (`ticketChip`; also `focus.html:191`), `mockups/knowledge.html:39` (`.filter-row`).

**Evidence:** these `<span>` and `<div>` elements have no role, and support for naming them is unreliable. The chip's source qualification is otherwise only in a hover `title`. Project/source context is usually visible nearby, so this isn't a data loss on screen, but `EXPERIENCE.md:89`'s qualification may not be heard.

**Minimal fix:** use visually hidden text inside the chip, and `role="group"` on named groups.

### A11Y-18 — `<p>` placed directly in `<dl>` groups detaches provenance from its value
**Type:** Reference
**Location:** `mockups/work-detail.html:123`–`:126`; `mockups/usage.html:107`–`:110`.

**Impact:** invalid `dl` structure can leave source or coverage notes unassociated with their fact, for example "1.20M tokens priced · 0.40M unpriced".

**Minimal fix:** move each `<p>` into its `<dd>`, or into a second `<dd>`.

### A11Y-19 — Component tokens conflict with text rules
**Type:** Contract
**Location:** `DESIGN.md:75` vs `:158` (`attention-item` token uses attention text; the table says the body is main text); `DESIGN.md:90` vs `:113` (`state-message` uses secondary text, while permission and failure text should be main text).

**Impact:** both pairs pass contrast (5.41:1 or better), so this isn't a contrast failure. An implementer following the token would lower emphasis on failures, permissions and attention text.

**Minimal fix:** set both component text tokens to `{colors.text}`. Use the attention color only on the marker, and secondary text only for supporting lines.

### A11Y-20 — Other reference drift from the spines
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

### A11Y-21 — Standalone references lose focus rings or fall below the ring target
**Type:** Reference (does not affect the product or host-rendered previews)
**Location:** `daily-work.html:14`, `focus.html:14`, and line 6 of `connections.html`, `administrator-setup.html`, `notifications.html`, all using `var(--ring)` with no fallback. `knowledge.html:10`, `knowledge-detail.html:10`, `promotion.html:10` use a fixed `#2456D6` fallback that their dark media query doesn't override.

**Evidence:**
- Without host tokens, an undefined variable invalidates the outline at computed-value time, so the rule removes the browser's default ring as well. The same applies to progress fills and agent dots.
- In dark mode, `#2456D6` calculates to 3.07:1 on canvas, 2.81:1 on card and 2.42:1 on secondary surface.
- `DESIGN.md` links these files directly, so opening them outside the host is a realistic way to review them.

**Impact:** reviewers could misjudge focus visibility and bars, or validate the wrong thing.

**Minimal fix:** give the tokens exact-palette fallbacks, or label each file as host-rendered only. The existing "not proof of the standalone palette" note doesn't cover the lost focus ring.

### A11Y-22 — Gallery chooser label and iframe height
**Type:** Reference
**Location:** `mockups/gallery.html:1`.

**Evidence:** `aria-label="Choose a visual reference"` overrides the visible "Screen" label. Height is set only on load, capped at 1750px, so expanding details adds nested scrolling in the frame.

**Impact:** a speech-input mismatch, plus awkward nested scrolling at phone widths. This affects review only.

**Minimal fix:** remove the `aria-label`, and either update the height when disclosures toggle or link each screen to its standalone file.

---

## Checked with no defect found

Static checks only; these still need the runtime verification below.

- **Palette arithmetic:** I recomputed all 25 pairs in `.working/palette-contrast.md`, and they match in both themes, including on-primary at 6.22:1 and 8.70:1. Control outline passes at 3.32:1 or better.
- **Decorative dividers:** dividers calculate below 3:1 by design, which `DESIGN.md:122` correctly declares; they aren't used as sole control boundaries.
- **Expandable details:** native `details`/`summary`, with keyboard behavior and expanded state from the platform. The spec at `EXPERIENCE.md:124` is sound.
- **Scripted filters:** Daily Work and Focus use `aria-pressed`, a polite status region and focus that stays on the trigger.
- **Progress:** measured bars carry `aria-valuetext` with the basis, Unknown has no false progressbar, and decorative bars are hidden with a text equivalent alongside.
- **Status:** connection, readiness and check states pair markers with text, so none is color-only.
- **Motion:** only a short chevron transition exists, it's disabled under reduced motion, and in-page jumps use instant scrolling. `work-detail.html` and `usage.html` lack the media query but have no transitions.
- **Zoom:** no viewport disables scaling.
- **Touch:** all checked controls meet 44px, apart from the A11Y-08 link. No required drag, hover-only action or keyboard shortcut is specified.
- **Disabled prototypes:** each has a nearby reason or a shared description, and promotion actions name their version and audience.
- **Usage:** visual bars are hidden with a text equivalent in the same row, and missing cost reads as Unavailable, never zero.

## Remaining implementation verification

These are downstream tests, not defects in the UX contract. All depend on architecture and packaging choices that are still open.

1. **Real rendering:** every S1–S10 surface at 320, 390, 768 and 1024+ CSS px, at 200% text and 400% browser zoom, in landscape, and with WCAG 1.4.12 text spacing. Confirm no loss of content and re-check the A11Y-12 estimates.
2. **Exact palette in rendered states:** the final standalone theme in both modes, including hover, focus, selected, disabled, overlays, tints and any chart.
3. **Assistive technology:** VoiceOver (iOS and macOS), TalkBack, and NVDA or JAWS, covering `summary` styled with `display: flex`, pseudo-element markers, live regions, chips and dynamic filters.
4. **Keyboard:** the compact navigation menu, skip link, landmarks, overlay focus containment, Escape behavior and focus not obscured. The references have static navigation and no skip link, so none of this has been exercised.
5. **Live behavior:** a refresh, revocation and load-more test against the A11Y-01 and A11Y-11 rules, including reconnect.
6. **Push:** per platform, cover permission states, lock-screen reading, distinct notification identity, stacking, deep-link arrival and offline or revoked entry. Actual delivery is still unvalidated (`EXPERIENCE.md:250`).
7. **User text settings:** px-based tokens and breakpoints should map to relative units or platform text scaling, such as iOS Dynamic Type and Android font scale, once packaging is chosen.
8. **Forced colors:** progress fills, selection indicators, identity markers and status dots in Windows forced-colors mode.
9. **Other WCAG 2.2 AA items not exercised here:** accessible authentication in enrollment and setup (3.3.8), consistent help (3.2.6), redundant entry (3.3.7), and timing or data loss on expired sessions.
10. **External and source content:** `↗` and other external indicators need text alternatives. Source text in other languages or right-to-left scripts needs correct language and direction handling. Localization itself remains undecided.
11. **Provider assets:** final type icons need alternative-text handling and contrast checks once the asset choice is made.

**Reminder:** this report is static evidence only. It doesn't certify WCAG conformance, and no integration or pilot behavior was tested.
