---
title: 'Resolve the bmad-review findings on PR #107 (ENG-01 unattended execution foundation)'
type: 'bugfix'
created: '2026-11-09'
status: 'done'
route: 'oneshot'
review_loop_iteration: 0
context: []
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** PR #107 (merged 2026-11-07 as `945da5b`, head `f71167bdaf0c8519cc71874af1167b4b66f9f3ee`) carries a post-merge bmad-review (review 5827032319, 2026-11-09) with 36 findings; checked against `main` at `137e084625adb328a3248399a428d850c9ef4fbd`, 32 are still open and one (corrupt story files) is only partly resolved. They weaken the admission race, marker trust, run identity, policy parsing, transport fail-closed classification and the cleanup paths the unattended coordinator relies on.

**Approach:** Work through every open or partly resolved finding one by one on a new branch from `main`, fixing each in the code, tests, workflow or docs it names, declining none. Push the result as a new PR, reply to every inline thread with what was done, and keep CI green.

</frozen-after-approval>

## Implementation Notes

- Baseline: `main` at `137e084625adb328a3248399a428d850c9ef4fbd`, 339 automation tests OK (43 s). Branch `t3/pr107-review-findings`. The uncommitted PR #108 follow-up work found in the tree was preserved as a WIP commit on its own branch `t3/pr108-review-findings` (local only) so this branch starts at `main`.
- Findings 2, 8 and 36 were already resolved on `main` (review ledger); no change.
- Finding map (ledger # / comment id → fix):
  - 1 / 4513632901 CI skip: `automation-tests` checkout uses `fetch-depth: 0`; `RegeneratedLegacyFixturesTests` fails instead of skipping when `CI` is set and the baseline ref is unreachable. `HistoricalCopyTests` stays an optional machine-local replay (documented).
  - 3 / 4513632924 marker trust: markers count only when the comment author is the transport's own identity (`Transport.viewer_login()`; `gh api user`); other authors are ignored and journaled (`foreign-marker-ignored`). Applies to foreign-claim detection, intent adoption/duplicate detection and the write probe.
  - 4 / 4513632931 reserve race: after the claim posts, claims are re-read; earliest claim wins (created_at, then comment id); a later claimant is cancelled with its release posted and refuses `claim-race-lost`; its unlaunched authorization resolves structurally.
  - 5 / 4513632937 per-run budgets: `reserve` refuses `run-concurrent` while another run under the same state directory has an active or conflict story; budgets are documented as per run id.
  - 6 / 4513632954 run id: `Store.__init__` validates `^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$` (`run-id-invalid`); the CLI goes through it (also `probe-write`).
  - 7 / 4513632970 markers: `render_marker` validates every value against `^[A-Za-z0-9._:/-]+$` (`marker-value-invalid`); parse/render round-trip tested.
  - 9 / 4513632994 truncation: `pageInfo{hasNextPage}` on `fieldValues`, `labels` and `fields`; truncation raises `TransportError`.
  - 10 / 4513633005 repository: items carry `repository{nameWithOwner}`; `take_snapshot` drops other repositories' items and refuses duplicate issue numbers (`ambiguous-project-item`).
  - 11 / 4513633012 CI rollup: `_validate_pr` requires `SUCCESS` (`pr-checks-not-successful`).
  - 12 / 4513633021 eligibility: an unknown dependency or epic prerequisite is `unknown-eligibility` before the contract-design exception.
  - 13–16 / 4513633025, 4513633035, 4513633042, 4513633054 policy typing: strict `_bool`/`_int`/`_strings` helpers (`type(v) is int`, no coercion), sections must be tables, timeouts ≥ 1, `commands`/`allow` must be arrays of strings; every failure is a `PolicyError` problem.
  - 17 / 4513633060 reviewer isolation: `targets.reviewer.isolation` must be `worktree`; policy files, the activation candidate, test receipts and the committed legacy fixtures (regenerated from `bb4c3ee` with the new policy text) follow.
  - 18 / 4513633069 CLI contract: `_load_json_arg` raises `input-invalid`; `main` ends with `except Exception` → `{"error": {"code": "internal", ...}}`, exit 3.
  - 19 / 4513633074 snapshot: `_snapshot` also catches `TypeError`.
  - 20 / 4513633080 org Projects: queries go through `repositoryOwner(login:) { ... on ProjectV2Owner { projectV2 } }`; a null owner or project is `NotFound`; `check-permissions` uses the same query.
  - 21 / 4513633090 torn journal: append terminates a torn last line first; `read_journal` reports an unparsable line as `journal-torn-line` instead of raising.
  - 22 / 4513633095 durability: `atomic_write_text` fsyncs the parent directory after `os.replace`.
  - 23 / 4513633102 policy drift: a changed policy digest is a run stop (`policy-drift`, journaled once at open): advancing refuses, cleanup (cancel, block, terminal records, cancel-run, resume cleanup, reconcile, status) proceeds, a late receipt binds for cleanup only. The digest stays the raw bytes (the activation binds it).
  - 24 / 4513633109 probe-write: `--run-id` required; exit 2 when the probe is not idempotent.
  - 25–27 / 4513633114, 4513633120, 4513633134 transport: GraphQL errors classified on `type` first (`RATE_LIMITED` → `Outage`, `FORBIDDEN` → `PermissionDenied`, `NOT_FOUND` → `NotFound`); `data` must be an object; comment JSON parsing raises `TransportError`.
  - 28 / 4513633146 git failures: `git_clean` reports failure as `None`; a `None` HEAD or unreadable status refuses `worktree-unreadable` without invalidating evidence.
  - 29 / 4513633153 cancel-run: evidence maps validated as objects before the run is marked cancelled; every `Refused` per story is reported in `awaiting_worker_termination` with its code.
  - 30 / 4513633166 resume: owed cleanups replay before the worktree check; the worktree is checked only for active stories.
  - 31 / 4513633177 receipt shape: `bind-receipt` refuses a non-object receipt (`receipt-invalid`) before any `.get`.
  - 32 / 4513633186 run_commands: unbalanced quotes or an empty command become a failed result, never an exception.
  - 33 / 4513633190 check-permissions: a missing or hanging `gh` is a reported problem, not a crash.
  - 34 / 4513633204 story files: `load_story`/`list_stories` refuse `state-corrupt` on unreadable JSON or shape errors.
  - 35 / 4513633212 backups: the backup name carries the authorization id and refuses when the path exists (`backup-exists`).
- Verification: `CI=1 python3 -m unittest discover -s automation/tests -t .` → 371 tests OK (339 baseline + 1 cross-run admission test in `test_sync.py` + 31 in the new `automation/tests/test_pr107_review_findings.py`). The legacy fixtures were regenerated with `PYTHONPATH=. python3 -m automation.tests.legacy_baseline --ref bb4c3ee480ed9094a67f1a18030e65be9a2a782c --out automation/tests/fixtures/legacy-bb4c3ee` (same scenario sha `0399856038fd…`, 44 scenarios, ~9 s) because the policy text (reviewer isolation) changes the digest the fixtures bind; only digests, timestamps and the reviewer receipts' `isolation` changed.
- Decisions: the `cancel-run` report shape is unchanged (no extra message key) so existing consumers keep working. A lost claim race ends as `cancelled` with `blocked.conflict = true` (released and terminal, so it does not block later admissions the way `conflict` does). `rebase-revisions` still lacks the run-active gate: that is PR #108 finding 4513640440 and stays with that branch (`t3/pr108-review-findings`). `HistoricalCopyTests` stays an optional machine-local replay; its temporary copy now gets a labelled policy patch (reviewer isolation) which exercises the policy-drift cleanup path.
- Surprises: markers from other authors were previously adopted as the coordinator's own (`_post_intent`), so the duplicate-marker tests had to be rewritten with the trusted author; `small_backlog()` items now carry the repository, so snapshots must be taken for `gabrianoo/owl-mast` (several tests used `x/y`).
- Review round (blind hunter, 17 findings): 16 patched in the same change (run-checks post-command git failures refuse `worktree-unreadable`; `gh api graphql` non-zero exits are classified on the typed errors; `foreign-marker-ignored` is journaled once per comment id; per-section unknown policy keys refuse; only directories with `run.json` count as runs; `GITHUB_ACTIONS`/`OWLMAST_REQUIRE_BASELINE` gate the baseline failure instead of `CI`; CLI crashes exit 4 with a traceback tail; GraphQL shapes are checked; messages, docs table, test cleanups and extra branch tests). Final: 372 tests OK with `GITHUB_ACTIONS=true`.

## Review Triage Log

- run-checks persists `checks-failed` when git fails after the commands — medium, patched: refuses `worktree-unreadable`, records nothing.
- typed GraphQL classification unreachable because `gh api graphql` exits 1 on errors — medium, patched: `_run` classifies the printed `errors` before the stderr text; tested on the subprocess path.
- `foreign-marker-ignored` journaled on every read — medium, patched: once per comment id, seeded from the journal.
- race loss spends the story slot silently — low, patched: refusal message and docs say so; the slot stays spent by design (an issued slot is spent).
- `run-concurrent` message suggested bypassing the guard — low, patched: names the real exit.
- GraphQL item/issue/PR shapes could raise `KeyError` — low, patched: `_shaped` wraps them into `TransportError`.
- crash and refusal shared exit 3 — low, patched: crash exits 4 with a traceback tail (finding 18's suggestion said 3; 4 keeps them apart).
- duplicate problem for a missing `project_number`; unknown keys inside sections ignored — medium, patched: `SECTION_KEYS`, no duplicate.
- any directory counted as a run — low, patched: `run.json` required; unreadable files named.
- directory fsync may fail on translated mounts — maybe-false here (verified: fsync of a directory handle works on this repository's `/mnt/c` mount and on `/tmp`); guarded anyway for `EINVAL`/`ENOTSUP`.
- `_load_json_arg` heuristic (`@file` syntax) — false for the cases named (`7` and `-1` parse as JSON after the path miss; a BOM-prefixed inline object is not a supported input); rejected: an `@file` syntax would change the CLI contract for no shown failure.
- dead code in tests — low, patched.
- untested branches — low, patched: backup-exists, run-checks pre/post unreadable, non-object journal line, empty `gh api user`, unreadable other-run story, unknown section keys, non-zero `gh` exit; the release-post failure inside `_settle_claim_race` and the `mine is None` conflict stay untested (same code path as `_cancel_stale_claim`'s failure branch, which is tested).
- `mkdtemp` leaks — low, patched.
- `CI=1` redundant and local-dev hazard — medium, patched: gate on `GITHUB_ACTIONS` or `OWLMAST_REQUIRE_BASELINE`.
- codes not documented in one place — low, patched: codes/events table in the docs.
- `_author` undeclared; App tokens cannot be the trusted author — low, patched: initialised in `__init__`; doc note.
