---
title: 'ENG-01 — Unattended execution foundation (GitHub-authoritative dispatch, sync and T3 coordination)'
type: 'feature'
created: '2026-11-06'
status: 'in-review'
route: 'dispatch'
review_loop_iteration: 1
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
- [x] `automation/unattended/coordinator.py` -- claim/record-head/run-checks/request-review/record-review/repair/propose-evidence/block/cancel/resume/rebase-revisions/status with marker comments only (round 1: no Status writes, stable operation identities, revision closure, lock, live gate) -- requirement 3.
- [x] `automation/unattended/probes.py`, `automation/unattended/cli.py`, `automation/unattended/__main__.py` -- permission/environment probes, check runner, CLI -- requirement 4.
- [x] `automation/tests/*` -- stdlib `unittest` suite with fake transport and fault injection, real normalized snapshot fixture -- requirement 5.
- [x] `docs/unattended-execution.md`, `docs/engineering-tracking.md`, `.github/workflows/ci.yml`, `.gitignore` -- operator guide, pointer, CI job, ignored state dir.
- [x] `_bmad-output/implementation-artifacts/unattended-execution/{design,permissions,evidence}.md` -- companions: design/state semantics, permission matrix, requirements-to-evidence matrix with exact commands and results.

**Acceptance Criteria:**
- Given the live repository, when `verify-mapping` runs, then it reports 19/85/340 with all relationships satisfied and exit 0.
- Given policy allowlist `OM-01.02`, when `plan --dry-run` runs against live GitHub, then it writes nothing and reports the owner-gate decision.
- Given the unit suite, when `python3 -m unittest discover -s automation/tests -t .` runs, then every matrix row has a passing test.
- Given ENG-01 (#106), when `probe-write` runs twice, then exactly one marker comment exists and no Project Status is written.
- Given a live transport, when `claim` is attempted for any product story, then it is refused with `live-execution-disabled` before any GitHub effect.

## Implementation Notes

- 2026-11-06: Planned and implemented directly by the delegated implementation agent (no sub-delegation, per coordinator instruction). Spec kernel is ~1.9k tokens, above the 1600 guideline; kept whole because the bridge is one cohesive deliverable whose parts are not independently shippable, with detail moved to the `unattended-execution/` companions. No Open Questions: every remaining choice is routine and recorded here.
- Implemented as planned; one design correction during work: `Depends on` lines may name epics (e.g. OM-02.01 depends on E01), so epic dependencies resolve like epic prerequisites (all stories Done and closed). Live finding: a same-value Project Status write leaves `updatedAt` unchanged, so `updatedAt` cannot flag a same-value race; recorded as a limitation in `unattended-execution/design.md`.
- Verified: 81 unit tests pass (0 skipped); `verify-mapping` ok 19/85/340; dry run OM-01.02 → awaiting-owner-acceptance with zero writes; `check-permissions` minimum satisfied with excess scopes listed; `probe` ok; bounded `probe-write` on ENG-01 idempotent and verified; `./gradlew build` successful (backend untouched). Details and commands: `unattended-execution/evidence.md`.
- Matrix audit: every I/O row is covered by a running, passing test (see the evidence matrix); the residual-window row is pinned as a limitation rather than a detection, which the frozen matrix anticipates ("reported, not hidden").

- Repair round 1 (2026-11-06), review of 7cb25b2524436dc212c276ba0d49820775760dee by three independent GPT-6 Astra layers: all findings real and high. Fixed in place (no revert) under the preserve-work boundary. Design corrections: Project Status is never written (owner field, no CAS); every effect has a stable operation identity with write-ahead intent; admission and proposals re-read the revision closure; store-wide fcntl lock and run binding; `record-head` after a failure requires a budgeted `repair`; `run-checks` executes the full configured set on the exact clean HEAD and is the only check evidence (`record-checks` removed); per-reviewer objections; identity check before any resume effect; `repair` and `resume` behind `--live`; permission probe separates `basic_access` from `bounded`; `claim` on the live transport refused (`live-execution-disabled`). Owner steering applied in the same commit: the automation CI job runs on `ubuntu-26.04`. Verified: 116 tests pass; the reviewer's ten probe scenarios are refused or no longer applicable (evidence/reviewer-probes-rerun-2026-11-06.txt); live read-only probes repeated; comment-only write probe idempotent on #106; `check-permissions` now exits 2 (not bounded). Outcome: implemented and fixture-qualified, **not qualified for unattended use** (T3 enforcement gaps, no bounded credential), live execution disabled.

## Spec Change Log

- Round 1 (2026-11-06). Triggering findings: B3/E3/V10 (owner Status overwritten), B7/E6/E7/E8/V4/V5 (unstable effect identity, stranded cleanup), B1/E1/V2 (stale issues claimed), B9/E2/V3 (unknown dependencies), B2 (no serialization), B6/E9 (unbound run), B4 (repair bypass), B8/E10 (masked objection), E5 (resume rebases), E11 (repair without --live), E12/V9 (unbounded credential accepted), V1 (transport untested), V6 (effects before identity), V7 (asserted checks), V8 (T3 unenforceable). Amended: non-frozen sections (Code Map, Tasks, Design Notes, Verification) and the companions. **Deviation from the frozen block, logged, not silently applied:** the generated frozen Intent/Boundaries/Matrix described machine writes of Project Status `In progress`/`In review`/`Blocked`/`Ready` with check-then-write-then-verify and a "documented residual race". That text weakened the original user requirement (one writer per field; never present read-then-write as CAS; fail closed) and is superseded: the machine writes no Project Status; matrix rows "Claim", "Stale write", "Repair cap", "Cancel / resume" now mean marker comment only, revision refusal before admission/effects, block marker, release marker. The frozen text is left unmodified for the human to renegotiate. Known-bad state avoided: last-writer-wins on an owner field; duplicate proposals; terminal cleanups left pending; loops around the repair budget. KEEP: stable-ID mapping and verification, strict allowlist/E17/E19/owner-gate eligibility, receipt validation, synthetic fault coverage via the fake transport and a real git worktree, read-only live probes, comment-only probe on engineering issues, no merge/Done/body/checkbox paths.

## Review Triage Log

- B1 (blind): stale GitHub issues claimable — **high**, confirmed by probe `stale-issues` (claimed with closed story and reopened dependency); routed bad_spec; fixed: admission re-reads the revision closure and refuses (`test_story_closed_and_dependency_reopened_after_snapshot`). Same cause as E1, V2.
- B2 (blind): concurrent calls bypass single-worker and budgets — **high**, confirmed by probe `concurrent-claims` (two claimed, count 1); bad_spec; fixed: store-wide non-blocking fcntl lock held across each operation, run accounting reloaded inside it (`test_interleaved_claim_from_another_coordinator_is_refused_by_the_lock`, `test_lock_is_held_across_the_whole_operation_against_other_processes`).
- B3 (blind): owner's concurrent Blocked overwritten — **high**, confirmed by the former `test_residual_window…` test; bad_spec; fixed by design correction: no Project Status writes at all (`test_owner_status_is_never_written`, `test_no_merge_status_or_done_write_path_exists`). Same cause as E3, V10.
- B4 (blind): repair ceiling bypassable through record-head — **high**, confirmed by probe `five-failed-iterations`; bad_spec; fixed: `record-head` refused after checks-failed/changes-requested (`repair-required`), only budgeted `repair` reopens (`test_record_head_after_failure_requires_budgeted_repair`).
- B5 (blind): resume turns duplicate-marker conflict into success — **high**, confirmed by probe `duplicate-resume`; bad_spec; fixed: exactly-one rule applied on resume, story enters `conflict` (`test_duplicate_marker_is_a_conflict_on_claim_and_stays_one_on_resume`). Same cause as E4.
- B6 (blind): run identity not bound to repository/policy — **high**, confirmed by probe `policy-rebind`; bad_spec; fixed: `Store.ensure_run` refuses a different repo or digest before recovery (`test_run_is_bound_to_repository_and_policy`). Same cause as E9.
- B7 (blind): partial effects lack recovery and stable retry identity (release post fails; status crash; duplicate proposal) — **high**, confirmed by probes `cancel-recovery`, `status-crash-resume`, `proposal-retry`; bad_spec; fixed: operation ids with write-ahead intents, pending terminal intents replayed on resume, status effect removed (`test_cancel_release_failure_is_replayed_on_resume`, `test_proposal_retry_reuses_the_same_operation_identity`). Same cause as E6, E7, E8, V4, V5.
- B8 (blind): another reviewer's approval masks an objection — **high**, confirmed by probe `masked-objection`; bad_spec; fixed: per-reviewer effective state at any commit until dismissed or re-reviewed (`test_another_reviewers_approval_does_not_mask_an_objection`, `test_objection_at_an_earlier_commit…`). Same cause as E10.
- B9 (blind): unknown dependency text becomes no dependencies — **high**, confirmed by probe `unknown-dependency`; bad_spec; fixed: strict declaration grammar, `depends_on_known`, unknown ⇒ `unknown-eligibility` (`test_unparsed_dependency_text_fails_closed`, `test_missing_or_duplicated_declaration_fails_closed`). Same cause as E2, V3.
- E1 (edge): revalidate issue and dependency revisions before claim — **high**; duplicate of B1; fixed as B1.
- E2 (edge): unparsed dependencies dispatchable — **high**; duplicate of B9; fixed as B9.
- E3 (edge): owner Blocked overwritten in the write window — **high**; duplicate of B3; fixed as B3.
- E4 (edge): resume bypasses duplicate conflict — **high**; duplicate of B5; fixed as B5.
- E5 (edge): resume replaces a rejected revision and proceeds — **high**, confirmed by reading `resume` (it reset `item_updated_at`); bad_spec; fixed: resume refuses changed revisions; `rebase-revisions` is explicit and journaled (`test_resume_refuses_changed_revisions_instead_of_replacing_them`, `test_proposal_refuses_changed_revisions_and_rebase_is_explicit`).
- E6 (edge): proposal retry allocates a new sequence — **high**; duplicate of B7(c); fixed as B7.
- E7 (edge): crash after a successful Status mutation unrecoverable — **high**; duplicate of B7(b); resolved by removing the Status effect (no such effect exists).
- E8 (edge): cancelled/blocked stories keep pending release forever — **high**; duplicate of B7(a); fixed as B7.
- E9 (edge): run identity not bound — **high**; duplicate of B6; fixed as B6.
- E10 (edge): approval masks another reviewer's objection — **high**; duplicate of B8; fixed as B8.
- E11 (edge): `repair` without `--live` reaches the block fallback — **high**, confirmed (`repair` absent from `WRITE_COMMANDS`); patch; fixed: `repair`, `resume`, `rebase-revisions`, `cancel-run` require `--live`, and the coordinator itself refuses writes when not live (`test_write_commands_need_live`, `test_non_live_coordinator_cannot_write`).
- E12 (edge): permission probe accepts unrestricted credentials — **high**, confirmed (`minimum_satisfied` true with excess scopes); bad_spec; fixed: `basic_access` vs `bounded`, unknown scopes and excess are not bounded, exit 2, activation not allowed (`test_check_permissions_separates_basic_access_from_bounded`). Same cause as V9. Bounded credential remains a blocker.
- V1 (verification): GitHub transport regressions invisible to the suite — **high**, confirmed (no test touched `GhCliTransport`); patch; fixed: `test_transport.py` feeds realistic GraphQL pages, REST comment lines, PR reviews and error texts through `GhCliTransport` into the coordinator, including a `CHANGES_REQUESTED` carried in raw JSON refusing the proposal.
- V2 (verification): claim ignores concurrent issue changes — **high**; duplicate of B1; fixed as B1.
- V3 (verification): unknown dependency text — **high**; duplicate of B9; fixed as B9.
- V4 (verification): crash after Status mutation — **high**; duplicate of B7(b)/E7; resolved by removing the effect.
- V5 (verification): proposal retries duplicate comments — **high**; duplicate of B7(c)/E6; fixed as B7.
- V6 (verification): resume advances before identity check — **high**, confirmed by reading `resume`; bad_spec; fixed: identity check precedes every effect (`test_resume_checks_identity_before_any_effect`).
- V7 (verification): checks accept an asserted pass — **high**, confirmed (`record_checks(… True, {})`); bad_spec; fixed: `record-checks` removed; `run-checks` executes the full set on the exact clean HEAD and re-checks HEAD; `request-review` verifies the record (`test_no_asserted_pass_exists`, `test_review_requires_executed_passing_checks_at_head`, `test_checks_that_modify_the_tree_do_not_pass`).
- V8 (verification): T3 cancellation/budgets are an unqualified operator protocol — **high**, confirmed against the installed tool contracts (no admission hook, no cancel acknowledgement, no child deadline, agent-only tools); bad_spec; resolution: live product admission refused in code (`live-execution-disabled`), gaps and smallest upstream changes documented; requirement reported as **blocked**, not met.
- V9 (verification): minimum-permission qualification not performed — **high**; duplicate of E12; resolution as E12; reported as **blocked** with the exact minimum and test plan in `permissions.md`.
- V10 (verification): concurrency limitation contradicts the qualification boundary — **high**; duplicate of B3/E3; resolved by removing the Status write and the limitation test.

## Design Notes

See `unattended-execution/design.md` (state machine, operation identities, revision closure, lock and binding, live gate) and `unattended-execution/permissions.md` (bounded-credential blocker, T3 enforcement gaps). After round 1 the machine writes no Project Status; the frozen matrix rows that mention Status writes are superseded as logged in the Spec Change Log.

## Verification

**Commands:**
- `python3 -m unittest discover -s automation/tests -t . -v` -- expected: all tests pass, none skipped.
- `python3 -m automation.unattended verify-mapping --out <report>` -- expected: `ok: true`, counts 19/85/340.
- `python3 -m automation.unattended plan --policy automation/examples/first-run-om-01-02.toml --dry-run` -- expected: decision `awaiting-owner-acceptance` for OM-01.02, no writes.
- `python3 -m automation.unattended check-permissions` -- expected today: `basic_access` true, `bounded` false, exit 2 (blocker recorded); exit 0 only with a bounded credential.
- `./gradlew build` -- expected: unchanged backend still builds (no backend change).
