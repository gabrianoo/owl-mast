---
title: Owl Mast — AISQUAD organizational learning and delivery visibility
status: draft
created: 2026-11-05
updated: 2026-11-05
---

# Product brief: Owl Mast

## Purpose and first customer

Discovery draft for review.

The user confirmed observation and knowledge delivery as the first-version focus. Agents continue to be launched and controlled through existing tools. Owl Mast observes available activity, connects evidence, captures reusable knowledge and delivers authorized context; it does not launch, pause, cancel or retry agents. Knowledge capture and publication can still write to designated knowledge stores under their access policies.

Owl Mast will be an open-source project, first used inside AISQUAD. Commercialization may follow; agent sandboxing is a possible future offering, not an initial commitment. The open-source license and deployment model remain undecided.

AISQUAD's humans and agents work continuously across multiple projects. The user identifies their generated work and learnings as AISQUAD assets. Owl Mast should let the company manage those assets and understand progress across its human and agent workforce. Ownership is a product requirement supplied by the user; it does not automatically determine every participant's access rights.

## The problem

Organizational knowledge and work evidence are spread across people, agents, repositories, trackers and memory stores. A company-level view must preserve project context and authorization even when the same person or agent works across projects.

The concrete failure occurs when Mohamed starts multiple agents to develop a feature: the user loses track of Mohamed's contributions, the agents' contributions and the resulting state of the work. The user's own agents then cannot readily benefit from what Mohamed's agents produced. Today the team uses shared Discord connected to Hermes as a centralized-agent workaround. Agents also take too long to onboard, especially across teams. A drop-in experience with minimal onboarding is a first-version requirement.

The pilot deliberately spans two real environments:

- Syntelligence uses Jira in its own cloud account and GitHub.
- Movesion uses Jira in a different account and Bitbucket.
- Their other tools and AWS accounts also differ.
- The user, Mohamed and their agents work across both under AISQUAD.
- Hermes already develops skills and memory, with memory dumped into Notion.

These facts were supplied by the user on 2026-11-05; integration access and deployment details have not been tested.

## Proposed product experience

A contributor starts work in a project, receives relevant authorized knowledge, and leaves reusable learning with evidence of where it came from. A team lead follows work across the project's existing tracker and repository. An AISQUAD owner sees aggregate progress, agent activity, costs and the organizational assets produced, with drill-down governed by access rights.

The proposed first workflow is: Mohamed starts agents on a feature; Owl Mast shows the linked runs, changes, blockers and review needs; reusable lessons become available within that project; the user's next agent session receives relevant context without repeating discovery. General skills and lessons reach the company level only through explicit promotion.

[ASSUMPTION] A shared web interface and harness integrations serve these roles. A replacement coding client is not required. Claude, Codex and Hermes are in the pilot context; the instrumentation order remains to be selected.

## First-version boundary

The proposed pilot must demonstrate both projects, their separate Jira connections, GitHub and Bitbucket. It may be implemented sequentially, but a single-project demonstration does not prove the organizational requirement.

- Maintain organization, project, human and agent identities across connected systems. Record delegation and initiators where available without pretending every autonomous action had an immediate human author.
- Connect work items, runs, contributions and acceptance evidence using source-qualified identifiers. Preserve the existing trackers as authoritative.
- Capture selected skills, memories and chat evidence; distinguish raw records from validated reusable knowledge. Integrate the existing Hermes/Notion flow rather than silently replacing it.
- Keep knowledge project-scoped by default. Reusable skills and lessons require explicit promotion to AISQUAD-wide knowledge; this policy is user-confirmed. Who can promote and what validation is required remain open.
- Show progress, dependency evidence, usage and costs with missing coverage visible. Separate estimated usage cost from billing and subscription allocation.
- Minimize initial connection and per-agent setup. [PROPOSAL] An administrator connects each project's systems once; contributors enroll existing clients and select an authorized project. Exact installation steps and permissions must be validated.

These are proposed scope items, not validated connector capabilities. Reuse existing components where practical; no memory engine or telemetry stack has been selected.

## Pilot evidence and success

Demonstrate a sourced lesson produced in one session and used by a different contributor or agent. Demonstrate project boundaries and an authorized cross-project reuse case. Trace a work item through an agent run, repository contribution and acceptance in each project's toolchain. Show how AISQUAD discovers a blocked or failed run that no one is monitoring.

Measure time to understand a colleague's work without asking for a recap; time and manual steps from a fresh agent setup to its first useful project action; successful reuse of another contributor's learning; attribution coverage and collection gaps. Also inspect stale/conflicting knowledge, repeated work, review delays and maintenance effort. Numerical thresholds require a baseline and user agreement. Cost visibility alone is not proof of ROI.

## Deferred scope and unresolved decisions

Defer agent execution controls, predictive budget allocation, monetization features and agent sandboxing until the initial value is demonstrated. Open-source code does not imply public operational data or shared credentials.

Resolve during specification and technical validation: promotion authority, validation and revocation; deployment/access constraints and installation permissions; instrumentation order; acceptance thresholds; license. The colleague's ConvaDesk screenshots are user-supplied UX references, detailed in the addendum; they do not establish integration correctness or code reuse rights.

## Evidence

User discovery conversation, 2026-11-05; existing brainstorming and tool research under `_bmad-output/`. Public-source research supports component evaluation, not proven operational fit or a unique market gap. Durable project context is maintained in the Notion concept page: https://app.notion.com/p/40e8ce657080814ca0fdf40e67a36e8b.
