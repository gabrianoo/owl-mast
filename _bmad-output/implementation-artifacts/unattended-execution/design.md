# ENG-01 design: state machine, writers and guarantees (repair round 2)

Companion to `../spec-unattended-execution-foundation.md`. Operator guide: `docs/unattended-execution.md`. This revision follows two independent review rounds: the machine never writes Project Status; every effect is a write-ahead intent with a stable operation identity and its complete payload; admission (reserve) precedes delegation and re-reads revisions; evidence gates re-read the actual worktree; ownership is released only with terminal task evidence; operations are serialized by a store lock; run state is bound to its environment; and every state command refuses the real transport.

## Components (`automation/unattended`)

| Module | Responsibility |
| --- | --- |
| `policy.py` | Strict TOML policy: allowlist, epic inclusion flags, contract-design exceptions, budgets, T3 targets, check/probe commands, write rules. Refuses secret-like keys/values, `apply_task_checkboxes`, `merge != owner`, more than two repair rounds, more than one implementer, unknown sections, empty checks/probes, targets without an effort option. |
| `github.py` | `Transport` protocol (reads plus `post_comment` only) and the `gh`-backed implementation flagged `live = True`; PR reviews read across all pages with total/shape verification; error classification; marker rendering/parsing. |
| `backlog.py` | Snapshot normalization with a strict declaration grammar (`None` or comma-separated ids, optional final period; exactly one line); `depends_on_known` / `epic_prerequisites_known` flags; `verify_mapping` (19/85/340, labels, parents, task numbering, declarations, Project items, `TASKS.md` cross-check). |
| `eligibility.py` | Fail-closed `decide`: allowlist → epic exclusion → declaration known → Project item/Stable ID → closed/reopened/active/blocked → owner gate (`Ready`) → dependencies and epic prerequisites (`Done` and closed as completed, declarations known) → contract-design exception. |
| `state.py` | Run binding (repo + policy digest + environment fixture/live), store-wide non-blocking `fcntl` lock re-entrant per coordinator instance, per-story checkpoint with worker state, append-only journal, write-ahead intents keyed by operation id carrying the full comment body and preconditions, atomic file replacement. |
| `receipts.py` | Validates T3 `delegate_task` receipts against the policy targets (provider, model, every option such as effort, isolation, fresh task id). |
| `coordinator.py` | The per-story state machine (reserve → bind-receipt → … → proposed); closure/revision helpers; worktree re-read at evidence gates; per-reviewer objection logic over all review pages; terminal task evidence; live gate on every operation. |
| `probes.py` | Permission probe (`basic_access` observation; `bounded` and activation never granted by the probe), environment probes (fail fast), deterministic check runner (full set), comment-only live write probe restricted to `engineering-automation` issues. |
| `cli.py` | One JSON document per command; every command that can reach a write needs `--live`; no asserted check result exists. |

## Story phases

```
reserve ──(admission under lock, revisions re-read, claim marker)──> claim-incomplete ──(marker exactly once)──> reserved
reserved ──bind-receipt (receipt validated, worktree identity, delegation counted)──> claimed            worker: running
claimed ──record-head──> implemented                                                                      worker: returned
implemented ──run-checks (full set, exact clean HEAD, HEAD re-checked)──> checks-passed | checks-failed
checks-passed ──request-review (worktree re-read, fresh reviewer receipt)──> review-requested               worker: running
review-requested ──record-review (worktree re-read)──> review-approved | changes-requested                  worker: returned
checks-failed | changes-requested ──repair (budgeted, round ≤ 2, fresh implementer receipt)──> claimed ; round 3 ──> blocked
checks-failed | changes-requested ──record-head──> REFUSED (repair-required)
review-approved ──record-head(new sha)──> implemented (approval invalidated)
any evidence gate with unreported worktree change ──> implemented (check and review evidence invalidated)
review-approved ──propose-evidence (revisions, worktree, PR head/reviews/checks)──> proposed
any active | conflict ──block | cancel (terminal task evidence while a worker is running)──> blocked | cancelled
duplicate marker on any effect (first run or resume) ──> conflict
```

`proposed`, `blocked`, `cancelled` and `conflict` are terminal for the machine. A story is admitted at most once per run; a later run may admit it after the release marker. `Done`, closing the issue, ticking tasks, Project Status, merging and deploying are owner or GitHub facts the machine reads and never writes.

## External effects and their identity

| Local event | GitHub effect | Operation id | Payload and recovery |
| --- | --- | --- | --- |
| reserve | comment `kind=claim` | `claim` | body persisted with the intent; preconditions = revisions; pending ⇒ re-verified then replayed on resume; exactly one marker required; foreign unreleased claim ⇒ refuse |
| propose-evidence | comment `kind=proposal sha=… pr=…` | `proposal-<sha12>-pr<n>` | body persisted; preconditions = sha, pr, revisions; replay only after revisions, worktree and PR (head, all review pages, checks) re-verify; GitHub regression ⇒ intent abandoned, nothing posted |
| block | comment `kind=block` | `block` | phase and intent saved in one write; failure recorded; replayed on resume |
| cancel | comment `kind=release` | `release` | as block; requires terminal task evidence while a worker is running |
| bind-receipt, repair, review request, head, checks, review verdict | none | — | local checkpoint + journal; receipts and commit SHAs are the evidence |

## Precise guarantees

1. **Revisions before admission and before effects.** `reserve` compares the plan snapshot's revisions of the closure against a fresh read and refuses on any difference; the fresh decision must also be dispatchable. `propose-evidence`, a proposal replay and `resume` compare against the revisions recorded at admission. No revision is ever replaced implicitly; `rebase-revisions` is explicit and journaled.
2. **One writer per field.** The machine appends comments only. Project Status synchronization is not implemented because GitHub offers no compare-and-swap and the field belongs to the owner.
3. **Stable operation identity with payload.** Every effect is a write-ahead intent keyed by operation id, carrying its marker and complete body. Retries and restarts find the intent and post that body. Zero markers ⇒ post, one ⇒ adopt, more than one ⇒ `conflict`.
4. **Terminal atomicity.** `block` and `cancel` save the terminal phase and the cleanup intent in a single atomic write before posting; a crash anywhere afterwards leaves a pending cleanup that `resume` replays.
5. **Restart order.** `resume` refuses on the live transport, validates the worktree identity before any effect, replays pending cleanups, re-verifies pending advancing effects (claim: revisions; proposal: revisions, worktree, PR) before posting their persisted body, then refuses active phases whose revisions changed.
6. **Serialization and binding.** Every operation holds the store lock and reloads run accounting inside it. A run is bound to its repository, policy digest and environment (`fixture` or `live`); reopening with another refuses before recovery, so fixture-born state can never drive production.
7. **Admission before delegation; no reclaim.** `reserve` admits under the lock before any task exists; `bind-receipt` binds exactly one receipt; a story has at most one state per run.
8. **Budgeted repair.** After `checks-failed` or `changes-requested` only `repair` returns the story to `claimed`; `record-head` is refused.
9. **Executed checks and re-read worktree.** `run-checks` requires the claimed worktree, HEAD equal to the recorded sha, a clean tree, runs the full configured set and re-checks HEAD and cleanliness. `request-review`, `record-review` and `propose-evidence` re-read the worktree identity, HEAD and cleanliness; an unreported change invalidates check and review evidence (phase `implemented`, head set to the actual HEAD).
10. **Per-reviewer objections over all pages.** Reviews are read until `pageInfo.hasNextPage` is false; a malformed page, a changed total or a count below the total refuses. A reviewer's latest effective review (`APPROVED`, `CHANGES_REQUESTED`, `DISMISSED`) at any commit decides.
11. **Ownership until terminal evidence.** While a delegated task is running (`worker_state`), `cancel`/`block` require `{taskId, status}` matching the bound task with a terminal status; `cancel-run` stops admissions and reports stories still awaiting termination.
12. **Fail closed.** Unknown declarations, unknown close reasons, missing Project items, inconsistent issue state, `PermissionDenied`, `Outage`, `NotFound`, unknown transport errors, binding and environment mismatches, worktree mismatches refuse without advancing.
13. **Live gate.** Every state-advancing operation and every recovery refuses a live transport with `live-execution-disabled` and the verified gaps. The only live write is the comment-only probe on `engineering-automation` issues.

## Why not bmad-loop

`bmad-loop` 0.13.2 dispatches from `sprint-status.yaml`, `stories.yaml` or a `tickets.py` tree, none of which is GitHub; its sprint key grammar `N-M-slug` and the sprint parser's `Epic N`/`Story N.M` headings reject `E01`/`OM-01.01`; `[verify]`/`[environment]` entries are empty; tmux CLI adapters ignore `effort`; its merge-back and cleanup act on local branches. The foundation keeps T3 as the sole coordinator and stores machine state under `.unattended-runs/`, separate from `.bmad-loop/`, which stays untouched.
