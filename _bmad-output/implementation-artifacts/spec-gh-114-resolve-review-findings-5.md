---
title: 'PR #114 round 6: resolve review 5862675978'
type: 'bugfix'
created: '2026-11-11'
status: 'in-progress'
route: 'dispatch'
review_loop_iteration: 0
baseline_commit: 'e9fbfade0882fc671e0c62af085016f5f51db0ae'
context:
  - '/tmp/claude-1000/-mnt-c-Users-gabrianoo-Work-aisquad-owlmast/cc143ade-28ef-4359-9698-9dedd1bcafec/scratchpad/wt114/docs/unattended-execution.md'
  - '/tmp/claude-1000/-mnt-c-Users-gabrianoo-Work-aisquad-owlmast/cc143ade-28ef-4359-9698-9dedd1bcafec/scratchpad/wt114/_bmad-output/implementation-artifacts/spec-gh-114-resolve-review-findings-4.md'
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** Review 5862675978 on PR #114 (head e9fbfad) left 18 open inline threads. The owner ranked five as fix-first:
1. The abort note always says "re-issue", even when `run.json` exists or the record is not this run's (state.py:566).
2. A clear that took effect exits 3 like a refusal, and Ctrl-C after the replace is neither journaled nor tested (coordinator.py:2206/2201).
3. A ledger record that fails validation is not journaled on open, and the refusal says "cannot be read" without naming the field (activation.py:576/420).
4. The state-dir-mismatch advice cannot be followed once the directory has moved (activation.py:579).
5. No test pins git's answer to exactly the plain discovery failure (cli.py:175).

**Approach:** Fix the five first, then the other 13. Each fix gets a test that fails when the fix is reverted. Then reply to each thread on GitHub and resolve it.

**Decisions (owner, 2026-11-11):**
- Clear whose save reported an error after `run.json` was replaced (R_I0): `clear_clock_regression` returns the normal clear result (`journal_seq`, `run`) plus `save_uncertain`, and the CLI exits 0. The `clear-save-uncertain` refusal is removed.
- The full spec covers all 18 threads; no split (~2,000 tokens).

## Boundaries & Constraints

**Always:** fail closed; all earlier owner decisions hold (a clearance is a convention; it is refused in any work tree or when git cannot answer; `--expect` is required with `--run-id`; time a forward skew runs ahead is never refunded; a revoked repair is reconciled under a clock stop that can still be cleared); update docs and help with every behaviour change; tests must fail on revert on Python 3.12 **and** 3.14.

**Never:** edit the shared checkout on `main`; change CI or Helm; fetch evidence from GitHub.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| Abort, run.json exists | `save_run` raised after `os.replace` | note: "run.json exists: reopen the same run, the next open confirms the record; do not re-issue" | — |
| Abort, record not this run's / unreadable / not pending | — | note names that cause; never says "stays pending" | — |
| Clear, save fails after replace | `fsync_directory` raises OSError | normal clear result + `save_uncertain`, exit 0 | `activation-stop-cleared` with `save_uncertain` is journaled |
| Clear, Ctrl-C after replace | `fsync_directory` raises KeyboardInterrupt | KeyboardInterrupt propagates; a best-effort `activation-stop-cleared` (`interrupted`) line is written first | journal failure swallowed |
| Invalid record on open | record with non-string `state_dir` / bad `attempts` | one `activation-use-unconfirmed` line (`ledger-unreadable`, names the field) | — |
| Moved state dir | recorded `state_dir` no longer exists | message: cannot be settled from here, the document is spent; moving the directory back is the only way to confirm it | — |
| git: extra diagnostic | rc 128, `error: x\nfatal: not a git repository (or any of the parent directories): .git` | `WorkTreeUnknown`, `clearance-invalid` | — |

</frozen-after-approval>

## Code Map

All work happens in the PR #114 worktree `/tmp/claude-1000/-mnt-c-Users-gabrianoo-Work-aisquad-owlmast/cc143ade-28ef-4359-9698-9dedd1bcafec/scratchpad/wt114` (branch `t3/pr108-review-findings`), paths relative to it. Never edit `/mnt/c/Users/gabrianoo/Work/aisquad/owlmast`. Commit locally; do not push or touch GitHub. Thread ids are `PRRT_kwDOVjxExc62R_` suffixes; the full text is in `/tmp/claude-1000/-mnt-c-Users-gabrianoo-Work-aisquad-owlmast/cc143ade-28ef-4359-9698-9dedd1bcafec/scratchpad/open114r6.txt`.

- `automation/unattended/activation.py`
  - `abort_activation_use:~590`: return a reason, not a bool (`aborted`, `run-json-exists`, `no-record`, `unreadable`, `not-pending`, `not-this-run`, `ledger-error`) (Iy). Pin the `NotADirectoryError` branch (Jp) and the `[:500]` cap (Ju).
  - `activation_use:~413`: an invalid record returns `{"unreadable": True, "why": "<field problem>"}` (I-).
  - `use_refusal:~470`: print `why` when it is set (I-).
  - `confirm_activation_use:~566`:
    - Return a tagged result, `("committed"|"unchanged"|"error", detail)`, and drop `report_success` (JX).
    - An unreadable record is an error of type `ledger-unreadable` that names the field (I7).
    - When the mismatch's recorded dir no longer exists, the message changes (JC).
  - `evidence_problems:~214`: fold the id-0 check into the first loop's `elif` chain (Jc).
  - `_retryable_creation` docstring: realpath **or** samefile (Je).
- `automation/unattended/state.py`
  - `ensure_run:~560-590`:
    - Word the abort note per reason (Iy).
    - Adapt both callers to the tagged result (JX).
    - The creation-path caller still journals only errors.
  - `_unconfirmed_since_confirmation:~604`: scan the journal lines in reverse and stop at the first `activation-use-confirmed`. JSON-parse only lines that contain `"activation-use-` (JQ). Do not add a sidecar file: `journal()` already reads the whole file to count lines, so this keeps the same order of cost.
  - `_journal_confirmed:~630`: pin the guard (Js).
- `automation/unattended/coordinator.py`
  - `clear_clock_regression:~2195-2210`:
    - Save-uncertain path: return the normal result plus `save_uncertain`; no refusal (owner decision).
    - A `BaseException` that is not an `Exception`, raised after the replace, writes a best-effort `activation-stop-cleared` line with `interrupted` and re-raises (I0/I3).
  - `reconcile_retained_execution:~1466`: an authorization that is already `consumed` and has a `reconciliation` passes like a revoked one. The identical-evidence check still applies (JF).
  - `reconcile_retained_execution:~1564-1572`: on the clearable-stop path, stamp `bound_at`, `reconciliation.at`, `task_history[].at` and the backup name with `max(now, high_water)`, and record `observed_at` (JJ).
  - `status:~2240`: when the recorded stop is `clock-regression`, add `activation.clock_stop` = `{clearable, clear_spent, high_water, expires_at, reason}` (JM). Reuse `_clearable_clock_stop` and `_clear_spent`.
- `automation/unattended/cli.py`
  - `_work_tree:~165`: a timeout names the directory and says a hung mount (network, autofs, stale drvfs) is the likely cause (Jj).
  - The `_git_entry_above` lstat walk runs only after git has walked the same ancestors successfully, so it needs no timeout. State that in its docstring.
  - No exit mapping is needed: the result already prints with exit 0.
- `docs/unattended-execution.md:119` (the clear paragraph) and the error-code table near `:163`: the save-uncertain exit, the Ctrl-C line, `clock_stop` in `status`, `ledger-unreadable`.
- `automation/tests/test_pr114_round6_findings.py` (new): reuse the helpers in `test_pr114_round5_findings.py` (`ClearanceLocationCase`, the live-store harness). Update the round-4/5 asserts on `abort_activation_use` (`assertTrue`/`assertFalse` become reason checks) and the round-4 `confirm_activation_use` call at `round4:224`.

## Tasks & Acceptance

**Execution:**
- [x] `automation/unattended/activation.py` -- Iy, I-, I7, JC, JX, Jc, Je as mapped -- the abort reason, field-naming, journaling, honest advice and a tagged result.
- [x] `automation/unattended/state.py` -- per-reason notes, tagged-result callers, the reverse scan -- Iy, JX, JQ.
- [x] `automation/unattended/coordinator.py` -- save-uncertain and interrupt paths, the reconcile idempotence and stamping, `status.clock_stop` -- I0, I3, JF, JJ, JM.
- [x] `automation/unattended/cli.py` -- the timeout wording and the save-uncertain exit -- Jj, I0.
- [x] `docs/unattended-execution.md` -- the behaviour changes above.
- [x] `automation/tests/test_pr114_round6_findings.py` -- one test class per thread (all 18), each failing on revert. This covers Jm (fullmatch→search), Jp, Js and Ju, plus the KeyboardInterrupt-after-replace case.

**Acceptance Criteria:**
- Given each of the 18 threads, when its fix is reverted, then at least one test in `test_pr114_round6_findings.py` fails.
- Given the full suite, when it runs on Python 3.14 and 3.12, then every test passes and the real ledger under `~/.local/state/owl-mast/` is never written.

## Implementation Notes

- Baseline `e9fbfad`, 685 tests OK. After this change: 724 tests OK on Python 3.14.4 and 3.12.14, 39 new in `automation/tests/test_pr114_round6_findings.py`. `~/.local/state/owl-mast/` did not exist before or after the runs.
- Revert check: 18 single-site mutations, one per thread (script kept outside the repository, in the session scratchpad), each run against the round-6 module on 3.14 **and** 3.12; every one failed at least one test there.
- Adapted earlier tests (each says why in a comment): round 4 `UnconfirmedStableKeyTests.test_confirm_returns_type_errno_and_message` (tagged result), `AbortHandlerNeverMasksTests.test_abort_returns_false_when_the_run_path_cannot_be_checked` (`ledger-error`), `FailedClearRestoresTheStopTests.test_a_save_that_fails_after_run_json_was_written_follows_the_disk` (result plus `save_uncertain`); round 5 `UnreadableRunDirectoryTests` (reasons), `StateDirMissingIsUnreadableTests` (now one `ledger-unreadable` line, I7), `AttemptHistoryValidationTests` (the field is named, I-), `AbortFalseNoteTests` and the round-3/4 `abort_activation_use` mocks (`return_value="ledger-error"`), `ClearSaveUncertainTests` (owner decision R_I0: exit 0, no refusal).
- Design choices:
  - `run.json` that cannot be examined (`os.stat` raising anything but `FileNotFoundError`/`NotADirectoryError`) maps to `ledger-error`, the spec's "ledger or file-system error", whose note says the record stays pending.
  - `ledger-unreadable` dedupes on `(type, None, None)`: one line per episode, whichever field failed.
  - `status.activation.clock_stop.clearable` is `_clearable_clock_stop()` and, in addition, false when the wall clock judged on the high-water mark is spent (the clear refuses `wall-clock-exceeded` there, and `_durable_run_stop` treats the stop as durable).
  - The help texts of `clear-clock-regression` and `status` name `save_uncertain` and `clock_stop`.
- Thread map (suffix of `PRRT_kwDOVjxExc62R_…` → change → test class in the new module):
  - **Iy** `abort_activation_use` returns one of `ABORT_REASONS`; `state.abort_note` words each → `AbortReasonTests`.
  - **I0** save-uncertain returns the normal result plus `save_uncertain` (exit 0) → `ClearSaveUncertainIsAClearTests`. **I3** an interrupt after the replace writes a best-effort `interrupted` line and propagates → `ClearInterruptedAfterReplaceTests`.
  - **I7** unreadable record → `("error", {type: ledger-unreadable})`, journaled once → `UnreadableRecordJournaledTests`. **I-** `activation_use` adds `why`; `use_refusal` prints it → `InvalidRecordNamesTheFieldTests`.
  - **JC** the mismatch advice depends on whether the recorded directory exists → `MovedStateDirAdviceTests`.
  - **JF** any consumed authorization with a `reconciliation` passes under a clearable stop → `ReconcileRepeatUnderClearableStopTests`. **JJ** stamps `max(now, high_water)`, records `observed_at` → `ReconcileStampedWithHighWaterTests`.
  - **JM** `status.activation.clock_stop` → `StatusClockStopTests`.
  - **JQ** reverse scan, parses only `"activation-use-` lines → `UnconfirmedReverseScanTests`. **JX** tagged result, `report_success` gone → `ConfirmTaggedResultTests`.
  - **Jc** id 0 folded into the `elif` chain → `EvidenceIdZeroWrongRepositoryTests`. **Je** docstring → `RetryableCreationDocstringTests`.
  - **Jj** a git timeout names the directory and a hung mount; `_git_entry_above` docstring says why it needs no timeout → `GitTimeoutNamesTheDirectoryTests`.
  - **Jm** → `OnlyThePlainAnswerAllowsTests`. **Jp** → `NotADirectoryMeansAbsentTests`. **Js** → `ConfirmedNeedsAnUnconfirmedLineTests`. **Ju** → `AbortCauseCapTests`.
- Not done here, by the Code Map's instruction (commit locally, do not push or touch GitHub): the replies and the resolution of the 18 threads.

## Spec Change Log

## Review Triage Log

## Verification

**Commands:**
- `python3 -m unittest discover -s automation/tests -t .` -- expected: all OK.
- `python3.12 -m unittest discover -s automation/tests -t .` -- expected: all OK.
- `ls -la ~/.local/state/owl-mast/activation-ledger/` before and after -- expected: unchanged.
