# ENG-01 permissions: minimum, observed, blocker (repair round 2)

## GitHub: what this tool needs

| Need | Minimum | Observed on 2026-11-06 (`check-permissions`) |
| --- | --- | --- |
| Read issues, bodies, comments, sub-issue parents | Issues: read, Metadata: read (classic: `repo`) | present |
| Post marker comments | Issues: write (classic: `repo`) | present |
| Read Project 2 items and fields | Projects: **read** (classic: `read:project`; `project` is more than needed) | present, and the identity can also update the Project (excess) |
| Read PR head, reviews, status rollup | Pull requests: read (classic: `repo`) | present |

Pushing implementation branches and opening PRs belongs to the implementer identity (the delegated task), not to this tool; it is assessed separately and is not part of this minimum.

Verdicts: `basic_access: true`; `bounded: false`; `denial_tested: false`; `resource_scope_verified: false`; `unattended_activation_allowed: false`. Reasons recorded: admin on the repository; excess scopes `admin:public_key`, `gist`, `read:org`, `workflow`; classic `repo` is broad by definition; the identity can update the Project; denial untested; resource scope unverified. The probe never grants `bounded` or activation from scope headers or the admin flag; both require a qualification it does not perform. Full record: `evidence/check-permissions-2026-11-06.json`.

## Candidate bounded credentials (proposals, none provisioned or qualified)

GitHub documents, under "Fine-grained personal access tokens limitations", that "Using fine-grained personal access token to access Projects owned by a user account" is a current gap ([managing personal access tokens](https://docs.github.com/en/authentication/keeping-your-account-and-data-secure/managing-your-personal-access-tokens)). Project 2 is owned by the user account, so a fine-grained PAT cannot be assumed to read it. Classic scopes: `read:project` "Grants read only access to user and organization projects"; `project` grants read/write; `repo` "Grants full access to public and private repositories" and also manages user-owned projects ([OAuth scopes](https://docs.github.com/en/apps/oauth-apps/building-oauth-apps/scopes-for-oauth-apps)).

| Proposal | Shape | Open question before it can qualify |
| --- | --- | --- |
| A. Fine-grained PAT, repository `gabrianoo/owl-mast` only: Issues RW, Pull requests R, Contents R, Metadata R | smallest repository boundary | cannot read a user-owned Project per the documented limitation; the Project read would need proposal C or a separate read-only identity |
| B. Classic PAT with `repo` + `read:project` | reads the user Project; no write to it | `repo` is full repository access, so it is bounded only at the repository-admin boundary, not at the operation boundary; denial testing cannot narrow `repo` |
| C. Move the Project to an organization and use a GitHub App installation or fine-grained PAT with organization Projects: read | operation-level boundary | organizational change owned by the user; not available today |

Qualification steps for whichever the owner selects (not performed): run `check-permissions` and record `basic_access`; attempt a forbidden read-only operation (for example `gh api repos/gabrianoo/owl-mast/actions/secrets`, expected 403) and a forbidden Project write and record both denials (`denial_tested`); list the resources the token can see and confirm one repository and one Project (`resource_scope_verified`); only then may a reviewed change let the probe report `bounded`. The credential is provided through T3 `request_secret` (`delivery: "file"`) and exported as `GH_TOKEN` for the command only; it never enters policy, state, logs or chat. No credential was requested in this round.

## T3: what the tools support, what is implemented, what is not qualified

| Need | Tool support (inspected metadata) | This foundation |
| --- | --- | --- |
| Explicit implementer and reviewer targets with effort | `orchestrator_capabilities` lists `claude-fable-5-1` `effort` and `gpt-6-astra` `reasoningEffort` values incl. `high`; this task's receipt shows the inherited target (`evidence/t3-task-receipt-2026-11-06.json`) | receipt validation implemented; a false receipt is not detectable |
| Admission before the task starts | `delegate_task` returns a task id; nothing prevents the coordinator from reserving first | implemented as `reserve` (under the lock, claim marker) then `bind-receipt`; not exercised with a real task |
| Isolated worktree, identity and resume | `delegate_task` `isolation: "worktree"`; `t3_worktree_status` reports path/branch | recorded at bind; re-read at every evidence gate and before resume effects |
| Terminal task evidence before releasing ownership | `task_status` reports `workState` (`working`, `waiting_for_children`, `result_available`) and the final summary; `task_cancel` stops running and queued turns and delegates and, per the coordinator's inspection of the tool metadata, reports `cancel_requested` or a terminal state | implemented as required `{taskId, status}` evidence for `cancel`/`block`; `cancel_requested` is not terminal; not exercised with a real task |
| Hard deadline or resource bound on a child | **not available**: `timeoutMs` applies to `mode: wait` only and "does not cancel the child"; no resource options | unmet; smallest upstream change: a child deadline that cancels or an equivalent bound |
| Credential confinement of a child | **not established**: the child runs with the coordinator's credentials and a runtime mode at most the parent's | unmet |
| No schedules or competing runners | `list_scheduled_tasks` returned none; `.bmad-loop/` holds only the untouched policy | observed |

Consequence: every state command refuses the real transport (`live-execution-disabled`); fixture-born state cannot be reopened with it (`environment-mismatch`). The protocol above is implemented and fixture-covered but has not been qualified with an actual bounded worker, and no such qualification launch happened in this work.

## Filesystem and containers

| Need | Scope |
| --- | --- |
| Read the repository checkout; write `.unattended-runs/` (state, `.lock`) | Repository root of the coordinator checkout (gitignored). |
| Implementer worktrees | `~/.t3/worktrees/<project>/…` created by T3; the tool records and re-checks path/branch, HEAD and cleanliness. |
| Deterministic checks (`./gradlew build`, `scripts/verify-quality-gates.sh`, unit suite) | A JDK to launch the wrapper and a reachable Docker-compatible runtime (`docker version` probe). |
| Nothing else | No home-directory, credential-store or system configuration access. |

## Budgets and stopping conditions (policy)

`max_stories_per_run = 1`, `max_concurrent_implementers = 1` (fixed), `max_repair_rounds = 2` (ceiling), `max_delegated_tasks = 6`, `max_wall_clock_minutes = 240`; empty allowlist by default; E17/E19 excluded. Any refusal, transport error, blocked or conflicted story or exhausted budget stops the state machine from admitting further work; it cannot terminate a running T3 task, and ownership of a running task is kept until terminal evidence arrives.
