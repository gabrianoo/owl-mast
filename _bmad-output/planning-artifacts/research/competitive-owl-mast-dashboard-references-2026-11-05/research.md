---
title: Owl Mast — existing tools and dashboard references
type: competitive
topic: Ponytail, T3 Code, CodeMie, Visdom, PAPI and memory helpers
decision: What to reuse, integrate and differentiate
source: Public documentation, repository code and publisher screenshots
status: complete
preset: standard
validation: normal
claims_verified: 0
claims_unverified: 35
created: 2026-11-05
updated: 2026-11-05
---

# Existing tools change the Owl Mast starting point

## Executive summary

**Recommendation: evaluate integration before building an organization-wide suite.** Use Ponytail and T3 as implementation/interface references, and evaluate CodeMie and Visdom as potentially overlapping platforms, and PAPI as a shared-context/workflow candidate. [20][22] The earlier evidence-and-learning concept is still useful, but its broad combination is not yet a demonstrated market gap.

Ponytail supplies the compact board the user described. T3 documents cross-provider usage and account limits. CodeMie documents shared skills, project knowledge/MCP and scoped analytics. Visdom describes organizational context, dependencies, tracing and ticket-to-code evidence. [1][3][6][7][8][11][12][13]

**Evidence boundary:** current public sources and four static screenshots were inspected; no authenticated product session or integration was tested. T3's interface assessment is documentation-derived. Capability claims have medium confidence and rely on each publisher’s evidence, except reference [13], whose technical details could not be re-accessed during audit and have low confidence. Operational outcomes and cross-product completeness remain independently unverified. Undated documentation cannot establish a release date. Missing evidence is not evidence of a missing feature.

The helper extension favors evaluating OKF for structured knowledge and Operator for documentation workflows. Kody offers portable personal memory and native run history, with a restrictive platform license. These are component candidates, not a tested combined stack. [26][27][28][29][32]

## What changes for Owl Mast

These are proposed product decisions, not user-approved scope:

1. **Keep the experience small before expanding it.** The personal and project overview should feel closer to Ponytail; spending views should follow T3’s distinction between estimated API cost and subscription billing. Organizational views can add scoped knowledge and evidence without making every user navigate the full platform.
2. **Test existing platforms before declaring a gap.** Ask whether CodeMie, Visdom or PAPI can supply the required shared-workspace and evidence capabilities without duplicating the existing tracker. An Owl Mast integration or specialized view may be more justified than a new backend.
3. **Separate four kinds of evidence:** activity (streaks/sessions), consumption (tokens/cost), delivery (accepted/deployed work) and outcome (measured benefit). Every displayed percentage needs a denominator and source.
4. **Investigate narrower differentiation:** easy adoption across existing harnesses; project-safe learning promotion; transparent lineage from accepted outcome back to runs/skills; coverage-aware cross-tool economics. These are hypotheses, not established competitor gaps.
5. **Preserve build-versus-integrate options.** CodeMie/Visdom exports and authorization boundaries are evaluation questions. Source code covered by Ponytail’s and T3’s MIT licenses is a reuse option. UI inspiration does not itself require replacing any execution system.

## 1. Ponytail — compact feedback close to the work

The board source implements project/time filters; session, agent-time, cost and token summaries; project trends; searchable sessions with test-status records; an 84-day activity view; current/longest streaks; and image exports. It renders local CSV-ledger data into a self-contained page. The implementation reports cost estimated from Claude’s API prices rather than actual billed charges. [1]

The inspected screenshot shows a project sidebar, four sparklined KPI cards, a large stacked area chart, then session evidence beside a hexagonal activity heatmap. Its hierarchy is easy to scan: **project → period → summary → trend → session**. The latter judgment is visual analysis, not a usability test. Screenshot values are illustrative, not performance evidence. [2]

**Borrow:** compact personal/project overview, restrained cards, activity history, session evidence one level down. Keep streaks optional and personal; using them to rank organizational contribution is our rejected design proposal, not a limitation claimed by Ponytail.

**Reuse:** the repository carries an MIT license. Covered code is a plausible reuse starting point, with notices retained; review dependencies/assets and current terms before copying a selected component. [4] CSV consumption is an implementation option, not a verified supported organization telemetry API. A stable outbound webhook contract was not established in this pass.

## 2. T3 Code — usage across agents and environments

Usage documentation describes histories from several coding providers, environment filters, cache/model breakdowns, configurable prices and estimated API-equivalent cost. It explicitly distinguishes those estimates from subscription billing. The Limits view presents pooled allowance windows, account details and reset information; duplicate accounts or history locations are handled in documented cases. Totals depend on accessible history. [3]

**Borrow:** separate Cost, Tokens and Limits; preserve project/environment scope during drill-down; show coverage and incomplete scans; expose model/cache detail without overwhelming the overview. This is a docs-derived recommendation, not a visual appraisal of a running T3 instance.

**Reuse/integrate:** the repository carries an MIT license, subject to notice retention and dependency review. [5] Documented webhooks trigger tasks from incoming requests and support templating and delivery controls. That is an inbound automation interface; it does not establish an outbound analytics feed. [18] Verify the reporting/export boundary before making T3 an organization-wide collector.

## 3. CodeMie — substantial shared-workspace overlap

Analytics is documented at personal, managed-project and organization scopes, with spending/token metrics and persistent filters. The analytics page says basic Analytics is available to authenticated users, while the broader Enterprise page groups adoption analytics among enterprise capabilities: exact entitlements need confirmation. [6][9]

Skills support private/project/marketplace visibility and Markdown export. Workflow documentation covers indexed knowledge, MCP tools and propagated correlation/build identifiers. The Enterprise material describes CLI governance, budgets, chargeback and Langfuse tracing. These are documented primitives, not proof of a complete ticket-to-business-outcome graph. [7][8][9]

The inspected analytics screenshot separates global navigation, a time/project/user filter rail, KPI cards, assistant usage and workflow performance tables. It supports a practical pattern: **one persistent scope for multiple analytics sections**. Screenshot tabs need not represent every current feature. [16]

**Borrow:** role-scoped analytics, persistent filters and explicit skill sharing. **Evaluate integrating:** shared skills, knowledge, MCP and trace infrastructure before recreating them. Authorized API access and conversation-history configuration are documented; export coverage and organizational learning semantics still need testing. [19]

**Important fit question:** the Admin FAQ explicitly says indexed shared-project content is accessed through integration credentials without rechecking each viewer's original source permissions; it also describes default chat/profile retention limitations. These need a deployment-specific check for customer/project boundaries. [10] Neither those limitations nor a vendor claim alone settles suitability. Numeric commercial terms were not established; “no per-developer fees” is not a total-cost quote. [9]

## 4. Visdom — close overlap with the combined vision

Context Fabric describes repositories, docs, tickets and internal tools compiled into agent context, supplied through MCP and AGENTS.md, with services/dependency knowledge. AI Tracing describes session/commit/tool evidence, usage and attribution analytics, policies and governance. The researcher’s technical-documentation digest reports self-hosted Kubernetes and a ticket-to-code flow with cost-bearing commit evidence; that page could not be re-accessed by the verifier or lead, so these details remain low-confidence imported evidence. [11][12][13]

**This is the strongest challenge to the earlier broad positioning.** That is an analyst conclusion about documented scope, not an independently verified competitive ranking. We cannot claim Owl Mast uniquely combines knowledge, telemetry and SDLC evidence based on the current scan.

The inspected token-analytics screenshot shows nested analytics navigation, cache summaries, a time series and a repository table. Particularly useful is its visible coverage note: aggregate totals may include proxy traffic while repository/session views reflect hook-tracked sessions. Borrow **summary → repository/session evidence**, plus explicit coverage caveats. [17]

The public commercial description is engagement-based: assessment, pilot, scaling and support, without a fixed price list. This suggests a different adoption path from a tiny self-serve tool, but does not establish relative cost. [14] Public API/export and reuse-license terms remain unresolved; do not classify the platform's source availability solely from the user's “closed” description.

The maturity framework recommends metrics such as cost per iteration/feature and autonomy by task type. Those are measurement recommendations, not proof that every metric ships in the product. [15] Attributing lines of code to AI does not establish that AI caused productivity gains or delivered an economic return on investment.

## 5. PAPI — shared project memory and a managed work cycle

**Addendum, 2026-11-05:** PAPI belongs on the shortlist for the shared-learning and workflow portion of Owl Mast. The public materials describe a hosted MCP service that keeps project plans, decisions, conventions, handoffs and review history across AI clients; the client performs the development work. This is vendor documentation, not a tested integration. [20][21]

Its feature examples show dependency-aware planning, task handoffs with acceptance criteria, build reports recording surprises/dead ends, human review and lessons carried into later cycles. Decision records preserve rationale and supersession, while a roadmap and multiple-project view expose progress. These overlap directly with the earlier learning-to-delivery idea. Structured project history does not establish automatic capture of every chat or an organization-wide executable skill registry. [22]

The official hub screenshot was visually inspected. It prioritizes a human-action queue (Needs you), then project health, roadmap and a board from backlog through release readiness. A left rail exposes Strategy, Decisions, Reviews, Insights and Library. **Borrow the action-first landing page:** show what needs judgment before presenting a large metrics dashboard. Screenshot percentages are examples, not validated performance measurements. [23]

**Critical fit question:** PAPI has its own task board and planning cycles. The user's preference is to keep Jira/GitHub authoritative. Bidirectional tracker sync, external work IDs and conflict resolution were not established in the reviewed material. Verify these before choosing PAPI as infrastructure; otherwise it may introduce a competing work record. [21][22]

Pricing lists Free with three projects/unlimited cycles; Pro adds cross-project lessons and one collaborator, while Team lists roles, shared task pools and API/BI export. Pro's amount is shown at checkout; Team is custom. API/BI entitlement is not an API-schema guarantee. [24]

The dated Trust page says full project exports are available as Markdown/JSON/CSV on every tier; the hosted engine/dashboard are closed source, the guide repository MIT, and a separately described server/install layer Elastic License 2.0. It also states that operator access is possible and no DPA is offered at that page's date. These are vendor statements requiring current confirmation for customer data. Do not infer that the full dashboard is reusable from the guide repository's license. [25]

Two documentation nuances need checking: the homepage's no-server-AI message is qualified by the Trust page's onboarding brief-extraction exception; the hosted-only install guide coexists with a Trust-page description of a self-runnable install layer. The public material may span different product versions. [20][21][25]

**Recommendation:** evaluate PAPI as a planning/context component or integration partner. OpenTelemetry ingestion, comprehensive model-cost accounting and ML budget optimization were not established in this bounded search. This is an evidence boundary, not a claim that the features are absent. The experiment should prove external-tracker synchronization, project isolation, learning retrieval and usable export before adding an Owl Mast economics layer.

## 6. Memory helpers — components to evaluate

This extension examines Kody, OKF Agent Memory and Operator Memory as components or design references. These are documentation/source findings, not tested compatibility or approved architecture. All new source publication dates are unknown; branch references are mutable.

**Kody:** a portable MCP backend with org/team permissions, but its memory tools operate on the signed-in person's personal memory. Task-relevant summaries surface across that person's agents; this does not establish a shared organizational memory corpus. [26][35] Its Activity UI already records native runs, failures, initiators and logs, with approximately 30-day capped retention. External coding-agent OpenTelemetry ingestion and full ticket-to-outcome accounting were not established. [27] The platform uses FSL-1.1-ALv2: internal use is expressly permitted, competing commercial use is restricted, and each version converts to Apache 2.0 after two years. Treat it as a design/integration candidate; do not assume unrestricted code reuse for an overlapping commercial product. [28]

**OKF Agent Memory:** a candidate for a portable knowledge format and retrieval component. Git-backed Markdown, BM25 and stdio MCP support selective retrieval; optional Hub sync and package distribution also exist. Project > vendor > user > system is retrieval precedence, so project concepts can shadow matching system concepts. [29] The convention records provenance, generation/verification, status and freshness, and instructs agents to search before saving. It explicitly distinguishes durable knowledge from conversation transcripts. These are useful primitives, not proof of correct knowledge or guaranteed capture. [30] The repository is MIT licensed. [31] Publisher speed and token-saving claims were not reproduced and are not adopted as expected savings.

**Operator Memory:** a candidate for the developer-facing documentation workflow. It separates private project, shared project and personal cross-project Markdown, loads a compact orientation, and routes agents into deeper documents. Its precedence is Private > User > Shared. Documents acknowledge that agents can forget to update knowledge. [32] Claude/Codex integrations are documented, while more reliable long-conversation updates remain roadmap work. Sharing happens through repository publication; centralized organization access control and automatic capture of every chat were not established. [33] The repository uses BSD 3-Clause. [34]

**Recommendation (analysis):** trial OKF first for structured knowledge and retrieval; evaluate Operator separately for adoption and documentation maintenance. Do not install both as competing authorities over the same records before testing ownership and reconciliation. Kody is an adjacent MCP/runtime reference, with personal-memory scope and licensing requiring explicit fit checks.

**What Owl Mast would still connect:** authorized capture → proposed lesson → validation/promotion → scoped retrieval, with each lesson linked to a work receipt and the runs that produced or reused it. Keep transcripts separately governed. Enforce company delivery policy through trusted server-side checks rather than memory precedence. The existence of these helpers strengthens the case for building the integration and evidence layer rather than a new memory engine.

**Proposed pilot:** a Claude session on Syntelligence records a sourced lesson; another developer's Codex session retrieves it after approved publication. A Movesion session must not receive it without an explicit cross-project grant/promotion. Exercise stale and contradictory lessons, concurrent edits and skipped writes. Compare maintenance effort and retrieval usefulness before choosing a component. No installation was performed.

## A concrete evaluation scenario

Use the same scenario for all platforms, without assuming every one aims to support it: start a Jira/GitHub work item; run an agent with project-scoped context; inspect cost semantics; link the PR and review; publish one validated learning; retrieve it in a second session; then verify a different project's member cannot retrieve restricted material. Finally export the evidence and reproduce the totals.

Record **supported / requires integration / not established** per step, backed by a demo or API response. Do not assign feature scores from marketing. The outcome will determine whether the next brief describes a new product, a plugin, or a thin integration layer.

## Open questions and follow-up

- PAPI tracker synchronization, project-scoped lessons, API/BI schema and current deployment/licensing boundaries: validate before adoption.

- Stable Ponytail/T3 telemetry exports, event schemas and retention: inspect contracts/source and execute a controlled export.
- CodeMie entitlements, source-permission preservation and retention: validate the intended deployment/version.
- Visdom connector depth, public/private APIs, export portability and license/commercial model: request technical documentation or a demo only if the user authorizes outreach.
- Outcome lineage and ML budget recommendations: demonstrate them; public evidence here does not establish causal ROI or budget optimization.
- Browser interaction and usability: static images establish layout only. No clicks, latency, accessibility or real-work usability were tested.

## Source appendix

Confidence is **medium; independently unverified**, except reference [13], which is **low; not re-accessible during audit**. Code and screenshots directly evidence what the files show, not production behavior. Publication dates below are unknown unless explicitly identified as file-change dates.

| Ref | Finding supported | Publisher / source | Publication date | Accessed | Confidence |
| --- | --- | --- | --- | --- | --- |
| [1] | Ponytail board implementation | [DietrichGebert](https://github.com/DietrichGebert/ponytail/blob/main/hooks/band/board.ts) | 2026-10-16 (file change) | 2026-11-05 | Medium; independently unverified |
| [2] | Ponytail visual reference | [DietrichGebert](https://raw.githubusercontent.com/DietrichGebert/ponytail/main/assets/band/board.png) | undated | 2026-11-05 | Medium; independently unverified |
| [3] | T3 usage and cost semantics | [T3 Code](https://github.com/pingdotgg/t3code/blob/main/docs/user/usage.md) | 2026-11-02 (file change) | 2026-11-05 | Medium; independently unverified |
| [4] | Ponytail MIT license | [DietrichGebert](https://github.com/DietrichGebert/ponytail/blob/main/LICENSE) | undated | 2026-11-05 | Medium; independently unverified |
| [5] | T3 MIT license | [T3 Tools](https://github.com/pingdotgg/t3code/blob/main/LICENSE) | undated | 2026-11-05 | Medium; independently unverified |
| [6] | CodeMie role-scoped analytics | [EPAM](https://docs.codemie.ai/user-guide/analytics/) | undated | 2026-11-05 | Medium; independently unverified |
| [7] | CodeMie skill sharing/export | [EPAM](https://docs.codemie.ai/user-guide/skills/manage-skills/) | undated | 2026-11-05 | Medium; independently unverified |
| [8] | CodeMie MCP and correlation | [EPAM](https://docs.codemie.ai/user-guide/workflows/configuration/integration-capabilities/) | undated | 2026-11-05 | Medium; independently unverified |
| [9] | CodeMie enterprise capabilities | [EPAM](https://docs.codemie.ai/user-guide/getting-started/enterprise-features/) | undated | 2026-11-05 | Medium; independently unverified |
| [10] | CodeMie explicit access/retention limits | [EPAM](https://docs.codemie.ai/admin/faq/) | undated | 2026-11-05 | Medium; independently unverified |
| [11] | Visdom tracing and analytics | [VirtusLab](https://visdom.virtuslab.com/platform/ai-tracing) | undated | 2026-11-05 | Medium; independently unverified |
| [12] | Visdom context and dependencies | [VirtusLab](https://visdom.virtuslab.com/platform/context-fabric) | undated | 2026-11-05 | Medium; independently unverified |
| [13] | Visdom deployment and ticket evidence | [VirtusLab](https://docs.visdom.virtuslab.com/) | undated | 2026-11-05 | Low; imported evidence, audit fetch failed |
| [14] | Visdom commercial positioning | [VirtusLab](https://visdom.virtuslab.com/) | undated | 2026-11-05 | Medium; independently unverified |
| [15] | Visdom metrics methodology | [VirtusLab](https://visdom-maturity-matrix.virtuslab.com/matrix/delivery/metrics) | undated | 2026-11-05 | Medium; independently unverified |
| [16] | CodeMie screenshot | [EPAM](https://docs.codemie.ai/assets/images/analytics-dashboard-overview-85b720dc070fcf05955e3ad098ae2264.png) | undated | 2026-11-05 | Medium; independently unverified |
| [17] | Visdom screenshot | [VirtusLab](https://visdom.virtuslab.com/images/visdom/header-page/view-ai-tracing.webp) | undated | 2026-11-05 | Medium; independently unverified |
| [18] | T3 inbound webhook contract | [T3 Code](https://github.com/pingdotgg/t3code/blob/main/docs/user/project-settings.md) | 2026-11-01 (file change) | 2026-11-05 | Medium; independently unverified |
| [19] | CodeMie API and conversation configuration | [EPAM](https://docs.codemie.ai/admin/configuration/codemie/api-configuration/) | undated | 2026-11-05 | Medium; independently unverified |

| [20] | PAPI product/workflow | [PAPI](https://getpapi.ai/) | undated | 2026-11-05 | Medium; independently unverified |
| [21] | PAPI hosted connection/context | [PAPI](https://getpapi.ai/llms.txt) | undated | 2026-11-05 | Medium; independently unverified |
| [22] | PAPI planning and learning features | [PAPI](https://getpapi.ai/features) | undated | 2026-11-05 | Medium; independently unverified |
| [23] | PAPI hub screenshot | [PAPI](https://getpapi.ai/landing/hub-desktop-light.webp) | undated | 2026-11-05 | Medium; independently unverified |
| [24] | PAPI plan entitlements | [PAPI](https://getpapi.ai/pricing) | undated | 2026-11-05 | Medium; independently unverified |
| [25] | PAPI exports and platform boundaries | [PAPI](https://getpapi.ai/trust) | 2026-09-18 | 2026-11-05 | Medium; independently unverified |

| [26] | Kody personal memory | [kody-hq](https://github.com/kody-hq/kody/blob/main/docs/use/memory.md) | undated | 2026-11-05 | Medium; independently unverified |
| [27] | Kody native Activity | [kody-hq](https://github.com/kody-hq/kody/blob/main/docs/use/activity.md) | undated | 2026-11-05 | Medium; independently unverified |
| [28] | Kody platform license | [kody-hq](https://github.com/kody-hq/kody/blob/main/LICENSE) | undated | 2026-11-05 | Medium; independently unverified |
| [29] | OKF retrieval, scopes and optional Hub | [okf-memory](https://github.com/okf-memory/okf-agent-memory/blob/develop/README.md) | undated | 2026-11-05 | Medium; independently unverified |
| [30] | OKF provenance and lifecycle | [okf-memory](https://github.com/okf-memory/okf-agent-memory/blob/develop/docs/spec/CONVENTION.md) | undated | 2026-11-05 | Medium; independently unverified |
| [31] | OKF license | [okf-memory](https://github.com/okf-memory/okf-agent-memory/blob/develop/LICENSE) | undated | 2026-11-05 | Medium; independently unverified |
| [32] | Operator partitions and persistence limits | [aerovato](https://github.com/aerovato/operator-memory/blob/main/docs/architecture.md) | undated | 2026-11-05 | Medium; independently unverified |
| [33] | Operator integration and roadmap | [aerovato](https://github.com/aerovato/operator-memory/blob/main/README.md) | undated | 2026-11-05 | Medium; independently unverified |
| [34] | Operator license | [aerovato](https://github.com/aerovato/operator-memory/blob/main/LICENSE) | undated | 2026-11-05 | Medium; independently unverified |
| [35] | Kody organization permissions | [kody-hq](https://github.com/kody-hq/kody/blob/main/docs/guides/organizations.md) | undated | 2026-11-05 | Medium; independently unverified |

## Staleness map

The tool computed re-check dates only for the three sources with known file-change dates and the dated PAPI Trust page; repository dates indicate file freshness, not initial feature publication. All other source dates are unknown and must be rechecked before a build, purchase or integration decision. Unknown dates were excluded from date arithmetic, not treated as recent.

```json
{
  "today": "2026-11-05",
  "claims": [
    {
      "claim": "Ponytail board implementation",
      "class": "features",
      "pub_date": "2026-10-16",
      "recheck": "2027-01-16",
      "stale": false
    },
    {
      "claim": "T3 usage and cost semantics",
      "class": "features",
      "pub_date": "2026-11-02",
      "recheck": "2027-02-02",
      "stale": false
    },
    {
      "claim": "T3 inbound webhook contract",
      "class": "features",
      "pub_date": "2026-11-01",
      "recheck": "2027-02-01",
      "stale": false
    },
    {
      "claim": "PAPI exports and platform boundaries",
      "class": "features",
      "pub_date": "2026-09-18",
      "recheck": "2026-12-18",
      "stale": false
    }
  ],
  "stale_count": 0,
  "earliest_recheck": "2026-12-18",
  "no_window_classes": []
}
```

Earliest computed re-check: **2026-12-18**. Undated sources require confirmation before a commitment; moving repository branches should be pinned during adapter evaluation.
