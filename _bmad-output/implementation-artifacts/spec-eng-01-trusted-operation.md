---
title: 'ENG-01 — Trusted-machine operating agreement and lifecycle smoke qualification'
type: 'feature'
created: '2026-11-06'
status: 'in-review'
route: 'dispatch'
review_loop_iteration: 1
baseline_commit: '93df46e0833c26c035d38b706b0586013d7e0d8e'
context:
  - 'docs/engineering-tracking.md'
  - 'docs/unattended-execution.md'
  - '_bmad-output/implementation-artifacts/unattended-execution/design.md'
  - '_bmad-output/implementation-artifacts/unattended-execution/permissions.md'
---

<frozen-after-approval reason="User explicitly accepted the revised operating agreement and instructed proceed">

## Intent

Replace ENG-01's strict platform-containment prerequisites with the owner's accepted trusted-machine agreement. Qualify a small engineering-only T3 lifecycle against isolated synthetic state without activating product execution. This supersedes the old requirement that hard child bounds, exhaustive credential-denial qualification and automated Project Status synchronization must precede all unattended work; it does not assert those guarantees now exist.

## Boundaries & Constraints

**Always:** T3 is the sole coordinator. Explicit Claude Fable 5.1 High implementation and fresh GPT-6 Astra High exact-commit review; one story/worker at a time; at most two repair rounds. Deterministic checks precede approval. Preserve reservation-before-launch, task-specific ownership, stale/duplicate/outage/denial refusal, exact-SHA review, cancellation acknowledgement and restart reconciliation. Budgets are coordinator-enforced best effort: stop dispatch and request cancellation on expiry, acknowledge that coordinator failure can leave a worker running. Trust the operator's development machine; worktrees isolate files, not host credentials. Use restricted credentials where practical, never claim credential confinement. GitHub remains authoritative; Status/acceptance remain manual owner actions, comments evidence proposals. No new Execution state field required. Existing broad credentials must be disclosed as such, not certified bounded.

**Never:** Enable real transport/product dispatch; remove live-execution-disabled/environment binding; admit OM-01.02; change product SPEC or the 19/85/340 mapping; change ubuntu-26.04 automation CI; merge/deploy/release/schedule/loop; delete branches/worktrees; touch .java-version; use secrets outside request_secret; modify installed T3 or run permission-denial writes. No upstream T3 work is required for this agreement. Do not rewrite historical evidence as if it passed the new real smoke test.

## I/O & Edge-Case Matrix

| Scenario | Expected outcome |
| --- | --- |
| Owner accepts trust model | Current engineering requirements explain accepted residual risks and manual Status; historical strict results remain labeled historical |
| Real production state command | Still refused before effects; acceptance of risk is not activation |
| Synthetic reservation then real T3 task | Real task/model/effort and actual worktree correlate to the pre-launch authorization |
| Checks then fresh review | Approval only for exact checked clean SHA; all substantive objections block advancement |
| Cancellation request or ambiguous task outcome | Retain ownership until task-specific terminal acknowledgement; never infer no-launch from silence |
| Restart/duplicate/stale/outage/denial/budget expiry | No new admission or advancing effects when required evidence is missing; existing regression guarantees survive |

</frozen-after-approval>

## Code Map

- `automation/unattended/coordinator.py`: existing protocol and real-transport gate; `LIVE_EXECUTION_GAPS` currently describes superseded acceptance requirements. Correct current reasons without removing the gate.
- `automation/unattended/probes.py`: keep permission facts distinct from user acceptance and activation; never change bounded=false to true because risk was accepted.
- `automation/tests/{support,fake_transport}.py`: reusable synthetic state; do not use actual product identities for new real-worker smoke. A fixture-only OM-99.01/E99 namespace may be used without broadening production ID grammar.
- `automation/unattended/{state,receipts,policy}.py`: reuse identity/locking/budget semantics, not a new orchestrator.
- Engineering specs/companions and operator/tracking docs: reconcile current requirements and correct LOW design debt (proposal abandoned; unresolved review authorization revoked and retained).

## Tasks & Acceptance

- [x] Update engineering tracking/operator docs, foundation spec current intent, design/permissions/evidence companions and policy comments to the accepted agreement, with an explicit dated supersession. Preserve old evidence and substantive guards.
- [x] Correct current runtime refusal/report wording as needed so it does not demand superseded strict prerequisites or imply activation. Keep the live gate unconditional for this effort and default allowlist empty.
- [x] Add a small manual-step synthetic lifecycle helper under `automation/tests/` if needed, with temporary isolated persisted transport/state, no network transport, no internal delegation/wait loop, and distinct prepare/bind/check/review/cancel/restart operations. It must consume actual T3 receipts/terminal evidence supplied by the coordinator; fabricated receipts cannot count as real smoke qualification. Unit fixtures remain labeled fixtures.
- [x] Add meaningful tests for changed behavior; run the existing full 212-test baseline plus additions. Do not weaken old assertions to fit changed prose.
- [x] Commit scoped implementation locally; coordinator integrates/reviews/pushes, preserving the same implementation owner for repairs.
- [ ] Coordinator runs the real lifecycle smoke, publishes evidence/limitations, and updates ENG-01/GitHub/Notion without activating anything.

Acceptance: Given the agreed trust model, documentation and runtime reports distinguish accepted residual risks, tested controls and disabled activation. Given actual engineering worker/reviewer results, the smoke binds real task identities, validates checks at exact SHA and records a fresh independent review. Given cancellation/restart/failure, ownership and stop behavior remain conservative. Given product/live input, execution remains refused.

## Implementation Notes

Owner approved the operating agreement in this conversation; no repeat approval checkpoint is needed. Current retained T3-created worktree is `/home/gabrianoo/.t3/worktrees/owlmast/t3-08a6bd98`, branch `t3/unattended-execution-foundation`. Implement in this existing isolated checkout; do not create another or alter main. Parent writes evidence outside the checkout while you work. No subagents, provider CLIs, pushes or external writes from the implementation task. Parent handles GitHub/Notion. Read this spec and context fully; legacy strict instructions are superseded only as explicitly stated here.

Bounded effort: one implementation pass plus at most two repairs and fresh reviews (six tasks); at most two additional engineering smoke tasks for cancellation/restart (eight total), strictly sequential. Overall best-effort 120 minutes from 2026-11-06T22:45:17Z; implementation task should stop and report by 23:15:17Z. These are instructions/accounting, not native hard caps. Stop on expired budget, unknown ownership, failed checks/review, denied access or outage; no replacement until predecessor terminal. No fixed spend guarantee is claimed. Parent may request cancellation if a worker exceeds budget; an unattended coordinator crash remains accepted residual risk.

Implementation (2026-11-06, implementation task, stopped before 23:15:17Z):

- Runtime: `coordinator.LIVE_EXECUTION_GAPS` and the `live-execution-disabled` message now state the accepted agreement (`OPERATING_AGREEMENT` constant, reported by `status`); the gate itself is unchanged and unconditional; `check-permissions` adds `owner_acceptance` and still never certifies bounded/activation; `policy.toml` comments record the agreement and that the wall clock stops no child. No guard, budget or refusal was weakened; no test assertion was relaxed.
- Smoke helper: `automation/tests/lifecycle_smoke.py` (one operation per invocation; JSON-persisted fixture transport with no network; fixture-only `E99`/`OM-99.01`; policy allowing only that story; `prepare`/`bind`/`head`/`check`/`authorize-review`/`review`/`cancel`/`terminal`/`restart`/`status`; every supplied receipt, terminal evidence and attestation is kept verbatim under `inputs/` with its declared `--source real|fixture`; `status.evidence_class` is `real` only when every input was declared real). It never fabricates inputs and contains no delegation or wait loop; the coordinator supplies real T3 results.
- Tests: `test_lifecycle_smoke.py` (7): full fixture lifecycle with two restarts, cancel refused without terminal evidence and `cancel_requested` not terminal, release replayed after restart, unlaunched authorization owned until attested, product identities and live transport out of reach, prepare refuses reuse, gate wording states the agreement and not the superseded prerequisites, permission report keeps facts separate from acceptance. Full suite: 219 pass (212 baseline + 7), none skipped; `git diff --check` clean; `backend/`, product specs, planning artifacts, `.github/workflows/ci.yml` (`ubuntu-26.04`) and `.java-version` unchanged against `93df46e0`.
- Docs: `docs/unattended-execution.md` (dated supersession, status table with tested controls vs accepted residual risks vs pending real smoke vs disabled activation, smoke helper section, activation section), `docs/engineering-tracking.md` pointer, dated supersession notes at the top of `design.md`, `permissions.md`, `evidence.md`, and the foundation spec's Implementation Notes/Change Log. Historical results keep their labels; nothing is rewritten as if the real smoke passed.
- Repair round 1 (2026-11-06/07): the three findings above fixed in `automation/tests/lifecycle_smoke.py` with six new tests (13 in the file); no gate, binding, budget or refusal changed.
- Not done here (coordinator's part): the real lifecycle smoke with real T3 receipts, its publication, ENG-01/GitHub/Notion updates, review, push.

## Spec Change Log

## Review Triage Log

- TO-R1-1 (fresh Astra review of 92c42d51, 2026-11-06): `PersistedFakeTransport.save` overwrote `transport.json` in place (an interrupted write truncates the JSON and restart cannot load it) and `post_comment` raised the simulated after-effect crash before saving, so a landed comment vanished on reload — **high** (restart fidelity and fault model), confirmed; patch; fixed: save uses the store's atomic durable write (temp file, fsync, rename) and the landed effect is persisted before the simulated crash (`test_interrupted_save_leaves_the_previous_complete_file`, `test_landed_comment_survives_a_crash_after_post`).
- TO-R1-2: `check` used the `prepare`-time `smoke.json` worktree instead of the authoritative bound claim worktree, so a real T3 checkout bound at a different path made checks refuse — **high**, confirmed; patch; fixed: `check` reads the bound claim path and refuses before any bind (`test_check_uses_the_bound_worktree_not_the_prepared_one`, `test_check_before_bind_is_refused`).
- TO-R1-3: module docstring examples placed `--dir` after the operation although the parser requires it before — **medium** (misleading docs), confirmed; patch; fixed: every example corrected and `test_documented_syntax_matches_the_parser` parses the documented order and rejects the old one.
- Reviewer note on `evidence_class`: it summarizes declared input provenance only; a rejected input declared `real` still yields `real`. Clarified in the docstring and pinned by `test_evidence_class_is_declared_provenance_not_success`; no qualification claim is attached to it (patch, documentation).
- Operational observation (parent, not a code finding): resuming this implementation owner through `t3_thread_send` returned a run id but no fresh task id despite the tool contract; the parent keeps the pending repair authorization `eng01-trusted-20261106:OM-99.01:3` unresolved rather than inventing a task id. Receipt freshness is not weakened and no bridge is added; this remains a narrow operational qualification gap of the installed T3 for resumed cross-parent children.

## Verification

- `PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s automation/tests -t .`
- `git diff --check`
- Compare protected product paths and CI runner pin against baseline.
- Coordinator: real T3 receipts and exact-commit review, cancellation acknowledgement, reload of persisted temporary state; retain fixture-vs-real distinctions.
