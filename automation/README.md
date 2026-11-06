# automation

Engineering automation for Owl Mast, separate from the product backend.

- `unattended/` — the unattended execution foundation (ENG-01): GitHub-authoritative dispatch, synchronization and T3 coordination policy. Every state command refuses the real GitHub transport until the T3 execution protocol and a bounded credential are qualified; the foundation is not qualified for unattended use. Guide: [docs/unattended-execution.md](../docs/unattended-execution.md).
- `policy.toml` — default policy (empty allowlist: nothing dispatchable). `examples/first-run-om-01-02.toml` is the candidate first activation.
- `tests/` — stdlib `unittest` qualification suite with an in-memory GitHub transport and the real backlog snapshot fixture. Run `python3 -m unittest discover -s automation/tests -t .` from the repository root (Python 3.12, no dependencies). `tests/test_final_findings.py` covers the six defects of the final PR #107 disposition; `PYTHONPATH=. python3 automation/tests/probe_final_findings.py` re-runs those scenarios as a readable transcript.
