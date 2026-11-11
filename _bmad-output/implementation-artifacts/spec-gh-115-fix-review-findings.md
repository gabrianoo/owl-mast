---
title: 'Fix the bmad-review findings on PR #115 (ENG-01 unattended execution, second pass)'
type: 'bugfix'
created: '2026-11-09'
status: 'done'
route: 'oneshot'
review_loop_iteration: 0
context: []
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** PR #115 (`t3/pr107-review-findings` at `973d7e4c0840a010790957d363c09fe287ee2437`) carries a bmad-review (review 5831815549, 2026-11-09) with 30 findings: 27 inline threads and 3 in the review body. Most #107 fixes cover only the reported example: the claim race is unsettled when the re-read fails, the process crashes or `resume` completes the claim; markers are trusted only from the local viewer so two legitimate identities can admit one story; `cancel-run` marks the run cancelled and then aborts on one corrupt story file; the contract-design exception still admits stories over unknown dependency facts; HTTP 403 secondary rate limits classify as permission denial; several fixes have tests that would not fail if reverted.

**Approach:** Work through every finding on the same branch, fixing each in the code, tests, fixtures or docs it names and declining none without a recorded reason. Push the result to PR #115, reply to every inline thread with what was done and resolve it, and keep CI green.

</frozen-after-approval>

## Implementation Notes

- Baseline: branch `t3/pr107-review-findings` at `973d7e4`, 372 automation tests OK (`GITHUB_ACTIONS=true python3 -m unittest discover -s automation/tests -t .`). Working tree clean apart from the untracked local `.java-version`.
- Decisions taken without asking (the owner would not notice a different choice, or the reviewer's own suggestion was followed):
  - Finding 3 (cross-identity trust): fail closed. A `claim` marker from **any** author blocks admission and takes part in the claim race; only the trusted author's markers are adopted as our own, and a `release`/`block`/`proposal` clears a claim only when posted by the same author and run as that claim. No policy allowlist of logins (that would be a second trust root the activation does not bind).
  - Finding 2 (shared run id): every run records an `instance` nonce in `run.json` (optional key, absent on legacy runs) and carries it as `inst=` in its markers; a same-run marker with another nonce is foreign.
  - Finding 10 (state-dir scope): `reserve` scans the comments of every other allowlisted story for an active claim by any other coordinator (any state dir, any machine) and refuses `claim-active-elsewhere`; the state-dir scan stays as a cheap local check.
  - Finding 14 (digest): the policy digest becomes the sha256 of the canonical parsed policy (`json.dumps(asdict(policy), sort_keys=True)` without the digest); a run bound to the legacy raw-bytes digest of the same bytes is still bound (`Policy.raw_digest`), so the committed legacy fixtures and historical state keep working without migration.
  - Body finding 2 (reviewer isolation): a review receipt now needs `--worktree`/`--branch` naming the reviewer's own checkout; it is verified with the worktree check and refused when it equals the implementer's claimed worktree (`reviewer-worktree-shared`).
  - Body finding 3 (drift): `run.json` records the policy targets at creation (optional key); a late receipt under policy drift validates against the recorded targets.
  - Finding 15 (HistoricalCopyTests): a scrubbed copy of the immutable pre-recovery backup (`/home/gabrianoo` → `/home/operator`, pickle converted to `transport.json`, only the files the replay needs) is committed under `automation/tests/fixtures/historical-eng01-trusted-20261106/` and the replay runs unconditionally; the machine-local replay of the original backup stays optional.
  - Finding 11 (run-id case): run ids are lowercase only (`^[a-z0-9][a-z0-9._-]{0,63}$`, no `--`); every committed run id already is.
- Finding map (review 5831815549, thread comment id → fix):
  - 1 / 4517278409 claim race on every path: `claim.race_settled` persists (`False` with the claim, `True` by `_settle_claim_race`); `bind-receipt` refuses `claim-race-unsettled`; both `resume` claim paths and a `reserved`-but-unsettled story settle (lost ⇒ cancelled + release); an unreadable own claim is `conflict` (`claim-unverifiable`); `_unreturned_authorization` treats an unsettled reservation as structurally unlaunched.
  - 2 / 4517278423 shared run id: `RunState.instance` nonce (optional key), `inst=` in every marker; `_own_marker`/`_same_effect` (a marker without `inst` is a legacy one of this run).
  - 3 / 4517278440 cross-identity trust: `_marked_comments(trusted_only=False)`; any author's claim counts (`foreign-claim-counted`), release/block/proposal clear only the same (run, inst, author) claim, only the trusted author's markers are adopted.
  - 4 / 4517278453 App tokens: `viewer_login` falls back to GraphQL `viewer{login}` on `PermissionDenied`.
  - 5 / 4517278464 eligibility tri-state: `dependency_state`/`epic_complete` return met/unmet/unknown; any unknown ⇒ `unknown-eligibility` before the exception (no item/Status, close reason not COMPLETED, reopened, unreadable declarations, unknown child state). Two `test_eligibility` expectations moved from `blocked-by-dependency` to `unknown-eligibility`.
  - 6 / 4517278475 repository filter: casefold compare; `Snapshot.dropped_items` (also in `verify_mapping.counts.dropped_project_items`); all items foreign while the repo has issues ⇒ `project-items-foreign`.
  - 7 / 4517278484 and 8 / 4517278499: `Store.list_stories_tolerant`; `cancel-run` releases readable stories and reports unreadable ones (`state-corrupt`) in `awaiting_worker_termination`; `status` reports `unreadable_stories` and counts the rest; admission and every other reader stay strict.
  - 9 / 4517278510 values: `StoryState._value_problems` (phase in PHASES, basic field types) ⇒ `state-corrupt` with `path`.
  - 10 / 4517278526 state-dir scope: `_claims_elsewhere` scans every other allowlisted story on GitHub ⇒ `claim-active-elsewhere`.
  - 11 / 4517278539 and 12 / 4517278556 run ids: lowercase only, no `--`, dead `split('.')` clause removed; `other_runs_with_active_stories` compares casefold.
  - 13 / 4517278568 durability: `ensure_directory` fsyncs every created directory in its parent (atomic writes, lock dir, run root); the journal's first line fsyncs the run root.
  - 14 / 4517278585 digest: `canonical_digest` (sorted JSON of the parsed policy); `Policy.raw_digest` kept; `Store.digest_bound` accepts a run bound to the legacy raw digest of exactly these bytes (legacy fixtures and historical state need no regeneration).
  - 15 / 4517278592 HistoricalCopyTests: committed scrubbed fixture `automation/tests/fixtures/historical-eng01-trusted-20261106/` and `HistoricalFixtureReplayTests` (runs in CI, also exercises cleanup under drift); the machine-local replay stays optional.
  - 16 / 4517278600 nested connections: `_complete(connection, what, more)` follows `endCursor` pages for labels, field values and project fields (50-page runaway guard); a page without a cursor still refuses.
  - 17 / 4517278605 `project_info` builds inside `_shaped`.
  - 18 / 4517278611 bounds: `max_wall_clock_minutes ≤ 10080`, `checks.timeout_minutes ≤ 1440`, `probes.timeout_seconds ≤ 86400`, stories ≤ 1000, tasks ≤ 10000.
  - 19 / 4517278622 spec fix map item 18 corrected to exit 4.
  - 20 / 4517278629 CLI: `_Parser.error` raises `input-invalid`; `parse_args` inside the `try`; exit 2 is only a negative result.
  - 21–27 / 4517278647, 4517278659, 4517278666, 4517278678, 4517278689, 4517278699, 4517278709 verification gaps: real `git_clean` failures (deleted dir, exit 128, timeout) and the gate end to end over a timing-out `git status`; captured queries assert `pageInfo{hasNextPage endCursor}` on labels/fieldValues/fields and `repository{ nameWithOwner }`; `check-permissions` argv pinned to `repositoryOwner(login:`; `os.fsync` spied on directory descriptors with EIO propagating and EINVAL tolerated; `validate_receipt` and `bind-receipt` refuse a `shared`/missing reviewer isolation; the release-post failure and the unreadable-own-claim branches of `_settle_claim_race`.
  - body 1 classify: rate-limit text (primary, secondary, abuse, 429) classified as `Outage` before the 401/403 branch.
  - body 2 reviewer isolation: review receipts need `--worktree`/`--branch`, verified with the worktree check, refused when equal to the implementer's claim (`reviewer-worktree-shared`); recorded on the reviewer receipt. Test support: `REVIEW_WORKTREE`/`REVIEW_BRANCH`; 51 reviewer bind call sites updated; the smoke helper's reviewer `bind` takes them too.
  - body 3 drift targets: `RunState.targets` recorded at creation (optional key); `_bound_target` uses them under drift so a late receipt binds for cleanup.
- Verification: `GITHUB_ACTIONS=true python3 -m unittest discover -s automation/tests -t .` → 408 tests OK (372 + 36 in `automation/tests/test_pr115_review_findings.py`); the committed legacy fixtures pass unchanged (the raw-digest alias binds them).
- Review round (blind hunter, 13 findings): 12 patched in the same change (see the triage log); the spec-status finding is closed by this finalization. Thread replies and resolutions on PR #115 are recorded in the memory note and the PR itself (every inline thread gets a "Fixed in <sha>" reply naming the change).

## Review Triage Log

- legacy inst-less marker adopted by a nonce-carrying run (shared run id with pre-nonce code) — medium, patched: `_own_marker`/`_same_effect` accept a marker without `inst` only when the run itself has no nonce; the two tests that seed own duplicates now carry the nonce.
- `resume` claim replay skips the cross-story scan; scan limited to this policy's allowlist — medium, patched: the pending-claim replay runs `_claims_elsewhere` before posting and cancels the reservation (nothing landed, no release owed); refusal text and docs say "this policy's allowlist".
- one comment read per allowlisted story per `reserve`, journal entries under the other story — low, patched in the docs (call budget stated; the allowlist is small by design); the journal entry is correct where it is (the claim is on that story).
- reviewer worktree nested with the implementer's passes; HEAD not asserted — medium, patched: a path nested either way is `reviewer-worktree-shared`; the reviewer's HEAD at binding is recorded (`head_at_bind`) but not asserted, because the reviewer checks the SHA out itself after launch and a worktree created from another ref would otherwise refuse a legitimate review.
- crash after the resume post untested — low, patched: `test_a_crash_after_the_resume_post_is_settled_by_the_next_resume` (the premise corrected: such a crash leaves `claim-incomplete`, the next resume adopts and settles).
- stale `sha256sum` guidance on the activation candidate and in `activation.py` — medium, patched: both point at the canonical digest reported by `check-activation`; `activation.problems` deliberately has no raw-digest alias (an activation is written fresh for one run).
- `instance` regex admits non-hex — low, patched: `[0-9a-f]{8,32}`.
- `project-items-foreign` fires for drafts-only Projects and for the historical transport (repository null) — medium, patched: only items linking a *named* other repository are evidence; unknown-repository items are counted under `?` and the snapshot proceeds; tested.
- fixture-untouched comment without an assertion — low, patched: the fixture tree is hashed before and after the replay.
- two ceilings untested — low, patched.
- `node(id:"%s")` interpolation — low, patched: `json.dumps` like the cursor.
- tolerant `status` budgets silently partial — low, patched: `budgets.partial` flag.
- spec frontmatter `in-progress` and no record of the push and thread replies — true at review time; closed by this finalization (status `done`; replies recorded on the PR and in the memory note).
