# ENG-01 enabling change: explicit activation opt-in, plus OM-01.02 activation preflight

Engineering automation only ([ENG-01, #106](https://github.com/gabrianoo/owl-mast/issues/106)); no product contract changes, no new product IDs. Base: the qualified foundation at `f71167bdaf0c8519cc71874af1167b4b66f9f3ee` (PR #107, fresh review PASS, disposition PR107#issuecomment-6706853226). Stacked on `t3/unattended-execution-foundation`; PR #107 is untouched. Authorization: the owner authorized preparation through review; **final configuration approval and activation remain the owner's**. This change does not activate anything, merges nothing and dispatches no worker.

## Problem

The foundation refuses every real-transport state command unconditionally (`live-execution-disabled`). The accepted operating agreement and the Notion loop-setup page require "a separately reviewed enabling change and explicit first-run authorization" before activation. Merely deleting the refusal would make the shipped policy or a copied example able to dispatch.

## Design: smallest supported explicit opt-in

- **Activation authorization document** (`automation/unattended/activation.py`, `--activation <file>`): TOML with `approved`, `id`, `approver`, `issued_at`, `expires_at`, `agreement`, `[binding]` (repository, policy digest, `environment = "live"`, exact run id), `[scope] stories`, `[targets]`, `[budgets]`, `[evidence]` (lifecycle smoke and fresh review references). Strict loader: unknown or secret-like keys, credential-like values, non-story scope, missing evidence refuse `activation-invalid`.
- **Current** only when approved, bound to this repo / exact policy digest / run id, scope equals the allowlist, targets and budgets equal the policy's, `issued_at <= now <= expires_at`, window ≤ 24 h. Otherwise `activation-unapproved | activation-mismatch | activation-invalid | activation-not-yet-valid | activation-expired`.
- **Gate placement.** A live run is created only under a current activation and records its binding in `run.json`. `reserve` and every advancing operation require it current. Expiry is a run stop like the wall clock (`_run_stop`): advancement refuses, late receipts bind for cleanup only, resume abandons advancing replays. Cleanup (`cancel`, `block`, `record-task-terminal`, `record-no-launch`, `cancel-run`, `reconcile-retained-execution`, cleanup part of `resume`) works after expiry or without the file on the recorded binding; a different activation (id or digest) refuses everything. A run never activated (fixture-born or legacy) releases nothing on live (`activation-required`).
- **Defaults stay disabled.** `automation/policy.toml` keeps `allow = []`. The committed candidate `automation/examples/activation-om-01-02.candidate.toml` has `approved = false`, placeholder run id, zero policy digest, expired window: copied as-is it refuses. `check-activation` is a read-only explanation command. Approved activations are private, run-specific, never committed.
- **Trust model (stated honestly).** The activation is a trusted-coordinator/owner engineering approval on the trusted machine, not a credential, not signed, not cryptographically verified.

## Acceptance criteria

- AC1 Without `--activation`, no live run is created and every admitting or advancing real-transport state command refuses `activation-required` before any GitHub call (on a run that was never activated `status` and cleanup refuse too); cleanup and `status` of a run activated earlier work on its validated recorded binding without the file. (`test_cli_and_probes`, `test_coordinator`, `test_sync`, `test_transport`, `test_lifecycle_smoke`)
- AC2 The shipped policy and the committed candidate activation never authorize a run through the CLI (`check-activation` exit 2; `reserve` refuses, no state, no calls). (`test_activation.CandidateAndLoaderTests`)
- AC3 Malformed, unknown-key, secret-like, non-story-scope, missing-evidence and unreadable activations refuse at load. (`test_malformed_activations_refuse_at_load`)
- AC4 A current activation on a live-marked synthetic transport admits OM-01.02 and advances through claim, head, checks, review authorization and approved review; the run records the binding. (`test_current_activation_admits_and_advances…`)
- AC5 Foreign run id, foreign repository, policy digest drift, scope drift, implementer/reviewer model drift, budget drift, non-live environment, over-long or inverted window, not-yet-valid and expired activations refuse at run start with the specific code, no calls, no run state. Policy drift after activation refuses the existing run (`run-binding-mismatch`) and a new one (`activation-mismatch`). (`test_foreign_scope_and_drift…`, `test_policy_drift…`)
- AC6 After expiry every advancing operation refuses `activation-expired`; a late receipt binds for cleanup only; cancel with terminal evidence, record-task-terminal, resume (cleanup only), cancel-run work with the same or no activation and never advance; restart replays cleanup but abandons advancing intents. (`ExpiryAndCleanupTests`)
- AC7 A changed or different activation refuses every operation including cleanup. (`test_changed_activation…`)
- AC8 All previously qualified safeguards and the existing suite stay green: 324 tests (277 + 11 + 17 + 19), `./gradlew build --console=plain`, `scripts/verify-quality-gates.sh`. `.java-version`, backend, product specs and CI untouched.
- AC9 Preflight evidence is recorded with verified vs missing items and explicit blockers; no status, checkbox, Project or environment mutation.

## Code map

| Path | Change |
| --- | --- |
| `automation/unattended/activation.py` | new: `Activation`, `load_activation`, problems/stop codes |
| `automation/unattended/coordinator.py` | `require_not_live` → `require_activation(op, advancing)`; activation stop in `_run_stop`; run creation under activation; gap wording; `status` activation facts |
| `automation/unattended/state.py` | `RunState.activation`; `ensure_run(activation=…)` records/validates the binding |
| `automation/unattended/cli.py` | `--activation`, `check-activation`; reserve pre-read gate |
| `automation/examples/activation-om-01-02.candidate.toml` | unapproved candidate (cannot dispatch when copied) |
| `automation/tests/test_activation.py` | 11 tests for AC1–AC7 |
| `automation/tests/test_enabling_repair_1.py` | 17 tests for the repair-round-1 findings R1–R6 below |
| `automation/tests/test_enabling_repair_2.py` | 19 tests for the repair-round-2 findings F1–F3 below (foreign run record, persisted temporal facts, status under the gate) |
| `automation/tests/test_enabling_repair_3.py` | 12 tests for the final-review findings FINAL-1/FINAL-2 below (source re-read at creation for both public entrypoints; one clock observation per locked operation) |
| `automation/tests/test_{cli_and_probes,coordinator,sync,transport,lifecycle_smoke,repair_pass_2_findings}.py` | gate expectations moved to `activation-required` |
| `docs/unattended-execution.md`, `automation/README.md`, `docs/engineering-tracking.md` | opt-in semantics, candidate, trust model (`automation/policy.toml` stays byte-identical: committed legacy fixtures bind to its digest) |
| `_bmad-output/implementation-artifacts/eng-01-enabling-preflight-20261107.md` | sanitized OM-01.02 activation preflight |

## Review triage (independent review of 96ad53a: CHANGES REQUESTED; repair round 1)

Status: **implemented; reviewed with changes requested at 96ad53a (repair round 1 applied at aa80168), at aa80168 (repair round 2 applied at ce0320e) and at ce0320e (FINAL-1/FINAL-2, owner-authorized repair round 3 applied, below); fresh exact-commit review of the round-3 head pending; not eligible for activation approval; not approved; not enabled.** Findings and the shared fix (one validation in `Coordinator.require_activation`, run under the existing operation lock by every advancing and cleanup consumer, reading fresh locked state, never the cached run):

| Finding | Fix | Code |
| --- | --- | --- |
| R1 missing `run.json` with retained artifacts promoted fixture stories to live | `Store.ensure_run` refuses creation (any environment) when the run folder holds a journal or story checkpoints without metadata; nothing written, artifacts kept for explicit recovery | `run-metadata-missing` |
| R2 persisted binding accepted by truthiness; public `Store.ensure_run` took a dictionary; cached binding checked before reload | `Store.ensure_run` is the only live creation path: it takes the loaded `Activation`, the policy and the time, persists the complete binding record (`BINDING_RECORD_KEYS`: document identity, window, run binding, `approved`, `validated_at`) only when `problems` is empty; `Store.bound_run` / `validate_binding` re-check the full record against the run on every load; every consumer reloads under the lock before any decision | `activation-binding-invalid`, `activation-required` |
| R3 long-lived Coordinator ignored a changed or missing file | `_refresh_activation` re-reads the source at every gate: changed digest or malformed file refuses every operation (omit `--activation` to clean up on the recorded binding); a missing file stops advancement (`activation-required`), cleanup and cleanup replays proceed on the validated binding | `activation-mismatch`, `activation-invalid`, `activation-required` |
| R4 naive timestamps crashed with `TypeError` | `parse_utc`: time part and explicit offset required, normalized to UTC at load; naive, date-only, malformed and overflowing values refuse at load; a naive injected clock is a structured refusal | `activation-invalid` |
| R5 unknown nested target keys ignored | per-target allowlist `provider/model/options/isolation`, string-typed fields, string-valued options, no coercion | `activation-invalid` |
| R6 observed expiry reversible after clock rollback/restart | `_observe_stop` persists the first observed expiry (from the recorded window) or a clock regression past the last observed time (5 min tolerance) in `run.json` (`activation_stop`, `last_observed_at`); the run never advances again, cleanup, late receipts (cleanup only) and terminal evidence stay allowed; approvals and budgets untouched | `activation-expired`, `clock-regression` |

Unchanged: the trusted-machine boundary (no credential scheme, no signatures), `automation/policy.toml` (byte-identical to f71167b), the default empty allowlist, the unapproved committed candidate. One existing assertion changed: after an observed expiry the bare restart reports the durable `activation-expired` stop instead of `activation-required` (`test_cleanup_after_expiry_works_with_the_same_or_no_activation_but_never_advances`).

## Review triage (independent review of aa80168: CHANGES REQUESTED; repair round 2, final)

One validation boundary again, this time on the persisted run record: `Store.load_run` validates shape, types, time controls and **run identity against the selected `Store.run_id`**, `Store.bound_run` validates the activation record against that same selected identity, and `status` joins every other consumer under `require_activation`.

| Finding | Fix | Code |
| --- | --- | --- |
| F1 a genuine `run.json` restored from another run authorized cleanup (binding checked against ids read from the same file) | `load_run` refuses a record whose `run_id` is not the store's; `bound_run`/`validate_binding` check the activation record against `Store.run_id`; applies at construction, every fresh locked reload, cancel, cancel-run, late receipts, pending cleanup replay, `status`, CLI and the public `Store` entrypoints; nothing rewritten, zero transport calls | `run-identity-mismatch`, `activation-binding-invalid` |
| F2 persisted temporal facts accepted without validity (`validated_at` null/outside window; malformed `last_observed_at` replaced by now; `activation_stop` `[]`/`false` read as absent) | `validate_binding` requires a non-null strict `validated_at` inside `issued_at..expires_at` (window ≤ 24 h); `validate_high_water` / `validate_stop_record` at the load boundary (null or exactly the supported record with a recognized code and typed fields); `_observe_stop` refuses on any parse problem instead of substituting now; `is not None` everywhere instead of truthiness; valid expired cleanup unchanged | `activation-binding-invalid`, `run-state-invalid` |
| F3 `status` observed expiry without recording it; rollback/restart resumed work; cached run/file facts could go stale | `status` calls `require_activation("status", advancing=False)` under the lock: fresh reload/validation, source re-read, durable expiry/clock-regression observation, coherent snapshot of the persisted run; no-file status on a valid binding kept; changed/malformed source refuses like every other consumer | `activation-expired`, `clock-regression`, `activation-mismatch`, `activation-invalid` |

Legacy records written before the opt-in (no `activation`, `last_observed_at`, `activation_stop` keys) still load with those controls read as null; the committed legacy fixtures and their regeneration are unchanged. `automation/policy.toml` stays byte-identical to f71167b. Regressions: `automation/tests/test_enabling_repair_2.py` (19 tests).

## Review triage (final independent review of ce0320e: CHANGES REQUESTED; repair round 3, owner-authorized)

The final review (`review-final-ce0320e.md`) confirmed R1–R6 and F1–F3 resolved and found two residual boundary cases. The owner explicitly authorized one more bounded repair; this round is that repair.

| Finding | Fix | Codes |
| --- | --- | --- |
| FINAL-1 run creation persisted an approved binding from a stale loaded object (source changed to unapproved, removed or malformed between load and construction; both `Coordinator` and public `Store.ensure_run`) | one shared `refresh_activation` (activation.py) re-reads the source; `Store.ensure_run` calls it under the store lock **before** any `run.json` or journal write and validates the fresh document (`Coordinator.__init__` performs the same re-read before its pre-check and passes the fresh object). Changed source: `activation-mismatch`; missing: `activation-required` (nothing is presented); malformed: `activation-invalid`; no binding, no `run-started` event, no replacement record, zero transport calls. The unchanged source creates as before; a genuinely activated run still cleans up on its recorded binding without the file; retained-artifact, foreign-run and schema safeguards are unchanged | `activation-mismatch`, `activation-required`, `activation-invalid` |
| FINAL-2 expiry newly observed by a later clock sample inside one operation (status report, `_refuse_unless_current`, `_run_stop`, replay) was reported or refused without a durable stop, so a within-tolerance rollback and restart could advance again | `Coordinator.operation()` is the one boundary of every locked operation (all 17 consumers, the CLI pre-read gate, construction): the store lock plus **one** clock observation sampled after the lock is held and used by every authorization decision of that operation (`_activation_problems`, `_observe_stop`, `_elapsed`/`_run_stop`, the status report, which is now built inside the lock). An operation whose observation is still valid reports no expiry and persists none (a rollback inside the tolerance is then a correction, not a reversal); the first operation whose observation is past the window records the stop before refusing or reporting, and the record survives rollback and restart. Nested operations share the outer observation; independent operations sample afresh, so elapsed budgets and later expiries are never hidden. The five-minute tolerance and all requirements are unchanged | `activation-expired`, `clock-regression` |

Regressions: `automation/tests/test_enabling_repair_3.py` (12 tests: creation source matrix unchanged/changed/missing/malformed for both entrypoints and the CLI, binding records the re-read digest, no-file cleanup control, moving-clock crossings for `status`, `record-head`, every advancing consumer, both `resume` branches, rollback/restart durability, CLI status coherence). Full suite 336 tests OK. `automation/policy.toml` stays byte-identical to f71167b. No further repair rounds without owner authorization.

## Out of scope / blockers kept explicit

Merge, activation, OM-01.02 `Ready`, any product work, any Kubernetes/storage/identity target selection, credential provisioning. See the preflight artifact for the verified/missing evidence table.
