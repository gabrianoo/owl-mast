# Unattended execution foundation (ENG-01)

`automation/unattended` is the smallest supported bridge between the GitHub backlog that owns engineering progress ([tracking contract](engineering-tracking.md)) and a T3 coordinator that dispatches story work. It is engineering automation, tracked in [ENG-01 (#106)](https://github.com/gabrianoo/owl-mast/issues/106), outside the OM product numbering. It does not run on its own: a T3 coordinator thread calls it between `delegate_task` turns. There is no loop, schedule or daemon, and the installed `bmad-loop` CLI is not used.

Status: implemented with fixture and bounded live evidence; **not activated**. Activation (first story OM-01.02) remains a separate owner authorization. The companions under `_bmad-output/implementation-artifacts/unattended-execution/` hold the design, permission matrix and requirements-to-evidence matrix.

## What GitHub owns and who writes what

| Fact | Where | Writer | Meaning |
| --- | --- | --- | --- |
| Stable ID, parent epic, `Depends on`, tasks | Issue body (`<!-- owl-mast-id -->`, native sub-issue parent, checklist) | Owner through Git-revised specs | Specification. The machine reads it and never edits a body. |
| Project Status `Backlog`, `Ready`, `Done` | Project 2 Status field | Owner | `Ready` = owner acceptance; `Done` = accepted completion. The machine never writes these. |
| Project Status `In progress`, `In review`, `Blocked` | Project 2 Status field | Machine (this tool) | Claimed by one implementer; evidence proposed and awaiting owner; stopped with a stated reason. `Ready` is restored on cancel. |
| Checkpoints | Issue comments with `<!-- unattended kind=… run=… story=… seq=… -->` | Machine, append-only | `claim`, `release`, `block`, `proposal`, `probe`. Idempotent: the same marker is never posted twice. |
| Task checkboxes | Issue body | Owner | The `proposal` comment lists tasks with the exact commit; the owner ticks them. |
| Issue open/closed | Issue | Owner | Closing is acceptance; closed as not planned is not `Done`. |
| CI pass, review approval, merge, deployment | PR checks, PR reviews, merge, release | GitHub / reviewer / owner | Read by the tool, never written. Each stays a distinct fact. |

Dispatch is possible only when all of these hold: the story is in the policy allowlist; its epic is not E17/E19 (unless explicitly included); its Project item exists with a matching Stable ID; Status is `Ready`; every `Depends on` story and every story of a prerequisite epic is `Done` **and** closed as completed. A story in `contract_design_exceptions` may run its designated design portion before prerequisites, flagged `dispatchable-contract-design-only`. Anything unknown fails closed.

## Commands

All commands print one JSON document. Global flags go before the command.

```sh
python3 -m automation.unattended verify-mapping            # 19/85/340 and relationships against live GitHub
python3 -m automation.unattended --policy automation/examples/first-run-om-01-02.toml plan   # dry run, writes nothing
python3 -m automation.unattended check-permissions         # minimum GitHub permission probe
python3 -m automation.unattended probe                     # environment probes from policy
python3 -m unittest discover -s automation/tests -t .      # qualification suite (fixtures)
```

State commands need `--run-id` and `--live`, and run under `.unattended-runs/<run-id>/` (gitignored machine state: `run.json`, `journal.jsonl`, `stories/<ID>.json`):

```sh
U="python3 -m automation.unattended --live --run-id <run-id>"
$U claim OM-01.02 --receipt receipt.json --worktree <path> --branch <branch> --baseline <sha>
$U record-head OM-01.02 --sha <sha>
$U run-checks OM-01.02 --sha <sha> --cwd <worktree>        # policy checks, fail fast, recorded at that sha
$U request-review OM-01.02 --sha <sha> --receipt reviewer-receipt.json
$U record-review OM-01.02 --sha <sha> --verdict approved|changes-requested --report <ref>
$U repair OM-01.02 --receipt receipt.json                     # at most two rounds, then blocked
$U propose-evidence OM-01.02 --sha <sha> --pr <n> --task OM-01.02-T1 --summary "…"
$U block|cancel OM-01.02 --reason "…";  $U cancel-run --reason "…";  $U resume OM-01.02;  $U status
```

## Coordinator protocol (T3)

1. `verify-mapping`, `check-permissions`, `probe` must all pass before a run starts.
2. `plan` decides eligibility from a fresh snapshot. Nothing else infers readiness.
3. `delegate_task` with `isolation: "worktree"`, `role: "implementation"`, target `claudeAgent` / `claude-fable-5-1` / `options {effort: "high"}`. Pass the returned task id and target as the receipt to `claim`; the tool refuses receipts without the exact model and effort. One active implementer per story and per run.
4. When the implementer returns, `record-head` with the exact commit, then `run-checks` in the claimed worktree. Checks fail ⇒ `repair` (new implementer task, round 1 or 2) or `block`.
5. `request-review` only after passing checks at that commit, with a fresh `delegate_task` receipt for `codex` / `gpt-6-astra` / `options {reasoningEffort: "high"}`, `role: "review"`. The reviewer reads the actual source, full diff, requirements and test evidence. `record-review` binds the verdict to the commit; any later commit invalidates it.
6. `propose-evidence` after approval: verifies the PR head equals the approved commit, the PR is open and unmerged, no `CHANGES_REQUESTED` review exists at that commit and CI is not failing, then posts the proposal and sets `In review`. Merge, `Done` and closing remain owner actions.
7. Stop conditions: `budgets` in policy (stories per run, delegated tasks, repair rounds, wall clock), any `blocked` story, any refusal or transport error. `cancel`/`cancel-run` release claims; `resume` reconciles pending GitHub effects and refuses a worktree whose path/branch differ from the claim. `task_cancel` stops the delegated T3 task itself.

## Guarantees and limits

- **Stale revisions.** Every Status write re-reads the Project item first and refuses if its Status or `updatedAt` differ from the last verified read, then re-reads after the write and refuses to proceed unless the value is exactly the intended one.
- **No compare-and-swap.** GitHub exposes none for Project fields or comments. An edit that lands between the pre-write read and the write is overwritten and cannot be detected afterwards; the suite pins this limitation (`test_residual_window_edit_is_not_detectable_documented_limitation`). The machine only ever writes from a specific expected value, so the exposure is one field for the duration of one request.
- **Idempotency.** Every comment carries a unique marker; a retry or duplicate event finds it and posts nothing. Two comments with the same marker (a concurrent writer) are reported as a conflict.
- **Partial writes.** Effects are recorded as write-ahead intents; `resume` adopts an effect that reached GitHub before a crash and re-executes one that did not.
- **Fail closed.** Permission denial, outage, unknown objects, parse failures and inconsistent issue state stop the operation without advancing state.
- **Live transport.** Fixture tests cover the fault matrix with an in-memory transport. Live GitHub evidence is limited to read-only snapshots and a bounded write probe on the engineering issue; live T3 evidence is this tool's own delegated-task receipt. No product story has been dispatched.

## Permissions and secrets

Minimum GitHub access: classic scopes `repo` and `project` (or a fine-grained token with Issues read/write, Pull requests read, Contents read, Metadata read, user Projects read/write). `check-permissions` reports the observed scopes and lists excess ones; the current operator token carries `workflow`, `gist` and `admin:public_key` in excess. The tool restricts what it writes by policy; the credential boundary is enforced only by the token the operator provisions. Tokens never enter policy, state or logs: the policy loader refuses secret-like keys and values, and probe output redacts token-shaped strings. A `GH_TOKEN` for an unattended coordinator is obtained through T3 `request_secret` with file delivery and exported for the command only. Details: `_bmad-output/implementation-artifacts/unattended-execution/permissions.md`.

## Candidate first activation

`automation/examples/first-run-om-01-02.toml` allowlists OM-01.02 only. The 2026-11-06 dry run reports `awaiting-owner-acceptance` because its Status is `Backlog`. Activation requires, in order: owner sets OM-01.02 to `Ready`; independent review of ENG-01 accepted; `verify-mapping`, `check-permissions` and `probe` pass on the coordinator machine; a coordinator thread follows the protocol above with the example policy. Kubernetes, storage, identity, secrets and live-environment gates of OM-01.02 itself are untouched by this foundation.
