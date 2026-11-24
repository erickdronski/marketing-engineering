"""Read the workspace's chronological decision records."""

import json

from .errors import MktgError
from .workspace import atomic_write, scoped


def read(root):
    path = scoped(root, "log/ledger.jsonl")
    if not path.exists():
        return []
    rows = []
    for line_no, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        try:
            row = json.loads(line)
            if not isinstance(row, dict) or not isinstance(row.get("event"), str):
                raise TypeError("event must be a string")
            for name in ("item", "claim", "action", "channel", "sha256", "review_sha256", "ts"):
                if name in row and (not isinstance(row[name], str) or not row[name].strip()):
                    raise TypeError(f"{name} must be nonempty text")
            if "version" in row and (type(row["version"]) is not int or row["version"] < 1):
                raise ValueError("version must be a positive integer")
        except (ValueError, TypeError) as exc:
            raise MktgError(f"line {line_no}: {exc}", path="log/ledger.jsonl") from exc
        rows.append(row)
    return rows


def append(root, event):
    if not isinstance(event.get("event"), str):
        raise MktgError("missing ledger event name")
    path = scoped(root, "log/ledger.jsonl")
    previous = path.read_text(encoding="utf-8") if path.exists() else ""
    separator = "\n" if previous and not previous.endswith("\n") else ""
    atomic_write(path, previous + separator + json.dumps(event, ensure_ascii=False, allow_nan=False) + "\n")
