# Brief input reconciliation

2026-11-05; reconciled against the current draft spines and UX-01–UX-13 in [.memlog.md](.memlog.md). This records input coverage; it is not the optional reviewer gate or proof of an implemented experience.

Inputs: [brief](../../briefs/brief-owl-mast-2026-11-05/brief.md), [addendum](../../briefs/brief-owl-mast-2026-11-05/addendum.md), [decision log](../../briefs/brief-owl-mast-2026-11-05/.memlog.md), and [extraction](.working/source-brief-references.md). Finalized PRD and later confirmed UX decisions supersede older proposals.

| Source idea | Disposition | Draft location / explanation |
|---|---|---|
| Open source; AISQUAD first; humans and agents across both projects | Retained | EXPERIENCE Foundation; IA company/project scope; J2. Ownership is not broadened read access. |
| Separate Syntelligence Jira + GitHub and Movesion Jira + Bitbucket | Retained | EXPERIENCE J2 and `scope-bar`; distinct source accounts/keys, independent source failures, both clients in both projects. |
| Mohamed's contributions become understandable without a recap | Retained and refined | EXPERIENCE SC-1 and S1/S2; later UX-05 sets tickets closed → blockers → measured progress as the desired order. |
| Distinguish initiator, human/agent contribution, evidence, blockers and uncertainty | Retained | EXPERIENCE `work-record`, `evidence-detail`, State Patterns, and Evidence semantics; DESIGN corresponding components. |
| Newly connected agents benefit from another contributor's learning | Retained and refined | EXPERIENCE SC-2 and S3–S5. UX-08 selects agent search on demand; automatic injection is explicitly excluded as the default. Receipt and demonstrated reuse remain separate. |
| Low recurring onboarding effort | Retained | EXPERIENCE Foundation and J2; observation/delivery readiness are independent. A-5 remains a proposed step ceiling, not a validated capability. |
| Minimize initial connection work | Superseded by later direction | EXPERIENCE Foundation permits complex initial administrator work; J2 separates it from recurring contributor enrollment. This is not an accidental loss. |
| Shared web interface and harness integrations | Earlier assumption resolved/adapted | UX-01 confirms a dedicated UI on laptop/tablet/phone. EXPERIENCE Foundation/Responsive leave browser/PWA/native packaging and actual integration mechanism to architecture. |
| Hermes-to-Notion and current knowledge workflows | Retained | EXPERIENCE Foundation, Knowledge semantics and SC-2; preserve origin, avoid duplicate saves/silent overwrite, and distinguish successful writing from unverified skill reading. |
| Project-default knowledge with explicit company promotion | Retained and refined | EXPERIENCE Promotion semantics and SC-3 retain scoped, versioned publication. Current preferred automatic mode plus manual/disabled supersedes a human-only reading of the older brief. UX-09 names project-designated maintainers for exceptions/manual review. |
| Permissions, source identity and company ownership remain distinct | Retained | EXPERIENCE Foundation, scope changes, State Patterns, SC-3 and notification reentry. Hidden-source counts and origin excerpts do not leak through aggregates or promoted content. |
| Work observation and knowledge delivery, without agent execution | Retained; later conflict resolved explicitly | EXPERIENCE Foundation, `external-link`, J1/J8 and UX-06. Replies/assignments/launch controls stay in existing tools; permitted knowledge/admin actions remain possible. |
| Trace work to runs, changes and acceptance; show unmapped/incomplete data | Retained | EXPERIENCE SC-1, Evidence semantics, J6; DESIGN `evidence-detail` and `usage-breakdown`. |
| Costs/usage are not bills or proof of productivity/ROI | Retained | EXPERIENCE Usage semantics and J6; DESIGN Typography and `usage-breakdown`. |
| Discover observed blockers or failures even when no one is watching | Retained and refined | EXPERIENCE S1 attention, S9/J7 and UX-10 every-observed-update push. Stale telemetry cannot create a fabricated blocker. |
| Measure time-to-understand, onboarding effort, learning reuse and coverage | Retained by upstream reference | EXPERIENCE source authority, SC-1/SC-2/J2/J6 and inherited A-5/A-6. No numeric target or completed pilot outcome is invented. |
| Commercialization, sandboxing and predictive allocation later | Deferred upstream scope | Spines do not add these surfaces or imply a license/deployment choice. EXPERIENCE Foundation keeps technical packaging open. |

No essential brief idea was silently dropped, and no unsupported capability claim was found in this reconciliation. Current additions—separate assigned-to-me Focus, concurrent epic visibility, accepted displayed colors/mobile appearance/logo, demand-driven search, designated maintainers, and every-update push—are consistent with the recorded later decisions. Focus layout mechanics remain proposals and its mock is a known pending artifact.

## Finalization addendum — 2026-11-05

The earlier pending Focus/reference statements describe the reconciliation snapshot. All ten surfaces now have visual references, with a separate shared navigation/company example. Review dispositions cover the later UX-15 identity chips, UX-17 contextual cost, explicit system quarantine (FR-13), and derivative permissions. Original A-1–A-6 remain unconfirmed. See [review disposition](review-disposition.md).
