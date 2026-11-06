# Unattended execution foundation (ENG-01)

`automation/unattended` is the smallest supported bridge between the GitHub backlog that owns engineering progress ([tracking contract](engineering-tracking.md)) and a T3 coordinator that dispatches story work. It is engineering automation, tracked in [ENG-01 (#106)](https://github.com/gabrianoo/owl-mast/issues/106), outside the OM product numbering. It does not run on its own: a T3 coordinator thread calls it between `delegate_task` turns. There is no loop, schedule or daemon, and the installed `bmad-loop` CLI is not used.

**State on 2026-11-06 (after repair round 2, the last):**

| Level | Meaning | Status |
| --- | --- | --- |
| Code implementation | The state machine, revision checks, locking, intents, checks runner and probes exist | yes |
| Passing fixture coverage | Fault matrix and production transport parser pass in the unit suite (137 tests) against an in-memory GitHub and a real local git worktree | yes |
| Live support | Read-only snapshot, mapping verification and dry run against live GitHub; one idempotent marker comment on the engineering issue; every state command refuses the real transport | read-only plus one probe; execution refused |
| Unmet requirements | T3 execution protocol qualified with an actual bounded worker; bounded credential with tested denial; Project Status synchronization | **unmet, blocked** |

The foundation is **not qualified for unattended use**. `reserve` and every other state command refuse the real GitHub transport (`live-execution-disabled`), and run state created against the fixture transport cannot be reopened with the real one (`environment-mismatch`).

## What GitHub owns and who writes what

| Fact | Where | Writer | Meaning |
| --- | --- | --- | --- |
| Stable ID, parent epic, `Depends on`, `Epic prerequisites`, tasks | Issue body | Owner through Git-revised specs | Specification. Read with a strict grammar (`None` or a comma-separated list of ids); anything else is unknown and blocks dispatch. |
| Project Status (`Backlog`, `Ready`, `In progress`, `In review`, `Blocked`, `Done`) | Project 2 Status field | **Owner only** | `Ready` = owner acceptance; `Done` = accepted completion. GitHub offers no compare-and-swap, so the machine never writes this field. It reads it for eligibility and treats any change as a stale revision. |
| Machine checkpoints | Issue comments `<!-- unattended kind=… run=… story=… op=… -->` | Machine, append-only | `claim`, `release`, `block`, `proposal`, `probe`. One comment per operation identity; a duplicate is a conflict. |
| Task checkboxes | Issue body | Owner | The `proposal` comment lists tasks with the exact commit; the owner ticks them. |
| Issue open/closed | Issue | Owner | Closing as completed is acceptance; any other or unknown close reason is not. |
| CI pass, review approval, merge, deployment | PR checks, PR reviews, merge, release | GitHub / reviewer / owner | Read, never written; each stays a distinct fact. |

Project Status synchronization is **not implemented**: there is no safe equivalent on GitHub's API. The owner moves Status by reading the machine's comments.

Dispatch is possible only when all of these hold: the story is in the policy allowlist; its epic is not E17/E19 (unless explicitly included); its Project item exists with a matching Stable ID; both declarations parse; Status is `Ready`; every `Depends on` story and every story of a prerequisite epic is `Done` **and** closed with the explicit reason `COMPLETED`. A story in `contract_design_exceptions` may run its designated design portion before prerequisites, flagged `dispatchable-contract-design-only`. Anything unknown fails closed.

## Commands

All commands print one JSON document. Global flags go before the command.

```sh
python3 -m automation.unattended verify-mapping            # 19/85/340 and relationships against live GitHub
python3 -m automation.unattended --policy automation/examples/first-run-om-01-02.toml plan   # dry run, writes nothing
python3 -m automation.unattended check-permissions         # basic_access observation; bounded and activation are never granted by this probe (exit 2)
python3 -m automation.unattended probe                     # environment probes from policy
python3 -m unittest discover -s automation/tests -t .      # qualification suite (fixtures)
```

State commands need `--run-id`; anything that can reach a GitHub write also needs `--live` (`reserve`, `repair`, `propose-evidence`, `block`, `cancel`, `cancel-run`, `resume`, `rebase-revisions`, `probe-write`). On the real transport every state command refuses today. State lives under `.unattended-runs/<run-id>/` (gitignored: `run.json` with its environment binding, `journal.jsonl`, `stories/<ID>.json`); a store-wide `fcntl` lock serializes every operation across processes.

```sh
U="python3 -m automation.unattended --live --run-id <run-id>"
$U reserve OM-01.02 --baseline <sha>                           # admission BEFORE delegate_task (refused on the real transport today)
$U bind-receipt OM-01.02 --receipt receipt.json --worktree <path> --branch <branch>   # after delegate_task returned its id
$U record-head OM-01.02 --sha <sha>                           # the implementer task returned
$U run-checks OM-01.02 --sha <sha> --cwd <worktree>           # full configured set on the exact clean HEAD; the only check evidence
$U request-review OM-01.02 --sha <sha> --receipt reviewer-receipt.json   # worktree re-read; fresh reviewer task
$U record-review OM-01.02 --sha <sha> --verdict approved|changes-requested --report <ref>
$U repair OM-01.02 --receipt receipt.json                     # budgeted; required after any failure; at most two rounds, then blocked
$U propose-evidence OM-01.02 --sha <sha> --pr <n> --task OM-01.02-T1 --summary "…"
$U cancel|block OM-01.02 --reason "…" [--task-evidence '{"taskId": "...", "status": "result_available"}']
$U cancel-run --reason "…" [--task-evidence '{"OM-01.02": {...}}'];  $U resume OM-01.02;  $U rebase-revisions OM-01.02 --reason "…";  $U status
```

## Coordinator protocol (T3) and what is and is not established

1. `verify-mapping` and `probe` must pass; `check-permissions` must report `basic_access` (it never reports a bounded credential, see below).
2. `plan` decides eligibility from a fresh snapshot. `reserve` re-reads every revision the decision depends on (story, parent epic, dependency closure, Project items) under the store lock and posts the claim marker **before** any task exists.
3. `delegate_task` with `isolation: "worktree"`, `role: "implementation"`, target `claudeAgent` / `claude-fable-5-1` / `options {effort: "high"}`; `bind-receipt` validates the receipt (exact model and effort), the worktree identity, and counts the delegation. One active story per run, enforced under the lock; a story is admitted at most once per run (no reclaim).
4. `record-head` with the exact commit when the task returns, then `run-checks` in the claimed worktree. Checks fail ⇒ `repair` (new implementer task, round 1 or 2) or `block`; `record-head` after a failure without `repair` is refused.
5. `request-review` only after the full configured check set passed at that commit **and** the worktree still reads that commit and is clean; a fresh `codex` / `gpt-6-astra` / `options {reasoningEffort: "high"}` receipt. `record-review` binds the verdict to the commit and re-reads the worktree; any unreported change invalidates check and review evidence.
6. `propose-evidence` after approval: revisions unchanged, worktree re-read, PR head equals the approved commit, PR open and unmerged, every review page read, no reviewer with an outstanding `CHANGES_REQUESTED`, CI not failing; posts the persisted proposal body. Merge, `Done`, Status and closing remain owner actions.
7. Ownership is released only with terminal task evidence while a worker is running: `cancel`/`block` need `{taskId, status}` from `task_status` (`workState: result_available`) or a terminal `task_cancel` result; `cancel-run` stops admissions and reports stories still awaiting termination. `resume` checks the worktree identity first, replays cleanups, re-validates advancing effects (revisions, worktree, PR) before posting their persisted payload, then refuses on changed revisions.

**What the installed T3 tools support and what this foundation has not done.** The tool metadata supports the protocol above: reservation happens under the local lock before `delegate_task`; the receipt is bound afterwards; `task_status` reports `workState` (`working`, `waiting_for_children`, `result_available`) and the final summary; `task_cancel` stops the task's running and queued turns and its delegates and, per the coordinator's inspection of the tool metadata, reports `cancel_requested` or a terminal state. No admission hook or subprocess bridge is required for that protocol. What remains **unestablished**: a hard deadline or resource bound on a delegated child (`timeoutMs` limits the wait in `mode: wait` only and does not cancel the child), credential confinement of the child (it runs with the coordinator's credentials and runtime mode), and any qualification of the protocol with an actual bounded worker. Because of that, every state command refuses the real transport. The smallest upstream change that closes a verified gap is a child deadline that cancels (or an equivalent resource bound); the rest is qualification work with a bounded worker and credential, not a tool change.

## Guarantees and limits (precise)

- **Revisions.** Admission, every proposal and every resume compare the recorded revisions (issue `updatedAt`, body hash, state, close reason, Project item `updatedAt`, Status) of the story's closure with a fresh read; any difference refuses. `rebase-revisions` is the only way to accept a change, and it is explicit, journaled and needs `--live` and a reason.
- **No owner field is written.** The only write is appending an issue comment. There is nothing to overwrite, so no compare-and-swap is needed or claimed.
- **Operation identity and payload.** Each effect is a write-ahead intent with a stable operation id and its complete comment body. Replays post exactly that body. Zero markers ⇒ post, one ⇒ adopt, more than one ⇒ `conflict`, on first execution and on resume alike. Advancing replays (claim, proposal) re-verify their preconditions before posting; a failed re-verification posts nothing. Terminal phases persist together with their cleanup intent, so a crash between the two cannot strand ownership.
- **Serialization and binding.** One non-blocking `fcntl` lock per state directory covers admission, budgets and effects; a second coordinator (same or another process) gets `store-busy`. A run is bound to its repository, policy digest and environment. Coordinators on other machines are detected through foreign claim markers, not excluded.
- **Fail closed.** Unknown declarations, unknown close reasons, missing Project items, inconsistent issue state, permission denial, outage, malformed or truncated review pages, parse failures, binding mismatches and worktree mismatches refuse without advancing.
- **Live transport.** Fixture tests cover the fault matrix and the production transport parser with realistic responses. Live GitHub evidence is read-only plus one idempotent comment on #106. Live T3 evidence is this tool's own delegated-task receipt. No product story has been dispatched and none can be until the gate is removed in a reviewed change.

## Permissions and secrets

This tool needs: Issues read/write (comments), Pull requests read, Contents read, Metadata read, and **Project read**. Pushing implementation branches and opening PRs is the implementer identity's privilege, assessed separately. `check-permissions` reports `basic_access` (the identity can act) and always reports `bounded: false` and `unattended_activation_allowed: false`, because scope names, push and a non-admin flag never prove a bounded credential (classic `repo` is broad by definition); `denial_tested` and `resource_scope_verified` stay false until a qualification this probe does not perform. On 2026-11-06 the operator token has basic access, is admin, can update the Project, and carries `admin:public_key`, `gist`, `read:org`, `workflow`. Candidate credentials and their open questions are in `_bmad-output/implementation-artifacts/unattended-execution/permissions.md`; none has been provisioned or tested. Tokens never enter policy, state or logs; a bounded identity's `GH_TOKEN` would be obtained through T3 `request_secret` with file delivery and exported for the command only.

## Candidate first activation (blocked)

`automation/examples/first-run-om-01-02.toml` allowlists OM-01.02 only. The 2026-11-06 dry run reports `awaiting-owner-acceptance` (Status `Backlog`). Activation is blocked until all of: owner sets OM-01.02 to `Ready`; ENG-01 reviewed and merged; a bounded credential passes a denial-tested qualification; the T3 protocol is qualified with an actual bounded worker including a termination bound; the `live-execution-disabled` gate is removed in a reviewed change; `verify-mapping` and `probe` pass on the coordinator machine. OM-01.02's own Kubernetes, storage, identity, secrets and live gates are untouched by this foundation.
