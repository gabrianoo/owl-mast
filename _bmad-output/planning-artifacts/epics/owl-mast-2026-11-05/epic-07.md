---
epic: E07
status: planned
review_status: pending-owner-review
implementation_status: not-started
---

# Epic E07 — Use Claude Code with Owl Mast in every supported execution mode

Claude Code users retrieve authorized knowledge and report supported lifecycle, usage and knowledge-use evidence from the executing machine, both standalone and within T3. Both modes are full planned scope; T3 enrichment is optional and cannot replace native integration qualification.

**Epic prerequisites:** E06

<a id="om-07-01"></a>

### OM-07.01 — Package and qualify native Claude integration

As a contributor, I want a versioned Claude package and configuration tied to my enrollment, so that I can use Owl Mast without replacing my existing client setup.

**Requirements:** FR-2, FR-3, FR-18, FR-19, FR-21; NFR-5, NFR-6; AR-14, AR-18, AR-19; UX-DR22, UX-DR33, UX-DR54, UX-DR59

**Depends on:** E06

**Acceptance criteria:**

- Given a supported enrolled Claude version, when the package is configured, then it adds direct Owl Mast MCP/hook/OTLP configuration on the executing machine using secret references, preserving unrelated servers, hooks, skills and user settings.
- Given standalone and T3-hosted modes, when qualification runs, then a versioned matrix records effective configuration and observed support for each required field/signal in both modes; T3 passthrough is verified rather than inferred from upstream documentation.
- Given an unsupported version, conflicting setting or unavailable credential, when setup runs, then it leaves a recoverable state with a precise safe explanation instead of silently overwriting settings, granting execution permissions or reporting ready.
- Given the adopted full-conversation default, when the package is qualified, then synthetic content fixtures verify capture and project opt-out settings; live export still requires the remaining project archive/other-record-policy and destination/permission prerequisites. Missing or truncated content is reported rather than presented as complete history.

**Tasks:**

- [ ] **OM-07.01-T1** Define the supported Claude versions/modes and package manifest, configuration merge/repair contract and owned-file inventory.
- [ ] **OM-07.01-T2** Build the native package/configuration integration with enrollment-bound credentials, secret references and reversible preservation of existing settings.
- [ ] **OM-07.01-T3** Qualify actual standalone and installed T3 execution paths for MCP availability, hooks, exporter settings, supported fields and credential handling.
- [ ] **OM-07.01-T4** Add setup failure/repair checks and document transport reachability and native offline-buffering limits without installing a mandatory daemon.

<a id="om-07-02"></a>

### OM-07.02 — Deliver exact knowledge and native skill packages to Claude

As an enrolled Claude user, I want scoped memory and complete skills available through native mechanisms, so that I can continue useful work without a manual recap.

**Requirements:** FR-10, FR-11, FR-17, FR-21; NFR-1, NFR-4, NFR-5; AR-06, AR-14, AR-15, AR-16, AR-19; UX-DR21, UX-DR33, UX-DR48, UX-DR50

**Depends on:** OM-07.01

**Acceptance criteria:**

- Given a selected authorized project, when Claude chooses to search through MCP, then it receives bounded summaries and exact-version references, followed by selected content only on explicit load; validated-only is the default and the client must explicitly opt in to labelled unvalidated candidates. No session/turn/work-update trigger injects full lesson content without a client request, and denied/empty results do not fall back to another customer's knowledge.
- Given a compatible skill package, when the native package installs or refreshes it through the authorized local mechanism, then manifest paths/checksums and required references/assets are preserved; a Markdown search result alone is not reported as native installation or activation.
- Given existing authorized Notion page creation and memory workflows, when Owl Mast is enabled, then those flows continue without duplicate saves or authority transfer; Notion-backed skill reading and native activation are verified separately.
- Given revocation, withdrawal, a checksum mismatch or unavailable eligibility verification, when an Owl Mast-managed retrieval, delivery, materialization or refresh is attempted, then it is withheld or fails safely and records an accurate outcome; independent loading of retained local packages and already delivered session context remain outside server enforcement unless a specific native interception capability has been separately qualified.

**Tasks:**

- [ ] **OM-07.02-T1** Implement the Claude MCP knowledge adapter and project-context selection using existing authorization and versioned knowledge contracts.
- [ ] **OM-07.02-T2** Implement qualified native skill-package materialization/refresh with manifest validation, ownership boundaries and explicit eligibility/cache behavior.
- [ ] **OM-07.02-T3** Preserve and verify authorized Notion creation/read paths independently of Owl Mast knowledge receipts and native skill activation.
- [ ] **OM-07.02-T4** Verify client-driven bounded search/selected load, validated default and explicit unvalidated opt-in in both modes, plus empty/denied/conflicting results, package corruption, withdrawal, interrupted delivery and receipts; no unsolicited lesson injection or inference that managed revocation prevents independent use of retained copies.

<a id="om-07-03"></a>

### OM-07.03 — Send Claude observations directly without controlling execution

As an authorized viewer, I want Claude's native observations connected to its work context, so that I can inspect supported run and usage evidence without giving Owl Mast execution authority.

**Requirements:** FR-4, FR-11, FR-16, FR-18, FR-19; NFR-2, NFR-3, NFR-6; AR-14, AR-15, AR-16, AR-17, AR-18; UX-DR21, UX-DR46, UX-DR47, UX-DR50, UX-DR54

**Depends on:** OM-07.01

**Acceptance criteria:**

- Given an enabled native integration, when a supported lifecycle/tool/knowledge event occurs, then observational hooks and OTLP exporters send directly to Spring with available session/prompt/tool/request correlation; no T3 relay, agent launcher or remote shell is introduced.
- Given separately enabled logs, metrics and traces, when export is configured, then HTTP/protobuf endpoints and authentication are correct, tracing's required native opt-in is explicit, and delta/cumulative metadata is preserved rather than assumed.
- Given permitted model/effort/role/session/location or delegation evidence, when it is mapped, then observed values and timestamps remain separate from configured values; unsupported task attribution or machine identity remains unknown rather than inferred from a shared provider account.
- Given a retrieval, delivery, native skill activation or use claim, when an observation is emitted, then each uses its own evidence type and exact version where known; loading does not prove semantic application or human-verified useful reuse.
- Given Owl Mast is unavailable or an observational hook fails, when Claude continues, then observation does not block, approve, retry or alter its work; missing export coverage is visible and raw prompts/tool content stay governed by A-3 and redaction.

**Tasks:**

- [ ] **OM-07.03-T1** Implement non-controlling lifecycle/knowledge hooks with bounded failure behavior and supported native correlation fields.
- [ ] **OM-07.03-T2** Generate separate log/metric/trace exporter configuration with protocol, endpoint semantics and trace opt-in; apply the adopted prompt/response/tool-content capture default, project overrides and secret exclusions across supported content channels.
- [ ] **OM-07.03-T3** Map Claude events and token categories into E06 contracts, preserving counter windows, cost provenance and capability/version coverage.
- [ ] **OM-07.03-T4** Verify default-on capture and project opt-out, duplicate hook/OTLP evidence, partial/truncated content, shared accounts, redaction, failed connections and uncertain offline delivery; document content gaps explicitly.

<a id="om-07-04"></a>

### OM-07.04 — Prove Claude works across both projects and execution modes

As a pilot contributor, I want verified enrollment, reporting, delivery and repair for every Claude path, so that readiness reflects actual operation.

**Requirements:** FR-2, FR-3, FR-10, FR-11, FR-16, FR-17, FR-21; NFR-1, NFR-3, NFR-4, NFR-5; AR-14, AR-18, AR-19; UX-DR22, UX-DR33, UX-DR46, UX-DR54, UX-DR59

**Depends on:** OM-07.02, OM-07.03

**Acceptance criteria:**

- Given Syntelligence and Movesion in standalone and T3-hosted Claude, when the matrix is exercised, then all four combinations demonstrate permitted knowledge delivery and direct native reporting with field-level outcomes; an unverified cell cannot be marked supported.
- Given supported task/run observations, when qualification examines them, then model, effort, session, role, location and tokens each have a verified source/time or an explicit gap; an unmet required capability remains an unresolved integration issue rather than a completed proof.
- Given a user repairs configuration, rotates/revokes credentials or resumes after disconnection, when the client reconnects, then current authority is checked, unrelated settings survive, replay is not new usage, and unexported history is not fabricated.
- Given a recurring session, when enrollment is measured, then initial administration is separated from recurring steps/time/help; failed attempts remain in the results and successful page creation is not evidence of successful skill reading.

**Tasks:**

- [ ] **OM-07.04-T1** Build the four-cell project/mode qualification procedure and reproducible fixtures, including current installed T3/native versions.
- [ ] **OM-07.04-T2** Exercise real authorized knowledge/reporting paths only after content-policy gates, retaining redacted outcome and capability evidence.
- [ ] **OM-07.04-T3** Validate repair, refresh, rotation, withdrawal, project isolation, revoked access and disconnection behavior in both modes.
- [ ] **OM-07.04-T4** Publish contributor setup/repair instructions and truthful readiness results with recurring enrollment measurements and unresolved gaps.

## Qualification and source notes

Owner review and A-3's remaining archive/other-record-policy and environment-permission/destination prerequisites remain pending; full conversation capture is the adopted default. Full native reporting is planned for both modes; neither mode is deferred. Supported native fields, package behavior and T3 propagation require executed qualification.

- [Claude MCP](https://code.claude.com/docs/en/mcp) documents remote HTTP access; this does not establish skill installation or usefulness.
- [Claude hooks](https://code.claude.com/docs/en/hooks) documents observational mechanisms and failure behavior; a hook is not an offline durable queue.
- [Claude monitoring](https://code.claude.com/docs/en/monitoring-usage) documents independent signals, trace opt-in, temporality and sensitive-content controls. Installation-scoped identifiers and provider accounts do not establish Owl Mast human or machine identity.
