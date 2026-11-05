# Kody — competitive reference digest

Accessed: 2026-11-05. Read-only public primary-source research; no installation or runtime validation. Discovery lead: opensourceprojects.dev/post/kody; conclusions below use the upstream repository. Sources are mutable `main` documents, not a pinned release. Publication dates unknown unless stated.

## Findings

- **Product/category:** Kody describes an agents’ cloud providing portable memory, credentials, code/packages, and automation through MCP. It is a Cloudflare Workers application with OAuth-protected MCP, a TanStack Start UI, D1/KV storage and Durable Objects. Its compact `search` / Code Mode `execute` interface is an explicit alternative to a large static MCP tool catalogue. Treat it as an adjacent agent backend/workspace, not established evidence of a complete software-delivery command center. [S1, S3]
- **Memory:** Task hints (`memoryContext`) and search queries retrieve long-term memories; top one or two active personal memories surface compact summaries, with full detail fetched separately. Documents describe lexical/vector ranking, deduplication, a relevance threshold, verify-before-write, source URI metadata, and JSON export. Crucially, the memory capabilities target the signed-in person's **personal org**; team/org resource support does not establish a shared team-memory layer. Personal facts should not be copied into org packages without permission. [S4]
- **Org/team scopes:** Personal and team orgs are explicit data/billing boundaries. Memberships, teams, resource grants, outside collaborators, owner-controlled creation permissions, and org-wide read/manage grants are documented. One MCP connection binds one org. Org-wide `job:read` covers jobs, workflows, runs, Activity and overview run history; memories and secret values are not grantable org-wide. This is substantial access-control/workspace evidence, rather than a single-user-only product. [S5]
- **Native telemetry exists:** Run records cover MCP execute, package exports, subscriptions, app HTTP/realtime handlers, jobs, workflows and webhooks. They include statuses, timing, attribution, errors, logs and triage; Activity UI and `runList`/`runGet`/`runSummary` provide inspection. History caps are approximately 30 days, 2,000 runs per user, 200 log lines per run; keyless successful exports can be omitted. Role-gated admin insights aggregate content-free snapshots. Therefore a blanket claim that Kody lacks centralized telemetry would be unsupported. [S6]
- **What remains unproven:** In these six sources, no evidence establishes ingestion of arbitrary external coding-agent sessions, organization-wide cross-host token/cost normalization, or an end-to-end requirement→story→PR→CI→deployment evidence graph. This is a bounded search finding, **not proof of absence**. Project intent prioritizes portable personal-assistant infrastructure; enterprise SSO/directory provisioning is explicitly not an optimization target. [S3, S6]
- **License/commercial reuse:** Actual license is **Functional Source License 1.1, ALv2 Future License (FSL-1.1-ALv2)**, copyright 2026 Kent C. Dodds. Internal use and specified other permitted uses are allowed; commercial availability to others that substitutes for Kody or offers the same/substantially similar functionality is excluded as “Competing Use.” Terms apply to modifications/derivatives and redistribution must retain terms/notices. Each version receives Apache 2.0 rights on its own second anniversary. Do not treat the Fair Source label as current unrestricted Apache/MIT reuse permission. A competing commercial fork or copied backend needs a separate permission/eligibility determination; no such permission was found. [S2]

## Decision relevance and uncertainty

Strong reference for compact MCP capability discovery, task-sensitive personal memory retrieval, org/grant boundaries, and actionable native run-history UI. A commercial product can study those behaviors as design references; this research does not establish permission to copy competing implementation code. A distinct opportunity may lie in cross-host SDLC evidence and telemetry, but that remains a hypothesis requiring broader feature/code validation. [S1–S6]

Documentation uses per-org isolation language in product intent but per-user RunLog language in the architecture page. The org guide also offers org-wide run access. Record this as a terminology/implementation verification question rather than asserting either unrestricted cross-org visibility or no team observability. No deployed UX, security enforcement, source-code tests, release provenance, or historical license conversion dates were validated. [S3, S5, S6]

## Source register

All publishers: kody-hq/Kody upstream repository maintainers on GitHub. All publication dates: unknown; S2 copyright notice is 2026, not a verified publication date. All accessed: 2026-11-05. Content retrieved from each linked file's `raw.githubusercontent.com/kody-hq/kody/main/` equivalent because the GitHub rendered page timed out.

1. **S1 — README:** https://github.com/kody-hq/kody/blob/main/README.md
2. **S2 — LICENSE:** https://github.com/kody-hq/kody/blob/main/LICENSE
3. **S3 — Project intent:** https://github.com/kody-hq/kody/blob/main/docs/contributing/project-intent.md
4. **S4 — Memory and conversation context:** https://github.com/kody-hq/kody/blob/main/docs/use/memory.md
5. **S5 — Organizations:** https://github.com/kody-hq/kody/blob/main/docs/guides/organizations.md
6. **S6 — Run records:** https://github.com/kody-hq/kody/blob/main/docs/contributing/architecture/run-records.md
