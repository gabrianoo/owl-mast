"""T3 task receipts.

The coordinator passes the receipt of each ``delegate_task`` call (its ``taskId`` and the
``target`` it actually used). The tool admits only receipts that name the policy target
exactly, including the effort option, so a delegated run that silently fell back to another
model or effort cannot advance a story.
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


def validate_receipt(receipt: dict, target: Target, role: str, used_task_ids: set[str] = frozenset()) -> dict:
    if not isinstance(receipt, dict):
        raise ReceiptInvalid(f"{role} receipt must be a JSON object")
    missing = [k for k in REQUIRED_KEYS if not receipt.get(k)]
    if missing:
        raise ReceiptInvalid(f"{role} receipt lacks {missing}", missing=missing)
    task_id = str(receipt["taskId"])
    if task_id in used_task_ids:
        raise ReceiptInvalid(f"{role} receipt reuses task {task_id}; each turn needs a fresh T3 task", task_id=task_id)
    provider, model = str(receipt["providerInstanceId"]), str(receipt["model"])
    if provider != target.provider or model != target.model:
        raise ReceiptInvalid(f"{role} receipt targets {provider}/{model}; policy requires {target.provider}/{target.model}")
    options = _options(receipt.get("options"))
    for key, value in target.options.items():
        if options.get(key) != value:
            raise ReceiptInvalid(f"{role} receipt option {key}={options.get(key)!r}; policy requires {value!r}", option=key)
    if target.isolation and str(receipt.get("isolation", "")) != target.isolation:
        raise ReceiptInvalid(f"{role} receipt isolation {receipt.get('isolation')!r}; policy requires {target.isolation!r}")
    return {"taskId": task_id, "providerInstanceId": provider, "model": model, "options": options, "isolation": str(receipt.get("isolation", "")), "role": role, "title": str(receipt.get("title", ""))}
