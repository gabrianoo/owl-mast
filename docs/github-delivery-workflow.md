# GitHub delivery workflow

GitHub is the single source of truth for supervised delivery. `bmad-build`, `bmad-review` and `bmad-walkthrough` keep running their own steps unchanged; the team overrides in `_bmad/custom/` only move their state from repository files to GitHub and chain them through fresh T3 threads.

Every skill reads this document as a persistent fact. Where it conflicts with a skill step about *where* state lives, this document wins. Everything else (planning, implementation, internal review layers, triage, walkthrough steps) stays as the skill defines it.

## Where state lives

| State | Lives in | Writer |
|---|---|---|
| Ticket status | [Project](https://github.com/users/gabrianoo/projects/2) `Status` field | the skill that owns the transition (below) |
| Story spec (the old `spec-*.md` with its frontmatter: `status`, `route`, `baseline_commit`, `review_loop_iteration`, …) | one comment on the story issue marked `<!-- bmad:spec key=<spec file stem> -->`, edited in place | `bmad-build` |
| Fix-round spec ("Resolve the bmad-review findings on PR #M") | one comment on the PR, same marker | `bmad-build` |
| Review round and verdict | one marked PR review per round, body `<!-- bmad:review round=N verdict=clean\|changes -->`, anchored to the reviewed commit. File-level findings are extra single-comment reviews without the marker; they do not count as rounds | `bmad-review` |
| Review findings | one PR review thread per finding, first comment marked `<!-- bmad:finding id=RN-K -->` | `bmad-review` opens and resolves; `bmad-build` replies |
| Ticket claim | a short-lived comment on the issue marked `<!-- bmad:claim token=… -->`, removed when the claim settles | `bmad-build`, on pickup |
| Deferred work | a GitHub issue labelled `deferred-work`, linking its source issue/PR | whichever skill defers |
| Code | the PR branch | `bmad-build` |

Local copies are disposable. `implementation_artifacts` points at the git-ignored `.bmad-work/` (see `_bmad/custom/config.toml`), so specs, `deferred-work.md`, epic-context caches and staged diffs never enter a commit or a merge. Before acting on a spec, hydrate it from GitHub; after every change to a spec's frontmatter or body, publish it back. Never commit anything under `.bmad-work/` and never recreate specs under `_bmad-output/implementation-artifacts/`. The files already committed there are historical evidence; leave them alone.

## The helper

All GitHub writes go through one tested helper, run from the repository root (requires an authenticated `gh`):

```sh
H="python3 -m automation.github_delivery"
$H ready                                              # Ready issues in pickup order (Priority, then Stable ID)
$H status <issue> "In progress" --expect Ready --claim  # move Status; --expect refuses if it already moved, --claim (needs --expect) serializes rival pickups
$H spec-pull <issue|pr> [--key K] --out .bmad-work/<K>.md
$H spec-push <issue|pr> --file .bmad-work/<K>.md      # create or edit the spec comment in place
$H spec-list <issue|pr>
$H review-state <pr>                                  # head_sha, base, rounds (each with its commit), last_round_at_head, next_round, open_findings, other_unresolved_threads
$H post-review <pr> --round N --commit <reviewed SHA> --verdict changes --summary-file S --findings-file F.json
$H reply <thread-id> --body-file B
$H resolve <thread-id>...
```

The findings file is a JSON array of `{"id": "R2-3", "path": "src/x.py", "line": 41, "body": "…"}`. Every finding becomes one resolvable thread. A finding on a line of the reviewed diff is an inline comment of the round's review. GitHub's create-review endpoint takes no file-level comments, so a finding outside the diff hunks, or on a file the PR does not change, is posted as its own file-level comment (`POST pulls/{n}/comments` with `subject_type: file`) before the review, and the review body lists those ids.

`--commit` is the full SHA that was reviewed: the `head_sha` that `review-state` reported when the diff was staged. The round is anchored to that commit and to GitHub's diff for it, not to whatever the head is at posting time. If the head moved since, the round is still posted against the reviewed commit and its body says so; a commit that is no longer in the head's history, or is not ahead of the base branch, is refused, and so is a PR that is not open or whose diff has 300 or more files (GitHub truncates it). `review-state` reports each round's commit and `last_round_at_head`: a clean round covers the head only when that is true.

`post-review` posts the file-level comments first and the review, which carries the round marker, last. If it fails part-way, run the same command again: file-level findings that already have a thread are skipped, and the round counts only once the review is up. If the response to the review itself was lost, the rerun is refused with "Round N is already posted": the round went through, so do not post it again under the next number. If the review can never be posted (GitHub keeps rejecting it), the file-level threads already up stay open without a round: reply on them with the reason and resolve them by hand.

If the helper exits 2, report its message and stop; never work around a refusal with raw `gh` writes.

### Claims and their limit

GitHub has no compare-and-set for a Project field, so `--expect` alone reads the Status and writes it in two calls, and two runs could both pass. `--claim` narrows that: the run posts a claim marker comment on the issue, backs off if an earlier marker is there, reads the Status once more, writes it, and removes its marker. Of two rival runs the one with the later marker refuses (exit 2) and removes its marker; a run that arrives after the winner finished is refused by the second Status read.

What remains: GitHub may serve a stale comment list or Status for a moment after a write, so two runs started within about a second of each other can, rarely, both claim. The loop is supervised by one operator, and a double claim shows up as two branches or PRs for one issue; close the later one. A run that dies between posting and removing its marker leaves it behind: other runs ignore a marker older than 15 minutes, and anyone may delete it by hand. Only the Ready → In progress pickup uses `--claim`, and `--claim` refuses an `--expect` list that holds the target status. Nothing serializes two threads launched for the same stage of the same PR: two fix rounds would both pass the fix-round guard, and two review threads could both post the same round number. The loop launches exactly one thread per stage; do not start a second by hand while one is running.

## Status transitions

```text
Ready ──bmad-build──▶ In progress ──bmad-review──▶ In review ──bmad-walkthrough (Approve + merge)──▶ Done
                          ▲                             │
                          └──── bmad-build (fix round) ◀┘   any skill ──▶ Blocked (cap reached or escalation)
```

| Transition | Who | Command |
|---|---|---|
| Ready → In progress | `bmad-build`, on pickup | `status N "In progress" --expect Ready --claim` |
| In review → In progress | `bmad-build`, fix round | `status N "In progress" --expect "In review" --expect "In progress"` |
| In progress → In review | `bmad-review`, before reviewing | `status N "In review" --expect "In progress" --expect "In review"` |
| In review → Done | `bmad-walkthrough`, after the merge | `status N Done --expect "In review"` |
| any → Blocked | the skill that stops | `status N Blocked`, plus an issue comment naming the missing decision or evidence |

Each transition between Ready, In progress, In review and Done has one writer. A review that asks for changes, whether a `bmad-review` round or a walkthrough **Rework**, leaves the ticket In review; only the fix round moves it back to In progress. The fix round also accepts In progress, so a fix round that was interrupted after moving the ticket can start again.

These are the agent-written transitions the owner authorized for this supervised loop. The [tracking rules](engineering-tracking.md#tracking-rules) still define what each status means. The unattended ENG-01 tool is unaffected and stays off.

## The loop

One issue, one branch (`t3/<spec-slug>`), one PR that closes the issue. Each stage runs in a **new top-level T3 thread** (`t3_thread_launch`, no `projectId` so it inherits this project, `workspaceStrategy: {"type": "existing_worktree", "worktreePath": "<current worktree>"}` when the current checkout is a worktree, otherwise `{"type": "root"}`), titled `<Stable ID> · <stage>`. The launching thread then ends. If `t3_thread_launch` is unavailable (for example in Codex), print the exact next prompt below and stop.

| Stage | Prompt of the new thread |
|---|---|
| review | `skill:bmad-review GitHub delivery: issue #N, PR #M, round R. Follow docs/github-delivery-workflow.md.` |
| fix | `/bmad-build GitHub delivery fix round: issue #N, PR #M, after review round R. Resolve the open bmad-review threads. Follow docs/github-delivery-workflow.md.` |
| walkthrough | `/bmad-walkthrough GitHub delivery: issue #N, PR #M. Follow docs/github-delivery-workflow.md.` |

### 1. bmad-build

1. **Pick the ticket.** Use the issue the user named; otherwise take the first entry of `$H ready` whose issue body lists no open blocker. Claim it with `status N "In progress" --expect Ready --claim` and `gh issue edit N --add-assignee @me`. A refusal means someone else took it or is taking it: pick the next one. See [Claims and their limit](#claims-and-their-limit). The exception is a pickup of your own that was interrupted: when the issue is already In progress, assigned to you, and its branch `t3/<spec-slug>` exists, resume it without claiming again.
2. **Hydrate.** `spec-list N`. If a story spec exists, `spec-pull` it to `.bmad-work/` and hand that path to step 1 of the build as the explicit argument, so Build resumes from its frontmatter `status`. Otherwise the issue body (acceptance criteria, tasks, links to the repository specification) is the starting intent; slug the spec with the Stable ID (`spec-om-01-05-…`). For epic continuity, `spec-pull` the spec of the previous Done story in the same epic instead of scanning local files.
3. **Branch.** From a clean `main`, `git switch -c t3/<spec-slug> origin/main` (fetch first) unless already on the issue's branch.
4. **Run Build as written.** After every change to the spec (creation, approval, status change, triage log, change log, review loop increment), `spec-push N --file <spec>`.
5. **Finish** (Build's on-complete): push the branch, open the PR if none exists (`gh pr create --base main`, conventional title, body with the intent summary, verification result and `Closes #N`), publish the final spec, file new `deferred-work.md` entries as `deferred-work` issues and empty that file, then launch the **review** thread with `R = next_round` from `review-state`.

**Fix round** (prompt names a PR): `review-state M`. Move Status back with `status N "In progress" --expect "In review" --expect "In progress"`, check out the PR head branch, and run Build with the open bmad findings (each with thread id, location and the full thread) as the intent; key the spec `spec-gh-<M>-review-round-<R>` and publish it on the PR (if `spec-list M` already holds that key, `spec-pull` it and resume instead). Treat each thread as an addressable finding: fix it or decide it is wrong. On finishing, push, then reply on every open thread with `Fixed in <full SHA>: <one line>` or `Not changed: <evidence>`. Never resolve a thread yourself. Then launch the **review** thread for the next round.

### 2. bmad-review

1. `review-state M`. If `next_round` exceeds 6, set **Blocked** (below) and stop. Move Status with `status N "In review" --expect "In progress" --expect "In review"`.
2. The reviewed SHA and the diff base are `head_sha` and `base` from that `review-state` call; read them nowhere else. Stage GitHub's diff for them (`gh api -H "Accept: application/vnd.github.diff" repos/<owner>/<repo>/compare/<base>...<head_sha>`) as the content, and stop if it is truncated as the `bmad-review` standing rule defines (300 or more files, or a changed file without a patch), with the PR body plus the hydrated spec(s) as `claims`. Run the lenses exactly as the skill defines.
3. **Settle earlier threads.** For each open bmad finding, read Build's reply and the current code. Fixed, or the rebuttal holds → `resolve` it. Not settled → `reply` with what is still wrong and leave it open.
4. **Triage new findings** with Build's verdict rules (`high`/`medium`/`low`/`false`/`maybe-false`): verify each claim at its location; drop `false`; drop `low` unless the fix is a direct correction or deletion; drop anything already raised in an open or resolved thread; pre-existing problems this PR did not cause become `deferred-work` issues, not threads. The adversarial lens's finding floor is an input, not a quota: only verified, actionable findings are posted.
5. **Post the round.** `post-review M --round R --commit <reviewed SHA>`, with `--verdict changes` and the surviving findings (ids `R<R>-1`, `R<R>-2`, …), or `--verdict clean` when nothing survives. Write the summary to `.bmad-work/review-M-round-R.md` and the findings array to `.bmad-work/review-M-round-R.json` and pass them as `--summary-file` and `--findings-file`. The summary lists the lenses run, threads resolved this round, findings posted, findings dropped by reason and any deferred issues.
6. **Route.**
   - `clean` **and** `review-state` shows no open bmad finding and `last_round_at_head` true → launch the **walkthrough** thread.
   - `clean` but the head moved after the reviewed commit (`last_round_at_head` false) → the round does not cover the head: if `R < 6`, launch a new **review** thread for round `R + 1`.
   - Otherwise, if `R < 6` → launch the **fix** thread.
   - Otherwise (round 6 not clean) → **Blocked**: `status N Blocked` and a PR comment listing the open threads and the decision needed. No new thread.

### 3. bmad-walkthrough

1. Treat PR #M as the explicit change. `spec-pull` the story spec from issue #N into `.bmad-work/` so orientation finds the intent and any `Suggested Review Order`.
2. Run the walkthrough steps as written, including the Approve / Rework / Discuss decision; the human makes that call.
3. **Approve** is the authorization to merge. First confirm: `review-state M` shows the last round `clean` with `last_round_at_head` true (the clean round reviewed the commit that is about to merge), no open bmad finding and no other unresolved thread; `gh pr checks M` is all green; the PR is mergeable and not a draft. Any gap → report it and stop, Status unchanged. Then `gh pr merge M --merge --delete-branch`, `status N Done --expect "In review"`, and close issue #N with a comment linking the merge commit if GitHub did not close it.
4. **Rework** → post the human's feedback with `post-review M --round <next_round> --commit <head_sha> --verdict changes --summary-file S --findings-file F.json`, where `<head_sha>` is the head the walkthrough showed. Each point of feedback is one finding (`{"id": "R<round>-K", "path", "line", "body"}`) at the code it is about; feedback about no particular line names the most relevant changed file without a line. The summary says the round is the human's walkthrough feedback. It counts as a round; with no round left, set **Blocked** instead. Then offer to launch the **fix** thread. Leave the Status at In review: the fix round moves it to In progress when it starts, exactly as after a `bmad-review` round that asked for changes. **Discuss** changes nothing.

## Round limit

A round is one posted `bmad-review` review. At most six rounds run per PR. A round-6 review that is not clean blocks the ticket for the owner. Build's internal `review_loop_iteration` cap is separate and unchanged; it lives in the spec comment like the rest of the frontmatter.
