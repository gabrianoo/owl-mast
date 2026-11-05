# Bounded corrections — Daily Work and Focus

Edited only `mockups/daily-work.html` and `mockups/focus.html`, plus this requested report. The spines, gallery, other mockups, and earlier `.working` studies were not changed. This is an editing/verification record, not a new independent review.

## Applied findings

| Finding IDs | Applied correction |
| --- | --- |
| Rubric T1; A11Y-05 | Replaced identity chart colors with the dedicated `--identity-iris`, `--identity-mulberry`, `--identity-clay`, and `--identity-slate` variables. Identity markers are diamonds, distinct from round status markers. No literal palette values were added; root owns the shared exact light/dark fallback block. |
| A11Y-06 | Selected person/layout/filter controls retain a 3px primary inset indicator rather than relying on a low-contrast fill alone. The root's exact primary palette supplies its measured contrast. |
| A11Y-07, A11Y-12 | Removed outer/epic clipping; Focus full-width epic disclosure focus uses an inset outline. Daily Work summaries use auto-fit columns with a font-relative minimum, allowing enlarged text to reflow. Long chip text can wrap. |
| A11Y-08, A11Y-15 | Focus evidence links retain their visible shared-run wording in the accessible name and add ticket context. Shared-evidence links have 44px targets. A local evidence jump creates a contextual Back link to its originating ticket; both directions open required ancestor disclosures and restore focus. Repeated work/usage disclosures name their record. |
| A11Y-09, A11Y-20; rubric SH1 | Operational text and source freshness use at least 14px; input/select text uses 16px. Compact layout is below 600px; tablet/wide transitions use 1024px. Together view now has an h2 and a heading for distinct observed runs. Attention-region naming includes its reason. |
| A11Y-01 | Daily Work has a local “New updates · 1” fixture: activation exposes the new row, preserves existing open event evidence, and moves focus to the new heading with one polite announcement. Focus's explicit refresh preserves open disclosures and scroll position. These are local examples, not polling or integration claims. |
| A11Y-13 | Feed rows expose visible text event types as well as decorative icons. |
| A11Y-17 | Dynamic ticket chips rely on their readable text and adjacent source identity rather than `aria-label` on generic spans; Daily Work's summary group has an appropriate group role. |
| Rubric F1; PK-17 | Focus explicitly labels **All authorized projects** as its initial aggregate, with an external study note identifying that default as a designer proposal. |
| Rubric F4 | Daily Work includes a user-selected authorized-company branch with constant scope labeling, separate Syntelligence and stale Movesion summaries, and retained project detail. Company context does not become the default. |
| PK-1; rubric V4 | Constant **Counted from records you can access** basis labels accompany the summary and each epic rollup. Epic fractions use “3 of 5 child tickets closed” as the dominant value; ticket percentages continue to mean completed criteria. Whole accessible epic scope remains distinct from the assigned-ticket subset. |
| PK-4 | The delivered-knowledge fixture demonstrates a neutral **since withdrawn** state: no original title/body, no healthy-looking delivery claim, and a clear distinction between stopped Owl Mast delivery and separately governed direct source/client access. |
| Rubric C1; PK-7 | Aliases are looked up from this viewer's preference map: Tawny → CL-17, Snowy → CX-16, Barn → CL-8, Eagle → CX-4. Unknown clients fall back to fixed type plus stable ID. Mohamed's clients are unaliased CL-21 and CX-27; no other person's owl alias is copied. |
| PK-8 | SYN-42 and SYN-67 link to shared run **R-17**, belonging to client **CL-17**. Its usage is linked but unallocated, not absent and not zero. Ticket/epic cost remains unavailable until supported attribution exists. Epic scope names all accessible child tickets; contextual classes require separate Usage authority and do not expose hidden allocation bases. CX-16/R-16 usage is also unassigned to the displayed ticket. |
| PK-9 | Focus derives shared labels, link text, and reference lists from readable records in the selected project scope. With only one readable link, the run is ordinary and no second record/epic is named. Counts deduplicate permitted run records. Assigned-record permission changes also adjust the accessible fixture denominator rather than retaining a hidden open ticket. |
| PK-13 | Attention content shows a permitted metadata-only case and explicitly says request text is not collected under the example project's policy. This does not confirm A-3's default. |
| PK-15 | Both screens include a neutral source-identity-unconfirmed state: assigned work may be missing; matching a display name is insufficient. Focus's normal state says the assignment mapping is confirmed. |
| PK-19 | Both Movesion clients depend on expired Jira authorization. Work, criteria, assignment, and agent associations are labeled as stale **07:55** snapshots; current work observation and dependent knowledge readiness are unavailable. No current-active claim is made for them. |
| Rubric V5 | Daily Work's embedded work section is **Active work**, preserving Focus as a separate destination. |

## Fixture alignment

- Ahmed's SYN-42: 2/4 criteria; client CL-17 / run R-17. SYN-67 in Focus: 3/4 criteria, same run R-17. Usage stays unassigned across those permitted links.
- Mohamed's first Daily Work record: **SYN-72 — Verify account rollout rules**, 3/4 criteria (75%), under SYN-10, unaliased client CL-21 / run R-21. It does not take ownership of Ahmed's SYN-67.
- Syntelligence Codex: client CX-16 / run R-16; Movesion Claude: CL-8 / R-8; Movesion Codex: CX-4 / R-4. The unmatched CX-12/R-12 uses its fixed-type fallback.
- No numeric shared usage or cost was copied into a ticket allocation. The separate Usage reference owns the measured shared-session figures.

## Verification and remaining integration work

JavaScript syntax and static IDs/label references pass. A local DOM stub exercised both Daily Work people and all five filters, the 50%/75% criteria switch, neutral withdrawal, refresh, and company branch. Focus's six layout/project combinations preserve unique targets, deduplicated counts, and stale Movesion labels. Removing SYN-67 from the readable fixture removes its ID and shared-run wording from rendered output; removing CL-17's personal alias renders the stable-ID fallback.

Root still needs to inject the shared exact-palette fallbacks, normalize the final type glyph treatment, and render the edited versions. These checks do not prove browser focus rendering, actual identity mapping, source authorization, refresh transport, or revocation propagation. No new independent review or delegation was started.
