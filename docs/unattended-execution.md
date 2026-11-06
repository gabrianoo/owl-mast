# Unattended execution foundation (ENG-01)

`automation/unattended` is the smallest supported bridge between the GitHub backlog that owns engineering progress ([tracking contract](engineering-tracking.md)) and a T3 coordinator that dispatches story work. It is engineering automation, tracked in [ENG-01 (#106)](https://github.com/gabrianoo/owl-mast/issues/106), outside the OM product numbering. It does not run on its own: a T3 coordinator thread calls it between `delegate_task` turns. There is no loop, schedule or daemon, and the installed `bmad-loop` CLI is not used.

**State on 2026-11-06 (after repair round 1):**

| Level | Meaning | Status |
| --- | --- | --- |
| Implemented | The code exists and behaves as specified against an in-memory GitHub transport and a real local git worktree | yes |
| Fixture-qualified | The fault matrix (stale revisions, duplicates, retries, crash/restart, denial, outage, locking, binding, budgets, objections) passes in the unit suite, including the production transport parser fed with realistic `gh` responses | yes |
| Live-verified | Read-only snapshot, mapping verification and dry run against live GitHub; one idempotent marker comment on the engineering issue | partial, read-only plus one probe |
| Enabled for product stories | `claim` on the live transport | **no, refused by code** (`live-execution-disabled`) |
| Qualified for unattended use | All six tracking-contract properties met with enforceable evidence | **no, blocked** (T3 enforcement gaps and no bounded credential; see below) |

## What GitHub owns and who writes what

| Fact | Where | Writer | Meaning |
| --- | --- | --- | --- |
| Stable ID, parent epic, `Depends on`, `Epic prerequisites`, tasks | Issue body | Owner through Git-revised specs | Specification. Read with a strict grammar (`None` or a comma-separated list of ids); anything else is unknown and blocks dispatch. |
| Project Status (`Backlog`, `Ready`, `In progress`, `In review`, `Blocked`, `Done`) | Project 2 Status field | **Owner only** | `Ready` = owner acceptance; `Done` = accepted completion. GitHub offers no compare-and-swap, so the machine never writes this field. It reads it for eligibility and treats any change as a stale revision. |
| Machine checkpoints | Issue comments `<!-- unattended kind=… run=… story=… op=… -->` | Machine, append-only | `claim`, `release`, `block`, `proposal`, `probe`. One comment per operation identity; a duplicate is a conflict. |
| Task checkboxes | Issue body | Owner | The `proposal` comment lists tasks with the exact commit; the owner ticks them. |
| Issue open/closed | Issue | Owner | Closing is acceptance; closed as not planned is not `Done`. |
| CI pass, review approval, merge, deployment | PR checks, PR reviews, merge, release | GitHub / reviewer / owner | Read, never written; each stays a distinct fact. |

Because the machine writes no Status, Project Status synchronization is **not implemented**: there is no safe equivalent on GitHub's API. The owner moves Status by reading the machine's comments. This is a deliberate refusal, not a limitation to be documented away.

Dispatch is possible only when all of these hold: the story is in the policy allowlist; its epic is not E17/E19 (unless explicitly included); its Project item exists with a matching Stable ID; both declarations parse; Status is `Ready`; every `Depends on` story and every story of a prerequisite epic is `Done` **and** closed as completed. A story in `contract_design_exceptions` may run its designated design portion before prerequisites, flagged `dispatchable-contract-design-only`. Anything unknown fails closed.

## Commands

All commands print one JSON document. Global flags go before the command.

```sh
python3 -m automation.unattended verify-mapping            # 19/85/340 and relationships against live GitHub
python3 -m automation.unattended --policy automation/examples/first-run-om-01-02.toml plan   # dry run, writes nothing
python3 -m automation.unattended check-permissions         # basic_access vs bounded; exit 0 only when bounded
python3 -m automation.unattended probe                     # environment probes from policy
python3 -m unittest discover -s automation/tests -t .      # qualification suite (fixtures)
```

State commands need `--run-id`; anything that can reach a GitHub write also needs `--live` (`claim`, `repair`, `propose-evidence`, `block`, `cancel`, `cancel-run`, `resume`, `rebase-revisions`, `probe-write`). State lives under `.unattended-runs/<run-id>/` (gitignored: `run.json`, `journal.jsonl`, `stories/<ID>.json`); a store-wide `fcntl` lock serializes every operation across processes and a run is bound to one repository and policy digest.

```sh
U="python3 -m automation.unattended --live --run-id <run-id>"
$U claim OM-01.02 --receipt receipt.json --worktree <path> --branch <branch> --baseline <sha>   # refused on the live transport today
$U record-head OM-01.02 --sha <sha>
$U run-checks OM-01.02 --sha <sha> --cwd <worktree>        # full configured set on the exact clean HEAD; the only check evidence
$U request-review OM-01.02 --sha <sha> --receipt reviewer-receipt.json
$U record-review OM-01.02 --sha <sha> --verdict approved|changes-requested --report <ref>
$U repair OM-01.02 --receipt receipt.json                     # budgeted; required after any failure; at most two rounds, then blocked
$U propose-evidence OM-01.02 --sha <sha> --pr <n> --task OM-01.02-T1 --summary "…"
$U block|cancel OM-01.02 --reason "…";  $U cancel-run --reason "…";  $U resume OM-01.02;  $U rebase-revisions OM-01.02 --reason "…";  $U status
```

## Coordinator protocol (T3) and what the tool can and cannot enforce

1. `verify-mapping`, `check-permissions` (bounded) and `probe` must pass before a run starts.
2. `plan` decides eligibility from a fresh snapshot. `claim` re-reads every revision the decision depends on (story, parent epic, dependency closure, Project items) and refuses on any change.
3. `delegate_task` with `isolation: "worktree"`, `role: "implementation"`, target `claudeAgent` / `claude-fable-5-1` / `options {effort: "high"}`; the receipt goes to `claim`, which refuses receipts without the exact model and effort. One active implementer per story and per run, enforced under the store lock.
4. `record-head` with the exact commit, then `run-checks` in the claimed worktree. Checks fail ⇒ `repair` (new implementer task, round 1 or 2) or `block`; `record-head` after a failure without `repair` is refused.
5. `request-review` only after the full configured check set passed at that commit, with a fresh `codex` / `gpt-6-astra` / `options {reasoningEffort: "high"}` receipt. `record-review` binds the verdict to the commit; a later commit invalidates it.
6. `propose-evidence` after approval: revisions unchanged, PR head equals the approved commit, PR open and unmerged, no reviewer with an outstanding `CHANGES_REQUESTED` (per reviewer, at any commit, until dismissed or re-reviewed), CI not failing; posts the proposal comment. Merge, `Done`, Status and closing remain owner actions.
7. Stop conditions: budgets in policy (stories per run, delegated tasks, repair rounds, wall clock), any `blocked` or `conflict` story, any refusal or transport error. `cancel`/`cancel-run` post release markers; `resume` checks the worktree identity first, replays pending effects with the same operation identity, then refuses on changed revisions.

**Enforceability.** The tool is a subprocess; T3 tools are MCP calls available only to the coordinator agent. Inspected contracts (`orchestrator_capabilities`, `delegate_task`, `task_status`, `task_cancel`, `t3_thread_wait`, `t3_worktree_status`, `request_secret`, `schedule_task`) give no way for the tool to make admission precede a delegated task, to observe a cancellation acknowledgement, or to terminate a child on a budget (`timeoutMs` applies to `mode: wait` only and "does not cancel the child"). Steps 3, 4 and 7 are therefore instructions the agent follows, not guarantees the tool enforces. Until that changes, `claim` on the live transport is refused (`live-execution-disabled`) and the state machine is exercised only through the fixture transport. Smallest upstream changes that would close the gap: a `delegate_task` admission hook or pre-start command, an acknowledged terminal state for `task_cancel` readable through `task_status`, a child deadline that cancels, and a CLI or socket through which a subprocess can call `task_status`/`task_cancel`.

## Guarantees and limits (precise)

- **Revisions.** Admission and every proposal compare the recorded revisions (issue `updatedAt`, body hash, state, state reason, Project item `updatedAt`, Status) of the story's closure with a fresh read; any difference refuses. `rebase-revisions` is the only way to accept a change, and it is explicit, journaled and needs `--live` and a reason.
- **No owner field is written.** The only write is appending an issue comment. There is nothing to overwrite, so no compare-and-swap is needed or claimed.
- **Operation identity.** Each effect has a stable operation id; retries and restarts reuse it. Zero markers ⇒ re-post, one ⇒ adopt, more than one ⇒ `conflict`, on first execution and on resume alike. Terminal cleanups (`release`, `block`) stay pending until replayed.
- **Serialization.** One non-blocking `fcntl` lock per state directory covers admission, budgets and effects; a second coordinator (same or another process) gets `store-busy`. Coordinators on other machines are detected through foreign claim markers, not excluded.
- **Fail closed.** Unknown declarations, missing Project items, inconsistent issue state, permission denial, outage, parse failures, run-binding mismatches and worktree mismatches refuse without advancing.
- **Live transport.** Fixture tests cover the fault matrix and the production transport parser with realistic responses. Live GitHub evidence is read-only plus one idempotent comment on #106. Live T3 evidence is this tool's own delegated-task receipt. No product story has been dispatched.

## Permissions and secrets

Minimum GitHub access: classic scopes `repo` and `project`, or a fine-grained token with Issues read/write, Pull requests read, Contents read, Metadata read and user Projects read/write. `check-permissions` reports `basic_access` (can act) separately from `bounded` (provably cannot act beyond the minimum). On 2026-11-06 the operator token has basic access but is **not bounded** (admin on the repository; excess scopes `admin:public_key`, `gist`, `read:org`, `workflow`), so unattended activation is not allowed. A bounded identity has not been provisioned; the exact requirement and test plan are in `_bmad-output/implementation-artifacts/unattended-execution/permissions.md`. Tokens never enter policy, state or logs; a `GH_TOKEN` for a bounded identity is obtained through T3 `request_secret` with file delivery, exported for the command only.

## Candidate first activation (blocked)

`automation/examples/first-run-om-01-02.toml` allowlists OM-01.02 only. The 2026-11-06 dry run reports `awaiting-owner-acceptance` (Status `Backlog`). Activation is blocked until all of: owner sets OM-01.02 to `Ready`; ENG-01 reviewed and merged; a bounded credential passes `check-permissions`; the T3 enforcement gaps above are closed upstream and the `live-execution-disabled` gate is removed in a reviewed change; `verify-mapping` and `probe` pass on the coordinator machine. OM-01.02's own Kubernetes, storage, identity, secrets and live gates are untouched by this foundation.
