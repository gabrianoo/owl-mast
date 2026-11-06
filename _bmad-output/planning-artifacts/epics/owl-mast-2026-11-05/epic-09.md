---
epic: E09
status: planned
review_status: pending-owner-review
implementation_status: not-started
---

# Epic E09 — Connect both customer work environments

Teams observe Syntelligence's Jira/GitHub and Movesion's separate Jira/Bitbucket simultaneously, with independently verified editions, authorized resource scopes and recovery. A generic vendor name is not a compatibility claim. Qualification precedes commitment to an edition-specific adapter; both environments remain required scope.

**Epic prerequisites:** E02, E06

<a id="om-09-01"></a>

### OM-09.01 — Qualify actual source editions and permission contracts

As an integration administrator, I want the actual source environments and permitted collection verified, so that connector implementation targets the systems we use.

**Requirements:** FR-1, FR-3, FR-17, FR-18; NFR-1, NFR-2, NFR-6; AR-07, AR-09, AR-10, AR-17, AR-18; UX-DR22, UX-DR36, UX-DR59

**Depends on:** E02, E06

**Acceptance criteria:**

- Given the two customer environments, when qualification completes, then each Jira site's stable identity, hosting edition/version, API/authentication method, account, allowed projects and record restrictions are documented separately alongside the actual GitHub and Bitbucket editions/accounts/repositories.
- Given a proposed connector, when its implementation contract is accepted, then source IDs, pagination/history/deletion visibility, webhook or polling options, rate limits, current-access verification and acceptance/progress evidence capabilities have qualified evidence; unknown edition or permissions block adapter commitment rather than being guessed.
- Given shared external credentials, when source access is evaluated, then the contract distinguishes connector reach from each Owl Mast person's permitted records; a source that cannot prove current access fails closed and exposes a gap rather than relying on project membership alone.
- Given missing project data-owner approval or unresolved archive/other-record/removal policies and processing destinations under A-3, when live collection is requested, then it stays gated; qualification uses safe samples and does not authorize customer ingestion implicitly.
- Given an edition-specific obstacle, when findings are recorded, then the required Movesion/Bitbucket or separate-Jira work stays visible with a bounded resolution task instead of being replaced by a GitHub-only demonstration.

**Tasks:**

- [ ] **OM-09.01-T1** Inventory both Jira sites and the actual GitHub/Bitbucket instances with source-qualified identities, versions, owners and permitted resource selections.
- [ ] **OM-09.01-T2** Qualify authentication, user/source entitlement, revocation and restricted-record behavior using approved minimal probes or redacted fixtures.
- [ ] **OM-09.01-T3** Record edition-specific event/history/pagination/limit capabilities and accepted connector contracts before implementing the provider adapters.
- [ ] **OM-09.01-T4** Record A-3, retention/removal and destination decisions as live-ingestion gates with unresolved items and owners; keep secrets in protected configuration only.

<a id="om-09-02"></a>

### OM-09.02 — Observe both qualified Jira sites independently

As a project lead, I want work evidence from each customer's Jira, so that identical issue keys and different site behavior do not mix projects.

**Requirements:** FR-1, FR-3, FR-5, FR-6, FR-17, FR-18; NFR-1, NFR-2, NFR-3, NFR-4; AR-07, AR-11, AR-17, AR-18; UX-DR22, UX-DR36, UX-DR43, UX-DR45, UX-DR59

**Depends on:** OM-09.01

**Acceptance criteria:**

- Given both qualified Jira connections, when authorized records synchronize, then site-qualified stable issue IDs, display keys, project, original status, assignments, epic membership, supported criteria/progress and explicit relationships retain provenance and source time independently.
- Given changes, reopened criteria, issue movement or a restricted/deleted record, when evidence updates, then history/corrections and safe current visibility follow the qualified source semantics; a not-found response does not automatically prove deletion.
- Given repeated webhook delivery, incomplete pagination or interrupted polling, when collection resumes, then durable checkpoints and reconciliation recover supported records without duplicate facts or a false complete-history claim.
- Given token expiry, rate limiting or one unavailable Jira site, when the other project is used, then it remains available with its own health; unauthorized fields, counts and links are not disclosed through shared credentials.
- Given source closure or a measurable criterion count, when normalized, then closure and the labeled progress basis remain separate from acceptance, merge or deployment.

**Tasks:**

- [ ] **OM-09.02-T1** Implement the qualified Jira edition adapter or adapters for both sites behind source ports, with independently scoped secret references and configuration.
- [ ] **OM-09.02-T2** Collect supported issue/history/criteria/relationship evidence using bounded pagination and authenticated webhooks or qualified polling.
- [ ] **OM-09.02-T3** Implement checkpoints, rate-limit handling, incremental reconciliation and source-access refresh without direct tracker mutations.
- [ ] **OM-09.02-T4** Verify colliding keys, record restrictions, source permission removal, reopened progress, pagination interruption and isolated site failure.

<a id="om-09-03"></a>

### OM-09.03 — Observe Syntelligence contributions from GitHub

As a Syntelligence contributor, I want GitHub contribution evidence connected to source-qualified work, so that reviewers can inspect what happened without assuming acceptance.

**Requirements:** FR-1, FR-3, FR-4, FR-5, FR-17, FR-18; NFR-1, NFR-2, NFR-3, NFR-4; AR-07, AR-11, AR-17, AR-18; UX-DR22, UX-DR36, UX-DR45, UX-DR59

**Depends on:** OM-09.01

**Acceptance criteria:**

- Given the qualified GitHub connection and authorized repositories, when collection runs, then commits, pull requests, reviews, check outcomes and available deployment/acceptance references retain stable source IDs, original states, timestamps and permitted navigation links.
- Given a merged pull request or successful check, when evidence is presented downstream, then it remains that specific source fact and does not imply human acceptance, deployment, an independent review or the identity of an initiating person.
- Given webhook replay, missing notifications, pagination interruption or rate limits, when reconciliation runs, then durable source checkpoints and bounded API reads recover supported current/history evidence without inventing unavailable history.
- Given repository scope removal, private records or revoked user/source access, when cached evidence is read or refreshed, then current authorization excludes forbidden content and derivatives; connector credential reach is insufficient to grant viewer access.

**Tasks:**

- [ ] **OM-09.03-T1** Implement the qualified GitHub authentication and repository-scoped read adapter with protected credential references.
- [ ] **OM-09.03-T2** Normalize contribution, review, check and supported deployment/acceptance-reference records with provenance and stable navigation identities.
- [ ] **OM-09.03-T3** Implement verified webhook handling where permitted plus bounded incremental reconciliation, checkpointing and rate-limit/backoff behavior.
- [ ] **OM-09.03-T4** Verify restricted repositories, revocation, duplicates, missing webhooks, renamed repositories and separate merge/check/acceptance facts.

<a id="om-09-04"></a>

### OM-09.04 — Observe Movesion contributions from Bitbucket

As a Movesion contributor, I want equivalent evidence from the actual Bitbucket edition, so that the second customer environment participates fully in Owl Mast.

**Requirements:** FR-1, FR-3, FR-4, FR-5, FR-17, FR-18; NFR-1, NFR-2, NFR-3, NFR-4; AR-07, AR-11, AR-17, AR-18; UX-DR22, UX-DR36, UX-DR45, UX-DR59

**Depends on:** OM-09.01

**Acceptance criteria:**

- Given Movesion's qualified Bitbucket edition/account and selected repositories, when collection runs, then its native stable IDs, commits, pull requests, review/build status and supported deployment/acceptance references map to common evidence without assuming GitHub's API or state semantics.
- Given identical repository names or user display names across providers, when records are ingested, then source namespace and stable identities keep them separate; display names and shared integration accounts do not prove personal authorship or initiation.
- Given unsupported fields or missing historical API coverage, when a record normalizes, then the capability gap stays visible and does not become a fabricated successful check, deployment or acceptance.
- Given duplicate events, interrupted pagination, rate limiting, expiry or revoked access, when recovery runs, then permitted state converges through qualified reconciliation, restricted derivatives remain unavailable and Syntelligence continues independently.

**Tasks:**

- [ ] **OM-09.04-T1** Implement the qualified Bitbucket Cloud or Data Center adapter for the actual installation, authentication and permission model.
- [ ] **OM-09.04-T2** Map native contribution/review/build and supported deployment-reference semantics with source-qualified identities and documented capability gaps.
- [ ] **OM-09.04-T3** Implement approved webhook/poll paths, durable checkpoints, bounded reconciliation and edition-specific rate-limit handling.
- [ ] **OM-09.04-T4** Verify provider/name collisions, denied repositories, permission changes, out-of-order updates and recovery independent of GitHub/Jira availability.

<a id="om-09-05"></a>

### OM-09.05 — Reconcile both environments and explain connection coverage

As an authorized operator, I want consistent health and recovery across the four source connections, so that simultaneous operation remains understandable and safe.

**Requirements:** FR-1, FR-3, FR-5, FR-6, FR-17, FR-18; NFR-1, NFR-2, NFR-3, NFR-4, NFR-6; AR-07, AR-11, AR-17, AR-18; UX-DR22, UX-DR26, UX-DR36, UX-DR43, UX-DR45, UX-DR59

**Depends on:** OM-09.02, OM-09.03, OM-09.04

**Acceptance criteria:**

- Given both customer environments connected together, when an operator inspects them, then account/site, resources, project association, capabilities, cadence, last success, current failure and affected coverage are shown independently with source and collection times.
- Given a gap, reordered updates or changed source permissions, when reconciliation resumes, then checkpoints advance only with durable accepted evidence and current authorization; correction history is preserved and inaccessible historical payloads do not reappear.
- Given a proposed Jira-to-repository correlation, when source evidence is insufficient or ambiguous, then it stays unlinked/inferred with basis rather than becoming an accepted work-to-contribution match; actual acceptance requires its own authority and artifact.
- Given one connection fails or is revoked, when authorized users inspect other connections, then those remain functional; remediation contains no secrets, hidden record counts or unauthorized source text.

**Tasks:**

- [ ] **OM-09.05-T1** Implement unified connection-health/readiness views with independent scopes, selected resources, collection cadence and safe remediation.
- [ ] **OM-09.05-T2** Exercise a cross-provider recovery suite covering webhook gaps, checkpoint interruption, duplicates, reordering and source-access removal.
- [ ] **OM-09.05-T3** Supply E10 with verified source-qualified work/contribution relationships and acceptance references, preserving ambiguous/unlinked records.
- [ ] **OM-09.05-T4** Demonstrate simultaneous two-site Jira plus GitHub/Bitbucket operation using authorized samples after the live-content gates and record remaining coverage gaps.

## Qualification and source notes

Actual editions, site identifiers, scopes and processing permissions are not established by this planning draft. OM-09.01 is a prerequisite to each connector commitment, not a substitute for delivering the four required connections. A-3's full-conversation default is adopted; its remaining archive/other-record-policy and actual-environment permission/destination decisions are required before live customer ingestion.

- [Jira Cloud API](https://developer.atlassian.com/cloud/jira/platform/rest/v3/intro/) and [Jira Data Center API](https://developer.atlassian.com/server/jira/platform/rest-apis/) are separate contracts; pin the qualified installation's version.
- [GitHub API practices](https://docs.github.com/en/rest/using-the-rest-api/best-practices-for-using-the-rest-api) inform event-driven collection, conditional reads and rate-limit handling; reconciliation still needs an explicit coverage contract.
- [Bitbucket Cloud API](https://developer.atlassian.com/cloud/bitbucket/rest/intro/) and [Bitbucket Data Center API](https://developer.atlassian.com/server/bitbucket/rest/) must not be treated as interchangeable.
