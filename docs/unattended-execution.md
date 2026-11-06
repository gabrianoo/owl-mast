# Unattended execution foundation (ENG-01)

`automation/unattended` is the smallest supported bridge between the GitHub backlog that owns engineering progress ([tracking contract](engineering-tracking.md)) and a T3 coordinator that dispatches story work. It is engineering automation, tracked in [ENG-01 (#106)](https://github.com/gabrianoo/owl-mast/issues/106), outside the OM product numbering. It does not run on its own: a T3 coordinator thread calls it between `delegate_task` turns. There is no loop, schedule or daemon, and the installed `bmad-loop` CLI is not used.

**State on 2026-11-06 (remediation pass 1 after the final disposition of PR #107; awaiting a fresh independent review):**

| Level | Meaning | Status |
| --- | --- | --- |
| Code implementation | The state machine, revision checks, locking, intents, pre-launch task authorizations, independent active-task ownership, checks runner and probes exist | yes |
| Passing fixture coverage | Fault matrix, the six final-disposition scenarios (combined transitions, crash/restart, tampered and legacy state) and the production transport parser pass in the unit suite (170 tests) against an in-memory GitHub and a real local git worktree | yes, not independently reviewed yet |
| Live support | Read-only snapshot, mapping verification and dry run against live GitHub; one idempotent marker comment on the engineering issue; every state command refuses the real transport | read-only plus one probe; execution refused |
| Unmet requirements | T3 execution protocol qualified with an actual bounded worker (hard child deadline/resource bound, credential confinement, launches visible to the tool); bounded credential with tested denial; Project Status synchronization | **unmet, blocked** |

The foundation is **not qualified for unattended use**. `reserve` and every other state command refuse the real GitHub transport (`live-execution-disabled`), and run state created against the fixture transport cannot be reopened with the real one (`environment-mismatch`). The final disposition of 2026-11-06 (PR #107, comment 6686575345) verified six defects on head `a0fa769e`; this pass fixes them with adversarial tests and records the before/after reproduction (`evidence/final-findings-repro-{before,after}-2026-11-06.txt`). Passing tests are fixture evidence, not qualification.

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

State commands need `--run-id`; anything that can reach a GitHub write also needs `--live` (`reserve`, `authorize-repair`, `propose-evidence`, `block`, `cancel`, `cancel-run`, `resume`, `rebase-revisions`, `probe-write`). On the real transport every state command refuses today. State lives under `.unattended-runs/<run-id>/` (gitignored: `run.json` with its environment binding, `journal.jsonl`, `stories/<ID>.json`); a store-wide `fcntl` lock serializes every operation across processes. Budgets are derived from the story files under that lock; `run.json` counters are a cache for `status`.

```sh
U="python3 -m automation.unattended --live --run-id <run-id>"
E='{"taskId": "<id>", "status": "result_available"}'            # terminal evidence from task_status (or a terminal task_cancel result) for the ACTIVE task
$U reserve OM-01.02 --baseline <sha>                           # admission + implementer authorization BEFORE delegate_task (refused on the real transport today)
$U bind-receipt OM-01.02 --receipt receipt.json --worktree <path> --branch <branch>   # consumes the authorization after delegate_task returned its id
$U record-head OM-01.02 --sha <sha> --task-evidence "$E"       # the implementer task is terminal; its exact commit is recorded
$U run-checks OM-01.02 --sha <sha> --cwd <worktree>           # full configured set on the exact clean HEAD; the only check evidence
$U authorize-review OM-01.02 --sha <sha>                      # worktree re-read; reviewer authorization BEFORE delegate_task
$U bind-receipt OM-01.02 --receipt reviewer-receipt.json      # consumes it; the reviewer is now the active task
$U record-review OM-01.02 --sha <sha> --verdict approved|changes-requested --report <ref> --task-evidence "$E"
$U authorize-repair OM-01.02                                  # budgeted; required after any failure; at most two rounds, then blocked; then bind-receipt
$U record-task-terminal OM-01.02 --task-evidence "$E"         # release the active task without recording anything else (e.g. after an invalidation)
$U propose-evidence OM-01.02 --sha <sha> --pr <n> --task OM-01.02-T1 --summary "…"
$U cancel|block OM-01.02 --reason "…" [--task-evidence "$E"]  # required while a task is active
$U cancel-run --reason "…" [--task-evidence '{"OM-01.02": {...}}'];  $U resume OM-01.02;  $U rebase-revisions OM-01.02 --reason "…";  $U status
```

## Coordinator protocol (T3) and what is and is not established

1. `verify-mapping` and `probe` must pass; `check-permissions` must report `basic_access` (it never reports a bounded credential, see below).
2. `plan` decides eligibility from a fresh snapshot; a stable id carried by more than one issue (in the plan snapshot or the fresh read) is `ambiguous-identity` and admits nothing. `reserve` re-reads every revision the decision depends on (story, parent epic, dependency closure, Project items) under the store lock, issues the implementer **task authorization** (counted against `max_delegated_tasks` from that moment, bound or not) and posts the claim marker **before** any task exists; an exhausted task budget refuses here, before any launch.
3. `delegate_task` with `isolation: "worktree"`, `role: "implementation"`, target `claudeAgent` / `claude-fable-5-1` / `options {effort: "high"}`; `bind-receipt` validates the receipt (exact model and effort, fresh task id), the worktree identity, consumes the pending authorization and makes the task the story's **active task**. One active story per run and one active task per story, enforced under the lock; a story is admitted at most once per run (no reclaim); an authorization binds once.
4. `record-head` with the exact commit and the implementer's terminal evidence (`task_status` `workState: result_available` or a terminal `task_cancel` result), then `run-checks` in the claimed worktree. Checks fail ⇒ `authorize-repair` (round 1 or 2, counted at authorization, then `bind-receipt` of the new implementer task) or `block`; `record-head` after a failure without an authorized and bound repair is refused.
5. `authorize-review` only after the full configured check set passed at that commit, the worktree still reads that commit and is clean, and no task is active; then `delegate_task` for a fresh `codex` / `gpt-6-astra` / `options {reasoningEffort: "high"}` reviewer and `bind-receipt`. `record-review` needs the reviewer's terminal evidence, binds the verdict to the commit and re-reads the worktree; any unreported change or a new commit invalidates check and review evidence and abandons a pending proposal, but never releases the active task.
6. `propose-evidence` after approval: phase `review-approved`, approved and head SHA equal to the proposed commit, no active task, revisions unchanged, worktree re-read, PR head equals the approved commit, PR open and unmerged, every review page read, no reviewer with an outstanding `CHANGES_REQUESTED`, CI not failing; posts the persisted proposal body and the `proposed` phase in one write. Merge, `Done`, Status and closing remain owner actions.
7. Ownership is released only with terminal evidence for exactly the active task: `cancel`/`block`/`record-task-terminal` need `{taskId, status}` matching it (implementer evidence never releases a reviewer); `cancel-run` marks the run cancelled, releases the stories without an active task and reports the rest; a cancelled run refuses every advancing operation. Cancelling or blocking a story abandons its pending advancing intents in the same write as the terminal phase. `resume` checks the worktree identity first, replays cleanups, reconciles a completed intent whose transition did not persist, abandons advancing intents of a terminal story or a cancelled run, re-validates the remaining ones (current phase and exact-SHA approval, revisions, worktree, PR) before posting their persisted payload, then refuses on changed revisions.

**What the installed T3 tools support and what this foundation has not done.** The tool metadata supports the protocol above: authorization happens under the local lock before `delegate_task`; the receipt is bound afterwards; `task_status` reports `workState` (`working`, `waiting_for_children`, `result_available`) and the final summary; `task_cancel` stops the task's running and queued turns and its delegates and, per the coordinator's inspection of the tool metadata, reports `cancel_requested` or a terminal state. No admission hook or subprocess bridge is required for that protocol. What remains **unestablished**: a hard deadline or resource bound on a delegated child (`timeoutMs` limits the wait in `mode: wait` only and does not cancel the child), credential confinement of the child (it runs with the coordinator's credentials and runtime mode), visibility of launches (the tool bounds what can be bound; a task launched without an authorization, or launched twice for one authorization, is invisible to it and is the coordinator's to cancel), and any qualification of the protocol with an actual bounded worker. Because of that, every state command refuses the real transport. The smallest upstream change that closes a verified gap is a child deadline that cancels (or an equivalent resource bound); the rest is qualification work with a bounded worker and credential, not a tool change.

## Guarantees and limits (precise)

- **Revisions.** Admission, every proposal and every resume compare the recorded revisions (issue `updatedAt`, body hash, state, close reason, Project item `updatedAt`, Status) of the story's closure with a fresh read; any difference refuses. `rebase-revisions` is the only way to accept a change, and it is explicit, journaled and needs `--live` and a reason.
- **No owner field is written.** The only write is appending an issue comment. There is nothing to overwrite, so no compare-and-swap is needed or claimed.
- **Operation identity and payload.** Each effect is a write-ahead intent with a stable operation id and its complete comment body. Replays post exactly that body. Zero markers ⇒ post, one ⇒ adopt, more than one ⇒ `conflict`, on first execution and on resume alike. An intent's completion and the phase it carries (`reserved`, `proposed`) persist in one write; a completed intent found without its transition is reconciled on resume without posting. Advancing replays (claim, proposal) run only for an active story in a run that is not cancelled and re-verify their preconditions (for a proposal: phase `review-approved`, approved and head SHA equal to the intent's SHA, no active task, then revisions, worktree and PR) before posting; otherwise the intent is abandoned and nothing is posted. Terminal phases persist together with their cleanup intent and the abandonment of every pending advancing intent, so a crash cannot strand ownership or replay an abandoned effect.
- **Task capacity and ownership.** Every delegated task is authorized durably before its launch (`reserve`, `authorize-review`, `authorize-repair`); an issued authorization counts against `max_delegated_tasks` whether or not it is bound, `bind-receipt` consumes exactly one, repair rounds are counted at authorization, and all three budgets are derived from the story files under the lock (corrupted or stale `run.json` counters cannot bypass them). The active task (id, role) is independent of the phase: HEAD recording (same or new SHA), verdicts and evidence invalidation never release it; only terminal evidence for exactly that task does. A story state file with another schema is refused, never reinterpreted.
- **Serialization and binding.** One non-blocking `fcntl` lock per state directory covers admission, budgets and effects; a second coordinator (same or another process) gets `store-busy`. A run is bound to its repository, policy digest and environment. Coordinators on other machines are detected through foreign claim markers, not excluded.
- **Fail closed.** Unknown declarations, unknown close reasons, duplicate stable ids, missing Project items, inconsistent issue state, permission denial, outage, malformed or truncated review pages, parse failures, binding, schema and worktree mismatches refuse without advancing.
- **Live transport.** Fixture tests cover the fault matrix and the production transport parser with realistic responses. Live GitHub evidence is read-only plus one idempotent comment on #106. Live T3 evidence is this tool's own delegated-task receipt. No product story has been dispatched and none can be until the gate is removed in a reviewed change.

## Permissions and secrets

This tool needs: Issues read/write (comments), Pull requests read, Contents read, Metadata read, and **Project read**. Pushing implementation branches and opening PRs is the implementer identity's privilege, assessed separately. `check-permissions` reports `basic_access` (the identity can act) and always reports `bounded: false` and `unattended_activation_allowed: false`, because scope names, push and a non-admin flag never prove a bounded credential (classic `repo` is broad by definition); `denial_tested` and `resource_scope_verified` stay false until a qualification this probe does not perform. On 2026-11-06 the operator token has basic access, is admin, can update the Project, and carries `admin:public_key`, `gist`, `read:org`, `workflow`. Candidate credentials and their open questions are in `_bmad-output/implementation-artifacts/unattended-execution/permissions.md`; none has been provisioned or tested. Tokens never enter policy, state or logs; a bounded identity's `GH_TOKEN` would be obtained through T3 `request_secret` with file delivery and exported for the command only.

## Candidate first activation (blocked)

`automation/examples/first-run-om-01-02.toml` allowlists OM-01.02 only. The 2026-11-06 dry run reports `awaiting-owner-acceptance` (Status `Backlog`). Activation is blocked until all of: the remediation pass 1 passes a fresh independent exact-commit review (at most two further repair passes are authorized); owner sets OM-01.02 to `Ready`; ENG-01 reviewed and merged; a bounded credential passes a denial-tested qualification; the T3 protocol is qualified with an actual bounded worker including a termination bound and credential confinement; the `live-execution-disabled` gate is removed in a reviewed change; `verify-mapping` and `probe` pass on the coordinator machine. OM-01.02's own Kubernetes, storage, identity, secrets and live gates are untouched by this foundation. The existing `cancel-run`/`resume` commands are fixture-covered controls, not approved operational controls for product use.
