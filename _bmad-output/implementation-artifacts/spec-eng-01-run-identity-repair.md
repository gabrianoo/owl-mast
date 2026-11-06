---
title: 'ENG-01 — Explicitly authorized third repair: retained task/run identity'
type: 'bugfix'
created: '2026-11-07'
status: 'in-review'
route: 'dispatch'
baseline_commit: '56c077cea9245759e4f2d023a13011509a85e416'
context:
  - docs/unattended-execution.md
  - docs/engineering-tracking.md
  - _bmad-output/implementation-artifacts/spec-eng-01-trusted-operation.md
  - _bmad-output/implementation-artifacts/unattended-execution/design.md
---

## Intent and authorization

The user explicitly authorized a third repair after the two earlier slots were consumed. Scope is one focused implementation pass and one fresh independent exact-commit review; stop and report substantive unresolved findings afterward. The owner accepted trusted-machine operation, best-effort bounds, broad credentials disclosed, manual owner Status. Fix the mismatch between actual retained T3 task/new-run behavior and the foundation's fresh-task-per-repair assumption. No new T3 runtime or machine setup is needed. This is engineering automation, not product authentication or activation.

## Observed contract

Original implementation task/thread survives repair resumption. Actual repair run ordinal5 completed at 2026-11-06T23:00:54.928Z and produced 313087f056bdbaeb59296eeab3b1a68a114c0013. thread_send returned runId but no taskId. Original coordinator recovered task_status: workState=result_available, hasPendingChildRuns=false, latestTerminalStatus=completed, latestTerminalRunId=ordinal5. childRunId and original summary still point to ordinal1; repair result is latestTerminalSummary. No fresh delegated-task node exists. Current coordinator cannot task_status the old task because it belongs to the earlier coordinator, but can read/wait its thread/run. This evidence is trusted coordinator input, not platform-attested provenance.

## Required behavior

1. Treat executions as actual (taskId, runId) pairs. Preserve taskId as task_cancel handle; never substitute a run ID for a task ID. Validate explicit provider/model/effort and isolated ownership as before. A repair may reuse the same implementer task only for a fresh run of that retained owner after predecessor terminal. Reject replayed pair, wrong owner/story/role, ambiguous/missing run identity and concurrency. Fresh independent reviewer tasks remain mandatory; a new run on an old reviewer task is not fresh review.
2. Bind terminal evidence to the exact authorized execution. Prefer the actual latestTerminalRunId/latestTerminalStatus for task_status-shaped evidence, not stale childRunId/status/summary. Refuse a matching task with wrong run, latest terminal mismatch, live current/pending child work, nonterminal/cancel_requested or ambiguous fields. Document the canonical normalized receipt and terminal shapes for coordinator reports. Validate metadata against known dispatch evidence; never infer missing identity by guessing.
3. Provide explicit audited cleanup of the historical cancelled run whose revoked authorization was launched but never bound. It must require exact authorization, actual retained owner task and actual repair run, matching terminal evidence, reason/provenance and existing worktree/ownership correlation. Resolve only that obligation for cleanup; retain cancellation, history and budgets; never re-authorize work, approve a SHA or create a no-launch attestation. Must be idempotent for identical evidence and refuse conflicting evidence. Preserve pre-migration backup and handle legacy task-only state conservatively; no silent loss of unresolved obligations and no manual JSON edits. Choose the smallest supported implementation after inspecting actual state/schema.
4. Preserve reservation-before-launch, environment and repository/policy binding, locks, cancellation/restart guards, stale revisions, budget/denial/outage failure stops and default repair limits. This exceptional third repair does not globally raise policy repair caps.

## Scope and files

Inspect actual automation/unattended/{receipts,state,coordinator,cli}.py and smoke helper/tests. Update identity storage/validation, minimal schema compatibility/recovery, CLI/helper inputs and operator/design documentation as required. Add meaningful regression tests for same task/new run repair, replay, wrong run/owner, stale task_status fields, active/pending children, reviewer reuse, cancellation acknowledgement and historical cleanup/restart. Keep existing regression guarantees; adapt fixtures explicitly to truthful new schema, not by weakening negative tests.

## Acceptance

- Given valid retained owner plus a new run, when its reserved repair is bound, only that pair owns the execution; old terminal evidence cannot clear it.
- Given stale or ambiguous status, replayed pair, another story/owner or reused reviewer task, when presented, advancement refuses without releasing ownership.
- Given the exact historical revoked authorization and completed ordinal5 evidence, when explicit reconciliation runs, the cancelled run becomes cleanly releasable without approval or new admission; repeated identical recovery is harmless, conflicting recovery refuses.
- Given legacy state with insufficient evidence, recovery preserves it and reports the precise missing facts rather than inferring completion.
- Given live/product transport, all state transitions remain refused. Default allowlist empty; product contracts/mapping and ubuntu-26.04 unchanged.

## Execution and boundaries

Use existing T3-created /home/gabrianoo/.t3/worktrees/owlmast/t3-08a6bd98, branch t3/unattended-execution-foundation. Same Claude Fable5.1 High owner, parent GPT-6 Astra High, fresh Astra High reviewer. No subagents/provider CLIs, pushes or remote writes from implementer. Parent handles publication. Read rendered BMAD workflow already rendered for this conversation; do not render again. No merge/schedule/deploy/release/live collection, product execution, OM-01.02, branch/worktree deletion, .java-version change or secrets. No edits to installed T3 or private content copied to GitHub.

Read historical evidence at /home/gabrianoo/.local/state/owlmast-eng01/trusted-20261106 only; do not mutate it. Parent will exercise reviewed recovery against an isolated copy, then the stopped synthetic source with backup if successful. Actual cancellation qualification remains separate; no additional smoke worker is authorized by this repair brief.

Budget established before launch: two sequential workers (one retained implementation run, one fresh review), best-effort 60 minutes from 2026-11-06T23:19Z to 2026-11-07T00:19Z, implementer stop/report by23:45Z. Stop on failed verification, unknown ownership or new substantive findings; no fourth repair automatically. Manual maintenance authorization is separate from the cancelled synthetic run and must not be represented as its next execution.

## Verification and delivery

Run full automation unittest suite, focused identity/recovery regressions, diff check and protected-path comparison against baseline. Commit scoped changes locally and report exact SHA, changed behavior, tests, remaining assumptions and concrete recovery commands. Set spec in-review, parent performs independent review before mutation of historical state or push. Never claim code review/fixtures complete actual unattended qualification.


## Implementation Notes

- 2026-11-07 (implementation run, stopped before 23:45Z): executions are `(taskId, runId)` pairs in `receipts.py` (`execution_run_id`, retained-owner allowance, replay refusal), `state.py` (`executions`, `owner_task`, `predecessor_terminal`, `Store.bound_executions`; schema stays 3 with optional run fields), `coordinator.py` (`normalize_task_evidence` for both shapes using only the latest terminal fields; `_apply_task_evidence` bound to the exact pair, legacy task-only active tasks refused with `run-identity-missing`; `bind_receipt` retained path for repairs only, reviewers never reused; `reconcile_retained_execution` with dispatch/time correlation, backup, idempotency, conflict refusal, no re-authorization/approval/admission/no-launch), `cli.py` (`reconcile-retained-execution`), `lifecycle_smoke.py` (`reconcile`, `--run-id`, legacy `fixture-transport.pickle` loading).
- Fixtures adapted to the truthful schema (`run_of`, `evidence`, receipts carry `runId`); no negative test weakened. New `test_run_identity.py` (13 tests): evidence shapes, wrong run, same task/new run repair, replayed pair, ambiguity, missing run, reviewer reuse, other story, legacy active task, historical reconciliation (resolution, idempotency, releasability, old run / wrong authorization / missing correlation / conflicting evidence / worktree / provenance refusals, restart), and a reconciliation of a temporary copy of the historical run with the user-supplied snapshot (skipped where that copy is absent).
- Assumptions: receipts, terminal evidence, dispatch records and timestamps are the coordinator's reports; the historical `issued_at` (22:58:39Z) precedes ordinal5's `startedAt` (22:58:39.527Z) and ordinal4 started earlier, which is the correlation used. No historical state was mutated; the parent exercises recovery on an isolated copy first.
