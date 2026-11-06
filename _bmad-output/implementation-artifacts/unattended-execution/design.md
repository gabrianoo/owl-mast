# ENG-01 design: state machine, writers and guarantees (repair round 1)

Companion to `../spec-unattended-execution-foundation.md`. Operator guide: `docs/unattended-execution.md`. This revision replaces the initial design after independent review: the machine no longer writes Project Status, every effect has a stable operation identity, admission re-reads revisions, operations are serialized by a store lock, and live product admission is refused.

## Components (`automation/unattended`)

| Module | Responsibility |
| --- | --- |
| `policy.py` | Strict TOML policy: allowlist, epic inclusion flags, contract-design exceptions, budgets, T3 targets, check/probe commands, write rules. Refuses secret-like keys/values, `apply_task_checkboxes`, `merge != owner`, more than two repair rounds, more than one implementer, unknown sections, empty checks/probes, targets without an effort option. |
| `github.py` | `Transport` protocol (reads plus `post_comment` only) and the `gh`-backed implementation flagged `live = True`; error classification; marker rendering/parsing. |
| `backlog.py` | Snapshot normalization with a strict declaration grammar (`None` or comma-separated ids, optional final period; exactly one line); `depends_on_known` / `epic_prerequisites_known` flags; `verify_mapping` (19/85/340, labels, parents, task numbering, declarations, Project items, `TASKS.md` cross-check). |
| `eligibility.py` | Fail-closed `decide`: allowlist → epic exclusion → declaration known → Project item/Stable ID → closed/reopened/active/blocked → owner gate (`Ready`) → dependencies and epic prerequisites (`Done` and closed as completed, declarations known) → contract-design exception. |
| `state.py` | Run binding (repo + policy digest), store-wide non-blocking `fcntl` lock re-entrant per coordinator instance, per-story checkpoint, append-only journal, write-ahead intents keyed by operation id, atomic file replacement. |
| `receipts.py` | Validates T3 `delegate_task` receipts against the policy targets (provider, model, every option such as effort, isolation, fresh task id). |
| `coordinator.py` | The per-story state machine; closure/revision helpers; per-reviewer objection logic; live gate. |
| `probes.py` | Permission probe (`basic_access` vs `bounded`), environment probes (fail fast), deterministic check runner (full set), comment-only live write probe restricted to `engineering-automation` issues. |
| `cli.py` | One JSON document per command; every command that can reach a write needs `--live`; no asserted check result exists. |

## Story phases

```
claim ──> claim-incomplete ──(claim marker exactly once)──> claimed
claimed ──record-head──> implemented ──run-checks (full set, exact clean HEAD, HEAD re-checked)──> checks-passed | checks-failed
checks-passed ──request-review (fresh reviewer receipt)──> review-requested ──record-review──> review-approved | changes-requested
checks-failed | changes-requested ──repair (budgeted, round ≤ 2, fresh implementer receipt)──> claimed ; round 3 ──> blocked
checks-failed | changes-requested ──record-head──> REFUSED (repair-required)
review-approved ──record-head(new sha)──> implemented  (approval invalidated)
review-approved ──record-review(changes-requested)──> changes-requested  (regression)
review-approved ──propose-evidence (revisions unchanged, PR head == sha, open, unmerged, no outstanding objection, CI not failing)──> proposed
any active | conflict ──block──> blocked ; any active | conflict ──cancel──> cancelled
duplicate marker on any effect (first run or resume) ──> conflict
```

`proposed`, `blocked`, `cancelled` and `conflict` are terminal for the machine. `Done`, closing the issue, ticking tasks, Project Status, merging and deploying are owner or GitHub facts the machine reads and never writes.

## External effects and their identity

| Local event | GitHub effect | Operation id | Recovery |
| --- | --- | --- | --- |
| claim | comment `kind=claim` | `claim` | pending ⇒ replay on resume; exactly one marker required; foreign unreleased claim ⇒ refuse |
| propose-evidence | comment `kind=proposal sha=… pr=…` | `proposal-<sha12>-pr<n>` | retry after crash reuses the id; second comment never allocated |
| block | comment `kind=block` | `block` | local phase set first; GitHub failure recorded; replayed on resume |
| cancel | comment `kind=release` | `release` | as block |
| repair, review request, head, checks, review verdict | none | — | local checkpoint + journal; receipts and commit SHAs are the evidence |

## Precise guarantees

1. **Revisions before admission and before effects.** `claim` compares the plan snapshot's revisions of the closure (story, parent epic, direct dependencies, prerequisite epics and all their stories: issue `updatedAt`, body hash, state, state reason, Project item `updatedAt`, Status) against a fresh read and refuses on any difference; the fresh decision must also be dispatchable. `propose-evidence` and `resume` (active phases) compare against the revisions recorded at admission. No revision is ever replaced implicitly; `rebase-revisions` is explicit and journaled.
2. **One writer per field.** The machine appends comments only. Project Status synchronization is not implemented because GitHub offers no compare-and-swap and the field belongs to the owner; the previous check-then-write design was removed as unsafe.
3. **Stable operation identity.** Every effect is a write-ahead intent keyed by operation id with a marker carrying that id. Retries and restarts find the intent and its marker. Zero markers ⇒ post, one ⇒ adopt, more than one ⇒ `conflict` (the story leaves the active set; only `cancel`/`block` can follow).
4. **Restart order.** `resume` validates the worktree identity before any effect, then replays pending intents (terminal cleanups included), then completes an incomplete claim only if revisions are unchanged (otherwise it releases the claim), and for active phases refuses on changed revisions.
5. **Serialization and binding.** Every operation holds the store lock (non-blocking; `store-busy` on contention) and reloads run accounting from disk inside it. A run is bound to its repository and policy digest; reopening with another refuses before recovery.
6. **Budgeted repair.** After `checks-failed` or `changes-requested` only `repair` (budget-counted, receipt-validated, at most two rounds) returns the story to `claimed`; `record-head` is refused.
7. **Executed checks only.** `run-checks` requires the claimed worktree, HEAD equal to the recorded sha, a clean tree, runs the full configured command set, re-checks HEAD and cleanliness afterwards, and records every command. `request-review` requires that record: all commands present with exit 0, HEAD unchanged, tree clean. No command records an asserted pass.
8. **Per-reviewer objections.** A reviewer's latest effective review (`APPROVED`, `CHANGES_REQUESTED`, `DISMISSED`) at any commit decides; another reviewer's approval never clears an objection.
9. **Fail closed.** Unknown declarations, missing Project items, inconsistent issue state, `PermissionDenied`, `Outage`, `NotFound`, unknown transport errors, run-binding mismatches and worktree mismatches refuse without advancing a phase.
10. **Live gate.** `claim` refuses on a transport flagged `live` with `live-execution-disabled` and the list of T3 enforcement gaps. The only live write is the comment-only probe on `engineering-automation` issues.

## Why not bmad-loop

`bmad-loop` 0.13.2 dispatches from `sprint-status.yaml`, `stories.yaml` or a `tickets.py` tree, none of which is GitHub; its sprint key grammar `N-M-slug` and the sprint parser's `Epic N`/`Story N.M` headings reject `E01`/`OM-01.01`; `[verify]`/`[environment]` entries are empty; tmux CLI adapters ignore `effort`; its merge-back and cleanup act on local branches. The foundation keeps T3 as the sole coordinator and stores machine state under `.unattended-runs/`, separate from `.bmad-loop/`, which stays untouched.
