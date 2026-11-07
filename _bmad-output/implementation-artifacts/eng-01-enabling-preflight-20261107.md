# OM-01.02 activation preflight (read-only), 2026-11-07

Companion to `spec-eng-01-enabling-preflight.md`. Everything below was read, never written: no status, checkbox, Project field, issue comment, cluster, service or credential was changed. Sanitized: no tokens, no private Notion content.

**Status: activation target unspecified and unqualified. The enabling change was reviewed at 96ad53a with changes requested (six findings R1–R6); repair round 1 is applied and a fresh review is pending. Not eligible for activation approval, not approved, not enabled; activation itself stays blocked on the owner decisions listed at the end. OM-01.02 remains Backlog; PR #107 remains unmerged at f71167b.**

## Verified (read-only, this machine)

| Item | Result |
| --- | --- |
| Baseline | worktree clean at `f71167bdaf0c8519cc71874af1167b4b66f9f3ee`; `origin/main` `c5d9d2e`; PR #107 OPEN, head f71167b, base `main`, no review decision |
| ENG-01 #106 | OPEN, label `engineering-automation` |
| OM-01.02 #21 | OPEN, labels `story`, `scope:v1`; Project Status **Backlog** (candidate `plan` dry run: `awaiting-owner-acceptance`, "Ready requires owner acceptance"); `Depends on: OM-01.01` |
| OM-01.01 #20 | CLOSED, reason `COMPLETED` (2026-11-06) — dependency satisfied |
| E01 #1 | OPEN |
| `verify-mapping` | ok, no problems (19/85/340 and relationships against live GitHub) |
| `probe` | ok: `gh auth status` 0, `git --version` 0 (2.43.0), `docker version` 0 (server 29.9.2) |
| `check-permissions` | `basic_access` true; `bounded` false; `unattended_activation_allowed` false (exit 2, by design). Disclosed: active identity has repository **admin**, classic scopes `repo`, `project`, `workflow`, `read:org`, `gist`, `admin:public_key`; Project `viewerCanUpdate` true. Broad, not least-privilege; denial not tested; resource scope not verified. A second inactive `gh` account exists on this host. |
| Candidate policy | `automation/examples/first-run-om-01-02.toml`: allow `["OM-01.02"]`, E17/E19 excluded, no exceptions, 1 story, 1 implementer, 2 repairs, 6 tasks, 240 min; implementer `claudeAgent`/`claude-fable-5-1`/worktree/effort high; reviewer `codex`/`gpt-6-astra`/reasoningEffort high; checks `./gradlew build --console=plain`, `scripts/verify-quality-gates.sh`, `python3 -m unittest discover -s automation/tests -t .` (45 min); probes as above (60 s) |
| Candidate activation | `automation/examples/activation-om-01-02.candidate.toml`: `check-activation` against the candidate policy exits 2, stop `activation-mismatch`, problems: unapproved, zero policy digest, placeholder run id, expired window — cannot dispatch when copied |
| Local tooling present | `kubectl` client v1.36.1, `helm` v3.16.3 installed; **no cluster was contacted** |
| Checks on this change | 288 unit tests OK; `./gradlew build --console=plain` BUILD SUCCESSFUL; `scripts/verify-quality-gates.sh` all gates OK |

## Missing or unverified (explicit blockers, not guessed)

| Gate | State |
| --- | --- |
| Owner acceptance | OM-01.02 is Backlog; `Ready` is an owner Project action, not taken |
| Enabling change | this PR: prepared, **not reviewed, not merged**; PR #107 not merged |
| Approved activation | none exists; the owner would write a private run-specific copy with `approved = true`, exact run id, sha256 of the exact policy file, ≤ 24 h window and the smoke/review references |
| Kubernetes target (OM-01.02 AC1 "qualified Kubernetes/storage target") | **unspecified**: no cluster, context, namespace, storage class or node selection is recorded anywhere read; none was probed or chosen here |
| Durable storage / persistent-volume ownership (T3) | unspecified; no evidence |
| Identity (Keycloak) and existing-secret references (T1/T2) | unspecified; no secret references exist in the repository and none may be committed |
| Image/chart pins (T1) | not selected; product decision |
| Credential for the worker/coordinator | only the broad disclosed `gh` identity; no restricted credential provisioned; nothing requested in this preparation |
| Real whole-run `cancel-run` smoke, live product dispatch | never performed; outside this change |

## Supported syntax for the first run (reference only; nothing here was executed against live state)

```sh
P=automation/examples/first-run-om-01-02.toml; A=<private approved activation, outside the repo>; R=<run id>
python3 -m automation.unattended --policy $P verify-mapping && python3 -m automation.unattended --policy $P probe
python3 -m automation.unattended --policy $P --activation $A --run-id $R check-activation            # must print "current": true
U="python3 -m automation.unattended --policy $P --activation $A --live --run-id $R"
$U reserve OM-01.02 --baseline <sha>        # then delegate_task (implementer), bind-receipt, record-head, run-checks, authorize-review, bind-receipt, record-review, propose-evidence
# stop conditions: wall clock 240 min, 6 task authorizations, 2 repair rounds, activation expiry — all refuse advancement; then:
$U cancel OM-01.02 --reason "…" --task-evidence '{"taskId": …, "runId": …, "status": "interrupted"}'   # after task_cancel reports terminal
$U cancel-run --reason "…"                 # shutdown; works after expiry without advancing
$U resume OM-01.02                         # restart: cleanup replayed, advancement only under a current activation
```

Terminal evidence is task-specific: the `task_status` record of exactly the bound `(taskId, runId)` with `workState: result_available`, or the terminal `task_cancel` result; `cancel_requested` is not terminal.
