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
- First pass (35 PR comments, 2026-11-09): rewrote `on_complete` in `_bmad/custom/bmad-review.toml` and `_bmad/custom/bmad-code-review.toml` as one sequence (identify PR, check for an earlier post, collect, anchor, format, body, post, verify, report) behind one PR detection rule. Added:
  - owner, repo, and number from the PR URL; the reviewed SHA must be on the PR;
  - a duplicate-post check by heading; LEFT-side anchors for removed lines; anchors validated against the diff at the reviewed SHA;
  - a 422 fallback that moves unanchorable comments to the body; a paginated comment count with a follow-up review on mismatch;
  - zero-finding and no-story-file body rules; a credential placeholder rule; rejected `decision-needed` findings kept out of the inline comments (second pass: into a collapsed Rejected appendix in the body);
  - a "fixing SHA replied after push" clause, dropped in the second pass because `on_complete` is the skill's terminal instruction.
- First pass, bmad-review: dropped the `output_format = "markdown"` override (default `both` stays for non-PR content); the PR-only Markdown behavior lives in `output_preferences`.
- First pass, spec OM-01.01: links relabeled by reviewed SHA (`review of d1d1ce25`, `review of b4024d55`), the wrong "(round 1)" label removed from the Triage Log, serial comma added, blob SHAs of the five deleted review files recorded.
- Second pass (Blind Hunter, 14 findings): see the Review Triage Log.
- Third pass (round-2 review 5827386006 at b44d90c: 4 reopened threads and 32 new findings):
  - commands spell out `<owner>/<repo>/<number>` with a rule to fill them from the PR URL and never leave gh's `{owner}`/`{repo}` placeholders;
  - the reviewed SHA is checked with the compare endpoint (`identical` or `ahead`), not the 250-commit `pulls/<n>/commits` list, and both files behave the same when it is missing: tell the user to push, skip posting;
  - anchors are checked against GitHub's own diff (`compare/<base>...<sha>` with the diff media type), not a local fetch;
  - the comment count is `--jq '.[].id' | wc -l`, because gh 2.103.3 rejects `--slurp` with `--jq` (the first-pass triage entry recorded that combination as confirmed without running it; corrected below);
  - a rerun on the same SHA posts under a `rerun` heading instead of being suppressed; headings are given as literals;
  - the SHA capture is a standing rule (`activation_steps_prepend` in bmad-review, before staging; `activation_steps_append` in bmad-code-review) and covers PR-by-reference sources; bmad-code-review posts before the section 7 menu via an `activation_steps_append` entry; its `headRefOid` equality gate is replaced by the part A check;
  - `--base` added to the PR lookup; a bare commit range is never posted; posting and report trimming are skipped when another skill invoked bmad-review;
  - override steps lettered A to I so they are not confused with the skills' own step numbers; part F is the complete body list; prose fixes throughout.
  - Spec OM-01.01: one "Archived review files" note, chronological Triage Log, `b4024d55` throughout.

## Review Triage Log

- Blind Hunter (14 findings): patched 13, documented 1 without changing it (first entry).
- Dropping `output_format = "markdown"` re-enables the JSON block for non-PR content — low; this is what inline comment 4513475098 asked for (the owner request was PR-scoped). Documented in the TOML comment; not changed.
- Reviewed SHA undefined when HEAD moves between staging and posting — medium, confirmed (neither skill records it). Patched: `activation_steps_append` entry in both overrides records the SHA at staging time.
- `git diff <merge-base>...` names no base — medium, confirmed. Patched: `git fetch origin` then `git diff origin/<baseRefName>...<reviewed-sha>`.
- bmad-code-review silent on commit SHA, range, baseline_commit, and slug-derived branch sources — medium, confirmed against step-01. Patched: post when the source is a PR, branch, or range whose reviewed SHA equals the PR `headRefOid`; everything else never posts.
- headRefOid guard only on the branch-diff source — medium, confirmed. Patched by the same rule; user told to push when the SHA is local only.
- "Reply after push" has no place to run (on_complete is the terminal instruction) — medium, confirmed. Patched: clause dropped; status is a snapshot of the run and a later round records the push.
- `gh api -f` cannot send a comments array; `--paginate --jq length` prints per page — medium, confirmed. Patched with `--input <file>`. The count was first written as `--paginate --slurp --jq 'map(length) | add'` without running it; the round-2 reviewer ran it on gh 2.103.3 and it prints `the --slurp option is not supported with --jq or --template`. Replaced in the third pass with `gh api --paginate .../comments --jq '.[].id' | wc -l`, which printed 35 for review 5826826542.
- "exactly one open PR" contradicts "spans several PRs" — medium, confirmed. Patched: several PRs only when passed explicitly; leftover findings go in the first PR's body; `gh pr view <url-or-number>` named as the owner/repo source. Fork PRs (`owner:branch`) not handled; rare, left out.
- Heading SHA length unspecified and follow-up review could match the dedupe check — low, confirmed. Patched: full 40-character SHA, distinct `follow-up` heading.
- No credential rule in bmad-code-review — medium, confirmed. Patched: same placeholder rule.
- Rejected findings dropped from the GitHub record — low, confirmed. Patched: Rejected appendix in a collapsed `<details>` block in the body, never inline.
- Owner-decision comment only in bmad-review.toml — low, confirmed. Patched: same comment in bmad-code-review.toml.
- Blob IDs given without path, deleting commit, or `git show` hint; SHA abbreviation inconsistent — low, confirmed. Patched: path, commit c988f50, `git show <blob>`, 8-character `d1d1ce25` and `b4024d55` throughout.
- Triage Log entries reverse-chronological with a dangling "the repaired head" reference — low, confirmed. Patched: entries labeled first/second review with dates (third pass: put in chronological order).
