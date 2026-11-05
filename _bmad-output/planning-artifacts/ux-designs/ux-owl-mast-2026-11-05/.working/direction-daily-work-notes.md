# Daily work — exploratory direction

Status: designer proposal for coached UX discovery; not a final specification. The user delegated visual and color choices on 2026-11-05. All records, counts, ticket names, times, and evidence in the HTML are illustrative. No product integration or action occurs.

## Intent

The first screen answers the stated morning questions in order: what closed, what is blocked, and how far the owned work has progressed. A dedicated input-request panel carries the immediate need for judgment. Native expandable details expose evidence without replacing the current work context. A compact chronological stream supports the user's feed/wall idea while leaving its final form open.

ConvaDesk contributes explicit scope, work-to-evidence drill-down, and separation of tracker completion from acceptance. The inspected Ponytail reference contributes fine panel borders, rounded surfaces, compact type, and selective highlights. The study avoids making token totals, streaks, or people rankings the landing experience.

## Proposed visual decisions

- Use a neutral ink/slate foundation, blue for orientation and selection, and restrained cyan for knowledge-related information. Amber marks an observed need for attention; green marks a known source event, never inferred overall success. Labels and icons carry status independently of color.
- Keep the header compact, project/source identity persistent, and the three summary values modest. Pair progress bars with their numerator, denominator, basis, and observation time.
- Use 12px panel radii, 14px base text, 28px page titles on laptop and 25px on phone, and a system sans family with a system monospace family for IDs and times. These are proposals subject to final spine extraction.
- Layout adapts from two columns to a single reading sequence on phone. The essential order is summary → input request → epic → focused tickets → updates → collection coverage. At tablet width, the request and epic share a row, with full-width work and updates below.
- The HTML inherits the preview host's semantic theme tokens and responds to light/dark host themes. Theme preference/default has not been selected. It contains no literal color palette so that host rendering stays compatible; the exact standalone proposal below is for later DESIGN.md adoption, not applied proof.

## Standalone palette proposal for future DESIGN.md

| Token purpose | Light | Dark |
| --- | --- | --- |
| Canvas | `#F5F7FB` | `#0B1018` |
| Card | `#FFFFFF` | `#121A27` |
| Secondary surface | `#EAF0F8` | `#1B2738` |
| Main text | `#172337` | `#EAF1FA` |
| Secondary text | `#52627A` | `#A5B5CB` |
| Divider | `#D7E0EC` | `#2E3C50` |
| Interactive control outline | `#74849B` | `#73869E` |
| Primary/action | `#2456D6` | `#91B5FF` |
| On primary | `#FFFFFF` | `#0B1730` |
| Information/knowledge | `#086A7B` | `#70D7E7` |
| Attention | `#845900` | `#F0C268` |
| Success | `#176B50` | `#72D6AF` |
| Destructive/error | `#B23549` | `#FF95A5` |

Fine panel dividers need not carry control boundaries. Interactive outlines use their stronger dedicated token. Palette contrast should be measured in the final token combinations before accepting DESIGN.md; no accessibility certification is claimed here.

## Behavioral boundaries demonstrated

- My work / Mohamed changes only the local illustrative dataset; both views remain in Syntelligence.
- Filter chips narrow local updates. Reviews deliberately has no fixtures and demonstrates a meaningful empty state without equating it with complete source coverage.
- Native details elements expose request/checklist/source evidence with keyboard support and visible focus. Reduced-motion preference disables transitions.
- Ticket percentage uses the now-confirmed completed acceptance-criteria/checklist basis; a ticket with no breakdown displays unknown. Epic percentage illustrates 3/5 tracker-closed tickets and explicitly does not imply acceptance. Epic aggregation remains a proposal to settle separately if necessary.
- Input requests are visible, but replies, agent assignment, launch, retry, and other execution controls are absent. The user clarified these occur in existing tools/later scope. No mobile reply journey is promised.
- A knowledge delivery event names its version and project scope; it does not claim usefulness or verified reuse. Notion skill reading is explicitly unverified, separate from observation connection activity.
- Source records are entirely synthetic and permitted within the study. No restricted record previews, hidden-item counts, or source identifiers appear.

## Still open

The full navigation, feed versus wall behavior, notification interruption/payload rules, default theme, and product packaging remain unresolved. The study does not select a UI framework, storage technology, connectors, offline contract, or promotion interface. It does not demonstrate Movesion's independent context; that needs a separate journey/coverage check rather than relabeling Syntelligence records.

Spines, when distilled and finalized, win over this exploratory artifact.

## Later user-directed refinement — identity and contextual usage

The updated study replaces ticket/epic IDs with compact chips whose accessible labels include the source account; visible project/source context remains adjacent or in the scope header. Agent identity uses an illustrative owl alias, colored marker, prototype type glyph, and fixed readable Claude/Codex label. My work uses Tawny/Claude and Snowy/Codex; Mohamed's fixture uses Barn/Claude and Eagle/Codex. These names describe display aliases, not changed provider identities or real configured agents. The name/color editing surface is illustrated in `key-connections.html`.

Tickets and the epic now expose **Usage & cost: Unavailable**. Disclosure explains that no linked usage records exist in these fixtures; observed tokens, API-equivalent estimates, subscription allocation, and actual bills remain separate unavailable measurement classes. Nothing is represented as zero. Shared-run attribution and coverage must be established before aggregation. The full Usage surface is a separate reference; contextual cost does not imply execution or budgeting controls.

Operational copy, identifiers, agent labels, filter/view labels, source context, and evidence text now use at least 14px. Phone content wraps and the scope header can wrap instead of shrinking text. This supersedes the initial study's small labels and increases its readable height. Existing local person switching, event filtering, native disclosure behavior, accepted logo, and host-theme inheritance remain intact.
