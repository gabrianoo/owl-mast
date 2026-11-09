# GitHub delivery workflow

GitHub is the single source of truth for supervised delivery. `bmad-build`, `bmad-review` and `bmad-walkthrough` keep running their own steps unchanged; the team overrides in `_bmad/custom/` only move their state from repository files to GitHub and chain them through fresh T3 threads.

Every skill reads this document as a persistent fact. Where it conflicts with a skill step about *where* state lives, this document wins. Everything else (planning, implementation, internal review layers, triage, walkthrough steps) stays as the skill defines it.

## Where state lives

| State | Lives in | Writer |
|---|---|---|
| Ticket status | [Project](https://github.com/users/gabrianoo/projects/2) `Status` field | the skill that owns the transition (below) |
| Story spec (the old `spec-*.md` with its frontmatter: `status`, `route`, `baseline_commit`, `review_loop_iteration`, …) | one comment on the story issue marked `<!-- bmad:spec key=<spec file stem> -->`, edited in place | `bmad-build` |
| Fix-round spec ("Resolve the bmad-review findings on PR #M") | one comment on the PR, same marker | `bmad-build` |
| Review round and verdict | one PR review per round, body marked `<!-- bmad:review round=N verdict=clean\|changes -->` | `bmad-review` |
| Review findings | one PR review thread per finding, first comment marked `<!-- bmad:finding id=RN-K -->` | `bmad-review` opens and resolves; `bmad-build` replies |
| Deferred work | a GitHub issue labelled `deferred-work`, linking its source issue/PR | whichever skill defers |
| Code | the PR branch | `bmad-build` |

Local copies are disposable. `implementation_artifacts` points at the git-ignored `.bmad-work/` (see `_bmad/custom/config.toml`), so specs, `deferred-work.md`, epic-context caches and staged diffs never enter a commit or a merge. Before acting on a spec, hydrate it from GitHub; after every change to a spec's frontmatter or body, publish it back. Never commit anything under `.bmad-work/` and never recreate specs under `_bmad-output/implementation-artifacts/`. The files already committed there are historical evidence; leave them alone.

## The helper

All GitHub writes go through one tested helper, run from the repository root (requires an authenticated `gh`):

```sh
H="python3 -m automation.github_delivery"
$H ready                                              # Ready issues in pickup order (Priority, then Stable ID)
$H status <issue> "In progress" --expect Ready        # move Status; --expect refuses if someone else moved it
$H spec-pull <issue|pr> [--key K] --out .bmad-work/<K>.md
$H spec-push <issue|pr> --file .bmad-work/<K>.md      # create or edit the spec comment in place
$H spec-list <issue|pr>
$H review-state <pr>                                  # rounds_done, next_round, open_findings, other_unresolved_threads
$H post-review <pr> --round N --verdict changes --summary-file S --findings-file F.json
$H reply <thread-id> --body-file B
$H resolve <thread-id>...
```

The findings file is a JSON array of `{"id": "R2-3", "path": "src/x.py", "line": 41, "body": "…"}`. A finding outside the diff hunks becomes a file-level thread, so every finding is resolvable. If the helper exits 2, report its message and stop; never work around a refusal with raw `gh` writes.

## Status transitions

```text
Ready ──bmad-build──▶ In progress ──bmad-review──▶ In review ──bmad-walkthrough (Approve + merge)──▶ Done
                          ▲                             │
                          └──── bmad-build (fix round) ◀┘   any skill ──▶ Blocked (cap reached or escalation)
```

| Transition | Who | Command |
|---|---|---|
| Ready → In progress | `bmad-build`, on pickup | `status N "In progress" --expect Ready` |
| In review → In progress | `bmad-build`, fix round | `status N "In progress" --expect "In review"` |
| In progress → In review | `bmad-review`, before reviewing | `status N "In review" --expect "In progress" --expect "In review"` |
| In review → Done | `bmad-walkthrough`, after the merge | `status N Done --expect "In review"` |
| any → Blocked | the skill that stops | `status N Blocked`, plus an issue comment naming the missing decision or evidence |

These are the agent-written transitions the owner authorized for this supervised loop. The [tracking rules](engineering-tracking.md#tracking-rules) still define what each status means. The unattended ENG-01 tool is unaffected and stays off.

## The loop

One issue, one branch (`t3/<spec-slug>`), one PR that closes the issue. Each stage runs in a **new top-level T3 thread** (`t3_thread_launch`, no `projectId` so it inherits this project, `workspaceStrategy: {"type": "existing_worktree", "worktreePath": "<current worktree>"}` when the current checkout is a worktree, otherwise `{"type": "root"}`), titled `<Stable ID> · <stage>`. The launching thread then ends. If `t3_thread_launch` is unavailable (for example in Codex), print the exact next prompt below and stop.

| Stage | Prompt of the new thread |
|---|---|
| review | `skill:bmad-review GitHub delivery: issue #N, PR #M, round R. Follow docs/github-delivery-workflow.md.` |
| fix | `/bmad-build GitHub delivery fix round: issue #N, PR #M, after review round R. Resolve the open bmad-review threads. Follow docs/github-delivery-workflow.md.` |
| walkthrough | `/bmad-walkthrough GitHub delivery: issue #N, PR #M. Follow docs/github-delivery-workflow.md.` |

### 1. bmad-build

1. **Pick the ticket.** Use the issue the user named; otherwise take the first entry of `$H ready` whose issue body lists no open blocker. Claim it with `status N "In progress" --expect Ready` and `gh issue edit N --add-assignee @me`. A refusal means someone else took it: pick the next one.
2. **Hydrate.** `spec-list N`. If a story spec exists, `spec-pull` it to `.bmad-work/` and hand that path to step 1 of the build as the explicit argument, so Build resumes from its frontmatter `status`. Otherwise the issue body (acceptance criteria, tasks, links to the repository specification) is the starting intent; slug the spec with the Stable ID (`spec-om-01-05-…`). For epic continuity, `spec-pull` the spec of the previous Done story in the same epic instead of scanning local files.
3. **Branch.** From a clean `main`, `git switch -c t3/<spec-slug> origin/main` (fetch first) unless already on the issue's branch.
4. **Run Build as written.** After every change to the spec (creation, approval, status change, triage log, change log, review loop increment), `spec-push N --file <spec>`.
5. **Finish** (Build's on-complete): push the branch, open the PR if none exists (`gh pr create --base main`, conventional title, body with the intent summary, verification result and `Closes #N`), publish the final spec, file new `deferred-work.md` entries as `deferred-work` issues and empty that file, then launch the **review** thread with `R = next_round` from `review-state`.

**Fix round** (prompt names a PR): `review-state M`. Move Status back with `status N "In progress" --expect "In review"`, check out the PR head branch, and run Build with the open bmad findings (each with thread id, location and the full thread) as the intent; key the spec `spec-gh-<M>-review-round-<R>` and publish it on the PR (if `spec-list M` already holds that key, `spec-pull` it and resume instead). Treat each thread as an addressable finding: fix it or decide it is wrong. On finishing, push, then reply on every open thread with `Fixed in <full SHA>: <one line>` or `Not changed: <evidence>`. Never resolve a thread yourself. Then launch the **review** thread for the next round.

### 2. bmad-review

1. `review-state M`. If `next_round` exceeds 6, set **Blocked** (below) and stop. Move Status with `status N "In review" --expect "In progress" --expect "In review"`.
2. Stage `gh pr diff M` as the content and the PR body plus the hydrated spec(s) as `claims`. Run the lenses exactly as the skill defines.
3. **Settle earlier threads.** For each open bmad finding, read Build's reply and the current code. Fixed, or the rebuttal holds → `resolve` it. Not settled → `reply` with what is still wrong and leave it open.
4. **Triage new findings** with Build's verdict rules (`high`/`medium`/`low`/`false`/`maybe-false`): verify each claim at its location; drop `false`; drop `low` unless the fix is a direct correction or deletion; drop anything already raised in an open or resolved thread; pre-existing problems this PR did not cause become `deferred-work` issues, not threads. The adversarial lens's finding floor is an input, not a quota: only verified, actionable findings are posted.
5. **Post the round.** `post-review M --round R`, with `--verdict changes` and the surviving findings (ids `R<R>-1`, `R<R>-2`, …), or `--verdict clean` when nothing survives. The summary lists the lenses run, threads resolved this round, findings posted, findings dropped by reason and any deferred issues.
6. **Route.**
   - `clean` **and** `review-state` shows no open bmad finding → launch the **walkthrough** thread.
   - Otherwise, if `R < 6` → launch the **fix** thread.
   - Otherwise (round 6 not clean) → **Blocked**: `status N Blocked` and a PR comment listing the open threads and the decision needed. No new thread.

### 3. bmad-walkthrough

1. Treat PR #M as the explicit change. `spec-pull` the story spec from issue #N into `.bmad-work/` so orientation finds the intent and any `Suggested Review Order`.
2. Run the walkthrough steps as written, including the Approve / Rework / Discuss decision; the human makes that call.
3. **Approve** is the authorization to merge. First confirm: `review-state M` shows the last round `clean`, no open bmad finding and no other unresolved thread; `gh pr checks M` is all green; the PR is mergeable and not a draft. Any gap → report it and stop, Status unchanged. Then `gh pr merge M --merge --delete-branch`, `status N Done --expect "In review"`, and close issue #N with a comment linking the merge commit if GitHub did not close it.
4. **Rework** → post the human's feedback with `post-review M --round <next_round> --verdict changes` (it counts as a round; with no round left, set **Blocked** instead), `status N "In progress" --expect "In review"`, and offer to launch the **fix** thread. **Discuss** changes nothing.

## Round limit

A round is one posted `bmad-review` review. At most six rounds run per PR. A round-6 review that is not clean blocks the ticket for the owner. Build's internal `review_loop_iteration` cap is separate and unchanged; it lives in the spec comment like the rest of the frontmatter.
