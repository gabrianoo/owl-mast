---
epic: E08
status: planned
review_status: pending-owner-review
implementation_status: not-started
---

# Epic E08 — Use Codex with Owl Mast in every supported execution mode

Codex users receive scoped knowledge and report supported lifecycle, usage and knowledge-use evidence through native configuration, MCP, plugins/hooks and direct telemetry. The executing machine communicates with Spring in standalone and T3-hosted operation. Both paths are full planned scope and do not depend on the optional T3 enrichment adapter.

**Epic prerequisites:** E06

<a id="om-08-01"></a>

### OM-08.01 — Package and qualify the native Codex connection

As a contributor, I want an enrollment-aware Codex package that preserves my configuration, so that Owl Mast joins my existing workspace with minimal recurring setup.

**Requirements:** FR-2, FR-3, FR-18, FR-19, FR-21; NFR-5, NFR-6; AR-14, AR-18, AR-19; UX-DR22, UX-DR33, UX-DR54, UX-DR59

**Depends on:** E06

**Acceptance criteria:**

- Given an enrolled supported Codex installation, when its package/configuration is applied, then owned changes add direct Owl Mast integration through secret references while preserving existing MCP servers, hooks, skills, feature settings and managed-policy constraints.
- Given standalone or T3-hosted Codex, when compatibility is qualified, then effective settings, hook availability, exporter behavior and fields are recorded for that exact runtime/version; API-provider usage, native Codex telemetry and T3 diagnostics remain different sources.
- Given policy-disabled hooks, an unsupported version, a conflicting endpoint or missing credentials, when readiness is evaluated, then unsupported/denied/failed states remain distinct and repair does not weaken sandbox, approval or execution policies.
- Given the adopted full-conversation default, when setup is prepared, then synthetic content fixtures verify capture and project opt-out without changing execution permissions; actual live export still requires resolved project archive/other-record-policy and destination/permission prerequisites and content coverage is measured explicitly.

**Tasks:**

- [ ] **OM-08.01-T1** Define the versioned Codex package manifest, supported modes, owned settings and managed-policy-compatible merge/repair behavior.
- [ ] **OM-08.01-T2** Implement enrollment-bound MCP, hook and OTLP configuration with secret references and preservation of unrelated user configuration.
- [ ] **OM-08.01-T3** Qualify the actual standalone and T3-hosted configurations and retain a capability matrix covering native settings, hooks and fields.
- [ ] **OM-08.01-T4** Add failure/repair checks for unsupported clients, missing secrets, managed overrides and endpoint conflicts without changing execution authority.

<a id="om-08-02"></a>

### OM-08.02 — Deliver exact-version memory and complete Codex skills

As an enrolled Codex user, I want applicable memory and native skills in my project context, so that I can continue work without migrating Notion or copying a recap.

**Requirements:** FR-10, FR-11, FR-17, FR-21; NFR-1, NFR-4, NFR-5; AR-06, AR-14, AR-15, AR-16, AR-19; UX-DR21, UX-DR33, UX-DR48, UX-DR50

**Depends on:** OM-08.01

**Acceptance criteria:**

- Given an authorized selected project, when Codex chooses to search through authenticated MCP, then it receives bounded summaries and exact-version references, followed by selected content only on explicit load; validated-only is the default and the client must explicitly opt in to labelled unvalidated candidates. No session/turn/work-update trigger injects full lesson content without a client request, and empty/denied searches do not disclose private matches elsewhere.
- Given a qualified native skill package, when it is materialized or refreshed through the supported local mechanism, then every declared file/path/checksum is validated and ownership respected; search, retrieval, native installation and actual loading remain separate outcomes.
- Given the user's existing authorized Notion page creation and knowledge flow, when the package is enabled, then it continues without duplicate Notion saves or replacing source authority; skill discovery/reading is verified independently from page creation.
- Given revoked access, withdrawal, package corruption or unavailable eligibility checks, when an Owl Mast-managed retrieval, delivery, materialization or refresh is requested, then it fails safely and records the true result; independent loading of retained local packages and text already inside an external session remain outside server enforcement unless a specific native interception capability has been separately qualified.

**Tasks:**

- [ ] **OM-08.02-T1** Implement the Codex MCP knowledge adapter using current authorization and exact-version delivery contracts.
- [ ] **OM-08.02-T2** Implement qualified native package discovery/materialization with manifest validation, preserved unrelated skills and explicit cache/withdrawal handling.
- [ ] **OM-08.02-T3** Verify Notion page creation, source-authorized reading, skill activation and delivery receipts as separate paths in both modes.
- [ ] **OM-08.02-T4** Verify client-driven bounded search/selected load, validated default, explicit unvalidated opt-in and no unsolicited lesson injection in both modes; retain restricted/empty/conflicting-result, invalid-manifest, interrupted-refresh and revoked-version tests and distinguish independent retained-copy use.

<a id="om-08-03"></a>

### OM-08.03 — Observe native Codex work with its actual event contracts

As an authorized viewer, I want source-supported Codex events and usage, so that its run history is accurate without granting Owl Mast control of the agent.

**Requirements:** FR-4, FR-11, FR-16, FR-18, FR-19; NFR-2, NFR-3, NFR-6; AR-14, AR-15, AR-16, AR-17, AR-18; UX-DR21, UX-DR46, UX-DR47, UX-DR50, UX-DR54

**Depends on:** OM-08.01

**Acceptance criteria:**

- Given native observations are enabled, when Codex runs, then separately configured log, metric and trace exporters send directly to Spring using the qualified endpoint/protocol/header contract; ordinary analytics or T3 diagnostic export is not substituted for this evidence.
- Given supported model-request hooks, when an attempt completes, fails or is cancelled, then available turn/agent/model/status/token evidence maps into source-qualified events; absent token usage stays unknown and real retry consumption differs from replay of the same event.
- Given hooks using MCP, when the connection is not ready at startup or a hook event lacks MCP support, then the integration follows qualified native limitations or an observational command adapter and records missing coverage; it does not assume reconnect or SessionEnd delivery guarantees.
- Given configured and runtime-reported effort, location or model differ, when evidence arrives, then each keeps its source/time; provider identity, task role and human initiator are not guessed from configuration or shared credentials.
- Given hook/export failure or sensitive tool output, when reporting occurs, then observation does not block/approve/rewrite execution and excludes disallowed content before persistence; loading, application and verified useful reuse remain separate evidence types.

**Tasks:**

- [ ] **OM-08.03-T1** Implement qualified observational command/MCP hooks, including supported model-attempt evidence and bounded shutdown/startup behavior.
- [ ] **OM-08.03-T2** Generate independent logs/metrics/traces configuration using native Codex keys, binary/JSON options, exact endpoints and protected authentication references.
- [ ] **OM-08.03-T3** Map available conversation messages, roles, turn/agent/tool IDs and tool argument/result pairs into E06 alongside request tokens and usage semantics; preserve content gaps and do not assume metrics carry session-level detail.
- [ ] **OM-08.03-T4** Apply default-on prompt/response/tool-content capture and project overrides; verify redaction, missing/truncated content, retries, null counts, startup races, background-hook cancellation and duplicate cross-signal records.

<a id="om-08-04"></a>

### OM-08.04 — Prove Codex integration and recovery in all pilot combinations

As a pilot contributor, I want evidence that Codex works in both projects and execution modes, so that readiness and recurring setup claims are trustworthy.

**Requirements:** FR-2, FR-3, FR-10, FR-11, FR-16, FR-17, FR-21; NFR-1, NFR-3, NFR-4, NFR-5; AR-14, AR-18, AR-19; UX-DR22, UX-DR33, UX-DR46, UX-DR54, UX-DR59

**Depends on:** OM-08.02, OM-08.03

**Acceptance criteria:**

- Given Codex in Syntelligence and Movesion, both standalone and T3-hosted, when the four combinations are exercised, then each demonstrates direct knowledge access/reporting with verified capability coverage; an unmet required capability remains an open integration issue.
- Given supported per-run fields, when evidence is inspected, then model, effort, session, task role, location and input/output tokens each have a source/time or labeled gap; matching provider names do not establish equivalent effort scales.
- Given rotation, revocation, package repair, interruption or restart, when the client reconnects, then current authorization is enforced, unrelated settings survive and duplicated evidence is not new usage; missing final flush or offline history is not claimed recovered.
- Given recurring enrollment trials, when their outcomes are reported, then administrator setup is measured separately and failures, manual steps and help remain visible for both projects; Notion write success cannot substitute for knowledge/skill delivery proof.

**Tasks:**

- [ ] **OM-08.04-T1** Build and run the four-cell native/T3 project matrix against supported installed versions using safe fixtures before live-content gates.
- [ ] **OM-08.04-T2** Validate authorized Notion, MCP, native skill and telemetry paths separately, retaining redacted capability evidence.
- [ ] **OM-08.04-T3** Verify cross-project denial, revoked source access, withdrawn versions, startup/shutdown losses and repaired configurations.
- [ ] **OM-08.04-T4** Publish contributor instructions and measured recurring setup/readiness outcomes without claiming unverified historical coverage.

## Qualification and source notes

Owner review and A-3's remaining archive/other-record-policy and environment-permission/destination prerequisites remain pending; full conversation capture is the adopted default. Full native scope covers standalone and T3-hosted clients; exact installed versions and fields still require qualification. Cloud orchestration is not silently treated as equivalent to executing-machine standalone/T3 operation.

- [Official Codex hooks](https://learn.chatgpt.com/docs/hooks) documents model-attempt observations, optional token usage, existing-connection MCP behavior and lifecycle limitations. Native hooks must be used observationally here.
- [Official advanced configuration](https://learn.chatgpt.com/docs/config-file/config-advanced) documents opt-in logs and event/metric distinctions; batching and normal-shutdown flush do not establish durable offline delivery.
- [Official configuration reference](https://learn.chatgpt.com/docs/config-file/config-reference) documents independent exporters and content controls. Prompt redaction alone does not remove tool-result snippets or other sensitive fields.
- [Official MCP documentation](https://learn.chatgpt.com/docs/extend/mcp?surface=cli) is the remote-access contract; retrieval alone is not native skill activation.
