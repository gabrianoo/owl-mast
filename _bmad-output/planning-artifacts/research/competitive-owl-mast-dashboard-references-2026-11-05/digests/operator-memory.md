# Operator Memory — primary-source digest

Accessed: 2026-11-05. Read-only examination of the public repository and documentation; no installation or runtime validation. Publisher for all sources: aerovato / Aerovato Research (Kevin Liao). Publication dates unknown; LICENSE carries copyright 2026. GitHub main is mutable. The browser fetch timed out; public files were retrieved directly from GitHub's raw endpoint.

## Findings

- **Three ownership scopes are concrete filesystem partitions.** User/global `~/.operator/user/` holds reusable preferences, standards and skills; project-private `.operator/` is Git-ignored by Helper at setup; project-shared `.operator-shared/` is activated explicitly and published with the repository. Instruction conflict precedence is **Private > User > Shared**. These are ownership/placement conventions, not evidence of server-side tenant isolation or enforceable corporate-policy precedence; private instructions outrank shared ones by design. [S1, S2]
- **Real automation exists for context loading; persistence still depends on agent behavior.** A deterministic preamble loads guidance, partition instructions/catalogs, the main code index and diagnostics. Deeper documents remain on disk and are read when the agent chooses relevant catalog routes. The README calls documentation automatic, but its roadmap explicitly lists reliable long-conversation brain updates as future work, and architecture acknowledges agents can forget to update. Thus this is an instruction-driven documentation workflow plus automatic context injection, not demonstrated independent observation/capture or background extraction. The inspected Codex hook runs `operator-helper preamble` and emits its output; it does not capture tool activity or write memories. [S1, S2, S6]
- **Claude Code and Codex are documented integrations, with different freshness behavior.** README labels both CLI and Desktop fully supported. Claude requires its documented minimum version and loads a preamble once per process, including delegated subagent task prompts; clear/resume/branch do not refresh it, so changed memory needs a process restart. Codex uses plugin skills and startup-approved hooks; the inspected hook recognizes startup, clear and compact SessionStart sources. Both harness docs say there is no Operator status UI. Support is repository/documentation evidence, not a tested compatibility claim. [S1, S3, S4, S6]
- **Sharing means repository publication; synchronization is not a hosted service claim.** Shared Markdown can travel with Git. Private project memory stays local by design, and user memory resides in a local home directory. The reviewed architecture describes no account system, organization workspace, multi-tenant API, RBAC, collaborative conflict resolution, or cross-device synchronization service. Do not claim these capabilities exist or that their absence has been exhaustively proven. Agent/human edits of ordinary files and Git are the evidenced collaboration mechanism. [S1, S2]
- **License: BSD 3-Clause.** The repository license permits redistribution and modification subject to notice/disclaimer retention and its non-endorsement condition; copyright is Kevin Liao @ Aerovato Research, 2026. This is the license text observed, not a legal assessment. [S5]

## Decision relevance (inference)

A useful reference for explicit private/shared/user memory placement, readable canonical documents, compact catalogs, and inspectable stale-memory failure. It provides little evidence for dashboard design: the reviewed Claude/Codex adapters explicitly have no status UI. If adapting the pattern into a team dashboard, memory freshness, publication boundaries and permission enforcement would require their own design and validation. [S2–S4]

## Source register

| ID | Primary source | Publication date | Accessed |
|---|---|---|---|
| S1 | [Repository README](https://github.com/aerovato/operator-memory/blob/main/README.md) | Unknown | 2026-11-05 |
| S2 | [Architecture](https://github.com/aerovato/operator-memory/blob/main/docs/architecture.md) | Unknown | 2026-11-05 |
| S3 | [Claude Code integration](https://github.com/aerovato/operator-memory/blob/main/docs/harnesses/claude-code.md) | Unknown | 2026-11-05 |
| S4 | [Codex integration](https://github.com/aerovato/operator-memory/blob/main/docs/harnesses/codex.md) | Unknown | 2026-11-05 |
| S5 | [LICENSE](https://github.com/aerovato/operator-memory/blob/main/LICENSE) | Unknown; copyright 2026 | 2026-11-05 |
| S6 | [Codex hook implementation](https://github.com/aerovato/operator-memory/blob/main/packages/codex/src/hook.ts) | Unknown | 2026-11-05 |
