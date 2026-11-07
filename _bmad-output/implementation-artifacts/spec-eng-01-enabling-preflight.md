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

- AC1 Without `--activation`, every real-transport state command (`status` included) refuses `activation-required` before any GitHub call and creates no state. (`test_cli_and_probes`, `test_coordinator`, `test_sync`, `test_transport`, `test_lifecycle_smoke`)
- AC2 The shipped policy and the committed candidate activation never authorize a run through the CLI (`check-activation` exit 2; `reserve` refuses, no state, no calls). (`test_activation.CandidateAndLoaderTests`)
- AC3 Malformed, unknown-key, secret-like, non-story-scope, missing-evidence and unreadable activations refuse at load. (`test_malformed_activations_refuse_at_load`)
- AC4 A current activation on a live-marked synthetic transport admits OM-01.02 and advances through claim, head, checks, review authorization and approved review; the run records the binding. (`test_current_activation_admits_and_advances…`)
- AC5 Foreign run id, foreign repository, policy digest drift, scope drift, implementer/reviewer model drift, budget drift, non-live environment, over-long or inverted window, not-yet-valid and expired activations refuse at run start with the specific code, no calls, no run state. Policy drift after activation refuses the existing run (`run-binding-mismatch`) and a new one (`activation-mismatch`). (`test_foreign_scope_and_drift…`, `test_policy_drift…`)
- AC6 After expiry every advancing operation refuses `activation-expired`; a late receipt binds for cleanup only; cancel with terminal evidence, record-task-terminal, resume (cleanup only), cancel-run work with the same or no activation and never advance; restart replays cleanup but abandons advancing intents. (`ExpiryAndCleanupTests`)
- AC7 A changed or different activation refuses every operation including cleanup. (`test_changed_activation…`)
- AC8 All previously qualified safeguards and the existing suite stay green: 288 tests (277 + 11), `./gradlew build --console=plain`, `scripts/verify-quality-gates.sh`. `.java-version`, backend, product specs and CI untouched.
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
| `automation/tests/test_{cli_and_probes,coordinator,sync,transport,lifecycle_smoke,repair_pass_2_findings}.py` | gate expectations moved to `activation-required` |
| `docs/unattended-execution.md`, `automation/README.md`, `docs/engineering-tracking.md` | opt-in semantics, candidate, trust model (`automation/policy.toml` stays byte-identical: committed legacy fixtures bind to its digest) |
| `_bmad-output/implementation-artifacts/eng-01-enabling-preflight-20261107.md` | sanitized OM-01.02 activation preflight |

## Out of scope / blockers kept explicit

Merge, activation, OM-01.02 `Ready`, any product work, any Kubernetes/storage/identity target selection, credential provisioning. See the preflight artifact for the verified/missing evidence table.
