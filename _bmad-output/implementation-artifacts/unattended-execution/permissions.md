# ENG-01 permissions: minimum, observed, blocker (remediation pass 1, repair pass 1; unchanged observations)

> **Supersession (2026-11-06).** The owner accepted the trusted-machine operating agreement (`../spec-eng-01-trusted-operation.md`). Where this document lists hard child deadline/resource bounds, credential confinement, denial-tested bounded credentials or automated Project Status synchronization as *prerequisites*, they are now accepted residual risks or manual owner steps; the controls, refusals and guards described here remain in force and nothing historical below is rewritten. Activation remains disabled.

## GitHub: what this tool needs

| Need | Minimum | Observed on 2026-11-06 (`check-permissions`) |
| --- | --- | --- |
| Read issues, bodies, comments, sub-issue parents | Issues: read, Metadata: read (classic: `repo`) | present |
| Post marker comments | Issues: write (classic: `repo`) | present |
| Read Project 2 items and fields | Projects: **read** (fine-grained: Projects read; classic: `read:project` names the need, but see below: classic scopes are a union and any classic token able to post comments carries `repo`, which also manages user-owned Projects) | present, and the identity can also update the Project (excess) |
| Read PR head, reviews, status rollup | Pull requests: read (classic: `repo`) | present |

Pushing implementation branches and opening PRs belongs to the implementer identity (the delegated task), not to this tool; it is assessed separately and is not part of this minimum.

Verdicts: `basic_access: true`; `bounded: false`; `denial_tested: false`; `resource_scope_verified: false`; `unattended_activation_allowed: false`. Reasons recorded: admin on the repository; excess scopes `admin:public_key`, `gist`, `read:org`, `workflow`; classic `repo` is broad by definition; the identity can update the Project; denial untested; resource scope unverified. The probe never grants `bounded` or activation from scope headers or the admin flag; both require a qualification it does not perform. Full record: `evidence/check-permissions-2026-11-06.json`.

## Candidate bounded credentials (proposals, none provisioned or qualified; under the agreement, use restricted credentials where practical and disclose broad ones as broad, never certify them bounded)

GitHub documents, under "Fine-grained personal access tokens limitations", that "Using fine-grained personal access token to access Projects owned by a user account" is a current gap ([managing personal access tokens](https://docs.github.com/en/authentication/keeping-your-account-and-data-secure/managing-your-personal-access-tokens)). Project 2 is owned by the user account, so a fine-grained PAT cannot be assumed to read it. Classic scopes, quoted from the primary source ([Scopes for OAuth apps](https://docs.github.com/en/apps/oauth-apps/building-oauth-apps/scopes-for-oauth-apps), read 2026-11-06): `read:project` "Grants read only access to user and organization projects"; `project` "Grants read/write access to user and organization projects"; `repo` "Grants full access to public and private repositories …" and "This scope also grants the ability to manage projects owned by users." Scopes grant a union of capabilities: adding `read:project` next to `repo` narrows nothing, so **no classic token that can post issue comments (which needs `repo`) is read-only on a user-owned Project**.

| Proposal | Shape | Open question before it can qualify |
| --- | --- | --- |
| A. Fine-grained PAT, repository `gabrianoo/owl-mast` only: Issues RW, Pull requests R, Contents R, Metadata R | smallest repository boundary | cannot read a user-owned Project per the documented limitation; the Project read would need proposal C or a separate read-only identity |
| B. Classic PAT with `repo` + `read:project` | reads the user Project **and can write it**: `repo` alone grants management of user-owned Projects, and `read:project` adds nothing that restricts it | **disqualified** for the required operation boundary (Project read-only, comment-only writes): the earlier claim "no write to it" was false; `repo` is full repository access and user-Project management, so B is bounded only at the repository-admin boundary and a denial test of a Project write would *succeed*, not be denied |
| D. Split identities: fine-grained PAT as in A for issues/comments/PR reads, plus a classic PAT carrying only `read:project` for the Project read | smallest classic footprint that is read-only on the Project (`read:project` without `repo`) | two credentials for one tool; the `read:project`-only token's actual reach on a user-owned Project and on repository issues is unverified; the tool would need per-call credential selection it does not have today |
| C. Move the Project to an organization and use a GitHub App installation or fine-grained PAT with organization Projects: read | operation-level boundary | organizational change owned by the user; not available today |

Qualification steps for whichever candidate the owner selects (A, C or D; B is disqualified above), none performed:

1. Run `check-permissions` and record `basic_access`.
2. Attempt a forbidden **read-only** operation on the real repository (for example `gh api repos/gabrianoo/owl-mast/actions/secrets`, expected 403) and record the denial. A read cannot mutate anything, so the live repository is an acceptable target.
3. **Denial of a Project write is probed only against a separately authorized disposable qualification resource** (a throwaway Project, or a throwaway repository with its own Project, created for the qualification and deleted afterwards by the owner), **never against Project 2 or any backlog issue**. The probe must be written so that an unexpected success is harmless: the write targets only a field of the disposable resource, the attempt and its outcome are recorded verbatim, and a success means the candidate **fails** qualification (`denial_tested` stays false, the candidate is disqualified like B) rather than being retried elsewhere. Owner authorization of the disposable resource is a prerequisite recorded before the probe; without it the Project-write denial stays untested and `bounded` stays false.
4. List the resources the token can see and confirm one repository and one Project (`resource_scope_verified`).
5. Only then may a reviewed change let the probe report `bounded`.

The credential is provided through T3 `request_secret` (`delivery: "file"`) and exported as `GH_TOKEN` for the command only; it never enters policy, state, logs or chat. No credential was requested and no denial probe of any kind was run in remediation pass 1 or its repair pass 1; the only identity observed is the operator's broad token, whose `viewerCanUpdate: true` on Project 2 is the reason B cannot be considered read-only.

## T3: what the tools support, what is implemented, what is not qualified

| Need | Tool support (inspected metadata) | This foundation |
| --- | --- | --- |
| Explicit implementer and reviewer targets with effort | `orchestrator_capabilities` lists `claude-fable-5-1` `effort` and `gpt-6-astra` `reasoningEffort` values incl. `high`; this task's receipt shows the inherited target (`evidence/t3-task-receipt-2026-11-06.json`) | receipt validation implemented; a false receipt is not detectable |
| Admission and capacity before the task starts | `delegate_task` returns a task id; nothing prevents the coordinator from authorizing first | implemented as `reserve` / `authorize-review` / `authorize-repair` (durable authorization counted before launch, under the lock) then `bind-receipt` (consumes it); a launch itself is invisible to the tool; not exercised with a real task |
| Isolated worktree, identity and resume | `delegate_task` `isolation: "worktree"`; `t3_worktree_status` reports path/branch | recorded at bind; re-read at every evidence gate and before resume effects |
| Terminal task evidence before releasing ownership | `task_status` reports `workState` (`working`, `waiting_for_children`, `result_available`) and the final summary; `task_cancel` stops running and queued turns and delegates and, per the coordinator's inspection of the tool metadata, reports `cancel_requested` or a terminal state | implemented as `{taskId, status}` evidence matching exactly the active task (id and role) for `record-head`, `record-review`, `record-task-terminal`, `cancel`, `block`; `cancel_requested` is not terminal; ownership survives HEAD recording, evidence invalidation, run cancellation and the wall-clock expiry (a receipt for an authorization issued before the stop binds for cleanup only and the task stays owned until its evidence); a task id binds once per run across stories and roles; not exercised with a real task |
| Hard deadline or resource bound on a child | **not available**: `timeoutMs` applies to `mode: wait` only and "does not cancel the child"; no resource options | unmet; the tool's `max_wall_clock_minutes` is a local expiry of what it authorizes and advances, not a bound on a child; smallest upstream change: a child deadline that cancels or an equivalent bound |
| Credential confinement of a child | **not established**: the child runs with the coordinator's credentials and a runtime mode at most the parent's | unmet |
| No schedules or competing runners | `list_scheduled_tasks` returned none; `.bmad-loop/` holds only the untouched policy | observed |

Consequence: every state command refuses the real transport (`live-execution-disabled`); fixture-born state cannot be reopened with it (`environment-mismatch`). The protocol above is implemented and fixture-covered but has not been qualified with an actual bounded worker, and no such qualification launch happened in this work or in remediation pass 1. No credential was created or requested in remediation pass 1 or its repair pass 1; the existing broad token proves basic access only and cannot prove restricted permissions. No denial probe was run against live resources, and none may ever target the live Project (see the qualification steps above).

## Filesystem and containers

| Need | Scope |
| --- | --- |
| Read the repository checkout; write `.unattended-runs/` (state, `.lock`) | Repository root of the coordinator checkout (gitignored). |
| Implementer worktrees | `~/.t3/worktrees/<project>/…` created by T3; the tool records and re-checks path/branch, HEAD and cleanliness. |
| Deterministic checks (`./gradlew build`, `scripts/verify-quality-gates.sh`, unit suite) | A JDK to launch the wrapper and a reachable Docker-compatible runtime (`docker version` probe). |
| Nothing else | No home-directory, credential-store or system configuration access. |

## Budgets and stopping conditions (policy)

`max_stories_per_run = 1`, `max_concurrent_implementers = 1` (fixed), `max_repair_rounds = 2` (ceiling), `max_delegated_tasks = 6`, `max_wall_clock_minutes = 240`; empty allowlist by default; E17/E19 excluded. Any refusal, transport error, blocked or conflicted story or exhausted budget stops the state machine from admitting or advancing further work (past the wall clock: no authorization returned or issued, no advancing operation, receipts bind for cleanup only); it cannot terminate a running T3 task, and ownership of a running task is kept until terminal evidence arrives.
