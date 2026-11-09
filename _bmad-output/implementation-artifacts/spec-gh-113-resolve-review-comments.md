---
title: 'Resolve the bmad-review findings on PR #113'
type: 'chore'
created: '2026-11-09'
status: 'done'
route: 'oneshot'
review_loop_iteration: 0
context: []
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** PR #113 (`t3/review-records-on-github`, head `baa4cb6`) carries a bmad-review with 35 inline findings on `_bmad/custom/bmad-review.toml`, `_bmad/custom/bmad-code-review.toml` and the OM-01.01 spec. They are unresolved, and the two `on_complete` instructions they target will govern every later PR review.

**Approach:** Work through the 35 comments one by one on the PR branch. Apply each finding that improves the instructions or the spec; where a finding conflicts with a decision the owner has already made (post PR reviews unasked, as a COMMENT review), decline it with the reason. Reply to every inline thread on GitHub with what was done and resolve it. Push the result to the PR.

</frozen-after-approval>

## Implementation Notes

- Open for owner: whether to hold back unfixed security findings on the public repository.
- Declined as owner decisions (recorded in the TOML comments): a confirmation prompt before posting (the owner asked on 2026-11-09 for reviews to be posted unasked) and a cap or verification pass on the number of inline comments (the review is the record; the body states the findings are unverified).
- First pass (35 PR comments, 2026-11-09): rewrote `on_complete` in `_bmad/custom/bmad-review.toml` and `_bmad/custom/bmad-code-review.toml` as nine steps, now parts A to I (identify PR, check for an earlier post, collect, anchor, format, body, post, verify, report), preceded by one shared PR-detection rule. Added:
  - owner, repo, and number from the PR URL; the reviewed SHA must be on the PR;
  - a duplicate-post check by heading; LEFT-side anchors for removed lines; anchors validated against the diff at the reviewed SHA;
  - a 422 fallback that moves unanchorable comments to the body; a paginated comment count with a follow-up review on mismatch;
  - zero-finding and no-story-file body rules; a credential placeholder rule; rejected `decision-needed` findings kept out of the inline comments (second pass: moved into a collapsed Rejected appendix in the body);
  - a "fixing SHA replied after push" clause, dropped in the second pass because `on_complete` is the skill's terminal instruction.
- First pass, bmad-review: dropped the `output_format = "markdown"` override (default `both` stays for non-PR content); the PR-only Markdown behavior lives in `output_preferences`.
- First pass, spec OM-01.01: links relabeled by reviewed SHA (`review of d1d1ce25`, `review of b4024d55`), the wrong "(round 1)" label removed from the Triage Log, serial comma added, blob SHAs of the five deleted review files recorded.
- Second pass (Blind Hunter, 14 findings): recorded only in the Review Triage Log.
- Third pass (round-2 review 5827386006 at b44d90c: 4 reopened threads and 32 new findings); each outcome is in its GitHub thread reply, and the Triage Log gets no new rows (superseded entries are annotated):
  - commands spell out `<owner>/<repo>/<number>` with a rule to fill them from the PR URL and never leave gh's `{owner}`/`{repo}` placeholders;
  - the reviewed SHA is checked with the compare endpoint (`identical` or `ahead`), not the 250-commit `pulls/<n>/commits` list, and both files behave the same when it is missing: tell the user to push, skip posting;
  - anchors are checked against GitHub's own diff (`compare/<base>...<sha>` with the diff media type), not a local fetch;
  - the comment count is `--jq '.[].id' | wc -l` (see the `gh api -f` Triage Log entry);
  - a rerun on the same SHA posts under a `rerun` heading instead of being suppressed; headings are given as literals;
  - the SHA capture is a standing rule (`activation_steps_prepend` in bmad-review, before staging; `activation_steps_append` in bmad-code-review) and covers PR-by-reference sources; bmad-code-review posts before the section 7 menu via an `activation_steps_append` entry; its `headRefOid` equality gate is replaced by the part A check;
  - `--base` added to the PR lookup; a bare commit range is never posted; posting and report trimming are skipped when another skill invoked bmad-review;
  - override parts lettered A to I so they are not confused with the skills' own step numbers; part F is the complete body list; prose fixes throughout.
- Third pass, spec OM-01.01: one "Archived review files" note, chronological Triage Log, `b4024d55` throughout.
- Fourth pass (round-3 review 5827766651 at ea4562f: 1 reopened thread and 29 new findings); each outcome is in its GitHub thread reply:
  - a PR source is staged from GitHub's compare diff at `headRefOid` (read before staging), in both skills; a range named with a PR is staged as the range;
  - part A adds `compare/<base>...<sha> --jq .ahead_by` > 0 so base-branch commits no longer pass;
  - part H captures gh's exit status before counting and puts missing comments in the follow-up's body instead of reposting anchors;
  - part G records the review id, re-checks part B after a timeout or 5xx, and falls back to a body-only review when the 422 re-check changes nothing; part D says what to do when the compare diff cannot be fetched or is truncated;
  - part B is split into B1 to B3 and works without `/user`; part F gains slots for the earlier round's thread status, failed layers, and file groups, and names "the findings to fix first" as a deliberate exception to the no-ranking rule;
  - bmad-review excludes uncommitted content, handles lookup errors and several PRs explicitly; bmad-code-review takes a PR source from `gh pr view`, defines a run as one pass through step-04 so the terminal pass does not post twice, and records that a session abandoned at section 4 or 5 posts nothing;
  - the commands paragraph is split from the credential rule and says that bare numbers and branches resolve against the checkout, so the report prints the PR URL.
- Fourth pass, spec OM-01.01: blank lines removed so the Implementation Notes render as one list; the archived-files note stays where it is.
- Fifth pass (round-4 review 5828354337 at 1e8de4a: 3 reopened threads and 4 new findings); each outcome is in its GitHub thread reply:
  - a diff base is defined for PR sources: the base branch for an OPEN PR, the merge commit's first parent for a MERGED PR (verified on #112: `main...head` gives 0 files, `<mergeCommit>^1...head` gives 100); staging, part A, and part D all use it, and a merged PR is never told to push;
  - a staging fetch that fails or is truncated stops the run; truncation is defined as 300 or more files in the JSON compare, and a file with changes but no `patch` is unpatched, so its findings go in the body;
  - in a range review, removed-line findings go in the body because LEFT numbers refer to the range start;
  - part H fetches `path:line` pairs, counts them with `printf '%s' | grep -c .` (0 for an empty list), and finds missing comments by multiset difference;
  - part G's timeout path looks for the exact heading this POST sent, accepts only a review not in the part B list, retries the lookup once after a wait, and never POSTs again blindly.
- Fifth pass, continued (the 20 further round-4 threads that a 100-thread page limit in my thread query had hidden); each outcome is in its GitHub thread reply:
  - a Headings paragraph defines the main, rerun, follow-up, and continuation headings, with the file-group suffix on all of them in bmad-code-review, matched on the whole first line;
  - part F is a numbered list (F1 to F10, F1 to F13), B1 is dropped in favor of part G's timeout rule, and the ranking-exception reason moved to the owner-decision comment;
  - part G retries body-only on any second 422 and splits a body over 60,000 characters into continuation reviews;
  - bmad-review presents the full report for content with no reviewed SHA, and the PR lookup strips a remote prefix from the base;
  - bmad-code-review posts for a spec `baseline_commit` diff on a PR branch, filters the compare diff for file groups instead of rebuilding from HEAD, and refuses to apply patches when the checkout is not at the reviewed SHA.

## Review Triage Log

- Second pass, Blind Hunter (14 findings): patched 13; the next entry was documented, not changed.
- Dropping `output_format = "markdown"` re-enables the JSON block for non-PR content — low; this is what inline comment 4513475098 asked for (the owner request was PR-scoped). Documented in the TOML comment; not changed.
- Reviewed SHA undefined when HEAD moves between staging and posting — medium, confirmed (neither skill records it). Patched: `activation_steps_append` entry in both overrides records the SHA at staging time (third pass: a standing rule, `activation_steps_prepend` in bmad-review; fourth pass: a PR source records `headRefOid` read before staging).
- `git diff <merge-base>...` names no base — medium, confirmed. Patched: `git fetch origin` then `git diff origin/<baseRefName>...<reviewed-sha>` (third pass: replaced by GitHub's `compare/<base>...<sha>` diff).
- bmad-code-review silent on commit SHA, range, baseline_commit, and slug-derived branch sources — medium, confirmed against step-01. Patched: post when the source is a PR, branch, or range whose reviewed SHA equals the PR `headRefOid`; everything else never posts (third pass: the equality gate became the part A compare check; fourth pass: a PR source skips the branch lookup).
- headRefOid guard only on the branch-diff source — medium, confirmed. Patched by the same rule; user told to push when the SHA is local only (third pass: part A applies to every source).
- "Reply after push" has no place to run (on_complete is the terminal instruction) — medium, confirmed. Patched: clause dropped; status is a snapshot of the run and a later round records the push.
- `gh api -f` cannot send a comments array; `--paginate --jq length` prints per page — medium, confirmed. Patched with `--input <file>`. The count was first written as `--paginate --slurp --jq 'map(length) | add'` without running it; the round-2 reviewer ran it on gh 2.103.3 and it prints `the --slurp option is not supported with --jq or --template`. Replaced in the third pass with `gh api --paginate .../comments --jq '.[].id' | wc -l`, which printed 35 for review 5826826542.
- "exactly one open PR" contradicts "spans several PRs" — medium, confirmed. Patched: several PRs only when passed explicitly; leftover findings go in the first PR's body (fourth pass: one diff per PR, findings tagged, leftovers in the first PR whose post succeeds); `gh pr view <url-or-number>` named as the owner/repo source. Fork PRs (`owner:branch`) not handled; rare, left out.
- Heading SHA length unspecified and follow-up review could match the dedupe check — low, confirmed. Patched: full 40-character SHA, distinct `follow-up` heading.
- No credential rule in bmad-code-review — medium, confirmed. Patched: same placeholder rule.
- Rejected findings dropped from the GitHub record — low, confirmed. Patched: Rejected appendix in a collapsed `<details>` block in the body, never inline.
- Owner-decision comment only in bmad-review.toml — low, confirmed. Patched: same comment in bmad-code-review.toml.
- Blob IDs given without path, deleting commit, or `git show` hint; SHA abbreviation inconsistent — low, confirmed. Patched: path, commit c988f50, `git show <blob>`, 8-character `d1d1ce25` and `b4024d55` throughout.
- Triage Log entries reverse-chronological with a dangling "the repaired head" reference — low, confirmed. Patched: entries labeled first/second review with dates (third pass: put in chronological order).
