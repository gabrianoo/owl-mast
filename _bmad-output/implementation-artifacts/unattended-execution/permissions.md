# ENG-01 permissions: minimum, observed, blocker

## GitHub

| Need | Minimum | Observed on 2026-11-06 (`check-permissions`) |
| --- | --- | --- |
| Read issues, bodies, comments, sub-issue parents | `repo` (classic) or Issues: read, Metadata: read | present |
| Post marker comments | `repo` or Issues: write | present |
| Read Project 2 items and fields | `project` (classic; user projects need it) or Projects (user account): read | present |
| Read PR head, reviews, status rollup | `repo` or Pull requests: read | present |
| Push implementation branches, open PRs (implementer task, not this tool) | push on the repository | `permissions.push: true` |

Verdicts: `basic_access: true`, `bounded: false`, `unattended_activation_allowed: false`. Reasons: the identity has `admin` on the repository and carries excess scopes `admin:public_key`, `gist`, `read:org`, `workflow`. `denial_tested: false`. Full record: `evidence/check-permissions-2026-11-06.json`.

**Blocker (requirement 4).** A bounded identity is not available on this machine and was not requested. Exact minimum to provision when the owner decides to: a fine-grained personal access token restricted to `gabrianoo/owl-mast` with Issues read/write, Pull requests read, Contents read, Metadata read, plus the account permission Projects read/write for the user project; no admin, workflow, gist, key or organization permissions. Test plan before activation: run `check-permissions` with it (expect `basic_access` true; `bounded` stays false for fine-grained tokens because GitHub exposes no scope header, so the operator attaches the token's permission screen as evidence); run `probe-write --issue 106` (comment succeeds); attempt a forbidden read-only operation it must not have (for example `gh api repos/gabrianoo/owl-mast/actions/secrets`, expected 403) and record the denial. The token is provided through T3 `request_secret` (`delivery: "file"`) and exported as `GH_TOKEN` for the command only; it never enters policy, state, logs or chat.

The tool implements the write policy (comment-only, engineering issues for probes, product admission refused); it cannot enforce the credential boundary. Never granted and never used: merge, release, deployment, repository administration, workflow dispatch, organization scopes, live collection credentials.

## T3

| Need | Evidence | Enforceable by the tool? |
| --- | --- | --- |
| Explicit implementer target `claudeAgent` / `claude-fable-5-1` / `effort=high` | `orchestrator_capabilities` lists the option values; this task's own receipt shows the inherited target (`evidence/t3-task-receipt-2026-11-06.json`) | receipt validation only; a false receipt is not detectable |
| Explicit reviewer target `codex` / `gpt-6-astra` / `reasoningEffort=high` | listed; `canRunCrossProviderChildTask: true` | receipt validation only |
| Isolated worktree, identity and resume | `delegate_task` `isolation: "worktree"`; `t3_worktree_status` path/branch recorded at claim and re-checked before any resume effect | yes for the recorded path/branch |
| Admission before the delegated task starts | no hook or pre-start command in `delegate_task` | **no** |
| Cancellation acknowledged before ownership release | `task_cancel` returns no state the subprocess can observe; `task_status` is agent-only | **no** |
| Termination on budget expiry | `timeoutMs` applies to `mode: wait` only and does not cancel the child; no deadline option | **no** |
| No schedules or competing runners | `list_scheduled_tasks` returned none; `.bmad-loop/` holds only the untouched policy | observed |

Consequence: live product admission is refused in code (`live-execution-disabled`). Smallest upstream changes: `delegate_task` admission hook/pre-start command; acknowledged terminal cancel state exposed via `task_status`; child deadline that cancels; a subprocess-callable path to `task_status`/`task_cancel`.

## Filesystem and containers

| Need | Scope |
| --- | --- |
| Read the repository checkout; write `.unattended-runs/` (state, `.lock`) | Repository root of the coordinator checkout (gitignored). |
| Implementer worktrees | `~/.t3/worktrees/<project>/…` created by T3; the tool records and re-checks path/branch and requires a clean tree at the exact HEAD for checks. |
| Deterministic checks (`./gradlew build`, `scripts/verify-quality-gates.sh`, unit suite) | A JDK to launch the wrapper and a reachable Docker-compatible runtime (`docker version` probe). |
| Nothing else | No home-directory, credential-store or system configuration access. |

## Budgets and stopping conditions (policy)

`max_stories_per_run = 1`, `max_concurrent_implementers = 1` (fixed), `max_repair_rounds = 2` (ceiling), `max_delegated_tasks = 6`, `max_wall_clock_minutes = 240`; empty allowlist by default; E17/E19 excluded. Any refusal, transport error, blocked or conflicted story or exhausted budget stops the run; nothing advances on failure. Budgets stop the state machine from admitting further work; they cannot terminate a running T3 task (see above).
