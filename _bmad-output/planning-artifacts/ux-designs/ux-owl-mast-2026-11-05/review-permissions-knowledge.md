# Permissions and knowledge lifecycle review — Owl Mast UX

Date: 2026-11-05. Lens: company/project/source boundaries through summaries and counts, notifications, Focus groupings, client aliases, knowledge search, receipts, evaluation, promotion, version changes, withdrawal, and usage/cost aggregation.

Read: `review-brief.md`, `EXPERIENCE.md`, `DESIGN.md`, `.memlog.md`, `.working/source-prd.md`, the finalized `prd.md`, `review-access-knowledge.md`, `reconcile-prd.md`, the Focus, knowledge, connections, and work/usage study notes, and all ten surface mockups (their text and inline fixture scripts; `gallery.html` was not inspected separately). Line numbers are as read on this date. The private sample in `/tmp/owlmast-ux-private` and Notion were not accessed. No target artifact was changed.

## Overall synthesis

**Verdict: the spines are not ready to finalize as permission contracts until the four high findings are fixed. Each needs only a bounded text or state change; none reopens a confirmed choice or requires an architecture selection.**

The spines handle the obvious boundaries well: no cross-project fallback, neutral unavailable states, fail-closed authorization, push disclosure checks, version-bound approval, and honest limits on recalling delivered copies.

The remaining defects sit where a generic rule ("count authorized data only", "subject to permissions") meets a specific case the contract never resolves:

- A permission-filtered total has to be truthful without revealing what was filtered.
- A project-scoped lesson can derive from a source record that only some project members can read.
- A company publication's reader in another project has no defined view of it.
- Withdrawn content has no defined state on human-read surfaces.

These matter because PRD SM-5 makes any boundary failure block pilot acceptance. They are planning defects: an implementer following the current text could comply and still leak or mislead.

| Severity | Count | IDs |
|---|---|---|
| Critical | 0 | — |
| High | 4 | PK-1 to PK-4 |
| Medium | 12 | PK-5 to PK-16 |
| Low | 5 | PK-17 to PK-21 |

**Preserved as given, not challenged:** agent-initiated on-demand search (UX-08), every-observed-update push (UX-10), project-designated maintainers (UX-09), preferred automatic company-safe promotion with manual and disabled modes, and A-1 to A-6 with their exact text, owners, and revisit points. Where a fix touches an assumption, it adds a state and leaves the assumption open. Mockup findings concern what the references depict. All mock data is illustrative and is not treated as integration evidence.

## High

### PK-1 — Permission-filtered totals must either look complete or reveal that records are hidden

**Location:** `EXPERIENCE.md:85` (`work-summary`: "Count authorized data only; show partial coverage"), `:111` (no hidden-source counts), `:117`, `:156` (incomplete child scope "prevents a complete-looking rollup"), `:260` ("never reveal hidden titles or counts"). `DESIGN.md:157–159`, `:164`. `mockups/daily-work.html:210`, `mockups/focus.html:237`, `mockups/usage.html:124`. Source: PRD FR-6 line 108, NFR-1 line 249, NFR-2 line 250.

**Evidence:** The contract requires partial coverage to show and also forbids disclosing hidden records, but never says how both hold when the partiality comes from permissions. The references differ:

- Daily Work states an absolute: "Denominator: five tickets in this epic", under "Your owned scope".
- Focus says "permitted epic tickets", but only inside a collapsed disclosure, and its visible label is "Epic: 3/5 tracker-closed".
- Usage places "only permitted … records" inside a collapsed disclosure.

**Impact:** A viewer who cannot read 3 of 8 child tickets sees "5 of 5 child tickets closed", an apparently finished epic. If an "incomplete" label appears only when something is actually hidden, that label itself discloses hidden records. SC-1's climax ("can explain what is closed") then fails silently, and two viewers get different figures with no signal why.

**Minimal fix:** Add one rule to `work-summary`, `epic-group`, and `usage-breakdown`:

- Every aggregate carries a constant, always-visible basis label, such as "Counted from records you can access". It appears identically whether or not anything is hidden, so it reveals nothing and never implies a whole-source total.
- A permission-scoped rollup never presents as "all closed" or "complete" without that label.
- Source-collection gaps (FR-3) keep their own conditional "incomplete" label, separate from this basis label.
- Search omission notices (`:160`) count only eligible results that were truncated, never results filtered out by permission.
- Change the Daily Work denominator copy to match.

### PK-2 — A project-scoped lesson has no reader check when it derives from restricted same-project material

**Location:** `EXPERIENCE.md:160` (project scope; "permitted references"), `:95`, `:114` ("no inaccessible origin excerpt"), `:98`, SC-2 `:213–216`. `mockups/knowledge-detail.html:38`, `mockups/knowledge.html:42`. Source: PRD FR-17 lines 209–211, FR-21 line 244, FR-12 line 161.

**Evidence:** The contract gates excerpts and references, not the lesson itself. S4's mock says "Visible in Syntelligence · Original source access is checked separately", and S3's says "Source access is required to inspect the supporting record", so the body's visibility is decided at project level. The restricted-content checks in FR-12 apply only to company promotion. Nothing equivalent applies when Hermes or Notion capture produces a project lesson from a restricted Jira record or a narrowly shared Notion page.

**Impact:**

- SC-2's Mohamed → Ahmed path can deliver restricted text to a same-project agent, or show it in S3. This is the FR-17 case of a same-project user lacking source access, reached through a derivative rather than a preview. It also covers the case where source permission is removed after indexing.
- Evaluation basis and check-reason text are derived content with the same exposure.
- `promotion-review` is internally unresolved. A maintainer must "inspect exact candidate content", yet "designation does not grant source access". The contract does not say what happens when the candidate contains material that maintainer may not read.

**Minimal fix:** State that project scope is a ceiling, not a read grant.

- A version's title, body, evaluation basis, and check reasons are disclosed, delivered, or returned in search only to a person or agent authorized for the material they derive from, or after a version has been evaluated as safe for the wider project audience.
- If this cannot be determined, withhold the version (fail closed) under the existing S3/S4 and SC-2 failure copy.
- Add an S6 state: "This review needs a maintainer with access to its source." No decision is recorded and the item stays project-scoped.

This keeps the project-default confirmed direction and selects no mechanism.

### PK-3 — A company publication has neither its own identity nor a defined view for readers in another project

**Location:** SC-3 `EXPERIENCE.md:226–229`, `:95`, `:114`, `:162`. `DESIGN.md:167`, `:170`. `mockups/promotion.html:41–42`, `mockups/knowledge-detail.html:39`. Source: PRD FR-12 lines 162–164, A-2 line 172, SM-5 line 278.

**Evidence:**

- S6's "Exact proposed company content" differs from S4's v3 body: it drops "and inspect its reported result" and the third sentence. Yet the record is labeled "Evaluated source version SYN-K07 · v3" and the control says "Approve v3 for this audience". What was approved is therefore not the exact content of v3, despite FR-12's "exact version".
- `knowledge-record` shows evaluator or policy, basis, and origin with no audience distinction, and the ID format embeds the source project key.
- No surface or reference shows SC-3's climax: how a reader or agent in the other project sees the published item.

**Impact:** A Movesion reader of the published item could see "SYN-K07", Syntelligence's evaluator, a basis describing source records, and lineage. All of that is provenance FR-12 reserves for authorized readers. Withdrawal, supersession, receipts, and reuse also have no unambiguous version to attach to, and A-2's "promoted derivatives" has no representation.

**Minimal fix:**

- Define a publication as its own versioned record: publication ID without the source project key, exact text, audience, policy version, publishing person or automation identity, and a restricted reference to the originating version.
- Bind approval and automatic evaluation to that record, and relabel the control to approve that publication version.
- Add a "company reader" field list to S4: content, publication version, company scope, applicability, freshness, and evaluated-by-policy or reviewed-by-person kind. Origin project, source ID, named evaluator, basis, and other projects' receipts appear only to authorized readers.
- Add a visual reference for this state. Whether the published text may differ from the source is a product detail; if it may, the record above carries it.

### PK-4 — After withdrawal, human-read surfaces can keep showing the withdrawn content

**Location:** `EXPERIENCE.md:114` ("Conflicting/superseded/withdrawn … content carries lifecycle state"), `:162`, `:229`, `:96`, `:94`, J7 `:247`. `mockups/daily-work.html:272`, `:287`. No reference shows a withdrawn state (zero occurrences of "withdrawn" in `knowledge.html`, `knowledge-detail.html`, `daily-work.html`, `notifications.html`). Source: PRD FR-13 lines 170–174, FR-18 line 218.

**Evidence:** The withdrawal contract covers future agent delivery and external copies. For Owl Mast's own surfaces, the only statement is that content "carries lifecycle state", which reads as still displayed with a label. Feed rows embed the lesson title ("Stable account identifiers · v3"), and S9's return can land on S4.

**Impact:** Take an automatically published version withdrawn because its text exposed a customer detail. Former-audience readers can still read the title or body through S3, S4, S6 history, feed rows, and old notification links. That contradicts FR-18 ("cannot leave excluded content in snippets, caches, exports, or derived summaries"). Separately, a receipt for that version keeps looking healthy, so a recipient cannot tell that guidance they received has since been withdrawn.

**Minimal fix:** Add a post-withdrawal row covering S3, S4, S6, the activity feed, notification return, and receipts:

- Former-audience readers see the lifecycle state, plus a neutral reference when the withdrawal reason concerns safety or permission, without the body or title.
- Authorized maintainers or auditors see the audit record.
- Feed rows and receipts for that version show "since withdrawn" or "since superseded".
- Superseded content may stay readable.

Keep A-2's exact retention and retrieval default open, with this as the state contract it resolves.

## Medium

### PK-5 — A generic push can still reveal a restricted update, and the "non-generic" preview is undefined

**Location:** J7 `EXPERIENCE.md:245–246`, `:250`; `mockups/notifications.html:10`. Source: NFR-1 line 249, FR-18 line 218.

**Evidence and impact:**

- "Rights are checked before any notification disclosure" can be read as: send "Owl Mast has an update" for every project event and withhold only the detail. The arrival and timing of a push for a record the recipient cannot read is an inference-bearing signal.
- The mock's "Use a generic preview" checkbox implies a richer mode, but no contract defines its content. With every-update push, it could put customer titles on lock screens in copies the spine admits cannot be recalled.

**Minimal fix:** Keep UX-10 and add three rules:

- Push eligibility is evaluated per recipient and per source record at send time, including when the recipient's device session has ended. An unauthorized or unverifiable update produces no push at all, not a generic one.
- This withholding is not throttling or a digest, and the feed follows the same rule.
- Either remove the preview checkbox or list exactly which fields a non-generic preview may carry.

### PK-6 — Receipts have no boundary for colleagues, other projects, or query text

**Location:** `EXPERIENCE.md:96`, `:114`, `:229`; `DESIGN.md:168`; `mockups/knowledge-detail.html:44`; `mockups/daily-work.html:287`. Source: FR-11 line 152, FR-13 line 170, A-3 line 217.

**Evidence and impact:**

- SC-3 asks maintainers to see earlier deliveries "subject to permissions", but no state exists for recipients outside the maintainer's access. They either see cross-project recipients or get no sense of withdrawal impact.
- The mock adds "Requested context: Syntelligence Jira · SYN-42 · Check review", beyond FR-11's recipient, project, item/version, and time. For a cross-project delivery, this would show one customer's work to another project's maintainer.
- On-demand search also creates a new data flow, agent query text, whose retention and visibility are undefined.
- Daily Work's "A sync lesson reached Eagle" shows a colleague's receipt with the lesson title, with no stated link to S4's separate recipient-visibility check.

**Minimal fix:**

- Apply `delivery-receipt` visibility wherever a receipt appears, including feed rows and push.
- Requested context and query text are gated to the recipient's project access. Their retention is undecided, so mark it [OPEN] under A-3 rather than implying they are stored.
- Add a state showing the maintainer a neutral statement that deliveries outside their access exist under the publication's permitted audience, without identities or task context. The publication's audience is already known to its maintainer, so this reveals nothing new.

### PK-7 — Personal aliases are undefined for other people's agents, and the references contradict the personal scope

**Location:** `EXPERIENCE.md:90`, `:166`; `DESIGN.md:162`. `mockups/daily-work.html:241`, `:287`; `focus.html:210–213`; `connections.html:10`; `administrator-setup.html:10`; `work-detail.html:143`; `knowledge-detail.html:42`, `:44`; `usage.html:118–119`.

**Evidence:** The contract says aliases are per-viewer preferences, and DESIGN says "User-chosen owl display name". It does not say what a chip shows for an agent the viewer did not name, or whose clients S5 lists. The fixtures show one alias on different agents and people:

| Alias | Depicted as |
|---|---|
| Eagle | Ahmed-initiated Movesion run CX-4 in Focus; Mohamed's Syntelligence Codex session in Daily Work |
| Barn | Movesion client in Connections and Focus; Mohamed's Syntelligence Claude in Daily Work |
| Tawny | Ahmed's CL-17 in Focus and Usage; Mohamed's CL-21 in Work Detail; Mohamed's contributor agent in Knowledge Detail |

S8 also shows contributors' aliases to an administrator, and alias text is embedded in feed titles.

**Impact:** If one person's alias renders for another viewer, free text from one person crosses audiences, and the same name can point to different agents. Evidence reading then becomes unreliable (FR-4). Implementers would also have to guess the shared-naming authority the spine leaves unspecified.

**Minimal fix (designer proposal, no shared-naming decision):**

- A viewer sees only their own alias for a client. Otherwise the chip shows the fixed type label plus a stable short identifier.
- Another person's alias is never rendered in S1–S10, push, receipts, or audit.
- Alias settings list only clients the viewer may currently see, and drop out when access is revoked.
- Keep S5 scoped to the viewer's own clients unless a separate shared-workspace view is defined (FR-15).
- Correct the fixtures so each alias names one client throughout.

### PK-8 — Contextual cost lacks a viewer rule and an epic scope, and its fixtures violate its own attribution rule

**Location:** `EXPERIENCE.md:99`, `:117`, `:120`, `:168`. `mockups/usage.html:118–119`, `focus.html:194`, `:210`, `daily-work.html:210–211`, `:236`. Source: FR-16 lines 197–201, FR-17 line 207.

**Evidence and impact:**

1. S10 applies S1/S2 access to each card, so anyone who can read a ticket gets its cost. No rule says that allocation or bill classes need separate authority, or that a share of a company-wide subscription could let a viewer infer the other project's share by subtraction. S7's residual rule isn't stated for allocation bases.
2. Focus's epic cost doesn't say whether it covers the whole permitted child set or only the viewer's assigned subset, though Focus distinguishes those for closure counts.
3. False state: Focus and Daily Work show SYN-42 as "Usage & cost: Unavailable … No linked usage records", while S7 shows SYN-42 with 0.60M tokens and $3.60 from an "explicit session work reference" on the same date.
4. False state: S7 assigns all of CL-17's session to SYN-42, while Focus says that one session links both SYN-42 and SYN-67. Under `:99`, "ambiguous allocation stays unassigned". S7 also assigns SYN-67 to Mohamed's Snowy CX-16, while Focus links it to Ahmed's CL-17 and Daily Work calls it "Define project sync rules".

**Minimal fix:**

- Contextual summaries show only classes the viewer may see in S7.
- Allocation or bill figures never expose a basis from which an inaccessible share can be derived.
- Each epic amount names its record set.
- Align the three references: one illustrative SYN-42 state and an unassigned or explicitly split shared session.

### PK-9 — The "Shared run" label and its evidence text can reveal hidden work

**Location:** `EXPERIENCE.md:92`, `:256`, `:260`; `DESIGN.md:164`; `mockups/focus.html:210`, `:223`, `:234`.

**Evidence and impact:** A "Shared" marker and "One confirmed session links SYN-42 in SYN-10 and SYN-67 in SYN-20" assume the viewer can see both sides. For a viewer with only SYN-10, the marker reveals another linked item and the text names it. The rule at `:260` covers hidden titles and counts, not this label or a run linked across projects.

**Minimal fix:** Show the marker, references, and shared-run labels only for links the viewer can read; otherwise render the run as an ordinary run. A run's other-project links never appear in the other project's scope. Deduplicated totals count only records the viewer can access.

### PK-10 — Maintainers own exceptions, but the exception has no resolution path

**Location:** `EXPERIENCE.md:40`, `:53`, `:227`, `:232`; `mockups/promotion.html:41`. Source: UX-09, FR-12 line 161.

**Evidence and impact:** The mock tells the maintainer to "Confirm permitted company use before evaluating this version again", and also that "A human decision cannot bypass the required checks". Nothing says where that confirmation is recorded, who may give it (the maintainer or a project data owner), or what outcomes exist. The confirmed exception-handling job therefore has no defined action. Under the preferred automatic mode, this is the main human touchpoint. A version whose lineage carries a withdrawal also needs a defined outcome. Without one, implementers may build an override, which the spine forbids, or a dead end.

**Minimal fix:** Enumerate exception outcomes on `promotion-review`:

- Keep project-scoped with a recorded reason.
- Correct the content, creating a new version that gets a new evaluation.
- Request re-evaluation after the missing permission or policy input is recorded by its authorized owner.

Mark the owner of the use-permission input as [OPEN] instead of implying it is the maintainer.

### PK-11 — The required quarantine state is missing from the lifecycle model

**Location:** `EXPERIENCE.md:53`, `:114`, `:160`, `:230`, `:270`; `DESIGN.md:167`; zero occurrences in `knowledge.html`, `knowledge-detail.html`, and `promotion.html`. `reconcile-prd.md:25`. Source: FR-13 line 170, SM-5 line 278.

**Evidence and impact:** FR-13's system quarantine is a requirement outside A-2. A-2 only proposes its effects. The spine's lifecycle list omits quarantined, S4 has no state for it, and no maintainer path or actor record exists. Reconciliation filed it entirely under A-2. SM-5 tests quarantine blocking new delivery, and a system-initiated change with no surface would look like silent disappearance.

**Minimal fix:** Add **Quarantined (system-initiated, with reason and time)** as a distinct state in Knowledge semantics, `knowledge-record`, S3 filters, S4/S6 states, and the maintainer exception view. Leave its exact retrieval effects to A-2.

### PK-12 — Withdrawal and receipts don't disclose independent Notion or client access

**Location:** `EXPERIENCE.md:96`, `:114`, `:162`, `:229`; `mockups/knowledge-detail.html:44`. Source: FR-17 line 211, FR-21 line 245.

**Evidence and impact:** The spine discloses the limit on "earlier copies" but not ongoing independent access: a client with its own Notion access can still read the source page after an Owl Mast withdrawal, and that read produces no receipt. So "withdrawn" can be taken to mean no agent can get it now, and "no deliveries" can be taken to mean nobody read it. The PRD requires these limits to be reported separately.

**Minimal fix:**

- Label withdrawal outcomes "Owl Mast delivery stopped" and add one line noting that direct source or client access is governed separately.
- Label receipts as covering Owl Mast-mediated delivery only, so "No deliveries" isn't read as no reads.
- Whether a withdrawal should also change the Notion page stays with the implementation design, per FR-14.

### PK-13 — Attention items assume captured session text, which the A-3 default wouldn't collect

**Location:** `EXPERIENCE.md:86`, J1 `:185`; `mockups/daily-work.html:264`, `:279`. Source: A-3 line 217, FR-7 line 116.

**Evidence and impact:** J1 has Ahmed "read the request", and the mock shows a body taken from a "linked Claude session", including for Mohamed's work. A-3's proposed default collects metadata, references, and deliberately submitted knowledge, with raw chat needing explicit enablement. No state covers that default, so building the shown body presumes the unresolved answer, and colleagues read session content before data owners decide.

**Minimal fix:** Add an attention and S2 state: "Request text isn't collected under this project's policy", showing reason, source, time, and the source link (all FR-7 needs). Show captured text only where policy permits. Keep A-3 open.

### PK-14 — Duplicate and conflict references are a side channel

**Location:** `EXPERIENCE.md:95` ("Duplicate detection links to existing lineage"), `:51`, `:214`. Source: FR-8 line 130, FR-9 line 137.

**Evidence and impact:** Submitting a lesson that matches a restricted item, or an item in another project, would return a link or a "duplicate" result that confirms the item exists. Conflict exposure has the same risk if the conflicting version isn't visible to that recipient. FR-9's exposure duty has no stated scope limit.

**Minimal fix:**

- Readers and agents see duplicate or conflict references only for versions they can access.
- For anything else, the submission records neutrally ("Saved as a candidate") and the match is routed to an authorized maintainer.
- Two projects' private items are never compared in anything shown to a reader.

### PK-15 — "Assigned to me" has no identity-mapping guard or state

**Location:** `EXPERIENCE.md:44`, `:91`, `:120`, `:193`, `:254`. Source: FR-1 line 65, FR-4 line 93.

**Evidence and impact:** Focus and the S1 person filter need one person's identities across two Jira sites, but no contract says how assignment is established. S10 has only "No assignments" as an empty state. An unmapped identity would give a false "nothing assigned" on the page meant to show parallel work, and matching by display name could show another person's work, which FR-1 explicitly rejects.

**Minimal fix:** Attribute assignment only through a source-provided identity or confirmed mapping, never a display-name match. Add a per-source S1/S10 state: "Your identity in this source isn't confirmed; assigned work may be missing." The mapping mechanism stays with architecture.

### PK-16 — Reuse verification has no actor, action, or boundary

**Location:** SC-2 `EXPERIENCE.md:218`, `:96`, `:114`; `mockups/knowledge-detail.html:44`. Source: FR-11 line 153, A-6 line 276.

**Evidence and impact:** "Only then record demonstrable reuse" names no verifier or surface, and `delivery-receipt` has no write action. SM-3's proof therefore can't be recorded from this contract. In the SC-3 case, the task artifact lives in the recipient project, so attaching it to the origin project's S4 would expose it to that project's maintainers.

**Minimal fix:** Define a permitted action on the receipt: an authorized reviewer records verified reuse with the version, artifact reference, and time. The artifact reference is visible only to readers with access to its project; origin-project readers see only "Reuse verified in a permitted project". The sample size stays A-6.

## Low

### PK-17 — Focus opens with a cross-project aggregate, against the IA's default

**Location:** `EXPERIENCE.md:44`, `:254`; `mockups/focus.html:173`, `:216`.

The IA says company context is explicitly selected, "not an automatic cross-project default". Focus defaults to "Both permitted projects". It is labeled and contains only authorized data, so this is a contract inconsistency rather than a leak. **Fix:** state explicitly whether Focus is a deliberate exception for the concurrent-work need, or start it from the restored project.

### PK-18 — Reference copy departs from the safe patterns the spine defines

**Location and fix:**

- `mockups/usage.html:124` names Movesion and its tools on a Syntelligence-scoped screen, against `EXPERIENCE.md:63`. Remove it, or render it only for viewers authorized for both.
- `mockups/notifications.html:10` adds "Its current access could not be verified" to the neutral message, which differs from a missing item. Use the single copy at `EXPERIENCE.md:73`.
- `mockups/knowledge.html:43` omits a scope marker on candidate SYN-K12, against `DESIGN.md:167`. Add one.
- `mockups/knowledge-detail.html:44` merges "Retrieved and delivered" on one row, though its timestamps differ. Show separate rows, per `EXPERIENCE.md:96`.

### PK-19 — One source failure is shown as a single client's state

**Location:** `mockups/connections.html:10`, `administrator-setup.html:10`, `focus.html:223`; `EXPERIENCE.md:115`.

S8 shows the Movesion Jira authorization as expired at the source level. S5 shows only Barn affected and withholds its knowledge because "source access cannot be verified", while Eagle in the same project shows healthy observation with only "Not verified". Focus's Movesion cards say "Source observed 08:42", while S5 and S8 show that Jira's last success was 07:55. **Fix:** show the shared source failure on both Movesion clients, apply the withholding consistently where it depends on that source, and label Focus's snapshot accordingly.

### PK-20 — Administrator authority isn't scoped to a project

**Location:** `EXPERIENCE.md:55`, `:118`; `mockups/administrator-setup.html:10`. Source: FR-18 line 215.

"Only authorized administrators" and a single two-customer page can be read as company-wide administration. **Fix:** S8 lists only projects the viewer administers, and another project's site, repository, and client identities don't appear. The mock remains valid for someone who administers both.

### PK-21 — Enabling automatic mode and the successful-publication path aren't shown

**Location:** `EXPERIENCE.md:100`, `:230`; `mockups/promotion.html`. Source: FR-12 lines 164–165.

SC-3 step 7 covers switching away from automatic. It doesn't cover switching to it, which evaluates existing candidates and may publish many under the preferred mode. References show only withheld and pending-manual states. **Fix:** make the mode-change confirmation state that existing candidates will be evaluated and name the audience. Add one reference for a published-by-policy record showing the automation identity and policy version.

## Explicit nonblocking dependencies

These are implementation validations or open decisions, not UX contract defects. They should not delay finalization once the findings above are resolved.

| Dependency | Owner / gate |
|---|---|
| Actual source record-level permission and identity data for both Jira sites, GitHub, and Bitbucket; connector ability to evaluate per-reader access | Architecture/integration; connector feasibility (PRD line 318) |
| Revocation propagation through indexes, caches, derived content, and aliases; FR-17 negative cases in both directions | Architecture; SM-5 acceptance |
| Push platform, payload handling, delivery limits, and subscription lifecycle | Architecture; packaging decision |
| Notion and client permission boundaries, skill reading, and Hermes sync ownership; the current unverified state remains as written | Implementation design; FR-14, FR-21 |
| Client cache behavior and how recipients recognize withdrawn versions | Delivery contract; FR-13, NFR-4 |
| Availability of model, session, and work attribution; pricing, allocation, and billing sources | Integration; SM-C4 |
| A-1 to A-6 | Stated owners and revisit points, unchanged |
| Owner of the permitted-use input for promotion checks; shared alias naming authority | Open questions, labeled in PK-10 and PK-7; not user preferences |
| Real-data sample: Jira and Bitbucket access not established | Separate from this review; not inspected, and not evidence for or against any finding |

## Checked with no finding

- No cross-project search fallback or default company scope in S3 or SC-2 (`:113`, `:220`), and empty results are separated from authorization failure.
- Neutral unavailable behavior, fail-closed authorization, and reconnect rechecks in the S1–S10 baseline (`:107`).
- Project-designated maintainers don't gain source access, and mode doesn't widen source permissions (`:98`, `:162`).
- Failed or uncertain checks stay project-scoped (`:227`). Changed versions or policies invalidate pending decisions (`:116`, `:230`). A-4 isn't presented as settled.
- Available, retrieved, delivered, and reused stay distinct at the contract level, and reading isn't treated as use (`:96`, `:160`).
- Measurement classes, currencies, unassigned and unpriced portions, and the absence of productivity scoring (`:99`, `:164`, `mockups/usage.html`). Estimate arithmetic in the S7 fixture reconciles.
- Aliases are stated not to merge records, change permissions, or rename source objects, and S4 keeps stable recipient identity (`:90`, `mockups/knowledge-detail.html:44`).
- No agent execution, reassignment, status mutation, or reply controls in any reference. Illustrative labels are present, and Notion skill reading is kept unverified.
