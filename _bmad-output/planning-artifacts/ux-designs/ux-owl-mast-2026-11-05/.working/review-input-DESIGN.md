---
name: Owl Mast
description: Readable work evidence and shared knowledge across laptop, tablet, and phone.
status: draft
updated: 2026-11-05
paired_with: EXPERIENCE.md
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
colors:
  canvas: '#F5F7FB'
  canvas-dark: '#0B1018'
  card: '#FFFFFF'
  card-dark: '#121A27'
  secondary-surface: '#EAF0F8'
  secondary-surface-dark: '#1B2738'
  text: '#172337'
  text-dark: '#EAF1FA'
  secondary-text: '#52627A'
  secondary-text-dark: '#A5B5CB'
  divider: '#D7E0EC'
  divider-dark: '#2E3C50'
  control-outline: '#74849B'
  control-outline-dark: '#73869E'
  primary: '#2456D6'
  primary-dark: '#91B5FF'
  on-primary: '#FFFFFF'
  on-primary-dark: '#0B1730'
  knowledge: '#086A7B'
  knowledge-dark: '#70D7E7'
  attention: '#845900'
  attention-dark: '#F0C268'
  success: '#176B50'
  success-dark: '#72D6AF'
  error: '#B23549'
  error-dark: '#FF95A5'
typography:
  title: {fontFamily: 'system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif', fontSize: 28px, fontWeight: '650', lineHeight: '1.2', letterSpacing: -0.02em}
  title-compact: {fontFamily: 'system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif', fontSize: 25px, fontWeight: '650', lineHeight: '1.25'}
  heading: {fontFamily: 'system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif', fontSize: 18px, fontWeight: '600', lineHeight: '1.4'}
  body: {fontFamily: 'system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif', fontSize: 16px, fontWeight: '400', lineHeight: '1.5'}
  row: {fontFamily: 'system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif', fontSize: 14px, fontWeight: '400', lineHeight: '1.5'}
  label: {fontFamily: 'system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif', fontSize: 14px, fontWeight: '600', lineHeight: '1.5'}
  meta: {fontFamily: 'system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif', fontSize: 12px, fontWeight: '400', lineHeight: '1.5'}
  identifier: {fontFamily: 'ui-monospace, SFMono-Regular, Consolas, monospace', fontSize: 14px, fontWeight: '400', lineHeight: '1.5'}
rounded:
  sm: 6px
  md: 8px
  lg: 12px
  full: 9999px
spacing:
  '1': 4px
  '2': 8px
  '3': 12px
  '4': 16px
  '5': 24px
  '6': 32px
  page-compact: 16px
  page-wide: 32px
  control-target: 44px
components:
  brand-mark: {textColor: '{colors.primary}', size: 24px}
  scope-bar: {backgroundColor: '{colors.card}', textColor: '{colors.text}', typography: '{typography.label}', padding: '{spacing.4}'}
  surface-navigation: {backgroundColor: '{colors.canvas}', textColor: '{colors.secondary-text}', typography: '{typography.label}', padding: '{spacing.3}'}
  work-summary: {backgroundColor: '{colors.card}', textColor: '{colors.text}', typography: '{typography.title}', rounded: '{rounded.lg}', padding: '{spacing.4}'}
  attention-item: {backgroundColor: '{colors.card}', textColor: '{colors.attention}', typography: '{typography.row}', rounded: '{rounded.lg}', padding: '{spacing.4}'}
  progress-evidence: {backgroundColor: '{colors.secondary-surface}', textColor: '{colors.text}', typography: '{typography.label}', rounded: '{rounded.sm}'}
  work-record: {backgroundColor: '{colors.card}', textColor: '{colors.text}', typography: '{typography.row}', padding: '{spacing.4}'}
  ticket-chip: {backgroundColor: '{colors.secondary-surface}', textColor: '{colors.primary}', typography: '{typography.identifier}', rounded: '{rounded.full}', padding: '{spacing.2}'}
  agent-chip: {backgroundColor: '{colors.secondary-surface}', textColor: '{colors.text}', typography: '{typography.label}', rounded: '{rounded.full}', padding: '{spacing.2}'}
  focus-board: {backgroundColor: '{colors.canvas}', textColor: '{colors.text}', typography: '{typography.row}', padding: '{spacing.4}'}
  epic-group: {backgroundColor: '{colors.card}', textColor: '{colors.text}', typography: '{typography.heading}', rounded: '{rounded.lg}', padding: '{spacing.4}'}
  evidence-detail: {backgroundColor: '{colors.secondary-surface}', textColor: '{colors.text}', typography: '{typography.body}', rounded: '{rounded.md}', padding: '{spacing.4}'}
  activity-list: {backgroundColor: '{colors.card}', textColor: '{colors.text}', typography: '{typography.row}', rounded: '{rounded.lg}', padding: '{spacing.4}'}
  knowledge-record: {backgroundColor: '{colors.card}', textColor: '{colors.text}', typography: '{typography.body}', rounded: '{rounded.lg}', padding: '{spacing.4}'}
  delivery-receipt: {backgroundColor: '{colors.secondary-surface}', textColor: '{colors.text}', typography: '{typography.row}', rounded: '{rounded.md}', padding: '{spacing.3}'}
  connection-readiness: {backgroundColor: '{colors.card}', textColor: '{colors.text}', typography: '{typography.row}', rounded: '{rounded.lg}', padding: '{spacing.4}'}
  promotion-review: {backgroundColor: '{colors.card}', textColor: '{colors.text}', typography: '{typography.body}', rounded: '{rounded.lg}', padding: '{spacing.4}'}
  usage-breakdown: {backgroundColor: '{colors.card}', textColor: '{colors.text}', typography: '{typography.row}', rounded: '{rounded.lg}', padding: '{spacing.4}'}
  settings-field: {backgroundColor: '{colors.card}', textColor: '{colors.text}', typography: '{typography.body}', rounded: '{rounded.md}', padding: '{spacing.3}'}
  state-message: {backgroundColor: '{colors.secondary-surface}', textColor: '{colors.secondary-text}', typography: '{typography.row}', rounded: '{rounded.md}', padding: '{spacing.4}'}
  action-control: {backgroundColor: '{colors.primary}', textColor: '{colors.on-primary}', typography: '{typography.label}', rounded: '{rounded.md}', padding: '{spacing.3}'}
  action-control-dark: {backgroundColor: '{colors.primary-dark}', textColor: '{colors.on-primary-dark}', typography: '{typography.label}', rounded: '{rounded.md}', padding: '{spacing.3}'}
  external-link: {textColor: '{colors.primary}', typography: '{typography.label}'}
---

## Brand & Style

**Draft visual contract.** The user delegated visual design and color choices (UX-03 in [.memlog.md](.memlog.md)). The tokens and visual rules below are **delegated design decisions**, not claims about the user's personal preferences. Behavior and unresolved choices live in [EXPERIENCE.md](EXPERIENCE.md). Both spines take precedence over exploratory mocks and imported references.

Owl Mast is a focused workspace for understanding work and receiving useful learning. Neutral ink/slate surfaces make room for readable evidence. Blue marks orientation and navigation; cyan identifies knowledge; amber draws attention to an observed issue. Work status is legible before decorative detail. Modest summaries lead into the records behind them, rather than overwhelming those records.

The user values ConvaDesk's concepts and UX, not its appearance. Ponytail's compact panels, fine boundaries, and selective accents inform the direction: [inspected dark reference](.working/reference-ponytail-board.png), [primary image source](https://raw.githubusercontent.com/DietrichGebert/ponytail/main/assets/band/board.png). Neither its branding nor its dark-only presentation is adopted. The user accepted the displayed colors, mobile appearance, and generated owl mark in the [daily-work study](mockups/daily-work.html); preserve that mark. AISQUAD brand ideas may inform future refinement, but do not replace the accepted mark. No UI framework or implementation stack is selected.

The accepted [owl mark](assets/owl-mark.svg) preserves the study's 24×24 geometry, unfilled paths, rounded stroke caps/joins, and 1.8-unit stroke. Use its `currentColor` with the theme's primary token; pair it with the Owl Mast wordmark text. Do not redraw it or substitute another brand asset.

**Delegated design decision:** provide light and dark themes, follow the device theme initially, and allow an explicit user override. Apply every unsuffixed color in light mode and its `-dark` counterpart in dark mode; the mapping applies to component token references too. Component variants are separate entries, as illustrated by `action-control-dark`.

## Colors

| Role | Token pair | Use |
|---|---|---|
| Canvas, panel, nested evidence | `{colors.canvas}` / `{colors.canvas-dark}`; `{colors.card}` / `{colors.card-dark}`; `{colors.secondary-surface}` / `{colors.secondary-surface-dark}` | Three tonal layers; avoid nested card stacks deeper than necessary. |
| Main and supporting text | `{colors.text}` / `{colors.text-dark}`; `{colors.secondary-text}` / `{colors.secondary-text-dark}` | Supporting text stays readable; use main text for permission, progress basis, and failures. |
| Dividers and controls | `{colors.divider}` / `{colors.divider-dark}`; `{colors.control-outline}` / `{colors.control-outline-dark}` | Fine dividers organize; stronger outlines identify controls and focus boundaries. |
| Orientation and selection | `{colors.primary}` / `{colors.primary-dark}` | Active navigation, links, known measured progress, permitted primary actions. |
| Text on primary fill | `{colors.on-primary}` / `{colors.on-primary-dark}` | Only on the matching primary fill. |
| Knowledge | `{colors.knowledge}` / `{colors.knowledge-dark}` | Knowledge type markers and delivery events; color does not imply approved or reused. |
| Attention | `{colors.attention}` / `{colors.attention-dark}` | Observed request, blocker, or review need; never inferred from missing telemetry. |
| Known success | `{colors.success}` / `{colors.success-dark}` | Specific reported event/check with a text label; never a universal acceptance verdict. |
| Error | `{colors.error}` / `{colors.error-dark}` | Failed collection, failed permitted operation, or destructive knowledge lifecycle action. |

Contrast targets follow [WCAG 2.2](https://www.w3.org/TR/WCAG22/): normal text **≥4.5:1**, large text **≥3:1**, meaningful control/focus boundaries **≥3:1** against adjacent surfaces. All 25 tested pair types pass in both themes in the [exact-palette calculation](.working/palette-contrast.md); primary-fill text measures 6.22:1 light and 8.70:1 dark. This calculation does not validate rendered states, overlays, graphs, or the final app. Dividers are decorative and must not be the sole control boundary. Do not reduce text opacity or introduce unmeasured accent tints.

## Typography

Use the system sans family; IDs use the system monospace family. No font download is required. Body copy and inputs use `{typography.body}`; compact evidence lists use `{typography.row}`; labels use `{typography.label}`. Key facts, source identity, progress basis, access messages, and actions remain **at least 14px**. `{typography.meta}` is reserved for supplementary text. Keep compact labels at the same readable floor as other operational facts.

Use `{typography.title}` on wide layouts and `{typography.title-compact}` on compact layouts. Headings use `{typography.heading}`. Counts use tabular numerals; large counts never replace their denominator, period, or measurement label. Allow text scaling and wrapping; truncate only optional previews with an accessible expansion.

## Layout & Spacing

Use the 4/8/12/16/24/32px spacing scale. Wide-page margins use `{spacing.page-wide}`; compact margins use `{spacing.page-compact}`. Panels use `{spacing.4}` padding, grouped sections `{spacing.5}` gaps. Controls have a minimum hit area of `{spacing.control-target}` in both dimensions and grow with text.

**Designer proposal:** at 1024px and above, a persistent navigation rail and a flexible two-column main area support summaries, attention, work, and evidence. At 600–1023px, navigation collapses to a labeled menu; compatible panels can share a row. Below 600px, use one reading column and full-width details. Do not shrink information to preserve desktop columns. The main reading area may grow to 1440px; long prose stays near 70 characters per line.

The proposed Daily Work order is scope and period → own/colleague summary → attention → epic and ticket evidence → recent updates → collection coverage. This is an IA proposal, not a confirmed feed-versus-wall choice. The [daily-work study](mockups/daily-work.html) illustrates local filtering and expandable evidence; [study notes](.working/direction-daily-work-notes.md) explain the intent. The HTML inherits preview-host theme tokens, so it is **not visual proof of these exact standalone colors**. Its fixture dates, records, and counts are illustrative.

**User-confirmed addition:** Focus is a separate board for assigned work, not the Daily Work landing page. **Designer proposal:** stack readable epic groups, with a combined view available; within each group show observed work and agent contributions. On phone, groups remain vertically stacked and cards retain source/status labels. Parallel agent activity across several epics is visible without implying that each agent belongs to only one epic. The [Focus study](mockups/focus.html) demonstrates both arrangements and project filtering; [study notes](.working/key-focus-notes.md) explain shared runs, unmatched work, and the distinction between assigned tickets and whole-epic context.

## Elevation & Depth

Use tonal surfaces and fine dividers for hierarchy. Persistent panels have no shadow. A temporary overlaid detail may use a restrained shadow only to distinguish it from the retained page; that shadow must not replace its boundary or focus handling. Ordinary evidence expansion stays in the reading flow. No glow, animated pulse, or decorative blur is required.

## Shapes

Panels use `{rounded.lg}` (12px), controls and nested evidence `{rounded.md}`, and compact markers `{rounded.sm}`. `{rounded.full}` is reserved for small identity/status markers. Rounded progress tracks remain supplemental to text. Unknown progress has no filled bar; it uses a readable text state.

## Components

Names below match EXPERIENCE.md exactly. All component colors follow the theme mapping above. Selected state has a visible indicator plus a label/state change; hover is supplemental; focus uses a 3px control outline with a 2px offset. Disabled controls retain readable labels and a nearby reason.

| Component | Visual contract |
|---|---|
| `brand-mark` | Accepted 24px owl SVG, theme-primary stroke, paired with the Owl Mast name; retain its proportions and geometry. |
| `scope-bar` | Project/company label, source identity, and period remain visible. Wrap on phone; do not compress them into unlabeled icons. |
| `surface-navigation` | Text labels with a blue selection indicator; compact navigation uses a labeled menu. |
| `work-summary` | Modest count, explicit noun, reporting period, and coverage. No trophy styling or person ranking. |
| `attention-item` | Amber marker and explicit reason, work reference, source, and age. Body remains main text on a neutral panel. |
| `progress-evidence` | Blue measured bar paired with numerator/denominator and basis. Unknown/conflicting basis is text, without a fabricated value. |
| `work-record` | Title and source-qualified ID lead; owner, agents, status, and progress occupy separate labeled fields. |
| `ticket-chip` | Compact rounded ID tag; retain nearby project/source qualification. Text remains readable and wraps without obscuring the title. An interactive chip has a 44px hit area even when its visible capsule is smaller. |
| `agent-chip` | User-chosen owl display name, colored identity marker, fixed type icon, and readable Claude/Codex label. Type and status remain separate. Personal color never implies running, blocked, approved, or trusted. Prototype glyphs illustrate icon placement; final provider artwork remains an asset choice. |
| `focus-board` | Separate page with an explicit assigned-to-me scope, epic grouping/combined-view choice, and compact source-status labels. No dense horizontal-only layout. |
| `epic-group` | Epic heading, child-closure basis, blockers, and associated agent/work records; groups stack with consistent spacing. Shared/unknown attribution has a labeled area. |
| `evidence-detail` | Readable content column with compact provenance alongside on wide screens and above on phone; facts and inference use text labels. |
| `activity-list` | Chronological rows with event type, time, summary, and expandable evidence; no masonry or fixed-height clipped cards. |
| `knowledge-record` | Title, version, scope, lifecycle state, applicability, source, and review metadata. Cyan marks type, not trust. |
| `delivery-receipt` | Compact structured fields for recipient, project, item/version, time, and observed delivery/reuse state. |
| `connection-readiness` | Clearly separated observation and knowledge-readiness rows. Provider name and project/source account stay beside each result. |
| `promotion-review` | Exact candidate version and target audience dominate; checks, reasons, publication result, and history follow. |
| `usage-breakdown` | Full view has distinct measurement headings, aligned numbers, units, coverage, and unassigned rows. Compact ticket/epic summaries show the measurement class beside any amount and lead to detail. Missing cost says Unavailable, never a zero price. Charts have labeled data equivalents. |
| `settings-field` | Persistent label and description above field; selected value, validation, and help remain visible. |
| `state-message` | Plain title, scope-safe explanation, and useful next step. Loading shapes match the content area without fabricated numbers. |
| `action-control`, `action-control-dark` | Filled primary action, labeled text, 44px minimum target. Knowledge/admin actions only where authorized; destructive styling uses error text with explicit wording. |
| `external-link` | Underlined descriptive source label plus external-destination indicator; no play, launch, or resume icon. |

[Browse the screen gallery](mockups/gallery.html). Visual references: [work evidence](mockups/work-detail.html), [knowledge search and submission](mockups/knowledge.html), [version and delivery history](mockups/knowledge-detail.html), [client connections and appearance](mockups/connections.html), [promotion review](mockups/promotion.html), [usage and cost](mockups/usage.html), [administrator setup](mockups/administrator-setup.html), and [preferences and notification return](mockups/notifications.html). Each uses the defined components with illustrative data; native disclosures expose supporting or alternate states. Provider glyphs and owl aliases are prototype presentation, not verified provider artwork or real agent attribution.

Reference extraction: [ticket detail](imports/IMG_AB4D1C8F3C45-1.jpeg) informs `evidence-detail`; [dependency explorer](imports/IMG_A9CC932E588C-1.jpeg) informs inspectable relationships inside it; [overview](imports/IMG_EF516651E585-1.jpeg) informs `work-summary` and `attention-item`. [Usage summary](imports/IMG_BC54BCBE01C2-1.jpeg), [attribution table](imports/IMG_3626EBD8C28F-1.jpeg), and [table continuation](imports/IMG_DE187537BF11-1.jpeg) inform `usage-breakdown`. These are reference concepts, not accepted Owl Mast layouts or real Owl Mast measurements; [import manifest](imports/manifest.md) records their identity.

## Do's and Don'ts

| Do | Don't |
|---|---|
| Keep source, scope, denominator, and freshness readable beside the claim. | Use a big percentage to imply accepted delivery. |
| Use color with text/icon/state cues and measured contrast. | Make color the only evidence of status or reduce supporting text to illegibility. |
| Preserve focused detail and meaningful reading order across devices. | Force a dense dependency graph or wide table into phone-sized text. |
| Give unknown, partial, conflicting, and unavailable information their own visible states. | Fill an absent metric with zero or a guessed progress bar. |
| Treat the study as exploratory and the exact tokens as this draft's visual contract. | Infer a framework, storage system, accepted navigation, or successful connector from the mock. |
