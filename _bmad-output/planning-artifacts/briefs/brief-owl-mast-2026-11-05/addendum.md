# Discovery details and future options

## User-confirmed pilot context — 2026-11-05

AISQUAD is the first customer and the company under which the user, Mohamed and their agents work. The user describes generated assets as AISQUAD property and wants both asset management and progress monitoring for humans and agents working around the clock.

Syntelligence has a dedicated Jira cloud account and GitHub; Movesion has another Jira account and Bitbucket. Other tools, including AWS accounts, differ. Exact Jira hosting/account structure, Bitbucket deployment type, provider identities and access permissions are not yet established.

Hermes has self-development skills and memory dumped into Notion. The memory schema, write mechanism, sync behavior and overlap with current Notion knowledge remain to be inspected during technical validation.

## Product direction

Open source first, internal organizational use first, possible commercialization later. Agent sandboxing was offered as an example of a possible future feature, not a selected commercial strategy. No license has been selected and no publication or access change has been requested.

## Architecture implications to investigate

Source identity should include connection/account and project so identical issue keys or repository names from different sources are not confused. A human or agent can participate in more than one project without those projects inheriting all its memory. Asset ownership, read access, publication and use are separate concepts. These are design implications, not an implemented architecture.

## Confirmed sharing policy and concrete pain

Project-scoped knowledge is the default. Reusable skills and lessons are explicitly promoted to AISQUAD-wide knowledge. Promotion approver, review criteria and revocation remain to be defined.

When Mohamed starts multiple agents to build a feature, the user loses track of human and agent contributions and cannot readily equip their own agents with the resulting knowledge. Shared Discord connected to Hermes is the existing centralized-agent workaround. Slow agent onboarding, especially across teams, makes minimal-setup, drop-in adoption a core requirement. These are user-reported pains, not inferred from the screenshots.

## Colleague's ConvaDesk UI references

Source: six screenshots supplied by the user on 2026-11-05, named IMG_AB4D1C8F3C45-1.jpeg, IMG_A9CC932E588C-1.jpeg, IMG_EF516651E585-1.jpeg, IMG_BC54BCBE01C2-1.jpeg, IMG_3626EBD8C28F-1.jpeg and IMG_DE187537BF11-1.jpeg. Inspected directly in the conversation. No live app or code was accessed; displayed numbers are not independently verified metrics. Original attachments remain in the conversation, not copied or published to the repository.

- Ticket detail combines goal/work area, assignees, workstream, prerequisites, observed PR signals, a GitHub link, Markdown and CI/review tabs. This is a useful drill-down pattern.
- Dependency explorer supports focus on a ticket, prerequisite context, filters, graph/list views and export. Its caption distinguishes issue state from evidence of a merge or acceptance. Dense edges suggest that a focused dependency neighborhood should be the default rather than an entire organizational graph; this is a design inference, not a usability test.
- Overview groups progress by release and goal, with an attention panel for active work, CI and qualification. Ticket completion is explicitly separate from release qualification. Proposed Owl Mast behavior: preserve the distinction and show who/which agents moved each work item.
- Usage view filters by machine, agent, model, ticket and dates, distinguishes cached input, and states that token volume is not a bill. The ticket breakdown visibly retains unassigned work. These are useful transparency patterns; Owl Mast should make attribution gaps actionable.
- The ticket modal displays a Completed badge while the body says Status: planned and no current PR signal is shown. The screenshot cannot establish the cause, but it motivates showing source, freshness and conflicting evidence rather than silently asserting one completion truth.

The supplied screens do not demonstrate cross-person learning delivery, scoped knowledge promotion, enrollment effort, or identity-linked human/agent delegation. Those capabilities need to be demonstrated in the pilot; their absence from the screenshots is not proof the colleague's application lacks them.

## Proposed acceptance story

Mohamed starts multiple agents against a real project work item. Another AISQUAD contributor can determine who initiated work, which agents executed it, what changed, what evidence exists and what is blocked, with timestamps and collection gaps visible. A newly enrolled agent can obtain a relevant sourced lesson produced by those agents without a manual recap. The lesson remains project-scoped until explicitly promoted. Repeat on both project toolchains.

Separate two onboarding measures: organization/project integration setup, and a new contributor/agent reaching its first useful action. A one-time administrative setup cost should not be hidden inside a claim of zero onboarding.

## Confirmed execution boundary

The user selected observation and knowledge delivery for the first version. Existing tools retain agent launch, pause, cancellation and retry. This does not make the knowledge workflow read-only: capture, validation and scoped publication remain part of the product. Integrations must not introduce execution authority merely to observe work.

## Proposed next validation work

Turn the pilot into a short specification with explicit acceptance criteria, then validate event capture and identity mapping for Claude, Codex and Hermes, separate Jira connections and GitHub/Bitbucket evidence. Inspect the existing Discord/Hermes/Notion learning path before selecting a memory component. Record unsupported events and synchronization gaps. Deployment preferences, promotion authority and numeric onboarding targets remain open; do not invent them as user decisions.
