# E01 follow-up issues to create (E01-R-12)

Drafted by the E01 retrospective remediation on 2026-11-12. **Nothing here has been created on GitHub**: creating issues, editing them and changing Project Status are owner actions. This file is the ready-to-run list the retrospective asked for (action item E01-R-12, finding L6: none of the E01 deferrals had a tracking issue).

- 26 entries of the deferred-work ledger (`deferred-work.md`), keys `L01`–`L26` in ledger order.
- The retrospective findings that had no ledger entry: `B4`, `B7`, `D1`, `S1`, `S2`.
- 10 more that the remediation itself turned up and that would otherwise be lost: `X1`–`X10` (`X4`–`X10` are also new ledger entries). Create them or not as you see fit.

Entries this pull request resolves are listed for completeness and marked; they need no issue (L02, L07). That leaves **39 issues to create**.

The machine-readable list, with the full body of each issue, is [`e01-deferred-issues.json`](e01-deferred-issues.json) (fields: `key`, `title`, `labels`, `parent_epic`, `parent_issue`, `related_story_issue`, `resolved_by_this_pr`, `body`). Labels are existing repository labels. The parent epic is a proposal with its reason in the body; change it in the JSON before running if you disagree.

## Run it

Review the JSON first. The loop below creates each issue that is not marked resolved and attaches it to its parent epic as a native sub-issue. It prints what it would do unless `APPLY=1` is set. It skips a title that already exists as an issue (open or closed), so it can be run again after a failure, and it stops at the first command that fails instead of reporting success.

```sh
set -euo pipefail
cd "$(git rev-parse --show-toplevel)"
REPO=gabrianoo/owl-mast
LIST=_bmad-output/implementation-artifacts/e01-deferred-issues.json
jq -c '.[] | select(.resolved_by_this_pr | not)' "$LIST" | while read -r issue; do
  title="$(jq -r .title <<<"$issue")"; parent="$(jq -r .parent_issue <<<"$issue")"
  labels="$(jq -r '.labels | join(",")' <<<"$issue")"
  existing="$(gh issue list --repo "$REPO" --state all --limit 500 --json number,title \
    | jq -r --arg t "$title" '.[] | select(.title == $t) | .number' | head -1)"
  if [ -n "$existing" ]; then echo "exists: #$existing $title"; continue; fi
  if [ "${APPLY:-}" != 1 ]; then echo "would create: [$labels] $title (sub-issue of #$parent)"; continue; fi
  url="$(jq -r .body <<<"$issue" | gh issue create --repo "$REPO" --title "$title" --label "$labels" --body-file -)"
  [ -n "$url" ] || { echo "failed to create: $title" >&2; exit 1; }
  child="$(gh api "repos/$REPO/issues/${url##*/}" --jq .id)"
  gh api -X POST "repos/$REPO/issues/$parent/sub_issues" -F sub_issue_id="$child" --silent \
    || { echo "created $url but could not attach it to #$parent; attach it by hand, then rerun" >&2; exit 1; }
  echo "created $url under #$parent"
done
```

New issues start in the Project's Backlog like all imported work; adding them to the Project and setting Status and Priority is left to you.

## The list

| Key | Title | Labels | Parent epic | Related story | Note |
| --- | --- | --- | --- | --- | --- |
| L01 | Mount an operator-supplied CA trust so external PostgreSQL can use sslMode=verify-ca/verify-full | `enhancement`, `scope:v1` | E18 (#18) |  |  |
| L02 | Rerun the Kind qualification for chart 0.2.0, including first-enable and bootstrap-admin retirement | `enhancement`, `scope:v1` | E01 (#1) |  | resolved by this pull request; no issue needed |
| L03 | Check rendered HTTPRoutes against an API server with the Gateway API v1.4.0 CRDs (server-side CEL) | `enhancement`, `scope:v1` | E18 (#18) |  |  |
| L04 | Serve TLS from the bundled PostgreSQL and connect with a verifying sslmode | `enhancement`, `scope:v1` | E18 (#18) |  |  |
| L05 | Check the audit actor of an audited mutation against the principal bound in the scope | `enhancement`, `scope:v1` | E02 (#2) | #27 |  |
| L06 | Authorize the failed-work operator listing through the real authorization port | `enhancement`, `scope:v1` | E02 (#2) | #27 |  |
| L07 | Align the feature layering table with FeatureModuleRules | `enhancement`, `scope:v1` | E01 (#1) |  | resolved by this pull request; no issue needed |
| L08 | Process tenants with bounded parallelism instead of one at a time per wake-up | `enhancement`, `scope:later-evolution` | E19 (#19) |  |  |
| L09 | Add fenced lease renewal (heartbeat) for long-running work handlers | `enhancement`, `scope:v1` | E06 (#6) |  |  |
| L10 | Make audit.event append-only for the application role and keep corrections as linked rows | `enhancement`, `scope:v1` | E16 (#16) | #88 |  |
| L11 | Enforce tenant isolation of jobs and audit tables with row-level security | `enhancement`, `scope:v1` | E02 (#2) | #27 |  |
| L12 | Define retention for published audit intents and succeeded work items | `enhancement`, `scope:v1` | E16 (#16) |  |  |
| L13 | Expose failed separate-path audit outcome writes as a metric or readiness signal | `enhancement`, `scope:v1` | E18 (#18) |  |  |
| L14 | List work items that are blocked but not terminal for an authorized operator | `enhancement`, `scope:v1` | E16 (#16) | #88 |  |
| L15 | Set TCP keepalive and connect timeout on the R2DBC connection the chart renders | `enhancement`, `scope:v1` | E18 (#18) |  |  |
| L16 | Record abstract/default and type-parameter bounds in the frozen contract-shape test | `enhancement`, `scope:v1` | E02 (#2) |  |  |
| L17 | Read stored vocabularies without failing on an unknown enum constant | `bug`, `scope:v1` | E02 (#2) |  |  |
| L18 | Bound owlmast.jobs.lease-duration below PostgreSQL's timeout integer limit | `bug`, `scope:v1` | E06 (#6) |  |  |
| L19 | Fail audit publication when the event id already exists for another tenant | `bug`, `scope:v1` | E16 (#16) | #88 |  |
| L20 | Use one waiting-time definition for tenant discovery and the claim order | `enhancement`, `scope:v1` | E06 (#6) |  |  |
| L21 | Gate protected features on the API compatibility verdict | `enhancement`, `scope:v1` | E02 (#2) |  |  |
| L22 | Run the pre-rollout API compatibility check automatically | `enhancement`, `scope:v1` | E18 (#18) |  |  |
| L23 | Bring failures raised outside controllers and the authentication challenge under the RFC 9457 envelope | `enhancement`, `scope:v1` | E02 (#2) | #24 |  |
| L24 | Decide whether the frontend image ships the nginx base image's 50x.html | `enhancement`, `scope:v1` | E18 (#18) |  |  |
| L25 | Recover automatically from a shown Incompatible verdict or denial when a later check passes | `enhancement`, `scope:v1` | E02 (#2) |  |  |
| L26 | Generate the frontend image's refused shell-route list from one source | `enhancement`, `scope:v1` | E18 (#18) |  |  |
| B4 | Bound database connections: pooling decision and connection limits for the backend and Keycloak | `enhancement`, `scope:v1` | E18 (#18) |  |  |
| B7 | Give the chart a supported path to tune owlmast.jobs.*, owlmast.audit.* and owlmast.blocking.* | `enhancement`, `scope:v1` | E18 (#18) |  |  |
| D1 | Validate the API path prefix from one source of truth | `enhancement`, `scope:v1` | E02 (#2) |  |  |
| S1 | Split WorkProcessor into claim/dispatch and settle | `enhancement`, `scope:v1` | E06 (#6) |  |  |
| S2 | Group the durable-work and audit integration suites by acceptance criterion | `enhancement`, `scope:v1` | E06 (#6) |  |  |
| X1 | Add a migration lint that refuses hnsw/ivfflat when the first vector index is created | `enhancement`, `scope:v1` | E03 (#3) | #34 |  |
| X2 | State how audit rows with project Unknown are shown once projects exist | `enhancement`, `scope:v1` | E02 (#2) | #25 |  |
| X3 | Name recovery of unpublished audit intents in the live pod-replacement qualification | `enhancement`, `scope:v1` | E18 (#18) | #98 |  |
| X4 | Keep a blocking call that fails after its deadline from being logged with its stack trace | `bug`, `scope:v1` | E02 (#2) |  |  |
| X5 | Deploy the frontend image in the Kind qualification and check the routed compatibility endpoint | `enhancement`, `scope:v1` | E18 (#18) |  |  |
| X6 | Script the full bootstrap-admin retirement: permanent administrator created, temporary user deleted | `enhancement`, `scope:v1` | E02 (#2) | #24 |  |
| X7 | Move the Gradle wrapper from 9.9.0 to 9.9.1 with a rerun of the wrapper qualification | `enhancement`, `scope:v1` | E18 (#18) |  |  |
| X8 | Lint the shell embedded in the chart's ConfigMap scripts and the Kind fixtures | `enhancement`, `scope:v1` | E18 (#18) |  |  |
| X9 | Make `helm upgrade` from chart 0.1.0 work: the backend Deployment cannot change from rolling to Recreate in place | `bug`, `scope:v1` | E18 (#18) |  |  |
| X10 | Run one uninterrupted first-enable through the bootstrap-admin retirement on the Kind target | `enhancement`, `scope:v1` | E01 (#1) |  |  |

Sources: `L` keys quote the ledger entry's summary, status and evidence verbatim in the issue body; `B`, `D` and `S` keys cite the retrospective finding of the same name; `X` keys cite where the remediation found them.
