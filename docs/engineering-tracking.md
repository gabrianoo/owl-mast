# Engineering progress lives in GitHub

GitHub Issues own engineering progress. The [Owl Mast engineering Project](https://github.com/users/gabrianoo/projects/2) owns status and priority. Repository specifications define acceptance; Git history records their revisions. Notion retains decisions and pointers, without a second task list.

Browse the [epic issues](https://github.com/gabrianoo/owl-mast/issues?q=is%3Aissue%20label%3Aepic) and [story issues](https://github.com/gabrianoo/owl-mast/issues?q=is%3Aissue%20label%3Astory). [E01](https://github.com/gabrianoo/owl-mast/issues/1) contains the foundation stories, beginning with [OM-01.01](https://github.com/gabrianoo/owl-mast/issues/20).

The [specification](../_bmad-output/specs/spec-owl-mast/SPEC.md) adopts the existing architecture, PRD, UX and backlog. AD-1 through AD-16 and all OM story/task IDs remain stable. The import baseline is commit `b156ad5bb870a0f4cb8659f869ce0e3d8e234113`.

The private Project is linked to this repository. Its fields are Status, Priority, Scope and Stable ID. Status options are Backlog, Ready, In progress, In review, Blocked and Done. Priorities are P1 - Foundation (E01), P2 - Pilot (E02–E16/E18), Optional (E17) and Later (E19). Scope distinguishes v1, Optional and Later evolution. Stable ID retains each E/OM identifier. These fields describe engineering work; they do not enable BMAD synchronization.

## Tracking rules

- Each E01–E19 epic has one parent issue. Each OM story has one native sub-issue. Task checklists retain the exact OM task IDs and wording.
- Issue bodies preserve acceptance criteria, requirements, dependencies and links to the source revision. When requirements change, revise the repository specification through Git, then reconcile the affected issue without resetting its progress.
- Existing epic frontmatter, TASKS.md checkboxes and VALIDATION.md describe the planning baseline. Do not maintain execution status there. They remain intact as specifications and historical evidence.
- Project status describes execution; priority describes ordering, never readiness. All imported work starts in Backlog. Ready requires owner acceptance, satisfied implementation prerequisites and the applicable qualification gates. E01 is first priority; remaining pilot work follows dependencies. E17 is Optional; E19 is Later evolution.
- In progress requires actual work. In review requires linked implementation and validation evidence. Done requires acceptance criteria, relevant gates and review evidence; checked tasks alone are insufficient. Closed as not planned is not Done. Reopened or regressed work returns to its justified status.
- Keep blocked or operator-waiting work explicit. Preserve issue links to blockers and the missing decision/evidence. Epic completion requires its required children to qualify as complete.
- The [shared completion rules](../_bmad-output/planning-artifacts/epics.md#shared-story-completion-rules) and [qualification gates](../_bmad-output/planning-artifacts/epics.md#decision-and-qualification-gates) remain binding. Named contract-design work may proceed early with documentation or synthetic fixtures; production implementation and completion retain original dependencies.

## BMAD execution is not yet synchronized

The 2026-11-06 inspection found these compatibility limits:

- Installed `bmad-loop` is 0.13.2. `.bmad-loop/policy.toml` selects `stories.source = "sprint-status"`. Supported sources are `sprint-status`, `stories` and local BMAD `tickets`; none is a GitHub backend.
- The referenced `_bmad/method/scripts/tickets.py` is absent. Switching to `tickets` cannot enable GitHub execution. `stories.yaml` is another local dispatch format, not a GitHub adapter.
- The installed [sprint parser](../.agents/skills/bmad-sprint-planning/scripts/sprint_plan.py) expects `Epic 1` and `Story 1.1`. Its read-only dry run against E01 returned `no epics or stories parsed from the given epic files`. Preserve `E01` and `OM-01.01`; do not rename them to fit the parser.
- [Build synchronization](../.agents/skills/bmad-build/sync-sprint-status.md) writes local sprint entries. Build completion can set its story document to `done` while the sprint entry remains `review`. Neither transition automatically means a GitHub issue is complete.
- At inspection, no sprint-status file, implementation-artifact directory or loop run state existed. The policy file remains unchanged. No synchronization, execution loop or scheduled automation was enabled.

Retain the policy and any future run journals, checkpoints, review/operator state and deferred-work records. These are required machine state, not a second manually maintained progress tracker. Do not fabricate a sprint file to imply readiness.

Before unattended execution, qualify a bridge with these properties:

1. Map stable OM IDs to GitHub issue IDs and BMAD dispatch keys without renumbering. Adapt or generate the parser input; verify all 19 epics, 85 stories and 340 tasks.
2. Project a GitHub queue into machine-owned sprint state. Define one writer per field and explicit mappings for backlog, ready, active, review, blocked/operator-waiting, done, cancelled and reopened work.
3. Enforce dependencies, owner gates and scoped contract-design exceptions. Exclude optional E17 and later E19 from default pilot dispatch.
4. Send evidence-backed result proposals to GitHub with revision checks. Detect concurrent edits; never silently overwrite a newer issue or infer acceptance from checkboxes.
5. Test retries, duplicate events, partial writes, stale revisions, restart/resume, review regression, reopened issues, permission failures and GitHub outages. Fail closed when eligibility or synchronization is unknown.
6. Configure and qualify actual environment probes and verification commands before starting the loop. Their installed policy entries are empty.

Manual supervised development can use GitHub directly while the loop stays off. Do not claim the installed BMAD workflows provide automatic GitHub writeback.

The [unattended execution foundation](unattended-execution.md) (ENG-01, [#106](https://github.com/gabrianoo/owl-mast/issues/106)) implements a T3-driven tool under `automation/unattended` with passing fixture coverage for properties 1–5; every state command refuses the real GitHub transport. The final independent disposition of its PR (#107) verified six synchronization and control defects; remediation pass 1 fixes them with adversarial tests and awaits a fresh independent review. It is not qualified for unattended use: the T3 execution protocol has not been exercised with a bounded worker and T3 offers no child deadline or credential confinement, no bounded credential exists, and Project Status stays owner-written because GitHub offers no compare-and-swap (owner-only Status updates are not automated synchronization). `bmad-loop` stays unused.

## Starting E01

E01 and OM-01.01 have no predecessors. The owner must accept the E01 planning slice and authorize implementation in a subsequent session.

Begin with OM-01.01-T1: qualify Java 27/Spring Boot 4.1.2 against pinned Gradle, JDK distribution/patch, Lombok, formatter, analyzers and Testcontainers. Confirm a usable local/CI container runtime. Record compatibility evidence before relying on the bootstrap conventions.

The integration fixture must run actual PostgreSQL/VectorChord with its required pgvector dependency and exercise migrations and reactive transactions. OM-01.02/03/04 follow OM-01.01 and own installation packaging, work/audit infrastructure and independent frontend/API qualification respectively.

Browser authentication/origin/session qualification remains in OM-02.01. Live collection, retention and recovery gates remain later prerequisites; they do not block synthetic foundation qualification. Unattended E01 additionally requires the qualified synchronization path above.
