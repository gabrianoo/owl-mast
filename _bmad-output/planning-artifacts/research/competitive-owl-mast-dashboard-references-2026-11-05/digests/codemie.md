# CodeMie evidence digest

Accessed: 2026-11-05. Public documentation only; no product login, installation, outreach, or project-context inspection. Eight retained sources below. All are published by EPAM / AI/Run CodeMie. Publication dates are **undated**: crawl timestamps are not publication dates. Capabilities are vendor-documented, not independently tested; confidence is **medium (single vendor)** unless labeled inference. UI assessment is **docs-derived**: the linked dashboard image was fetched but not visually inspected. No numerical ROI claims are accepted.

## Documented capabilities and source records

### C1 — Analytics and personas

- Claim: Analytics reports spending, several token categories, active users, invoked assistants/workflows, and workflow execution/success metrics. Regular users see personal statistics; project admins see managed projects; platform admins and auditors see organization-wide data. Time/user/project filters persist across dashboard sections. The personal budget widget lives under Profile. Tabs include Insights, CLI Insights, AI/Run Adoption, and Leaderboard; engagement rankings are not delivery-outcome measurements.
- URL: https://docs.codemie.ai/user-guide/analytics/
- Publisher: EPAM / AI/Run CodeMie; pub_date: undated; accessed: 2026-11-05; confidence: medium (single vendor); class: documented capability / docs-derived UI.
- Qualification: This page explicitly says basic Analytics is available to every authenticated user and shows an empty state without Elasticsearch. C6 broadly lists adoption analytics as Enterprise; validate exact entitlements for the intended deployment.

### C2 — Shared skills and export

- Claim: Skills have private, project, and marketplace visibility. Project skills can be searched/filtered; cards expose sharing status. Skill details show attached assistants. Editing a skill's required tools changes the tools inherited by its assistants. Markdown export supports storing skills in Git and importing into other projects.
- URL: https://docs.codemie.ai/user-guide/skills/manage-skills/
- Publisher: EPAM / AI/Run CodeMie; pub_date: undated; accessed: 2026-11-05; confidence: medium (single vendor); class: documented capability / docs-derived UI.

### C3 — Knowledge, MCP, and workflow traceability

- Claim: Workflow assistants retrieve indexed Git, Confluence, Jira, Google Docs, uploaded files, and custom API sources. MCP tools can be attached to assistants. Execution APIs can propagate filtered request headers to MCP calls, including tenant, correlation, and build identifiers. A documented example runs integration tests for a PR with correlation/build headers. This is evidence for trace propagation primitives, not proof of an automatic ticket-to-PR-to-business-outcome graph.
- URL: https://docs.codemie.ai/user-guide/workflows/configuration/integration-capabilities/
- Publisher: EPAM / AI/Run CodeMie; pub_date: undated; accessed: 2026-11-05; confidence: medium (single vendor); class: documented capability / example configuration.
- Qualification: Docs warn that propagated user headers require validation at the MCP server; they are not sufficient for critical authorization.

### C4 — API access and conversation memory configuration

- Claim: Authorized external applications can use JWT authentication with resource scopes for assistants, workflows, and conversations. Configuration documents history replay, optional history compaction, storage indexes for complete conversations and metrics, and optional budget enforcement that blocks over-budget requests.
- URL: https://docs.codemie.ai/admin/configuration/codemie/api-configuration/
- Publisher: EPAM / AI/Run CodeMie; pub_date: undated; accessed: 2026-11-05; confidence: medium (single vendor); class: documented configuration/API capability.
- Qualification: Conversation storage and summarization establish history management; they do not establish an organization-wide learned memory system.

### C5 — Governance boundaries

- Claim: External-source access follows the configured integration credential. For indexed shared-project data, the platform does not re-check each viewer's original source permissions at retrieval time. Administrators can restrict MCP to catalog servers or disable it. The FAQ explicitly says chat/profile retention periods and purge schedules are not configurable by default.
- URL: https://docs.codemie.ai/admin/faq/
- Publisher: EPAM / AI/Run CodeMie; pub_date: undated; accessed: 2026-11-05; confidence: medium (single vendor); class: documented capability / explicit limitation.
- Implication: An integration evaluation should verify source authorization preservation and lifecycle controls against actual organizational requirements. This follows an explicit documented limitation, not missing marketing text.

### C6 — Enterprise packaging, telemetry, and commercial statement

- Claim: Enterprise documentation lists a CLI wrapping Claude Code, Gemini, OpenCode, and LangGraph; SSO, analytics, audit logging, budget controls, and governance policies; CLI access to shared assistants and skills; Langfuse-based tracing/evaluation; per-user/project budgets and cost-center chargeback. It describes the CLI as bring-your-own-infrastructure with no per-developer fees.
- URL: https://docs.codemie.ai/user-guide/getting-started/enterprise-features/
- Publisher: EPAM / AI/Run CodeMie; pub_date: undated; accessed: 2026-11-05; confidence: medium (single vendor); class: documented capability / vendor commercial statement.
- Qualification: “No per-developer fees” is not evidence of zero platform, infrastructure, or model cost. A numeric price, complete license grant, and commercial terms were not established by this bounded review.

### C7 — Deployment options

- Claim: Standalone combines frontend/backend/nginx in one Docker image plus PostgreSQL via Compose. It is explicitly for PoCs and development, not production. Retrieval is disabled by default and budget management is not included. Production guidance points to Kubernetes or VM deployment.
- URL: https://docs.codemie.ai/user-guide/standalone/
- Publisher: EPAM / AI/Run CodeMie; pub_date: undated; accessed: 2026-11-05; confidence: medium (single vendor); class: documented deployment capability / explicit limitation.
- Qualification: A standalone demo cannot validate retrieval and budget features without additional configuration. Repository/image names containing “oss” do not establish license rights.

### C8 — History, SDLC actions, and project model

- Claim: Projects associate assistants, integrations, and data sources. Chat history supports assistant folders, read-only sharing links, and exports to PPTX, DOCX, PDF, or JSON. Tools can create Git pull requests and update Jira issues. Templates target developer, QA, project-manager, and code-reviewer roles. Skills are reusable instructions loaded by relevance and can supply inherited tools.
- URL: https://docs.codemie.ai/user-guide/getting-started/glossary/
- Publisher: EPAM / AI/Run CodeMie; pub_date: undated; accessed: 2026-11-05; confidence: medium (single vendor); class: documented capability.

## Implications for the proposed platform

These are analyst inferences from C1–C8, not vendor claims or validated product gaps. Confidence: medium for relevance, low for differentiation until product testing.

- **Strong direct comparison:** shared skills, project knowledge, MCP, history, CLI governance, and cost reporting overlap substantially with the proposed scope (C1–C8).
- **Useful UI reference:** role-scoped analytics, persistent global filters, budget details near the user's profile, and skill sharing/attachment visibility are concrete patterns to evaluate (C1, C2). Visual aesthetics and interaction quality remain unassessed.
- **Integration candidate:** scoped APIs, markdown skill export, conversation export, and correlation/build propagation provide plausible integration surfaces (C2–C4, C8). No integration was executed.
- **Differentiation hypothesis to test:** make the chain from ticket through agent run, skill version, PR, validation, and accepted outcome explicit. Retrieved evidence demonstrates SDLC actions and trace primitives, but does not settle whether CodeMie already presents that complete chain (C3, C8).
- **Measurement principle:** keep activity, engagement, spend, execution success, and accepted delivery outcomes distinct. The sources document the first four; they do not validate a causal productivity/ROI model (C1, C6).

## Vendor outcomes and unresolved questions

No independent customer outcomes or causal ROI evidence were retained. Product documentation is stronger evidence of supported configuration than of production effectiveness. Verify exact licensing/pricing, Enterprise feature gating, external analytics export schema, immutable skill/run version lineage, cross-tool session coverage, source ACL preservation, and actual ticket/PR/outcome joins before a build-versus-integrate decision. None of these unresolved points is an absent-feature claim.
