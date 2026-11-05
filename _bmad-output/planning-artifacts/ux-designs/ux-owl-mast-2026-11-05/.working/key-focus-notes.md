# Focus — assigned work across epics

Exploratory key-screen study, 2026-11-05. Based on confirmed UX-11–13 and the existing DESIGN.md/EXPERIENCE.md draft. The accepted logo paths and host-token visual language carry forward. The HTML contains only illustrative fixtures and local interactions; it does not change real work.

## Distinct purpose and proposed presentation

Focus is a separate surface for Ahmed's assigned tickets; Daily Work remains a separate navigation label and landing surface. This screen has no overview feed, agent dispatch, input submission, dragging, reassignment, or source mutations.

The local **By epic / Together** toggle demonstrates grouped epic sections and one combined list over identical records. Both are designer proposals for the newly confirmed need; the initial grouped view is not claimed as a user-selected default. A project filter narrows the same permitted scope without changing assignment. In Together, explicit input requests precede other work; this ordering is a proposal.

In the initial grouped study, the first epic's work is expanded and the remaining epic sections can be expanded independently. Every epic title, project, assigned-ticket count, tracker-closure fraction, agent types, and linked-run count stays visible. This demonstrates stacked concurrent context without an excessively long initial screen; expansion/default persistence remains an implementation-level proposal.

Shared components: `scope-bar`, `surface-navigation`, `work-record`, `progress-evidence`, `evidence-detail`, `state-message`, and `external-link` visual affordances. Run links in this study navigate to local observed evidence; production source-link behavior remains in the spines. Key identity, measurement basis, source state, and action labels use at least 14px; supplementary times/run identifiers may use 12px. Interactive targets are at least 44px high. The study includes keyboard focus, native details, and a polite state announcement when the view/filter changes.

## Fixture integrity

- Five assigned tickets span three epics: Syntelligence/SYN-10 and SYN-20 use the distinct Syntelligence Jira site + GitHub; Movesion/MOV-30 uses its separate Jira site + Bitbucket. Project, account, and epic identity remain on every work card, including the combined list.
- Both Claude and Codex are represented in both projects. Each source reports its linked run active at the illustrative 08:42 observation time. This is observed state, not a guarantee of current activity or an execution control.
- Syntelligence Claude CL-17 contributes to two epics. It appears under both, with a single evidence target and an explicit shared marker. Four distinct linked runs are counted across the board, not five epic appearances.
- Codex CX-12 remains outside epic totals with unknown linkage. It belongs to Ahmed's context because the source explicitly confirms him as initiating person, not because he owns a connection or commit. Its state is not inferred as active. The record remains visible separately rather than assigned to a guessed epic.
- Card percentages use completed acceptance criteria: 2/4, unknown, 3/4, 1/4, and 2/5. Unknown has no progress bar. Evidence states that marked criteria do not establish the ticket's overall acceptance decision.
- Epic bars show explicit tracker-closure fractions over all permitted epic tickets. Expanded Whole-epic context distinguishes that denominator from Ahmed's displayed assigned-ticket subset. No summed or weighted cross-epic completion metric is shown.

## Boundaries

This is not proof of account integrations, source permissions, concurrent-session collection, or final responsive accessibility. The host supplies its light/dark theme tokens; the HTML does not hardcode or prove the standalone palette. It does not reveal hidden counts or imply the existence of unauthorized projects. All source identities, names, times, and data are illustrative, as marked outside the app shell.

No files were moved, no spines or memlog changed, and no production/source action was invoked.

## Later user-directed refinement — identity and contextual usage

Ticket and epic IDs are now source-qualified chips, retaining the project/account context on each work card. Agent chips use the same treatment as Connections: owl display alias, colored marker, prototype type glyph, and fixed readable provider label. Tawny/Claude and Snowy/Codex belong to the illustrative Syntelligence context; Barn/Claude and Eagle/Codex to Movesion. Underlying run IDs are in evidence details. Shared appearances of Tawny's CL-17 still reference the same evidence and count only once; the unmatched CX-12 remains separate with its confirmed initiating person.

Every ticket and grouped epic exposes **Usage & cost: Unavailable**. Its disclosure states that the fixture contains no linked usage records and keeps observed tokens, API-equivalent estimates, subscription allocation, and actual bills separate. No monetary value, guessed allocation, or aggregate effort is fabricated. Any future aggregate must deduplicate shared runs and retain attribution/coverage gaps; the dedicated Usage screen remains the fuller measurement surface.

The existing project filter, By epic/Together toggle, safe evidence navigation, native disclosures, accepted logo, source identities, and progress semantics remain intact. Colors and aliases are adjustable presentation, not permission or provider changes; editing is illustrated in Connections rather than adding mutation controls to Focus.
