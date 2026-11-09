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

- 2026-11-09: Rewrote `on_complete` in `_bmad/custom/bmad-review.toml` and `_bmad/custom/bmad-code-review.toml` as the same nine-step sequence (identify PR, check for an earlier post, select, anchor, format, body, post, verify, report), preceded by the same PR detection (`gh pr list --head <branch> --state open`, exactly one result). Added: owner/repo/number from the PR URL; reviewed SHA must be a PR commit, else body-only; duplicate-post check by heading marker; LEFT-side anchors for removed lines; anchors validated against `git diff <merge-base>...<reviewed-sha>`; 422 fallback moving failing comments to the body; paginated comment count with a follow-up review on mismatch; zero-finding and no-story-file body rules; credential placeholder rule; rejected decision-needed findings not posted; fixing SHA replied after push.
- Dropped the `output_format = "markdown"` override in bmad-review (default `both` stays for non-PR callers); the PR-only markdown behaviour and the "plan line only before on_complete" precedence now live in `output_preferences`.
- Declined, as owner decisions recorded in the TOML comment: a confirmation prompt before posting (owner asked on 2026-11-09 for reviews to be posted unasked) and a cap or verification pass on the number of inline comments (the review is the record; the body states findings are unverified). Not applied: holding back unfixed security findings on the public repository; flagged to the owner.
- Spec OM-01.01: links relabelled by reviewed SHA (`review of d1d1ce2`, `review of b4024d5`), the wrong "(round 1)" label removed from the Triage Log, serial comma added, and the git blob SHAs of the five deleted review files recorded at `137e084` next to each archive link.

- Blind Hunter (14 findings): patched 13, documented 1. Details in the Review Triage Log.

## Review Triage Log

- Dropping `output_format = "markdown"` re-enables the JSON block for non-PR content — low; this is what inline comment 4513475098 asked for (the owner request was PR-scoped). Documented in the TOML comment; not changed.
- Reviewed SHA undefined when HEAD moves between staging and posting — medium, confirmed (neither skill records it). Patched: `activation_steps_append` entry in both overrides records the SHA at staging time.
- `git diff <merge-base>...` names no base — medium, confirmed. Patched: `git fetch origin` then `git diff origin/<baseRefName>...<reviewed-sha>`.
- bmad-code-review silent on commit SHA, range, baseline_commit, and slug-derived branch sources — medium, confirmed against step-01. Patched: post when the source is a PR, branch, or range whose reviewed SHA equals the PR `headRefOid`; everything else never posts.
- headRefOid guard only on the branch-diff source — medium, confirmed. Patched by the same rule; user told to push when the SHA is local only.
- "Reply after push" has no place to run (on_complete is the terminal instruction) — medium, confirmed. Patched: clause dropped; status is a snapshot of the run and a later round records the push.
- `gh api -f` cannot send a comments array; `--paginate --jq length` prints per page — medium, confirmed (gh 2.103.3 supports `--input` and `--slurp`). Patched with `--input <file>` and `--paginate --slurp --jq 'map(length) | add'`.
- "exactly one open PR" contradicts "spans several PRs" — medium, confirmed. Patched: several PRs only when passed explicitly; leftover findings go in the first PR's body; `gh pr view <url-or-number>` named as the owner/repo source. Fork PRs (`owner:branch`) not handled; rare, left out.
- Heading SHA length unspecified and follow-up review could match the dedupe check — low, confirmed. Patched: full 40-character SHA, distinct `follow-up` heading.
- No credential rule in bmad-code-review — medium, confirmed. Patched: same placeholder rule.
- Rejected findings dropped from the GitHub record — low, confirmed. Patched: Rejected appendix in a collapsed `<details>` block in the body, never inline.
- Owner-decision comment only in bmad-review.toml — low, confirmed. Patched: same comment in bmad-code-review.toml.
- Blob IDs given without path, deleting commit, or `git show` hint; SHA abbreviation inconsistent — low, confirmed. Patched: path, commit c988f50, `git show <blob>`, 8-character `d1d1ce25` throughout.
- Triage Log entries reverse-chronological with a dangling "the repaired head" reference — low, confirmed. Patched: entries labelled first/second review with dates; reference points at the entry above.
