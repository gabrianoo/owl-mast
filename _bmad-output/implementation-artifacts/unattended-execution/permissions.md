# ENG-01 permissions: minimum, observed, policy versus enforcement

## GitHub

| Need | Minimum | Observed on 2026-11-06 (`check-permissions`) |
| --- | --- | --- |
| Read issues, bodies, comments, sub-issue parents | `repo` (classic) or Issues: read, Metadata: read | present |
| Post marker comments | `repo` or Issues: write | present |
| Read Project 2 items and fields; write Status | `project` (classic; user projects need it) or Projects: read/write | present, `viewerCanUpdate: true` |
| Read PR head, reviews, status rollup | `repo` or Pull requests: read | present |
| Push implementation branches, open PRs (implementer, not this tool) | `repo` push on the repository | `permissions.push: true` |
| Excess, unused by the tool | — | `workflow`, `gist`, `admin:public_key` (`read:org` is harmless) |

The existing coordinator token is a full-access user OAuth token. It satisfies the minimum but does not demonstrate a bounded credential. The tool **implements** the write policy (which fields, which values, which issues); it **cannot enforce** the credential boundary. A bounded unattended run needs a fine-grained token limited to this repository with the permissions above, provided through T3 `request_secret` (`delivery: "file"`) and exported as `GH_TOKEN` for the coordinator's commands only. Never store it in policy, state, logs or chat; the policy loader refuses secret-like keys and values and probe output redacts token-shaped strings.

Never granted and never used: merge, release, deployment, repository administration, workflow dispatch, organization scopes, live collection credentials.

## T3

| Need | Evidence |
| --- | --- |
| Explicit implementer target `claudeAgent` / `claude-fable-5-1` / `effort=high` | `orchestrator_capabilities` lists the model with `effort` values including `high`; this task's own receipt shows the inherited target (`evidence/t3-task-receipt-2026-11-06.json`). |
| Explicit reviewer target `codex` / `gpt-6-astra` / `reasoningEffort=high` | Listed with `reasoningEffort` values including `high`; `canRunCrossProviderChildTask: true`. |
| Isolated worktree per implementer, identity and resume | `delegate_task` `isolation: "worktree"`; `t3_worktree_status` reports path and branch, which `claim` records and `resume` re-checks. |
| Cancellation and polling | `task_cancel`, `task_status`; `features.cancellation: true`, `asyncPolling: true`. |
| No schedules or competing runners | `list_scheduled_tasks` returned none; `.bmad-loop/` holds only the untouched policy. |

Runtime mode: a delegated child runs at most at the parent's mode. The tool does not require `full-access`; it needs shell access to `gh`, `git` and the repository checkout. Narrower modes that pause for approval are compatible with supervised runs but defeat unattended operation; that trade-off is the owner's.

## Filesystem and containers

| Need | Scope |
| --- | --- |
| Read the repository checkout; write `.unattended-runs/<run-id>/` | Repository root of the coordinator checkout (gitignored). |
| Implementer worktrees | `~/.t3/worktrees/<project>/…` created by T3; the tool only records and re-checks path/branch. |
| Deterministic checks (`./gradlew build`, `scripts/verify-quality-gates.sh`, unit suite) | Need a JDK to launch the wrapper and a reachable Docker-compatible runtime (`docker version` probe). |
| Nothing else | No home-directory, credential-store or system configuration access. |

## Budgets and stopping conditions (policy)

`max_stories_per_run = 1`, `max_concurrent_implementers = 1` (fixed), `max_repair_rounds = 2` (ceiling), `max_delegated_tasks = 6`, `max_wall_clock_minutes = 240`; empty allowlist by default; E17/E19 excluded. Any refusal, transport error, blocked story or exhausted budget stops the run; nothing advances on failure.
