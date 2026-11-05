# Brief and reference extraction for UX discovery

Date: 2026-11-05. Purpose: evidence for coached UX discovery, not an approved design. The finalized PRD and the user's current instructions govern any older brief/research wording. No architecture or UI system is selected here. No new public research, product session, integration test or publication of screenshots was performed.

## Source register

- **B:** [Product brief](../../../briefs/brief-owl-mast-2026-11-05/brief.md), especially “The problem,” “Proposed product experience,” “First-version boundary,” and “Pilot evidence and success.” Brief status is draft.
- **BA:** [Brief addendum](../../../briefs/brief-owl-mast-2026-11-05/addendum.md), especially “Confirmed sharing policy and concrete pain,” “Colleague's ConvaDesk UI references,” and “Proposed acceptance story.”
- **BM:** [Brief decision log](../../../briefs/brief-owl-mast-2026-11-05/.memlog.md). Distinguishes user-confirmed decisions from interface/metrics proposals.
- **RB:** [Research brief](../../../research/competitive-owl-mast-dashboard-references-2026-11-05/brief.md). Research authorization does not approve architecture or interface decisions.
- **R:** [Research report](../../../research/competitive-owl-mast-dashboard-references-2026-11-05/research.md). Public documentation/source and static-screen evidence; 35 independently unverified claims.
- **RM:** [Research decision/evidence log](../../../research/competitive-owl-mast-dashboard-references-2026-11-05/.memlog.md).
- **V:** [Lead visual observations](../../../research/competitive-owl-mast-dashboard-references-2026-11-05/digests/visual-observations.md). CodeMie/Visdom static screenshots only; no observed interaction behavior.
- **T:** [Ponytail and T3 digest](../../../research/competitive-owl-mast-dashboard-references-2026-11-05/digests/ponytail-t3.md). Ponytail screenshot inspected; T3 interpretation derives from docs/source.
- **O:** [Operator Memory digest](../../../research/competitive-owl-mast-dashboard-references-2026-11-05/digests/operator-memory.md). Source/documentation evidence, not runtime validation.
- **U:** Current UX request, including six attached ConvaDesk screenshots. The user explicitly confirms scope and requests coaching through unresolved choices.

## Actual needs and evidence status

| Need/context | Status and source | Implication for discovery |
|---|---|---|
| Understand Mohamed's and his agents' contributions without a manual recap; equip the user's agents with their learning | User-reported pain: B “The problem”; BA “Confirmed sharing policy and concrete pain” | Begin with a real work item and the evidence a colleague needs to understand it, rather than assuming dashboard content. |
| Recurring contributor/agent onboarding must require minimal effort | Confirmed: B/BA; sharpened by U | Distinguish first administrator setup from repeated contributor/client enrollment. Complex initial administrator setup is acceptable under U. |
| Both Syntelligence and Movesion are required pilot environments | Confirmed: B/BA/U | Preserve each project's identity and Jira account; GitHub belongs to the former, Bitbucket to the latter. Do not make a global issue key appear unique without its source context. |
| Claude and Codex in both projects | Confirmed by U | Both need understandable connection/health and knowledge-delivery journeys. Older brief wording about instrumentation order must not reopen provider coverage. |
| Observe work and deliver knowledge; existing tools keep execution controls | Confirmed: B/BA/BM/U | Connection health and evidence inspection are legitimate UX; launch/pause/cancel/retry agents are outside v1. Knowledge publication can write under policy. |
| Keep existing Notion workflows and Hermes-to-Notion learning | Confirmed: B/BA/U | Surface knowledge lineage and coexistence. Current Notion skill reading is unverified under U; do not imply automatic successful reading. |
| Knowledge defaults to project scope; support automatic company-safe promotion plus manual and disabled modes | Project scope confirmed by B/BM; automatic preference and modes confirmed by U | Older “explicit promotion” language does not establish mandatory human approval for every promotion. No approver, review layout or permission model is selected by this extraction. |
| Company asset ownership does not give everyone source access | B “Purpose and first customer”; BA “Architecture implications”; permission preservation reaffirmed by U | People/agent continuity across projects must not imply knowledge follows them into every project. |
| A shared web interface and harness integrations | Explicit **[ASSUMPTION]** in B “Proposed product experience” | Operating surface remains a discovery choice unless finalized PRD/current Notion decisions establish otherwise. |
| Administrative connection once, contributor enrolls existing clients and chooses project | Explicit **[PROPOSAL]** in B “First-version boundary” | A candidate journey to discuss, not approved enrollment mechanics. |
| Time-to-understand, time/steps-to-first-useful-action, learning reuse and attribution coverage | Proposed evaluation measures in B “Pilot evidence and success” | Do not invent targets or treat token totals as proof of usefulness. |

## Real journey material available

Only Mohamed is a named human protagonist in these supplied brief sources. “The user,” “another AISQUAD contributor,” and “administrator” are roles; do not invent personal names or biography. The descriptions below preserve source outcomes but leave interaction choices open.

1. **Connecting an existing agent.** A contributor wants an existing Claude or Codex setup to become useful in an authorized project with minimal repeated setup. The source proposal is administrator connection followed by enrollment; the user has not yet described the actual commands/screens they want. Discovery needs the current starting point, the minimum acceptable action, and what visible proof says “connected and receiving the right context.” B “First-version boundary”; BA “Proposed acceptance story”; U.
2. **Understanding Mohamed's work.** Mohamed starts multiple agents on a real feature. Another contributor needs to establish who initiated it, which agents worked, what changed, available review/acceptance evidence, and what is blocked. **Source-backed success beat:** that contributor can understand the state without asking Mohamed for a recap. The starting surface, ordering of evidence, and default level of detail remain undecided. B “The problem”; BA “Proposed acceptance story.”
3. **Receiving useful knowledge.** A newly enrolled agent obtains a relevant, sourced lesson from other contributors' sessions without repeating discovery. **Source-backed success beat:** the user's next session can use that lesson in the current project. Delivery location, degree of interruption, whether a human sees a receipt, and treatment of stale/conflicting context need coaching. B “Proposed product experience”; BA “Proposed acceptance story”; R “Memory helpers.”
4. **Managing promotion.** A reusable lesson starts project-scoped and may become suitable for AISQUAD-wide reuse. **Source-backed success beat:** another authorized context can use a company-safe lesson while restricted project evidence remains protected. Automatic identification/promotion, manual approval and disabled modes are current confirmed direction; who manages exceptions, the explanation of a candidate, and rollback/revocation interaction still need resolution against the PRD. BA “Confirmed sharing policy”; U.

Research offers a proposed scenario—Claude creates a sourced Syntelligence lesson, another developer's Codex session retrieves it, and Movesion does not receive restricted content without permitted promotion—but this is an analyst-proposed test, not a reported real completed session. R “Memory helpers,” lines 110–112.

## ConvaDesk: documented visual evidence and patterns to discuss

BA “Colleague's ConvaDesk UI references,” lines 25–35, is the durable source for all six screenshots. The current attachments corroborate those observations. Their numbers are examples, not verified metrics; the screenshots prove neither integration behavior nor accessibility. No Owl Mast visual preference is inferred from supplying them.

| Attachment | Visible observation | Discussion candidate, not approved Owl Mast choice |
|---|---|---|
| `IMG_AB4D1C8F3C45-1.jpeg` | Large ticket-detail overlay; metadata/prerequisites/source links in a left column; readable Markdown and CI/review tabs on the right. A “Completed” badge coexists with body text saying planned and no current PR signal. | Preserve context while inspecting evidence; ask which details should stay visible. Present conflicting evidence with its source/freshness, rather than silently resolving it into one completion label. |
| `IMG_A9CC932E588C-1.jpeg` | Persistent project sidebar; dependency explorer with filters, ticket focus, prerequisite context, graph/list choice and dense node edges. Caption separates issue status from merge/acceptance evidence. | Discuss whether dependencies deserve a surface and when a graph helps. Focused neighborhoods are an existing analyst inference, not a tested or approved default. |
| `IMG_EF516651E585-1.jpeg` | Release/goal overview, large progress summary, separate attention panel, goal cards; ticket completion distinguished from release qualification. | Discuss whether the landing moment is situational awareness, actions needing judgment, or a selected project. No approval yet for progress-first landing. |
| `IMG_BC54BCBE01C2-1.jpeg` | Machine/agent/model/ticket/date filters; total tokens with cache/input/output breakdown; “token volume, not a bill”; daily and agent/machine breakdowns. | Explicit scope and measurement semantics; discuss how much usage belongs in the principal journey versus a deeper view. |
| `IMG_3626EBD8C28F-1.jpeg` and `IMG_DE187537BF11-1.jpeg` | Long ticket/work usage table; unassigned work is retained visibly; numerical columns permit detailed inspection. | Keep attribution gaps discoverable. Decide whether and how contributors resolve an unmapped item without claiming every token can be assigned to a ticket. |

Additional direct observation from U's attached images, separate from the older written addendum: the reference uses a warm light background, white surfaces, dark green emphasis, muted green selected items, restrained borders, rounded cards and generous whitespace above denser tables. These are descriptors of the reference, **not chosen tokens, approved colors or a direction for Owl Mast**. Discuss which elements the user values and which they want changed before extracting a palette/type scale.

Visual pitfalls to carry into discovery:

- A prominent completion number can imply accepted delivery even when it counts tracker status only. The modal's conflicting labels illustrate why provenance matters; their cause is unknown.
- Dense graph edges and extremely small screenshot labels may impede comprehension. This is a visual concern, not a measured usability/accessibility finding.
- Repeated long tables can obscure the user's immediate question. Density and drill-down remain user choices; no replacement layout is selected.
- Green dominates the reference; color alone must not be presumed sufficient to convey status. No contrast values have been measured from these images.
- The references do not demonstrate cross-person learning delivery, scoped promotion, onboarding effort or human-to-agent delegation. That absence of screenshot evidence does not prove the product lacks these capabilities. BA line 35.

## Other reference patterns: research proposals and evidence limits

| Reference | Research-supported observation | Candidate for discussion | Boundary |
|---|---|---|---|
| Ponytail | Project → period → summary → trend → session hierarchy; missing test records represented explicitly; usage cost uses API estimates | Small overview with deeper session evidence | Static image/source evidence, not user preference or usability validation. Streaks/tokens are not productivity. R lines 38–46; T lines 20–25. |
| T3 Code | Multi-provider/environment history; Cost/Tokens/Limits semantics; partial scans and deduplication are documented | Preserve environment scope and distinguish usage, estimates, subscription limits and collection gaps | No T3 screenshot or actual two-agent setup journey was inspected. R lines 48–54; T lines 27–37. |
| CodeMie | Persistent scope/filter rail with summaries and detail tables; sharing scopes documented | One visible scope across related views; intelligible knowledge visibility | Vendor documentation/screenshot evidence. Source-permission behavior requires scrutiny; it cannot override Owl Mast's permission-preservation requirement. R lines 56–66; V. |
| Visdom | Token summaries, trends and repository detail with explicit difference between proxy totals and hook-tracked sessions | Coverage explanations beside totals and drill-downs | Static screenshot; technical integration evidence partly low confidence. No tested implementation. R lines 68–78; V. |
| PAPI | Static hub prioritizes “Needs you,” then project health/roadmap/work board | Surface decisions requiring human judgment where appropriate | Research recommendation only. Own-board interaction must not quietly replace authoritative Jira/GitHub/Bitbucket work records. R lines 80–96. |
| OKF / Operator | Provenance/freshness, distinction between durable lessons and transcripts; small context catalogs; documented missed-update risk | Understandable lesson source, age, applicability and incomplete capture | Components under evaluation, not selected architecture. Documentation does not prove reliable capture or preserved source permissions. R lines 98–112; O. |

### T3 two-agent reference specifically

The user has now confirmed T3's two-agent setup as an experience reference. That gives permission to use their described experience, but the existing research establishes neither its exact setup steps nor which parts the user values. It does not support claims of one-click enrollment, zero setup, identical Claude/Codex behavior, automatic source-permission inheritance, or successful knowledge sharing.

The useful follow-up is to have the user describe the part of connecting/working with two agents that should carry into Owl Mast: what they do, what the app handles, and when they know it worked. Keep launch/delegation controls out of Owl Mast's v1 even if present in T3. T3's inbound task webhooks are execution triggers; they are not evidence of an outbound observer feed or a reason to add execution authority. T lines 29–37.

## Outstanding UX choices to guide, not decide

Resolve the operating surface first: where the human opens Owl Mast, where an agent receives knowledge, and whether a separate web workspace is actually wanted. Then discuss the user's reaction to the ConvaDesk references rather than proposing a color/style they did not request.

Use the four real journeys to reveal first screen, primary question, evidence ordering, interruption level and success confirmation. Remaining concerns include project switching, permission-denied/partial-data states, stale/conflicting lessons, automatic-promotion exceptions, correction/revocation feedback, contribution versus usage presentation, responsive needs, density, accessibility, motion and notification channels. These are discovery topics, not mandatory new surfaces or approved scope.

Do not reopen confirmed scope choices. Do not treat older source recommendations, undocumented vendor capability, screenshot metrics or an untested implementation assumption as user decisions. PRD tagged assumptions retain their original status until the user resolves them.
