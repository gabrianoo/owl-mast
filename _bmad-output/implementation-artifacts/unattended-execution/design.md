# ENG-01 design: state machine, writers and guarantees

Companion to `../spec-unattended-execution-foundation.md`. Operator guide: `docs/unattended-execution.md`.

## Components (`automation/unattended`)

| Module | Responsibility |
| --- | --- |
| `policy.py` | Strict TOML policy: allowlist, epic inclusion flags, contract-design exceptions, budgets, T3 targets, check/probe commands, write rules. Refuses secret-like keys/values, `apply_task_checkboxes`, `merge != owner`, more than two repair rounds, more than one implementer, unknown sections, empty checks/probes, targets without an effort option. |
| `github.py` | `Transport` protocol and the `gh`-backed implementation; error classification (`permission-denied`, `outage`, `not-found`, `transport-unknown`); marker rendering/parsing. |
| `backlog.py` | Snapshot normalization (stable id, kind, parent, `Depends on`, `Epic prerequisites`, tasks, Project item/Status/Stable ID, body hash) and `verify_mapping` (19/85/340, labels, parents, task numbering, dependency resolution, Project items, cross-check with `TASKS.md`). Derives the bmad-loop `N-M-slug` key for traceability only. |
| `eligibility.py` | Fail-closed `decide`: allowlist → epic exclusion → Project item/Stable ID → closed/reopened/active/blocked → owner gate (`Ready`) → dependencies and epic prerequisites (`Done` and closed as completed) → contract-design exception. |
| `state.py` | Run state, per-story checkpoint, append-only journal, write-ahead intents, atomic file replacement. |
| `receipts.py` | Validates T3 `delegate_task` receipts against the policy targets (provider, model, every option such as effort, isolation, fresh task id). |
| `coordinator.py` | The per-story state machine and its GitHub effects. |
| `probes.py` | Permission probe, environment probes, deterministic check runner (fail fast, output tails redacted), bounded live write probe restricted to `engineering-automation` issues. |
| `cli.py` | One JSON document per command; writes need `--live`; state commands need `--run-id`. |

## Story phases

```
claim ──> claim-incomplete ──(comment + Status Ready→In progress verified)──> claimed
claimed ──record-head──> implemented ──checks──> checks-passed | checks-failed
checks-passed ──request-review (fresh reviewer receipt)──> review-requested ──record-review──> review-approved | changes-requested
checks-failed | changes-requested ──repair (round ≤ 2, fresh implementer receipt)──> claimed ; round 3 ──> blocked
review-approved ──record-head(new sha)──> implemented  (approval invalidated)
review-approved ──record-review(changes-requested, same sha)──> changes-requested  (regression)
review-approved ──propose-evidence (PR head == approved sha, open, unmerged, no CHANGES_REQUESTED, CI not failing)──> proposed (Status In progress→In review)
any active ──block──> blocked (Status →Blocked) ; any active ──cancel──> cancelled (Status In progress→Ready restored)
```

`proposed` is terminal for the machine. `Done`, closing the issue, ticking tasks, merging and deploying are owner or GitHub facts the machine reads and never writes.

## GitHub projection

| Local event | GitHub effect | Order and verification |
| --- | --- | --- |
| claim | marker comment `kind=claim`; Status `Ready`→`In progress` | Intent recorded → comment (idempotent by marker, read back, duplicate marker = conflict) → Status check-then-write-then-verify. Foreign unreleased `claim` markers from another run refuse the claim. |
| repair, review request, head, checks, review verdict | none | Local checkpoint and journal only; receipts and commit SHAs are the evidence. |
| propose-evidence | marker comment `kind=proposal sha=… pr=…` with the task list; Status `In progress`→`In review` | Same protocol. Tasks are listed unchecked for owner application. |
| block | marker `kind=block`; Status `In progress`→`Blocked` | Local phase first; GitHub failure is recorded in `blocked.github_error`, never hidden. |
| cancel | marker `kind=release`; Status `In progress`→`Ready` | As block. |
| resume | adopts intents whose marker exists; re-posts those that do not; completes or abandons an incomplete claim depending on the current Status | Never overwrites a Status the owner changed. |

## Precise synchronization guarantees

1. **Pre-write staleness check.** `_write_status` reads the Project item and refuses (`stale-revision`) unless its Status equals the expected predecessor and its `updatedAt` equals the last value the tool verified (the snapshot's value for a first claim). This closes every concurrent edit that lands before that read.
2. **Post-write verification.** The item is read again; the operation proceeds only when the Status equals the target. The new `updatedAt` becomes the next expected value.
3. **No compare-and-swap.** GitHub's `updateProjectV2ItemFieldValue` and issue-comment APIs accept no expected revision. An edit inside the window between step 1 and the mutation is overwritten and is not detectable afterwards (a same-value write does not even change `updatedAt`, observed live on 2026-11-06). The suite pins this limitation; the tool does not claim atomicity.
4. **Append-only comments.** Markers are unique per `(kind, run, story, seq)`. Retries and duplicate events find the existing comment. Two comments with one marker mean a concurrent writer; the tool raises `conflict` and stops.
5. **Write-ahead intents.** Each GitHub effect is recorded as a pending intent before it is attempted and completed after it is read back. A crash in between leaves a pending intent that `resume` reconciles against GitHub.
6. **Fail closed.** `PermissionDenied`, `Outage`, `NotFound`, unknown transport errors, unreadable snapshots, missing Project items and inconsistent issue states refuse without advancing a phase. `block` and `cancel` keep their local phase even when GitHub is unreachable and record the error.
7. **One writer per field.** The machine writes only `In progress`, `In review`, `Blocked` and restores `Ready`; it never writes `Done`, `Backlog`, issue bodies or issue state. Tests assert the absence of merge and `Done` paths.

## Why not bmad-loop

`bmad-loop` 0.13.2 dispatches from `sprint-status.yaml`, `stories.yaml` or a `tickets.py` tree, none of which is GitHub; its sprint key grammar `N-M-slug` and the sprint parser's `Epic N`/`Story N.M` headings reject `E01`/`OM-01.01`; `[verify]`/`[environment]` entries are empty; tmux CLI adapters ignore `effort`; its merge-back and cleanup act on local branches. Wrapping it would add a second runner with its own board. The foundation therefore keeps T3 as the sole coordinator and stores machine state under `.unattended-runs/`, separate from `.bmad-loop/`, which stays untouched.
