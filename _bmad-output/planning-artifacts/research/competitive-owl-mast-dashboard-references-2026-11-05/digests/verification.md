# Citation verification — 2026-11-05

Scope: fresh-context audit of research.md and its four existing digests; five public-web calls. No product execution, authenticated access, or independent operational testing. Statuses in the source ledger remain unverified: checking that a publisher documents a capability does not independently prove its operational outcome.

## Findings and mismatches

1. **T3 digest has a minor completeness mismatch.** Its provider list omits Pi and Muse Code, which the current usage document includes. Its Cursor description also narrows authentication to the server CLI login; the current document first allows T3 sign-in or CURSOR_API_KEY, with CLI login as fallback. The research.md wording (“several coding providers”) remains accurate. Current sources are moving main-branch documents, so the digest's file-change dates and commit IDs should be checked or pinned before claiming they describe this exact retrieved version. [T3 usage](https://raw.githubusercontent.com/pingdotgg/t3code/main/docs/user/usage.md)

2. **Ponytail “searchable session/test records” is ambiguous.** The implementation displays test status in each session row, but its search predicate matches session name, project and model; test status is not a search field. Prefer “searchable sessions with test-status records.” The same source confirms CSV-ledger rendering, four KPI categories, an 84-day activity window and streak calculations. Code inspection establishes implementation, not browser behavior or reliable collection. [Board source](https://raw.githubusercontent.com/DietrichGebert/ponytail/main/hooks/band/board.ts)

3. **Visdom technical detail could not be freshly corroborated.** The technical introduction failed twice through the web tool. Self-hosted Kubernetes and ticket-to-code details in research.md therefore retain their imported digest provenance; this audit neither confirms nor disproves them. Do not mark reference [13] freshly verified. [Technical documentation](https://docs.visdom.virtuslab.com/)

4. **CodeMie permission limitation is correctly scoped in research.md.** The FAQ explicitly distinguishes indexed/shared-project content from per-user MCP authentication. Its indexed retrieval does not recheck original source permissions, while per-user MCP can propagate a user token. Retention controls are unavailable by default. Avoid broadening this into “CodeMie never supports per-user source authorization.” [Admin FAQ](https://docs.codemie.ai/admin/faq/)

## Load-bearing claims checked

- **Visdom Context Fabric:** repositories, documentation, tickets/internal tools, MCP/AGENTS.md delivery, and services/dependencies are explicitly described. Supports the research's documented-overlap argument, without proving reduced tokens or improved accuracy. [Context Fabric](https://visdom.virtuslab.com/platform/context-fabric)
- **Visdom AI Tracing:** linked sessions/commits/tool calls, usage and cost analytics, attribution, policies and signed records are described. Supports documented scope; not independently demonstrated coverage, tamper resistance, productivity or ROI. [AI Tracing](https://visdom.virtuslab.com/platform/ai-tracing)
- **CodeMie:** private/project/marketplace skills and Markdown export are explicit. Personal, managed-project and organization analytics scopes and persistent filters are explicit; basic Analytics is expressly not Enterprise-gated. This pass did not reopen Enterprise packaging, workflow integration or API configuration pages. [Skills](https://docs.codemie.ai/user-guide/skills/manage-skills/), [Analytics](https://docs.codemie.ai/user-guide/analytics/)
- **T3:** API-equivalent estimates versus billing, history-dependent coverage, environment filters, model pricing and pooled allowance windows are supported. Webhook request delivery controls describe incoming automation, not an outbound analytics contract. [Usage](https://raw.githubusercontent.com/pingdotgg/t3code/main/docs/user/usage.md), [Project settings](https://raw.githubusercontent.com/pingdotgg/t3code/main/docs/user/project-settings.md)

## Independent-publisher check and limits

Searched for Visdom Context Fabric outside virtuslab.com and CodeMie analytics/skills outside codemie.ai, epam.com and GitHub. A [FindSkills listing](https://www.findskills.org/skills/codemie-ai-codemie-code) was opened, but it attributes content to codemie-ai and reproduces maintainer-style documentation; it is not an independent capability test. [Visdom's LinkedIn product page](https://www.linkedin.com/products/virtuslab-visdom/) and [VirtusLab's GitHub Pages site](https://virtuslab.github.io/visdom-governance/) are vendor-authored despite different domains. No retrieved independent evidence proves the major overlap operationally.

No material contradiction was found in the checked load-bearing positioning claims. Screenshot appearance, licenses, commercial terms, exact source-change dates and remaining citations were not freshly audited. Existing visual-observations.md explains why research.md can cite inspected screenshots even though the initial CodeMie/Visdom digests themselves did not inspect them.
