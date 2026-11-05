# Draft spine coverage — 2026-11-05

Mechanical Pass 1 performed during drafting, not an opt-in independent reviewer run. Both spines remain `status: draft`. Both stay within the requested compact limits (DESIGN.md <240 lines; EXPERIENCE.md <380 lines). Sources: memlog, source extracts, journey/direction notes and HTML, six imported references, accepted mark asset, all five configured spine examples, local spec and validation reference. No upstream source or memlog was edited.

## Pass 1 results

| Category | Checked | Result / bounded gap |
|---|---|---|
| Flow coverage | SC-1, SC-2, SC-3 names preserved; eight named-protagonist flows have numbered steps, climax, and failure path. FR-1–21 map through IA/journeys and cross-cutting rules. | Structurally covered. J2's enrollment steps still inherit A-5; real integration mechanism and acceptance evidence remain pre-live dependencies. SC-2/SC-3 remain planned scenarios, not demonstrated results. |
| Token completeness | Parsed YAML; resolved every `{colors…}`, `{typography…}`, `{rounded…}`, `{spacing…}`, and component reference in both spines. All 26 color tokens are six-digit hex and form 13 light/dark pairs. | No unresolved token or missing pair. 25 token-pair types pass calculated contrast in both themes; actual rendered app/states still need validation. |
| Component coverage | 21 component/variant names in DESIGN.md frontmatter have meaningful visual and behavioral rows in both documents. | No missing component row. Dark color mapping is explicit; action-control-dark is a separate named variant. |
| State coverage | All ten IA surfaces have cold-load/focus/access/offline baseline plus their own empty/error/stale/unsupported treatments. | No unrepresented surface. Notification arrival, mobile app packaging, and offline capability are not assumed. |
| Visual reference coverage | All six imported images and import manifest have inline relevant links. Daily-work HTML, notes, Ponytail reference, and palette evidence are linked. Every local link and frontmatter source path resolves. | No import orphan. No mockups/ or wireframes/ keepers yet. S1 and inline S2 have exploratory HTML only; S3–S10 remain spine-only, including the newly requested Focus board. Final mock coverage choice remains facilitator work. |

DESIGN.md canonical section order is correct. EXPERIENCE.md contains every required section plus responsive/platform, inspiration, and product-specific evidence semantics. The source-PRD assumptions link retains exact A-1–A-6 semantics/owners/revisit conditions; no answer to UX-Q1–3 was treated as wholesale assumption confirmation.

## Decision and IA synopsis

- Confirmed: dedicated laptop/tablet/phone UI; V1 observes and supplies knowledge; actions stay in T3/other tools; ticket percentages use completed criteria/checklists or Unknown; agents search knowledge when needed; project-designated maintainers handle exceptions/manual review; every observed work update triggers push by default.
- Confirmed addition: Focus is a separate assigned-work board, not the landing page. Concurrent epics and agents must be visible; the draft proposes stacked epic groups plus a combined view and explicitly avoids duplicate aggregates, inferred assignments, or source mutations.
- Proposed navigation: Daily Work / Focus / Knowledge / Connections / Usage; Promotion within Knowledge, setup within Connections, Preferences utility. Ten IA surfaces have matching named journeys. Daily Work/notification coverage is the authorized connected project scope, not silently only assigned-to-me work.
- User accepted displayed colors/mobile view and generated owl mark. Exact standalone palette remains distinguished from host-token rendering; system-theme default, type ramp, 12px panels, and accessible control outlines are delegated design decisions.

## Remaining handoff work

1. Facilitator offers optional validation and mock-coverage choice; do not mark the draft final before the skill's closing steps.
2. Focus needs its own visual study; the existing landing-page study cannot stand in for it. Knowledge delivery/promotion layouts remain covered in tables until mock choice is resolved.
3. Reconcile user inputs and update mock links if keeper artifacts are created. Root owns durable Notion updates and canonical memlog.
4. Preserve A-1–A-6 at their original checkpoints. Architecture validates actual enrollment/reading, push/platform constraints, source links, authorization behavior, and collection/retention support. No framework/storage choice or integration success is claimed by this draft.

UX-Q1–3 are closed by UX-08–10. Remaining layout/period/preview choices are explicitly designer proposals, not fresh preference questions or hidden user commitments.
