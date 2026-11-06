---
title: 'ENG-01 — Unattended execution foundation (GitHub-authoritative dispatch, sync and T3 coordination)'
type: 'feature'
created: '2026-11-06'
status: 'in-review'
route: 'dispatch'
review_loop_iteration: 0
baseline_commit: 'c5d9d2eff121423223bf75607c89dd1c55015813'
context:
  - '{project-root}/docs/engineering-tracking.md'
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** `docs/engineering-tracking.md` forbids unattended story execution until a bridge is qualified: installed `bmad-loop` 0.13.2 only reads local sprint/stories/tickets queues, its parser rejects `E01`/`OM-01.01` IDs, its probes/verify commands are empty and its CLI adapters ignore reasoning effort, so nothing today lets a T3 coordinator dispatch, synchronize and gate story work with GitHub Issues/Projects as the progress authority.

**Approach:** Add a small, dependency-free Python tool (`automation/unattended`) that reads the actual GitHub backlog and Project, verifies the stable mapping (19 epics, 85 stories, 340 tasks, native parent links, `Depends on` lines), decides eligibility fail-closed, and drives a machine-owned per-story checkpoint/journal state machine whose only GitHub effects are idempotent marker comments and bounded Project Status writes. T3 remains the sole coordinator: the tool validates T3 task receipts (Claude Fable 5.1 `effort=high` implementer, fresh Codex GPT-6 Astra `reasoningEffort=high` reviewer), enforces checks-before-review, SHA-bound approval, at most two repair rounds, one implementer per story and cancel/resume/stop controls. Tracking identifier: GitHub issue #106 (ENG-01), outside OM numbering.

## Boundaries & Constraints

**Always:** Keep the product `SPEC.md`, epics, stories, task IDs and issue bodies unchanged. GitHub owns progress; the machine writes only Project Status values `In progress`, `In review`, `Blocked` (and restores `Ready` on cancel) plus append-only marker comments; `Ready`, `Done`, closing issues and ticking task checkboxes stay owner actions, and task completion reaches GitHub only as an evidence proposal naming the exact commit. Every GitHub write re-reads the target before and after the write and refuses on a stale `updatedAt`/status; the tool documents that GitHub exposes no compare-and-swap, so the residual race between the pre-write check and the write is reported, not hidden. Unknown eligibility, denied permission, outage, parse failure, missing Project item or a receipt that lacks the required model/effort fails closed and never advances state. Credentials come only from the `gh` CLI session (or `GH_TOKEN` provided through the supported secret path); the policy file refuses secret-like keys. Exclude E17 and E19 from default dispatch; dispatch only stories in an explicit allowlist with `Ready` status and `Done`+closed dependencies, except designated contract-design portions listed in policy.

**Never:** Merge, deploy, release, schedule, enable a persistent loop, start product stories (OM-01.02 remains separately authorized), edit issue bodies or checkboxes, close issues, write sprint-status.yaml, run or wrap the `bmad-loop` CLI, store tokens in config or state, claim live-transport qualification from fixture tests, or present fixture coverage as qualification before independent review.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| Mapping verified | live snapshot of issues + Project | report: 19 epics, 85 stories, 340 tasks, every story parented to its epic, every issue has a Project item with matching Stable ID, all `Depends on` targets exist | any mismatch → nonzero exit, named discrepancies |
| Plan, owner gate | allowlisted story with Status `Backlog` | decision `awaiting-owner-acceptance`, nothing written | N/A |
| Plan, dependency | allowlisted story whose dependency is not `Done`+closed | decision `blocked-by-dependency` naming it | reopened dependency (`Done` but OPEN) → `unknown`, fail closed |
| Plan, excluded epics | E17/E19 story in allowlist, flags off | decision `excluded-epic` | N/A |
| Plan, not allowlisted / unknown ID | story absent from allowlist or snapshot | `not-allowlisted` / `unknown-story` | fail closed |
| Claim | eligible story, valid implementer receipt, worktree identity | checkpoint written, marker comment posted, Status `Ready`→`In progress` | second claim for same story or any other active claim → refused |
| Stale write | Project item `updatedAt` changed since snapshot | write refused as `stale-revision`, no effect | N/A |
| Duplicate event / retry | same marker posted twice; transient failure then retry | exactly one comment; retry reuses existing | outage → `outage` blocker, no state change |
| Partial write / crash | process dies after comment posted, before checkpoint | resume finds the marker on GitHub and adopts the effect | missing marker → intent stays pending |
| Checks before review | `request-review` without passing checks at head SHA | refused | N/A |
| SHA invalidation | new head SHA after approval | phase returns to `implemented`; approval kept as history only | N/A |
| Repair cap | third repair request | story `blocked` with reason, Status `Blocked` | N/A |
| Review regression | changes requested after approval at same SHA | approval invalid; repair path | N/A |
| Denied permission | 401/403 from GitHub | `permission-denied` blocker, nothing advanced | N/A |
| Cancel / resume | `cancel` then `resume` | claim released (Status back to `Ready`), resume refuses mismatched worktree/branch | N/A |
| Policy guard | secret-like key, `merge != owner`, checkbox application enabled, repair rounds > 2 | policy load fails naming the key | N/A |

</frozen-after-approval>

## Code Map

- `docs/engineering-tracking.md` -- binding tracking contract and six bridge properties; append a pointer to the new foundation, keep status semantics.
- `_bmad-output/planning-artifacts/epics/owl-mast-2026-11-05/TASKS.md` -- 340 task IDs; read-only cross-check source for mapping verification.
- GitHub: issues 1–19 (epics, `<!-- owl-mast-id: E.. -->`), 20–104 (stories, native `parent`, `**Depends on:**` line, `- [ ] **OM-xx.yy-Tn**` tasks); Project `PVT_kwHOACHLt84Bqc0U` fields Status (`Backlog/Ready/In progress/In review/Blocked/Done`), Stable ID; issue #106 = ENG-01 (label `engineering-automation`).
- `bmad-loop` 0.13.2 (`sprintstatus.py` key grammar `N-M-slug`, `worksource.py` sources, `policy.py` effort ignored by tmux CLIs) -- not reused; only a derived `N-M-slug` key is reported for traceability.
- T3 contracts: `orchestrator_capabilities` (providers/models/options), `delegate_task` (`target.options`, `isolation: worktree`), `task_status`, `task_cancel`, `t3_worktree_status`, `request_secret` -- the coordinator calls these; the tool consumes their receipts.
- `.github/workflows/ci.yml` -- add an automation unit-test job; `.gitignore` -- add `.unattended-runs/`.
- Do not change: `backend/**`, product specs, `.bmad-loop/policy.toml`, `.claude/settings.json`, `.codex/hooks.json`.

## Tasks & Acceptance

**Execution:**
- [x] `automation/unattended/policy.py`, `automation/policy.toml`, `automation/examples/first-run-om-01-02.toml` -- TOML policy with allowlist, budgets, targets, checks, probes, write rules; validation refuses secret-like keys and unsafe values -- requirement 4.
- [x] `automation/unattended/github.py` -- `Transport` protocol, `gh`-backed transport, error classification (`permission-denied`, `outage`, `not-found`, `unknown`) -- requirement 2.
- [x] `automation/unattended/backlog.py` -- snapshot normalization, mapping verification report, derived bmad key -- requirement 1/5.
- [x] `automation/unattended/eligibility.py` -- fail-closed decisions (allowlist, epic exclusion, owner gate, dependencies, contract-design exception, reopened/inconsistent) -- requirement 1.
- [x] `automation/unattended/state.py` -- run/story checkpoints, append-only journal, write-ahead intents, atomic writes, recovery -- requirement 2.
- [x] `automation/unattended/receipts.py` -- T3 task receipt validation against targets -- requirement 3.
- [x] `automation/unattended/coordinator.py` -- claim/record-head/run-checks/record-checks/request-review/record-review/repair/propose-evidence/block/cancel/resume/status with Status writes and markers -- requirement 3.
- [x] `automation/unattended/probes.py`, `automation/unattended/cli.py`, `automation/unattended/__main__.py` -- permission/environment probes, check runner, CLI -- requirement 4.
- [x] `automation/tests/*` -- stdlib `unittest` suite with fake transport and fault injection, real normalized snapshot fixture -- requirement 5.
- [x] `docs/unattended-execution.md`, `docs/engineering-tracking.md`, `.github/workflows/ci.yml`, `.gitignore` -- operator guide, pointer, CI job, ignored state dir.
- [x] `_bmad-output/implementation-artifacts/unattended-execution/{design,permissions,evidence}.md` -- companions: design/state semantics, permission matrix, requirements-to-evidence matrix with exact commands and results.

**Acceptance Criteria:**
- Given the live repository, when `verify-mapping` runs, then it reports 19/85/340 with all relationships satisfied and exit 0.
- Given policy allowlist `OM-01.02`, when `plan --dry-run` runs against live GitHub, then it writes nothing and reports the owner-gate decision.
- Given the unit suite, when `python3 -m unittest discover -s automation/tests -t .` runs, then every matrix row has a passing test.
- Given ENG-01 (#106), when `probe-write` runs twice, then exactly one marker comment exists and the Status write is verified by re-read.

## Implementation Notes

- 2026-11-06: Planned and implemented directly by the delegated implementation agent (no sub-delegation, per coordinator instruction). Spec kernel is ~1.9k tokens, above the 1600 guideline; kept whole because the bridge is one cohesive deliverable whose parts are not independently shippable, with detail moved to the `unattended-execution/` companions. No Open Questions: every remaining choice is routine and recorded here.
- Implemented as planned; one design correction during work: `Depends on` lines may name epics (e.g. OM-02.01 depends on E01), so epic dependencies resolve like epic prerequisites (all stories Done and closed). Live finding: a same-value Project Status write leaves `updatedAt` unchanged, so `updatedAt` cannot flag a same-value race; recorded as a limitation in `unattended-execution/design.md`.
- Verified: 81 unit tests pass (0 skipped); `verify-mapping` ok 19/85/340; dry run OM-01.02 → awaiting-owner-acceptance with zero writes; `check-permissions` minimum satisfied with excess scopes listed; `probe` ok; bounded `probe-write` on ENG-01 idempotent and verified; `./gradlew build` successful (backend untouched). Details and commands: `unattended-execution/evidence.md`.
- Matrix audit: every I/O row is covered by a running, passing test (see the evidence matrix); the residual-window row is pinned as a limitation rather than a detection, which the frozen matrix anticipates ("reported, not hidden").

## Spec Change Log

## Review Triage Log

## Design Notes

See `unattended-execution/design.md` (state machine, writer table, guarantees and the explicit non-CAS statement) and `unattended-execution/permissions.md`.

## Verification

**Commands:**
- `python3 -m unittest discover -s automation/tests -t . -v` -- expected: all tests pass, none skipped.
- `python3 -m automation.unattended verify-mapping --out <report>` -- expected: `ok: true`, counts 19/85/340.
- `python3 -m automation.unattended plan --policy automation/examples/first-run-om-01-02.toml --dry-run` -- expected: decision `awaiting-owner-acceptance` for OM-01.02, no writes.
- `python3 -m automation.unattended check-permissions` -- expected: minimum satisfied, excess scopes listed.
- `./gradlew build` -- expected: unchanged backend still builds (no backend change).
