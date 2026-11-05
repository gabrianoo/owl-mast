# Knowledge and promotion visual references

2026-11-05. Three additional surfaces requested by the user. Their request for all remaining surfaces supersedes the renderer's usual 2–4-screen cap. These are layout proposals under the existing delegated visual direction, not newly inferred preferences or integration evidence.

| File / surface | Canonical state | Compact alternate | Spine mapping |
| --- | --- | --- | --- |
| [key-knowledge.html](key-knowledge.html) / **S3** | Scoped catalog/search with approved and candidate examples, provenance, and visible project-lesson submission fields. | An authorized search succeeds but finds no relevant result; no other project's content is substituted. | DESIGN: `scope-bar`, `knowledge-record`, `settings-field`, `state-message`. EXPERIENCE: S3, SC-2 steps 1–3, S3 states, Knowledge semantics. |
| [key-knowledge-detail.html](key-knowledge-detail.html) / **S4** | Exact knowledge version, human evaluation with basis/time, a distinct earlier automated evaluation, controlled origin, and illustrative recipient receipt with reuse still unverified. | Current access cannot be confirmed: neutral unavailable message without title, excerpt, recipients, or hidden-source detail. | DESIGN: `knowledge-record`, `delivery-receipt`, `evidence-detail`, `state-message`. EXPERIENCE: S4, SC-2 steps 2–6, S4 states, FR-9/11/17/21. |
| [key-promotion.html](key-promotion.html) / **S6** | Automatic mode is current/preferred; a specific version stays project-scoped because permitted company use is unresolved. Exact publication text, intended audience, policy, checks, and decision record are visible. | Manual-approval snapshot with required checks confirmed, the exact same version/content available for inspection, and disabled decision controls. | DESIGN: `promotion-review`, `settings-field`, `knowledge-record`, `state-message`. EXPERIENCE: S6, SC-3, S6 states, Promotion semantics. |

## Layout and rendering contract

- Transparent outer page; bounded internal theme-token shell, inline CSS, system fonts, no viewport-height sizing. The accepted owl geometry/strokes are copied from the existing Focus study without alteration.
- Header → labeled workspace context → project scope → primary record/task → supporting provenance → compact alternate state. This follows the existing panels, full-width compact detail, and disclosure patterns; no new modal, control system, or navigation architecture is introduced.
- Primary target width is 728px, with one-column reflow below 600px for the requested 390px phone reference. All essential copy is at least 14px; controls and disclosure targets are at least 44px. Reading content/input text is 16px. No fixed-height clipped cards or horizontal-only tables.
- Host theme tokens drive the visible shell; DESIGN.md values provide standalone fallbacks. Native disclosure controls reveal supporting evidence. This is not proof of every standalone color pairing, measured height, or accessibility conformance; the root facilitator handles actual preview/render checks.
- Each file is static, offline HTML: no JavaScript, event handlers, remote assets, network calls, or live source URLs. All search, submission, policy, publication, return, and source-navigation buttons are disabled and give a nearby reason. Native `details` remains interactive locally.

## Latest ticket and agent styling instruction

- S4 shows the source-qualified example ticket **SYN-42** as a compact ticket chip and the recipient **Snowy · Codex** as an agent chip. Source provenance also includes **Tawny · Claude**. Both owl aliases and their identity colors are explicitly illustrative fixtures, not configured real agents.
- Each agent chip includes a fixed small provider/type glyph **and visible type text**, with the customizable owl alias alongside it. These are prototype glyphs, not official provider logos. Identity color is a narrow marker on a neutral chip, not a knowledge approval/delivery/status color.
- Receipt attribution remains tied to the stable example client/run identity, available in a disclosure. Renaming or recoloring does not change authorization, provider identity, or the recorded recipient. Customization controls belong to the separate S5 study.
- Knowledge-version IDs remain knowledge identifiers; they are not relabeled as tickets or agent identities. Human reviewers/contributors remain distinct from agents.

## Source and policy boundaries

- Fixture lessons, dates, reviews, permissions, and receipts are labeled illustrative outside every app frame. They are not actual Syntelligence facts or proof that any client read a Notion skill.
- Agents search when they need knowledge. Catalog browsing does not inject, send, or execute anything. Existing Hermes → Notion capture remains the source flow; the proposed submission surface does not require a second save or replacement store.
- Candidate, approved, human-reviewed, automatically evaluated, retrieved, delivered, and verified reuse remain distinct. S4 explicitly labels current Notion skill reading as unverified despite demonstrating a hypothetical receipt.
- Source/project permission governs record visibility, evidence, recipient history, and publication. The wider publication preview excludes restricted source references. A maintainer designation, automatic mode, or a human click cannot bypass required company-use checks.
- **A-1 remains provisional:** the catalog intentionally shows multiple visible lifecycle states; no default agent-delivery eligibility is selected by the example.
- **A-2 remains provisional:** the alternate S4 state illustrates an access check failure, not a newly selected withdrawal/quarantine policy or recall of previous copies.
- **A-4 remains provisional:** the disabled-mode description promises only no new company publication; it does not settle what happens to existing publications.
- The manual-review alternate is a separate snapshot after checks are confirmed. It is not an override of the unresolved company-use check in the canonical automatic-exception snapshot. No publication occurs in either.

No spines, memlog, upstream requirements, Notion content, or real permissions were changed by producing these references.
