# Architecture research and reality review

Date: 2026-11-06

Verdict: **PASS for the architecture contract.** No critical, high or medium research finding requires changing a committed technology decision. This is documentation/source verification, not a successful build, native integration, deployment or recovery test. The existing qualification gates remain required.

Reviewed: `ARCHITECTURE-SPINE.md` and technology research recorded in `.memlog.md`. The selected Java 27/Spring Boot 4.1.2 pins are supported by current primary documentation. Other exact versions remain intentionally unselected; this review does not turn previously researched recommendations into adopted pins.

## Evidence by commitment

| Decision | Current primary evidence | Assessment and remaining boundary |
| --- | --- | --- |
| Java 27 with Spring Boot 4.1.2 | [Spring Boot system requirements](https://docs.spring.io/spring-boot/system-requirements.html), [Oracle JDK 27 documentation](https://docs.oracle.com/en/java/javase/27/) | Boot's current 4.1.2 page explicitly includes Java 27 compatibility. JDK 27 documentation exists. No downgrade or replacement is warranted. Distribution/patch and actual application build remain OM-01.01 work. |
| Gradle Kotlin DSL build | [Gradle 9.8.2 release notes](https://docs.gradle.org/9.8.2/release-notes.html) | A compatible stable build option exists: 9.8.2 documents Java 27 support for both its daemon and toolchains. It remains a researched recommendation, not a selected wrapper pin. |
| Focused Lombok use | [Lombok changelog](https://projectlombok.org/changelog) | Current changelog documents JDK 27 support in 1.18.48. Exact compiler/plugin/formatter/analyzer integration remains OM-01.01 qualification. No claim that arbitrary older Lombok versions work. |
| PostgreSQL with VectorChord indexes | [VectorChord upstream](https://github.com/supervc-stack/VectorChord), [installation](https://docs.vectorchord.ai/vectorchord/getting-started/installation.html) | VectorChord explicitly depends on pgvector representation; its installation includes the dependency and dedicated extension. AD-7 correctly permits that dependency while disallowing native pgvector indexes. Actual image/version, preload, codecs and query/index behavior remain OM-01.02/OM-04.01 tests. |
| Reactive request/persistence seed | [Spring R2DBC](https://docs.spring.io/spring-framework/reference/data-access/r2dbc.html), [Reactor blocking-adapter guidance](https://projectreactor.io/docs/core/release/reference/faq.html#faq.wrap-blocking) | Reactive database facilities and bounded isolation of blocking calls are documented. AD-5 does not pretend that all SDK calls are nonblocking. Connection-bound authorization and atomic work/audit integration still need tests. |
| Spring AI when needed | [Spring AI getting started](https://docs.spring.io/spring-ai/reference/getting-started.html), [PgVectorStore](https://docs.spring.io/spring-ai/reference/api/vectordbs/pgvector.html) | Current Spring AI 2.0.x supports Boot 4.1.x. The stock pgvector example is JDBC and uses HNSW; it is not proof of a reactive VectorChord adapter. The explicit OM-04.01 qualification and AD-5/AD-7 rules correctly prevent adopting it unchanged. |
| MCP endpoint inside the backend | [Spring AI MCP server starter](https://docs.spring.io/spring-ai/reference/api/mcp/mcp-server-boot-starter-docs.html) | Async WebFlux and Streamable HTTP are supported. HTTP starters do not supply authentication/authorization by default. AD-4/AD-8 and the MCP/enrollment gates retain the required security boundary; no automatic Keycloak interoperability is claimed. |
| Keycloak-managed personal accounts and optional external hosting | [Keycloak OIDC](https://www.keycloak.org/securing-apps/oidc-layers), [database configuration](https://www.keycloak.org/server/db) | OIDC identity facilities exist, and supported PostgreSQL versions overlap the documented VectorChord image family. Browser origins/session ownership and native credential refresh remain gated; app Java 27 is not asserted as the Keycloak process runtime. |
| PostgreSQL-backed work processing | [PostgreSQL SELECT locking](https://www.postgresql.org/docs/current/sql-select.html) | PostgreSQL documents queue-like use of locking with skipped locked rows. This supplies a building block, not a complete durable-work engine. AD-6 correctly assigns leases, retries, ownership checks, audit durability and uncertain-effect reconciliation to application implementation. |
| Explicit direct OTLP receiver | [OTLP specification](https://opentelemetry.io/docs/specs/otlp/) | Standard client/server signal protocols and acknowledgment/retry semantics support a direct receiver. Configuring Spring outbound telemetry does not create it. OM-06.02 owns actual protocol implementation, limits and interoperability; AD-8 correctly avoids a mandatory collector. |
| Codex MCP, hooks and telemetry | [Codex MCP](https://learn.chatgpt.com/docs/extend/mcp?surface=cli), [hooks](https://learn.chatgpt.com/docs/hooks), [advanced configuration](https://learn.chatgpt.com/docs/config-file/config-advanced) | Current official documentation supports authenticated remote MCP, lifecycle hooks and OTLP export. Local read-only `codex --version` returned `codex-cli 0.166.0`. MCP hooks require an existing connection and have lifecycle limits; OTel is opt-in and its routing is outside project-local config. These are capability-qualification constraints, not contradictions of the product's desired default-on capture policy. |
| Claude Code MCP and telemetry | [Claude MCP](https://code.claude.com/docs/en/mcp), [monitoring](https://code.claude.com/docs/en/monitoring-usage) | Remote HTTP MCP and separately configurable OTLP signals are documented. Content flags, hook readiness, incomplete exports and real runtime coverage still require E05–E08/OM-18.01 qualification. No complete conversation history or durable offline backlog is proven by documentation. |
| Testcontainers with actual dependencies | [Boot Testcontainers](https://docs.spring.io/spring-boot/reference/testing/testcontainers.html), [PostgreSQL module](https://java.testcontainers.org/modules/databases/postgres/), [generic containers](https://java.testcontainers.org/features/creating_container/) | Boot 4.1.2 documents PostgreSQL R2DBC service connection support. Custom compatible images and generic service containers make the selected test approach feasible. Pinned VectorChord and Keycloak fixtures, issuer/network behavior and CI compatibility still need execution. |
| Kubernetes PVC snapshots and recovery limits | [Kubernetes snapshots](https://kubernetes.io/docs/concepts/storage/volume-snapshots/), [PostgreSQL filesystem backup](https://www.postgresql.org/docs/current/backup-file.html) | Snapshot support depends on CSI/controller/driver capabilities. PostgreSQL snapshots require complete consistent data including WAL; multi-volume consistency needs care. AD-15 accurately retains those prerequisites and avoids equating two app pods with end-to-end HA. |

## Findings and disposition

No new blocker or unsupported committed version was found. Leave the selected stack and the explicit deferred gates intact.

Keep these qualifications visible in implementation handoff:

1. Documentation-level compatibility is not a tested combination. OM-01.01/02 must pin and run the build, dependency images and integration fixtures before downstream code relies on them.
2. Spring AI transport availability is not authentication, and its stock PgVectorStore is not the selected reactive VectorChord integration. Existing MCP/security and persistence gates cover both distinctions.
3. Native capture, identities, hooks, telemetry content and cross-channel accounting remain supported-runtime evidence work. Default-on Owl Mast collection does not alter native exporter defaults automatically or prove complete capture.
4. The current OTLP specification also requires bounded responses, including decompressed client parsing and partial-success diagnostics. Treat its wire rules as part of OM-06.02 conformance; the spine intentionally delegates exact protocol details rather than freezing a partial implementation.
5. React/TypeScript/Vite is an unselected recommendation, and no starter is claimed to have been instantiated. Verify live starter defaults when OM-01.04 selects it. MongoDB, Neo4j, OpenFGA and workflow engines are later candidates, not mandatory unverified dependencies.

## Verification limits

OpenJDK's project/download pages returned HTTP 403 through the web fetch tool; Oracle's JDK 27 documentation plus the current Spring and Gradle compatibility pages supplied independent primary evidence. This access failure does not establish a missing release.

No source accounts, secrets, exporter settings or live application configuration were inspected or changed. No application build, container, runtime adapter, snapshot, restore or deployment was executed by this review. Official OpenAI documentation was consulted under the OpenAI Docs skill for the Codex-specific claims.

Reviewed spine SHA-256: `cc8baab022ac624e10090f73895df1b0e9fcfd9a7b362de154f9f6f6be39cb78`.
