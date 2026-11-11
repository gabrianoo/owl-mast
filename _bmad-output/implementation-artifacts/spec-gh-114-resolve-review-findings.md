---
title: 'Resolve the review findings on PR #114 and the reopened PR #108 threads (ENG-01 activation opt-in)'
type: 'bugfix'
created: '2026-11-11'
status: 'done'
route: 'oneshot'
review_loop_iteration: 0
context: []
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** PR #114 (`t3/pr108-review-findings`, head `773bd4c98b2ada7d3b7426195d7705acbe77cd58`) carries two bmad-reviews (5828027825 with 24 inline comments, 5850902826 with 22 inline comments and one unanchored finding), all open, and four threads of the merged PR #108 were reopened against it. The branch also conflicts with `main` after PR #115 merged.

**Approach:** Bring the branch up to date with `main`, work through every open thread on both pull requests in the code, tests and documents of PR #114, push the result to that PR, reply to each thread with what was done and resolve it on GitHub.

</frozen-after-approval>

## Implementation Notes

- Baseline: `origin/main` at `143584b` merged into the branch (16 conflict hunks in 7 files). Where `main` and the branch disagreed, both rules are kept: `check-activation` without `--run-id` still reports the policy digest and looks no run up (`main`, PR #115 round 4) and is current for nothing, exit 2 (PR #108 finding: no run-less currency). Two `main` tests were adapted and say why (`test_pr115_recheck_round4`, `test_enabling_repair_3`, which created a run through `status`).
- Thread map (several threads describe the same defect; each group has one fix):
  - **Read-only status and run creation** (#114 coordinator.py:290 twice, cli.py:193; #108 coordinator.py:1440). `Coordinator(read_only=True)` opens without the lock, the state directory, the lock file or a write and refuses every locked operation; the CLI uses it for `status --read-only`. `Coordinator(create=False)` / `Store.ensure_run(create=False)` refuse `run-not-found`; the CLI creates a run only from `reserve`.
  - **`clear-clock-regression`** (#114 coordinator.py:1485 twice, :1513 twice; #108 coordinator.py:134). Needs an owner clearance (`--clearance`, `load_clearance`: `run_id`, `activation_id`, `approver`, `stop_observed_at`, `reason`), which the loop is never given and which names one stop. Refuses while the clock is more than the tolerance behind the high-water mark, keeps that mark, and works once per run (`clock-clear-exhausted`). Decision: the stricter of the two options the reviewer offered. Judging time as `max(now, high-water)` would let work continue on a clock that is stuck behind; waiting until the clock has caught up costs the same budget and trusts no slow clock. `--live` is not required: the command writes nothing to GitHub.
  - **Use ledger** (#114 activation.py:205, :183 twice, :347, :335, :321, :204, :342, state.py:421 twice, .gitignore:20 twice; #108 state.py:418). One record per document digest under `~/.local/state/owl-mast/activation-ledger/` (`activation.ledger_root`; no flag or environment override, the suite replaces the function in `automation/tests/__init__.py`). Written through a temporary file, an exclusive link and a directory sync; `pending` until `run.json` exists, then `committed`, so a failed creation is retried by the same state directory and run id and is refused for any other. A re-issued document has its own record. `*.used.json` is no longer ignored (nothing is written beside the document). The `deferred-work.md` entry for the digest-keyed ledger is closed and the file, which only this branch had added, is removed.
  - **`check-activation`** (#114 cli.py:114, activation.py:197). `current` for a run that exists (the run's own document, still current, no recorded stop), `can_create` for one that does not; `stops` lists every code and `activation-used` ranks ahead of the time codes.
  - **Deferred resume** (#114 coordinator.py:1394, :1409 twice, :1410, the unanchored revision-check finding; #108 coordinator.py:1330). `reconciliation-deferred` journal event, written once per unchanged situation; no GitHub read; the call refuses with the activation's code and `deferred: true`. The unsettled-claim and unverifiable-claim branches, which `main` added, defer too.
  - **Stops** (#114 coordinator.py:448, :443, :442). `_run_stop` is `_durable_run_stop() or _activation_stop()`; policy drift (from `main`) is a durable cause; a recorded stop outranks the wall clock, tested.
  - **Evidence rule** (#114 activation.py:156 twice, :158, :58, :161). Moved to `creation_problems` (never mid-run), whole-value match with ASCII digits, slug compared without case, the two keys must differ. The content of the cited comments is not fetched; documented.
  - **Lost activation file** (#114 coordinator.py:866, :868). `bind-receipt --for-cleanup` binds a launched task for cleanup only; the comment and docs now say that the refusal changes no story or budget state while the gate may still write `run.json`.
  - **Smaller items.** `Activation.__post_init__` raises `ActivationError` (activation.py:118). The coordinator re-reads the source after the locked open (state.py:434). Direct `Store.ensure_run` short-window test (state.py:415). The pre-check is documented as advisory, with a no-footprint test (coordinator.py:281). `LiveHelpTests` reads the option's own help (test line 418). The monitoring command in the docs carries `--policy` and `--state-dir` (docs line 66). Policy loader: duplicates and non-strings were already refused on `main` (activation.py:148 twice, policy.py:95). A wall-clock budget that does not fit one activation window is refused when a run is created, with its own message, not at policy load: a load-time ceiling would also refuse every cleanup command of a run that already exists under such a policy (activation.py:187).
  - **Spec of the earlier round** (#114 spec-gh-108 line 17). A note in that spec records that its one deferral is closed here and that two findings stay documented limits. Its frozen intent is the owner's to reword.
- Not done, on purpose: evidence URLs are not resolved against GitHub (an advancing check that needs the network and a second trust decision); `record_activation_use` does not refuse an activation inside the work tree (the ledger no longer lives there, and an approved file in the tree is visible to `git status` again).
- `check-activation` without `--activation` now reports the policy digest (exit 2, current for nothing), which is what the docs and the candidate file on `main` already told the owner to run.
- Verification (worktree of `t3/pr108-review-findings`, `main` merged): `python3 -m unittest discover -s automation/tests -t .` runs 528 tests OK (482 after the merge, 46 new in `test_pr114_review_findings.py`). `automation/policy.toml` is byte-identical to `main`. The suite writes nothing under the home directory. CI and the per-thread replies are recorded on PR #114.

## Review Triage Log

Blind Hunter on the staged diff against `main` (12 findings):

- The ledger directory followed `$HOME` — medium, reproduced by the reviewer. Patched: the home directory comes from the account database; a test sets `HOME` and `XDG_STATE_HOME`.
- The two evidence keys could cite one comment under two URL spellings — medium, reproduced. Patched: the comment fragment is compared.
- `check-activation` reported `current: true` for a cancelled or over-time run — medium, reproduced. Patched: both are problems of an existing run; tests added.
- The once-per-run clear limit read a journal line written after the state change — medium, reproduced. Patched: the journal line is written first; test with a failing journal.
- A stale `clear-clock-regression` paragraph in the docs contradicted the new one, and the example lacked `--activation` — low, confirmed. Patched.
- A missing run without `--activation` reports `activation-required`, not `run-not-found` — low, confirmed. Kept (existing tests on `main` pin the activation refusal first for commands without the file); the docs now say which refusal comes first.
- The candidate file told the owner to use the file sha256 and a command that needed `--activation` — low, confirmed (the lines came from `main`). Patched: wording, and `check-activation` reports the digest without an activation.
- A damaged ledger record was reported as a run "None under None" — low, reproduced. Patched: its own message in both refusals; test added.
- The 1440-minute policy ceiling was itself unactivatable and stranded runs under larger budgets — medium, confirmed by reading. Patched: the load-time ceiling is back at `main`'s value and the rule moved to run creation.
- A `pending` record can outlive a created run when the confirmation fails and the run directory is deleted before any reopen; `abspath` compared — low. Patched in part: `realpath` is compared and the docs name the retry. A failed confirmation still does not fail the creation: `run.json` exists by then, and the next open settles it.
- A deferred resume with nothing to defer exits 0 without the revision check — low, confirmed. Patched: `resume-revisions-unverified` is journaled once.
- The suite redirects the ledger by an import-time patch and production keeps a parameter for it — low, rejected: a per-test fixture would touch some thirty test modules for no change in behaviour, and the one test of the production rule restores the real function.
