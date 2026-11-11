---
title: 'PR #114 round 5: resolve review 5861377408'
type: 'bugfix'
created: '2026-11-11'
status: 'done'
route: 'dispatch'
review_loop_iteration: 0
baseline_commit: 'f5ab25a9aad6aca24df0ed82438a7a0bef0b897f'
context:
  - '/tmp/claude-1000/-mnt-c-Users-gabrianoo-Work-aisquad-owlmast/cc143ade-28ef-4359-9698-9dedd1bcafec/scratchpad/wt114/docs/unattended-execution.md'
  - '/tmp/claude-1000/-mnt-c-Users-gabrianoo-Work-aisquad-owlmast/cc143ade-28ef-4359-9698-9dedd1bcafec/scratchpad/wt114/_bmad-output/implementation-artifacts/spec-gh-114-resolve-review-findings-3.md'
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** Review 5861377408 on PR #114 (head f5ab25a) left 21 open inline threads. The owner ranked five as fix-first:
1. A dangling gitfile counts as "not a work tree".
2. `Path.exists()` hides a `PermissionError` on Python ≥ 3.13 in `abort_activation_use`.
3. A clock-regression stop stays "clearable" when no clear can succeed.
4. The reconcile refusal leads nowhere for a revoked repair, and the docs contradict it.
5. A forward clock jump permanently spends the wall-clock budget.

**Approach:** Fix the five fix-first threads first, then the other 16, each with a test that fails when the fix is reverted. Then reply to each thread on GitHub and resolve it.

**Decisions (owner, 2026-11-11):**
- Forward clock jump (OW): keep the round-2 rule (time ahead is spent waiting, not refunded). Docs and the `clear-clock-regression` help say plainly that a forward skew larger than the remaining budget ends the run. No behaviour change.
- Reconcile (OM): a revoked repair is reconciled under a clock stop that can still be cleared (cleanup only); a pending repair still refuses until the clear, with "clear the stop or cancel the run".

## Boundaries & Constraints

**Always:** fail closed; the round-3/4 owner decisions hold (a clearance is a convention; it is refused in any work tree or when git cannot answer; `--expect` is required with `--run-id`); update docs and help with each behaviour change; tests must fail on revert on Python 3.12 **and** 3.14.

**Never:** edit the shared checkout on `main`; change CI or Helm; fetch evidence from GitHub.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| Dangling gitfile | clearance dir has `.git` = `gitdir: /nonexistent/...` | `clearance-invalid` | — |
| Ancestor `.git` | any ancestor of the clearance dir has a `.git` entry (file or dir) | `clearance-invalid` | — |
| Unreadable run dir | mode-000 run dir, `save_run` raised | record stays `pending` (never `aborted`) | skipped when running as root |
| Stop past its window | `clock-regression` recorded, then `max(now, high_water) > expires_at` | not clearable: durable consequences (resume abandons, late receipts bind for cleanup) | — |
| Reconcile, revoked repair, clearable stop | revoked authorization, retained owner run | reconcile proceeds (cleanup) | pending authorization: still refuses `clock-regression` |

</frozen-after-approval>

## Code Map

All work happens in the PR #114 worktree `/tmp/claude-1000/-mnt-c-Users-gabrianoo-Work-aisquad-owlmast/cc143ade-28ef-4359-9698-9dedd1bcafec/scratchpad/wt114` (branch `t3/pr108-review-findings`), paths relative to it. Never edit `/mnt/c/Users/gabrianoo/Work/aisquad/owlmast`. Commit locally; do not push or touch GitHub.

Thread ids are `PRRT_kwDOVjxExc62Pk…` suffixes. The full text is in `gh api repos/gabrianoo/owl-mast/pulls/114/comments --paginate` filtered by `pull_request_review_id == 5861377408`, read-only.

- `automation/unattended/cli.py` -- `_work_tree:~147-165` (OE: allow only the plain discovery failure `not a git repository (or any of the parent directories)` with no `: <path>` suffix and no "Stopping at filesystem boundary"; anything else is unknown; also refuse when any ancestor of the clearance dir has a `.git` entry); `:174` (O6: `os.stat` and report ENOENT / EACCES / not a regular file); `:147` (Pp: locale test); `:160` (P1: tri-state tests).
- `automation/unattended/activation.py` -- `abort_activation_use:547` (QS: `os.stat`; only `FileNotFoundError`/`NotADirectoryError` mean absent); `_same_run:415` (Pf: fold both paths); retry record `:504-506` (Ot: `attempts` must be a list of dicts, otherwise an unreadable record; cap at first + last 10; record the abort cause; QK: test the `source` rewrite); `_fold:567` (O0: refusal wording "inside, or a case variant of"); `EVIDENCE_URL_RE:71` (PS: an all-zero id refuses; PZ: pin the 20-digit bound).
- `automation/unattended/state.py` -- `:565` (Og: note when `abort_activation_use` returns False); `:584` (Pi: state-dir mismatch is journaled); `_journal_unconfirmed:605` (PE: dedupe against the keys since the last successful confirmation; errno-less `OSError` keys on `strerror`).
- `automation/unattended/coordinator.py` -- `_clearable_clock_stop:636` (OR: clearable only while `max(now, high_water) <= recorded expires_at`); `reconcile_retained_execution:1451` (OM: a revoked authorization proceeds under a clearable stop; a pending one still refuses, and the message says "clear the stop or cancel the run"); `:580` (OW: no change; docs and help only); `clear_clock_regression:2170-2175` (Ol: when the reload shows the stop cleared, journal `activation-stop-cleared` and raise a coded `clear-save-uncertain` that says the clear took effect; QD: test the fallback restore); `_clear_spent` memo `:604` (P5: invalidation tests).
- `docs/unattended-execution.md:97,118` -- PJ, OM, and OW wording.
- `automation/tests/test_pr114_round5_findings.py` (new). Reuse the round-3/4 helpers.

## Tasks & Acceptance

**Execution:**
- [x] `cli.py` + tests -- dangling gitfile and ancestor `.git` refuse; tri-state and locale tests that really fail on revert -- OE, P1, Pp, O6
- [x] `activation.py` + tests -- `os.stat` guard (real mode-000 directory test, skipped as root); `_same_run` fold; `attempts` validation and cap; zero id; bound tests; `source` test; wording -- QS, Pf, Ot, PS, PZ, QK, O0
- [x] `coordinator.py` + tests -- clearable only inside the recorded window; reconcile of a revoked repair under a clearable stop; OW docs and help; a clear that took effect is reported as such; memo and fallback tests -- OR, OM, OW, Ol, P5, QD
- [x] `state.py` + tests -- abort note, state-dir mismatch journaled, dedupe set -- Og, Pi, PE
- [x] `docs/unattended-execution.md` -- PJ and the wording of the behaviour changes
- [x] GitHub -- reply to and resolve all 21 threads; refresh the PR body

**Acceptance Criteria:**
- Given the full suite on Python 3.14 (local) and 3.12 (CI), when run, then it passes, and reverting any fix fails at least one named test.
- Given PR #114 after the push, when its threads are listed with pagination, then none is unresolved.

## Implementation Notes

- Baseline `f5ab25a`, 625 tests OK. After this change: 673 tests OK on Python 3.14.4 (local) and 3.12.14 (uv-managed, local), 48 new in `automation/tests/test_pr114_round5_findings.py`. The suite wrote nothing under `~/.local/state/owl-mast`.
- Revert check: 36 single-site mutations (one per behaviour, script kept outside the repository), each run against the round-4 and round-5 modules on 3.14 **and** 3.12; every one failed at least one named test.
- Adapted round-4 tests (each says why in a comment): `AbortHandlerNeverMasksTests.test_abort_returns_false_when_the_run_path_cannot_be_checked` patches `os.stat` (QS); `RetryAttemptHistoryTests` expects `abort_cause` on the aborted attempt (Ot); `FailedClearRestoresTheStopTests.test_a_save_that_fails_after_run_json_was_written_follows_the_disk` expects `clear-save-uncertain` (Ol).
- Design choice (OE): requiring git's plain message alone would refuse every clearance on a separately mounted directory (git stops at the mount with "Stopping at filesystem boundary"; `/tmp` is tmpfs on this machine, `/mnt/c` is drvfs). `_git_env` therefore sets `GIT_DISCOVERY_ACROSS_FILESYSTEM=1`, so git walks to `/` and the boundary message never appears for a legitimate location; it still refuses when it does.
- Design choice (PE): a success is journaled as `activation-use-confirmed` only on a reopen that actually marks the record `committed` while an `activation-use-unconfirmed` line is on record; the dedupe set is the keys since that line. `confirm_activation_use(..., report_success=True)` reports the write.
- Note (OR): under the creation rule (`activation-window-short`) `expires_at` is never before the wall-clock end, so for a run created by this code the wall clock already made such a stop durable; the new check matters for runs whose recorded window is shorter than their budget (created before that rule). The tests shorten the recorded window by a labelled mutation.
- Thread map (suffix of `PRRT_kwDOVjxExc62Pk…` → change → test class in the new module):
  - **OE** `_work_tree` allows only `NOT_A_WORK_TREE_RE` (plain discovery failure); discovery across file systems; `_git_entry_above` refuses any `.git` entry above the clearance when git reports no work tree → `DanglingGitfileTests`.
  - **P1** tests only → `WorkTreeTriStateTests`. **Pp** fake git answering in German unless `LC_ALL=C` → `GitLocaleTests`.
  - **O6** `os.stat`: no such file / permission denied / not a regular file (and its kind) → `ClearancePathKindTests`.
  - **QS** `abort_activation_use` uses `os.stat`; only `FileNotFoundError`/`NotADirectoryError` mean absent → `UnreadableRunDirectoryTests` (real mode-000 directory, `Path.exists` given its 3.13 semantics so a revert fails on 3.12 too; skipped as root).
  - **Pf** `_same_run` compares `_fold` of both paths → `StateDirFoldTests`. **Pi** `confirm_activation_use` returns `state-dir-mismatch` → `StateDirMismatchJournaledTests`.
  - **Ot** `activation_use` treats `attempts` that is not a list of dicts as unreadable; history capped at the first + last 10 (`MAX_RECENT_ATTEMPTS`); `abort_cause` recorded and moved into the history on retry → `AttemptHistoryValidationTests`. **QK** → `RetrySourceTests`.
  - **PS, PZ** id 0 refuses; 21 digits refuse → `EvidenceIdValueTests`. **O0** "inside, or inside a case variant of" in both refusals → `CaseVariantWordingTests`.
  - **Og** note when `abort_activation_use` returns False → `AbortFalseNoteTests`. **PE** dedupe set since the last confirmation, `strerror` for errno-less `OSError` → `UnconfirmedDedupeSetTests`.
  - **OR** `_clearable_clock_stop` needs `max(now, high_water) <= expires_at` → `ClearableOnlyInsideTheWindowTests`.
  - **OM** reconcile proceeds for a revoked (or already reconciled revoked) authorization under a clearable stop; a pending one refuses "clear the stop or cancel the run" → `ReconcileRevokedUnderClearableStopTests`. **PJ** docs line 97/118 → same class.
  - **OW** docs and `clear-clock-regression` help only → `ForwardSkewDocumentedTests`.
  - **Ol** reload shows the stop cleared: journal `activation-stop-cleared` with `save_uncertain`, refuse `clear-save-uncertain` (exit 3) → `ClearSaveUncertainTests`. **QD** → `FailedReloadRestoresTests`.
  - **P5** → `ClearSpentMemoInvalidationTests`.
- Not done here, by the Code Map's instruction (commit locally, do not push or touch GitHub): the replies, thread resolution and PR body refresh. The GitHub task stays open for the parent.

- Review pass 1: patches in `87c0e43`, nothing deferred. 685 tests OK on Python 3.14.4 and 3.12.14. git discovery runs with `GIT_DISCOVERY_ACROSS_FILESYSTEM=1` so a clearance on another mount (`/tmp` tmpfs, `/mnt/c` drvfs) is judged, not refused for the boundary.

## Spec Change Log

## Review Triage Log

Pass 1 (blind B1–B15, edge E1–E4, verification-gap V1–V2) on 0cfeb51:

| # | Finding | Verdict | Evidence / route |
|---|---------|---------|------------------|
| B1 | clearable rule and the clear judge the window on different clocks | medium | `_clearable_clock_stop` uses `max(now, hw)`, the clear uses `now`; resume abandons work a clear would save; patch (one rule) |
| B2/E2 | `_same_run` casefold loosens an identity check on case-sensitive file systems | medium | `/x/State` ≠ `/x/state` on ext4; patch (exact or `samefile`) |
| E1 | NUL in a recorded `state_dir` crashes the open | low | `realpath` raises `ValueError`, not caught; patch |
| B3 | docs contradict the code (state-dir mismatch, `NotADirectoryError`) | low | patch |
| B4 | errno-less `OSError` key falls back to `str(exc)` with a temp path | low | dedupe defeated again; patch |
| B5 | malformed `state_dir` reported as a moved directory; misnamed helper | low | patch |
| B6 | readability never checked; wording wrong | low | `os.stat` does not check `R_OK`; patch |
| B7 | empty `attempts` passes validation | low | patch |
| B8 | `BaseException` after the replace skips the coded refusal | low | interrupt during a clear; adds handling for a rare path; rejected |
| V2 | the `journaled=False` branch is untested | medium | pre-verified; patch (test) |
| B9/V1 | inclusive window edge and the `.git` lstat failure untested | medium | pre-verified (V1); patch (tests) |
| B10 | reconcile answers `clock-regression` for an unknown story/authorization | low | load before validate; patch |
| B11 | docs/help tests check wording | low | OW is docs-only by decision; rejected |
| B12 | abandonment test asserts conditionally | low | patch |
| B13 | spec paths, suffix, status | — | fix edits this build's spec; rejected by rule |
| B14 | mutation script is outside the repo | low | kept outside by design; the thread map names each test; rejected |
| B15 | zero-id check duplicates the loop | low | cosmetic refactor; rejected |
| E3 | a git `warning:` line refuses every clear | low | fails closed but blocks the owner; patch (ignore warnings) |
| E4 | test `finally` can raise AttributeError | low | patch |

## Verification

**Commands:**
- `python3 -m unittest discover -s automation/tests -t .` -- expected: all pass (625 before)
- `ls ~/.local/state/owl-mast` -- expected: does not exist
