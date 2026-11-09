# Deferred work

- source_spec: `_bmad-output/implementation-artifacts/spec-gh-108-resolve-review-findings.md`
  summary: Key the activation use ledger on the document digest in a fixed per-machine location instead of (or in addition to) the file path, so a byte-identical copy of an approved activation under another name cannot create a second live run.
  evidence: Blind Hunter review of the PR #108 follow-up (2026-11-09): `record_activation_use` writes `<path>.used.json`, so `cp approved.toml approved2.toml` yields a fresh ledger; the limit is documented in `docs/unattended-execution.md` and the ledger docstring. A machine-wide location needs a test-overridable root (environment variable or policy field) and a decision on where approved activations live.
