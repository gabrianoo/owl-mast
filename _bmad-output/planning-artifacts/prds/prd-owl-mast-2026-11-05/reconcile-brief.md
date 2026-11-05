# Input reconciliation — product brief

Source: `../../briefs/brief-owl-mast-2026-11-05/brief.md`, read in full. Compared with `prd.md` and `addendum.md` on 2026-11-05. This pass reconciles this source only; it does not independently validate the other input documents, Notion, integrations, or research claims.

## Verdict

No material source omission or reversal of a confirmed decision. Two small acceptance-language inconsistencies deserve clarification. Pending operating-surface, enrollment and knowledge-policy decisions are already disclosed and are not new findings.

## Findings

### R-B1 — Distinguish valid incomplete observation from pilot acceptance

- **Source:** `brief.md:59` requires tracing a work item through an agent run, repository contribution and acceptance in each toolchain.
- **Current text:** `prd.md:96` allows the connector demonstration to include actual acceptance evidence **or an explicit absence of it**. The integration table at `prd.md:244–245` and SM-4 at `prd.md:259` still require an acceptance evidence chain.
- **Implication:** Honest absence is a correct product state, but a reader could treat it as satisfying the required end-to-end pilot proof.
- **Suggested resolution:** State that an explicit absence is a supported observation state and does not replace the acceptance-evidence case required for each project's pilot demonstration.
- **Severity:** Medium clarification; requirement coverage exists elsewhere.

### R-B2 — Preserve time to first useful project action as the onboarding outcome

- **Source:** `brief.md:61` calls for time and manual steps from fresh agent setup to its first useful project action.
- **Current text:** `prd.md:71,257` instead centers time to first useful knowledge delivery. `addendum.md:45` preserves the original first-useful-project-action measure, and FR-11/SM-3 separately distinguish delivery from actual reuse.
- **Implication:** No source idea was lost, but the primary acceptance metric stops earlier than the source's outcome while its stronger measure sits in supporting material.
- **Suggested resolution:** Record delivery readiness as an intermediate onboarding milestone and retain time to first useful project action as an outcome measure. Exact thresholds remain pending as already acknowledged.
- **Severity:** Low clarification; the addendum and reuse requirements retain the intent.

## Coverage and qualitative reconciliation

| Source requirement or intent | Coverage |
| --- | --- |
| Open source; AISQUAD first; commercialization and sandboxing deferred (`brief.md:14–18,65`) | PRD §§0–1, FR-20, §5 and license follow-up preserve the direction and exclusions. |
| Observe and deliver knowledge; existing tools control execution; authorized knowledge writes remain allowed (`brief.md:14`) | PRD FR-8–FR-14 and FR-19 distinguish these responsibilities. |
| Mohamed's parallel-agent contributions become hard to understand or reuse; Discord/Hermes workaround; minimal onboarding (`brief.md:24`) | PRD vision, SC-1/SC-2, FR-2 and metrics preserve the concrete pain and low-setup intent. |
| Both real projects, distinct Jira connections, GitHub and Bitbucket; sequential implementation allowed (`brief.md:26–34,46`) | PRD FR-1, FR-5 and §5 explicitly require both; other tools/AWS remain context rather than invented connectors. |
| Cross-project humans/agents and AISQUAD asset ownership do not grant blanket access (`brief.md:18,22,31`) | PRD vocabulary, attribution, FR-12, FR-15, FR-17 and risk/access constraints retain the distinction. |
| Track source-qualified work, initiation/delegation and acceptance; keep trackers authoritative (`brief.md:48–49`) | PRD FR-4–FR-7 and NFR-2 cover the evidence model and uncertainty. |
| Skills, memories, selected chat evidence; raw versus reusable knowledge; preserve Hermes/Notion (`brief.md:32,50`) | PRD FR-8–FR-14 and FR-18 cover capture/lifecycle and explicitly flag transcript default policy as an assumption. |
| Project-default knowledge and explicit company promotion (`brief.md:40,51`) | PRD SC-2/SC-3, FR-10/FR-12/FR-17 and boundary proof preserve policy; authority and validation remain pending. |
| Progress/dependencies, usage/cost coverage; estimates separate from billing/subscription allocation (`brief.md:52`) | PRD FR-6, FR-7, FR-15/FR-16 and counter-metrics retain the distinction. |
| Work-understanding, knowledge reuse, project boundaries, unattended failure discovery and counter-metrics (`brief.md:59–61`) | PRD §6 covers all, subject to the two clarifications above. |
| Web/harness assumption, unselected instrumentation/components, unknown deployment/license/thresholds, limited screenshot evidence (`brief.md:42,53,55,67,71`) | PRD pending choices and bounded follow-up plus addendum preserve the unknowns and evidence limitations. |

The source's emphasis on avoiding a manual recap, easing adoption across teams, and connecting observation to actual reusable learning survives the requirement structure. No additional qualitative loss was identified. Added specificity in the PRD is presented as requirements elaboration or marked assumptions, not as evidence that connectors or user outcomes have already been validated.
