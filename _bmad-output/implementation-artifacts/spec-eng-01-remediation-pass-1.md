---
title: 'ENG-01 remediation pass 1 — six final-disposition defects in the unattended execution foundation'
type: 'bugfix'
created: '2026-11-06'
status: 'in-review'
route: 'dispatch'
review_loop_iteration: 0
baseline_commit: 'a0fa769ee5cd8dfb44fa02cae181bf0d37fad6ee'
context:
  - '{project-root}/docs/engineering-tracking.md'
  - '{project-root}/_bmad-output/implementation-artifacts/spec-unattended-execution-foundation.md'
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** The final exact-commit disposition of PR #107 (comment 6686575345, reviewed head `a0fa769ee5cd8dfb44fa02cae181bf0d37fad6ee`) verified six HIGH defects in `automation/unattended`: a cancelled run replays a pending proposal (`cancelled → proposed`); a locally rejected implementation can still be proposed on replay; reviewer ownership is lost through `record-head` (even at the same SHA) or phase invalidation; a crash between the saved `done` claim intent and the `reserved` transition strands the story; duplicate stable IDs collapse through `by_id()` and get admitted; and delegation capacity is checked only after a task was launched. The owner authorized one bounded remediation pass beyond the exhausted two-round limit, followed by a fresh independent review.

**Approach:** Fix the six defects in the coordinator/state/backlog/eligibility modules with adversarial combined-transition and crash/restart tests for each, keep every live-transport gate and fixture→live mismatch protection, keep the default allowlist empty, and correct the evidence and docs so they state exactly what is fixed, what is fixture-covered and what remains an explicit qualification blocker. Nothing is merged, pushed, scheduled, activated or dispatched.

## Boundaries & Constraints

**Always:** Keep `live-execution-disabled` on every state command and `environment-mismatch` on fixture-born state; keep comment-only GitHub effects, no owner-field writes, the `ubuntu-26.04` CI pin, the product SPEC/epics/stories/task IDs and all unrelated files untouched. Every advancing effect re-validates its preconditions from current local state (phase, exact-SHA approval, active task) and fresh GitHub revisions before posting. Budgets are enforced from durable state, before any launch. Unsupported or untested requirements stay explicit blockers with the smallest supported next step; green tests are not qualification.

**Never:** Invent a T3 API, hook or transport; treat `timeoutMs` as a child lifetime bound; claim restricted permissions from the existing broad token; run live execution, dangerous denial probes, merges, schedules, pushes, OM-01.02 dispatch, deployments, releases, credential creation; weaken the synchronization contract or present owner-only Status updates as automated synchronization; invoke subagents, provider CLIs or `bmad-loop`.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| D1 cancel abandons advancing intents | pending proposal (POST failed) then `cancel`/`block`/`cancel-run`; restart; `resume` | release/block posted; proposal intent `abandoned` in the same atomic save as the terminal phase; `resume` posts no proposal, phase stays terminal | run cancelled (crash before story cancel) + active story with pending advancing intent → `resume` abandons it, posts nothing, story stays owned for `cancel-run` |
| D2 replay needs current approval | pending proposal; then local `changes-requested`, new HEAD, or worktree invalidation; `resume` | proposal intent `abandoned` at invalidation time; `resume` replays only when phase is `review-approved` and `approved_sha == head_sha == intent sha` | otherwise abandoned, nothing posted |
| D3 independent active task | reviewer task bound; `record-head` (same or new SHA) or dirty-tree invalidation | `active_task` (id, role) unchanged; `cancel`/`block` without that task's terminal evidence refused `worker-not-terminal`; implementer evidence refused for a reviewer task | `record-head` while an implementer task is active without its terminal evidence → refused |
| D4 atomic claim completion | crash after the claim comment, between intent `done` and `reserved` | one save carries intent `done` + phase `reserved`; `resume` reconciles a legacy `claim-incomplete` with a `done` claim intent to `reserved` without posting; same for `review-approved` + `done` proposal → `proposed` | N/A |
| D5 duplicate stable IDs | planned or fresh snapshot with two issues carrying the same `owl-mast-id` | `plan` → `ambiguous-identity`; `reserve`, `resume`, `propose-evidence`, `rebase-revisions` refuse before `by_id()` reduction; no state, no comment | N/A |
| D6 pre-launch capacity | `reserve`, `authorize-review`, `authorize-repair` when `max_delegated_tasks` or repair cap would be exceeded | refused before any launch; an issued authorization is counted durably whether or not bound; `bind-receipt` consumes exactly one pending authorization | repeat authorize → same pending authorization (no double count); bind twice / bind without authorization / wrong role receipt → refused; corrupted `run.json` counters cannot bypass (budgets derive from story files) |

</frozen-after-approval>

## Code Map

- `automation/unattended/coordinator.py` -- state machine; defects live in `_terminal` (no intent abandonment), `resume` (replays pending intents regardless of run/story state, no local approval check, no reconciliation of done intents), `record_head` (`worker_state = "returned"` for any role; same-SHA early return), `_require_worker_terminal` (picks receipts by phase), `reserve` (`snapshot.by_id()[story]` after `decide`), `_budget(delegation=True)` only at bind/request-review/repair (post-launch). Reuse `_new_intent`, `_post_intent`, `_verify_worktree`, `_validate_pr`, `outstanding_objections`, `closure`, `revision_diff`.
- `automation/unattended/state.py` -- `StoryState.worker_state` (single string) → replace with `active_task`, `task_history`, `authorizations`; `PHASES`/`ACTIVE_PHASES` gain `review-authorized`, `repair-authorized`; `from_dict` must refuse unknown schemas; `RunState` counters become derived caches.
- `automation/unattended/backlog.py` -- `Snapshot.by_id()` silently collapses duplicates; add `duplicate_ids()`; `verify_mapping` already names duplicates (keep).
- `automation/unattended/eligibility.py` -- `decide` must return `ambiguous-identity` before any `by_id()` lookup.
- `automation/unattended/cli.py` -- commands `request-review`/`repair` (receipt after launch) → `authorize-review`/`authorize-repair` (pre-launch), `bind-receipt` consumes any role, `record-task-terminal`, `--task-evidence` on `record-head`/`record-review`; `WRITE_COMMANDS` updated.
- `automation/tests/support.py`, `fake_transport.py`, `test_coordinator.py`, `test_sync.py`, `test_cli_and_probes.py`, `test_eligibility.py`, `test_transport.py` -- adapt the harness to the authorize→bind protocol; add `test_final_findings.py` with the adversarial scenarios.
- `docs/unattended-execution.md`, `_bmad-output/implementation-artifacts/unattended-execution/{design,evidence,permissions}.md`, `spec-unattended-execution-foundation.md` -- correct overclaims (rows marked "none" for crash/restart, cancellation, budgets), record remediation pass 1, keep blockers explicit.
- Do not change: `backend/**`, `.github/workflows/ci.yml` (`ubuntu-26.04` pin stays), `automation/policy.toml` allowlist (empty), `automation/examples/first-run-om-01-02.toml`, product specs, `.bmad-loop/`, root `.java-version`.

## Tasks & Acceptance

**Execution:**
- [x] `automation/unattended/state.py` -- `active_task`/`task_history`/`authorizations` on `StoryState`; new phases; strict `from_dict`; `Store.story_counts()` for derived budgets -- D3, D6.
- [x] `automation/unattended/backlog.py` -- `Snapshot.duplicate_ids()` -- D5.
- [x] `automation/unattended/eligibility.py` -- `ambiguous-identity` decision before reduction -- D5.
- [x] `automation/unattended/coordinator.py` -- abandon advancing intents at terminal/invalidation; `resume` gated on run/story state with reconciliation and exact-SHA approval; independent active task with terminal evidence; atomic `_post_intent(phase_after)`; duplicate-id refusal at every snapshot read; pre-launch `authorize_*` with durable counting and `bind_receipt` consumption; `record_task_terminal`; run-cancelled guard on advancing operations -- D1–D6.
- [x] `automation/unattended/cli.py` -- new/renamed commands and flags -- D3, D6.
- [x] `automation/tests/*` -- harness adaptation; `test_final_findings.py` (combined transitions, crash/restart, fresh-coordinator reloads) -- all rows.
- [x] docs and evidence companions -- accurate state after pass 1; blockers unchanged where unproven.

**Acceptance Criteria:**
- Given the reviewed-head probe script that reproduced all six defects, when it is re-run against the remediated code, then every advancing step it relied on is refused or leaves the expected state (cancelled stays cancelled, no proposal after rejection, ownership kept, reserved after crash, duplicate refused, budget refused pre-launch).
- Given `python3 -m unittest discover -s automation/tests -t .`, when it runs, then every test passes with none skipped and each matrix row has at least one covering test that ran.
- Given the real transport, when any state command is attempted, then it is still refused with `live-execution-disabled` before any GitHub read.
- Given the evidence matrix, when read, then no row claims "none" for a requirement whose qualification needs a real T3 worker, a bounded credential or Project Status synchronization.

## Implementation Notes

- 2026-11-06: step-02 planned directly (no subagents, per owner instruction). No intent gaps: every choice below is routine and recorded. Nothing irreversible: local files, no pushes. Footprint: five modules, the test suite, four docs. Spec kernel exceeds 1600 tokens because six verified defects must each carry a matrix row; kept whole because they are one remediation deliverable reviewed as one exact commit.
- Design choices (mine, user would not notice): authorizations are issued by `reserve` (implementation), `authorize-review` and `authorize-repair`; each is durable on the story, idempotent while pending, counted against `max_delegated_tasks` whether or not it is ever bound (conservative: an issued slot is spent); `bind-receipt` consumes the pending one and sets `active_task`; `record-head`/`record-review` accept `--task-evidence` and clear the matching active task; `record-task-terminal` is the role-agnostic acknowledgment. Budgets are computed from story files under the lock, never from `run.json` counters. The tool cannot see launches; it bounds what can be bound and documents that an unbound launched task is the coordinator's to cancel.

- 2026-11-06, implementation: all six defects reproduced on `a0fa769e` first (scratch probe, old API; transcript in `unattended-execution/evidence/final-findings-repro-before-2026-11-06.txt`), then fixed. Suite: 170 tests pass, none skipped (137 adapted to the authorize→bind protocol, 33 new in `test_final_findings.py`). After-probe transcript: `final-findings-repro-after-2026-11-06.txt`. Fixture `verify-mapping` ok 19/85/340; dry-run plan `awaiting-owner-acceptance`, writes 0. Live gate re-verified for every state command including the new ones (`live-gate-all-state-commands-refused-2026-11-06.json`), zero GitHub reads or writes. Matrix audit: D1 → `D1CancellationAbandonsAdvancingIntents` (6), D2 → `D2ProposalReplayRequiresCurrentApproval` (5), D3 → `D3ActiveTaskOwnershipIsIndependent` (6), D4 → `D4ClaimCompletionIsAtomic` (5), D5 → `D5DuplicateStableIdsAreRefused` (5), D6 → `D6CapacityIsAuthorizedBeforeLaunch` (6); every covering test ran and passed. Surprise: the conflict-phase resume test previously expected `Conflict` to be re-raised by replaying the claim; a terminal story now abandons the claim and posts nothing, which is the stricter behavior; the test was updated accordingly and the change is noted in the evidence matrix. Not done, by scope: no live lifecycle, no credential, no denial probe, no T3 launch; blockers stay explicit in `unattended-execution/evidence.md`. Review-ready: hand back to the coordinator for a fresh independent review.

## Spec Change Log

## Review Triage Log

## Verification

**Commands:**
- `python3 -m unittest discover -s automation/tests -t . -v` -- expected: all pass, none skipped.
- `PYTHONPATH=. python3 automation/tests/probe_final_findings.py` -- expected: every scenario reports the refusal or the preserved state named in the matrix.
- `python3 -m automation.unattended --snapshot automation/tests/fixtures/backlog-snapshot-2026-11-06.json verify-mapping` -- expected: ok, 19/85/340.
- `python3 -m automation.unattended --snapshot automation/tests/fixtures/backlog-snapshot-2026-11-06.json --policy automation/examples/first-run-om-01-02.toml plan` -- expected: `awaiting-owner-acceptance`, writes 0.
