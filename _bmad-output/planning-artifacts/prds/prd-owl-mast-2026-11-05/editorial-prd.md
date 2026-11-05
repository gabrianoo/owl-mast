# Owl Mast PRD — final editorial proposals

This document exists to help AISQUAD's product, UX, architecture and engineering readers understand the v1 boundaries and turn the confirmed direction into an observable pilot.

Reviewed `prd.md` only, using the **Strategic/Context (Pyramid)** structure model for human readers. Structure was assessed first; prose suggestions below respect its proposed moves. This is an editorial pass only: product decisions, requirements, assumptions, IDs and acceptance rules remain unchanged. No PRD edits were applied.

The capability-led voice, concrete Mohamed/Ahmed examples, distinction between facts and uncertainty, and explicit authorization language are intentional and should be preserved. The document already separates behavior from implementation options and gives reviewers useful signposts. No forced shortening is warranted.

## Word metrics

Exact metrics from `uv run .agents/skills/bmad-review/scripts/word_metrics.py _bmad-output/planning-artifacts/prds/prd-owl-mast-2026-11-05/prd.md`: **4,895 words**. The script counts whitespace-separated tokens, including Markdown markers and frontmatter. Major-section figures below aggregate body words across each section's child headings; heading text is not included in those section figures.

| Section | Body words including child sections |
| --- | ---: |
| §0 Purpose and decision status | 152 |
| §1 Product vision and users | 428 |
| §2 Shared vocabulary | 312 |
| §3 Functional requirements | 2,323 |
| §4 Cross-cutting quality requirements | 222 |
| §5 MVP boundary and integrations | 214 |
| §6 Success and pilot acceptance | 409 |
| §7 Risks and operating constraints | 83 |
| §8 Assumptions index | 198 |
| §9 Unresolved requirements and downstream handoff | 288 |
| Section body subtotal | 4,629 |
| Frontmatter/preamble | 14 |
| Heading text | 252 |
| **Document total** | **4,895** |

## Structure, then prose

| Pass | Original Text | Revised Text | Changes |
| --- | --- | --- | --- |
| structure | §0, opening paragraph beginning “This PRD defines Owl Mast v1 for AISQUAD” and ending with the Notion concept-record link — 36 words. | **MOVE** this complete paragraph below §0's two decision paragraphs, immediately before §1. Preserve its text and links verbatim. | Put the confirmed direction first and its supporting-source inventory afterward. This follows the pyramid model without deleting orientation or citations. **0 words changed.** |
| structure | §6, the 60-word paragraph beginning “Counter-metrics prevent misleading success:” and containing all four SM-C definitions. | **MOVE** the four definitions into separate bullets within the same passage:<br><br>Counter-metrics prevent misleading success:<br><br>- **SM-C1:** Stale/conflicting guidance and repeated work counterbalance reuse counts.<br>- **SM-C2:** Wrong or overconfident work explanations and review delays counterbalance faster understanding.<br>- **SM-C3:** Connection maintenance, human cleanup, and setup assistance counterbalance enrollment speed.<br>- **SM-C4:** Unassigned/unpriced activity and collection gaps counterbalance attractive cost totals.<br><br>More captured text, more agent runs, and more retrieved items are not success targets. | Make four parallel safeguards independently scannable. Preserve every metric, pairing and the closing warning about activity counts. Proposed passage is **64 words, +4**, including list markers under the script's counting rule. |
| structure | FR-12 — Explicit company-wide promotion, 273 body words; the 198-word assumptions index in §8. | **PRESERVE** both. | FR-12's policy modes, checks, version boundaries and mode-change cases are distinct requirements. The assumptions index gives owners and revisit points that inline callouts cannot replace. Apparent repetition supports extraction and review. **0 words changed.** |
| prose | §0: “The confirmed boundaries are open source, AISQUAD as first customer, observation and knowledge delivery, both customer toolchains, project-default knowledge, and minimal recurring onboarding.” | “The confirmed boundaries are open source, AISQUAD as first customer, observation and knowledge delivery for Syntelligence (Jira/GitHub) and Movesion (separate Jira/Bitbucket), project-default knowledge, and minimal recurring onboarding.” | Resolve “both customer toolchains” at first mention, particularly useful after the structural move makes this the opening sentence. Adds no integration commitment. **23 → 27 words, +4.** |
| prose | FR-16: “Estimated cost records their pricing basis and date.” | “Cost estimates record their pricing basis and date.” | Repair the mismatch between singular “cost” and “their,” and make clear that estimates carry the pricing metadata. **8 → 8 words, 0.** |
| prose | FR-10: “No relevant knowledge produces an honest empty result.” | “If no relevant knowledge is found, delivery returns an empty result.” | Express the condition and response directly; remove an awkward construction that makes absent knowledge the actor. **8 → 11 words, +3.** |

## Editorial impact

**Five proposed changes and one explicit preserve recommendation.** If all changes are accepted, the estimated reduction is **−11 words (−0.22%)**: a small increase to **4,906 words**. The paragraph moves preserve all content; the increase comes from clearer first-use context, an explicit condition, and list markers. No length target was supplied, and no engagement, rationale, requirement, source or policy detail is sacrificed for brevity.

No additional prose fixes are needed for comprehension. These recommendations do not reopen the user's automatic/manual/disabled promotion choice, initial Claude/Codex requirement, T3 Code setup reference, or onboarding trade-off.
