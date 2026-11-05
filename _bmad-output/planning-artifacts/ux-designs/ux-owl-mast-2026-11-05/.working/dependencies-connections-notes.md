# Dependencies and Connections author notes

## Added reference: dependencies.html

All ticket/PR records, machine names and timestamps in these two references are illustrative. Dependencies uses source-qualified Syntelligence Jira SYN-40, SYN-42, SYN-48 and Syntelligence GitHub PR #118; it claims no real cross-source association.

- An explicit prerequisite points toward its dependent ticket; a contribution points from its PR toward the ticket. Possible dependency uses a dashed edge and never establishes a blocker.
- Relation filtering updates both diagram edges and evidence-list rows. Node buttons and the selection control update the selected detail. Every diagram relationship has an equivalent keyboard-accessible evidence disclosure with event and collection times.
- Phone opens in List view; Graph is optional and scrolls within its own container. Graph and selected-node content do not imply editing controls.
- Counts always say they are counted from records the viewer can access. No restricted placeholders, hidden counts or inaccessible identities are fixtures in the DOM.
- Closed tickets and merged PRs do not establish acceptance. Alternate states cover cycles, empty filtered results, unavailable collection and unavailable access.
- Storage choice remains an architecture question; no graph database was selected.

## Expanded reference: connections.html

- Existing stable clients remain CL-17, CX-16, CL-8 and CX-4. Owl aliases, marker colors, validation examples, readiness, source failure and existing Notion workflow sections remain.
- Added per-client machine/sandbox name, last-observed time, permitted underlying machine ID, configured profile and observed client/machine association. Current execution remains unknown from connection readiness alone.
- Enrollment shows a proposed machine context for an existing client; it does not launch or route work.
- Historical run evidence retains the machine at that time when a client changes location. Matching names or aliases never merge clients. A machine label does not claim security isolation.
- No machine evidence is Not observed; stale evidence cannot claim current location; revoked source access removes identity and location without hidden-machine disclosures.

## Author verification

Both files pass duplicate-ID, ARIA-target and local-link checks. Dependencies JavaScript passes `node --check`; all Owl fallback variables are defined in both files. Dependencies is 19,921 bytes. Rendering and interaction review is owned by the parent integration task.
