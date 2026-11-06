# ENG-01 evidence: requirements to evidence (remediation pass 1)

Pull request: https://github.com/gabrianoo/owl-mast/pull/107 (ENG-01 issue #106). Commands ran from the worktree `/home/gabrianoo/.t3/worktrees/owlmast/t3-08a6bd98` (branch `t3/unattended-execution-foundation`, base `c5d9d2eff121423223bf75607c89dd1c55015813`) on 2026-11-06. Nothing below dispatched a product story or mutated backlog progress.

**Correction of the previous revision of this matrix.** The round-2 matrix marked the crash/restart, cancellation and budget rows as fully covered ("none" unmet, "fixture only"). The final independent disposition of head `a0fa769ee5cd8dfb44fa02cae181bf0d37fad6ee` (PR #107, comment 6686575345) disproved that: six HIGH defects (cancelled run replaying a proposal, rejected implementation proposed on replay, reviewer ownership lost through HEAD recording or invalidation, stranded claim after a crash between intent completion and transition, duplicate stable ids admitted, delegation budget checked only after launch) reproduced against that head. Remediation pass 1 (owner-authorized beyond the exhausted two-round cap) fixes them; the rows below say "fixture-covered, awaiting independent review" rather than "none" wherever that is the honest state, and nothing live-qualifies the execution protocol.

## Columns

- **Code implementation**: the code path exists.
- **Passing fixture coverage**: the scenario is reproduced and its expected refusal or effect asserted in the unit suite (in-memory GitHub, real local git worktree, production transport parser fed realistic responses).
- **Live support**: observed against live GitHub or T3.
- **Unmet requirement**: what is still not met; "none" only when the row is fully covered at the fixture level and nothing live is required by the contract beyond what was observed.

## Requirements-to-evidence matrix

| # | Requirement | Code implementation | Passing fixture coverage | Live support | Unmet requirement |
| --- | --- | --- | --- | --- | --- |
| 1 | Stable E/OM IDs, native relationships, 19/85/340 | `backlog.verify_mapping` | real snapshot fixture passes; negatives: missing parent, wrong parent, duplicate task id, unknown dependency target, missing Project item each named and CLI exit 2 (`RealBacklogNegativeMappingTests`) | `verify-mapping` → ok 19/85/340 (`evidence/verify-mapping-2026-11-06.json`) | none |
| 1 | One writer per field; Done distinct | comment-only transport; no Status/body/close/merge paths | `test_owner_status_is_never_written`, `test_no_merge_status_or_done_write_path_exists`, proposal tests | the only live write is one marker comment on #106 | Project Status synchronization: not implemented (no safe equivalent) |
| 1 | Dependencies, owner gate, scoped exception, E17/E19, strict declarations, explicit COMPLETED | `eligibility.decide`, `backlog.parse_declaration` | 19 eligibility cases incl. malformed/missing/duplicated declarations, unknown epic prerequisites, unknown or non-COMPLETED close reason, reopened, active/blocked | dry run OM-01.02 → `awaiting-owner-acceptance`, writes 0 | none |
| 1 | Unique stable identity | `Snapshot.duplicate_ids`, `decide` → `ambiguous-identity`, `require_unique_ids` before every admitting `by_id` | D5: duplicate in the plan snapshot, only in the fresh read, duplicate epic id, real snapshot with a duplicated id; refused at reserve, resume, propose, rebase with no state and no comment (`test_final_findings.D5*`) | — | fixture-covered, awaiting independent review |
| 2 | Exact-commit evidence, SHA-bound approval | `record_head`, `record_review`, `_require_current_approval` | `test_review_sha_must_match_head`, `test_new_commit_invalidates_approval`; D2: local changes-requested, new head, worktree invalidation and tampered approval/phase/active task each abandon the pending proposal before any PR read; re-approval at the same commit posts once (`test_final_findings.D2*`) | — | fixture-covered, awaiting independent review |
| 2 | Stale revisions and concurrent edits | revision closure at reserve, proposal, resume; explicit rebase | `StaleRevisionTests` (7 cases) | — | none at the fixture level (no owner field is written); no live claim/propose cycle |
| 2 | Idempotent retries, duplicate events, stable identity and payload | intents with body and preconditions; exactly-one marker | duplicate claim, transient outage then retry, duplicate marker ⇒ conflict on claim (resume abandons the claim, posts nothing, stays conflict), proposal retry reuses id, replay posts persisted body | `probe-write` on #106 idempotent (`probe-write-4/5`) | fixture-covered; live only for the engineering-issue probe |
| 2 | Partial writes, crash/restart, terminal cleanup | write-ahead intents; completion + transition in one write; terminal phase + cleanup intent + abandonments in one save; gated and reconciled replays | crash after comment adopted; release failure replayed; crash after terminal save before post recovered; stale proposal replay refused before posting; GitHub regression abandons the proposal; D1: cancel-run/cancel/block with a pending proposal or claim (incl. crash after the terminal save, run cancelled before the story cancel, legacy terminal story with a pending intent) never post an advancing effect; D4: no persisted split state (proved by save spying), crash right after the claim post recovers as `reserved` with one comment, legacy split states reconciled without posting (`test_final_findings.D1*`, `D4*`) | — | fixture-covered, awaiting independent review; no live crash/restart |
| 2 | Reopened issues, review regression (all pages) | `outstanding_objections`, paginated reviews with total/shape checks | reopened dependency/story; per-reviewer objection; objection and dismissal on page 2 through `GhCliTransport`; malformed/drifting/truncated pages refuse; objection on a later page refuses the proposal through the coordinator | — | none (fixture only) |
| 2 | Fail closed on unknown eligibility, denial, outage | error classification; refusals before effects | `DenialOutageAndLiveGateTests`, GraphQL error and shape classification | `probe-write --issue 21` refused | none |
| 2 | Serialization, run binding, environment binding | store lock; `ensure_run` (repo, digest, environment) | interleaved reserve ⇒ `store-busy`; cross-process lock; repo/policy mismatch; fixture state with live transport ⇒ `environment-mismatch` | reserve on the real transport refused before any read (`evidence/live-gate-reserve-refused-2026-11-06.json`) | none |
| 3 | Explicit T3 targets; receipts validated | `receipts.validate_receipt` | 8 receipt cases | this task's own receipt (`evidence/t3-task-receipt-2026-11-06.json`) | a false receipt is not detectable |
| 3 | Authorization before delegate; one implementer; one active task; no reclaim; worktree identity; resume order | `reserve`/`authorize_review`/`authorize_repair` → `bind_receipt`; `active_task`; lock; identity before effects | reserve/bind ordering, no reclaim within a run, second run admits after release, identity before resume effects; D3: same-SHA and new-SHA head recording and invalidation keep the reviewer owned, implementer evidence never releases a reviewer, record-head needs implementer evidence, ownership survives restart, legacy schema refused (`test_final_findings.D3*`) | — | **not qualified with an actual worker**; launches invisible to the tool |
| 3 | Checks before review on the actual source | `run_checks`, `_verify_worktree` at review/verdict/proposal gates | full set executed on exact clean HEAD; tree-modifying checks fail; unreported commit or dirt at review admission, verdict or proposal invalidates evidence | — | none (fixture only) |
| 3 | Budgeted repair ≤ 2; no bypass | `authorize_repair` (round counted at authorization), `record_head` refusal | repair-required after failure; cap blocks before launch; idempotent pending authorization (`D6`) | — | fixture-covered |
| 3 | Cancellation acknowledgement and budget termination | terminal evidence for exactly the active task; `cancel-run` reports awaiting stories; cancelled run refuses advancing operations and replays | `test_running_worker_keeps_ownership_until_terminal_evidence`; D1/D3 scenarios | — | **unmet**: no child deadline/resource bound in T3; protocol not exercised with a real task |
| 4 | Task capacity reserved before launch; no double spend | durable authorizations counted from issue; `bind_receipt` consumes one; budgets derived from story files | D6: exhausted budget refuses reserve/authorize-review/authorize-repair before launch; idempotent authorization; bind twice / without authorization / wrong role refused; corrupted `run.json` counters bypass nothing after restart; unbound authorization stays spent after cancel (`test_final_findings.D6*`) | — | fixture-covered, awaiting independent review; the tool cannot see launches |
| 3 | No competing bmad-loop runner | design rationale | — | `list_scheduled_tasks` → none; `.bmad-loop/` untouched | none |
| 4 | Minimum permissions; bounded credential | `check_permissions` (`basic_access` observation only) | scope names, push and non-admin never yield `bounded`; unknown scopes not bounded; denial and resource scope recorded untested | live probe: `basic_access` true, `bounded` false, exit 2 | **unmet**: no bounded credential; fine-grained PAT cannot read a user-owned Project (documented); proposals only |
| 4 | Secrets only via supported path | policy loader refusals; output redaction | policy and redaction tests | no token read or stored | none |
| 4 | Probes and check commands; allowlist; budgets; stopping | policy, probes | probe and policy tests | `probe` ok | checks not run through the tool against the real build (no live claim) |
| 4 | No auto merge/deploy/release/live collection | policy refusals; absence test | yes | — | none |
| 5 | Bounded foreground dry run, no product dispatch | — | — | `plan` writes 0; live writes limited to #106 comments; reserve refused live | none |

## Exact commands and results (remediation pass 1)

```text
python3 -m unittest discover -s automation/tests -t .          → Ran 170 tests … OK (0 skipped; 33 in test_final_findings.py)
PYTHONPATH=. python3 <scratch probe, old API> on a0fa769e      → all six defects reproduced (evidence/final-findings-repro-before-2026-11-06.txt)
PYTHONPATH=. python3 automation/tests/probe_final_findings.py  → all six scenarios refused or state preserved (evidence/final-findings-repro-after-2026-11-06.txt)
python3 -m automation.unattended --snapshot automation/tests/fixtures/backlog-snapshot-2026-11-06.json verify-mapping   → ok true; 19/85/340; exit 0
python3 -m automation.unattended --snapshot … --policy automation/examples/first-run-om-01-02.toml plan   → OM-01.02 awaiting-owner-acceptance; writes 0
python3 -m automation.unattended --policy automation/examples/first-run-om-01-02.toml --live --run-id eng01-rp1-gate --state-dir <scratch> reserve|authorize-review|bind-receipt|record-task-terminal|resume|cancel-run …
                                                                → every one refused live-execution-disabled before any GitHub read (evidence/live-gate-all-state-commands-refused-2026-11-06.json)
```

Not re-run in this pass (previous observations stand, nothing changed them): `check-permissions` (exit 2, not bounded), `probe`, live `verify-mapping`, `probe-write`. No live write, no credential request, no denial probe, no T3 task launch occurred.

## Exact commands and results (repair round 2, superseded by the above)

```text
python3 -m unittest discover -s automation/tests -t .          → Ran 137 tests … OK (0 skipped)
PYTHONPATH=. python3 <round-1 reviewer scenarios re-run>       → all refused or recovered as required (evidence/reviewer-probes-round1-rerun-2026-11-06.txt)
PYTHONPATH=. python3 <initial reviewer scenarios re-run>       → evidence/reviewer-probes-rerun-2026-11-06.txt (round 1)
python3 -m automation.unattended --snapshot automation/tests/fixtures/backlog-snapshot-2026-11-06.json verify-mapping   → ok true; 19/85/340; exit 0
python3 -m automation.unattended --snapshot … --policy automation/examples/first-run-om-01-02.toml plan   → OM-01.02 awaiting-owner-acceptance; writes 0
python3 -m automation.unattended check-permissions             → basic_access true, bounded false, denial_tested false, resource_scope_verified false, unattended_activation_allowed false; exit 2
python3 -m automation.unattended probe                         → ok true
python3 -m automation.unattended --live --run-id eng01-foundation-2026-11-06 probe-write --issue 106   → comment_existed true, posted null, idempotent true
python3 -m automation.unattended --policy automation/examples/first-run-om-01-02.toml --live --run-id eng01-r2-gate --state-dir <scratch> reserve OM-01.02 --baseline c5d9d2e
                                                                → error live-execution-disabled before any GitHub read; run.json environment "live"
```

`probe-write-1/2-2026-11-06.json` record the superseded first-round design (a Project Status write); that path was removed in round 1 and the files are kept as history only. ENG-01's Status `In review` was set by that removed path; the owner maintains it from here on.

## Review findings by round

- Initial review of 7cb25b25 (B1–B9, E1–E12, V1–V10): fixed in round 1, see the spec's Review Triage Log.
- Round-1 review of b0b5167b (R1-B1–B7, R1-E1–E7, R1-V1–V7): fixed in round 2 as logged in the spec.
- Final disposition of a0fa769e (B1–B3, E1–E5, V1–V3, six defect groups): fixed in remediation pass 1 as logged in the spec's Review Triage Log (entries F-*); awaiting a fresh independent exact-commit review with at most two further repair passes.

## Six defects → fix → evidence (remediation pass 1)

| # | Defect (final disposition) | Fix | Tests (all ran, all pass) | Before / after |
| --- | --- | --- | --- | --- |
| 1 | cancel/block/cancel-run left advancing intents pending; a cancelled run replayed a proposal (`cancelled → proposed`) | `_terminal` abandons pending advancing intents and the pending authorization in the same write as the terminal phase; `resume` abandons advancing intents of a terminal story or a cancelled run; `_require_run_active` refuses every advancing operation on a cancelled run | `D1CancellationAbandonsAdvancingIntents` (6) | scenario 1 |
| 2 | proposal replay ignored current local approval; a locally rejected implementation could be proposed | `record_review` (changes-requested), `record_head` (new SHA) and `_verify_worktree` (invalidation) abandon pending proposals atomically; replay and first attempt require phase `review-approved`, `approved_sha == head_sha == sha`, no active task, before any PR read | `D2ProposalReplayRequiresCurrentApproval` (5) | scenario 2 |
| 3 | `worker_state` flipped by `record-head` (even same SHA); terminal guard picked receipts by phase; reviewer ownership releasable without its evidence | `active_task` (id, role) independent of phase; `_apply_task_evidence` matches exactly that task; `record-head` requires implementer evidence and never touches a reviewer; `record-task-terminal`; schema 2 with strict load | `D3ActiveTaskOwnershipIsIndependent` (6) | scenario 3 |
| 4 | intent `done` saved before the `reserved`/`proposed` transition; `resume` iterated pending intents only | `_post_intent(phase_after)` persists completion and transition in one write; `resume` reconciles done intents without posting | `D4ClaimCompletionIsAtomic` (5) | scenario 4 |
| 5 | duplicate stable ids collapsed by `by_id()` and admitted | `Snapshot.duplicate_ids`; `decide` → `ambiguous-identity`; `require_unique_ids` on the plan snapshot and every fresh read | `D5DuplicateStableIdsAreRefused` (5) | scenario 5 |
| 6 | delegation budget checked at bind/request-review/repair (after launch); counters cached in `run.json` | durable pre-launch authorizations (`reserve`, `authorize-review`, `authorize-repair`), counted when issued, consumed by `bind-receipt`; budgets derived from story files | `D6CapacityIsAuthorizedBeforeLaunch` (6) | scenario 6 |

## Unmet requirements and blockers (after remediation pass 1)

- **Fresh independent review pending**: the fixes above are fixture-covered by this implementer only; the acceptance standard is an independent exact-commit review of the new head, not green tests.
- **T3 execution protocol not qualified**: pre-launch authorization, receipt binding and terminal task evidence are implemented and fixture-covered, but no actual bounded worker exercised them; T3 offers no child deadline or resource bound (`timeoutMs` limits the wait only, never the child's lifetime), no credential confinement, and no launch visibility (the tool bounds what can be bound). Smallest supported next steps: (a) upstream, a child deadline that cancels or an equivalent resource bound; (b) locally, one supervised, separately authorized engineering-only lifecycle (reserve → delegate → bind → terminal evidence → cancel) against the engineering issue with the live gate still in place for product stories. Live execution stays refused.
- **No bounded credential**: the operator token is admin with excess scopes and cannot prove restricted permissions; fine-grained PATs cannot read user-owned Projects (documented limitation); candidate credentials are proposals with qualification steps, none provisioned or tested; no denial probe was run against live resources. Smallest next step: owner selects proposal B or C in `permissions.md`, provisions it through `request_secret` (file delivery), and the read-only `check-permissions` plus the two documented denial checks are recorded.
- **Project Status synchronization**: not implemented; owner-maintained. Owner-only Status updates do not satisfy the automated synchronization requirement; the contract stays unresolved until a safe write path (or an owner decision to keep it manual) is recorded.
- Receipt validation and terminal evidence trust the coordinator's reports of `delegate_task`, `task_status` and `task_cancel` results. Foreign coordinators on other machines are detected, not excluded. Deterministic checks have not run through the tool against the real backend build.

## Candidate first-run activation (blocked)

Policy: `automation/examples/first-run-om-01-02.toml`. Preconditions, all currently unmet: remediation pass 1 passes a fresh independent review; owner sets OM-01.02 to `Ready`; ENG-01 independently reviewed and merged; bounded credential selected, provisioned and denial-tested; T3 protocol qualified with an actual bounded worker including a termination bound and credential confinement; the live gate removed in a reviewed change; `verify-mapping` and `probe` pass on the coordinator machine. OM-01.02's own gates are untouched. `cancel-run`/`resume` remain fixture-covered controls, not approved operational controls.
