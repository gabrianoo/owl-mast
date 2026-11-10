---
title: 'Fix the five "fix first" findings of the PR #115 recheck review at 07c363c (ENG-01)'
type: 'bugfix'
created: '2026-11-10'
status: 'done'
route: 'oneshot'
review_loop_iteration: 0
context: []
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** The recheck review of PR #115 at `07c363cee76e6a8410705e9d8c74e687fcc1ba16` (review 5840034191, 2026-11-10, 20 findings) names five to fix first: `dismiss-claim` has no owner gate and dismisses a live coordinator's claim (`coordinator.py:812`, `:820`); a re-verified `claim-unverifiable` conflict is restored without the revision gate (`coordinator.py:1593`); earliest-wins trusts `created_at`, which an edit keeps, and counts claims whose holders already lost (`coordinator.py:964`, `:967`); a legacy split reservation saved without `race_settled` skips both race gates (`coordinator.py:1577`, body); the raw-bytes digest is accepted for every new activation (`activation.py:124`).

**Approach:** Fix exactly those five on the same branch (code, tests, docs), push to PR #115, reply to and resolve their threads, and leave the other findings of that review open for a later pass, listed for the owner.

</frozen-after-approval>

## Implementation Notes

- Baseline: `07c363c`, 419 tests OK, CI 6/6 green, tree clean apart from the untracked local `.java-version`.
- Fix map (review 5840034191 thread → change):
  - 1 / 4523540089 (`:812`) and 4523540082 (`:820`) `dismiss-claim`: gated `require_activation(advancing=True)` (live transport: the run's current activation, no stop, no drift); the target must be a claim on an allowlisted story's own issue (`dismiss-target-invalid`); a claim a run under this state directory still owns is refused always (`dismiss-target-live`, cancel it in its own run); the run must be active (not cancelled or past its wall clock); a claim younger than `max_wall_clock_minutes` is refused unless `--force` (the reason attests the coordinator is dead); the evidence (local run lookup with phase and last journal activity, claim age, wall clock, forced) is journaled write-ahead and with the dismissal; the comment body escapes free text (`_plain`: no `@`, backticks or line breaks); `posted` is true only when this call posted.
  - 2 / 4523540077 (`:1593`) re-verified conflict: `resume` runs `revision_diff` on the visible claim and cancels through `_cancel_stale_claim` on a change; the restore goes only to `reserved` (another `from_phase` is withheld), then the settle runs with the fresh snapshot.
  - 3 / 4523540132 (`:967`) and 4523540115 (`:964`) ordering: `Comment.updated_at` (REST `updated_at`, optional on fixtures); `_claim_order` is asymmetric so an edit never produces two winners: a foreign claim counts from its creation (a backdated edit costs us our slot, the loss names the edit and `dismiss-claim`), ours from its last edit; unparseable ⇒ foreign earliest / ours latest (fail closed); the settle re-reads once before cancelling and takes the win only on the visible release/block/proposal of every earlier claim (`claim-race-reread`), so a loser still posting its release costs no one a slot while a claim that merely vanished from one read still counts.
  - 4 / body (`:1577`) legacy split reservation: `resume` sets `race_settled=False` on a `claim-incomplete` claim without the key (`claim-race-flag-added`) and on a pending claim replay, so both gates run before `reserved` is reported.
  - 5 / 4523540184 (`activation.py:124`) raw digest: `Activation.problems(bound_digest=…)` accepts the raw-bytes digest only when it is the digest an existing run is bound to; `Store.ensure_run` creates a live run only under the canonical digest; `check-activation` reads the bound digest of an existing run from the state dir (`bound_digest` in its report).
- Verification: `GITHUB_ACTIONS=true python3 -m unittest discover -s automation/tests -t .` → 437 tests OK (18 new in `automation/tests/test_pr115_fix_first_round3.py`; one existing test re-premised).
- Left open on purpose (not in the requested scope): the other 14 inline threads of review 5840034191 and the 20 inline threads + 2 body findings of review 5832610891 the author deferred earlier.

## Review Triage Log

- foreign claims ordered by their edit time let an edit to a legitimate earlier claim produce two winners — high, patched: asymmetric order (foreign from creation, ours from last edit); the test premise corrected (an edited earlier claim still wins, ours cancels).
- the unconditional re-read doubles the fail-open window of a missed read — medium, patched: the win is taken only when every earlier claim has a visible release by its own key; a vanished claim still counts.
- `owns_story` excluded `conflict`, which `resume` can restore — medium, patched: same ownership as `other_runs_with_active_stories` (active, conflict, unreadable).
- dismissal age ignored the edit time — medium, patched: age from the later of creation and edit.
- `posted` true on an adoption between the first read and the intent; no read-back — low, patched (`posted`, `readable`).
- pending legacy path set the flag in memory only; docs listed the event under `reserve` — low, patched (saved + journaled; table row corrected).
- `_settle_claim_race` / `_claim_unsettled` docstrings stale — low, patched.
- the live-gate test passed with `advancing=False` — low, patched: the advancing gate's own message is asserted.
- the unparseable-timestamp integration half never reached the settle — low, patched: the claim lands after our post.
- `check-activation` read a corrupt `run.json` as "no run" — low, patched: the refusal is reported in `problems`, exit 2.
- allowlist mapping built without `require_unique_ids` — low, patched.
