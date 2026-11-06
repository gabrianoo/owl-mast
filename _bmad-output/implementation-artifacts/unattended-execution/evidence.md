# ENG-01 evidence: requirements to evidence (repair round 2, final)

Pull request: https://github.com/gabrianoo/owl-mast/pull/107 (ENG-01 issue #106). Commands ran from the worktree `/home/gabrianoo/.t3/worktrees/owlmast/t3-08a6bd98` (branch `t3/unattended-execution-foundation`, base `c5d9d2eff121423223bf75607c89dd1c55015813`) on 2026-11-06. Nothing below dispatched a product story or mutated backlog progress.

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
| 2 | Exact-commit evidence, SHA-bound approval | `record_head`, `record_review` | `test_review_sha_must_match_head`, `test_new_commit_invalidates_approval` | — | none (fixture only) |
| 2 | Stale revisions and concurrent edits | revision closure at reserve, proposal, resume; explicit rebase | `StaleRevisionTests` (7 cases) | — | none (no owner field is written) |
| 2 | Idempotent retries, duplicate events, stable identity and payload | intents with body and preconditions; exactly-one marker | duplicate claim, transient outage then retry, duplicate marker ⇒ conflict on claim and resume, proposal retry reuses id, replay posts persisted body | `probe-write` on #106 idempotent (`probe-write-4/5`) | none |
| 2 | Partial writes, crash/restart, terminal cleanup | write-ahead intents; terminal phase + intent in one save; validated replays | crash after comment adopted; release failure replayed; crash after terminal save before post recovered; stale proposal replay refused before posting; GitHub regression abandons the proposal | — | none (fixture only) |
| 2 | Reopened issues, review regression (all pages) | `outstanding_objections`, paginated reviews with total/shape checks | reopened dependency/story; per-reviewer objection; objection and dismissal on page 2 through `GhCliTransport`; malformed/drifting/truncated pages refuse; objection on a later page refuses the proposal through the coordinator | — | none (fixture only) |
| 2 | Fail closed on unknown eligibility, denial, outage | error classification; refusals before effects | `DenialOutageAndLiveGateTests`, GraphQL error and shape classification | `probe-write --issue 21` refused | none |
| 2 | Serialization, run binding, environment binding | store lock; `ensure_run` (repo, digest, environment) | interleaved reserve ⇒ `store-busy`; cross-process lock; repo/policy mismatch; fixture state with live transport ⇒ `environment-mismatch` | reserve on the real transport refused before any read (`evidence/live-gate-reserve-refused-2026-11-06.json`) | none |
| 3 | Explicit T3 targets; receipts validated | `receipts.validate_receipt` | 8 receipt cases | this task's own receipt (`evidence/t3-task-receipt-2026-11-06.json`) | a false receipt is not detectable |
| 3 | Admission before delegate; one implementer; no reclaim; worktree identity; resume order | `reserve`/`bind_receipt`; lock; identity before effects | reserve/bind ordering, no reclaim within a run, second run admits after release, identity before resume effects | — | **not qualified with an actual worker** |
| 3 | Checks before review on the actual source | `run_checks`, `_verify_worktree` at review/verdict/proposal gates | full set executed on exact clean HEAD; tree-modifying checks fail; unreported commit or dirt at review admission, verdict or proposal invalidates evidence | — | none (fixture only) |
| 3 | Budgeted repair ≤ 2; no bypass | `repair`, `record_head` refusal | repair-required after failure; cap blocks; budgets | — | none |
| 3 | Cancellation acknowledgement and budget termination | terminal task evidence required while a worker runs; `cancel-run` reports awaiting stories | `test_running_worker_keeps_ownership_until_terminal_evidence` | — | **unmet**: no child deadline/resource bound in T3; protocol not exercised with a real task |
| 3 | No competing bmad-loop runner | design rationale | — | `list_scheduled_tasks` → none; `.bmad-loop/` untouched | none |
| 4 | Minimum permissions; bounded credential | `check_permissions` (`basic_access` observation only) | scope names, push and non-admin never yield `bounded`; unknown scopes not bounded; denial and resource scope recorded untested | live probe: `basic_access` true, `bounded` false, exit 2 | **unmet**: no bounded credential; fine-grained PAT cannot read a user-owned Project (documented); proposals only |
| 4 | Secrets only via supported path | policy loader refusals; output redaction | policy and redaction tests | no token read or stored | none |
| 4 | Probes and check commands; allowlist; budgets; stopping | policy, probes | probe and policy tests | `probe` ok | checks not run through the tool against the real build (no live claim) |
| 4 | No auto merge/deploy/release/live collection | policy refusals; absence test | yes | — | none |
| 5 | Bounded foreground dry run, no product dispatch | — | — | `plan` writes 0; live writes limited to #106 comments; reserve refused live | none |

## Exact commands and results

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
- Round-1 review of b0b5167b (R1-B1–B7, R1-E1–E7, R1-V1–V7): fixed in round 2 as logged in the spec; the unmet requirements above remain blockers, not fixes.

## Unmet requirements and blockers (final)

- **T3 execution protocol not qualified**: reserve-before-delegate, receipt binding and terminal task evidence are implemented and fixture-covered, but no actual bounded worker exercised them, and T3 offers no child deadline or resource bound (`timeoutMs` limits the wait only) nor credential confinement. Smallest verified upstream change: a child deadline that cancels or an equivalent bound. Live execution stays refused.
- **No bounded credential**: the operator token is admin with excess scopes; fine-grained PATs cannot read user-owned Projects (documented limitation); candidate credentials are proposals with qualification steps, none provisioned or tested.
- **Project Status synchronization**: not implemented; owner-maintained.
- Receipt validation trusts the coordinator's report of the `delegate_task` target. Foreign coordinators on other machines are detected, not excluded. Deterministic checks have not run through the tool against the real backend build.

## Candidate first-run activation (blocked)

Policy: `automation/examples/first-run-om-01-02.toml`. Preconditions, all currently unmet: owner sets OM-01.02 to `Ready`; ENG-01 independently reviewed and merged; bounded credential selected, provisioned and denial-tested; T3 protocol qualified with an actual bounded worker including a termination bound; the live gate removed in a reviewed change; `verify-mapping` and `probe` pass on the coordinator machine. OM-01.02's own gates are untouched.
