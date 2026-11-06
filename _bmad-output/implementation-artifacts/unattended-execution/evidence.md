# ENG-01 evidence: requirements to evidence (repair round 1)

Pull request: https://github.com/gabrianoo/owl-mast/pull/107 (ENG-01 issue #106). Commands ran from the worktree `/home/gabrianoo/.t3/worktrees/owlmast/t3-08a6bd98` (branch `t3/unattended-execution-foundation`, base `c5d9d2eff121423223bf75607c89dd1c55015813`) on 2026-11-06. Nothing below dispatched a product story or mutated backlog progress.

## Status vocabulary

- **implemented**: the code path exists and is exercised by the suite against the in-memory transport and a real local git worktree.
- **fixture-qualified**: the fault scenario is reproduced and refused in the unit suite; the production transport parser is covered with realistic `gh` responses, but no live GitHub or T3 fault was induced.
- **live-verified**: observed against live GitHub or T3.
- **blocked**: the requirement cannot be met with the installed tools or available credentials; live execution stays refused.

## Requirements-to-evidence matrix

| # | Requirement | Fixture evidence | Live evidence | Status |
| --- | --- | --- | --- | --- |
| 1 | Stable E/OM IDs, native relationships, 19/85/340 | `test_backlog.RealBacklogMappingTests` on the real snapshot fixture (declarations all understood) | `verify-mapping` → `ok: true`, 19/85/340, `tasks_index 340` (`evidence/verify-mapping-2026-11-06.json`) | live-verified (read-only) |
| 1 | One writer per field; Done distinct from checks/review/merge | `test_no_merge_status_or_done_write_path_exists`, `test_owner_status_is_never_written`, proposal tests (tasks proposed unchecked, Status untouched) | the only live write is one marker comment on #106 | implemented; Project Status synchronization **not implemented** (no safe equivalent) |
| 1 | Dependencies, owner gates, scoped exceptions, E17/E19 excluded; strict declarations | `test_eligibility` (17 cases incl. malformed/missing/duplicated declarations, unknown epic prerequisites, reopened, not planned, active/blocked) | `plan` dry run OM-01.02 → `awaiting-owner-acceptance`, writes 0 | fixture-qualified; dry run live-verified |
| 2 | Exact-commit evidence, SHA-bound approval | `test_review_sha_must_match_head`, `test_new_commit_invalidates_approval` (real git commits) | — | fixture-qualified |
| 2 | Stale revisions and concurrent edits | `StaleRevisionTests` (Project item, Status, closed story + reopened dependency, dependency body, parent epic, proposal-time change, resume never rebases; explicit `rebase-revisions`) | — | fixture-qualified; no owner field is written, so no race window exists |
| 2 | Idempotent retries, duplicate events, stable operation identity | `test_duplicate_claim_event_posts_one_comment`, `test_transient_outage_on_post_then_retry_has_single_effect`, `test_duplicate_marker_is_a_conflict_on_claim_and_stays_one_on_resume`, `test_proposal_retry_reuses_the_same_operation_identity` | `probe-write` on #106: first run posted `6685915849`, second run `comment_existed: true`, one marker (`probe-write-4/5`) | fixture-qualified; comment idempotency live-verified |
| 2 | Partial writes, crash/restart, terminal cleanup | `test_partial_write_crash_after_comment_is_adopted_on_resume`, `test_cancel_release_failure_is_replayed_on_resume`, `test_resume_checks_identity_before_any_effect` | — | fixture-qualified |
| 2 | Reopened issues, review regression | `test_reopened_dependency_fails_closed`, `test_reopened_story_itself_is_inconsistent`, `test_review_regression_after_approval`, `test_another_reviewers_approval_does_not_mask_an_objection`, `test_objection_at_an_earlier_commit_still_counts…`, `CoordinatorOverTransportTests` (raw GraphQL reviews) | — | fixture-qualified at the production transport boundary |
| 2 | Fail closed on unknown eligibility, denial, outage | `DenialOutageAndLiveGateTests`, `test_outage_during_fresh_snapshot_refuses_admission`, `test_missing_project_item_is_unknown`, `test_graphql_errors_are_classified`, `test_error_classification` | `probe-write --issue 21` refused | fixture-qualified |
| 2 | Serialization, run binding | `test_interleaved_claim_from_another_coordinator_is_refused_by_the_lock`, `test_lock_is_held_across_the_whole_operation_against_other_processes`, `test_run_is_bound_to_repository_and_policy` | — | fixture-qualified (single machine) |
| 3 | Explicit T3 targets; receipts validated | `test_receipts` | `evidence/t3-task-receipt-2026-11-06.json` | receipt validation implemented; a false receipt is not detectable |
| 3 | One implementer per story/run; worktree identity; resume | lock, budget and identity tests | `t3_worktree_status` recorded | fixture-qualified |
| 3 | Checks before review (executed, full set, exact clean HEAD) | `test_checks_execute_full_set_on_exact_head`, `test_failed_command_fails_checks_but_runs_whole_set`, `test_checks_refuse_wrong_head_dirty_tree_and_foreign_cwd`, `test_checks_that_modify_the_tree_do_not_pass`, `test_no_asserted_pass_exists`, `test_review_requires_executed_passing_checks_at_head` | — | fixture-qualified |
| 3 | Budgeted repair ≤ 2; no bypass | `test_record_head_after_failure_requires_budgeted_repair`, `test_repair_cap_blocks_after_two_rounds`, `test_delegated_task_budget`, `test_wall_clock_budget` | — | fixture-qualified |
| 3 | Admission before delegate, cancel acknowledgement, budget termination | — | T3 contracts inspected (`delegate_task`, `task_status`, `task_cancel`, `t3_thread_wait`): no hook, no acknowledgement, no child deadline | **blocked**; live admission refused in code (`test_live_transport_refuses_product_admission`, `test_live_transport_flag_blocks_admission_before_any_call`) |
| 3 | No competing bmad-loop runner | design rationale; `.bmad-loop/` untouched | `list_scheduled_tasks` → none | implemented |
| 4 | Minimum permissions probed; bounded vs basic | `test_check_permissions_separates_basic_access_from_bounded` | `check-permissions` → `basic_access true`, `bounded false`, exit 2 (`evidence/check-permissions-2026-11-06.json`) | **blocked**: bounded identity not available; exact minimum and test plan in `permissions.md` |
| 4 | Secrets only via supported path | policy and redaction tests | no token read or stored | implemented |
| 4 | Probes and check commands; allowlist; budgets; stopping | probe and policy tests | `probe` ok (gh, git, docker) | implemented; live checks not run through the tool (no live claim) |
| 4 | No auto merge/deploy/release/live collection | policy loader refuses; absence test | — | implemented |
| 5 | Bounded foreground dry run, no product dispatch | — | `plan` writes 0; live writes limited to #106 comments | live-verified |

## Exact commands and results

```text
python3 -m unittest discover -s automation/tests -t .          → Ran 116 tests … OK (0 skipped)
PYTHONPATH=. python3 <reviewer probe re-run>                   → all ten scenarios refused or not applicable (evidence/reviewer-probes-rerun-2026-11-06.txt)
python3 -m automation.unattended snapshot --out automation/tests/fixtures/backlog-snapshot-2026-11-06.json   → 105 entries at 2026-11-06T13:19:42Z
python3 -m automation.unattended --snapshot … verify-mapping    → ok true; epics 19, stories 85, tasks 340, tasks_index 340; exit 0
python3 -m automation.unattended --snapshot … --policy automation/examples/first-run-om-01-02.toml plan   → OM-01.02 awaiting-owner-acceptance; writes 0
python3 -m automation.unattended check-permissions             → basic_access true, bounded false, unattended_activation_allowed false; exit 2
python3 -m automation.unattended probe                         → ok true
python3 -m automation.unattended --live --run-id eng01-foundation-2026-11-06 probe-write --issue 106   → posted 6685915849, idempotent true
python3 -m automation.unattended --live --run-id eng01-foundation-2026-11-06 probe-write --issue 106   → comment_existed true, posted null
python3 -m automation.unattended --live --run-id eng01-foundation-2026-11-06 probe-write --issue 21    → refused (backlog issue)
./gradlew build --console=plain                                → BUILD SUCCESSFUL (initial round; backend unchanged since, CI re-runs it)
```

`probe-write-1/2-2026-11-06.json` record the superseded first-round design (a Project Status write); that path was removed in repair round 1 and the files are kept as history only. ENG-01's Status `In review` was set by that removed path; from now on the owner maintains it.

## Reviewer findings addressed (round 1)

B1/E1/V2 stale issues → admission re-reads the closure; B2 → store lock; B3/E3/V10 → no Status writes; B4 → repair-required; B5/E4 → conflict on resume; B6/E9 → run binding; B7/E6/E7/E8/V4/V5 → operation identities, terminal replay, no Status effect; B8/E10 → per-reviewer objections; B9/E2/V3 → strict grammar; E5 → resume refuses changed revisions; E11 → `repair` behind `--live`; E12/V9 → bounded verdict, blocked; V1 → transport contract tests; V6 → identity before effects; V7 → executed checks only; V8 → live gate and documented gaps.

## Limitations and blockers

- Live product admission is refused until T3 can enforce admission ordering, cancellation acknowledgement and budget termination (upstream changes listed in `permissions.md`); the state machine is fixture-qualified only.
- No bounded credential exists; the operator token is admin with excess scopes. Activation stays blocked until a bounded identity passes the documented test plan.
- Project Status synchronization is not implemented; the owner moves Status from the machine's comments.
- Receipt validation trusts the coordinator's report of the `delegate_task` target.
- Foreign coordinators on other machines are detected through claim markers, not excluded.
- Deterministic checks have not been executed through the tool against the real backend build (no live claim); they run in CI independently.

## Candidate first-run activation (blocked)

Policy: `automation/examples/first-run-om-01-02.toml`. Preconditions, all currently unmet: owner sets OM-01.02 to `Ready`; ENG-01 independently reviewed and merged; bounded credential provisioned and tested; T3 enforcement gaps closed upstream and the live gate removed in a reviewed change; `verify-mapping` and `probe` pass on the coordinator machine. OM-01.02's own gates are untouched.
