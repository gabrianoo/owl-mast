# Spec: PR #115 recheck findings, round 4 (review 5842090200 at 35c8832)

Status: done

## Scope

Three of the four findings of the 2026-11-10 recheck review on `t3/pr107-review-findings` (ENG-01, PR #115), as handed over by the owner. The fourth (legacy `reserved` story without `race_settled`, thread 4525066044) stays open by scope.

## Fix map

| Thread | Finding | Fix |
|---|---|---|
| 4525066013 (`coordinator.py:910`) | a claim older than the run wall clock was dismissed without `--force`, though a run past its wall clock still owns its story until its task finishes | `--force` is required unless local state proves the claim's run finished with the story: a run of the marker's id **and instance** under the state directory with the story in `proposed`, `blocked` or `cancelled` (`local_run.finished`). Age and wall clock stay in the journaled evidence as information only. |
| 4525066020 (`coordinator.py:901`) | the local-run check read a story file without a phase, or with an unknown phase, as not owned, while `other_runs_with_active_stories` read it as owned | one rule, `state.story_ownership(path)`, used by both readers: unreadable, no phase and unknown phase are owned (fail closed); `FINISHED_PHASES = (proposed, blocked, cancelled)` are the only unowned phases. A torn `run.json` is read as unreadable (owned), never as a legacy run without an instance. |
| 4525066036 (`cli.py:145`) | `check-activation` without `--run-id` always listed `run id None is invalid` | the bound-digest lookup runs only when `--run-id` is given |

## Verification

`GITHUB_ACTIONS=true python3 -m unittest discover -s automation/tests -t .`: 442 OK. New `automation/tests/test_pr115_recheck_round4.py` (5 tests); `test_pr115_fix_first_round3.py` and `test_pr115_recheck_findings.py` re-premised where they assumed an old claim dismisses without `--force`.

## Blind review triage

1. Torn `run.json` read as legacy run without instance (same=True) ⇒ fixed: non-dict record raises into the unreadable branch (owned). Test added.
2. `run-concurrent` docs row still said "active or conflict, or unreadable" ⇒ updated (unknown phase included; cleared only by hand).
3. Refusal wording attributed the claim to the local run of the same id ⇒ reworded ("names run X, and a run of that id … still owns").
4. Unknown-phase story file now blocks admission under that state directory with no in-tool exit ⇒ accepted (fail closed), documented in the `run-concurrent` row.
5. `OverflowError` from an absurd journal mtime ⇒ not fixed (negligible).
6. Test gaps: legacy pairing (marker without `inst` + run without `instance` ⇒ proof; nonced marker ⇒ no proof) and torn `run.json` ⇒ tests added. Non-UTF-8 story bytes ⇒ not added (same branch as torn JSON).
7. `--run-id ""` still reaches `activation.problems` as `""` (activation-mismatch) ⇒ accepted.
