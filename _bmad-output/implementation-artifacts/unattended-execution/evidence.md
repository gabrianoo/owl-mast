# ENG-01 evidence: requirements to evidence

Pull request: https://github.com/gabrianoo/owl-mast/pull/107 (ENG-01 issue #106). All commands were run from the worktree `/home/gabrianoo/.t3/worktrees/owlmast/t3-08a6bd98` (branch `t3/unattended-execution-foundation`, base `c5d9d2eff121423223bf75607c89dd1c55015813`) on 2026-11-06. Fixture coverage and live transport are listed separately; nothing below dispatched a product story or mutated backlog progress.

## Requirements-to-evidence matrix

| # | Requirement | Fixture evidence (unit suite) | Live evidence | Status |
| --- | --- | --- | --- | --- |
| 1 | Stable E/OM IDs, native relationships, 19/85/340 | `test_backlog.RealBacklogMappingTests` on the real snapshot fixture | `verify-mapping` → `ok: true`, counts 19/85/340, `tasks_index 340`, 105 Project items (`evidence/verify-mapping-2026-11-06.json`) | met |
| 1 | One writer per field, explicit status semantics, Done distinct from checks/review/merge | `test_coordinator.test_no_merge_or_done_path_exists`, `test_propose_evidence_posts_proposal_and_in_review` (tasks proposed, body untouched, Status `In review`, never `Done`) | `docs/unattended-execution.md` writer table; `probe-write` on ENG-01 only | met (policy); enforcement by credential, see permissions |
| 1 | Dependencies, owner gates, scoped exceptions, E17/E19 excluded | `test_eligibility` (12 cases: owner gate, dependency, epic prerequisite, reopened, not planned, inconsistent, missing item, active/blocked, exceptions, E17/E19 flags) | `plan` dry run for OM-01.02 → `awaiting-owner-acceptance` (`evidence/plan-dry-run-om-01-02-2026-11-06.json`) | met |
| 2 | Exact-commit evidence, SHA-bound approval | `test_review_sha_must_match_head`, `test_new_commit_invalidates_approval` | — | met (fixture) |
| 2 | Stale revisions and concurrent edits | `test_project_item_edited_after_snapshot_is_stale`, `test_owner_moved_status_after_snapshot_is_stale`, `test_foreign_active_claim_is_refused`; residual window pinned as a limitation | Same-value write left `updatedAt` unchanged (`probe-write-1`), confirming `updatedAt` cannot flag a same-value race | met with documented limitation |
| 2 | Idempotent retries, duplicate events | `test_duplicate_claim_event_posts_one_comment`, `test_transient_outage_on_post_then_retry_has_single_effect`, `test_duplicate_marker_from_concurrent_writer_is_a_conflict` | `probe-write` twice on #106: one comment `6685359778`, second call `comment_existed: true`, `idempotent: true` | met |
| 2 | Partial writes, crash/restart | `test_partial_write_crash_after_comment_is_adopted_on_resume` (fresh coordinator over the same store adopts the posted comment, posts nothing twice) | — | met (fixture) |
| 2 | Reopened issues, review regression | `test_reopened_dependency_fails_closed`, `test_reopened_story_itself_is_inconsistent`, `test_review_regression_after_approval`, `test_propose_refuses_merged_pr_head_mismatch_and_github_regression` | — | met (fixture) |
| 2 | Fail closed on unknown eligibility, denial, outage | `test_permission_denied_on_status_write_does_not_advance`, `test_outage_on_read_fails_closed_before_any_effect`, `test_block_records_github_failure_but_stays_blocked_locally`, `test_resume_abandons_claim_when_owner_changed_status`, `test_missing_project_item_is_unknown` | `probe-write --issue 21` refused (`refused`, backlog issue) | met |
| 3 | Explicit T3 targets with effort; receipts validated | `test_receipts` (8 cases incl. the real receipt shape) | `evidence/t3-task-receipt-2026-11-06.json`: this task inherited `claudeAgent/claude-fable-5-1/effort=high`; `gpt-6-astra` offers `reasoningEffort=high` | met |
| 3 | One implementer per story/run; isolated worktree identity; resume | `test_one_active_implementer_per_run`, `test_claim_requires_worktree_identity`, `test_resume_refuses_worktree_mismatch` | `t3_worktree_status` path/branch recorded in the receipt evidence | met |
| 3 | Checks before review; fresh reviewer; ≤2 repair rounds; cancel/resume/stop | `test_review_requires_passing_checks_at_head`, `test_reviewer_task_must_be_fresh`, `test_repair_cap_blocks_after_two_rounds`, `test_cancel_restores_ready`, `test_cancel_run_stops_everything`, budget tests | — | met (fixture) |
| 3 | No competing bmad-loop runner | design.md rationale; `.bmad-loop/` untouched; state under `.unattended-runs/` | `list_scheduled_tasks` → none | met |
| 4 | Minimum permissions probed; excess reported | `test_check_permissions_minimum_and_excess` | `check-permissions` → `minimum_satisfied: true`, excess `admin:public_key, gist, workflow` | met; bounded credential not yet provisioned |
| 4 | Secrets only via supported path | `test_secret_like_key_is_refused`, `test_credential_like_value_is_refused`, `test_run_commands_redacts_token_like_output` | no token read or stored; `gh` session only | met |
| 4 | Actual probes and check commands; allowlist; budgets; stopping | `test_run_commands_stops_at_first_failure`, policy tests, budget tests | `probe` → `gh auth status`, `git --version`, `docker version` all exit 0 | met |
| 4 | No auto merge/deploy/release/live collection | policy loader refuses `merge != owner` and the auto_* flags; absence test | — | met |
| 5 | Bounded foreground dry run, no product dispatch | — | `plan` dry run (writes 0); live writes limited to #106 | met |

## Exact commands and results

```text
python3 -m unittest discover -s automation/tests -t .          → Ran 81 tests … OK (0 skipped)
python3 -m automation.unattended snapshot --out automation/tests/fixtures/backlog-snapshot-2026-11-06.json   → 105 entries at 2026-11-06T12:55:04Z
python3 -m automation.unattended --snapshot automation/tests/fixtures/backlog-snapshot-2026-11-06.json verify-mapping --out …/verify-mapping-2026-11-06.json
                                                                → ok: true; epics 19, stories 85, tasks 340, tasks_index 340, other_issues 1 (ENG-01); exit 0
python3 -m automation.unattended --snapshot … --policy automation/examples/first-run-om-01-02.toml plan
                                                                → OM-01.02 awaiting-owner-acceptance (Status Backlog); writes 0
python3 -m automation.unattended check-permissions             → minimum_satisfied true; excess [admin:public_key, gist, workflow]; exit 0
python3 -m automation.unattended probe                         → ok true (gh auth status, git 2.43.0, docker 29.9.2)
python3 -m automation.unattended --live --run-id eng01-foundation-2026-11-06 probe-write --issue 106 --status "In progress"
                                                                → comment 6685359778 posted, idempotent true; Status write verified; updatedAt unchanged (same value)
python3 -m automation.unattended --live --run-id eng01-foundation-2026-11-06 probe-write --issue 106
                                                                → comment_existed true, posted null, one comment with the marker
python3 -m automation.unattended --live --run-id eng01-foundation-2026-11-06 probe-write --issue 21
                                                                → error refused: not an engineering-automation issue (nothing written)
./gradlew build --console=plain                                → BUILD SUCCESSFUL in 21s (backend unchanged; unit + integration suites, gates)
python3 -m automation.unattended --live --run-id eng01-foundation-2026-11-06 probe-write --issue 106 --status "In review"
                                                                → Status In progress→In review verified; updatedAt 12:43:55Z→13:02:53Z; marker comment reused (idempotent)
```

Failure tests executed and passing inside the suite: stale revision (2), residual-window limitation (1), foreign claim (1), duplicate event (1), transient outage then retry (1), crash after post (1), duplicate marker conflict (1), permission denial (1), outage before effect (1), GitHub failure during block (1), abandoned claim on resume (1), checks missing/failed before review (1), SHA mismatch (2), stale reviewer task (1), repair cap (1), review regression (2), budgets (4), worktree mismatch (2), policy guards (10), write-probe guard (1).

## Limitations

- No compare-and-swap on GitHub: an edit inside the pre-write/write window is lost undetected (pinned by test). Exposure is one Status field for one request.
- Live transport coverage is read-only plus the bounded probe on #106; no live claim/propose cycle has run because no story is `Ready` and activation is not authorized. Observed live: a real Status change (`In progress`→`In review` on #106) moved `updatedAt` from `2026-11-06T12:43:55Z` to `2026-11-06T13:02:53Z` (`evidence/probe-write-3-in-review-2026-11-06.json`), so `updatedAt` does flag value-changing concurrent edits before the pre-write read; a same-value write does not change it.
- T3 `delegate_task` is invoked by the coordinator, not by the tool; the tool validates receipts. A coordinator that passes a false receipt defeats the check; this is a trust boundary, not an enforcement point.
- The credential in use is a full-access user token. A bounded fine-grained token has not been provisioned or tested.
- Deterministic checks run `./gradlew build` and the gate script; their duration (minutes) and Docker dependence bound the coordinator machine.

## Candidate first-run activation (separately authorized)

Policy: `automation/examples/first-run-om-01-02.toml` (allow `OM-01.02`, budgets as default). Preconditions: owner sets OM-01.02 to `Ready`; ENG-01 independently reviewed and merged; `verify-mapping`, `check-permissions`, `probe` pass on the coordinator machine; bounded `GH_TOKEN` via `request_secret` if the coordinator is unattended. Implementer: `delegate_task` `claudeAgent`/`claude-fable-5-1`/`effort=high`, `isolation: worktree`; reviewer: fresh `codex`/`gpt-6-astra`/`reasoningEffort=high`. OM-01.02's own Kubernetes, storage, identity, secrets and live gates remain in force and are not satisfied by this foundation.
