# OKF Agent Memory: sourced research digest

Accessed 2026-11-05. Primary public documentation and source inspection only; no installation or execution. Branch: `develop`; observed tree SHA `373cea4758eadfd9b12e28971e751edfb3131132`. This is a moving development branch, not a verified release snapshot.

## Findings

- **Storage and positioning:** local Markdown knowledge bundles, Git review/history, a Go toolchain and embedded stdio MCP form the core. The README identifies an MIT license. It also documents optional encrypted Hub synchronization and registry/Git bundle distribution, so “Git only” would misdescribe the current offering. Its approximately 80% token-saving and microsecond-search figures are publisher claims, not independently reproduced results; they cannot establish end-to-end agent latency, retrieval quality, or savings on another workload. [S1]
- **Metadata and lifecycle:** the convention explicitly separates `sources`, `generated`, `verified`, `status`, and `stale_after`; agents must preserve uncertainty and meaningful history. Its capture sequence is discover, evaluate, search, create/update, add provenance, validate and revisit. Semantic selection remains the agent's responsibility. The convention still lists verification workflows, sensitive knowledge and concurrency among unfinished topics; this older convention should not override newer implementation evidence. [S2]
- **Retrieval and validation:** CLI reference specifies lexical BM25, metadata predicates, path-bound `code_refs`, full concept inspection and stdio MCP tools. Strict validation checks provenance/graph problems; stale dates require separate flags to become failing gates. Project > vendor > user > system search precedence allows project concepts to shadow matching system IDs. This is retrieval precedence, not an enforceable corporate-policy hierarchy. [S3]
- **Capture automation boundary:** the skill instructs agents to search first, fetch detail selectively, save decisions/requirements and validate before finishing. These are agent instructions, not evidence of a background transcript watcher or guaranteed capture of every task. [S4] In contrast, MCP implementation concretely calls `SaveConcept` with automatic log/index updates and fixed actor `agent/mcp` for create/update. Tool-invoked bookkeeping is implemented; deciding to call those tools remains agent-controlled. The dispatcher loads a bundle before tool handling, so a small in-memory BM25 timing should not be equated with total MCP request cost. [S5]
- **Trust limits:** CLI documents restrictions against non-human actors adding/changing human verification entries, while allowing existing entries to remain. This is useful metadata validation, not demonstrated identity attestation or proof that a fact is true. [S3] The skill separately forbids forged human verification, reinforcing the distinction between behavioral convention and technical authority. [S4]
- **Sharing and tenancy:** documentation describes encrypted Hub push/pull/sync, concurrent-head conflict handling and local conflict copies. [S3] Inspected embedded Hub `Server.Handler` routes requests by caller-supplied vault ID; maps segregate vault heads/blobs and compare-and-swap rejects stale heads. That handler contains no authentication or authorization checks. Vault namespaces therefore do not establish tenant access isolation. This finding concerns the embedded handler, not any separately operated hosted service or external middleware, which were not assessed. [S6]

## Decision relevance (inference)

Strong reference for inspectable memory records, progressive retrieval, source/lifecycle metadata and automatic bookkeeping after explicit capture calls. A product using these patterns should separately design capture accountability, human approval identity and tenant authorization; those guarantees cannot be inferred from agent instructions, trust labels or scoped lookup alone. [S2–S6]

## Sources

All publishers: **okf-memory / okf-agent-memory maintainers**. Publication/update date: **unknown** for each. Access date: **2026-11-05** for each.

- **S1:** [Repository README](https://github.com/okf-memory/okf-agent-memory/tree/develop) — positioning, storage, license label, benchmark claims, Hub existence.
- **S2:** [Agent Memory Convention](https://github.com/okf-memory/okf-agent-memory/blob/develop/docs/spec/CONVENTION.md) — metadata semantics, lifecycle, agent/tool responsibility.
- **S3:** [CLI and MCP reference](https://github.com/okf-memory/okf-agent-memory/blob/develop/docs/guides/CLI.md) — retrieval, validation, scope priority, actor restrictions, synchronization.
- **S4:** [Memory skill](https://github.com/okf-memory/okf-agent-memory/blob/develop/.agents/skills/okf-memory/SKILL.md) — behavioral capture and retrieval rules.
- **S5:** [MCP implementation](https://github.com/okf-memory/okf-agent-memory/blob/373cea4758eadfd9b12e28971e751edfb3131132/pkg/okf/mcp.go) — tool dispatch, load-before-handle, automatic bookkeeping and fixed actor.
- **S6:** [Embedded Hub server](https://github.com/okf-memory/okf-agent-memory/blob/373cea4758eadfd9b12e28971e751edfb3131132/pkg/sync/server.go) — vault routing, storage maps, conflict check and absence of authorization inside handler.

Open questions: hosted Hub access controls and operational guarantees; human verifier authentication outside metadata; capture compliance under real agent workflows; independent benchmark quality and representative corpus scale. No claim of absence beyond the inspected files.
