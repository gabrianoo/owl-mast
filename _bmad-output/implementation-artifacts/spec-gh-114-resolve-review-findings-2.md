---
title: 'PR #114 round 3: resolve review 5851770529 and the two reopened threads'
type: 'bugfix'
created: '2026-11-11'
status: 'in-progress'
route: 'dispatch'
review_loop_iteration: 0
baseline_commit: '028b60cb8278f0b521261aa67176301e7202fcf0'
context:
  - '/tmp/claude-1000/-mnt-c-Users-gabrianoo-Work-aisquad-owlmast/cc143ade-28ef-4359-9698-9dedd1bcafec/scratchpad/wt114/docs/unattended-execution.md'
  - '/tmp/claude-1000/-mnt-c-Users-gabrianoo-Work-aisquad-owlmast/cc143ade-28ef-4359-9698-9dedd1bcafec/scratchpad/wt114/_bmad-output/implementation-artifacts/spec-gh-114-resolve-review-findings.md'
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** PR #114 has 21 open review threads at 028b60c: 19 from review 5851770529 (adversarial, edge-case and verification-gap lenses) and 2 reopened ones (r4531696320 self-clear, r4531696403 stale spec-gh-108). #108 has no open threads. The owner ranked five as fix-first: a run created twice from one activation, a self-written clearance, a clear spent without clearing, work lost under a clearable clock-regression stop, and the untested conflict-deferral path.

**Approach:** Fix the five fix-first findings first, then the other 16, each with a test that fails when the fix is reverted. Then reply to every thread on GitHub with the commit and test, and resolve it. A thread is declined only with a stated reason.

**Decisions (owner, 2026-11-11):**
- Self-clear (r4531696320): owner-only clearance stays a convention on the trusted machine. The docs and the `clear-clock-regression` help say so plainly, and a clearance file inside `--state-dir` or the repository work tree is refused (`clearance-invalid`). A GitHub-comment check is not used: the loop posts as the owner's account, so it would prove nothing.
- spec-gh-108 (r4531696403): the owner accepts both documented limits (the torn `status --read-only` read and the boundary advisory). Record that in spec-gh-108, mark the superseded ledger and clear notes, and keep `status: done`.

## Boundaries & Constraints

**Always:** fail closed (an ambiguous ledger or clear state refuses, it never allows); keep the trusted-machine statement (no new claim of authentication); one test per behaviour change that fails on revert; update `docs/unattended-execution.md` and the CLI help in the same commit as each behaviour change; post replies on GitHub per [[review-records-on-github]] (paginate reviewThreads).

**Never:** touch the shared checkout on `main` (another session's Java edits); change CI workflows or Helm packaging; fetch GitHub content to validate evidence URLs; add a flag or environment variable that relocates the use ledger.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| Confirm write fails | `save_run` ok, ledger `replace=True` write raises | run created; `activation-use-unconfirmed` journaled; record stays `pending` | delete run dir → `reserve` refuses `activation-used` ("creation unconfirmed") |
| save_run raises | ledger written, `run.json` absent | record marked `aborted`; same run id + state dir retries | other run id → `activation-used` naming the aborted run and how to retry |
| Process dies between ledger and run.json | record `pending`, no `run.json` | refused `activation-used` (unconfirmed); re-issue | — |
| Clear, save fails | `clear-started` journaled, `save_run` raises | stop stays; retry of the same stop allowed | after a successful clear, a second stop → `clock-clear-exhausted` |
| Clearable clock stop | stop `clock-regression`, no clear spent, run otherwise healthy | resume defers (exit 3, `deferred: true`); work bind refuses `clock-regression`, nothing bound | after the clear, the deferred steps complete |
| Conflict + race_unsettled, no file | LiveHarness, claim readable | `activation-required`, `deferred: true`, ops `['claim']`, no GitHub calls | — |

</frozen-after-approval>

## Code Map

All work happens in the PR #114 worktree `/tmp/claude-1000/-mnt-c-Users-gabrianoo-Work-aisquad-owlmast/cc143ade-28ef-4359-9698-9dedd1bcafec/scratchpad/wt114` (branch `t3/pr108-review-findings`); every path below is relative to it. Never edit `/mnt/c/Users/gabrianoo/Work/aisquad/owlmast`, which is another session's checkout on `main`. Commit locally in the worktree when done; do not push or touch GitHub (replies are posted afterwards).

- `automation/unattended/activation.py` -- `record_activation_use` / `confirm_activation_use` / `_same_pending_creation` (ledger states `pending`→`committed`, new `aborted`); `ledger_root:368` (KeyError → `activation-ledger-unwritable`); `EVIDENCE_URL_RE:64` (`pullrequestreview` only under `pull/`); `evidence_problems:198` (compare numeric ids); `load_clearance:475` (path refusal, decision A).
- `automation/unattended/state.py:504-580` -- `ensure_run`: on `save_run` failure mark the record `aborted` (only if `run.json` is absent); journal `activation-use-unconfirmed` when the confirm fails.
- `automation/unattended/coordinator.py` -- `__init__:330` pre-check (`run-not-found` before creation problems when `create` is false); `_durable_run_stop:529` (option to skip a clearable clock stop); `bind_receipt:1210-1245` (clearable stop refuses the work bind; `--for-cleanup` needs a reason, refused under a current activation); `_journal_once:1742` (one journal read per resume); `resume:1799-1937` (clearable stop defers; a deferred resume on an active story refuses with `ops: ['revisions']`); `clear_clock_regression:1961` (`clear-started` / `cleared` lines, exhaustion rule, elapsed from `max(now, high_water)`); `status` (ledger state and root).
- `automation/unattended/cli.py:133-180` -- `check-activation`: `--expect create|advance`, `ledger_root`, `run-metadata-missing`, the clock high-water check; `bind-receipt --reason`.
- `automation/tests/__init__.py`, `automation/tests/test_activation.py` (`LiveHarness`) -- make the ledger override hold however the tests are loaded; add a cross-directory copy test on one shared root.
- `automation/tests/test_pr114_round3_findings.py` (new) -- one test class per finding. Reuse `LiveCase`, `regress`, `clearance` from `test_pr114_review_findings.py` and `arm_failure_after_claim` from the `test_pr115_*` modules.
- `docs/unattended-execution.md:68,117-121`, `_bmad-output/implementation-artifacts/spec-gh-108-resolve-review-findings.md` -- docs and the superseded notes.

## Tasks & Acceptance

**Execution:**
- [x] `activation.py`, `state.py` -- ledger: `aborted` state, an unconfirmed `pending` refuses, journal the confirm failure, KeyError refusal, per-user wording -- fix-first 1, threads ii, ka, i0, i5
- [x] `activation.py`, `coordinator.py`, docs, CLI help -- clearance: path refusal, plain convention wording -- fix-first 2, r4531696320
- [x] `coordinator.py` -- clear write-ahead and exhaustion rule; elapsed time on the high-water mark -- fix-first 3, threads io, jw
- [x] `coordinator.py` -- clearable clock-regression defers instead of abandoning -- fix-first 4, thread jU
- [x] new test module -- conflict/race_unsettled deferral test and recorded-stop-over-policy-drift test -- fix-first 5, threads lB, lN
- [x] `coordinator.py`, `cli.py` -- `--for-cleanup --reason`; deferred resume always refuses; `run-not-found` order; `_journal_once` cost -- threads jN, je, jl, k2
- [x] `cli.py` -- check-activation `--expect`, `run-metadata-missing`, high-water mark, `ledger_root` -- threads j8, kJ, kQ, i0
- [x] `activation.py` -- evidence shape and numeric-id comparison -- threads kp, kv
- [x] `automation/tests/__init__.py`, `test_activation.py` -- ledger override robustness and cross-copy test -- thread jE
- [x] `spec-gh-108-resolve-review-findings.md` -- supersession markers and the owner decision -- r4531696403
- [ ] GitHub -- reply to and resolve all 21 threads; refresh the PR body

**Acceptance Criteria:**
- Given the full suite, when run, then it passes, and reverting any fix listed above fails at least one named test.
- Given PR #114 after the push, when its review threads are listed with pagination, then none is unresolved and each of the 21 has a reply naming the commit and the test (or the reason for declining).

## Implementation Notes

- Baseline `028b60c`, 528 tests OK. After this change: 561 tests OK (`python3 -m unittest discover -s automation/tests -t .`), 33 new in `automation/tests/test_pr114_round3_findings.py`. The suite wrote nothing under `~/.local/state/owl-mast`.
- Revert check: each fix was reverted on its own (29 single-site mutations, one per behaviour, script kept outside the repository) and every mutation failed at least one named test in `test_pr114_round3_findings.py` or `test_pr114_review_findings.py`.
- Thread map (suffix of the `PRRT_kwDOVjxExc619-…` id → change → test class in the new module):
  - **ii, ka** ledger states: `pending` / `committed` / `aborted` (`activation.abort_activation_use`, `_retryable_creation`, `use_refusal`); `Store.ensure_run` marks `aborted` when `save_run` raises with no `run.json`, confirms before `run-started` and journals `activation-use-unconfirmed` (once per error, also on reopen) when the confirmation fails; a retried aborted creation is set `pending` again → `UnconfirmedCreationTests`, `AbortedCreationTests`.
  - **i0** per-user wording in the module comment, docstrings, docs and candidate header; `check-activation` prints `ledger_root`, `status` prints `activation.ledger` → `LedgerRootTests.test_check_activation_and_status_print_the_ledger_root_and_record`.
  - **i5** `ledger_root` turns `KeyError` into `activation-ledger-unwritable`; `check-activation` reports it as a problem (exit 2) → `LedgerRootTests.test_a_uid_without_an_account_entry_refuses_instead_of_crashing`.
  - **r4531696320** (decision A) `load_clearance(refuse_inside=…)`; the CLI refuses a clearance inside `--state-dir`, `--repo-root`'s git work tree or the tool's own work tree, the coordinator refuses one inside its state directory; docstrings, help and docs say owner-only is a convention → `ClearancePlacementTests`.
  - **io** `activation-stop-clear-started` before `save_run`, `activation-stop-cleared` after; `_clear_spent` → `ClearWriteAheadTests`.
  - **jw** the clear judges the wall clock on `max(now, high_water)`; docs and help name the tolerance → `ClearWallClockOnHighWaterTests`.
  - **jU** `_durable_run_stop(skip_clearable=True)` / `_clearable_clock_stop`: `resume` defers with `clock-regression`, `bind-receipt` refuses a work bind and binds nothing; `--for-cleanup` still binds → `ClearableClockStopTests`.
  - **lB** → `ConflictRaceUnsettledDeferralTests` (`arm_failure_after_claim` gained a `run` parameter). **lN** → `RecordedStopOverPolicyDriftTests`.
  - **jN** `bind-receipt --reason` required with `--for-cleanup` (`reason-required`), journaled; refused under the presented current activation (`cleanup-not-needed`) → `ForCleanupReasonTests`.
  - **je** a deferred resume on an active story always refuses; `ops: ['revisions']` when only the revision check was skipped → `DeferredResumeAlwaysRefusesTests`; the round-2 test that expected success is updated and says why.
  - **jl** the unlocked pre-check refuses `run-not-found` before any creation rule when `create` is false (no document at all still reports `activation-required` first) → `RunNotFoundFirstTests`. Three earlier tests that pinned creation codes on `status` are adapted and say why (`test_enabling_repair_1.R1MissingRunMetadataTests` now drives `reserve`, `test_enabling_repair_3` expects `run-not-found`).
  - **k2** `_journal_once` shares one journal read per `resume` → `JournalOnceCostTests`.
  - **j8, kJ, kQ** `check-activation --expect create|advance`; `run-metadata-missing` for retained artifacts; `clock-regression` when the clock is more than the tolerance behind the high-water mark → `CheckActivationExpectTests`.
  - **kp, kv** `pullrequestreview` only under `pull/`; citations compared by `int` id → `EvidenceIdTests`.
  - **jE** `automation/tests/__init__.py` captures the production function once (a second load of the package cannot record the override as production) and `install_test_ledger()` is idempotent and called by every `LiveHarness`; cross-directory copy on one shared root → `TestLedgerOverrideTests`.
  - **r4531696403** `spec-gh-108-resolve-review-findings.md`: superseded markers on the ledger and clear notes and on the two ledger triage rows, the owner decision on the two limits recorded, `status: done` kept.
- Not done here, by the Code Map's instruction (commit locally, do not push or touch GitHub): the GitHub replies, thread resolution and the PR body refresh. The task stays open for the parent.

## Spec Change Log

## Review Triage Log

## Design Notes

- **Ledger states.** `pending` (written before `save_run`), `committed` (after), `aborted` (the `except` around `save_run` marks it only when `run.json` does not exist; if marking fails the record stays `pending` and the original error is re-raised). Only `aborted` + same run id + same realpath state dir may retry. `pending` without `run.json` is ambiguous (crash or deleted directory) and refuses `activation-used` with an "unconfirmed creation" message naming its run id and state dir. Opening an existing run confirms `pending` or `aborted`. This replaces the earlier claim that a dead process never burns the document: document that change.
- **Clear exhaustion.** Journal `activation-stop-clear-started` (detail names the stop's `observed_at`) before `save_run`, `activation-stop-cleared` after. The clear is spent when a `cleared` line exists, or a `clear-started` line exists for a stop other than the one recorded now. A `clear-started` for the current stop means the save failed: the retry proceeds.
- **Clearable clock stop.** `clock-regression` with the clear not spent and the run not cancelled. When no other durable cause applies (policy drift, wall clock), `resume` treats it like `deferred` (code `clock-regression`, nothing abandoned) and `bind-receipt` refuses a work bind with `clock-regression` and binds nothing (`--for-cleanup` still works). Once the clear is spent, the stop behaves as today.
- **Deferred resume.** On an active story it always refuses with `deferred: true`; ops include `revisions` when only the revision check was skipped. Update the existing test that expects success.
- **`check-activation --expect`.** `create` → exit 0 only when `can_create`; `advance` → only when `current`. Without the flag, the current behaviour is kept. Exit 2 otherwise.
- **Evidence ids.** Two citations are the same when their numeric ids are equal (`int`), whatever the kind.
- Reverting any fix must fail a test. Name each test after the behaviour, in a new module `test_pr114_round3_findings.py`.

## Verification

**Commands:**
- `python3 -m unittest discover -s automation/tests -t .` -- expected: all tests pass (528 before this change, plus the new ones)
- `gh api graphql --paginate --slurp ... reviewThreads` -- expected: 0 unresolved threads on #114 and #108
