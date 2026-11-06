---
epic: E04
status: planned
review_status: pending-owner-review
implementation_status: not-started
---

# Epic E04 — Retrieve authorized knowledge through MCP

Claude, Codex and authorized people find applicable exact-version knowledge through the same secured backend. Agents initiate bounded discovery when needed, then explicitly load selected versions; validated guidance is the default and a client-controlled inclusion flag can add labelled unvalidated candidates. Do not inject the lesson library automatically. Retrieval and package delivery remain distinct from native skill activation and useful reuse; this draft does not claim client interoperability has been qualified.

**Epic prerequisites:** E03

<a id="om-04-01"></a>

### OM-04.01 — Build lexical and VectorChord retrieval over eligible knowledge

As an authorized knowledge seeker, I want relevant project knowledge found through lexical and semantic retrieval, so that terminology differences do not hide useful guidance.

**Requirements:** FR-10, FR-13, FR-17, FR-18; NFR-1, NFR-2, NFR-3, NFR-4; AR-03, AR-05, AR-06, AR-11, AR-17; UX-DR31, UX-DR48.

**Depends on:** E03

**Acceptance criteria:**
- Given an eligible exact knowledge version and authorized processing destination, when indexing completes, then lexical records and embeddings retain version/provenance links and use VectorChord for vector indexes; pgvector is used only for its required type/operator dependency.
- Given project/source permissions, lifecycle or content changes after indexing, when a query runs, then current authorization and eligibility govern candidates and disclosures; stale indexes cannot return protected text, hidden matches or a withdrawn version.
- Given failed embeddings, unavailable vector search or delayed indexing, when a query is served, then supported lexical behavior may continue with an explicit degraded-coverage state; absent semantic coverage is not presented as complete or as zero matches for all knowledge.
- Given replayed indexing jobs, out-of-order versions or a restart, when processing resumes, then work is idempotent and a stale completion cannot replace the active version's index identity.

**Tasks:**
- [ ] **OM-04.01-T1** Qualify VectorChord/type/operator versions, R2DBC query/codec support and query plans on the selected PostgreSQL stack; record any bounded blocking adapter rather than assuming a JDBC Spring AI vector store is reactive.
- [ ] **OM-04.01-T2** Implement only the lexical/chunk/embedding/index-status records needed for exact-version knowledge, including model/index version and current-eligibility/source bindings.
- [ ] **OM-04.01-T3** Add durable index/update/invalidation jobs and scoped hybrid retrieval with declared freshness and lexical-degradation behavior; qualify any embedding destination before sending content.
- [ ] **OM-04.01-T4** Verify restricted-source exclusion, post-index revocation, withdrawn versions, duplicate/late jobs, embedding failure and authorization before any downstream model receives retrieved context.

<a id="om-04-02"></a>

### OM-04.02 — Return authorized exact-version knowledge with honest coverage

As an agent or contributor, I want a task-scoped knowledge response with provenance and freshness, so that I can interpret its applicability without receiving unrelated customer context.

**Requirements:** FR-9, FR-10, FR-11, FR-13, FR-17, FR-21; NFR-1, NFR-2, NFR-4, NFR-6; AR-07, AR-10, AR-16, AR-17, AR-18; UX-DR21, UX-DR31, UX-DR32, UX-DR48.

**Depends on:** OM-04.01

**Acceptance criteria:**
- Given an authenticated principal and explicit authorized project/purpose, when the client searches, then bounded summaries/metadata contain eligible exact-version references, scope, applicability, validation/freshness and permitted provenance; full content or package files are returned only through an explicit selected-version load. Independently authorized company publications use the same contract.
- Given missing/unauthorized scope or unverifiable current source access, when retrieval runs, then it fails closed without falling back to company/another project or revealing restricted result counts, snippets or source identifiers.
- Given no applicable results or an eligible result limit, when a response is built, then an honest empty result or eligible-only truncation notice is returned; permission-filtered matches do not appear in omission counts.
- Given the unvalidated inclusion flag is absent or false, when search or an exact-version load runs, then only currently validated/approved eligible knowledge is returned. An explicit client opt-in may add labelled candidates/conflicts but cannot widen permissions or override lifecycle restrictions; direct IDs and cached results follow the same rule. Adopted A-2 denies ordinary retrieval of withdrawn/quarantined versions and promoted derivatives while keeping permitted restricted history.
- Given a new session, another agent turn, a work update or new knowledge, when the client has not requested lesson content, then Owl Mast does not inject full lessons/history into its context. Search results and selected loads expose bounded pagination/continuation and truthful eligible-only truncation so the client controls what enters context.
- Given a completed retrieval, when its evidence is recorded, then it identifies the authorized recipient, project, exact versions and time without equating transport success to confirmed delivery, native loading or reuse and without depending on retained conversation bodies; the adopted capture default and remaining A-3 retention rules are separate from minimal retrieval evidence.

**Tasks:**
- [ ] **OM-04.02-T1** Implement Knowledge-owned versioned bounded search-summary and selected-version load contracts, delegating derived index/query work to Retrieval, with trusted scope, an explicit client-controlled unvalidated flag defaulting off, validation/provenance labels, pagination/coverage and safe empty/failure semantics.
- [ ] **OM-04.02-T2** Apply current project/source/purpose authorization, validation opt-in and lifecycle eligibility consistently to search, exact-version reads, caches and UI adapters; scope cached results by eligibility mode and recheck current state.
- [ ] **OM-04.02-T3** Emit minimal retrieval evidence and diagnostic/audit events through owned module contracts, preserving recipient disclosure and A-3 collection limits.
- [ ] **OM-04.02-T4** Verify validated-only defaults, explicit unvalidated opt-in, direct-ID/cache bypass attempts, candidate/conflict labels, bounded search/load, no unsolicited context injection and existing cross-project/revocation/hidden-match privacy cases.

<a id="om-04-03"></a>

### OM-04.03 — Expose authenticated remote MCP in the Spring backend

As a Claude or Codex user, I want one authenticated remote knowledge interface, so that the same Owl Mast service works from my executing machine with or without T3.

**Requirements:** FR-10, FR-17, FR-19, FR-21; NFR-1, NFR-3, NFR-5, NFR-6; AR-01, AR-02, AR-03, AR-09, AR-10, AR-14, AR-15, AR-16, AR-18; UX-DR21, UX-DR48.

**Depends on:** OM-04.02

**Acceptance criteria:**
- Given a supported Claude/Codex remote MCP client, when it authenticates through the qualified Keycloak-backed flow and requests knowledge, then the existing Spring application serves the knowledge contract with the trusted principal, tenant, project and purpose boundaries intact.
- Given incorrect issuer/audience, expired/revoked credentials, a mismatched client/project grant or a forged scope, when an MCP request arrives, then it is denied safely without logging credentials or falling back to a shared connector identity.
- Given a client reconnect or repeated request, when the connection resumes, then authorization is rechecked and observable operations have explicit replay semantics; connection success alone never implies source readiness or successful skill activation.
- Given the exposed MCP tool catalog, when a client discovers tools, then it contains authorized knowledge capabilities and no agent launch, shell, routing, merge or deployment controls; T3 is not a dependency of authentication or retrieval.
- Given OAuth client-registration/discovery differences between the actual supported clients and Keycloak, when qualification runs, then the working protected-resource/authorization metadata, token audience/scope, registration and refresh/revocation contract is documented with tested limits before promising interoperability.

**Tasks:**
- [ ] **OM-04.03-T1** Qualify the Java/Spring MCP server transport and Keycloak OAuth integration with actual Claude/Codex clients, including discovery, registration, token validation and token lifecycle; record any missing supported capability explicitly.
- [ ] **OM-04.03-T2** Implement authenticated remote MCP search and selected-version load adapters in the reactive Spring backend, exposing the client eligibility flag and bounded responses while isolating blocking calls and preserving request context.
- [ ] **OM-04.03-T3** Define the client-facing setup contract using endpoint and credential references; document direct-network requirements, reconnect limits and the boundary to later enrollment/client packaging.
- [ ] **OM-04.03-T4** Verify issuer/audience/scope failures, revocation, cross-project access and supported-client knowledge calls; keep standalone and T3-hosted native adapter qualification in their own dependent epics without requiring T3 here.

<a id="om-04-04"></a>

### OM-04.04 — Deliver complete exact-version packages with explicit receipts

As an agent client, I want to fetch and acknowledge a complete authorized skill package, so that I can verify what arrived before attempting native loading.

**Requirements:** FR-10, FR-11, FR-13, FR-17, FR-21; NFR-1, NFR-2, NFR-3, NFR-4; AR-06, AR-14, AR-16, AR-17, AR-18; UX-DR21, UX-DR32, UX-DR48.

**Depends on:** OM-04.02, OM-04.03

**Acceptance criteria:**
- Given an authorized exact package version, when a client requests its manifest and permitted files, then the response binds the complete file set and checksums to that version; memory text retrieval is not represented as native skill installation.
- Given a missing/corrupt file, partial transfer, permission loss or changed eligibility during delivery, when delivery completes or resumes, then the client receives an explicit incomplete/denied outcome and no successful complete-package receipt is recorded.
- Given a recipient acknowledges the verified delivered artifact/version, when a receipt is accepted, then the recipient/project/version/time and evidence basis are recorded idempotently; unsupported read/load or activation acknowledgment remains unavailable rather than inferred from the fetch.
- Given a revoked or withdrawn version is cached outside Owl Mast, when a new delivery is requested, then current eligibility is rechecked and denied if invalid; the contract states that earlier external copies cannot be recalled and verifies managed cache handling under adopted A-2.

**Tasks:**
- [ ] **OM-04.04-T1** Implement authorized manifest/file delivery through the knowledge contract with exact-version checksums, bounded responses and explicit partial/corrupt-transfer outcomes.
- [ ] **OM-04.04-T2** Add Knowledge-owned recipient-bound delivery acknowledgment and idempotent receipt records, keeping retrieval, delivery and client-reported native loading as separate evidence types.
- [ ] **OM-04.04-T3** Specify the client package-verification/native-activation boundary and current-eligibility/cache behavior consumed by the native Claude/Codex adapters; do not introduce remote execution tools.
- [ ] **OM-04.04-T4** Verify multi-file completeness, replayed receipts, unsupported acknowledgments, concurrent permission loss and withdrawn cached versions; verify adopted A-2 lineage-preserving withdrawal and managed-cache behavior.
