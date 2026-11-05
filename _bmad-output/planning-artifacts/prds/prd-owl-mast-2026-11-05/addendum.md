# Owl Mast — design evidence and downstream considerations

Supporting material for [the PRD](prd.md), dated 2026-11-05. Mechanisms and component candidates below remain unselected. Claude and Codex are the required initial clients; T3 Code's two-agent setup is the experience reference. Complex initial administrator setup is acceptable, while recurring enrollment must require minimal effort. Promotion supports the user's preferred automatic mode, manual approval, and disabled mode. Deployment packaging and integration mechanisms remain architecture work.

## Evidence and source authority

Current explicit user decisions take precedence over earlier choices and research suggestions. The [product brief](../../briefs/brief-owl-mast-2026-11-05/brief.md), its [source addendum](../../briefs/brief-owl-mast-2026-11-05/addendum.md) and [decision record](../../briefs/brief-owl-mast-2026-11-05/.memlog.md) distinguish confirmed direction from proposals. The [Notion project context](https://app.notion.com/p/40e8ce657080814ca0fdf40e67a36e8b) supplies durable context. The [competitive research](../../research/competitive-owl-mast-dashboard-references-2026-11-05/research.md) and [brainstorming record](../../../brainstorming/brainstorm-owl-mast-2026-11-05/.memlog.md) contain candidate designs, not blanket scope approval.

Publisher documentation establishes documented capabilities; screenshots establish visible interface patterns. Neither proves interoperability, operational outcomes or usability. Missing public evidence does not establish missing functionality. Existing knowledge and tracing products overlap Owl Mast's vision, so claims of a unique market gap or savings remain unproven. Earlier one-project pilot and enforcement proposals do not govern this PRD: both customer environments must be demonstrated, within observation and knowledge delivery.

## ConvaDesk reference patterns

The source addendum records six user-supplied screenshots inspected during brief discovery. Original attachments remain in that conversation; no live application, code or integration was tested. Displayed figures are illustrative evidence only.

Useful patterns include a ticket drill-down connecting intent, contributors, prerequisites, PR links and review evidence; focused dependency neighborhoods with graph/list options; release and goal summaries with attention cues; and usage filters retaining unassigned work and separating token volume from billing. Ticket completion and release qualification deserve distinct representations.

One screen combines a Completed badge, planned status text and absent current PR evidence. Its cause is unknown; the relevant design implication is to expose source, freshness and conflicting evidence. Focused dependency views are a design inference, not a usability result. The screenshots do not establish onboarding effort, cross-person knowledge delivery or promotion behavior, and do not grant code or asset reuse rights.

## Preserve the existing knowledge path

Hermes already develops skills and memory, with memory flowing to Notion; shared Discord connected to Hermes is the current collaboration workaround. Inspect the memory flow's schema, write mechanism, source references and synchronization before selecting new infrastructure. Preserve this path and establish ownership of each record, duplicate handling and reconciliation with any derived index. Do not silently create two competing knowledge authorities.

AISQUAD ownership, project membership, source access and permission to promote are separate concepts. A contributor working across projects must not carry all customer knowledge into every session. Architecture should distinguish retained evidence, candidate lessons and published guidance, with source lineage, freshness, supersession and withdrawal behavior. Automatic promotion evaluates reusable content under a configured policy; manual mode adds per-item approval; disabled mode prevents new publication. The PRD defines checks and records for each mode. Named maintainers and project-specific use permissions must be configured before activation.

The user reports that Claude and Codex already create Notion pages and may read Notion skills. Page creation is reported behavior; skill reading remains unverified. Preserve the existing workflow and separately validate skill discovery, scope, versioning and delivery to both clients. T3 Code is an experience reference, not an approved dependency, packaging choice, or authorization for Owl Mast to launch agents.

Relevant Notion examples support these requirements without establishing current connector behavior. [Hermes operations](https://app.notion.com/p/40b8ce657080810bab5de84d9e2cbac0) records separate Jira connection needs and problems from loading all projects into global memory. [Syntelligence knowledge](https://app.notion.com/p/4098ce65708081458f2fc4ff5876ec72) distinguishes source identity from actual authorship and task completion from acceptance. [Movesion's check history](https://app.notion.com/p/40a8ce65708081ddb61bc40e35d6123a) illustrates successful-looking checks that did not run and lessons whose root-cause explanation later changed. These are historical workspace records, not fresh operational verification.

## Candidate mechanisms, not architecture decisions

OpenTelemetry transport and a trace backend such as Langfuse are evaluation options; neither supplies work identity or proves complete client coverage. MCP delivery and generated context files are possible client interfaces, subject to the selected delivery requirements. Git-backed reviewed guidance, source pointers and selective retrieval may reduce migration and maintenance work.

OKF offers a candidate portable representation and retrieval component; its [convention](https://github.com/okf-memory/okf-agent-memory/blob/develop/docs/spec/CONVENTION.md) distinguishes knowledge from transcripts, preserves uncertainty and describes provenance and freshness. Operator Memory is another documentation-workflow candidate. Neither is selected, and using both requires clear ownership. Kody, CodeMie, Visdom and PAPI remain references or integration candidates, not an approved combined stack.

[Visdom Context Fabric](https://visdom.virtuslab.com/platform/context-fabric) and [AI Tracing](https://visdom.virtuslab.com/platform/ai-tracing) demonstrate documented overlap in contextual knowledge and development evidence. Their broader controls do not expand Owl Mast's first-version authority.

## Architecture validation work

Validate the following against real supported configurations before promising integration coverage:

- Establish Syntelligence's Jira connection and GitHub, and Movesion's separate Jira connection and Bitbucket; confirm deployment variants, account boundaries and authorized data access. Include connection identity in correlation so identical issue keys or repository names cannot collide.
- Inspect Claude, Codex and Hermes versions and available events. Validate outbound observation/export contracts separately from inbound automation hooks. Record observed versus inferred initiation, execution and contribution links; show unsupported fields and ambiguous attribution.
- Exercise retries, duplicate and late events, disconnected sources, changed tickets/PRs and reconciliation. Keep missing telemetry distinguishable from zero activity.
- Test retrieval and evidence access across both projects, including restricted source records, explicit company promotion and later withdrawal. Shared credentials require particular scrutiny: [CodeMie's FAQ](https://docs.codemie.ai/admin/faq/) documents a model that does not recheck each viewer's original source permissions.
- Demonstrate existing Hermes-to-Notion continuity and successful reuse by another contributor's agent. Collect evidence of usefulness and remaining manual work. Observation credentials must not introduce agent execution authority.

## Measurement methods

Measure organization/project setup separately from fresh contributor/agent enrollment. Record elapsed and active time, manual steps, prerequisites, failures and time to the first useful project action. Repeat for both customer environments. Measure finding a colleague's work without a recap and retrieving a useful sourced lesson; capture correctness and usefulness feedback, not merely retrieval counts.

Report attribution coverage with explicit denominators, unknown buckets and collection windows. Distinguish participation from causal credit, and accepted work from deployed or outcome-verified work. [T3's usage documentation](https://github.com/pingdotgg/t3code/blob/main/docs/user/usage.md) supports separating API-equivalent estimates from subscription bills and exposing unavailable history. Counter-metrics include stale guidance, repeated failures, irrelevant context, review delay and maintenance effort. Numeric time and outcome targets remain unconfirmed; establish baselines and agree thresholds before claiming pilot success or ROI.

## Licensing and portability

Open-source direction does not select Owl Mast's license. Evaluate candidate licenses, dependencies and redistribution obligations before reuse. The research records permissive and restricted candidates; recheck selected versions. [PAPI's Trust page](https://getpapi.ai/trust) distinguishes public guides/install components from its closed dashboard and hosted engine, and documents project exports. Evaluate export completeness, scope, identifiers, provenance and reconstructability independently of source availability. No publication or access change follows from this addendum.
