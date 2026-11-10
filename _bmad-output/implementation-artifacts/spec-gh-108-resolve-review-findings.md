---
title: 'Resolve the bmad-review findings on PR #108 (ENG-01 activation opt-in)'
type: 'bugfix'
created: '2026-11-09'
status: 'done'
route: 'oneshot'
review_loop_iteration: 0
context: []
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** PR #108 (merged 2026-11-07 at `09dfc69e5ef5f576681b1363a939905f82944b1c`) carries a bmad-review (review 5827052511 on 2026-11-09) with 21 findings: 20 inline comments on `automation/unattended/{coordinator,cli,activation,state}.py`, the ENG-01 spec and the preflight artifact, plus one unanchored finding on target-option typing. None is resolved on `main`; they weaken the activation opt-in that gates every live run.

**Approach:** Work through the 21 findings one by one on a new branch from `main`, fixing each in the code, tests or artifacts it names, declining none. Push the result as a new PR, reply to every inline thread with what was done, and keep CI green.

</frozen-after-approval>

## Implementation Notes

- Baseline: `main` at `137e084`, 339 automation tests OK. Branch `t3/pr108-review-findings`.
- Finding map (comment id → fix):
  - 4513640212 bind-receipt, 4513640218 resume, 4513640228 reconcile-retained-execution: a missing `--activation` is a temporary condition, never a run stop. New `Coordinator._durable_run_stop()` (cancelled, wall clock, recorded `activation_stop`) drives cleanup-capable operations; `bind-receipt` on a run that is not stopped refuses `activation-required` before any state change (unless the authorization is revoked, which is cleanup); `resume` defers advancing reconciliation and replays without saving or abandoning (`resume-advancing-deferred` journal event); `reconcile-retained-execution` refuses `run-not-stopped`.
  - 4513640239 / 4513640249 check-activation: `--run-id` required; `Activation.problems` takes a mandatory run id; success-path CLI test (exit 0, `current: true`, empty state dir, no transport call).
  - 4513640263 evidence: `evidence.*` must be a GitHub comment or review URL under the policy repository (`https://github.com/<owner>/<repo>/(issues|pull)/N#issuecomment-N` or `#pullrequestreview-N`); placeholders (`REPLACE`, `<`, `>`) refuse. Checked in `Activation.problems` (`activation-invalid`) so the committed candidate still loads and `check-activation` explains it.
  - 4513640278 status writes: `status --read-only` (`Coordinator.status(read_only=True)`) takes no lock and writes nothing, reporting `would_stop`; the default stays a locked, durable observation and is documented as a write.
  - 4513640293 clock regression: `clear-clock-regression --reason` (owner-only, journaled) clears only a recorded `clock-regression` stop under the presented, current activation and re-anchors the high-water mark; `activation-expired` is never cleared.
  - 4513640306 clocks: `RunState.started_at` is the same validated creation observation as `validated_at`; `Coordinator.__init__` now samples it inside the store lock (`Store.ensure_run(owner=...)` re-enters the coordinator's lock).
  - 4513640321 run-open: `Store.ensure_run` re-reads the activation source for an existing live run too (`run-open`) before comparing it with the recorded binding.
  - 4513640333 path-less Activation: `Activation.__post_init__` requires a source path; the `refresh_activation` bypass is gone.
  - 4513640346 scope: stories must be strings, duplicates refuse at load, equality is on sorted tuples.
  - 4513640355 window coverage: `Activation.creation_problems` adds `activation-window-short` when `expires_at - now < max_wall_clock_minutes`; used by run creation and `check-activation`, never mid-run.
  - 4513640367 `--live` help built from `sorted(WRITE_COMMANDS)`.
  - 4513640375 AC8 of the ENG-01 spec says 336 (277 + 11 + 17 + 19 + 12).
  - 4513640387 preflight status block labelled "as of 2026-11-07 at f71167b".
  - 4513640411 unlocked snapshot: CLI test where the snapshot call expires or edits the activation; `reserve` refuses (`activation-expired` / `activation-mismatch`), no story state, no GitHub write.
  - 4513640423 one activation, one run: a use ledger `<activation>.used.json` is created atomically (`O_EXCL`) beside the source file right before `run.json`; a second creation from the same document refuses `activation-used` whatever the state dir.
  - 4513640435 `started_at` parsed strictly in `Store.load_run` (`run-state-invalid`).
  - 4513640440 `rebase-revisions` calls `_require_run_active`.
  - unanchored target options: `policy._target` refuses non-string option values (same rule as the activation loader).
- Verification (worktree of `t3/pr108-review-findings`): `python3 -m unittest discover -s automation/tests -t .` runs 379 tests OK (339 on `main` + 40 new in `test_pr108_review_findings.py`; two R3 tests in `test_enabling_repair_1.py` rewritten for the new bind-receipt and resume behaviour). `automation/policy.toml` is byte-identical to `main`. CI result and per-thread replies are recorded on the follow-up PR (the record of review resolution lives on GitHub).
- Blind Hunter (14 findings): patched 11, documented 2, deferred 1. Details in the Review Triage Log.
- Follow-up of 2026-11-11 (reviews 5828027825 and 5850902826 on PR #114, see `spec-gh-114-resolve-review-findings.md`): the one deferral (the path-bound ledger) is closed in the same PR, the ledger is keyed on the document digest in a per-machine directory and `deferred-work.md` no longer carries the entry. Two findings stay documented limits, not fixes: a read-only status may be torn across files, and the window-coverage check is advisory at its exact boundary. The Intent above says no finding is declined; whether these two count as declined is the owner's call, and that block is not edited here.

## Review Triage Log

- `check-activation` ignores the use ledger and reports `current: true` for a document that already created a run — medium, confirmed. Patched: `creation_problems` adds `activation-used`; CLI test added.
- Ledger keyed by file path, so a byte-identical copy gets a fresh ledger — medium, confirmed. Documented as a path-bound trusted-machine control (docstring, docs, candidate header); a digest-keyed machine-wide ledger deferred to `deferred-work.md`.
- Ledger written before `run.json`; a later failure burns the approval; `OSError` reported as `activation-invalid`; no `.gitignore` pattern — medium, confirmed. Patched: code `activation-ledger-unwritable`, recovery sentence in the docs and docstring, `*.used.json` ignored.
- Run-id check chained with `elif` to the digest check, so both drifts were not reported together, and an empty run id reported a spurious mismatch — high, confirmed (my own regression). Patched with an explicit guard; tests assert both messages and the single `activation-invalid` stop.
- `clear-clock-regression` not in `WRITE_COMMANDS`, no wall-clock or `now < started_at` check, `run-cancelled` branch untested — medium, confirmed in part. Patched: refuses before `started_at` (`clock-regression`) and after the wall clock (`wall-clock-exceeded`); tests for both and for the cancelled run. Not a GitHub write, so `--live` is not required; stated in the docs.
- Revoked-authorization exception to the bind-receipt rule undocumented and untested — low, confirmed. Patched: docs sentence and a test (a new head revokes the pending review authorization; its late receipt binds for cleanup without the file).
- AC8 count "wrong for main and the branch" — false as stated: AC8 records PR #108's own evidence at `09dfc69` (336), which is what the original review finding asked for. Patched the qualifier "at `09dfc69`" for clarity.
- Preflight artifact rows disagree on merge state — low, confirmed. Patched: the enabling-change row carries the same as-of label as the status block.
- Candidate header lists refusal codes without `activation-invalid` / `activation-window-short` / `activation-used` — low, confirmed. Patched.
- Docs command block ends with the writing `status`; preflight syntax lacks the new commands — low, confirmed. Patched both.
- `status --read-only` may read a torn set of files — medium, confirmed. Documented in the docstring and the docs; the locked form stays the coherent one.
- Window-coverage check advisory at the exact boundary (shell clock vs locked clock) — low, confirmed. Documented; no margin added (the owner re-issues with a later expiry).
- `rebase-revisions` tested only on a cancelled run — low, confirmed. Patched: a recorded `activation-expired` stop test added; the wall-clock branch shares `_require_run_active` with every other advancing operation.
- Spec lacks a verification and thread-reply record — low, confirmed. Patched: this entry and the verification note above; replies are recorded on the PR.
