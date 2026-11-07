"""T3 task receipts.

The coordinator passes the receipt of each ``delegate_task`` call (its ``taskId`` and the
``target`` it actually used). The tool admits only receipts that name the policy target
exactly, including the effort option, so a delegated run that silently fell back to another
model or effort cannot advance a story.

Executions are ``(taskId, runId)`` pairs. ``taskId`` is the ``task_cancel`` handle and is
never replaced by a run id; ``runId`` is the execution of that task this receipt is for.
Canonical receipt shape (fields beyond these are ignored)::

    {"taskId": "node:…", "runId": "run:…", "providerInstanceId": "claudeAgent",
     "model": "claude-fable-5-1", "options": {"effort": "high"} | [{"id","value"}],
     "isolation": "worktree"}

``runId`` is the run this receipt reports; a fresh ``delegate_task`` receipt carries it as
``childRunId`` (accepted when ``runId`` is absent). When both are present and differ, the
receipt is ambiguous unless the task is a *retained* owner being re-run: then ``runId`` (the
current run) wins and ``childRunId`` is the stale first run. A retained task may be re-run
only for an implementer repair of the same story, only by the task that owns the story, and
only with a run never bound before; reviewer tasks are never reused.
"""

from __future__ import annotations

from .errors import ReceiptInvalid
from .policy import Target

REQUIRED_KEYS = ("taskId", "providerInstanceId", "model")


def _options(raw) -> dict[str, str]:
    if raw is None:
        return {}
    if isinstance(raw, dict):
        return {str(k): str(v) for k, v in raw.items()}
    if isinstance(raw, list):
        out = {}
        for entry in raw:
            if not isinstance(entry, dict) or "id" not in entry or "value" not in entry:
                raise ReceiptInvalid("receipt options list entries need id and value")
            out[str(entry["id"])] = str(entry["value"])
        return out
    raise ReceiptInvalid("receipt options must be a mapping or a list of {id, value}")


def execution_run_id(receipt: dict, retained: bool = False) -> str:
    """The run this receipt is for. Missing or ambiguous run identity refuses; nothing is guessed."""
    run_id, child_run = receipt.get("runId"), receipt.get("childRunId")
    if run_id and child_run and str(run_id) != str(child_run) and not retained:
        raise ReceiptInvalid(f"receipt names two runs (runId {run_id}, childRunId {child_run}) for a task that is not a retained owner; run identity is ambiguous", code="run-identity-ambiguous")
    chosen = run_id or child_run
    if not chosen:
        raise ReceiptInvalid("receipt carries no run identity (runId or childRunId); the execution cannot be identified and nothing is inferred", code="run-identity-missing")
    return str(chosen)


def validate_receipt(receipt: dict, target: Target, role: str, used_task_ids: set[str] = frozenset(), used_executions: set[tuple[str, str]] = frozenset(), retained_task: str | None = None) -> dict:
    """``retained_task`` (implementer repairs only) is the one task id that may be bound again,
    for a run never bound before. Every other reuse of a task id is refused."""
    if not isinstance(receipt, dict):
        raise ReceiptInvalid(f"{role} receipt must be a JSON object")
    missing = [k for k in REQUIRED_KEYS if not receipt.get(k)]
    if missing:
        raise ReceiptInvalid(f"{role} receipt lacks {missing}", missing=missing)
    task_id = str(receipt["taskId"])
    retained = retained_task is not None and task_id == retained_task
    if task_id in used_task_ids and not retained:
        raise ReceiptInvalid(f"{role} receipt reuses task {task_id}; each turn needs a fresh T3 task", task_id=task_id)
    run_id = execution_run_id(receipt, retained)
    if (task_id, run_id) in used_executions:
        raise ReceiptInvalid(f"{role} receipt replays execution ({task_id}, {run_id}); that run was already bound", code="execution-replayed", task_id=task_id, run_id=run_id)
    provider, model = str(receipt["providerInstanceId"]), str(receipt["model"])
    if provider != target.provider or model != target.model:
        raise ReceiptInvalid(f"{role} receipt targets {provider}/{model}; policy requires {target.provider}/{target.model}")
    options = _options(receipt.get("options"))
    for key, value in target.options.items():
        if options.get(key) != value:
            raise ReceiptInvalid(f"{role} receipt option {key}={options.get(key)!r}; policy requires {value!r}", option=key)
    if target.isolation and str(receipt.get("isolation", "")) != target.isolation:
        raise ReceiptInvalid(f"{role} receipt isolation {receipt.get('isolation')!r}; policy requires {target.isolation!r}")
    return {"taskId": task_id, "runId": run_id, "providerInstanceId": provider, "model": model, "options": options, "isolation": str(receipt.get("isolation", "")), "role": role, "title": str(receipt.get("title", "")), "retained": retained}
