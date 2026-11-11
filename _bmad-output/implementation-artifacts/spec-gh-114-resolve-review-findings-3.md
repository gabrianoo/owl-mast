---
title: 'PR #114 round 4: resolve review 5860194023'
type: 'bugfix'
created: '2026-11-11'
status: 'done'
route: 'dispatch'
review_loop_iteration: 0
baseline_commit: '54c89c1dcb15058540741eb547d2fc5b5ba0fe0e'
context:
  - '/tmp/claude-1000/-mnt-c-Users-gabrianoo-Work-aisquad-owlmast/cc143ade-28ef-4359-9698-9dedd1bcafec/scratchpad/wt114/docs/unattended-execution.md'
  - '/tmp/claude-1000/-mnt-c-Users-gabrianoo-Work-aisquad-owlmast/cc143ade-28ef-4359-9698-9dedd1bcafec/scratchpad/wt114/_bmad-output/implementation-artifacts/spec-gh-114-resolve-review-findings-2.md'
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** Review 5860194023 on PR #114 (head 54c89c1) left 20 open inline threads. The owner ranked five as fix-first: `reconcile-retained-execution` ignores a clearable clock stop, the clearance work-tree check fails open when git fails, the location check is case-sensitive on `/mnt/c`, delegated worktrees are not refused, and `activation-use-unconfirmed` is journaled on every open. Three body-only findings repeat decided points (clearance under `/tmp`, per-account ledger, shared numeric ids) and stay as decided.

**Approach:** Fix the five fix-first threads first, then the other 15, each with a test that fails when the fix is reverted. Then reply to each thread on GitHub and resolve it.

**Decisions (owner, 2026-11-11):** when git cannot answer, a clear refuses; a clearance inside any git work tree is refused; `check-activation --run-id` requires `--expect`.

## Boundaries & Constraints

**Always:** fail closed; owner-only clearance stays a documented convention (round-3 decision); update docs and CLI help with each behaviour change; replies per [[review-records-on-github]].

**Never:** edit the shared checkout on `main`; change CI or Helm; fetch evidence from GitHub; revisit the three body-only decisions.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| Reconcile under a clearable stop | retained repair pending, `clock-regression` recorded, clear not spent | refuses `clock-regression`, authorization still pending | after the clear, the repair binds for work |
| git cannot answer | `git rev-parse` raises / times out / fails other than "not a git repository" | `clearance-invalid` ("cannot determine work tree") | — |
| Clearance in any work tree | clearance file's parent is inside any git work tree (incl. delegated worktrees) | `clearance-invalid` | — |
| Case variant | clearance path differs from the state dir or work tree only by case | `clearance-invalid` | — |
| Ledger stays unwritable | many opens, same errno, random temp names | one `activation-use-unconfirmed` line | a different errno or type adds a line |

</frozen-after-approval>

## Code Map

All work happens in the PR #114 worktree `/tmp/claude-1000/-mnt-c-Users-gabrianoo-Work-aisquad-owlmast/cc143ade-28ef-4359-9698-9dedd1bcafec/scratchpad/wt114` (branch `t3/pr108-review-findings`), paths relative to it. Never edit `/mnt/c/Users/gabrianoo/Work/aisquad/owlmast`. Commit locally; do not push or touch GitHub.

Thread ids are `PRRT_kwDOVjxExc62NX…` suffixes. The full comment text is in `gh api repos/gabrianoo/owl-mast/pulls/114/comments --paginate` filtered by `pull_request_review_id == 5860194023`, read-only.

- `automation/unattended/coordinator.py` -- `reconcile_retained_execution:~1406` (2i: `skip_clearable`, refuse `clock-regression`); `_durable_run_stop:~569` (3i: wall clock on the high-water mark everywhere); `_clear_spent:573`/`_clearable_clock_stop` (4A: once per operation, use the journal view); stop key `:584` (4H); `bind_receipt:1263` (31: check the `--reason` pairing before `require_activation`); `clear_clock_regression:~2100-2120` (2w case-insensitive state-dir check, 38 restore in-memory stop on save failure); `status:2157` (3d).
- `automation/unattended/activation.py` -- `load_clearance:563-566` (2w casefold, 25 symlink comment); `ledger_root:382` (4M empty/relative home); retry record `:490` (3O `created_at`, `attempts`); `:493` (3U test only); `confirm_activation_use:513` (3Y tests only); `EVIDENCE_URL_RE`/`:208` (4P bound the id to 1–20 digits); `STOP_RECORD_KEYS`/`validate_stop_record` (`stop_id` optional key).
- `automation/unattended/state.py` -- `:562` abort handler (3J); `_journal_unconfirmed:598` (3E stable key).
- `automation/unattended/cli.py` -- `_work_tree:140`, `_clearance_forbidden:148` (2p, 2z); `--expect` (3t); the no-activation report (3y, one report builder); the `--reason` pairing pre-check (31).
- `automation/tests/test_pr114_round4_findings.py` (new) -- reuse `LiveCase`, `regress`, `clearance` from `test_pr114_review_findings.py`. For retained-repair setup, see `test_run_identity.py` / `test_pr107_review_findings.py`.
- `docs/unattended-execution.md`, the unattended prompt or docs that call `check-activation` -- `--expect` usage, the clearance rules, the wall-clock rule.

## Tasks & Acceptance

**Execution:**
- [x] `coordinator.py` + test -- reconcile defers to a clearable clock stop -- 2i
- [x] `cli.py`, `activation.py` + tests -- clearance location: git failure refuses; any work tree refused; casefold comparison (also in the coordinator); honest symlink comment -- 2p, 2z, 2w, 25
- [x] `state.py`, `activation.py` + tests -- unconfirmed key `(type, errno)`; abort handler never masks the original error; retry record keeps the attempt history; tests for the retry-write refusal and both confirm rules -- 3E, 3J, 3O, 3U, 3Y
- [x] `coordinator.py` + tests -- `status --read-only` ledger test; wall clock on the high-water mark in `_durable_run_stop` and `check-activation`; `--reason` pairing before the gate; in-memory restore on a failed clear; `_clear_spent` once per operation; `stop_id` -- 3d, 3i, 31, 38, 4A, 4H
- [x] `cli.py` + tests -- `--expect` required with `--run-id`; one report shape -- 3t, 3y
- [x] `activation.py` + tests -- empty/relative home refuses; evidence id bounded -- 4M, 4P
- [x] GitHub -- reply to and resolve all 20 threads; refresh the PR body

**Acceptance Criteria:**
- Given the full suite, when run, then it passes, and reverting any fix fails at least one named test.
- Given PR #114 after the push, when its threads are listed with pagination, then none is unresolved.

## Design Notes

- **Work-tree rule.** `_work_tree(p)` returns one of three answers: a path, "not a work tree" (git exit 128 with "not a git repository" in stderr), or "unknown" (any other failure: OSError, timeout, other exit codes such as dubious ownership). "Unknown" refuses `clearance-invalid`. A clearance is refused when its own parent directory resolves to any work tree (this covers delegated worktrees), and also when it lies inside `--state-dir`, the `--repo-root` work tree or the tool's work tree.
- **Containment.** Compare `os.path.normcase(os.path.realpath(x)).casefold()` component prefixes, in `load_clearance` and in the coordinator check.
- **`--expect`.** With `--run-id`, `--expect` is required (refusal `expect-required`, exit 3, as the CLI's contract for a malformed call). Without `--run-id`, it is not needed. Update every doc and prompt example.
- **`stop_id`.** New stops carry `stop_id` (a uuid4 hex). `validate_stop_record` accepts the documented keys plus an optional `stop_id`. `clear-started` records it, and `_clear_spent` compares `stop_id` when both sides have one, otherwise `observed_at` (legacy).
- **Unconfirmed key.** `confirm_activation_use` returns `{type, errno, message}`. Duplicates are suppressed on `(type, errno)`.
- Name each new test after the behaviour it checks.

## Implementation Notes

- Baseline `54c89c1`, 579 tests OK. After this change: 618 tests OK (`python3 -m unittest discover -s automation/tests -t .`), 39 new in `automation/tests/test_pr114_round4_findings.py`. The suite wrote nothing under `~/.local/state/owl-mast`.
- Revert check: 28 single-site mutations (one per behaviour, script kept outside the repository), each run against the round-2/3/4 modules; every one failed at least one named test.
- Adapted earlier tests (each says why in a comment): every `check-activation --run-id` call now passes `--expect` (3t) in `test_activation`, `test_pr108_review_findings`, `test_pr114_review_findings`, `test_pr115_fix_first_round3` and `test_pr114_round3_findings` (`CheckActivationExpectTests` now expects exit 3 without `--expect`); `FollowUpLedgerTests.test_a_reopen_journals_a_failing_confirmation_once_per_error` gives its third error its own errno (3E keys on `(type, errno)`).
- Thread map (suffix of `PRRT_kwDOVjxExc62NX…` → change → test class in the new module):
  - **2i** `reconcile_retained_execution` uses `_durable_run_stop(skip_clearable=True)` and refuses `clock-regression` under a clearable stop → `ReconcileUnderClearableStopTests`.
  - **2p** `cli._work_tree` answers a path, `None` (exit 128 + "not a git repository") or raises `WorkTreeUnknown`; unknown refuses `clearance-invalid` ("cannot determine the work tree") → `GitFailureRefusesTests`.
  - **2z** `_clearance_forbidden` also refuses the work tree of the clearance's own directory (covers delegated linked worktrees) → `AnyWorkTreeRefusedTests`.
  - **2w** `activation.is_inside` (normcase + realpath + casefold, component prefixes) in `load_clearance` and `clear_clock_regression` → `CaseInsensitiveContainmentTests`.
  - **25** the read comment states the limit (narrows, does not close, the race) → `HonestSymlinkCommentTests`.
  - **3E** `confirm_activation_use` returns `{type, errno, message}`; `_journal_unconfirmed` deduplicates on `(type, errno)` → `UnconfirmedStableKeyTests`.
  - **3J** the abort handler catches anything from `abort_activation_use` and attaches it as a note (not journaled: a journal before `run.json` would be a retained artifact); `run_path.exists()` is inside the guarded block → `AbortHandlerNeverMasksTests`.
  - **3O** the retry writes `created_at: now`, keeps `first_attempt_at`, appends to `attempts` (`at`, `pid`, `source`) → `RetryAttemptHistoryTests`.
  - **3U, 3Y** tests only → `RetryLedgerWriteRefusalTests`, `ConfirmRulesTests`.
  - **3d** test only → `ReadOnlyStatusLedgerTests`.
  - **3i** `_durable_run_stop` and `_stop_message` judge the wall clock on the high-water mark; `check-activation` on `max(now, last_observed_at)` → `WallClockOnHighWaterTests`.
  - **31** `coordinator.check_cleanup_reason` runs before the operation in `bind_receipt` and in the CLI before the coordinator is built → `ReasonPairingFirstTests`.
  - **38** `clear_clock_regression` restores `activation_stop` / `last_observed_at` when `save_run` raises → `FailedClearRestoresTheStopTests`.
  - **4A** `_clear_spent` is memoized per operation (keyed on the stop) and reads the resume's shared journal view → `ClearSpentOncePerOperationTests`.
  - **4H** new stops carry `stop_id` (uuid4 hex); `validate_stop_record` accepts it as optional; `clear-started` records it; `_clear_spent` compares it when both sides have one, else `observed_at` → `StopIdTests`.
  - **3t** `check-activation --run-id` without `--expect` refuses `expect-required` (exit 3); docs and the candidate updated → `ExpectRequiredTests`.
  - **3y** one report builder (`cli._activation_report`, `REPORT_KEYS`), `None` for what does not apply → `OneReportShapeTests`.
  - **4M** `ledger_root` refuses an empty or relative home → `LedgerHomeTests`.
  - **4P** `EVIDENCE_URL_RE` bounds the id to 1–20 digits → `EvidenceIdBoundTests`.
- Not changed: `_bmad-output/implementation-artifacts/eng-01-enabling-preflight-20261107.md` still shows `check-activation` without `--expect`; it is a dated record of that preflight, not a procedure.
- Not done here, by the Code Map's instruction (commit locally, do not push or touch GitHub): the replies, thread resolution and PR body refresh. The GitHub task stays open for the parent.

- Review pass 1: 15 patches in `16535f6`, nothing deferred. The locale test passes on this machine even without the fix, because no non-English git locale is installed.

## Spec Change Log

## Review Triage Log

Pass 1 (blind B1–B18, edge E1–E10, verification-gap V1–V2) on 5bfb1a4:

| # | Finding | Verdict | Evidence / route |
|---|---------|---------|------------------|
| B1 | `STOP_ID_RE` with `$` accepts a trailing newline | low | reproduced: validates; direct correction; patch |
| B2/E2 | inherited `GIT_*` env can make git deny a work tree | medium | `_work_tree` passes `os.environ`; the loop controls it; patch |
| B3/E1/V2 | translated git message makes every clear refuse | medium | match is on English stderr; patch (`LC_ALL=C`) |
| B4/B13 | work-tree rule is CLI-only; coordinator message is out of date | low | coordinator checks only the state dir; patch (message + docs) |
| B5 | home as a git work tree blocks every clear; no recommended location | low | patch (docs); the tmp-guard in tests is rejected (suite runs outside repos) |
| B6 | every `Refused` merges into one dedupe key | low | `Refused` has no errno; patch (`code`) |
| B7 | alternating errors and pre-upgrade lines still add lines | low | bounded by distinct causes; fix adds history scanning; rejected |
| B8 | `_clear_spent` fills the journal view early | false | the view is used only for `_journal_once`'s three event names, which the replays never write |
| B9/E6/V1 | legacy fallback allows a second clear in the mixed case; untested | medium | `coordinator.py:_clear_spent`; patch + legacy tests |
| B10 | test `git()` inherits the global git config | low | gpgsign or hooks break the suite; patch |
| B11 | the symlink-comment test greps the source | low | the comment-only fix has no behaviour to test; rejected |
| B12 | `--expect` without `--run-id` is accepted | low | patch (refuse) |
| B14 | "round 4" jargon in docs and code | low | patch |
| B15 | spec paths and status | — | fix edits this build's spec; rejected by rule |
| B16 | first `attempts` entry has no `pid` | low | patch (`pid: None`) |
| B17 | doc-example check is narrow; dated preflight record | low | the preflight file is a dated record; rejected |
| B18/E10 | 20-digit bound vs leading zeros; wrong reason in the comment | low | patch (comment, docs) |
| E3 | clearance on a separate mount inside a worktree | low | git's boundary message still says "not a git repository"; exotic; rejected |
| E4 | a missing parent dir reports "cannot determine work tree" | low | message quality; patch (existence check first) |
| E5 | casefold refuses a legitimate case-only sibling on a case-sensitive fs | low | fails closed; rejected |
| E7 | `attempts` not a list | false | the record is written only by this tool; a damaged record is caught by `activation_use` |
| E8 | in-memory restore wrong when the save raised after the replace | medium | `atomic_write_text` fsyncs after `os.replace`; patch (reload from disk) |
| E9 | claim: "any work tree" depends on discovery | — | covered by B2/E2 |

## Verification

**Commands:**
- `python3 -m unittest discover -s automation/tests -t .` -- expected: all pass (579 before)
- `ls ~/.local/state/owl-mast` -- expected: does not exist (the suite never writes the real ledger)
