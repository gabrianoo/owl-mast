---
title: 'Fix the five "fix first" findings of the PR #115 recheck review (ENG-01)'
type: 'bugfix'
created: '2026-11-09'
status: 'done'
route: 'oneshot'
review_loop_iteration: 0
context: []
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** The recheck review of PR #115 at `1e2ea5700a39951a539d6450c81c7d80baff78f6` (review 5832610891, 2026-11-09, 28 findings) names five to fix first: the cross-story single-active check is check-then-post with no re-check after the claim lands (`coordinator.py:893`, R10 still open); one stray or forged claim marker blocks every admission and only its author can clear it (`coordinator.py:798`); a live run bound to the legacy raw-bytes digest passes as bound but every advancing call refuses `activation-mismatch` (`activation.py:124`); a review receipt bound for cleanup only still needs a live reviewer worktree (`coordinator.py:1013`); a `claim-unverifiable` conflict is never settled again by `resume` (`coordinator.py:1543`).

**Approach:** Fix exactly those five on the same branch (code, tests, docs), push to PR #115, reply to and resolve their five threads, and leave the other findings of that review open for a later pass, listed for the owner.

</frozen-after-approval>

## Implementation Notes

- Baseline: `1e2ea57`, 408 tests OK, CI 6/6 green, tree clean apart from the untracked local `.java-version`.
- Fix map (review 5832610891 thread → change):
  - 1 / 4517895336 cross-story race: `_settle_claim_race(state, claim, issue, snapshot)` also reads `_claims_elsewhere` after our claim is visible; earliest `(created_at, comment_id)` across all allowlisted stories wins; a loss to another story cancels, releases and refuses `claim-active-elsewhere` (same story: `claim-race-lost`). Both `resume` claim paths pass their fresh snapshot. This also covers the body finding "done-claim reconciliation skips the cross-story gate" (the settle runs on that path).
  - 2 / 4517895365 stray or forged claims: `dismiss-claim --issue --comment-id --reason` (CLI, `WRITE_COMMANDS`) posts a `dismiss` marker naming the comment id as our identity (journaled `foreign-claim-dismissed`, idempotent, refuses a non-claim comment and this run's own claim); `_active_foreign_claims` ignores dismissed claims; the `claim-active-elsewhere` refusal names `dismiss-claim` and comment deletion as the ways out.
  - 3 / body "legacy raw-digest live runs": `Activation.problems` accepts `policy.raw_digest`; `Store.ensure_run` binds a new live run to the digest its activation names and checks it through `digest_bound`; the activation docstring updated.
  - 4 / 4517895390 cleanup-only review receipts: `cleanup` is computed before the worktree block; a review receipt under a stop or a revoked authorization binds on task identity alone (no `--worktree`, no identity check, `head_at_bind` null), a supplied path is still refused when shared or nested with the implementer's.
  - 5 / 4517895355 unverifiable claims: `resume` handles `conflict` + `blocked.race_unsettled`: still hidden ⇒ `claim-still-unverifiable`; visible ⇒ phase restored from `blocked.from_phase`, `claim-reverified`, then the normal settle (a loss cancels and releases); a stopped run withholds.
- Verification: `GITHUB_ACTIONS=true python3 -m unittest discover -s automation/tests -t .` → 419 tests OK (11 new in `automation/tests/test_pr115_recheck_findings.py`; the first count of 427 double-collected a TestCase imported from the sibling module, fixed).
- Left open on purpose (not in the requested scope): the other 19 inline threads and 3 body findings of review 5832610891.

## Review Triage Log

- TestCase class imported into the new module, collected twice — medium, patched: module-level `arm_failure_after_claim`, modules imported as namespaces.
- helper borrowed by instantiating a foreign TestCase — low, patched (same change).
- `resume` pending-claim pre-check cancels a landed claim that would have won — medium, patched: when our marker already landed the replay defers to the earliest-wins settle; both orders tested.
- cross-story loss journaled under `claim-race-lost`; Refused before the post, Conflict after — low, patched: journaled under `claim-active-elsewhere`; the two exception classes stay (both `UnattendedError` with the same code), documented in the codes table.
- cleanup-only review receipt records an unverified path indistinguishably; branch without worktree — low, patched: `worktree_verified: false`, both or neither.
- implementer cleanup-only receipts still need the worktree — true by design (the claim records it), documented in the codes table.
- a live run created under a raw-digest activation binds raw bytes, no cosmetic tolerance — low, documented (approve new activations with the canonical digest); consistent with legacy raw-bound runs.
- mismatch message names only the canonical digest — low, patched.
- still-hidden conflict needs `record-no-launch` before `cancel` — false: `_unreturned_authorization` resolves a `conflict` with an unsettled claim structurally, so `cancel` works without an attestation (covered by `test_a_claim_that_cannot_be_read_back_is_conflict_not_reserved`); the way out is now stated in the codes table.
- `dismiss-claim` posts without a write-ahead record and needs an existing run — medium, patched: `foreign-claim-dismiss-intent` journaled with the full body before the post; CLI help and docs say it needs the run.
- codes-table row for the reviewer worktree lacks the cleanup exception — low, patched.
- forged-dismissal assertion accepted two outcomes — low, patched: `_active_foreign_claims` asserted directly.
- style (conditional `mkdir`, in-body import) — low, patched.
- spec status and counts — closed by this finalization.
